"""Unit tests for A44 P5 resonance filter comparison diagnostic."""
from __future__ import annotations

from pathlib import Path

import pytest

import diagnostics.resonance_filter_comparison_report as report


def test_empty_metrics_structure():
    empty = report._empty_metrics()
    assert empty["trade_count"] == 0
    assert empty["win_rate"] == 0.0
    assert empty["pairs"] == []


def test_overall_metrics_extracts_report_values():
    fake_report = {
        "total_trades": 5,
        "win_rate": 0.4,
        "profit_factor": 1.5,
        "total_return_pct": 3.0,
        "max_drawdown_pct": 2.0,
        "sharpe_ratio": 0.8,
        "both_long_short_bars": 1,
    }
    pairs = [
        {"pnl_pct": 0.01},
        {"pnl_pct": -0.005},
        {"pnl_pct": 0.02},
        {"pnl_pct": -0.01},
        {"pnl_pct": 0.015},
    ]
    metrics = report._overall_metrics(fake_report, pairs)
    assert metrics["trade_count"] == 5
    assert metrics["win_count"] == 3
    assert metrics["loss_count"] == 2
    assert metrics["win_rate"] == pytest.approx(0.4)
    assert metrics["profit_factor"] == pytest.approx(1.5)


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
    assert payload["resonance_filter"] == "off vs daily vs daily_4h"
    assert "not used to select or tune" in payload["note"]

    json_text = (tmp_path / "resonance_filter_comparison_report_test.json").read_text(encoding="utf-8")
    assert "RESEARCH-ONLY" in json_text
    md_text = (tmp_path / "resonance_filter_comparison_report_test.md").read_text(encoding="utf-8")
    assert "RESEARCH-ONLY" in md_text


def test_missing_database_returns_error_and_empty_metrics(tmp_path: Path):
    result = report._run_symbol("AP888", tmp_path / "missing.db", "2024-01-01", "2024-01-10")
    assert result["error"] == "database_not_found"
    assert result["off"]["trade_count"] == 0
    assert result["daily"]["trade_count"] == 0
    assert result["daily_4h"]["trade_count"] == 0


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
    assert "off" in payload["total_trades_by_mode"]
    assert "daily" in payload["total_trades_by_mode"]
    assert "daily_4h" in payload["total_trades_by_mode"]
