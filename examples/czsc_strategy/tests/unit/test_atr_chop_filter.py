"""A45 P6 — ATR chop filter unit tests.

RESEARCH-ONLY, not a trading recommendation.
"""
from datetime import datetime

import pytest

from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.positions import (
    _atr_filter_signals,
    create_first_buy_position,
    create_first_sell_position,
    create_second_buy_position,
    create_second_sell_position,
    create_third_buy_position,
    create_third_sell_position,
)
from chan_strategy.signals import AtrStateTracker


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


def _make_constant_bars(count: int, price: float = 100.0):
    """Choppy constant-price bars -> ATR collapses toward zero."""
    return [{"high": price + 0.1, "low": price - 0.1, "close": price} for _ in range(count)]


def _make_expanding_bars(count: int, start_price: float = 100.0):
    """Bars with widening range -> current ATR ends up high in the lookback."""
    bars = []
    price = start_price
    for i in range(count):
        width = 0.1 + i * 0.5
        high = price + width
        low = price - width
        close = price
        bars.append({"high": high, "low": low, "close": close})
    return bars


def test_tracker_defaults_to_expansion_with_insufficient_history():
    tracker = AtrStateTracker(period=14, lookback=100, floor=0.30)
    for i in range(10):
        state = tracker.update(100 + i, 100 - i, 100)
    assert state["state"] == "扩张"
    assert state["percentile"] is None


def test_tracker_detects_compression_and_expansion():
    tracker = AtrStateTracker(period=5, lookback=20, floor=0.30)
    # Establish a high-ATR history first.
    for _ in range(30):
        tracker.update(110.0, 90.0, 100.0)
    # Then switch to narrow-range bars; current ATR should sit low in the lookback.
    for _ in range(10):
        tracker.update(100.1, 99.9, 100.0)
    assert tracker.signal("30分钟")["30分钟_ATR_波动V260615"].startswith("压缩")

    # A few wide bars push current ATR back above the floor.
    for _ in range(5):
        tracker.update(120.0, 80.0, 100.0)
    assert tracker.signal("30分钟")["30分钟_ATR_波动V260615"].startswith("扩张")


def test_atr_filter_signals_off_by_default():
    assert _atr_filter_signals("30分钟") == {"signals_all": [], "signals_not": []}


def test_atr_filter_signals_on_returns_expansion_signal():
    STRATEGY_CONFIG["atr_chop_filter"] = "on"
    assert _atr_filter_signals("30分钟") == {
        "signals_all": ["30分钟_ATR_波动V260615_扩张_任意_任意_100"],
        "signals_not": [],
    }


@pytest.mark.parametrize("factory", [
    create_first_buy_position,
    create_second_buy_position,
    create_third_buy_position,
    create_first_sell_position,
    create_second_sell_position,
    create_third_sell_position,
])
def test_open_event_includes_atr_signal_when_filter_on(factory):
    STRATEGY_CONFIG["atr_chop_filter"] = "on"
    pos = factory("TEST", freq="30分钟", enable_daily_filter=False)
    signals_all = pos.opens[0].signals_all
    values = [s.value for s in signals_all]
    assert any("ATR_波动V260615_扩张" in v for v in values)


def test_open_blocked_when_atr_compressed():
    STRATEGY_CONFIG["atr_chop_filter"] = "on"
    pos = create_first_buy_position("TEST", freq="30分钟", enable_daily_filter=False)
    dt = datetime(2024, 1, 1)
    signals = {
        "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
        "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
        "30分钟_D1BSP_一买V260615": "一买确认_任意_任意_80",
        "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
        "30分钟_ATR_波动V260615": "压缩_任意_任意_0",
    }
    pos.update(signals, 100, dt, execution_price=100)
    assert pos.pos == 0


def test_open_allowed_when_atr_expanding():
    STRATEGY_CONFIG["atr_chop_filter"] = "on"
    pos = create_first_buy_position("TEST", freq="30分钟", enable_daily_filter=False)
    dt = datetime(2024, 1, 1)
    signals = {
        "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
        "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
        "30分钟_D1BSP_一买V260615": "一买确认_任意_任意_80",
        "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
        "30分钟_ATR_波动V260615": "扩张_任意_任意_100",
    }
    pos.update(signals, 100, dt, execution_price=100)
    assert pos.pos == 1


def test_exit_still_fires_in_chop():
    STRATEGY_CONFIG["atr_chop_filter"] = "on"
    pos = create_first_buy_position("TEST", freq="30分钟", enable_daily_filter=False)
    dt = datetime(2024, 1, 1)
    open_signals = {
        "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
        "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
        "30分钟_D1BSP_一买V260615": "一买确认_任意_任意_80",
        "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
        "30分钟_ATR_波动V260615": "扩张_任意_任意_100",
    }
    pos.update(open_signals, 100, dt, execution_price=100)
    assert pos.pos == 1

    # ATR filter gates opens only, never exits.
    exit_signals = {
        "30分钟_D1BSP_风控V260615": "结构失效_任意_任意_0",
        "30分钟_D1BI_方向V260615": "向下_任意_任意_50",
        "30分钟_D1ZS_位置V260615": "中枢下方_任意_任意_0",
        "30分钟_ATR_波动V260615": "压缩_任意_任意_0",
    }
    pos.update(exit_signals, 99, dt, execution_price=99)
    assert pos.pos == 0
