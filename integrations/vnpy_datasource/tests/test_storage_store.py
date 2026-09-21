"""Store target: immutable research_store writes with real snapshot readback.

Run with an interpreter that has pyarrow/duckdb/zstandard, for example:
    D:/repo/vnpy/integrations/vnpy_researchstore/.venv/Scripts/python.exe -m pytest tests -q
The whole module skips cleanly when research_store or its Arrow/DuckDB
dependencies are not importable.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

RESEARCHSTORE_ROOT = Path(__file__).resolve().parents[2] / "vnpy_researchstore"
if RESEARCHSTORE_ROOT.is_dir() and str(RESEARCHSTORE_ROOT) not in sys.path:
    sys.path.insert(0, str(RESEARCHSTORE_ROOT))

pytest.importorskip("pyarrow", reason="store target needs pyarrow")
pytest.importorskip("duckdb", reason="snapshot readback needs duckdb")
pytest.importorskip("zstandard", reason="store objects need zstandard")
research_store = pytest.importorskip("research_store", reason="store target needs research_store")

from vnpy_datasource.storage import MANIFEST_NAME, save_history  # noqa: E402


def history(*, adjustment: str = "none", turnover: float | None = 12345.0) -> dict:
    return {
        "status": "ok", "source": "fixture", "recipe": "daily", "kind": "bars",
        "records": [{
            "datetime": "2025-01-02", "open": 1.1, "high": 1.3,
            "low": 1.0, "close": 1.2, "volume": 10000.0, "turnover": turnover,
        }],
        "metadata": {
            "interval": "d", "adjustment": adjustment, "time_label": "date",
            "volume_unit": "shares", "turnover_unit": "CNY",
            "missing_fields": ["turnover"] if turnover is None else [],
        },
        "request": {"symbol": "159915.SZSE"}, "attempts": [],
        "fetched_at": "2025-01-03T01:00:00Z", "registry_sha256": "fixture-hash",
    }


def readback_rows(root: Path, snapshot_id: str, dataset_id: str) -> list[dict]:
    store = research_store.open_store(root)
    try:
        reader = research_store.open_snapshot(store, snapshot_id)
        try:
            return [
                row
                for batch in reader.bars(
                    dataset_id, required_fields=(), allow_missing_auxiliary=True,
                )
                for row in batch.to_pylist()
            ]
        finally:
            reader.close()
    finally:
        store.close()


def test_store_roundtrip_real_readback(tmp_path: Path) -> None:
    payload = history()
    result = save_history(payload, "159915.SZSE", "store", tmp_path / "store")
    assert result["status"] == "ok"
    assert result["target"] == "store"
    assert result["verified_rows"] == 1
    assert result["readback"] == "research_store"
    root = Path(result["path"])
    assert (root / "store.json").is_file()
    assert not (root / MANIFEST_NAME).exists()

    capture = json.loads(Path(result["capture"]).read_text(encoding="utf-8"))
    assert capture == payload  # raw result preserved verbatim
    assert Path(result["capture"]).parent == root / "captures"

    receipt_path = Path(result["receipt"])
    assert receipt_path.parent == root / "reports"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["storage_status"] == "verified"
    assert receipt["turnover_missing"] is False
    assert receipt["fetched_at"] == "2025-01-03T01:00:00Z"
    assert receipt["registry_sha256"] == "fixture-hash"

    rows = readback_rows(root, result["snapshot_id"], result["dataset_id"])
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "159915.SZSE"
    assert row["exchange"] == "SZSE"
    assert row["instrument_id"] == "159915"
    assert row["trading_date"] == date(2025, 1, 2)
    assert row["close"] == 1.2
    assert row["turnover"] == 12345.0


def test_store_preserves_null_turnover(tmp_path: Path) -> None:
    result = save_history(history(turnover=None), "159915.SZSE", "store", tmp_path)
    assert result["status"] == "ok"
    assert result["turnover_missing"] is True
    receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
    assert receipt["turnover_missing"] is True
    assert receipt["turnover_missing_at"] == ["2025-01-02"]
    assert receipt["turnover_placeholder"] is None
    rows = readback_rows(Path(result["path"]), result["snapshot_id"], result["dataset_id"])
    assert len(rows) == 1
    assert rows[0]["turnover"] is None  # real NULL, never the 0.0 BarData placeholder
    assert rows[0]["close"] == 1.2
    assert json.loads(rows[0]["field_quality"])["missing"] == ["turnover", "open_interest"]


def test_store_rejects_non_ok_result(tmp_path: Path) -> None:
    payload = history()
    payload["status"] = "source_unavailable"
    with pytest.raises(ValueError, match="Cannot store"):
        save_history(payload, "159915.SZSE", "store", tmp_path / "uncreated")
    assert not (tmp_path / "uncreated").exists()


def test_store_repeat_import_is_idempotent(tmp_path: Path) -> None:
    first = save_history(history(), "159915.SZSE", "store", tmp_path)
    second = save_history(history(), "159915.SZSE", "store", tmp_path)
    assert second["status"] == "ok"
    assert second["dataset_id"] == first["dataset_id"]
    assert second["batch_id"] == first["batch_id"]  # prior receipt replayed
    assert second["idempotent_replay"] is True
    rows = readback_rows(Path(first["path"]), second["snapshot_id"], first["dataset_id"])
    assert len(rows) == 1  # no duplicated bars


def test_store_rejects_unmanaged_directory(tmp_path: Path) -> None:
    (tmp_path / "stray.txt").write_text("not a store", encoding="utf-8")
    with pytest.raises(Exception, match="non-empty"):
        save_history(history(), "159915.SZSE", "store", tmp_path)
    assert not (tmp_path / "store.json").exists()


def test_store_minute_requires_start_label(tmp_path: Path) -> None:
    payload = history()
    payload["metadata"]["interval"] = "5m"
    payload["metadata"]["time_label"] = "unknown"
    payload["records"] = [{
        "datetime": "2025-01-02T09:35:00+08:00", "open": 1.1, "high": 1.3,
        "low": 1.0, "close": 1.2, "volume": 100.0, "turnover": 120.0,
    }]
    with pytest.raises(ValueError, match="time_label"):
        save_history(payload, "159915.SZSE", "store", tmp_path / "store")
