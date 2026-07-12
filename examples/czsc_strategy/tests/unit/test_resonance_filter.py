"""A44 P5 — Multi-level resonance entry filter tests."""
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.positions import (
    create_first_buy_position,
    create_first_sell_position,
    create_second_buy_position,
    create_second_sell_position,
    create_third_buy_position,
    create_third_sell_position,
)


BASE = {
    "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_0",
    "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_0",
    "30分钟_D1BSP_一买V260615": "一买确认_任意_任意_80",
    "30分钟_D1BSP_二买V260615": "二买确认_任意_任意_75",
    "30分钟_D1BSP_三买阶段V260615": "三买确认_任意_任意_90",
    "30分钟_D1BSP_一卖V260615": "一卖确认_任意_任意_80",
    "30分钟_D1BSP_二卖V260615": "二卖确认_任意_任意_75",
    "30分钟_D1BSP_三卖阶段V260615": "三卖确认_任意_任意_90",
    "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
    "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
    "30分钟_D1BI_背驰V260615": "疑似_任意_任意_60",
}


def _with_daily(signals: dict, direction: str, position: str) -> dict:
    return signals | {
        "日线_D1BI_方向V260615": f"{direction}_任意_任意_50",
        "日线_D1ZS_位置V260615": f"{position}_任意_任意_50",
    }


def _with_4h(signals: dict, direction: str, position: str) -> dict:
    return signals | {
        "240分钟_D1BI_方向V260615": f"{direction}_任意_任意_50",
        "240分钟_D1ZS_位置V260615": f"{position}_任意_任意_50",
    }


def test_off_mode_matches_legacy_daily_filter():
    """resonance_filter='off' must reproduce the legacy daily filter exactly."""
    original = dict(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG["resonance_filter"] = "off"
        first = create_first_buy_position("T")
        second = create_second_buy_position("T")
        third = create_third_buy_position("T")

        daily_down = _with_daily(BASE, "向下", "中枢内")
        daily_up = _with_daily(BASE, "向上", "中枢内")
        daily_below = _with_daily(BASE, "向上", "中枢下方")

        # 一买：legacy strict=False (only excludes below)
        assert first.opens[0].is_match(BASE | daily_down)
        assert not first.opens[0].is_match(BASE | daily_below)

        # 二买/三买：legacy strict=True (requires up direction)
        assert not second.opens[0].is_match(BASE | daily_down)
        assert second.opens[0].is_match(BASE | daily_up)
        assert third.opens[0].is_match(BASE | daily_up)
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def test_daily_blocks_long_when_not_constructive():
    """'daily' requires daily up + position in {above, inside}; blocks below/down."""
    original = dict(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG["resonance_filter"] = "daily"
        first = create_first_buy_position("T")
        second = create_second_buy_position("T")
        third = create_third_buy_position("T")

        daily_up_inside = _with_daily(BASE, "向上", "中枢内")
        daily_up_above = _with_daily(BASE, "向上", "中枢上方")
        daily_down = _with_daily(BASE, "向下", "中枢内")
        daily_below = _with_daily(BASE, "向上", "中枢下方")
        daily_none = _with_daily(BASE, "向上", "无中枢")

        for pos in (first, second, third):
            assert pos.opens[0].is_match(BASE | daily_up_inside)
            assert pos.opens[0].is_match(BASE | daily_up_above)
            assert not pos.opens[0].is_match(BASE | daily_down)
            assert not pos.opens[0].is_match(BASE | daily_below)
            assert not pos.opens[0].is_match(BASE | daily_none)
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def test_daily_blocks_short_when_not_constructive():
    """'daily' short requires daily down + position in {below, inside}."""
    original = dict(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG["resonance_filter"] = "daily"
        first = create_first_sell_position("T")
        second = create_second_sell_position("T")
        third = create_third_sell_position("T")

        short_base = BASE | {"30分钟_D1BI_方向V260615": "向下_任意_任意_50"}
        daily_down_inside = _with_daily(short_base, "向下", "中枢内")
        daily_down_below = _with_daily(short_base, "向下", "中枢下方")
        daily_up = _with_daily(short_base, "向上", "中枢内")
        daily_above = _with_daily(short_base, "向下", "中枢上方")
        daily_none = _with_daily(short_base, "向下", "无中枢")

        for pos in (first, second, third):
            assert pos.opens[0].is_match(short_base | daily_down_inside)
            assert pos.opens[0].is_match(short_base | daily_down_below)
            assert not pos.opens[0].is_match(short_base | daily_up)
            assert not pos.opens[0].is_match(short_base | daily_above)
            assert not pos.opens[0].is_match(short_base | daily_none)
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def test_daily_4h_blocks_when_4h_non_constructive():
    """'daily_4h' additionally requires constructive 4H structure."""
    original = dict(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG["resonance_filter"] = "daily_4h"
        STRATEGY_CONFIG["resonance_freq_4h"] = "240分钟"
        second = create_second_buy_position("T")

        daily_ok = _with_daily(BASE, "向上", "中枢内")
        h4_ok = _with_4h(BASE, "向上", "中枢内")
        h4_down = _with_4h(BASE, "向下", "中枢内")
        h4_below = _with_4h(BASE, "向上", "中枢下方")
        h4_none = _with_4h(BASE, "向上", "无中枢")

        assert second.opens[0].is_match(BASE | daily_ok | h4_ok)
        assert not second.opens[0].is_match(BASE | daily_ok | h4_down)
        assert not second.opens[0].is_match(BASE | daily_ok | h4_below)
        assert not second.opens[0].is_match(BASE | daily_ok | h4_none)
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def test_disabled_daily_filter_still_disables_resonance():
    """When enable_daily_filter=False, resonance conditions must not be applied."""
    original = dict(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG["resonance_filter"] = "daily"
        pos = create_second_buy_position("T", enable_daily_filter=False)
        # With daily filter disabled, no higher-level signals should be required.
        assert pos.opens[0].is_match(BASE)
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def test_resonance_does_not_change_exit_events():
    """Resonance filter must gate entries only; exits remain unchanged."""
    original = dict(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG["resonance_filter"] = "daily_4h"
        pos = create_first_buy_position("T")
        assert not any("240分钟" in s.value for s in pos.exits[0].signals_all)
        assert not any("240分钟" in s.value for s in pos.exits[0].signals_not)
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)
