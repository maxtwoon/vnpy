"""A46 P7 — Regime-router unit tests.

Verifies that ``regime_model="router"`` suppresses counter-trend new opens,
guarantees ``both_long_short_bars == 0``, and still allows existing positions
to exit normally.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from chan_strategy import backtest_engine as backtest_module
from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.positions import create_first_sell_position


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


def _make_mock_signals(
    daily_direction: str = "向上",
    daily_position: str = "中枢内",
    short_open_call: int | None = None,
    long_open_call: int | None = None,
    exit_call: int | None = None,
):
    """Deterministic get_all_signals replacement for router tests."""
    counters = {"trade": 0, "daily": 0}

    def _mock(czsc, freq, buy1_anchor=None, sell1_anchor=None):
        if freq == "日线":
            counters["daily"] += 1
            return {
                "日线_D1BI_方向V260615": f"{daily_direction}_任意_任意_50",
                "日线_D1ZS_位置V260615": f"{daily_position}_任意_任意_50",
            }

        if freq != "30分钟":
            return {}

        counters["trade"] += 1
        call = counters["trade"]

        if call == exit_call:
            return {
                "日线_D1BI_方向V260615": f"{daily_direction}_任意_任意_50",
                "日线_D1ZS_位置V260615": f"{daily_position}_任意_任意_50",
                "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
                "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
                "30分钟_D1BSP_一买V260615": "非一买_任意_任意_0",
                "30分钟_D1BSP_一卖V260615": "非一卖_任意_任意_0",
                "30分钟_D1BSP_二买V260615": "非二买_任意_任意_0",
                "30分钟_D1BSP_二卖V260615": "非二卖_任意_任意_0",
                "30分钟_D1BSP_三买阶段V260615": "非三买_任意_任意_0",
                "30分钟_D1BSP_三卖阶段V260615": "非三卖_任意_任意_0",
                "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
                "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
                "30分钟_D1BI_背驰V260615": "无_任意_任意_0",
                "30分钟_D1BSP_风控V260615": "结构失效_任意_任意_0",
                "30分钟_D1BSP_空头风控V260615": "结构失效_任意_任意_0",
            }

        if call == long_open_call:
            return {
                "日线_D1BI_方向V260615": f"{daily_direction}_任意_任意_50",
                "日线_D1ZS_位置V260615": f"{daily_position}_任意_任意_50",
                "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
                "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
                "30分钟_D1BSP_一买V260615": "一买确认_任意_任意_80",
                "30分钟_D1BSP_一卖V260615": "非一卖_任意_任意_0",
                "30分钟_D1BSP_二买V260615": "非二买_任意_任意_0",
                "30分钟_D1BSP_二卖V260615": "非二卖_任意_任意_0",
                "30分钟_D1BSP_三买阶段V260615": "非三买_任意_任意_0",
                "30分钟_D1BSP_三卖阶段V260615": "非三卖_任意_任意_0",
                "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
                "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
                "30分钟_D1BI_背驰V260615": "疑似_任意_任意_60",
                "30分钟_D1BSP_风控V260615": "结构完好_任意_任意_0",
                "30分钟_D1BSP_空头风控V260615": "结构完好_任意_任意_0",
            }

        if call == short_open_call:
            return {
                "日线_D1BI_方向V260615": f"{daily_direction}_任意_任意_50",
                "日线_D1ZS_位置V260615": f"{daily_position}_任意_任意_50",
                "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
                "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
                "30分钟_D1BSP_一买V260615": "非一买_任意_任意_0",
                "30分钟_D1BSP_一卖V260615": "一卖确认_任意_任意_80",
                "30分钟_D1BSP_二买V260615": "非二买_任意_任意_0",
                "30分钟_D1BSP_二卖V260615": "非二卖_任意_任意_0",
                "30分钟_D1BSP_三买阶段V260615": "非三买_任意_任意_0",
                "30分钟_D1BSP_三卖阶段V260615": "非三卖_任意_任意_0",
                "30分钟_D1BI_方向V260615": "向下_任意_任意_50",
                "30分钟_D1ZS_位置V260615": "中枢下方_任意_任意_50",
                "30分钟_D1BI_背驰V260615": "疑似_任意_任意_60",
                "30分钟_D1BSP_风控V260615": "结构完好_任意_任意_0",
                "30分钟_D1BSP_空头风控V260615": "结构完好_任意_任意_0",
            }

        # Background: no trade signal.
        return {
            "日线_D1BI_方向V260615": f"{daily_direction}_任意_任意_50",
            "日线_D1ZS_位置V260615": f"{daily_position}_任意_任意_50",
            "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
            "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
            "30分钟_D1BSP_一买V260615": "非一买_任意_任意_0",
            "30分钟_D1BSP_一卖V260615": "非一卖_任意_任意_0",
            "30分钟_D1BSP_二买V260615": "非二买_任意_任意_0",
            "30分钟_D1BSP_二卖V260615": "非二卖_任意_任意_0",
            "30分钟_D1BSP_三买阶段V260615": "非三买_任意_任意_0",
            "30分钟_D1BSP_三卖阶段V260615": "非三卖_任意_任意_0",
            "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
            "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
            "30分钟_D1BI_背驰V260615": "无_任意_任意_0",
            "30分钟_D1BSP_风控V260615": "结构完好_任意_任意_0",
            "30分钟_D1BSP_空头风控V260615": "结构完好_任意_任意_0",
        }

    return _mock


def _run_router_backtest(monkeypatch, synthetic_1m_bars, daily_direction: str, daily_position: str):
    STRATEGY_CONFIG["enable_short"] = True
    STRATEGY_CONFIG["regime_model"] = "router"
    # Widen stops so the synthetic bar volatility does not immediately close trades.
    for key in ("stop_loss_1buy", "stop_loss_2buy", "stop_loss_3buy",
                "stop_loss_1sell", "stop_loss_2sell", "stop_loss_3sell"):
        STRATEGY_CONFIG[key] = 10000
    bars = synthetic_1m_bars(days=20, per_day=240, start=datetime(2024, 1, 2, 9, 0))
    engine = BacktestEngine(symbol="TEST_R", db_path="none")
    engine.load_data = lambda: setattr(engine, "bars", bars) or True
    monkeypatch.setattr(
        backtest_module,
        "get_all_signals",
        _make_mock_signals(
            daily_direction=daily_direction,
            daily_position=daily_position,
            long_open_call=8,
            short_open_call=12,
            exit_call=16,
        ),
    )
    report = engine.run(warmup_bars=100)
    return report, engine


def test_router_daily_down_blocks_long_opens(synthetic_1m_bars, monkeypatch):
    """When daily regime is down, long opens are suppressed."""
    report, engine = _run_router_backtest(monkeypatch, synthetic_1m_bars, "向下", "中枢下方")
    assert "error" not in report
    pairs = engine.strategy.get_combined_trades()
    long_pairs = [p for p in pairs if "多头" in (p.get("strategy") or "")]
    assert len(long_pairs) == 0, "long opens should be blocked in daily-down regime"


def test_router_daily_up_blocks_short_opens(synthetic_1m_bars, monkeypatch):
    """When daily regime is up, short opens are suppressed."""
    report, engine = _run_router_backtest(monkeypatch, synthetic_1m_bars, "向上", "中枢上方")
    assert "error" not in report
    pairs = engine.strategy.get_combined_trades()
    short_pairs = [p for p in pairs if "空头" in (p.get("strategy") or "")]
    assert len(short_pairs) == 0, "short opens should be blocked in daily-up regime"


def test_router_ambiguous_blocks_all_new_opens(synthetic_1m_bars, monkeypatch):
    """When daily regime is ambiguous, no new opens on either side."""
    report, engine = _run_router_backtest(monkeypatch, synthetic_1m_bars, "向上", "中枢下方")
    assert "error" not in report
    pairs = engine.strategy.get_combined_trades()
    assert len(pairs) == 0, "new opens should be blocked in ambiguous regime"


def test_router_guarantees_zero_simultaneous_long_short_bars(synthetic_1m_bars, monkeypatch):
    """Router mode must never have both long and short exposure at the same bar."""
    report, _ = _run_router_backtest(monkeypatch, synthetic_1m_bars, "向下", "中枢下方")
    assert "error" not in report
    assert report.get("both_long_short_bars", -1) == 0


def test_router_opens_allowed_does_not_block_exits():
    """opens_allowed=False suppresses new opens but still lets exits fire."""
    pos = create_first_sell_position("TEST_R", "30分钟")
    pos.opens_allowed = False
    # Manually open a short position.
    pos._open_short(100.0, datetime(2024, 1, 2, 9, 0))
    assert pos.pos == -1

    exit_signals = {
        "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
        "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
        "30分钟_D1BSP_一卖V260615": "非一卖_任意_任意_0",
        "30分钟_D1BSP_二卖V260615": "非二卖_任意_任意_0",
        "30分钟_D1BSP_三卖阶段V260615": "非三卖_任意_任意_0",
        "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
        "30分钟_D1ZS_位置V260615": "中枢上方_任意_任意_50",
        "30分钟_D1BI_背驰V260615": "无_任意_任意_0",
        "30分钟_D1BSP_风控V260615": "结构完好_任意_任意_0",
        "30分钟_D1BSP_空头风控V260615": "结构失效_任意_任意_0",
    }
    pos.update(exit_signals, 110.0, datetime(2024, 1, 2, 10, 0))
    assert pos.pos == 0, "existing short position should have exited despite opens_allowed=False"
    assert len(pos.pairs) == 1
