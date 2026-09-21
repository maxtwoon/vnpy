"""Shared helpers for the vnpy native bridges (Database and ResearchAlphaLab).

Owns the exact contracts that both consumers must implement identically:

* native interval <-> store interval mapping (5m/15m are never relabelled),
* source exchange-label -> native ``Exchange`` mapping (explicit, extensible;
  validated over the whole streamed row range of the requested symbol — never
  just the first batch — and re-checked on every emitted row),
* snapshot dataset indexing, symbol resolution (ambiguity is an error, never a
  latest-source preference),
* dataset semantic qualification (unknown units/time semantics are refused),
* native inclusive-end -> core half-open conversion plus precise ``<= end``
  filtering (an actual bar whose timestamp equals ``end`` survives),
* row -> ``BarData`` conversion with provenance in ``bar.extra``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from research_store import (
    MissingFieldDataError,
    SnapshotReader,
    StoreError,
    UnsupportedCapabilityError,
)

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.database import DB_TZ
from vnpy.trader.object import BarData

# Native interval -> core store interval value. vnpy cannot express 5m/15m;
# store datasets at those intervals are omitted from the native view (with
# diagnostics) and never relabelled as 1m.
NATIVE_INTERVALS: dict[Interval, str] = {
    Interval.MINUTE: "1m",
    Interval.HOUR: "1h",
    Interval.DAILY: "1d",
}

# Alpha supports only 1m/1d (plan N2); Database may also serve 1h.
ALPHA_INTERVALS: dict[Interval, str] = {
    Interval.MINUTE: "1m",
    Interval.DAILY: "1d",
}

# Explicit source exchange-label -> native exchange value. Identity
# passthrough applies when the stored label already IS a native value.
# Anything else is an unknown-label refusal, never a guess. Extend through the
# optional exchange-map JSON config (see configs/native_exchange_map.json).
DEFAULT_EXCHANGE_MAP: dict[str, str] = {
    "XSHG": "SSE",
    "XSHE": "SZSE",
    "XSGE": "SHFE",
    "XDCE": "DCE",
    "XCCE": "CZCE",
    "CCFX": "CFFEX",
    "XINE": "INE",
    "GFEX": "GFEX",
}

# Asset classes for which open interest is not applicable: a missing OI may be
# surfaced as an explicit 0.0 with metadata. For the other classes (futures,
# option) a missing OI is a data error, never a zero.
OI_NOT_APPLICABLE: frozenset[str] = frozenset(
    {"equity", "etf", "index", "convertible", "other"}
)

# Futures/option volume units accepted as verified single-side contract lots
# for VWAP conversion. Anything else (incl. "unknown") is refused.
VERIFIED_SINGLE_SIDE_VOLUME_UNITS: frozenset[str] = frozenset({"lot"})

_OHLCV = ("open", "high", "low", "close", "volume")

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class DatasetEntry:
    """One bars dataset bound by the snapshot manifest."""

    dataset_id: str
    semantic: dict[str, Any]
    partitions: tuple[str, ...]
    rows: int
    coverage_start_ns: int | None
    coverage_end_ns: int | None

    @property
    def interval(self) -> str:
        return str(self.semantic.get("interval", ""))

    @property
    def asset_class(self) -> str:
        return str(self.semantic.get("asset_class", ""))


def load_exchange_map(path: str | None) -> dict[str, str]:
    """Default label map plus optional user JSON overrides (label -> value)."""

    mapping = dict(DEFAULT_EXCHANGE_MAP)
    for exchange in Exchange:
        mapping.setdefault(exchange.value, exchange.value)
    if path:
        user = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(user, dict):
            raise StoreError(f"exchange map {path} must be a JSON object")
        for label, value in user.items():
            if value not in {e.value for e in Exchange}:
                raise StoreError(
                    f"exchange map {path}: {value!r} for label {label!r} "
                    "is not a native Exchange value"
                )
            mapping[str(label)] = str(value)
    return mapping


def map_exchange(label: str | None, exchange_map: dict[str, str]) -> Exchange | None:
    """Map a stored exchange label to a native Exchange; None if unmapped."""

    if label is None:
        return None
    value = exchange_map.get(label)
    return Exchange(value) if value is not None else None


def build_dataset_index(manifest: dict[str, Any]) -> dict[str, DatasetEntry]:
    """Index snapshot selections into per-dataset entries (bars only)."""

    grouped: dict[str, dict[str, Any]] = {}
    for selection in manifest.get("selections", []):
        dataset_id = str(selection["dataset_id"])
        entry = grouped.setdefault(
            dataset_id,
            {
                "semantic": selection.get("semantic", {}),
                "partitions": [],
                "rows": 0,
                "starts": [],
                "ends": [],
            },
        )
        entry["partitions"].append(str(selection["partition"]))
        entry["rows"] += int(selection.get("rows", 0))
        coverage = selection.get("coverage") or {}
        if coverage.get("start_ns") is not None:
            entry["starts"].append(int(coverage["start_ns"]))
        if coverage.get("end_ns") is not None:
            entry["ends"].append(int(coverage["end_ns"]))

    index: dict[str, DatasetEntry] = {}
    for dataset_id, entry in grouped.items():
        index[dataset_id] = DatasetEntry(
            dataset_id=dataset_id,
            semantic=entry["semantic"],
            partitions=tuple(sorted(entry["partitions"])),
            rows=entry["rows"],
            coverage_start_ns=min(entry["starts"]) if entry["starts"] else None,
            coverage_end_ns=max(entry["ends"]) if entry["ends"] else None,
        )
    return index


def interval_diagnostics(index: dict[str, DatasetEntry]) -> list[str]:
    """Diagnostics for snapshot datasets a native consumer cannot represent."""

    diagnostics: list[str] = []
    for entry in sorted(index.values(), key=lambda e: e.dataset_id):
        kind = str(entry.semantic.get("record_kind", ""))
        if kind != "bars":
            diagnostics.append(
                f"dataset {entry.dataset_id}: record_kind={kind!r} not served by "
                "the native bar bridge"
            )
            continue
        if entry.interval not in NATIVE_INTERVALS.values():
            diagnostics.append(
                f"dataset {entry.dataset_id}: interval {entry.interval!r} is not "
                "representable as a native Interval; omitted from overview and "
                "never relabelled as 1m"
            )
    return diagnostics


def validate_dataset_semantics(
    entry: DatasetEntry,
    *,
    purpose: str,
    allow_missing_auxiliary: bool,
) -> None:
    """Refuse datasets whose required semantics are unknown or ambiguous.

    Successful publication is NOT data qualification: units, timezone and
    time-label semantics must be known before native bars can be produced.
    ``purpose="alpha"`` additionally refuses unknown price adjustment (its
    returns would otherwise be silently misqualified).
    """

    semantic = entry.semantic
    problems: list[str] = []
    if str(semantic.get("timezone", "")) in ("", "unknown"):
        problems.append("timezone unknown")
    if str(semantic.get("source_time_label", "")) == "unknown":
        problems.append("source time-label semantics unknown")
    if str(semantic.get("volume_unit", "")) in ("", "unknown"):
        problems.append("volume unit unknown")
    turnover_unit = str(semantic.get("turnover_unit", ""))
    if turnover_unit in ("", "unknown") and not allow_missing_auxiliary:
        problems.append("turnover unit unknown")
    if purpose == "alpha":
        if str(semantic.get("adjustment", "")) == "unknown":
            problems.append("price adjustment unknown")
        if entry.interval not in ALPHA_INTERVALS.values():
            problems.append(f"interval {entry.interval!r} unsupported by alpha")
    if problems:
        raise StoreError(
            f"dataset {entry.dataset_id} refused for {purpose} consumption: "
            + "; ".join(problems)
            + " (publication is not qualification; resolve semantics upstream)"
        )


def _label_sort_key(label: str | None) -> tuple[bool, str]:
    """Order labels deterministically while tolerating NULL labels."""

    return (label is not None, label or "")


def candidate_identities(
    symbol: str,
    exchange: Exchange,
    exchange_map: dict[str, str],
) -> list[str]:
    """Stored identity candidates for one native (symbol, exchange) request.

    Importers preserve the vendor/source identity, which may be the bare
    native symbol (``000001``) or a vendor-suffixed id (``510130.XSHG``).
    Both are legitimate stored forms; the bridge resolves between them at
    read time using the actual exchange labels, never by rewriting the store.

    Candidates, in priority order:

    * the bare symbol itself (existing fixture/native identity);
    * ``symbol.<label>`` for every source label that maps to the requested
      native exchange via the explicit exchange map (e.g. ``510130.XSHG``
      for ``Exchange.SSE``).

    Arbitrary dotted symbols are never guessed: a candidate is only formed
    from labels the explicit map already knows, and resolution additionally
    requires the row's own exchange label to map to the requested exchange.
    """

    candidates = [symbol]
    for label, value in exchange_map.items():
        if value == exchange.value and label != symbol:
            suffixed = f"{symbol}.{label}"
            if suffixed not in candidates:
                candidates.append(suffixed)
    return candidates


def _identity_used_in_batch(batch: Any, candidates: list[str]) -> set[str]:
    """Which candidate identities actually appear in one batch."""

    found: set[str] = set()
    instruments = batch.column("instrument_id").to_pylist()
    series = batch.column("series_id").to_pylist()
    for identity, series_identity in zip(instruments, series, strict=True):
        effective = identity if identity is not None else series_identity
        if effective is not None and str(effective) in candidates:
            found.add(str(effective))
    return found


def resolve_bar_dataset(
    reader: SnapshotReader,
    index: dict[str, DatasetEntry],
    symbol: str,
    exchange: Exchange,
    interval_value: str,
    exchange_map: dict[str, str],
) -> tuple[DatasetEntry | None, str | None]:
    """Find THE snapshot dataset AND stored identity serving (symbol, exchange, interval).

    Identity matches on instrument_id/series_id across the candidate forms
    from ``candidate_identities`` (bare native id and vendor-suffixed ids
    whose label maps to the requested exchange). Returns ``(entry, stored
    identity)``; ``(None, None)`` when no dataset serves the request. The
    returned identity must be used for the actual read so vendor-suffixed
    rows are found; returned bars are stamped with the NATIVE symbol while
    ``bar.extra`` preserves the source identity.

    A stored exchange label that maps to a different native exchange is
    simply not a match (empty result); an unmapped label on
    otherwise-matching data is an explicit refusal. Multiple matching
    datasets are an ambiguity error — never a latest-source/source-preference
    guess. When BOTH the bare and a vendor-suffixed identity carry rows for
    the same native symbol in one dataset, that too is an explicit ambiguity
    error: the bridge never silently merges two stored identities into one
    native symbol.

    Exchange validation covers the WHOLE streamed row range of the requested
    symbol — every emitted batch, not just the first: a label appearing only
    in a later batch (unmapped, NULL, or mapping to a different native
    exchange) is held to exactly the same policy as a first-batch label. Only
    the distinct label set is retained (streamed validation; row history is
    never materialized), empty batches are not evidence of absence, and the
    selected dataset's labels must be uniform for the symbol: any row that
    would not be stamped with the requested exchange refuses the whole load
    instead of being silently relabelled, dropped, or split off.
    """

    candidates = candidate_identities(symbol, exchange, exchange_map)
    dataset_candidates = [
        entry
        for entry in index.values()
        if str(entry.semantic.get("record_kind", "")) == "bars"
        and entry.interval == interval_value
    ]
    matches: list[DatasetEntry] = []
    match_labels: dict[str, set[str | None]] = {}
    match_identity: dict[str, str] = {}
    unmapped_labels: dict[str, str | None] = {}
    for entry in dataset_candidates:
        # DISCOVERY-ONLY scan: which datasets serve this symbol, and do their
        # exchange labels map uniformly? It deliberately uses the explicit
        # observational reader mode with the full symbol stream: dataset
        # resolution must not depend on the caller's requested window (a
        # clean range must stay resolvable even when another range of the
        # same symbol carries default-qualified exclusions). Qualification is
        # enforced later, on the actual consumer read, for the effective
        # requested range (qualified-fix05 F1).
        stream = reader.bars(
            entry.dataset_id,
            instruments=candidates,
            required_fields=(),
            allow_missing_auxiliary=True,
            include_default_excluded=True,
        )
        labels: set[str | None] = set()
        identities: set[str] = set()
        for batch in stream:
            if batch.num_rows == 0:
                continue  # an empty batch says nothing about later batches
            labels.update(batch.column("exchange").to_pylist())
            identities.update(_identity_used_in_batch(batch, candidates))
        if not labels:
            continue  # no rows for this symbol in this dataset
        mapped = {map_exchange(label, exchange_map) for label in labels}
        if exchange in mapped:
            matches.append(entry)
            match_labels[entry.dataset_id] = labels
            if len(identities) > 1:
                raise StoreError(
                    f"ambiguous stored identities for {symbol}.{exchange.value} "
                    f"in {entry.dataset_id}: rows exist under multiple "
                    f"identities {sorted(identities)}; the native bridge "
                    "never silently merges bare and vendor-suffixed "
                    "identities into one native symbol"
                )
            match_identity[entry.dataset_id] = next(iter(identities))
        else:
            unmapped = [
                label
                for label in sorted(labels, key=_label_sort_key)
                if map_exchange(label, exchange_map) is None
            ]
            if unmapped:
                unmapped_labels[entry.dataset_id] = unmapped[0]
    if len(matches) > 1:
        ids = sorted(e.dataset_id for e in matches)
        raise StoreError(
            f"ambiguous native resolution: {symbol}.{exchange.value} "
            f"{interval_value} is served by multiple datasets {ids}; "
            "freeze an explicit selection instead of relying on a preference"
        )
    if not matches:
        if unmapped_labels:
            details = ", ".join(
                f"{ds} label={label!r}"
                for ds, label in sorted(unmapped_labels.items(), key=lambda i: i[0])
            )
            raise StoreError(
                f"unmapped exchange label for {symbol}: {details}; extend the "
                "native exchange map explicitly instead of guessing"
            )
        return None, None
    entry = matches[0]
    offenders = {
        label: map_exchange(label, exchange_map)
        for label in sorted(match_labels[entry.dataset_id], key=_label_sort_key)
        if map_exchange(label, exchange_map) != exchange
    }
    if offenders:
        details = ", ".join(
            f"{label!r} -> {mapped.value if mapped is not None else 'unmapped'}"
            for label, mapped in offenders.items()
        )
        raise StoreError(
            f"inconsistent exchange labels for {symbol} in {entry.dataset_id}: "
            f"{details}; every row of the symbol would be stamped "
            f"{exchange.value!r} — the native bridge never relabels, filters, "
            "or splits a dataset; fix the labels or extend the exchange map "
            "explicitly"
        )
    return entry, match_identity[entry.dataset_id]


def _ns_to_native_datetime(ns: int) -> datetime:
    """UTC epoch ns -> naive datetime in DB_TZ (native database convention)."""

    aware = _EPOCH + timedelta(microseconds=ns // 1000)
    return aware.astimezone(DB_TZ).replace(tzinfo=None)


def _native_to_utc_aware(dt: datetime) -> datetime:
    """Native datetime (naive = DB_TZ local, or aware) -> aware UTC."""

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = dt.replace(tzinfo=DB_TZ)
    return dt.astimezone(timezone.utc)


def parse_field_quality(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {"unparsed": raw}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def turnover_untrusted(field_quality: dict[str, Any]) -> bool:
    """Importer-recorded evidence that the turnover/amount is untrusted."""

    if field_quality.get("amount_untrusted") is True:
        return True
    flags = field_quality.get("flags")
    return isinstance(flags, list) and any(
        "untrusted" in str(flag) and ("amount" in str(flag) or "turnover" in str(flag))
        for flag in flags
    )


@dataclass(frozen=True)
class LoadReceipt:
    """Per-call receipt recording mode, binding and auxiliary degradation."""

    dataset_id: str
    snapshot_id: str
    symbol: str
    interval: str
    rows: int
    allow_missing_auxiliary: bool
    missing_turnover_rows: int
    missing_open_interest_rows: int
    untrusted_turnover_rows: int


def load_bars(
    reader: SnapshotReader,
    entry: DatasetEntry,
    symbol: str,
    exchange: Exchange,
    native_interval: Interval,
    start: datetime,
    end: datetime,
    *,
    stored_identity: str,
    allow_missing_auxiliary: bool,
    exchange_map: dict[str, str],
) -> tuple[list[BarData], LoadReceipt]:
    """Load native bars for one resolved dataset, inclusive of ``end``.

    ``stored_identity`` is the exact instrument_id/series_id form the store
    holds for this native symbol (bare native id or vendor-suffixed id, as
    resolved by ``resolve_bar_dataset``); it is used for the actual read so
    vendor-suffixed rows are found. Emitted bars are stamped with the NATIVE
    ``symbol`` while ``bar.extra["source_identity"]`` preserves the stored
    identity actually read.

    The core query is half-open; the internal upper bound is widened just
    enough to cover any bar whose native timestamp is ``<= end`` (one
    microsecond for minute/hour bars keyed by bar_start, one day for daily
    bars keyed by trading_date), then rows are filtered with a precise
    ``<= end`` comparison. No whole bar/day is ever added to the result.

    Every emitted row re-validates its own exchange label against the
    resolved mapping: a row whose label does not map to the requested
    exchange (unmapped, NULL, or a different native exchange) raises the
    same refusal it would have triggered at resolution time — a native bar
    is never stamped with an exchange its own row does not map to.
    """

    oi_required = entry.asset_class not in OI_NOT_APPLICABLE
    if allow_missing_auxiliary:
        required_fields: tuple[str, ...] = _OHLCV
    else:
        required_fields = _OHLCV + ("turnover",)
        if oi_required:
            required_fields += ("open_interest",)

    start_utc = _native_to_utc_aware(start)
    end_utc = _native_to_utc_aware(end)
    if native_interval is Interval.DAILY:
        internal_end = end_utc + timedelta(days=1)
    else:
        internal_end = end_utc + timedelta(microseconds=1)

    stream = reader.bars(
        entry.dataset_id,
        instruments=[stored_identity],
        start=start_utc,
        end=internal_end,
        required_fields=required_fields,
        allow_missing_auxiliary=allow_missing_auxiliary,
    )

    bars: list[BarData] = []
    missing_turnover = 0
    missing_oi = 0
    untrusted_turnover = 0
    columns = (
        "bar_start",
        "trading_date",
        "symbol",
        "exchange",
        "source_label",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover",
        "open_interest",
        "completeness",
        "field_quality",
        "contract_id",
        "asset_id",
        "batch_id",
        "transform_version",
    )
    for batch in stream:
        cols = {name: batch.column(name).to_pylist() for name in columns}
        for i in range(batch.num_rows):
            row = {name: cols[name][i] for name in columns}
            row_exchange = map_exchange(row["exchange"], exchange_map)
            if row_exchange != exchange:
                raise StoreError(
                    f"bar of {symbol} in {entry.dataset_id} carries exchange "
                    f"label {row['exchange']!r} mapping to "
                    f"{row_exchange.value if row_exchange is not None else 'no native exchange'}; "
                    f"refusing to stamp it as {exchange.value!r} — a native "
                    "bar never carries an exchange its own row does not map to"
                )
            if native_interval is Interval.DAILY:
                trading = row["trading_date"]
                if trading is None:
                    raise StoreError(
                        f"daily bar of {symbol} in {entry.dataset_id} has NULL "
                        "trading_date; unknown day semantics cannot become "
                        "native daily bars"
                    )
                dt = datetime.combine(
                    trading if isinstance(trading, date) else date.fromisoformat(str(trading)),
                    time.min,
                )
            else:
                dt = _ns_to_native_datetime(int(row["bar_start"]))
            # Precise inclusive-end filtering on the native timestamp.
            if dt < start or dt > end:
                continue

            field_quality = parse_field_quality(row["field_quality"])

            turnover = row["turnover"]
            turnover_note: str | None = None
            if turnover is None:
                missing_turnover += 1
                turnover = math.nan
                turnover_note = "missing_auxiliary_nan"
            elif turnover_untrusted(field_quality):
                untrusted_turnover += 1
                if allow_missing_auxiliary:
                    turnover = math.nan
                    turnover_note = "untrusted_turnover_nan"
                else:
                    raise MissingFieldDataError(
                        f"turnover of {symbol} @ {dt} in {entry.dataset_id} is "
                        "flagged untrusted by the importer; default mode refuses "
                        "it (explicit OHLCV-only mode returns NaN instead)"
                    )

            open_interest = row["open_interest"]
            oi_note: str | None = None
            if open_interest is None:
                if oi_required:
                    # strict required_fields already raised in default mode
                    missing_oi += 1
                    open_interest = math.nan
                    oi_note = "missing_auxiliary_nan"
                else:
                    open_interest = 0.0
                    oi_note = "not_applicable_explicit_zero"

            bar = BarData(
                symbol=symbol,
                exchange=exchange,
                datetime=dt,
                interval=native_interval,
                open_price=float(row["open"]),
                high_price=float(row["high"]),
                low_price=float(row["low"]),
                close_price=float(row["close"]),
                volume=float(row["volume"]),
                turnover=float(turnover),
                open_interest=float(open_interest),
                gateway_name="DB",
            )
            bar.extra = {
                "snapshot_id": reader.snapshot_id,
                "dataset_id": entry.dataset_id,
                "source_id": entry.semantic.get("source_id"),
                "adjustment": entry.semantic.get("adjustment"),
                "source_symbol": row["symbol"],
                "source_identity": stored_identity,
                "source_exchange_label": row["exchange"],
                "trading_date": (
                    str(row["trading_date"]) if row["trading_date"] is not None else None
                ),
                "source_label": row["source_label"],
                "completeness": row["completeness"],
                "field_quality": field_quality,
                "contract_id": row["contract_id"],
                "provenance": {
                    "asset_id": row["asset_id"],
                    "batch_id": row["batch_id"],
                    "transform_version": row["transform_version"],
                },
                "auxiliary": {
                    "turnover": turnover_note,
                    "open_interest": oi_note,
                },
            }
            bars.append(bar)

    bars.sort(key=lambda b: b.datetime)
    receipt = LoadReceipt(
        dataset_id=entry.dataset_id,
        snapshot_id=reader.snapshot_id,
        symbol=symbol,
        interval=entry.interval,
        rows=len(bars),
        allow_missing_auxiliary=allow_missing_auxiliary,
        missing_turnover_rows=missing_turnover,
        missing_open_interest_rows=missing_oi,
        untrusted_turnover_rows=untrusted_turnover,
    )
    return bars, receipt


def require_alpha_interval(interval: Interval) -> str:
    value = ALPHA_INTERVALS.get(interval)
    if value is None:
        raise UnsupportedCapabilityError(
            f"ResearchAlphaLab supports native 1m/1d only in v0.1, got "
            f"{interval.value!r}"
        )
    return value
