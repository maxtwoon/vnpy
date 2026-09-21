"""Bridge from canonical importer rows to the core publish boundary.

Implements the INTERFACES.md §5 insertion point on the importer side:

* canonical row dicts -> ``BARS_SCHEMA_V1`` ``pa.RecordBatch`` streams
  (sorted by (identity, bar_start), unique, NULLs preserved, non-finite
  already converted to NULL+flags by the normaliser);
* dataset ``SemanticSpec`` builders for each source with the verified
  semantics (RQ ETF END labels / adjustment none; JQ adjustment unknown
  despite factor 1.0; SSQuant label UNKNOWN; RQ futures dominant identity);
* :func:`publish_canonical` driving ``research_store.revisions.import_asset``.

Time contract (coordinator disposition 2026-09-16): canonical bar bounds are
always real and NOT NULL — rows without evidenced bounds raise
:class:`CoreBridgeError` here and stay on the candidate/inspection path.
``trading_date`` may be NULL for minute datasets without calendar evidence
(the schema and publish validation allow it); daily rows without a trading
date are rejected here already, before the core's own publish check.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from datetime import date
from typing import Any

import pyarrow as pa

from .errors import ImporterError
from ..models import (
    Adjustment,
    AssetClass,
    AssetRef,
    ImportRequest,
    Interval,
    OriginMethod,
    RecordKind,
    SemanticSpec,
    TimeLabel,
    compute_dataset_id,
)
from ..revisions import import_asset
from ..schemas import BARS_SCHEMA_V1, SCHEMA_VERSION
from ..store import Store

BATCH_ROWS = 65_536
TRANSFORM_VERSION = "import-v1"

SERIES_KINDS = {"continuous_888", "continuous_777", "continuous_dominant", "staging"}


class CoreBridgeError(ImporterError):
    """A canonical row cannot be represented in the core record schema."""


def _identity_split(row: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    if row.get("series_kind") in SERIES_KINDS:
        contract = row.get("extensions", {}).get("dominant_id") or row.get(
            "extensions", {}
        ).get("real_symbol")
        return None, str(row["instrument"]), (str(contract) if contract else None)
    return str(row["instrument"]), None, None


def to_core_row(
    row: dict[str, Any],
    dataset_id: str,
    asset_id: str,
    batch_id: str,
    transform_version: str = TRANSFORM_VERSION,
    interval: str = "1m",
) -> dict[str, Any]:
    """Convert one canonical row into a BARS_SCHEMA_V1 column dict."""
    if row.get("bar_start_ns") is None or row.get("bar_end_ns") is None:
        raise CoreBridgeError(
            f"core BARS_SCHEMA_V1 requires non-null bar bounds; "
            f"{row.get('instrument')} @ {row.get('source_label')} has unknown "
            "label semantics — route it to the candidate/inspection path"
        )
    raw_trading_date = row.get("trading_date")
    if raw_trading_date is None and interval == "1d":
        raise CoreBridgeError(
            f"daily datasets require non-null trading_date; "
            f"{row.get('instrument')} @ {row.get('source_label')} has none"
        )
    trading_date = (
        None
        if raw_trading_date is None
        else date.fromisoformat(str(raw_trading_date)[:10])
    )
    instrument_id, series_id, contract_id = _identity_split(row)
    extensions = row.get("extensions") or {}
    # ``symbol`` preserves the original source symbol even when identity was
    # resolved to a canonical contract id (e.g. Zhengzhou three-digit codes).
    source_symbol = extensions.get("source_symbol")
    quality: dict[str, Any] = {"flags": row.get("quality_flags", [])}
    for key in ("amount_untrusted", "repair"):
        if key in extensions:
            quality[key] = extensions[key]
    passthrough = {k: v for k, v in extensions.items() if k not in ("repair",)}
    return {
        "dataset_id": dataset_id,
        "instrument_id": instrument_id,
        "series_id": series_id,
        "symbol": str(source_symbol) if source_symbol else str(row["instrument"]),
        "exchange": row.get("exchange"),
        "bar_start": int(row["bar_start_ns"]),
        "bar_end": int(row["bar_end_ns"]),
        "trading_date": trading_date,
        "source_label": row.get("source_label"),
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "volume": row.get("volume"),
        "turnover": row.get("turnover"),
        "open_interest": row.get("open_interest"),
        "completeness": "unknown",
        "field_quality": json.dumps(quality, ensure_ascii=False),
        "contract_id": contract_id,
        "asset_id": asset_id,
        "batch_id": batch_id,
        "transform_version": transform_version,
        "extensions_json": json.dumps(passthrough, ensure_ascii=False),
    }


def core_rows_sorted(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort canonical rows into the core key order (identity, bar_start)."""
    def sort_key(row: dict[str, Any]) -> tuple[str, int]:
        return (str(row["instrument"]), int(row["bar_start_ns"] or 0))

    return sorted(rows, key=sort_key)


def to_record_batches(
    rows: Sequence[dict[str, Any]],
    dataset_id: str,
    asset_id: str,
    batch_id: str,
    transform_version: str = TRANSFORM_VERSION,
    batch_rows: int = BATCH_ROWS,
    interval: str = "1m",
) -> Iterator[pa.RecordBatch]:
    """Convert canonical rows to validated BARS_SCHEMA_V1 record batches."""
    core_rows = [
        to_core_row(row, dataset_id, asset_id, batch_id, transform_version, interval)
        for row in core_rows_sorted(rows)
    ]
    for offset in range(0, len(core_rows), batch_rows):
        chunk = core_rows[offset : offset + batch_rows]
        yield pa.RecordBatch.from_pydict(
            {name: [row[name] for row in chunk] for name in BARS_SCHEMA_V1.names},
            schema=BARS_SCHEMA_V1,
        )


def build_rq_etf_spec(frequency: str) -> SemanticSpec:
    """RQ ETF/LOF semantic identity.

    Verified evidence: README states adjustment none; minute labels are END
    (09:31 first bar); VWAP arithmetic amount/volume matches price so volume
    is shares and turnover CNY (checked on 510300.XSHG 2026-07-31 09:31:
    441176239/94259900 = 4.68 within the bar OHLC range).
    """
    return SemanticSpec(
        source_id="rqdatac",
        asset_class=AssetClass.ETF,
        record_kind=RecordKind.BARS,
        interval=Interval(frequency),
        adjustment=Adjustment.NONE,
        adjustment_version="",
        series_kind="instrument",
        rule_version="",
        timezone="Asia/Shanghai",
        source_time_label=TimeLabel.END,
        volume_unit="share",
        turnover_unit="CNY",
        origin_method=OriginMethod.SOURCE,
        schema_version=SCHEMA_VERSION,
    )


def build_jq_daily_spec() -> SemanticSpec:
    """JoinQuant holographic daily identity (adjustment UNKNOWN, factor 1.0)."""
    return SemanticSpec(
        source_id="joinquant",
        asset_class=AssetClass.EQUITY,
        record_kind=RecordKind.BARS,
        interval=Interval.D1,
        adjustment=Adjustment.UNKNOWN,
        adjustment_version="",
        series_kind="instrument",
        rule_version="",
        timezone="Asia/Shanghai",
        source_time_label=TimeLabel.START,
        volume_unit="share",
        turnover_unit="CNY",
        origin_method=OriginMethod.SOURCE,
        schema_version=SCHEMA_VERSION,
    )


def build_rq_futures_spec(
    dataset: str, frequency: str, time_label: str = "unknown"
) -> SemanticSpec:
    """RQ futures semantic identity (dominant continuous or real contract).

    ``time_label`` defaults to UNKNOWN: per FUTURES_TIME_REVIEW_04IB neither
    START nor END minute-label direction is established for the supplied
    archives, so the default identity must not declare one. An explicit
    ``time_label="start"``/``"end"`` may only be passed together with a
    matching scoped :class:`~research_store.importers.normalize.FuturesLabelScope`
    (the adapter verifies the pairing); UNKNOWN, START and END therefore
    never silently share one declared semantic identity.
    """
    is_dominant = dataset.startswith("dominant_")
    if time_label not in ("unknown", "start", "end"):
        raise ValueError(
            f"rq futures time_label must be unknown/start/end, got {time_label!r}"
        )
    return SemanticSpec(
        source_id="rqdatac",
        asset_class=AssetClass.FUTURES,
        record_kind=RecordKind.BARS,
        interval=Interval(frequency),
        adjustment=Adjustment.NONE,
        adjustment_version="",
        series_kind="dominant" if is_dominant else "instrument",
        # dominant selection/roll rules unverified -> rule_version stays ""
        rule_version="",
        timezone="Asia/Shanghai",
        source_time_label=TimeLabel(time_label),
        volume_unit="unknown",
        turnover_unit="CNY",
        origin_method=OriginMethod.SOURCE,
        schema_version=SCHEMA_VERSION,
    )


def build_ssquant_spec(
    frequency: str, series_kind: str, time_label: str = "unknown"
) -> SemanticSpec:
    """SSQuant semantic identity.

    Default ``time_label="unknown"``: label semantics unverified, units
    untrusted. When a scoped :class:`LabelEvidence` qualifies a
    capture/symbol/range, pass its conclusion (``"start"``/``"end"``) — the
    evidenced convention is part of the dataset's semantic identity, so
    evidenced and unevidenced SSQuant data never share a dataset id.
    """
    return SemanticSpec(
        source_id="ssquant",
        asset_class=AssetClass.FUTURES,
        record_kind=RecordKind.BARS,
        interval=Interval(frequency),
        adjustment=Adjustment.UNKNOWN,
        adjustment_version="",
        series_kind=series_kind,
        rule_version="",
        timezone="Asia/Shanghai",
        source_time_label=TimeLabel(time_label),
        volume_unit="unknown",
        turnover_unit="unknown",
        origin_method=OriginMethod.SOURCE,
        schema_version=SCHEMA_VERSION,
    )


def publish_canonical(
    store: Store,
    asset: AssetRef,
    spec: SemanticSpec,
    adapter: str,
    config: Mapping[str, str],
    partition_rows: Mapping[str, Sequence[dict[str, Any]]],
    batch_id: str,
    transform_version: str = TRANSFORM_VERSION,
) -> Any:
    """Publish canonical rows through the core ``import_asset`` boundary.

    ``partition_rows`` maps each partition key to its full canonical row set;
    the bridge sorts per partition and streams 65k-row record batches. The
    returned object is the core ``ImportReceipt``.
    """
    request = ImportRequest(
        asset=asset,
        spec=spec,
        adapter=adapter,
        config=dict(config),
        partitions=tuple(sorted(partition_rows)),
    )
    dataset_id = compute_dataset_id(spec)

    def rows(partition: str) -> Iterator[pa.RecordBatch]:
        yield from to_record_batches(
            partition_rows[partition],
            dataset_id=dataset_id,
            asset_id=asset.asset_id,
            batch_id=batch_id,
            transform_version=transform_version,
            interval=spec.interval.value,
        )

    return import_asset(store, request, rows)


__all__ = [
    "BATCH_ROWS",
    "CoreBridgeError",
    "TRANSFORM_VERSION",
    "build_jq_daily_spec",
    "build_rq_etf_spec",
    "build_rq_futures_spec",
    "build_ssquant_spec",
    "core_rows_sorted",
    "publish_canonical",
    "to_core_row",
    "to_record_batches",
]
