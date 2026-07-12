"""Unit tests for A50 limit-up/down/halt exposure diagnostic."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from conftest import make_raw_bar

import diagnostics.limit_halt_exposure_report as report


def test_empty_metrics_structure():
    empty = report._empty_metrics()
    assert empty["trade_count"] == 0
    assert empty["entry_at_limit_count"] == 0
    assert empty["exit_at_limit_count"] == 0
    assert empty["entry_not_at_limit_count"] == 0
    assert empty["exit_not_at_limit_count"] == 0
    assert empty["trades"] == []


def test_daily_prev_close_map():
    bars = [
        make_raw_bar(0, datetime(2024, 1, 2, 9, 0), open_=100.0, close=101.0),
        make_raw_bar(1, datetime(2024, 1, 2, 10, 0), open_=101.0, close=102.0),
        make_raw_bar(2, datetime(2024, 1, 3, 9, 0), open_=102.0, close=103.0),
    ]
    prev_map = report._daily_prev_close_map(bars)
    assert prev_map[datetime(2024, 1, 2).date()][0] is None
    assert prev_map[datetime(2024, 1, 3).date()][0] == 102.0


def test_bar_at_limit_flags_high_and_low():
    bar = make_raw_bar(0, datetime(2024, 1, 2, 9, 0), open_=100.0, close=101.0, high=105.0, low=99.0)
    at_limit, upper, lower = report._bar_at_limit(bar, 100.0, 0.05)
    assert upper == 105.0
    assert lower == 95.0
    assert at_limit is True

    bar2 = make_raw_bar(1, datetime(2024, 1, 2, 9, 0), open_=100.0, close=101.0, high=104.0, low=96.0)
    assert report._bar_at_limit(bar2, 100.0, 0.05)[0] is False


def test_bar_at_limit_without_prev_close():
    bar = make_raw_bar(0, datetime(2024, 1, 2, 9, 0), open_=100.0, close=101.0)
    at_limit, upper, lower = report._bar_at_limit(bar, None, 0.05)
    assert at_limit is False
    assert upper is None
    assert lower is None


def test_zero_volume_near_unavailable_and_true():
    bars = [
        make_raw_bar(0, datetime(2024, 1, 2, 9, 0), open_=100.0, close=100.0),
        make_raw_bar(1, datetime(2024, 1, 2, 10, 0), open_=100.0, close=100.0),
    ]
    assert report._zero_volume_near(bars, 0) is False

    zero_bar = make_raw_bar(2, datetime(2024, 1, 2, 11, 0), open_=100.0, close=100.0)
    zero_bar.vol = 0
    bars_with_zero = bars + [zero_bar]
    assert report._zero_volume_near(bars_with_zero, 2) is True

    class NoVolBar:
        dt = datetime(2024, 1, 2, 9, 0)
        high = 100.0
        low = 100.0

    assert report._zero_volume_near([NoVolBar()], 0) == "unavailable"


def test_compute_trade_diagnostics_reconciles_counts():
    prev_day = datetime(2024, 1, 2)
    today = datetime(2024, 1, 3)
    raw_bars = [
        make_raw_bar(0, prev_day + timedelta(hours=9), open_=100.0, close=100.0),
        make_raw_bar(1, prev_day + timedelta(hours=10), open_=100.0, close=100.0),
        make_raw_bar(2, today + timedelta(hours=9), open_=100.0, close=105.0, high=105.0, low=100.0),
        make_raw_bar(3, today + timedelta(hours=10), open_=100.0, close=100.0),
    ]
    trade_bars = [
        make_raw_bar(2, today + timedelta(hours=9), open_=100.0, close=105.0, high=105.0, low=100.0),
        make_raw_bar(3, today + timedelta(hours=10), open_=100.0, close=100.0),
    ]
    pairs = [
        {"open_dt": trade_bars[0].dt, "close_dt": trade_bars[1].dt, "strategy": "一买多头"},
        {"open_dt": trade_bars[1].dt, "close_dt": trade_bars[1].dt, "strategy": "一买多头"},
    ]
    diags = report._compute_trade_diagnostics(pairs, trade_bars, raw_bars, 0.05)
    assert len(diags) == len(pairs)

    entry_at = sum(1 for d in diags if d.entry_at_limit)
    exit_at = sum(1 for d in diags if d.exit_at_limit)
    assert entry_at + (len(pairs) - entry_at) == len(pairs)
    assert exit_at + (len(pairs) - exit_at) == len(pairs)

    # First trade enters at the bar whose high equals the upper limit (100 * 1.05)
    assert diags[0].entry_at_limit is True
    # First trade exits at the non-limit bar
    assert diags[0].exit_at_limit is False


def test_missing_database_returns_error_and_empty_metrics(tmp_path: Path):
    result = report._run_symbol("AP888", tmp_path / "missing.db", "2024-01-01", "2024-01-10")
    assert result["error"] == "database_not_found"
    assert result["metrics"]["trade_count"] == 0


def test_report_disclaimer_contains_research_only(tmp_path: Path):
    payload = report.main(
        db_path=tmp_path / "missing.db",
        out_dir=tmp_path,
        symbols=("AP888",),
        start_date="2024-01-01",
        end_date="2024-01-10",
        stamp="test",
    )
    assert "RESEARCH-ONLY" in payload["disclaimer"]
    json_text = (tmp_path / "limit_halt_exposure_report_test.json").read_text(encoding="utf-8")
    md_text = (tmp_path / "limit_halt_exposure_report_test.md").read_text(encoding="utf-8")
    assert "RESEARCH-ONLY" in json_text
    assert "RESEARCH-ONLY" in md_text
    assert "unavailable" not in payload["per_symbol"][0]["error"]


def test_build_payload_includes_window_and_totals(tmp_path: Path):
    payload = report._build_payload(
        tmp_path / "missing.db",
        ("AP888", "RB888"),
        "2024-01-01",
        "2024-01-10",
        "test",
    )
    assert payload["disclaimer"]
    assert payload["window"]["start_date"] == "2024-01-01"
    assert payload["window"]["end_date"] == "2024-01-10"
    assert payload["total_symbols"] == 2
    assert len(payload["per_symbol"]) == 2
    assert "trade_count" in payload["totals"]
    assert "entry_at_limit_count" in payload["totals"]


def test_limit_sources_cited_for_all_default_symbols():
    for symbol in report.SYMBOLS:
        cfg = report.SYMBOL_LIMIT_CONFIG.get(symbol)
        assert cfg is not None, f"missing limit config for {symbol}"
        assert cfg["limit_pct"] > 0
        assert cfg["source"]
        assert "http" in cfg["source"] or "交易所" in cfg["source"] or "SHFE" in cfg["source"] or "INE" in cfg["source"] or "DCE" in cfg["source"] or "CZCE" in cfg["source"]
