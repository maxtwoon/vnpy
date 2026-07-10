"""Unit tests for A39 rollover exclusion diagnostic."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

import diagnostics.rollover_exclusion_report as report


@pytest.fixture
def rollover_db(tmp_path: Path):
    """Build a tiny DB with AP888-style real_symbol transitions."""
    db = tmp_path / "rollover.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE ap888_1M_raw ("
        "datetime TEXT, symbol TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, amount REAL, real_symbol TEXT"
        ")"
    )
    rows = [
        # Day-session bars for two trading days
        ("2024-01-02 09:00:00", "AP888", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0, "AP2401"),
        ("2024-01-02 10:00:00", "AP888", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0, "AP2401"),
        ("2024-01-03 09:00:00", "AP888", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0, "AP2401"),
        ("2024-01-03 10:00:00", "AP888", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0, "AP2401"),
        # Rollover to AP2405 on 2024-01-04
        ("2024-01-04 09:00:00", "AP888", 110.0, 111.0, 109.0, 110.0, 1000.0, 100000.0, "AP2405"),
        ("2024-01-04 10:00:00", "AP888", 110.0, 111.0, 109.0, 110.0, 1000.0, 100000.0, "AP2405"),
    ]
    conn.executemany("INSERT INTO ap888_1M_raw VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return db


def test_detect_transitions_finds_real_symbol_changes(rollover_db: Path):
    result = report._detect_transitions(rollover_db, "AP888")
    assert result["unavailable"] is None
    assert result["detection_method"] == "real_symbol"
    assert len(result["transition_dates"]) == 1
    tr = result["transition_dates"][0]
    assert tr["date"] == "2024-01-04"
    assert tr["from_contract"] == "AP2401"
    assert tr["to_contract"] == "AP2405"


def test_detect_transitions_honors_window(rollover_db: Path):
    # Restrict to before the rollover; no transitions should be reported.
    result = report._detect_transitions(rollover_db, "AP888", start_date="2024-01-01", end_date="2024-01-03")
    assert result["unavailable"] is None
    assert result["transition_dates"] == []


def test_detect_transitions_mark_missing_table(rollover_db: Path):
    result = report._detect_transitions(rollover_db, "XX888")
    assert result["unavailable"].startswith("table_not_found")


def test_detect_transitions_mark_missing_column(tmp_path: Path):
    db = tmp_path / "no_real_symbol.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE ap888_1M_raw (datetime TEXT, symbol TEXT, open REAL, real_symbol_missing TEXT)"
    )
    conn.execute("INSERT INTO ap888_1M_raw VALUES (?,?,?,?)", ("2024-01-02 09:00:00", "AP888", 100.0, "AP2401"))
    conn.commit()
    conn.close()
    result = report._detect_transitions(db, "AP888")
    assert result["unavailable"] == "no_real_symbol_column"


def test_exclusion_window_expands_to_neighbor_trading_dates(rollover_db: Path):
    transitions = report._detect_transitions(rollover_db, "AP888")
    trading_dates = report._trading_dates_from_bars(rollover_db, "AP888")
    excluded = report._exclusion_dates(transitions["transition_dates"], trading_dates)
    # Transition on 2024-01-04 excludes prev (01-03), transition (01-04), and next (none in fixture).
    assert date("2024-01-03") in excluded
    assert date("2024-01-04") in excluded


def test_pair_in_exclusion_window_uses_open_and_close_dates():
    excluded = {datetime(2024, 1, 4).date()}
    inside = {"open_dt": datetime(2024, 1, 4, 9, 0), "close_dt": datetime(2024, 1, 5, 9, 0)}
    outside = {"open_dt": datetime(2024, 1, 2, 9, 0), "close_dt": datetime(2024, 1, 3, 9, 0)}
    assert report._pair_in_exclusion_window(inside, excluded) is True
    assert report._pair_in_exclusion_window(outside, excluded) is False


def test_metrics_from_pairs_computes_required_fields():
    pairs = [
        {"pnl_pct": 0.01, "exit_reason": "signal_exit"},
        {"pnl_pct": -0.02, "exit_reason": "stop_loss"},
        {"pnl_pct": -0.05, "exit_reason": "stop_loss"},
    ]
    metrics = report._metrics_from_pairs(pairs)
    assert metrics["trade_count"] == 3
    assert metrics["return"] == pytest.approx(-6.0, abs=1e-4)
    assert metrics["drawdown"] >= 0
    assert metrics["stop_loss_overshoot"]["overshoot_count"] == 1


def date(iso: str):
    from datetime import date as _date
    return _date.fromisoformat(iso)
