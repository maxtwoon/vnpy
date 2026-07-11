import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_tick_bars import (  # noqa: E402
    aggregate_ticks_to_1m,
    main,
    promote_staged_bars,
    upsert_bars_to_sqlite,
)


def _export_payload() -> dict[str, Any]:
    return {
        "meta": {
            "contract_map": {
                "AP888": {"symbol": "ap610", "exchange": "CZCE", "enabled": True},
            }
        },
        "raw": {
            "ticks": [
                {
                    "dt": "2026-07-01 09:00:00+08:00",
                    "symbol": "ap610",
                    "exchange": "CZCE",
                    "last_price": 100.0,
                    "volume": 1000,
                },
                {
                    "dt": "2026-07-01 09:00:30+08:00",
                    "symbol": "ap610",
                    "exchange": "CZCE",
                    "last_price": 102.0,
                    "volume": 1005,
                },
            ]
        },
    }


def test_default_mode_leaves_raw_table_unchanged(tmp_path):
    db_path = tmp_path / "bars.db"
    bars = aggregate_ticks_to_1m(_export_payload())

    upsert_bars_to_sqlite(db_path, bars)

    with sqlite3.connect(db_path) as conn:
        raw_exists = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='ap888_1M_raw'"
        ).fetchone()[0]
        staging_count = conn.execute("SELECT count(*) FROM ap888_1M_raw_staging").fetchone()[0]
    assert raw_exists == 0
    assert staging_count == 1


def test_direct_mode_without_flag_is_rejected(tmp_path):
    db_path = tmp_path / "bars.db"
    bars = aggregate_ticks_to_1m(_export_payload())

    try:
        upsert_bars_to_sqlite(db_path, bars, kline_write_mode="direct")
    except ValueError as exc:
        assert "allow_direct_write" in str(exc)
    else:
        raise AssertionError("expected ValueError for direct write without flag")


def test_promote_dry_run_does_not_change_raw(tmp_path):
    db_path = tmp_path / "bars.db"
    bars = aggregate_ticks_to_1m(_export_payload())
    upsert_bars_to_sqlite(db_path, bars)

    summary = promote_staged_bars(db_path, "AP888", ("2026-07-01 09:00:00", "2026-07-01 09:00:30"))

    assert summary["dry_run"] is True
    with sqlite3.connect(db_path) as conn:
        raw_exists = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='ap888_1M_raw'"
        ).fetchone()[0]
    assert raw_exists == 0


def test_promote_no_dry_run_writes_raw(tmp_path):
    db_path = tmp_path / "bars.db"
    bars = aggregate_ticks_to_1m(_export_payload())
    upsert_bars_to_sqlite(db_path, bars)

    summary = promote_staged_bars(
        db_path,
        "AP888",
        ("2026-07-01 09:00:00", "2026-07-01 09:00:30"),
        dry_run=False,
    )

    assert summary["dry_run"] is False
    assert summary["promoted_count"] == 1
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT datetime, close FROM ap888_1M_raw").fetchall()
    assert rows == [("2026-07-01 09:00:00", 102.0)]


def test_cli_promote_dry_run_by_default(tmp_path):
    export_path = tmp_path / "simnow_export_2026-07-01.json"
    db_path = tmp_path / "bars.db"
    summary_path = tmp_path / "summary.json"
    export_path.write_text(json.dumps(_export_payload(), ensure_ascii=False), encoding="utf-8")

    main([
        "--simnow-json", str(export_path),
        "--db-path", str(db_path),
        "--summary-json", str(summary_path),
        "--promote",
    ])

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["promote"] is True
    assert summary["dry_run"] is True
    with sqlite3.connect(db_path) as conn:
        raw_exists = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='ap888_1M_raw'"
        ).fetchone()[0]
    assert raw_exists == 0


def test_cli_promote_no_dry_run_writes_raw(tmp_path):
    export_path = tmp_path / "simnow_export_2026-07-01.json"
    db_path = tmp_path / "bars.db"
    summary_path = tmp_path / "summary.json"
    export_path.write_text(json.dumps(_export_payload(), ensure_ascii=False), encoding="utf-8")

    main([
        "--simnow-json", str(export_path),
        "--db-path", str(db_path),
        "--summary-json", str(summary_path),
        "--promote",
        "--no-dry-run",
    ])

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["promote"] is True
    assert summary["dry_run"] is False
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT datetime, close FROM ap888_1M_raw").fetchall()
    assert rows == [("2026-07-01 09:00:00", 102.0)]
