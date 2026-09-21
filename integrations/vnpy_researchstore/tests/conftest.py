"""Shared fixtures and builders for research_store core tests.

Fixtures are minimal reconstructable synthetic data — no purchased bulk data.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from research_store import (
    Adjustment,
    AssetClass,
    AssetRef,
    ImportReceipt,
    ImportRequest,
    Interval,
    OriginMethod,
    RecordKind,
    SemanticSpec,
    Store,
    TimeLabel,
    compute_dataset_id,
    import_asset,
    init_store,
)
from research_store import schemas

NS_MINUTE = 60 * 1_000_000_000


def ns(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp() * 1e9)


@pytest.fixture()
def store(tmp_path: Path):
    s = init_store(tmp_path / "store")
    yield s
    s.close()


def make_spec(**overrides: Any) -> SemanticSpec:
    defaults: dict[str, Any] = {
        "source_id": "synthetic",
        "asset_class": AssetClass.EQUITY,
        "record_kind": RecordKind.BARS,
        "interval": Interval.D1,
        "adjustment": Adjustment.NONE,
        "adjustment_version": "",
        "series_kind": "instrument",
        "rule_version": "",
        "timezone": "Asia/Shanghai",
        "source_time_label": TimeLabel.END,
        "volume_unit": "share",
        "turnover_unit": "CNY",
        "origin_method": OriginMethod.SOURCE,
        "schema_version": 1,
    }
    defaults.update(overrides)
    return SemanticSpec(**defaults)


def make_asset(tmp_path: Path, name: str, content: bytes) -> AssetRef:
    path = tmp_path / name
    path.write_bytes(content)
    return AssetRef(
        asset_id=f"asset-{name}",
        origin=str(path),
        format="synthetic_csv",
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def bar_row(
    dataset_id: str,
    instrument: str,
    start_ns: int,
    close: float | None = 10.0,
    volume: float | None = 100.0,
    turnover: float | None = 1000.0,
    open_interest: float | None = None,
    trading: date = date(2024, 1, 2),
    series: str | None = None,
    contract_id: str | None = None,
    batch_id: str = "batch-fixture",
    asset_id: str = "asset-fixture",
) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "instrument_id": instrument if series is None else None,
        "series_id": series,
        "symbol": instrument if series is None else series,
        "exchange": "XSHE",
        "bar_start": start_ns,
        "bar_end": start_ns + NS_MINUTE,
        "trading_date": trading,
        "source_label": None,
        "open": close,
        "high": None if close is None else close + 1,
        "low": None if close is None else close - 1,
        "close": close,
        "volume": volume,
        "turnover": turnover,
        "open_interest": open_interest,
        "completeness": "complete",
        "field_quality": None,
        "contract_id": contract_id,
        "asset_id": asset_id,
        "batch_id": batch_id,
        "transform_version": "t0",
        "extensions_json": None,
    }


def bars_batch(rows: list[dict[str, Any]]) -> pa.RecordBatch:
    schema = schemas.BARS_SCHEMA_V1
    columns = {name: [row[name] for row in rows] for name in schema.names}
    return pa.RecordBatch.from_pydict(columns, schema=schema)


def tick_row(
    dataset_id: str,
    instrument: str,
    ts_ns: int,
    session: str = "sess-1",
    seq: int = 1,
    last_price: float | None = 10.0,
    trading: date | None = None,
    batch_id: str = "batch-fixture",
    asset_id: str = "asset-fixture",
) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "instrument_id": instrument,
        "series_id": None,
        "symbol": instrument,
        "exchange": "XSHE",
        "session_id": session,
        "seq": seq,
        "ts": ts_ns,
        "trading_date": trading,
        "source_label": None,
        "last_price": last_price,
        "last_volume": 1.0,
        "turnover": 10.0,
        "bid_price1": last_price,
        "ask_price1": last_price,
        "bid_volume1": 2.0,
        "ask_volume1": 2.0,
        "completeness": "complete",
        "field_quality": None,
        "contract_id": None,
        "asset_id": asset_id,
        "batch_id": batch_id,
        "transform_version": "t0",
        "extensions_json": None,
    }


def ticks_batch(rows: list[dict[str, Any]]) -> pa.RecordBatch:
    schema = schemas.TICKS_SCHEMA_V1
    columns = {name: [row[name] for row in rows] for name in schema.names}
    return pa.RecordBatch.from_pydict(columns, schema=schema)


def import_rows(
    store: Store,
    tmp_path: Path,
    rows: list[dict[str, Any]],
    spec: SemanticSpec,
    partition: str = "2024",
    asset_name: str = "feed.csv",
    asset_content: bytes = b"fixture",
    adapter: str = "synthetic/0.1",
    config: dict[str, str] | None = None,
) -> ImportReceipt:
    dataset_id = compute_dataset_id(spec)
    for row in rows:
        row["dataset_id"] = dataset_id

    def stream(_partition: str):
        # two chunks to exercise streaming
        mid = max(1, len(rows) // 2)
        yield bars_batch(rows[:mid])
        yield bars_batch(rows[mid:])

    request = ImportRequest(
        asset=make_asset(tmp_path, asset_name, asset_content),
        spec=spec,
        adapter=adapter,
        config=config or {"member": asset_name},
        partitions=(partition,),
    )
    return import_asset(store, request, stream)
