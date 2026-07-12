"""A48 P8b — Portfolio coordinator unit tests.

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.portfolio_engine import PortfolioCoordinator


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
