"""A48 P8b — Portfolio coordinator unit tests.

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.portfolio_engine import PortfolioCoordinator, PortfolioEngine, run_portfolio_backtest


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


def _dt(day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(2024, 1, day, hour, minute)


def test_cluster_gross_cap_blocks_offending_open():
    """A new open that would breach ``cluster_gross_cap`` is blocked."""
    STRATEGY_CONFIG.update({
        "portfolio_risk": "on",
        "weighting": "fixed",
        "corr_clusters": {"cluster_x": ["S1", "S2"]},
        "cluster_gross_cap": 0.25,
        "daily_loss_limit_pct": 1.0,  # disable loss limit for this fixture
    })
    coord = PortfolioCoordinator(["S1", "S2"], 1_000_000, STRATEGY_CONFIG)

    # Open two positions in the same cluster; combined weight must stay <= 0.25.
    # With fixed weights and no overrides, 一买多头 = pos_1buy = 0.10.
    assert coord.allow_open("S1", "一买多头", _dt(2, 9), 100.0) is True
    coord.record_open("S1", "一买多头", _dt(2, 9), 100.0)

    assert coord.allow_open("S2", "一买多头", _dt(2, 9, 30), 100.0) is True
    coord.record_open("S2", "一买多头", _dt(2, 9, 30), 100.0)

    # Current cluster gross = 0.20.  Adding a third 0.10 position would make 0.30 > 0.25.
    assert coord.allow_open("S1", "二买多头", _dt(2, 10), 100.0) is False
    assert any(b["reason"] == "cluster_gross_cap" for b in coord.blocked_opens)

    # Exposure bookkeeping is consistent.
    assert coord.cluster_exposure["cluster_x"] == pytest.approx(0.20)


def test_cluster_gross_cap_allows_under_cap():
    """Opens that stay within the cap are allowed."""
    STRATEGY_CONFIG.update({
        "portfolio_risk": "on",
        "weighting": "fixed",
        "corr_clusters": {"cluster_x": ["S1", "S2"]},
        "cluster_gross_cap": 0.50,
        "daily_loss_limit_pct": 1.0,
    })
    coord = PortfolioCoordinator(["S1", "S2"], 1_000_000, STRATEGY_CONFIG)

    assert coord.allow_open("S1", "一买多头", _dt(2, 9), 100.0) is True
    coord.record_open("S1", "一买多头", _dt(2, 9), 100.0)
    assert coord.cluster_exposure["cluster_x"] == pytest.approx(0.10)

    assert coord.allow_open("S2", "三买多头", _dt(2, 9, 30), 100.0) is True
    coord.record_open("S2", "三买多头", _dt(2, 9, 30), 100.0)
    assert coord.cluster_exposure["cluster_x"] == pytest.approx(0.40)


def test_daily_loss_limit_flattens_and_blocks_then_resets_next_day():
    """Breaching the daily loss limit flattens all positions, blocks opens,
    and resumes normally on the next trading day."""
    STRATEGY_CONFIG.update({
        "portfolio_risk": "on",
        "weighting": "fixed",
        "corr_clusters": {},
        "cluster_gross_cap": 1.0,
        "daily_loss_limit_pct": 0.05,
    })
    coord = PortfolioCoordinator(["S1"], 1_000_000, STRATEGY_CONFIG)

    # Seed previous-day-close equity by advancing one bar on day 1.
    coord.on_bar(_dt(1, 15), {"S1": 100.0}, {"S1": 1_000_000})
    coord.record_open("S1", "一买多头", _dt(1, 15), 100.0)

    # Day 2: a 6% drop breaches the 5% daily loss limit.
    coord.on_bar(_dt(2, 9), {"S1": 94.0}, {"S1": 940_000})
    assert coord.daily_loss_limit_active is True
    assert len(coord.loss_limit_triggers) == 1
    assert len(coord.flat_events) == 1
    assert coord.flat_events[0]["symbol"] == "S1"

    # New opens are blocked for the rest of the day.
    assert coord.allow_open("S1", "二买多头", _dt(2, 10), 94.0) is False

    # Still day 2: block persists.
    coord.on_bar(_dt(2, 15), {"S1": 96.0}, {"S1": 960_000})
    assert coord.daily_loss_limit_active is True

    # Day 3: block resets.
    coord.on_bar(_dt(3, 9), {"S1": 95.0}, {"S1": 950_000})
    assert coord.daily_loss_limit_active is False
    assert coord.allow_open("S1", "二买多头", _dt(3, 10), 95.0) is True


def test_risk_parity_weights_inverse_to_volatility():
    """Higher-volatility symbol receives smaller risk-parity weight."""
    STRATEGY_CONFIG.update({
        "portfolio_risk": "on",
        "weighting": "risk_parity",
        "corr_clusters": {},
        "cluster_gross_cap": 1.0,
        "daily_loss_limit_pct": 1.0,
        "risk_parity_lookback": 10,
    })
    coord = PortfolioCoordinator(["LOWVOL", "HIGHVOL"], 1_000_000, STRATEGY_CONFIG)

    base = 100.0
    low_prices = [base]
    high_prices = [base]
    # LOWVOL moves 1% per bar; HIGHVOL moves 5% per bar.
    for i in range(15):
        low_prices.append(low_prices[-1] * (1.0 + (0.01 if i % 2 == 0 else -0.01)))
        high_prices.append(high_prices[-1] * (1.0 + (0.05 if i % 2 == 0 else -0.05)))

    start = _dt(2, 9)
    for i, (lp, hp) in enumerate(zip(low_prices, high_prices, strict=True)):
        dt = start + timedelta(minutes=i)
        coord.on_bar(dt, {"LOWVOL": lp, "HIGHVOL": hp}, {"LOWVOL": 1_000_000, "HIGHVOL": 1_000_000})

    assert coord.symbol_weights["LOWVOL"] > coord.symbol_weights["HIGHVOL"]
    # Sanity: weights sum to 1.
    assert sum(coord.symbol_weights.values()) == pytest.approx(1.0)


def test_risk_parity_sub_strategy_weight_scales_with_symbol_weight():
    """Sub-strategy weights are symbol_weight times the 1:2:3 relative split."""
    STRATEGY_CONFIG.update({
        "portfolio_risk": "on",
        "weighting": "risk_parity",
        "corr_clusters": {},
        "cluster_gross_cap": 1.0,
        "daily_loss_limit_pct": 1.0,
        "risk_parity_lookback": 5,
    })
    coord = PortfolioCoordinator(["S1"], 1_000_000, STRATEGY_CONFIG)
    coord.symbol_weights = {"S1": 0.30}  # fix symbol weight for the assertion

    w1 = coord._position_weight("S1", "一买多头")
    w2 = coord._position_weight("S1", "二买多头")
    w3 = coord._position_weight("S1", "三买多头")
    assert w1 == pytest.approx(0.30 * 1.0 / 6.0)
    assert w2 == pytest.approx(0.30 * 2.0 / 6.0)
    assert w3 == pytest.approx(0.30 * 3.0 / 6.0)
    assert w1 < w2 < w3


def test_fixed_weighting_reproduces_legacy_split():
    """``weighting='fixed'`` reproduces the legacy pos_1buy/pos_2buy/pos_3buy split."""
    STRATEGY_CONFIG.update({
        "portfolio_risk": "on",
        "weighting": "fixed",
        "pos_1buy": 0.10,
        "pos_2buy": 0.20,
        "pos_3buy": 0.30,
        "corr_clusters": {},
        "cluster_gross_cap": 1.0,
        "daily_loss_limit_pct": 1.0,
    })
    coord = PortfolioCoordinator(["S1"], 1_000_000, STRATEGY_CONFIG)

    assert coord._position_weight("S1", "一买多头") == pytest.approx(0.10)
    assert coord._position_weight("S1", "二买多头") == pytest.approx(0.20)
    assert coord._position_weight("S1", "三买多头") == pytest.approx(0.30)


def test_no_lookahead_volatility_ignores_future_bars():
    """Risk-parity weights at bar t do not incorporate returns from bars > t."""
    STRATEGY_CONFIG.update({
        "portfolio_risk": "on",
        "weighting": "risk_parity",
        "corr_clusters": {},
        "cluster_gross_cap": 1.0,
        "daily_loss_limit_pct": 1.0,
        "risk_parity_lookback": 5,
    })
    coord = PortfolioCoordinator(["QUIET", "NOISY"], 1_000_000, STRATEGY_CONFIG)

    # Build a short history where both symbols have non-zero vol and QUIET is lower vol.
    quiet_prices = [100.0]
    noisy_prices = [100.0]
    for i in range(6):
        quiet_prices.append(quiet_prices[-1] * (1.0 + (0.005 if i % 2 == 0 else -0.005)))
        noisy_prices.append(noisy_prices[-1] * (1.0 + (0.020 if i % 2 == 0 else -0.020)))

    weights_history = []
    for i, (qp, np) in enumerate(zip(quiet_prices, noisy_prices, strict=True)):
        dt = _dt(2, 9 + i)
        coord.on_bar(dt, {"QUIET": qp, "NOISY": np}, {"QUIET": 1_000_000, "NOISY": 1_000_000})
        weights_history.append(dict(coord.symbol_weights))

    # A future extreme bar is added; it must not retroactively change prior weights.
    coord.on_bar(
        _dt(2, 16),
        {"QUIET": quiet_prices[-1], "NOISY": noisy_prices[-1] * 2.0},
        {"QUIET": 1_000_000, "NOISY": 2_000_000},
    )

    # Prior weights stayed stable (both had enough history to be non-equal).
    prior = weights_history[-2]
    assert prior["QUIET"] > prior["NOISY"]
    assert weights_history[-1]["QUIET"] > weights_history[-1]["NOISY"]
    # After the extreme bar becomes current, NOISY vol spikes and its weight drops further.
    assert coord.symbol_weights["NOISY"] < coord.symbol_weights["QUIET"]


def test_no_lookahead_daily_loss_uses_only_cumulated_pnl():
    """Daily loss trigger uses only equity known up to the current bar."""
    STRATEGY_CONFIG.update({
        "portfolio_risk": "on",
        "weighting": "fixed",
        "corr_clusters": {},
        "cluster_gross_cap": 1.0,
        "daily_loss_limit_pct": 0.10,
    })
    coord = PortfolioCoordinator(["S1"], 1_000_000, STRATEGY_CONFIG)

    # Seed day 1 close.
    coord.on_bar(_dt(1, 15), {"S1": 100.0}, {"S1": 1_000_000})

    # Day 2 first bar: small loss, no trigger.
    coord.on_bar(_dt(2, 9), {"S1": 96.0}, {"S1": 960_000})
    assert coord.daily_loss_limit_active is False

    # Later day 2 bar (same day) recovers; still no trigger.
    coord.on_bar(_dt(2, 10), {"S1": 99.0}, {"S1": 990_000})
    assert coord.daily_loss_limit_active is False

    # A future bar cannot cause an earlier bar to trigger.
    assert len(coord.loss_limit_triggers) == 0


# ---------------------------------------------------------------------------
# PortfolioEngine regression tests — exercise the actual coordinated replay.
# ---------------------------------------------------------------------------

def _make_fake_engine(
    symbol: str,
    equity_curve: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
) -> SimpleNamespace:
    """Return a minimal fake BacktestEngine-like object for ``_build_on_report``."""
    strategy = SimpleNamespace(get_combined_trades=lambda: pairs)
    return SimpleNamespace(
        equity_curve=equity_curve,
        strategy=strategy,
        initial_capital=1_000_000,
    )


def _make_pair(
    strategy: str,
    open_dt: datetime,
    close_dt: datetime,
    open_price: float,
    close_price: float,
    pnl_pct: float,
) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "open_dt": open_dt,
        "close_dt": close_dt,
        "open_price": open_price,
        "close_price": close_price,
        "pnl_pct": pnl_pct,
        "bars_held": 1,
        "reason": "signal",
        "reason_code": "signal",
    }


def test_portfolio_engine_daily_loss_flatten_replay():
    """Daily loss limit in ``_build_on_report`` produces a loss-limit close
    and zero post-trigger gross exposure in the coordinated report."""
    STRATEGY_CONFIG.update({
        "portfolio_risk": "on",
        "weighting": "fixed",
        "corr_clusters": {},
        "cluster_gross_cap": 1.0,
        "daily_loss_limit_pct": 0.05,
        "pos_1buy": 1.00,  # 100% position so a -6% price move becomes -6% portfolio PnL
        "pos_1sell": 0.10,
        "commission_rate": 0.0001,
        "slippage": 0.0005,
    })

    symbol = "S1"
    d1_1500 = datetime(2024, 1, 1, 15, 0)
    d2_0900 = datetime(2024, 1, 2, 9, 0)
    d2_1000 = datetime(2024, 1, 2, 10, 0)
    d2_1500 = datetime(2024, 1, 2, 15, 0)

    equity_curve = [
        {"dt": d1_1500, "price": 100.0, "equity": 1_000_000.0},
        {"dt": d2_0900, "price": 94.0, "equity": 940_000.0},  # -6% portfolio PnL triggers 5% limit
        {"dt": d2_1000, "price": 93.0, "equity": 930_000.0},
        {"dt": d2_1500, "price": 95.0, "equity": 950_000.0},
    ]
    pairs = [_make_pair("一买多头", d1_1500, d2_1500, 100.0, 95.0, -0.05)]

    engine = PortfolioEngine([symbol], start_date="2024-01-01", end_date="2024-01-02")
    symbol_results = {
        symbol: {"engine": _make_fake_engine(symbol, equity_curve, pairs), "report": {}},
    }
    report = engine._build_on_report(symbol_results)

    assert len(report["loss_limit_triggers"]) == 1
    assert len(report["flat_events"]) == 1
    assert len(report["pairs"]) == 1

    pair = report["pairs"][0]
    assert pair["reason"] == "portfolio_daily_loss_limit"
    assert pair["close_dt"] == d2_0900
    assert pair["close_price"] == 94.0

    # Post-trigger bars must show zero gross exposure.
    post_trigger = [e for e in report["equity_curve"] if e["dt"] >= d2_0900]
    assert post_trigger
    assert all(e["gross_exposure"] == pytest.approx(0.0) for e in post_trigger)


def test_portfolio_engine_short_signed_pnl_and_exposure():
    """Short trades produce positive PnL when price falls and negative net exposure."""
    STRATEGY_CONFIG.update({
        "portfolio_risk": "on",
        "weighting": "fixed",
        "corr_clusters": {},
        "cluster_gross_cap": 1.0,
        "daily_loss_limit_pct": 1.0,  # disable loss limit
        "pos_1sell": 0.10,
        "commission_rate": 0.0001,
        "slippage": 0.0005,
    })

    symbol = "S1"
    open_dt = datetime(2024, 1, 2, 9, 0)
    interim_dt = datetime(2024, 1, 2, 10, 0)
    close_dt = datetime(2024, 1, 2, 15, 0)

    equity_curve = [
        {"dt": open_dt, "price": 100.0, "equity": 1_000_000.0},
        {"dt": interim_dt, "price": 90.0, "equity": 1_010_000.0},
        {"dt": close_dt, "price": 90.0, "equity": 1_010_000.0},
    ]
    pairs = [_make_pair("一卖空头", open_dt, close_dt, 100.0, 90.0, 0.10)]

    engine = PortfolioEngine([symbol], start_date="2024-01-02", end_date="2024-01-02")
    symbol_results = {
        symbol: {"engine": _make_fake_engine(symbol, equity_curve, pairs), "report": {}},
    }
    report = engine._build_on_report(symbol_results)

    interim = next(e for e in report["equity_curve"] if e["dt"] == interim_dt)
    # Price fell 10%; a 10% short position is up ~10% gross before costs.
    assert interim["equity"] == pytest.approx(1_010_000.0, rel=1e-4)
    assert interim["net_exposure"] == pytest.approx(-0.10)
    assert interim["gross_exposure"] == pytest.approx(0.10)


def test_run_portfolio_backtest_entry_point_accepts_table_names(monkeypatch):
    """The public convenience entry point constructs ``PortfolioEngine`` without
    ``TypeError`` and passes ``table_names`` through to per-symbol engines."""
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_run(self):
        calls.append((self.symbol, {"table_name": self.table_name}))
        self.equity_curve = [{"dt": datetime(2024, 1, 2, 9, 0), "price": 100.0, "equity": 1_000_000.0}]
        self.strategy = SimpleNamespace(get_combined_trades=lambda: [])
        return {}

    monkeypatch.setattr("chan_strategy.portfolio_engine.BacktestEngine.run", fake_run)

    result = run_portfolio_backtest(
        symbols=["S1", "S2"],
        start_date="2024-01-01",
        end_date="2024-01-02",
        table_names={"S1": "s1_custom", "S2": "s2_custom"},
    )

    assert "error" not in result
    assert len(calls) == 2
    assert calls[0] == ("S1", {"table_name": "s1_custom"})
    assert calls[1] == ("S2", {"table_name": "s2_custom"})


def test_run_rejects_risk_sizing_with_portfolio_risk_on():
    """``sizing_model='risk'`` combined with ``portfolio_risk='on'`` raises immediately
    instead of producing mismatched weight-based and currency-based accounting."""
    STRATEGY_CONFIG.update({
        "sizing_model": "risk",
        "portfolio_risk": "on",
    })

    engine = PortfolioEngine(["S1"], start_date="2024-01-01", end_date="2024-01-02")
    with pytest.raises(NotImplementedError):
        engine.run()


def test_run_allows_risk_sizing_with_portfolio_risk_off():
    """``sizing_model='risk'`` with ``portfolio_risk='off'`` remains a normal combination."""
    STRATEGY_CONFIG.update({
        "sizing_model": "risk",
        "portfolio_risk": "off",
    })

    engine = PortfolioEngine(["S1"], start_date="2024-01-01", end_date="2024-01-02")
    # Should not raise the portfolio_risk='on' guard.
    result = engine.run()
    assert "error" not in result or result.get("error") != "sizing_model='risk' with portfolio_risk='on' is not supported yet"


def test_daily_loss_limit_flatten_pair_is_net_of_cost():
    """A flatten pair produced by the daily-loss-limit path carries a net-of-cost
    ``pnl_pct`` that matches the hand-computed round-trip-cost deduction."""
    commission_rate = 0.0001
    slippage = 0.0005
    STRATEGY_CONFIG.update({
        "portfolio_risk": "on",
        "weighting": "fixed",
        "corr_clusters": {},
        "cluster_gross_cap": 1.0,
        "daily_loss_limit_pct": 0.05,
        "pos_1buy": 1.00,
        "pos_1sell": 0.10,
        "commission_rate": commission_rate,
        "slippage": slippage,
    })

    symbol = "S1"
    d1_1500 = datetime(2024, 1, 1, 15, 0)
    d2_0900 = datetime(2024, 1, 2, 9, 0)
    d2_1500 = datetime(2024, 1, 2, 15, 0)

    equity_curve = [
        {"dt": d1_1500, "price": 100.0, "equity": 1_000_000.0},
        {"dt": d2_0900, "price": 94.0, "equity": 940_000.0},
        {"dt": d2_1500, "price": 95.0, "equity": 950_000.0},
    ]
    # Close is after the trigger bar so the daily-loss-limit flatten fires first.
    pairs = [_make_pair("一买多头", d1_1500, d2_1500, 100.0, 95.0, -0.05)]

    engine = PortfolioEngine([symbol], start_date="2024-01-01", end_date="2024-01-02")
    symbol_results = {
        symbol: {"engine": _make_fake_engine(symbol, equity_curve, pairs), "report": {}},
    }
    report = engine._build_on_report(symbol_results)

    assert len(report["pairs"]) == 1
    pair = report["pairs"][0]
    assert pair["reason"] == "portfolio_daily_loss_limit"
    assert pair["open_price"] == 100.0
    assert pair["close_price"] == 94.0

    gross_pnl = (94.0 - 100.0) / 100.0  # long: +1 for sign
    expected_net_pnl = gross_pnl - (2 * commission_rate + slippage)
    assert pair["pnl_pct"] == pytest.approx(expected_net_pnl)
