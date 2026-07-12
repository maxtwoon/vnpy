"""A46 P7 — Symmetric P4/P5 short-open gating tests.

Verifies that short opens require both the P4 MACD/top divergence signal and
P5 short-side resonance, mirroring the long-side gating shipped in A43/A44.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from chan_strategy import backtest_engine as backtest_module
from chan_strategy import sell_signals as sell_signals_module
from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


def _base_short_signals(
    divergence: str = "疑似",
    daily_direction: str = "向下",
    daily_position: str = "中枢下方",
) -> dict:
    return {
        "日线_D1BI_方向V260615": f"{daily_direction}_任意_任意_50",
        "日线_D1ZS_位置V260615": f"{daily_position}_任意_任意_50",
        "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
        "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
        "30分钟_D1BSP_一卖V260615": "一卖确认_任意_任意_80",
        "30分钟_D1BSP_二卖V260615": "非二卖_任意_任意_0",
        "30分钟_D1BSP_三卖阶段V260615": "非三卖_任意_任意_0",
        "30分钟_D1BI_方向V260615": "向下_任意_任意_50",
        "30分钟_D1ZS_位置V260615": "中枢下方_任意_任意_50",
        "30分钟_D1BI_背驰V260615": f"{divergence}_任意_任意_60",
        "30分钟_D1BSP_风控V260615": "结构完好_任意_任意_0",
        "30分钟_D1BSP_空头风控V260615": "结构完好_任意_任意_0",
    }


def _make_mock_signals(missing: str | None = None):
    """Deterministic short-open signals with one required condition optionally missing."""
    counters = {"trade": 0}

    def _mock(czsc, freq, buy1_anchor=None, sell1_anchor=None):
        if freq != "30分钟":
            return {}

        counters["trade"] += 1
        call = counters["trade"]

        divergence = "疑似"
        daily_direction = "向下"
        daily_position = "中枢下方"
        if missing == "divergence":
            divergence = "无"
        if missing == "daily_direction":
            daily_direction = "向上"
        if missing == "daily_position":
            daily_position = "中枢上方"

        if call == 8:
            return _base_short_signals(
                divergence=divergence,
                daily_direction=daily_direction,
                daily_position=daily_position,
            )

        if call == 16:
            return {
                "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
                "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
                "30分钟_D1BSP_一卖V260615": "非一卖_任意_任意_0",
                "30分钟_D1BSP_二卖V260615": "非二卖_任意_任意_0",
                "30分钟_D1BSP_三卖阶段V260615": "非三卖_任意_任意_0",
                "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
                "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
                "30分钟_D1BI_背驰V260615": "无_任意_任意_0",
                "30分钟_D1BSP_风控V260615": "结构失效_任意_任意_0",
                "30分钟_D1BSP_空头风控V260615": "结构失效_任意_任意_0",
            }

        return {
            "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
            "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
            "30分钟_D1BSP_一卖V260615": "非一卖_任意_任意_0",
            "30分钟_D1BSP_二卖V260615": "非二卖_任意_任意_0",
            "30分钟_D1BSP_三卖阶段V260615": "非三卖_任意_任意_0",
            "30分钟_D1BI_方向V260615": "向下_任意_任意_50",
            "30分钟_D1ZS_位置V260615": "中枢下方_任意_任意_50",
            "30分钟_D1BI_背驰V260615": "无_任意_任意_0",
            "30分钟_D1BSP_风控V260615": "结构完好_任意_任意_0",
            "30分钟_D1BSP_空头风控V260615": "结构完好_任意_任意_0",
        }

    return _mock


def _run_gating_test(monkeypatch, synthetic_1m_bars, missing: str | None = None):
    STRATEGY_CONFIG["enable_short"] = True
    STRATEGY_CONFIG["regime_model"] = "independent"
    # Widen stops so the synthetic bar volatility does not immediately close the trade.
    for key in ("stop_loss_1sell", "stop_loss_2sell", "stop_loss_3sell"):
        STRATEGY_CONFIG[key] = 10000
    bars = synthetic_1m_bars(days=20, per_day=240, start=datetime(2024, 1, 2, 9, 0))
    engine = BacktestEngine(symbol="TEST_G", db_path="none")
    engine.load_data = lambda: setattr(engine, "bars", bars) or True
    mock = _make_mock_signals(missing=missing)
    monkeypatch.setattr(backtest_module, "get_all_signals", mock)
    monkeypatch.setattr(sell_signals_module, "get_all_signals", mock)
    report = engine.run(warmup_bars=100)
    return report, engine


def test_short_opens_with_p4_p5(synthetic_1m_bars, monkeypatch):
    """Short opens when P4 divergence and P5 resonance are both present."""
    report, engine = _run_gating_test(monkeypatch, synthetic_1m_bars, missing=None)
    assert "error" not in report
    short_pairs = [p for p in engine.strategy.get_combined_trades() if "空头" in (p.get("strategy") or "")]
    assert len(short_pairs) > 0, "short should open when P4 and P5 are satisfied"


def test_short_opens_blocked_without_divergence(synthetic_1m_bars, monkeypatch):
    """Short opens are blocked when P4 divergence is missing."""
    report, engine = _run_gating_test(monkeypatch, synthetic_1m_bars, missing="divergence")
    assert "error" not in report
    short_pairs = [p for p in engine.strategy.get_combined_trades() if "空头" in (p.get("strategy") or "")]
    assert len(short_pairs) == 0, "short should be blocked without P4 divergence"


def test_short_opens_blocked_without_daily_down(synthetic_1m_bars, monkeypatch):
    """Short opens are blocked when daily direction is not down."""
    report, engine = _run_gating_test(monkeypatch, synthetic_1m_bars, missing="daily_direction")
    assert "error" not in report
    short_pairs = [p for p in engine.strategy.get_combined_trades() if "空头" in (p.get("strategy") or "")]
    assert len(short_pairs) == 0, "short should be blocked without daily down direction"


def test_short_opens_blocked_when_daily_above_center(synthetic_1m_bars, monkeypatch):
    """Short opens are blocked when daily position is above center."""
    report, engine = _run_gating_test(monkeypatch, synthetic_1m_bars, missing="daily_position")
    assert "error" not in report
    short_pairs = [p for p in engine.strategy.get_combined_trades() if "空头" in (p.get("strategy") or "")]
    assert len(short_pairs) == 0, "short should be blocked when daily is above center"
