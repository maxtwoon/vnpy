"""Unit tests for A43 MACD-area divergence comparison diagnostic."""
from __future__ import annotations

from pathlib import Path

import pytest

import diagnostics.divergence_model_comparison_report as report


def test_empty_metrics_structure():
    empty = report._empty_metrics()
    assert empty["trade_count"] == 0
    assert empty["win_rate"] == 0.0
    assert empty["first_buy_pairs"] == []


def test_first_buy_metrics_extracts_sub_strategy():
    fake_report = {
        "sub_strategies": {
            "一买多头": {
                "total_trades": 3,
                "win_count": 1,
                "loss_count": 2,
                "win_rate": 1 / 3,
                "profit_factor": 0.5,
                "avg_profit": 0.02,
                "avg_loss": 0.01,
            },
        },
        "total_return_pct": 5.0,
        "max_drawdown_pct": 3.0,
    }
    pairs = [
        {"strategy": "一买多头", "pnl_pct": 0.01},
        {"strategy": "二买多头", "pnl_pct": -0.01},
    ]
    metrics = report._first_buy_metrics(fake_report, pairs)
    assert metrics["trade_count"] == 3
    assert metrics["win_rate"] == pytest.approx(1 / 3)
    assert len(metrics["first_buy_pairs"]) == 1
    assert metrics["first_buy_pairs"][0]["strategy"] == "一买多头"


def test_report_disclaimer_contains_research_only(tmp_path: Path):
    payload = report.main(
        db_path=tmp_path / "missing.db",
        symbols=("AP888",),
        start_date="2024-01-01",
        end_date="2024-01-10",
        out_dir=tmp_path,
        stamp="test",
    )
    assert "RESEARCH-ONLY" in payload["disclaimer"]
    assert payload["macd_params"]["fast"] == 12
    assert payload["macd_params"]["slow"] == 26
    assert payload["macd_params"]["signal"] == 9

    json_text = (tmp_path / "divergence_model_comparison_report_test.json").read_text(encoding="utf-8")
    assert "RESEARCH-ONLY" in json_text
    md_text = (tmp_path / "divergence_model_comparison_report_test.md").read_text(encoding="utf-8")
    assert "RESEARCH-ONLY" in md_text


def test_missing_database_returns_error_and_empty_metrics(tmp_path: Path):
    result = report._run_symbol("AP888", tmp_path / "missing.db", "2024-01-01", "2024-01-10")
    assert result["error"] == "database_not_found"
    assert result["amplitude"]["trade_count"] == 0
    assert result["macd"]["trade_count"] == 0


def test_build_payload_includes_window_and_params(tmp_path: Path):
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
    assert payload["macd_params"]["fast"] == 12
    assert payload["total_symbols"] == 2
    assert len(payload["per_symbol"]) == 2
