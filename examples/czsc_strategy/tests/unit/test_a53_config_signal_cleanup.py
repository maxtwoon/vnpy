"""A53 — Config/signal single-source-of-truth cleanup unit tests.

Covers:
- Orphan first-buy config keys default to no-op and behave as named when enabled.
- structural_invalidation_pct is the single source for the 5%-past-center threshold.
- equity_mode="compound" raises NotImplementedError at a real call site.
- signals.py superseded 二买/三买 still exist (deprecation-marked, not deleted).
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from czsc.objects import Direction

from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.positions import _research_first_buy_allowed, Position
from chan_strategy.signals import (
    signal_risk_control,
    signal_risk_control_recent,
    signal_second_buy,
    signal_third_buy,
)
from chan_strategy.sell_signals import (
    signal_short_risk_control,
    signal_short_risk_control_recent,
)


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


def _v(signal_dict: dict) -> str:
    return next(iter(signal_dict.values())).split("_")[0]


def test_core_risk_config_keys_do_not_use_literal_get_fallbacks():
    """Core risk defaults must stay single-sourced and fail-fast in config.py."""
    project_root = Path(__file__).resolve().parents[2]
    files = [
        project_root / "chan_strategy" / "backtest_engine.py",
        project_root / "chan_strategy" / "data_adapter.py",
        project_root / "chan_strategy" / "limit_config.py",
        project_root / "chan_strategy" / "positions.py",
        project_root / "chan_strategy" / "portfolio_engine.py",
        project_root / "chan_strategy" / "portfolio_ledger.py",
        project_root / "chan_strategy" / "signals.py",
        project_root / "chan_strategy" / "validation.py",
    ]
    keys = {
        "sizing_model",
        "risk_per_trade_pct",
        "max_margin_pct",
        "limit_halt_model",
        "portfolio_risk",
        "weighting",
        "daily_loss_limit_pct",
        "max_symbol_margin_pct",
        "cluster_gross_cap",
        "daily_agg",
        "night_session_start_hour",
        "trade_freq",
        "filter_freq",
        "resonance_filter",
        "resonance_freq_4h",
        "rollover_open_gating",
        "rollover_stat_tagging",
        "exit_event_semantics",
        "stop_execution_model",
        "stop_penalty_bp",
        "pos_1buy",
        "pos_2buy",
        "pos_3buy",
        "pos_1sell",
        "pos_2sell",
        "pos_3sell",
        "second_buy_mode",
        "enable_short",
        "regime_model",
        "equity_mode",
        "divergence_model",
        "macd_fast",
        "macd_slow",
        "macd_signal",
        "atr_period",
        "atr_lookback",
        "atr_percentile_floor",
        "exit_model",
        "atr_trail_mult",
        "partial_tp_frac",
    }
    violations: list[str] = []

    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "get":
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "STRATEGY_CONFIG":
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            key = node.args[0].value
            if key in keys:
                violations.append(f"{path.relative_to(project_root)}:{node.lineno}:{key}")

    assert violations == []


# ---------------------------------------------------------------------------
# Orphan first-buy gates
# ---------------------------------------------------------------------------

def test_research_first_buy_allowed_defaults_are_no_op():
    """With default config the four orphan gates are transparent."""
    # Ensure defaults are present/missing in a way that keeps today"s behavior.
    STRATEGY_CONFIG.pop("enable_1buy_symbols", None)
    STRATEGY_CONFIG.pop("block_1buy_daily_down", None)
    STRATEGY_CONFIG.pop("block_1buy_daily_not_up", None)
    STRATEGY_CONFIG.pop("block_1buy_daily_below_zs", None)

    signals = {
        "日线_D1BI_方向V260615": "向下_任意_任意_50",
        "日线_D1ZS_位置V260615": "中枢下方_任意_任意_50",
    }
    assert _research_first_buy_allowed("RB888", signals) is True


def test_enable_1buy_symbols_limits_first_buy():
    STRATEGY_CONFIG["enable_1buy_symbols"] = ["AP888"]
    signals = {
        "日线_D1BI_方向V260615": "向上_任意_任意_50",
        "日线_D1ZS_位置V260615": "中枢内_任意_任意_50",
    }
    assert _research_first_buy_allowed("AP888", signals) is True
    assert _research_first_buy_allowed("RB888", signals) is False


def test_block_1buy_daily_down_blocks_on_down_direction():
    STRATEGY_CONFIG["block_1buy_daily_down"] = True
    up_signals = {"日线_D1BI_方向V260615": "向上_任意_任意_50"}
    down_signals = {"日线_D1BI_方向V260615": "向下_任意_任意_50"}
    assert _research_first_buy_allowed("RB888", up_signals) is True
    assert _research_first_buy_allowed("RB888", down_signals) is False


def test_block_1buy_daily_not_up_blocks_unless_up():
    STRATEGY_CONFIG["block_1buy_daily_not_up"] = True
    up_signals = {"日线_D1BI_方向V260615": "向上_任意_任意_50"}
    flat_signals = {"日线_D1BI_方向V260615": "无有效笔_任意_任意_50"}
    assert _research_first_buy_allowed("RB888", up_signals) is True
    assert _research_first_buy_allowed("RB888", flat_signals) is False


def test_block_1buy_daily_below_zs_blocks_below_center():
    STRATEGY_CONFIG["block_1buy_daily_below_zs"] = True
    inside_signals = {"日线_D1ZS_位置V260615": "中枢内_任意_任意_50"}
    below_signals = {"日线_D1ZS_位置V260615": "中枢下方_任意_任意_50"}
    assert _research_first_buy_allowed("RB888", inside_signals) is True
    assert _research_first_buy_allowed("RB888", below_signals) is False


# ---------------------------------------------------------------------------
# structural_invalidation_pct single source of truth
# ---------------------------------------------------------------------------

def test_structural_invalidation_pct_default_matches_legacy(czsc_factory, bi_factory):
    """Default config value of 0.05 keeps the legacy hard-coded threshold."""
    STRATEGY_CONFIG["structural_invalidation_pct"] = 0.05
    base = datetime(2024, 1, 1)
    # Build a structure whose last down BI closes well below the center zd,
    # triggering the default 5% structural-invalidation threshold.
    bis = [
        bi_factory(Direction.Up, 90, 110, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 92, 108, base + timedelta(minutes=1), base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 94, 106, base + timedelta(minutes=2), base + timedelta(minutes=3)),
        bi_factory(Direction.Down, 80, 100, base + timedelta(minutes=3), base + timedelta(minutes=4)),
    ]
    c = czsc_factory(bis)
    assert _v(signal_risk_control(c)) == "结构失效"
    assert _v(signal_risk_control_recent(c)) == "结构失效"
    assert _v(signal_short_risk_control(c)) == "结构完好"
    assert _v(signal_short_risk_control_recent(c)) == "结构完好"


def test_structural_invalidation_pct_change_affects_all_four_sites(czsc_factory, bi_factory):
    """Changing the config value changes the threshold in all four functions."""
    base = datetime(2024, 1, 1)
    bis = [
        bi_factory(Direction.Up, 90, 110, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 92, 108, base + timedelta(minutes=1), base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 94, 106, base + timedelta(minutes=2), base + timedelta(minutes=3)),
        # Last close=86 is ~8.5% below a zd of ~94: fails at 5% but not at 10%.
        bi_factory(Direction.Down, 86, 100, base + timedelta(minutes=3), base + timedelta(minutes=4)),
    ]
    c = czsc_factory(bis)

    # With a 5% threshold the ~8.5% break is a failure.
    STRATEGY_CONFIG["structural_invalidation_pct"] = 0.05
    assert _v(signal_risk_control(c)) == "结构失效"
    assert _v(signal_risk_control_recent(c)) == "结构失效"
    assert _v(signal_short_risk_control(c)) == "结构完好"
    assert _v(signal_short_risk_control_recent(c)) == "结构完好"

    # With a 10% threshold the same break is no longer a failure.
    STRATEGY_CONFIG["structural_invalidation_pct"] = 0.10
    assert _v(signal_risk_control(c)) == "结构完好"
    assert _v(signal_risk_control_recent(c)) == "结构完好"

    # Short side: price 110 vs zg=106 is a ~3.8% break.  With 1% threshold it
    # fails; with 5% default it does not.
    short_bis = [
        bi_factory(Direction.Down, 90, 110, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Up, 92, 108, base + timedelta(minutes=1), base + timedelta(minutes=2)),
        bi_factory(Direction.Down, 94, 106, base + timedelta(minutes=2), base + timedelta(minutes=3)),
        bi_factory(Direction.Up, 110, 112, base + timedelta(minutes=3), base + timedelta(minutes=4)),
    ]
    c_short = czsc_factory(short_bis)
    STRATEGY_CONFIG["structural_invalidation_pct"] = 0.01
    assert _v(signal_short_risk_control(c_short)) == "结构失效"
    assert _v(signal_short_risk_control_recent(c_short)) == "结构失效"
    STRATEGY_CONFIG["structural_invalidation_pct"] = 0.10
    assert _v(signal_short_risk_control(c_short)) == "结构完好"
    assert _v(signal_short_risk_control_recent(c_short)) == "结构完好"


def test_explicit_stop_loss_pct_still_overrides(czsc_factory, bi_factory):
    """Backward compatibility: explicit argument overrides config."""
    base = datetime(2024, 1, 1)
    bis = [
        bi_factory(Direction.Up, 90, 110, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 92, 108, base + timedelta(minutes=1), base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 94, 106, base + timedelta(minutes=2), base + timedelta(minutes=3)),
        bi_factory(Direction.Down, 80, 100, base + timedelta(minutes=3), base + timedelta(minutes=4)),
    ]
    c = czsc_factory(bis)
    STRATEGY_CONFIG["structural_invalidation_pct"] = 0.10
    # Explicit 1% overrides the 10% config.
    assert _v(signal_risk_control(c, stop_loss_pct=0.01)) == "结构失效"
    assert _v(signal_short_risk_control(c, stop_loss_pct=0.01)) == "结构完好"


# ---------------------------------------------------------------------------
# equity_mode resolution
# ---------------------------------------------------------------------------

def test_equity_mode_compound_raises_not_implemented():
    """ compound  is documented but not implemented; selecting it must fail fast."""
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["equity_mode"] = "compound"
    pos = Position("p", "RB888", [], stop_loss=200)
    with pytest.raises(NotImplementedError, match="compound"):
        pos._size_open(100, 1_000_000, 0.0)


def test_equity_mode_fixed_allows_sizing():
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["equity_mode"] = "fixed"
    pos = Position("p", "RB888", [], stop_loss=200)
    volume, multiplier = pos._size_open(100, 1_000_000, 0.0)
    assert volume >= 1


# ---------------------------------------------------------------------------
# Superseded signals remain importable (deprecation path)
# ---------------------------------------------------------------------------

def test_superseded_second_buy_and_third_buy_still_exist(czsc_factory, bi_factory):
    """signals.py versions are deprecated but still callable for import graph safety."""
    base = datetime(2024, 1, 1)
    bis = [
        bi_factory(Direction.Up, 90, 110, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 92, 108, base + timedelta(minutes=1), base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 94, 106, base + timedelta(minutes=2), base + timedelta(minutes=3)),
        bi_factory(Direction.Down, 80, 100, base + timedelta(minutes=3), base + timedelta(minutes=4)),
        bi_factory(Direction.Up, 88, 103, base + timedelta(minutes=4), base + timedelta(minutes=5)),
    ]
    c = czsc_factory(bis)
    assert "二买" in _v(signal_second_buy(c, buy1_anchor={"price": 80, "zs_zg": 106}))
    assert signal_third_buy(c)
