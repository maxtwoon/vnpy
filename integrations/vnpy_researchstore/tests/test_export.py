"""Export module tests: faithful parquet copy, compatibility sqlite/alpha
copies with explicit missing-field rules, write/readback verification and
empty-or-same-binding target protection.

Rules under test (TASK_OPENCODE_CONSUMERS_02):
* target must be unmanaged-empty or bound to THIS store+snapshot+format;
* sqlite/alpha exports are rebuildable compatibility copies, never truth:
  NULL OHLCV rows skipped and listed, NULL turnover/open_interest become
  recorded 0.0 placeholders (sqlite NOT NULL), unmapped exchange labels
  skipped and recorded;
* every export is verified by reading the written artifact back.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from _rs_import_bootstrap import PYARROW_AVAILABLE, ZSTANDARD_AVAILABLE

from research_store.export import EXPORT_BINDING_NAME, export_snapshot
from research_store.importers.core_bridge import (
    build_rq_etf_spec,
    publish_canonical,
)
from research_store.importers.normalize import normalize_rq_etf_row
from research_store.importers.partitions import partition_for_row
from research_store.importers.safeio import file_sha256
from research_store.models import Selection, SnapshotRequest
from research_store.snapshots import freeze, open_snapshot
from research_store.store import Store, init_store

pytestmark = pytest.mark.skipif(
    not (ZSTANDARD_AVAILABLE and PYARROW_AVAILABLE),
    reason="zstandard and pyarrow required",
)


def _row(instrument: str, label: str, **overrides: str) -> dict[str, Any]:
    raw: dict[str, str] = {
        "order_book_id": instrument,
        "datetime": label,
        "open": "1.0",
        "high": "1.2",
        "low": "0.9",
        "close": "1.1",
        "volume": "100",
        "amount": "110",
        "num_trades": "2",
    }
    raw.update(overrides)
    return normalize_rq_etf_row(
        raw,
        interval_minutes=1,
        archive="rqdatac_etf_lof_1m_2016.tar.zst",
        member=f"2016/{instrument}.csv",
        batch_id="b-export",
    )


@pytest.fixture()
def frozen(tmp_path: Path) -> dict[str, Any]:
    rows = [
        _row("510300.XSHG", "2016-02-29 09:31:00"),
        # NULL turnover: sqlite placeholder + alpha real NULL
        _row("510300.XSHG", "2016-02-29 09:32:00", amount=""),
        # NULL close: skipped by BOTH compatibility exports, kept by store
        _row("159915.XSHE", "2016-02-29 09:31:00", close=""),
    ]
    weird = _row("A00001", "2016-02-29 09:31:00")
    weird["exchange"] = "XYZE"  # unmapped exchange label
    rows.append(weird)

    partition_rows: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        partition_rows.setdefault(
            partition_for_row(row, "1m", "etf"), []
        ).append(row)
    store = init_store(tmp_path / "store")
    spec = build_rq_etf_spec("1m")
    asset = type(
        "A",
        (),
        {
            "asset_id": "asset-export",
            "origin": "synthetic",
            "format": "synthetic",
            "size": 1,
            "sha256": file_sha256(Path(__file__)),
        },
    )()
    receipt = publish_canonical(
        store,
        asset,
        spec,
        adapter="rq_etf/0.1",
        config={"fixture": "export"},
        partition_rows=partition_rows,
        batch_id="b-export",
    )
    assert receipt.state.value == "published"
    snapshot = freeze(
        store,
        SnapshotRequest(
            selections=(Selection(receipt.dataset_id, "*"),),
            required_fields=(),
        ),
    )
    return {
        "store": store,
        "root": tmp_path / "store",
        "dataset_id": receipt.dataset_id,
        "snapshot_id": snapshot.snapshot_id,
        "tmp": tmp_path,
    }


def _snapshot_rows(store: Store, snapshot_id: str, dataset_id: str) -> list[dict]:
    reader = open_snapshot(store, snapshot_id)
    try:
        return [
            row
            for batch in reader.bars(
                dataset_id, required_fields=(), allow_missing_auxiliary=True
            )
            for row in batch.to_pylist()
        ]
    finally:
        reader.close()


def test_parquet_export_is_faithful_copy(frozen: dict[str, Any]) -> None:
    target = frozen["tmp"] / "export-parquet"
    receipt = export_snapshot(
        frozen["store"], frozen["snapshot_id"], target, "parquet"
    )
    entry = receipt["datasets"][frozen["dataset_id"]]
    assert entry["readback"] == "verified"
    assert entry["rows"] == 4
    assert receipt["compatibility_copy"] is False

    import pyarrow.parquet as pq

    exported = pq.read_table(entry["files"][0]).to_pylist()
    original = _snapshot_rows(
        frozen["store"], frozen["snapshot_id"], frozen["dataset_id"]
    )
    assert exported == original  # exact rows, NULLs included


def test_sqlite_compatibility_copy_rules(frozen: dict[str, Any]) -> None:
    target = frozen["tmp"] / "export-sqlite"
    receipt = export_snapshot(
        frozen["store"], frozen["snapshot_id"], target, "sqlite"
    )
    entry = receipt["datasets"][frozen["dataset_id"]]
    assert receipt["compatibility_copy"] is True
    # 510300 rows written; NULL-close XSHE and unmapped XYZE skipped
    assert entry["rows_written"] == 2
    assert len(entry["skipped_null_required"]) == 1
    assert entry["skipped_unmapped_exchange"] == ["A00001"]
    assert entry["turnover_zero_placeholders"] == 1
    assert entry["open_interest_zero_placeholders"] == 2
    with sqlite3.connect(entry["path"]) as con:
        rows = list(
            con.execute(
                "SELECT symbol, exchange, turnover, open_interest, close_price"
                " FROM dbbardata ORDER BY symbol, datetime"
            )
        )
    assert len(rows) == 2
    turnover_by_symbol = {row[0]: row[2] for row in rows}
    assert sorted(turnover_by_symbol) == ["510300.XSHG"]
    # NULL turnover row written as the recorded 0.0 compatibility placeholder
    assert sorted(row[2] for row in rows) == [0.0, 110.0]


def test_alpha_compatibility_copy_rules(frozen: dict[str, Any]) -> None:
    target = frozen["tmp"] / "export-alpha"
    receipt = export_snapshot(
        frozen["store"], frozen["snapshot_id"], target, "alpha"
    )
    entry = receipt["datasets"][frozen["dataset_id"]]
    assert entry["folder"] == "minute"
    assert entry["readback"] == "verified"
    # NULL-close 159915 row skipped and listed; others written per instrument
    assert entry["rows_written"] == 3
    assert len(entry["skipped_null_close"]) == 1

    import pyarrow.parquet as pq

    exported = pq.read_table(entry["files"][0]).to_pylist()
    symbols = {row_path.split("\\")[-1] for row_path in entry["files"]}
    assert any("510300.XSHG" in name for name in symbols)
    # real NULL turnover preserved (no zero placeholder in alpha copies)
    turnovers = [row["turnover"] for row in exported]
    assert None in turnovers


def test_target_protection(frozen: dict[str, Any]) -> None:
    store = frozen["store"]
    snapshot_id = frozen["snapshot_id"]
    # non-empty unmanaged directory -> refused
    stray = frozen["tmp"] / "stray"
    stray.mkdir()
    (stray / "other.txt").write_text("x", encoding="utf-8")
    with pytest.raises(Exception, match="unmanaged"):
        export_snapshot(store, snapshot_id, stray, "parquet")
    # same binding -> allowed (re-export)
    good = frozen["tmp"] / "export-parquet"
    receipt = export_snapshot(store, snapshot_id, good, "parquet")
    assert receipt["datasets"][frozen["dataset_id"]]["readback"] == "verified"
    # same directory, different format -> refused
    with pytest.raises(Exception, match="different"):
        export_snapshot(store, snapshot_id, good, "sqlite")
    # binding records store/snapshot/format identity
    binding = json.loads((good / EXPORT_BINDING_NAME).read_text(encoding="utf-8"))
    assert binding["snapshot_id"] == snapshot_id
    assert binding["format"] == "parquet"
    assert binding["store_id"] == store.store_id


def test_alpha_export_refuses_unsupported_interval(frozen: dict[str, Any]) -> None:
    # a 5m dataset cannot map to AlphaLab's daily/minute layout
    store: Store = frozen["store"]
    rows = [
        _row("510300.XSHG", "2016-02-29 09:35:00"),
    ]
    spec = build_rq_etf_spec("5m")
    partition_rows = {
        partition_for_row(row, "5m", "etf"): rows for row in rows
    }
    asset = type(
        "A",
        (),
        {
            "asset_id": "asset-export-5m",
            "origin": "synthetic",
            "format": "synthetic",
            "size": 1,
            "sha256": file_sha256(Path(__file__)),
        },
    )()
    receipt = publish_canonical(
        store,
        asset,
        spec,
        adapter="rq_etf/0.1",
        config={"fixture": "export5m"},
        partition_rows=partition_rows,
        batch_id="b-export-5m",
    )
    snapshot = freeze(
        store,
        SnapshotRequest(
            selections=(Selection(receipt.dataset_id, "*"),),
            required_fields=(),
        ),
    )
    with pytest.raises(Exception, match="1m/1d"):
        export_snapshot(
            store, snapshot.snapshot_id, frozen["tmp"] / "export-alpha-5m", "alpha"
        )
