import json
import sqlite3
import sys
from pathlib import Path

import pytest


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_tick_bars import (  # noqa: E402
    aggregate_ticks_to_1m,
    promote_staged_bars,
    summarize_bars,
    upsert_bars_to_sqlite,
)


def _export_payload() -> dict:
    return {
        "meta": {
            "contract_map": {
                "AP888": {"symbol": "ap610", "exchange": "CZCE", "enabled": True},
                "SC888": {"symbol": "sc2608", "exchange": "INE", "enabled": True},
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
                {
                    "dt": "2026-07-01 09:01:00+08:00",
                    "symbol": "ap610",
                    "exchange": "CZCE",
                    "last_price": 101.0,
                    "volume": 1010,
                },
                {
                    "dt": "2026-07-01 09:00:10+08:00",
                    "symbol": "sc2608",
                    "exchange": "INE",
                    "last_price": 450.0,
                    "volume": 200,
                },
            ]
        },
    }


def test_aggregate_ticks_to_1m_uses_contract_map_and_volume_deltas():
    bars = aggregate_ticks_to_1m(_export_payload())

    assert [bar["symbol"] for bar in bars] == ["AP888", "SC888", "AP888"]
    first = bars[0]
    assert first["datetime"] == "2026-07-01 09:00:00"
    assert first["open"] == 100.0
    assert first["high"] == 102.0
    assert first["low"] == 100.0
    assert first["close"] == 102.0
    assert first["volume"] == 5.0
    assert first["amount"] == 0.0
    assert first["source"] == "simnow_tick_agg"
    assert first["vt_symbol"] == "ap610.CZCE"

    single_tick_bar = bars[1]
    assert single_tick_bar["symbol"] == "SC888"
    assert single_tick_bar["volume"] == 0.0

    second_minute = bars[2]
    assert second_minute["datetime"] == "2026-07-01 09:01:00"
    assert second_minute["volume"] == 5.0


def test_upsert_bars_to_sqlite_staging_default_never_touches_raw(tmp_path):
    db_path = tmp_path / "simnow_bars.db"
    bars = aggregate_ticks_to_1m(_export_payload())

    first = upsert_bars_to_sqlite(db_path, bars)

    assert first["inserted_or_replaced"] == 3
    assert first["kline_write_mode"] == "staging"
    with sqlite3.connect(db_path) as conn:
        raw_exists = conn.execute(
            "select count(*) from sqlite_master where type='table' and name='ap888_1M_raw'"
        ).fetchone()[0]
        staging_rows = conn.execute("select datetime, symbol, close, volume from ap888_1M_raw_staging order by datetime").fetchall()
        meta = conn.execute("select source, vt_symbol from simnow_bar_meta order by datetime, symbol").fetchall()
    assert raw_exists == 0
    assert staging_rows == [
        ("2026-07-01 09:00:00", "AP888", 102.0, 5.0),
        ("2026-07-01 09:01:00", "AP888", 101.0, 5.0),
    ]
    assert len(meta) == 3
    assert meta[0] == ("simnow_tick_agg", "ap610.CZCE")


def test_upsert_bars_to_sqlite_direct_requires_allow_direct_write(tmp_path):
    db_path = tmp_path / "simnow_bars.db"
    bars = aggregate_ticks_to_1m(_export_payload())

    with pytest.raises(ValueError, match="allow_direct_write"):
        upsert_bars_to_sqlite(db_path, bars, kline_write_mode="direct")


def test_upsert_bars_to_sqlite_direct_writes_raw_when_allowed(tmp_path):
    db_path = tmp_path / "simnow_bars.db"
    bars = aggregate_ticks_to_1m(_export_payload())

    result = upsert_bars_to_sqlite(db_path, bars, kline_write_mode="direct", allow_direct_write=True)

    assert result["kline_write_mode"] == "direct"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("select datetime, symbol, close, volume from ap888_1M_raw order by datetime").fetchall()
    assert rows == [
        ("2026-07-01 09:00:00", "AP888", 102.0, 5.0),
        ("2026-07-01 09:01:00", "AP888", 101.0, 5.0),
    ]


def test_promote_staged_bars_dry_run_default_does_not_write(tmp_path):
    db_path = tmp_path / "simnow_bars.db"
    bars = aggregate_ticks_to_1m(_export_payload())
    upsert_bars_to_sqlite(db_path, bars)

    summary = promote_staged_bars(db_path, "AP888", ("2026-07-01 09:00:00", "2026-07-01 09:01:00"))

    assert summary["dry_run"] is True
    assert summary["staged_count"] == 2
    assert summary["promoted_count"] == 0
    with sqlite3.connect(db_path) as conn:
        raw_exists = conn.execute(
            "select count(*) from sqlite_master where type='table' and name='ap888_1M_raw'"
        ).fetchone()[0]
    assert raw_exists == 0


def test_promote_staged_bars_writes_raw_when_dry_run_false(tmp_path):
    db_path = tmp_path / "simnow_bars.db"
    bars = aggregate_ticks_to_1m(_export_payload())
    upsert_bars_to_sqlite(db_path, bars)

    summary = promote_staged_bars(
        db_path,
        "AP888",
        ("2026-07-01 09:00:00", "2026-07-01 09:01:00"),
        dry_run=False,
    )

    assert summary["dry_run"] is False
    assert summary["staged_count"] == 2
    assert summary["promoted_count"] == 2
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("select datetime, symbol, close, volume from ap888_1M_raw order by datetime").fetchall()
    assert rows == [
        ("2026-07-01 09:00:00", "AP888", 102.0, 5.0),
        ("2026-07-01 09:01:00", "AP888", 101.0, 5.0),
    ]


def test_promote_staged_bars_reports_materially_different_overwrites(tmp_path):
    db_path = tmp_path / "simnow_bars.db"
    bars = aggregate_ticks_to_1m(_export_payload())
    upsert_bars_to_sqlite(db_path, bars)
    # Pre-seed raw with a different value for the same key.
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ap888_1M_raw ("
            "datetime TEXT NOT NULL, symbol TEXT NOT NULL, open REAL NOT NULL, "
            "high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, "
            "volume REAL NOT NULL, amount REAL NOT NULL, PRIMARY KEY (datetime, symbol))"
        )
        conn.execute(
            "INSERT OR REPLACE INTO ap888_1M_raw (datetime, symbol, open, high, low, close, volume, amount) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-07-01 09:00:00", "AP888", 99.0, 99.0, 99.0, 99.0, 1.0, 0.0),
        )
        conn.commit()

    summary = promote_staged_bars(db_path, "AP888", ("2026-07-01 09:00:00", "2026-07-01 09:01:00"))

    assert summary["overlapping_rows"] == 1
    assert summary["materially_different_overwrites"] == 1


def test_upsert_bars_to_sqlite_is_idempotent_in_staging(tmp_path):
    db_path = tmp_path / "simnow_bars.db"
    bars = aggregate_ticks_to_1m(_export_payload())

    first = upsert_bars_to_sqlite(db_path, bars)
    second = upsert_bars_to_sqlite(db_path, bars)

    assert first["inserted_or_replaced"] == 3
    assert second["inserted_or_replaced"] == 3
    with sqlite3.connect(db_path) as conn:
        staging_rows = conn.execute("select count(*) from ap888_1M_raw_staging").fetchone()[0]
    assert staging_rows == 2


def test_summarize_bars_reports_missing_subscribed_symbols(tmp_path):
    payload = _export_payload()
    payload["raw"]["ticks"] = [
        tick for tick in payload["raw"]["ticks"] if tick["symbol"] == "sc2608"
    ]
    bars = aggregate_ticks_to_1m(payload)

    summary = summarize_bars(tmp_path / "bars.db", bars, payload)

    assert summary["expected_symbols"] == ["AP888", "SC888"]
    assert summary["symbols"] == ["SC888"]
    assert summary["missing_symbols"] == ["AP888"]
    assert summary["coverage_by_symbol"] == {
        "SC888": {
            "bars": 1,
            "tick_count": 1,
            "start_datetime": "2026-07-01 09:00:00",
            "end_datetime": "2026-07-01 09:00:00",
        }
    }


def test_summarize_bars_reports_symbols_below_minimum_bar_coverage(tmp_path):
    bars = aggregate_ticks_to_1m(_export_payload())

    summary = summarize_bars(tmp_path / "bars.db", bars, _export_payload(), min_bars_per_symbol=2)

    assert summary["min_bars_per_symbol"] == 2
    assert summary["short_symbols"] == ["SC888"]
    assert summary["coverage_by_symbol"]["AP888"]["bars"] == 2
    assert summary["coverage_by_symbol"]["SC888"]["bars"] == 1


def test_cli_writes_summary_and_database(tmp_path):
    export_path = tmp_path / "simnow_export_2026-07-01.json"
    db_path = tmp_path / "bars.db"
    summary_path = tmp_path / "summary.json"
    export_path.write_text(json.dumps(_export_payload(), ensure_ascii=False), encoding="utf-8")

    from simnow_tick_bars import main

    main([
        "--simnow-json",
        str(export_path),
        "--db-path",
        str(db_path),
        "--summary-json",
        str(summary_path),
        "--min-bars-per-symbol",
        "2",
    ])

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["bars"] == 3
    assert summary["symbols"] == ["AP888", "SC888"]
    assert summary["missing_symbols"] == []
    assert summary["short_symbols"] == ["SC888"]
    assert summary["db_path"] == str(db_path)
    assert summary["kline_write_mode"] == "staging"
