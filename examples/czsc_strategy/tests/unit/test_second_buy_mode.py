"""A45 P6 — second_buy_mode hard-gate unit tests.

RESEARCH-ONLY, not a trading recommendation.
"""
from datetime import datetime

import pytest

from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.positions import (
    _research_second_buy_allowed,
    create_second_buy_position,
)


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


@pytest.fixture
def all_hold_signals():
    """Signal set that satisfies every gated condition."""
    return {
        "30分钟_D1BI_背驰V260615": "疑似_任意_任意_60",
        "30分钟_ATR_波动V260615": "扩张_任意_任意_100",
        "日线_D1BI_方向V260615": "向上_任意_任意_50",
        "日线_D1ZS_位置V260615": "中枢内_任意_任意_50",
    }


def test_baseline_allows_second_buy():
    STRATEGY_CONFIG["second_buy_mode"] = "baseline"
    assert _research_second_buy_allowed("TEST", {"price": 100}, 101, {}, "30分钟")


def test_off_blocks_new_second_buy():
    STRATEGY_CONFIG["second_buy_mode"] = "off"
    assert not _research_second_buy_allowed(
        "TEST", {"price": 100}, 101, {"30分钟_D1BI_背驰V260615": "疑似_任意_任意_60"}, "30分钟"
    )


def test_off_existing_position_still_exits():
    pos = create_second_buy_position("TEST", freq="30分钟", enable_daily_filter=False)
    dt = datetime(2024, 1, 1)
    open_signals = {
        "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
        "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
        "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
        "30分钟_D1BSP_二买V260615": "二买确认_任意_任意_80",
        "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
    }
    pos.update(open_signals, 100, dt, execution_price=100)
    assert pos.pos == 1

    # Now gate new opens; existing position must still exit normally.
    STRATEGY_CONFIG["second_buy_mode"] = "off"
    exit_signals = {
        "30分钟_D1BSP_风控V260615": "结构失效_任意_任意_0",
        "30分钟_D1BI_方向V260615": "向下_任意_任意_50",
        "30分钟_D1ZS_位置V260615": "中枢下方_任意_任意_0",
    }
    pos.update(exit_signals, 99, dt, execution_price=99)
    assert pos.pos == 0


def test_gated_requires_divergence(all_hold_signals):
    STRATEGY_CONFIG["second_buy_mode"] = "gated"
    STRATEGY_CONFIG["resonance_filter"] = "off"
    signals = dict(all_hold_signals)
    signals["30分钟_D1BI_背驰V260615"] = "无_任意_任意_0"
    assert not _research_second_buy_allowed("TEST", {"price": 100}, 101, signals, "30分钟")


def test_gated_requires_resonance(all_hold_signals):
    STRATEGY_CONFIG["second_buy_mode"] = "gated"
    STRATEGY_CONFIG["resonance_filter"] = "daily"
    signals = dict(all_hold_signals)
    signals["日线_D1BI_方向V260615"] = "向下_任意_任意_50"
    assert not _research_second_buy_allowed("TEST", {"price": 100}, 101, signals, "30分钟")


def test_gated_requires_atr_expansion(all_hold_signals):
    STRATEGY_CONFIG["second_buy_mode"] = "gated"
    STRATEGY_CONFIG["resonance_filter"] = "off"
    signals = dict(all_hold_signals)
    signals["30分钟_ATR_波动V260615"] = "压缩_任意_任意_0"
    assert not _research_second_buy_allowed("TEST", {"price": 100}, 101, signals, "30分钟")


def test_gated_opens_when_all_conditions_hold(all_hold_signals):
    STRATEGY_CONFIG["second_buy_mode"] = "gated"
    STRATEGY_CONFIG["resonance_filter"] = "off"
    assert _research_second_buy_allowed("TEST", {"price": 100}, 101, all_hold_signals, "30分钟")


def test_gated_with_daily_4h_resonance(all_hold_signals):
    STRATEGY_CONFIG["second_buy_mode"] = "gated"
    STRATEGY_CONFIG["resonance_filter"] = "daily_4h"
    signals = dict(all_hold_signals)
    signals["240分钟_D1BI_方向V260615"] = "向上_任意_任意_50"
    signals["240分钟_D1ZS_位置V260615"] = "中枢上方_任意_任意_50"
    assert _research_second_buy_allowed("TEST", {"price": 100}, 101, signals, "30分钟")
