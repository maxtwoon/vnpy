from datetime import datetime

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.positions import create_first_buy_position, create_second_buy_position, create_third_buy_position


BASE = {
    "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_0",
    "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_0",
    "30分钟_D1BSP_一买V260615": "一买确认_任意_任意_80",
    "30分钟_D1BSP_二买V260615": "二买确认_任意_任意_75",
    "30分钟_D1BSP_三买阶段V260615": "三买确认_任意_任意_90",
    "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
    "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
    "30分钟_D1BI_背驰V260615": "疑似_任意_任意_60",
}


def test_daily_filter_semantics():
    first = create_first_buy_position("T")
    second = create_second_buy_position("T")
    third = create_third_buy_position("T")
    daily_down = {
        "日线_D1BI_方向V260615": "向下_任意_任意_50",
        "日线_D1ZS_位置V260615": "中枢内_任意_任意_50",
    }
    daily_up = {
        "日线_D1BI_方向V260615": "向上_任意_任意_50",
        "日线_D1ZS_位置V260615": "中枢内_任意_任意_50",
    }
    daily_below = {
        "日线_D1BI_方向V260615": "向上_任意_任意_50",
        "日线_D1ZS_位置V260615": "中枢下方_任意_任意_30",
    }
    assert first.opens[0].is_match(BASE | daily_down)
    assert not second.opens[0].is_match(BASE | daily_down)
    assert second.opens[0].is_match(BASE | daily_up)
    assert third.opens[0].is_match(BASE | daily_up)
    assert not first.opens[0].is_match(BASE | daily_below)


def test_disable_daily_filter_does_not_crash():
    create_first_buy_position("T", enable_daily_filter=False)
    create_second_buy_position("T", enable_daily_filter=False)
    create_third_buy_position("T", enable_daily_filter=False)


def test_daily_filter_disabled_when_daily_warmup_missing(monkeypatch, mini_backtest_bars):
    engine = BacktestEngine("TEST", db_path="none")
    engine.load_data = lambda: setattr(engine, "bars", mini_backtest_bars[:420]) or True
    report = engine.run(warmup_bars=2)
    assert "error" not in report
    assert engine.strategy.enable_daily_filter is False
