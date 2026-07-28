from datetime import datetime, timedelta

from czsc import Direction

from chan_strategy.positions import ChanTimingStrategy


def _base_signals():
    return {
        "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
        "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
        "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
        "30分钟_D1ZS_位置V260615": "中枢上方_任意_任意_60",
        "30分钟_D1BI_背驰V260615": "疑似_任意_任意_60",
        "30分钟_D1BSP_风控V260615": "结构完好_任意_任意_0",
    }


def _first_buy_signals():
    sig = _base_signals()
    sig["30分钟_D1BSP_一买V260615"] = "一买确认_任意_任意_80"
    sig["30分钟_D1BSP_二买V260615"] = "非二买_任意_任意_0"
    sig["30分钟_D1BSP_三买阶段V260615"] = "非三买_任意_任意_0"
    return sig


def _second_buy_signals():
    sig = _base_signals()
    sig["30分钟_D1BSP_一买V260615"] = "非一买_任意_任意_0"
    sig["30分钟_D1BSP_二买V260615"] = "二买确认_任意_任意_75"
    sig["30分钟_D1BSP_三买阶段V260615"] = "非三买_任意_任意_0"
    return sig


def _neutral_signals():
    sig = _base_signals()
    sig["30分钟_D1BSP_一买V260615"] = "非一买_任意_任意_0"
    sig["30分钟_D1BSP_二买V260615"] = "非二买_任意_任意_0"
    sig["30分钟_D1BSP_三买阶段V260615"] = "非三买_任意_任意_0"
    return sig


def _snapshot(strategy):
    return {
        "anchor": strategy.get_last_buy1_anchor().copy() if strategy.get_last_buy1_anchor() else None,
        "history_len": len(strategy.buy1_history),
        "positions": [(p.name, p.pos, p.cost, len(p.pairs)) for p in strategy.positions],
        "pairs": [
            (p.name, [(x["open_dt"], x["close_dt"], round(x["pnl_pct"], 8), x["reason"]) for x in p.pairs])
            for p in strategy.positions
        ],
    }


def _run_prefix(events, czsc_factory, bi_factory):
    strategy = ChanTimingStrategy("TEST", enable_daily_filter=False)
    base = datetime(2024, 1, 1, 9, 0)
    for offset, signals in events:
        dt = base + timedelta(minutes=offset)
        czsc = czsc_factory(
            [
                bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1)),
                bi_factory(Direction.Down, 80, 110, base, dt),
            ]
        )
        strategy.update(signals, price=100 + offset, dt=dt, execution_price=100 + offset, czsc_obj=czsc)
    return strategy


def test_strategy_state_replay_matches_incremental_prefixes(czsc_factory, bi_factory):
    events = [
        (0, _neutral_signals()),
        (1, _first_buy_signals()),
        (2, _neutral_signals()),
        (3, _second_buy_signals()),
        (4, _neutral_signals()),
    ]

    incremental = ChanTimingStrategy("TEST", enable_daily_filter=False)
    base = datetime(2024, 1, 1, 9, 0)
    for idx, (offset, signals) in enumerate(events, start=1):
        dt = base + timedelta(minutes=offset)
        czsc = czsc_factory(
            [
                bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1)),
                bi_factory(Direction.Down, 80, 110, base, dt),
            ]
        )
        incremental.update(signals, price=100 + offset, dt=dt, execution_price=100 + offset, czsc_obj=czsc)
        replayed = _run_prefix(events[:idx], czsc_factory, bi_factory)
        assert _snapshot(incremental) == _snapshot(replayed)

