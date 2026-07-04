"""Unit tests for the A35 stop-loss stress diagnostic."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from stop_loss_stress_report import (
    BarLoader,
    _load_bars_from_sqlite,
    _normalize_pnl_pct,
    _resolve_direction,
    build_report,
    collect_stop_loss_pairs,
    scenario_gap_open_exit,
    scenario_intrabar_trigger,
    scenario_observed_close,
    scenario_penalty_slippage,
    write_json_report,
    write_markdown_report,
)


@pytest.fixture
def long_stop_pair() -> dict[str, object]:
    return {
        "_index": 0,
        "symbol": "TEST",
        "strategy": "long",
        "open_dt": "2024-01-01 09:00:00",
        "close_dt": "2024-01-01 10:00:00",
        "open_price": 100.0,
        "close_price": 92.0,
        "pnl_pct": -8.0,
        "exit_reason": "stop_loss",
        "direction": "long",
        "source_file": "test.json",
    }


@pytest.fixture
def short_stop_pair() -> dict[str, object]:
    return {
        "_index": 1,
        "symbol": "TEST",
        "strategy": "short",
        "open_dt": "2024-01-01 09:00:00",
        "close_dt": "2024-01-01 10:00:00",
        "open_price": 100.0,
        "close_price": 108.0,
        "pnl_pct": -8.0,
        "exit_reason": "stop_loss",
        "direction": "short",
        "source_file": "test.json",
    }


def make_bars(triggered: bool, direction: str) -> list[dict[str, object]]:
    if direction == "long":
        low = 95.0 if triggered else 97.5
        return [
            {"dt": datetime(2024, 1, 1, 9, 0), "open": 100.0, "high": 101.0, "low": low, "close": 99.0},
            {"dt": datetime(2024, 1, 1, 9, 1), "open": 99.0, "high": 100.0, "low": 97.5, "close": 98.0},
        ]
    low = 98.0
    high = 105.0 if triggered else 102.0
    return [
        {"dt": datetime(2024, 1, 1, 9, 0), "open": 100.0, "high": high, "low": low, "close": 101.0},
        {"dt": datetime(2024, 1, 1, 9, 1), "open": 101.0, "high": 102.0, "low": 99.0, "close": 100.0},
    ]


def test_normalize_pnl_pct_converts_fraction_to_percentage():
    assert _normalize_pnl_pct(-0.126) == pytest.approx(-12.6)
    assert _normalize_pnl_pct(-12.6) == pytest.approx(-12.6)


def test_resolve_direction_infers_long_when_price_and_pnl_agree():
    assert _resolve_direction({"pnl_pct": -8.0, "open_price": 100.0, "close_price": 92.0}) == "long"


def test_resolve_direction_infers_short_when_price_and_pnl_disagree():
    assert _resolve_direction({"pnl_pct": -8.0, "open_price": 100.0, "close_price": 108.0}) == "short"


def test_scenario_observed_close_counts_overshoot_and_multiple(long_stop_pair):
    trades, unavailable = scenario_observed_close([long_stop_pair], stop_loss_bp=300)
    assert len(trades) == 1
    assert trades[0]["pnl_pct"] == pytest.approx(-8.0)
    assert not unavailable
    summary = build_report_summary(trades, unavailable, 300)
    assert summary["overshoot_count"] == 1
    assert summary["max_overshoot_multiple"] == pytest.approx(8.0 / 3.0, rel=1e-4)
    assert summary["worst_loss_pct"] == pytest.approx(-8.0)


def test_scenario_intrabar_trigger_long_uses_stop_level(long_stop_pair):
    bars = make_bars(triggered=True, direction="long")
    loader = _StaticBarLoader({"TEST": bars})
    trades, unavailable = scenario_intrabar_trigger([long_stop_pair], loader, stop_loss_bp=300)
    assert len(trades) == 1
    assert trades[0]["triggered"] is True
    assert trades[0]["pnl_pct"] == pytest.approx(-3.0, abs=0.01)
    assert not unavailable


def test_scenario_intrabar_trigger_short_uses_stop_level(short_stop_pair):
    bars = make_bars(triggered=True, direction="short")
    loader = _StaticBarLoader({"TEST": bars})
    trades, unavailable = scenario_intrabar_trigger([short_stop_pair], loader, stop_loss_bp=300)
    assert len(trades) == 1
    assert trades[0]["triggered"] is True
    assert trades[0]["pnl_pct"] == pytest.approx(-3.0, abs=0.01)
    assert not unavailable


def test_scenario_intrabar_trigger_not_triggered_falls_back_to_close(long_stop_pair):
    bars = make_bars(triggered=False, direction="long")
    loader = _StaticBarLoader({"TEST": bars})
    trades, unavailable = scenario_intrabar_trigger([long_stop_pair], loader, stop_loss_bp=300)
    assert trades[0]["triggered"] is False
    assert trades[0]["pnl_pct"] == pytest.approx(-8.0, abs=0.01)


def test_scenario_gap_open_exit_detects_gap(long_stop_pair):
    bars = [
        {"dt": datetime(2024, 1, 1, 9, 0), "open": 100.0, "high": 101.0, "low": 98.0, "close": 99.0},
        # session gap
        {"dt": datetime(2024, 1, 1, 22, 1), "open": 95.0, "high": 96.0, "low": 94.0, "close": 95.5},
    ]
    loader = _StaticBarLoader({"TEST": bars})
    trades, unavailable = scenario_gap_open_exit([long_stop_pair], loader, stop_loss_bp=300)
    assert len(trades) == 1
    assert trades[0]["triggered"] is True
    assert trades[0]["gap_method"] == "session_gap"
    assert trades[0]["pnl_pct"] == pytest.approx(-5.0, abs=0.01)


def test_scenario_penalty_slippage_worsens_loss(long_stop_pair):
    loader = _StaticBarLoader({})
    trades, unavailable = scenario_penalty_slippage([long_stop_pair], loader, stop_loss_bp=300, penalty_bp=10)
    assert len(trades) == 1
    assert trades[0]["pnl_pct"] == pytest.approx(-8.1, abs=0.01)
    assert not unavailable


def test_missing_open_price_and_no_bars_marks_unavailable(long_stop_pair):
    pair = {**long_stop_pair, "open_price": None, "direction": None}
    loader = _StaticBarLoader({})
    trades, unavailable = scenario_intrabar_trigger([pair], loader, stop_loss_bp=300)
    assert not trades
    assert unavailable[0]["reason"] == "missing_direction"


def test_missing_db_does_not_silently_pass(tmp_path):
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir()
    (diagnostics_dir / "trades.json").write_text(
        json.dumps(
            {
                "trades": [
                    {
                        "symbol": "TEST",
                        "open_dt": "2024-01-01 09:00:00",
                        "close_dt": "2024-01-01 10:00:00",
                        "open_price": 100.0,
                        "close_price": 92.0,
                        "pnl_pct": -0.08,
                        "reason_code": "stop_loss",
                        "direction": "long",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = build_report(
        diagnostics_dir=diagnostics_dir,
        db_path=None,
        stop_loss_bp=300,
    )
    assert report["status"] == "partial"
    assert report["scenarios"]["observed_close"]["status"] == "ok"
    assert report["scenarios"]["observed_close"]["trade_count"] == 1
    assert report["scenarios"]["intrabar_trigger"]["status"] == "unavailable"


def test_build_report_contains_required_fields(tmp_path):
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir()
    (diagnostics_dir / "trades.json").write_text(
        json.dumps(
            {
                "trades": [
                    {
                        "symbol": "TEST",
                        "open_dt": "2024-01-01 09:00:00",
                        "close_dt": "2024-01-01 10:00:00",
                        "open_price": 100.0,
                        "close_price": 92.0,
                        "pnl_pct": -0.08,
                        "reason_code": "stop_loss",
                        "direction": "long",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = build_report(diagnostics_dir=diagnostics_dir, db_path=None, stop_loss_bp=300)
    assert report["disclaimer"]
    assert "status" in report
    assert "stop_loss_bp" in report
    assert "data_source" in report
    assert "scenarios" in report
    assert "worst_trades" in report
    assert "unavailable_trades" in report
    assert "notes" in report
    for scenario in report["scenarios"].values():
        for key in (
            "status",
            "trade_count",
            "affected_trade_count",
            "affected_symbols",
            "worst_loss_pct",
            "overshoot_count",
            "max_overshoot_multiple",
            "avg_loss_pct",
            "sample_trades",
            "unavailable_count",
            "unavailable_reasons",
        ):
            assert key in scenario, f"missing {key}"


def test_load_bars_from_sqlite_handles_missing_db():
    bars, error = _load_bars_from_sqlite(Path("/nonexistent/db.db"), "TEST", datetime(2024, 1, 1), datetime(2024, 1, 2))
    assert bars is None
    assert "db_unavailable" in (error or "")


def test_load_bars_from_sqlite_reads_bars(tmp_path):
    db_path = tmp_path / "bars.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE kline (symbol TEXT, datetime TEXT, open REAL, high REAL, low REAL, close REAL)"
    )
    conn.execute(
        "INSERT INTO kline VALUES (?, ?, ?, ?, ?, ?)",
        ("TEST", "2024-01-01 09:00:00", 100.0, 101.0, 99.0, 100.5),
    )
    conn.commit()
    conn.close()
    bars, error = _load_bars_from_sqlite(db_path, "TEST", datetime(2024, 1, 1), datetime(2024, 1, 2))
    assert error is None
    assert len(bars) == 1
    assert bars[0]["low"] == 99.0


def test_generated_markdown_contains_disclaimer_and_metrics(tmp_path):
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir()
    (diagnostics_dir / "trades.json").write_text(
        json.dumps(
            {
                "trades": [
                    {
                        "symbol": "TEST",
                        "open_dt": "2024-01-01 09:00:00",
                        "close_dt": "2024-01-01 10:00:00",
                        "open_price": 100.0,
                        "close_price": 92.0,
                        "pnl_pct": -0.08,
                        "reason_code": "stop_loss",
                        "direction": "long",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = build_report(diagnostics_dir=diagnostics_dir, db_path=None)
    md_path = tmp_path / "report.md"
    write_markdown_report(report, md_path)
    text = md_path.read_text(encoding="utf-8")
    assert "Diagnostic only" in text
    assert "observed_close" in text
    assert "intrabar_trigger" in text
    assert "gap_open_exit" in text
    assert "penalty_slippage" in text
    assert "GOAL PASSED" not in text


def test_generated_json_contains_no_goal_passed(tmp_path):
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir()
    (diagnostics_dir / "trades.json").write_text(
        json.dumps({"trades": []}), encoding="utf-8"
    )
    report = build_report(diagnostics_dir=diagnostics_dir, db_path=None)
    json_path = tmp_path / "report.json"
    write_json_report(report, json_path)
    text = json_path.read_text(encoding="utf-8")
    assert "GOAL PASSED" not in text


def test_script_does_not_contain_trading_interface_calls():
    script = (DIAG / "stop_loss_stress_report.py").read_text(encoding="utf-8")
    forbidden = ("send_order", "cancel_order", "buy(", "sell(", "short(", "cover(")
    found = [token for token in forbidden if token in script]
    assert not found, f"found forbidden trading interface tokens: {found}"


def test_collect_stop_loss_pairs_finds_stop_loss_records(tmp_path):
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir()
    (diagnostics_dir / "trades.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "symbol": "TEST",
                        "open_dt": "2024-01-01 09:00:00",
                        "close_dt": "2024-01-01 10:00:00",
                        "open_price": 100.0,
                        "close_price": 92.0,
                        "pnl_pct": -0.08,
                        "reason_code": "stop_loss",
                        "direction": "long",
                    },
                    {
                        "symbol": "TEST",
                        "pnl_pct": 0.01,
                        "reason_code": "trailing_stop",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    pairs = collect_stop_loss_pairs(diagnostics_dir)
    assert len(pairs) == 1
    assert pairs[0]["pnl_pct"] == pytest.approx(-8.0)


class _StaticBarLoader:
    """Test helper that returns pre-defined bars for any symbol/window."""

    def __init__(self, symbol_bars: dict[str, list[dict[str, object]]]):
        self._bars = symbol_bars

    def load(self, symbol: str | None, start_dt: datetime, end_dt: datetime):
        if symbol in self._bars:
            return self._bars[symbol], None
        return None, "no_bars"


def build_report_summary(trades, unavailable, stop_loss_bp):
    """Re-export the private summary helper for tests."""
    from stop_loss_stress_report import _scenario_summary

    return _scenario_summary(trades, unavailable, stop_loss_bp)
