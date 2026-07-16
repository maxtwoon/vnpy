"""A83 — Portfolio ledger report unit tests.

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from chan_strategy.config import STRATEGY_CONFIG
from diagnostics.portfolio_ledger_report import (
    _build_ledger,
    _risk_sizing_config,
    _run_per_symbol_engines,
    _symbol_clusters,
)


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


def _dt(minute: int = 0) -> datetime:
    return datetime(2024, 1, 2, 9, 0) + timedelta(minutes=minute)


class FakeEngine:
    def __init__(
        self,
        symbol: str,
        equity_curve: list[dict[str, Any]],
        trades: list[dict[str, Any]],
        initial_capital: float = 1_000_000,
    ):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.equity_curve = equity_curve
        self.strategy = SimpleNamespace(get_combined_trades=lambda: list(trades))


def _make_result(
    symbol: str,
    margins: list[float],
    trades: list[dict[str, Any]],
    error: str | None = None,
) -> dict[str, Any]:
    if error is not None:
        return {"engine": None, "report": {"error": error}}
    equity_curve = [
        {"dt": _dt(i), "total_open_margin": m} for i, m in enumerate(margins)
    ]
    return {
        "engine": FakeEngine(symbol, equity_curve, trades),
        "report": {"symbol": symbol},
    }


def test_margin_sum_and_max_utilization():
    """Portfolio margin at each timestamp is the sum of per-symbol margins."""
    results = {
        "S1": _make_result("S1", [10_000.0, 20_000.0, 15_000.0], []),
        "S2": _make_result("S2", [5_000.0, 12_000.0, 8_000.0], []),
    }

    payload = _build_ledger(results, 100_000.0, {})

    assert payload["portfolio_summary"]["max_total_open_margin"] == pytest.approx(
        32_000.0
    )
    assert payload["portfolio_summary"]["final_total_open_margin"] == pytest.approx(
        23_000.0
    )
    assert payload["portfolio_summary"]["max_margin_utilization_pct"] == pytest.approx(
        0.32
    )

    ledger = payload["ledger"]
    assert len(ledger) == 3
    assert ledger[0]["total_open_margin"] == pytest.approx(15_000.0)
    assert ledger[1]["total_open_margin"] == pytest.approx(32_000.0)
    assert ledger[2]["total_open_margin"] == pytest.approx(23_000.0)


def test_realized_pnl_sum_per_symbol_and_total():
    """Realized currency PnL is summed per symbol and across the portfolio."""
    results = {
        "S1": _make_result(
            "S1",
            [0.0, 0.0],
            [{"pnl_currency": 1_000.0}, {"pnl_currency": -300.0}],
        ),
        "S2": _make_result(
            "S2",
            [0.0, 0.0],
            [{"pnl_currency": 2_500.0}],
        ),
    }

    payload = _build_ledger(results, 1_000_000.0, {})

    assert payload["portfolio_summary"]["total_realized_pnl_currency"] == pytest.approx(
        3_200.0
    )
    assert payload["per_symbol"]["S1"]["total_realized_pnl_currency"] == pytest.approx(
        700.0
    )
    assert payload["per_symbol"]["S2"]["total_realized_pnl_currency"] == pytest.approx(
        2_500.0
    )


def test_cluster_grouping_uses_config_clusters():
    """Cluster breakdowns aggregate margins for symbols listed in corr_clusters."""
    results = {
        "RB888": _make_result("RB888", [10_000.0, 20_000.0], []),
        "ZN888": _make_result("ZN888", [5_000.0, 8_000.0], []),
        "SC888": _make_result("SC888", [2_000.0, 4_000.0], []),
        "AP888": _make_result("AP888", [1_000.0, 1_000.0], []),
    }
    clusters = {"industrial_energy": ["RB888", "ZN888", "SC888"]}

    payload = _build_ledger(results, 1_000_000.0, clusters)

    cluster = payload["per_cluster"]["industrial_energy"]
    assert cluster["symbols"] == ["RB888", "ZN888", "SC888"]
    assert cluster["max_total_open_margin"] == pytest.approx(32_000.0)
    assert cluster["final_total_open_margin"] == pytest.approx(32_000.0)

    uncategorized = payload["per_cluster"]["_uncategorized"]
    assert uncategorized["symbols"] == ["AP888"]
    assert uncategorized["max_total_open_margin"] == pytest.approx(1_000.0)


def test_symbol_with_error_is_reported_but_does_not_break_aggregation():
    """A symbol that failed to run contributes zero margin/PnL and is flagged."""
    results = {
        "S1": _make_result("S1", [10_000.0], []),
        "S2": _make_result("S2", [], [], error="data_load_failed"),
    }

    payload = _build_ledger(results, 100_000.0, {})

    assert payload["symbol_errors"] == {"S2": "data_load_failed"}
    assert payload["per_symbol"]["S2"]["error"] == "data_load_failed"
    assert payload["portfolio_summary"]["max_total_open_margin"] == pytest.approx(
        10_000.0
    )
    assert payload["portfolio_summary"]["total_realized_pnl_currency"] == 0.0


def test_forward_fill_within_symbol_range():
    """Margins are forward-filled within a symbol's own range, not extrapolated."""
    # S1 has bars at 0,1,2; S2 only at 0 and 2.
    results = {
        "S1": _make_result("S1", [10_000.0, 12_000.0, 14_000.0], []),
        "S2": _make_result("S2", [5_000.0, 0.0, 6_000.0], []),
    }
    # Override S2 equity curve to drop the middle bar.
    results["S2"]["engine"].equity_curve = [
        {"dt": _dt(0), "total_open_margin": 5_000.0},
        {"dt": _dt(2), "total_open_margin": 6_000.0},
    ]

    payload = _build_ledger(results, 100_000.0, {})

    ledger = {row["dt"]: row["total_open_margin"] for row in payload["ledger"]}
    assert ledger[_dt(0).isoformat(sep=" ")] == pytest.approx(15_000.0)
    # S2 forward-filled to 5_000 at dt=1.
    assert ledger[_dt(1).isoformat(sep=" ")] == pytest.approx(17_000.0)
    assert ledger[_dt(2).isoformat(sep=" ")] == pytest.approx(20_000.0)


def test_symbol_clusters_maps_case_insensitive():
    """Cluster membership is case-insensitive for symbol matching."""
    clusters = {"group": ["rb888", "ZN888"]}
    mapping = _symbol_clusters(clusters, ["RB888", "zn888", "AP888"])
    assert mapping["RB888"] == ["group"]
    assert mapping["zn888"] == ["group"]
    assert mapping["AP888"] == []


def test_risk_sizing_config_restores_previous_value():
    """The sizing_model override is reverted after the context exits."""
    STRATEGY_CONFIG["sizing_model"] = "research"
    with _risk_sizing_config():
        assert STRATEGY_CONFIG["sizing_model"] == "risk"
    assert STRATEGY_CONFIG["sizing_model"] == "research"


def test_risk_sizing_config_restores_missing_key():
    """If sizing_model was absent, it is removed after the context exits."""
    STRATEGY_CONFIG.pop("sizing_model", None)
    with _risk_sizing_config():
        assert STRATEGY_CONFIG["sizing_model"] == "risk"
    assert "sizing_model" not in STRATEGY_CONFIG


def test_run_per_symbol_engines_sets_risk_sizing(monkeypatch):
    """_run_per_symbol_engines forces sizing_model='risk' during execution."""
    STRATEGY_CONFIG["sizing_model"] = "research"
    captured: list[str] = []

    def fake_run_per_symbol(self) -> dict[str, Any]:
        captured.append(STRATEGY_CONFIG.get("sizing_model"))
        return {
            "S1": {
                "engine": FakeEngine("S1", [], []),
                "report": {"symbol": "S1"},
            }
        }

    monkeypatch.setattr(
        "chan_strategy.portfolio_engine.PortfolioEngine._run_per_symbol",
        fake_run_per_symbol,
    )

    result = _run_per_symbol_engines(["S1"])

    assert captured == ["risk"]
    assert "S1" in result
    assert STRATEGY_CONFIG["sizing_model"] == "research"


def test_methodology_states_independent_aggregation():
    """The report honestly labels itself as independent-run aggregation."""
    results = {"S1": _make_result("S1", [0.0], [])}
    payload = _build_ledger(results, 1_000_000.0, {})

    note = payload["methodology"]["note"]
    assert "independently-run" in note
    assert "NOT a true joint" in note
    assert payload["methodology"]["sizing_model"] == "risk"
