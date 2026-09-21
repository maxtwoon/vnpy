"""Normalisation of raw source rows into canonical bar dictionaries.

Canonical row shape (all importers emit this to the sink)::

    {
        "instrument": str,            # original source symbol, case preserved
        "exchange": str | None,       # original exchange code, never guessed
        "series_kind": str,           # instrument|continuous_888|continuous_777|...
        "bar_start_ns": int | None,   # UTC ns; None when label semantics unknown
        "bar_end_ns": int | None,     # UTC ns
        "trading_date": str | None,   # "YYYY-MM-DD"; None when not derivable
        "source_label": str,          # original timestamp label, untouched
        "open": float | None, "high": ..., "low": ..., "close": ...,
        "volume": float | None,
        "turnover": float | None,     # source amount preserved raw
        "open_interest": float | None,
        "extensions": dict[str, Any], # every non-standard source column, raw
        "quality_flags": list[str],   # e.g. ["nonfinite:open", "negative:volume"]
        "provenance": dict[str, Any], # locator/batch/adapter/config identity
    }

Rules enforced here (from the execution contract):

* Missing values stay ``None``; they are NEVER filled with 0 or forward fill.
* Non-finite floats (NaN/inf) become ``None`` plus an explicit quality flag.
* RQ minute labels are END labels: 09:31 covers 09:30-09:31, so
  ``bar_end = label`` and ``bar_start = label - interval``. No midday or
  overnight filler bars are generated.
* Daily bars key on ``trading_date`` (the source date), never UTC midnight.
* SSQuant label semantics are UNVERIFIED: bar bounds stay ``None`` and the
  ``source_time_label_unknown`` flag is set; no conversion is guessed.
* Source amounts/OI units are preserved as-is in ``turnover``/extensions.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_UTC = timezone.utc

PRICE_FIELDS = ("open", "high", "low", "close")
_OHLCV_FIELDS = PRICE_FIELDS + ("volume", "turnover", "open_interest")

_NS_PER_SECOND = 1_000_000_000

LABEL_EVIDENCE_UNKNOWN = "source_time_label_unknown"
LABEL_EVIDENCE_OUT_OF_SCOPE = "outside_label_evidence_scope"


def to_float(value: Any) -> float | None:
    """Convert a raw source value to float.

    Empty/None -> ``None`` (explicit missing). Non-finite -> ``None`` as well,
    but the caller adds a quality flag via :func:`nonfinite_flag` first when
    the raw text was a valid non-finite token.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text == "" or text.lower() in {"nan", "none", "null", "na"}:
            return None
        return float(text)
    result = float(value)
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def raw_is_nonfinite(value: Any) -> bool:
    """True when the raw value parses to a non-finite float."""
    if value is None:
        return False
    try:
        result = float(value)
    except (TypeError, ValueError):
        return False
    return math.isnan(result) or math.isinf(result)


def parse_label(label: str) -> datetime:
    """Parse a source timestamp label (``YYYY-MM-DD[ HH:MM[:SS]]``)."""
    label = label.strip()
    if " " in label:
        return datetime.strptime(label, "%Y-%m-%d %H:%M:%S")
    return datetime.strptime(label, "%Y-%m-%d")


def shanghai_to_utc_ns(local: datetime) -> int:
    """Convert a naive Shanghai-local datetime to UTC epoch nanoseconds."""
    aware = local.replace(tzinfo=SHANGHAI_TZ)
    return int(aware.timestamp() * _NS_PER_SECOND)


def end_label_bounds_ns(label: datetime, interval_minutes: int) -> tuple[int, int]:
    """Convert an END-labelled minute bar to half-open UTC ns bounds.

    ``label`` 09:31 with 1m interval -> start 09:30:00, end 09:31:00 local.
    """
    end_local = label
    start_local = end_local - timedelta(minutes=interval_minutes)
    return shanghai_to_utc_ns(start_local), shanghai_to_utc_ns(end_local)


def daily_bounds_ns(day_label: datetime) -> tuple[int, int]:
    """Calendar-day half-open bounds for a daily bar (Shanghai local)."""
    start_local = day_label
    end_local = day_label + timedelta(days=1)
    return shanghai_to_utc_ns(start_local), shanghai_to_utc_ns(end_local)


def base_row(
    instrument: str,
    source_label: str,
    provenance: dict[str, Any],
    exchange: str | None = None,
    series_kind: str = "instrument",
) -> dict[str, Any]:
    """Build the canonical row skeleton with all value fields ``None``."""
    return {
        "instrument": instrument,
        "exchange": exchange,
        "series_kind": series_kind,
        "bar_start_ns": None,
        "bar_end_ns": None,
        "trading_date": None,
        "source_label": source_label,
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "volume": None,
        "turnover": None,
        "open_interest": None,
        "extensions": {},
        "quality_flags": [],
        "provenance": provenance,
    }


def apply_numeric_fields(
    row: dict[str, Any], raw: dict[str, Any], fields: dict[str, str]
) -> None:
    """Map ``canonical field -> source column`` and fill numeric values.

    Missing source columns and empty strings stay ``None``. Non-finite raw
    values add a ``nonfinite:<field>`` flag and the value becomes ``None``.
    Negative values are preserved and flagged ``negative:<field>``; the
    importer never zeroes them (repairs are the repair index's business).
    """
    for field, column in fields.items():
        if column not in raw:
            continue
        raw_value = raw[column]
        if raw_is_nonfinite(raw_value):
            row["quality_flags"].append(f"nonfinite:{field}")
            continue
        value = to_float(raw_value)
        if value is None:
            continue
        if value < 0:
            row["quality_flags"].append(f"negative:{field}")
        row[field] = value


def _rq_provenance(
    archive: str, member: str, batch_id: str, adapter: str
) -> dict[str, Any]:
    return {
        "source_id": "rqdatac",
        "archive": archive,
        "member": member,
        "batch_id": batch_id,
        "adapter": adapter,
    }


def normalize_rq_etf_row(
    raw: dict[str, str],
    interval_minutes: int,
    archive: str,
    member: str,
    batch_id: str,
) -> dict[str, Any]:
    """Normalise one RQ ETF/LOF bar row.

    RQ minute ``datetime`` is an END label (README + verified sample
    09:31 first bar). Daily rows carry a plain date whose key is the
    trading date itself. ``num_trades`` is kept in extensions.
    """
    instrument = raw["order_book_id"]
    label = parse_label(raw["datetime"] if "datetime" in raw else raw["date"])
    row = base_row(
        instrument=instrument,
        source_label=raw.get("datetime") or raw.get("date", ""),
        provenance=_rq_provenance(archive, member, batch_id, "rq_etf"),
        exchange=instrument.split(".")[-1] if "." in instrument else None,
        series_kind="instrument",
    )
    if interval_minutes == 0:  # daily
        start_ns, end_ns = daily_bounds_ns(label)
        row["trading_date"] = label.strftime("%Y-%m-%d")
    else:
        start_ns, end_ns = end_label_bounds_ns(label, interval_minutes)
        row["trading_date"] = label.strftime("%Y-%m-%d")
    row["bar_start_ns"] = start_ns
    row["bar_end_ns"] = end_ns
    apply_numeric_fields(
        row,
        raw,
        {
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "turnover": "amount",
        },
    )
    if "num_trades" in raw:
        trades = to_float(raw["num_trades"])
        if trades is not None:
            row["extensions"]["num_trades"] = trades
    return row


_JQ_OHLCV = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "turnover": "money",
}

_JQ_EXTENSION_COLUMNS = (
    "pre_close",
    "high_limit",
    "low_limit",
    "paused",
    "factor",
    "market_cap",
    "circulating_market_cap",
    "turnover_ratio",
    "pe_ratio",
    "pb_ratio",
    "ps_ratio",
    "industry_sw_l1",
    "industry_sw_l2",
    "is_st",
    "change_pct",
    "net_amount_main",
    "net_pct_main",
    "net_amount_xl",
    "net_pct_xl",
    "net_amount_l",
    "net_pct_l",
    "net_amount_m",
    "net_pct_m",
    "net_amount_s",
    "net_pct_s",
)


def normalize_jq_daily_row(
    raw: dict[str, str], archive: str, batch_id: str
) -> dict[str, Any]:
    """Normalise one JoinQuant holographic daily row (33 columns).

    All 33 source columns are preserved: OHLCV into canonical fields, the
    remaining 27 into ``extensions`` untouched (strings stay strings, empty
    stays empty). ``factor`` is 1.0 across the whole archive, so adjustment
    stays UNKNOWN at the dataset semantic level; the factor value itself is
    recorded verbatim in extensions. ``paused`` is preserved verbatim;
    suspended/placeholder states are never converted to volume-0 filler.
    """
    instrument = raw["code"]
    label = parse_label(raw["date"])
    row = base_row(
        instrument=instrument,
        source_label=raw["date"],
        provenance={
            "source_id": "joinquant",
            "archive": archive,
            "batch_id": batch_id,
            "adapter": "jq_daily",
        },
        exchange=instrument.split(".")[-1] if "." in instrument else None,
        series_kind="instrument",
    )
    start_ns, end_ns = daily_bounds_ns(label)
    row["bar_start_ns"] = start_ns
    row["bar_end_ns"] = end_ns
    row["trading_date"] = raw["date"]
    apply_numeric_fields(row, raw, _JQ_OHLCV)
    for column in _JQ_EXTENSION_COLUMNS:
        if column in raw:
            row["extensions"][column] = raw[column]
    row["extensions"]["adjustment_status"] = "unknown_factor_all_one"
    return row


_SSQUANT_NUMERIC = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "turnover": "amount",
    "open_interest": "openint",
}

_SSQUANT_PASSTHROUGH = (
    "cumulative_openint",
    "open_askp",
    "open_bidp",
    "close_askp",
    "close_bidp",
    "B",
    "S",
)


def normalize_ssquant_row(
    raw: dict[str, Any],
    table: str,
    batch_id: str,
    series_kind: str,
    label_profile: Any = None,
) -> dict[str, Any]:
    """Normalise one SSQuant bar row read from a captured SQLite table.

    SSQuant time-label semantics are unverified by default: without a scoped
    :class:`~research_store.importers.time_evidence.LabelProfile`,
    ``bar_start_ns``/``bar_end_ns`` stay ``None`` with flag
    ``source_time_label_unknown`` and ``trading_date`` stays ``None`` (night
    sessions cannot be attributed to a trading day without a calendar).

    With a profile whose capture/symbol/range covers this row, the evidenced
    convention (START or END) produces real half-open bounds and the
    evidence id is recorded in extensions; ``trading_date`` still stays
    ``None`` without calendar evidence. A profile that does NOT cover the row
    adds ``outside_label_evidence_scope`` — the row stays an honest candidate.

    ``real_symbol``, Chinese position columns and every other raw column are
    preserved in extensions exactly as stored, including their original
    (possibly GBK-decoded) names. ``openint`` is source OI, not total OI;
    ``cumulative_openint`` is the candidate total OI, both kept separately.
    ``amount`` is untrusted per vendor audit; it is preserved raw, never
    multiplied by a guessed factor.
    """
    instrument = str(raw.get("symbol", ""))
    label = str(raw.get("datetime", ""))
    row = base_row(
        instrument=instrument,
        source_label=label,
        provenance={
            "source_id": "ssquant",
            "table": table,
            "batch_id": batch_id,
            "adapter": "ssquant",
        },
        exchange=None,
        series_kind=series_kind,
    )
    if label_profile is None:
        row["quality_flags"].append("source_time_label_unknown")
    elif label_profile.covers(table, label):
        parsed = parse_label(label)
        minutes = int(label_profile.interval_minutes)
        if label_profile.conclusion == "end":
            row["bar_start_ns"], row["bar_end_ns"] = end_label_bounds_ns(
                parsed, minutes
            )
        else:
            row["bar_start_ns"] = shanghai_to_utc_ns(parsed)
            row["bar_end_ns"] = shanghai_to_utc_ns(
                parsed + timedelta(minutes=minutes)
            )
        row["extensions"]["label_evidence"] = label_profile.evidence.evidence_id
    else:
        row["quality_flags"].append("source_time_label_unknown")
        row["quality_flags"].append("outside_label_evidence_scope")
    row["quality_flags"].append("trading_date_unknown_no_calendar")
    apply_numeric_fields(row, raw, _SSQUANT_NUMERIC)
    for column in _SSQUANT_PASSTHROUGH:
        if column in raw:
            row["extensions"][column] = raw[column]
    for key, value in raw.items():
        if key not in {"symbol", "datetime"} and key not in _SSQUANT_NUMERIC and key not in _SSQUANT_PASSTHROUGH:
            row["extensions"][key] = value
    if "amount" in raw and row["turnover"] is not None:
        row["extensions"]["amount_untrusted"] = True
    return row


_FUTURES_LABEL_CONCLUSIONS = ("start", "end")


@dataclass(frozen=True)
class FuturesLabelScope:
    """Typed, explicitly supplied minute-label evidence for RQ futures.

    The default RQ futures minute semantics are UNKNOWN (see
    :func:`normalize_rq_futures_row`); canonical bounds exist only when a
    caller supplies independently reviewed evidence through this typed
    scope. The scope is deliberately narrow:

    * bound to one dataset (e.g. ``contract_1m_none``), one archive file
      name, one member path and one exact instrument (or every instrument
      of the member when ``instrument`` is None);
    * bound to one frequency and one contiguous inclusive/exclusive
      source-label interval;
    * carry the immutable sha256 of the exact input archive and of the
      evidence document the conclusion derives from, so a scope can never
      bless rows of an unrelated file, and its own basis stays auditable.

    Malformed scopes raise at construction; mismatched or out-of-scope rows
    are never promoted (they stay unknown-label candidates). This class
    carries evidence, it never creates it: a scope whose basis is unproven
    (e.g. the 04IB-UNKNOWN A2505 window) must not be constructed for it.
    """

    conclusion: str
    source_id: str
    dataset: str
    archive: str
    member: str
    frequency: str
    interval_minutes: int
    label_start: str
    label_end: str
    input_sha256: str
    evidence_ref: str
    evidence_sha256: str
    instrument: str | None = None
    version: str = "futures_label_scope/1"

    def __post_init__(self) -> None:
        if self.conclusion not in _FUTURES_LABEL_CONCLUSIONS:
            raise ValueError(
                f"label conclusion must be one of {_FUTURES_LABEL_CONCLUSIONS}, "
                f"got {self.conclusion!r}"
            )
        for name in (
            "source_id",
            "dataset",
            "archive",
            "member",
            "frequency",
            "evidence_ref",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"FuturesLabelScope.{name} must be non-empty")
        if int(self.interval_minutes) <= 0:
            raise ValueError("FuturesLabelScope.interval_minutes must be positive")
        object.__setattr__(self, "interval_minutes", int(self.interval_minutes))
        try:
            start = parse_label(self.label_start)
            end = parse_label(self.label_end)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "FuturesLabelScope label bounds must be 'YYYY-MM-DD[ HH:MM[:SS]]'"
            ) from exc
        if start >= end:
            raise ValueError("FuturesLabelScope label_start must precede label_end")
        for name in ("input_sha256", "evidence_sha256"):
            digest = str(getattr(self, name) or "").lower()
            if len(digest) != 64 or any(
                char not in "0123456789abcdef" for char in digest
            ):
                raise ValueError(
                    f"FuturesLabelScope.{name} must be a 64-hex sha256 digest"
                )
            object.__setattr__(self, name, digest)
        if self.instrument is not None and not str(self.instrument).strip():
            raise ValueError(
                "FuturesLabelScope.instrument must be None or a non-empty symbol"
            )

    @property
    def identity(self) -> str:
        """Immutable content identity of this scope (for provenance)."""
        payload = {
            "version": self.version,
            "conclusion": self.conclusion,
            "source_id": self.source_id,
            "dataset": self.dataset,
            "archive": self.archive,
            "member": self.member,
            "instrument": self.instrument,
            "frequency": self.frequency,
            "interval_minutes": self.interval_minutes,
            "label_start": self.label_start,
            "label_end": self.label_end,
            "input_sha256": self.input_sha256,
            "evidence_ref": self.evidence_ref,
            "evidence_sha256": self.evidence_sha256,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def covers(
        self,
        *,
        dataset: str,
        archive: str,
        member: str,
        instrument: str,
        label: str,
    ) -> bool:
        """True when this exact row location and label sit inside the scope."""
        if dataset != self.dataset or archive != self.archive or member != self.member:
            return False
        if self.instrument is not None and str(instrument) != self.instrument:
            return False
        return self.label_start <= str(label)[:19] < self.label_end


def normalize_rq_futures_row(
    record: dict[str, Any],
    dataset: str,
    archive: str,
    member: str,
    batch_id: str,
    interval_minutes: int,
    label_scope: FuturesLabelScope | None = None,
) -> dict[str, Any]:
    """Normalise one RQ futures row from a Parquet member.

    ``contract_1m_none`` rows carry ``order_book_id`` (real contract) with no
    ``trading_date``; identity is the contract itself. ``dominant_*`` rows
    carry ``underlying_symbol`` + ``dominant_id``; both are preserved so the
    continuous-to-real mapping survives. The continuous roll/selection rule
    stays unknown (never qualified here).

    Minute label semantics default to UNKNOWN (FUTURES_TIME_REVIEW_04IB:
    neither START nor END is established for the supplied archives):
    ``bar_start_ns``/``bar_end_ns`` stay ``None`` with the standard
    ``source_time_label_unknown`` flag, so the StoreSink candidate path
    preserves the row with its original label and payload. No silent
    START/END choice, no guessed session opens, and no natural-date
    trading-day inference happens here. Only an explicit, scoped
    :class:`FuturesLabelScope` (conclusion ``"end"`` -> bounds
    ``[label-interval, label)``; ``"start"`` -> ``[label, label+interval)``)
    produces canonical bounds for the rows it covers; out-of-scope rows
    stay candidates. Daily rows keep their date-level semantics (calendar
    day bounds keyed on the source date) which do not depend on the minute
    label question.

    The source ``trading_date`` column (dominant rows) is transferred
    verbatim as date-level evidence independently of label qualification.
    """
    is_dominant = dataset.startswith("dominant_")
    instrument = (
        f"{record['dominant_id']}" if is_dominant else str(record["order_book_id"])
    )
    label_value = record["datetime"]
    if isinstance(label_value, str):
        label = parse_label(label_value)
        label_text = label_value
    else:
        label_text = str(label_value)
        label = parse_label(label_text[:19])
    row = base_row(
        instrument=instrument,
        source_label=label_text,
        provenance=_rq_provenance(archive, member, batch_id, "rq_futures"),
        exchange=None,
        series_kind="continuous_dominant" if is_dominant else "instrument",
    )
    if interval_minutes == 0:
        start_ns, end_ns = daily_bounds_ns(label)
        row["bar_start_ns"] = start_ns
        row["bar_end_ns"] = end_ns
    elif label_scope is not None and label_scope.covers(
        dataset=dataset,
        archive=archive,
        member=member,
        instrument=instrument,
        label=label_text,
    ):
        if label_scope.conclusion == "end":
            row["bar_start_ns"], row["bar_end_ns"] = end_label_bounds_ns(
                label, interval_minutes
            )
        else:
            row["bar_start_ns"] = shanghai_to_utc_ns(label)
            row["bar_end_ns"] = shanghai_to_utc_ns(
                label + timedelta(minutes=interval_minutes)
            )
        row["extensions"]["label_evidence"] = {
            "scope_identity": label_scope.identity,
            "conclusion": label_scope.conclusion,
            "evidence_ref": label_scope.evidence_ref,
            "evidence_sha256": label_scope.evidence_sha256,
            "input_sha256": label_scope.input_sha256,
        }
    else:
        row["quality_flags"].append(LABEL_EVIDENCE_UNKNOWN)
        if label_scope is not None:
            row["quality_flags"].append(LABEL_EVIDENCE_OUT_OF_SCOPE)
    apply_numeric_fields(
        row,
        record,
        {
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "turnover": "total_turnover" if "total_turnover" in record else "amount",
            "open_interest": "open_interest",
        },
    )
    if is_dominant:
        row["extensions"]["underlying_symbol"] = record.get("underlying_symbol")
        row["extensions"]["dominant_id"] = record.get("dominant_id")
        trading_date = record.get("trading_date")
        if trading_date is not None:
            row["trading_date"] = str(trading_date)[:10]
    else:
        row["quality_flags"].append("trading_date_unknown_no_calendar")
    return row
