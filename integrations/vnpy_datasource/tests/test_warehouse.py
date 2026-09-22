"""Local warehouse reader: mapping rules offline, and a real snapshot read when available."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from vnpy_datasource.warehouse import WarehouseReader


class FakeSnapshot:
    """Stand-in for warehouse.query.Snapshot returning canned frames."""

    snapshot_id = "TEST-SNAP"

    def __init__(self, frame: pd.DataFrame, datasets: set[str]) -> None:
        self.frame, self._datasets = frame, datasets
        self.calls: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def datasets(self):
        return self._datasets

    def bars(self, symbols, start, end, *, asset, frequency):
        self.calls.append((symbols, start, end, asset, frequency))
        return self.frame


def reader_with(frame: pd.DataFrame, datasets: set[str]) -> tuple[WarehouseReader, FakeSnapshot]:
    reader = WarehouseReader("D:/nonexistent")
    fake = FakeSnapshot(frame, datasets)
    reader._snapshot = lambda: fake  # type: ignore[method-assign]
    return reader, fake


def frame(rows: list[dict]) -> pd.DataFrame:
    base = {"open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1, "volume": 100.0, "amount": 110.0, "paused": 0.0, "source": "local_rq_market_bars"}
    return pd.DataFrame([{**base, **row} for row in rows])


def test_symbol_interval_mapping_and_minute_relabel() -> None:
    minute = frame([{"timestamp": pd.Timestamp("2026-09-11 09:31:00")}, {"timestamp": pd.Timestamp("2026-09-11 15:00:00")}])
    reader, fake = reader_with(minute, {"bars_etf_1m"})
    result = reader.history("510050.SSE", "2026-09-11", "2026-09-11", "1m")
    assert result["status"] == "ok" and result["snapshot_id"] == "TEST-SNAP"
    assert fake.calls == [(["510050.XSHG"], date(2026, 9, 11), date(2026, 9, 11), "etf", "1m")]
    # warehouse end labels -> vnpy start labels
    assert [r["datetime"] for r in result["records"]] == ["2026-09-11T09:30:00+08:00", "2026-09-11T14:59:00+08:00"]
    assert result["metadata"]["time_label"] == "start" and result["metadata"]["volume_unit"] == "units"


def test_paused_rows_dropped_and_missing_volume_flagged() -> None:
    daily = frame([
        {"timestamp": pd.Timestamp("2026-09-16"), "paused": 1.0, "volume": 0.0},
        {"timestamp": pd.Timestamp("2026-09-17"), "volume": float("nan"), "amount": float("nan"), "source": "sina"},
        {"timestamp": pd.Timestamp("2026-09-18")},
    ])
    reader, _ = reader_with(daily, {"bars_index_1d"})
    result = reader.history("399001.SZSE", "2026-09-16", "2026-09-18", "d")
    assert [r["datetime"][:10] for r in result["records"]] == ["2026-09-17", "2026-09-18"]
    meta = result["metadata"]
    assert meta["paused_rows_dropped"] == 1
    assert meta["missing_fields"] == ["turnover", "volume"] and meta["volume_missing_at"] == ["2026-09-17"]
    assert result["records"][0]["volume"] == 0.0 and result["records"][0]["turnover"] is None
    assert meta["warehouse_sources"] == ["local_rq_market_bars", "sina"]


def test_unsupported_and_no_data_envelopes() -> None:
    reader, _ = reader_with(frame([]), {"bars_etf_1d"})
    assert reader.history("600519.SSE", "2026-09-01", "2026-09-18", "1m")["reason"] == "dataset_not_in_warehouse:bars_stock_1m"
    assert reader.history("159915.SZSE", "2026-09-01", "2026-09-18", "d", adjust="qfq")["reason"] == "warehouse_serves_unadjusted_only"
    with pytest.raises(ValueError):
        reader.history("159915", "2026-09-01", "2026-09-18", "d")


LIVE_ROOT = Path("D:/repo/dataSource")


@pytest.mark.skipif(not WarehouseReader(LIVE_ROOT).available(), reason="local warehouse snapshot not readable here")
def test_live_snapshot_read_is_reproducible() -> None:
    reader = WarehouseReader(LIVE_ROOT)
    result = reader.history("159915.SZSE", "2026-09-01", "2026-09-11", "d")
    assert result["status"] == "ok" and result["records"]
    pinned = WarehouseReader(LIVE_ROOT, result["snapshot_id"]).history("159915.SZSE", "2026-09-01", "2026-09-11", "d")
    assert pinned["records"] == result["records"]

def test_manifest_changes_during_pinned_read_fail(tmp_path):
    reader, fake = reader_with(frame([{'timestamp':pd.Timestamp('2026-09-11')}]), {'bars_etf_1d'})
    fake.root = tmp_path
    (tmp_path/'snapshots').mkdir()
    manifest=tmp_path/'snapshots/TEST-SNAP.json';manifest.write_text('{}')
    original=fake.bars
    def changed(*args,**kwargs):
        manifest.write_text('{"tampered":true}')
        return original(*args,**kwargs)
    fake.bars=changed
    with pytest.raises(ValueError,match='manifest changed'):
        reader.history('159915.SZSE','2026-09-11','2026-09-11','d')
