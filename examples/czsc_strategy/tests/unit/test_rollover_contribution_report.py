"""A73 — Unit tests for rollover-window return contribution report.

Tests use constructed ``Position.pairs``-style fixtures only; no real historical
DB dependency.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import diagnostics.rollover_contribution_report as report
from chan_strategy.config import STRATEGY_CONFIG


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


@pytest.fixture
def sample_pairs() -> list[dict]:
    """Five closed trades: two inside rollover window, three outside."""
    return [
        {
            "open_dt": datetime(2024, 1, 10, 9, 0),
            "close_dt": datetime(2024, 1, 10, 10, 0),
            "pnl_pct": 0.01,
            "is_rollover_window": False,
        },
        {
            "open_dt": datetime(2024, 1, 15, 9, 0),
            "close_dt": datetime(2024, 1, 15, 10, 0),
            "pnl_pct": -0.005,
            "is_rollover_window": True,
        },
        {
            "open_dt": datetime(2024, 1, 16, 9, 0),
            "close_dt": datetime(2024, 1, 16, 10, 0),
            "pnl_pct": 0.02,
            "is_rollover_window": True,
        },
        {
            "open_dt": datetime(2024, 2, 1, 9, 0),
            "close_dt": datetime(2024, 2, 1, 10, 0),
            "pnl_pct": -0.01,
            "is_rollover_window": False,
        },
        {
            "open_dt": datetime(2024, 2, 5, 9, 0),
            "close_dt": datetime(2024, 2, 5, 10, 0),
            "pnl_pct": 0.015,
            "is_rollover_window": False,
        },
    ]


def test_aggregate_pairs_empty():
    metrics = report._aggregate_pairs([])
    assert metrics["trade_count"] == 0
    assert metrics["total_return_pct"] == 0.0
    assert metrics["win_rate"] == 0.0
    assert metrics["avg_pnl_pct"] == 0.0


def test_aggregate_pairs_all_win():
    pairs = [
        {"pnl_pct": 0.01},
        {"pnl_pct": 0.02},
        {"pnl_pct": 0.005},
    ]
    metrics = report._aggregate_pairs(pairs)
    assert metrics["trade_count"] == 3
    assert metrics["total_return_pct"] == pytest.approx(3.5, abs=1e-4)
    assert metrics["win_rate"] == 1.0
    assert metrics["avg_pnl_pct"] == pytest.approx(3.5 / 3, abs=1e-4)


def test_aggregate_pairs_all_loss():
    pairs = [
        {"pnl_pct": -0.01},
        {"pnl_pct": -0.02},
    ]
    metrics = report._aggregate_pairs(pairs)
    assert metrics["trade_count"] == 2
    assert metrics["total_return_pct"] == pytest.approx(-3.0, abs=1e-4)
    assert metrics["win_rate"] == 0.0
    assert metrics["avg_pnl_pct"] == pytest.approx(-1.5, abs=1e-4)


def test_aggregate_pairs_mixed():
    pairs = [
        {"pnl_pct": 0.01},
        {"pnl_pct": -0.02},
        {"pnl_pct": 0.005},
        {"pnl_pct": -0.005},
    ]
    metrics = report._aggregate_pairs(pairs)
    assert metrics["trade_count"] == 4
    assert metrics["total_return_pct"] == pytest.approx(-1.0, abs=1e-4)
    assert metrics["win_rate"] == 0.5
    assert metrics["avg_pnl_pct"] == pytest.approx(-0.25, abs=1e-4)


def test_aggregate_pairs_ignores_missing_pnl():
    pairs = [{}, {"pnl_pct": 0.01}]
    metrics = report._aggregate_pairs(pairs)
    assert metrics["total_return_pct"] == pytest.approx(1.0, abs=1e-4)


def test_require_rollover_tagging_raises_when_off():
    STRATEGY_CONFIG["rollover_stat_tagging"] = "off"
    with pytest.raises(RuntimeError) as excinfo:
        report._require_rollover_tagging()
    assert "rollover_stat_tagging" in str(excinfo.value)
    assert "'on'" in str(excinfo.value)


def test_require_rollover_tagging_passes_when_on():
    STRATEGY_CONFIG["rollover_stat_tagging"] = "on"
    report._require_rollover_tagging()


def test_run_report_requires_rollover_tagging():
    STRATEGY_CONFIG["rollover_stat_tagging"] = "off"
    with pytest.raises(RuntimeError):
        report.run_report(Path("/dev/null"), ["AP888"], "2024-01-01", "2024-01-31")


def test_run_report_splits_pairs_by_rollover_flag(tmp_path: Path, sample_pairs: list[dict]):
    STRATEGY_CONFIG["rollover_stat_tagging"] = "on"

    class _MockStrategy:
        def get_combined_trades(self) -> list[dict]:
            return [dict(p) for p in sample_pairs]

    class _MockEngine:
        def __init__(self, **kwargs) -> None:
            self.strategy = _MockStrategy()

        def run(self, warmup_bars: int = 0) -> dict:
            return {"total_bars": 100, "traded_bars": 50}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(report, "BacktestEngine", _MockEngine)
    monkeypatch.setattr(report, "_dominant_symbol", lambda _db, _table, _start, _end: "AP888")

    payload = report.run_report(
        db_path=tmp_path / "missing.db",
        symbols=["AP888"],
        start="2024-01-01",
        end="2024-01-31",
        quiet=True,
    )

    data = payload["symbols"]["AP888"]
    assert data["total_trades"] == 5
    assert data["rollover"]["trade_count"] == 2
    assert data["non_rollover"]["trade_count"] == 3
    assert data["rollover"]["total_return_pct"] == pytest.approx(1.5, abs=1e-4)
    assert data["non_rollover"]["total_return_pct"] == pytest.approx(1.5, abs=1e-4)
    assert data["rollover"]["win_rate"] == 0.5
    assert data["non_rollover"]["win_rate"] == pytest.approx(2 / 3, abs=1e-4)

    monkeypatch.undo()


def test_run_report_propagates_engine_error(tmp_path: Path):
    STRATEGY_CONFIG["rollover_stat_tagging"] = "on"

    class _MockEngine:
        def __init__(self, **kwargs) -> None:
            pass

        def run(self, warmup_bars: int = 0) -> dict:
            return {"error": "data load failed"}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(report, "BacktestEngine", _MockEngine)
    monkeypatch.setattr(report, "_dominant_symbol", lambda _db, _table, _start, _end: "AP888")

    payload = report.run_report(
        db_path=tmp_path / "missing.db",
        symbols=["AP888"],
        start="2024-01-01",
        end="2024-01-31",
        quiet=True,
    )

    data = payload["symbols"]["AP888"]
    assert "error" in data
    assert data["rollover"]["trade_count"] == 0
    assert data["non_rollover"]["trade_count"] == 0

    monkeypatch.undo()


def test_write_outputs_contains_research_only_banner(tmp_path: Path, sample_pairs: list[dict]):
    STRATEGY_CONFIG["rollover_stat_tagging"] = "on"

    class _MockStrategy:
        def get_combined_trades(self) -> list[dict]:
            return [dict(p) for p in sample_pairs]

    class _MockEngine:
        def __init__(self, **kwargs) -> None:
            self.strategy = _MockStrategy()

        def run(self, warmup_bars: int = 0) -> dict:
            return {"total_bars": 100}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(report, "BacktestEngine", _MockEngine)
    monkeypatch.setattr(report, "_dominant_symbol", lambda _db, _table, _start, _end: "AP888")

    payload = report.run_report(
        db_path=tmp_path / "missing.db",
        symbols=["AP888"],
        start="2024-01-01",
        end="2024-01-31",
        quiet=True,
    )
    json_path, md_path = report.write_outputs(payload, tmp_path, "test")

    assert json_path.exists()
    assert md_path.exists()
    assert "RESEARCH-ONLY" in md_path.read_text(encoding="utf-8")
    assert "Rollover window" in md_path.read_text(encoding="utf-8")
    assert "Non-rollover window" in md_path.read_text(encoding="utf-8")

    monkeypatch.undo()
