from datetime import datetime, timedelta

from czsc.objects import Direction, RawBar

from chan_strategy.sell_signals import get_all_signals, signal_third_buy, signal_third_sell


def _mirror_bars(bars):
    """价格镜像必须取负并互换 high/low，否则中枢上下沿和笔方向不会正确翻转。"""
    mirrored = []
    for bar in bars:
        mirrored.append(RawBar(
            symbol=bar.symbol,
            id=bar.id,
            dt=bar.dt,
            freq=bar.freq,
            open=-bar.open,
            close=-bar.close,
            high=-bar.low,
            low=-bar.high,
            vol=bar.vol,
            amount=bar.amount,
        ))
    return mirrored


def _mirror_bis(bis, bi_factory):
    mirrored = []
    for bi in bis:
        direction = Direction.Down if bi.direction == Direction.Up else Direction.Up
        mirrored_bi = bi_factory(direction, -bi.high, -bi.low, bi.sdt, bi.edt)
        mirrored_bi.raw_bars = _mirror_bars(bi.raw_bars)
        mirrored.append(mirrored_bi)
    return mirrored


def _structures(base, bi_factory):
    return [
        [],
        [bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1))],
        [
            bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1)),
            bi_factory(Direction.Down, 94, 115, base, base + timedelta(minutes=2)),
        ],
        [
            bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1)),
            bi_factory(Direction.Down, 94, 115, base, base + timedelta(minutes=2)),
            bi_factory(Direction.Up, 96, 112, base, base + timedelta(minutes=3)),
        ],
        [
            bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1)),
            bi_factory(Direction.Down, 94, 115, base, base + timedelta(minutes=2)),
            bi_factory(Direction.Up, 96, 112, base, base + timedelta(minutes=3)),
            bi_factory(Direction.Down, 80, 93, base, base + timedelta(minutes=4)),
            bi_factory(Direction.Up, 85, 100, base, base + timedelta(minutes=5)),
        ],
        [
            bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1)),
            bi_factory(Direction.Down, 94, 115, base, base + timedelta(minutes=2)),
            bi_factory(Direction.Up, 96, 112, base, base + timedelta(minutes=3)),
            bi_factory(Direction.Up, 250, 300, base, base + timedelta(minutes=4)),
            bi_factory(Direction.Down, 200, 280, base, base + timedelta(minutes=5)),
            bi_factory(Direction.Up, 112, 112, base, base + timedelta(minutes=6)),
        ],
    ]


def test_complete_classification_signals_are_exhaustive_and_mutually_exclusive(czsc_factory, bi_factory):
    allowed = {
        "30分钟_D1BI_方向V260615": {"向上", "向下", "无有效笔"},
        "30分钟_D1ZS_位置V260615": {"中枢上方", "中枢下方", "中枢内", "无中枢"},
        "30分钟_D1ZS_数据状态V260615": {"充分", "不足"},
        "30分钟_D1BI_背驰V260615": {"无", "疑似", "确认", "失效"},
        "30分钟_D1ZS_结构状态V260615": {"已确认", "未确认", "无中枢"},
        "30分钟_D1BSP_一买V260615": {"非一买", "一买候选", "一买确认"},
        "30分钟_D1BSP_二买V260615": {"非二买", "二买候选", "二买确认"},
        "30分钟_D1BSP_三买阶段V260615": {"非三买", "离开中枢", "回抽不入中枢", "三买确认"},
        "30分钟_D1BSP_一卖V260615": {"非一卖", "一卖候选", "一卖确认"},
        "30分钟_D1BSP_二卖V260615": {"非二卖", "二卖候选", "二卖确认"},
        "30分钟_D1BSP_三卖阶段V260615": {"非三卖", "离开中枢", "反抽不入中枢", "三卖确认"},
        "30分钟_D1BSP_风控V260615": {"结构完好", "结构失效", "震荡超限"},
        "30分钟_D1BSP_空头风控V260615": {"结构完好", "结构失效", "震荡超限"},
    }
    base = datetime(2024, 1, 1, 9, 0)
    anchor = {"dt": base + timedelta(minutes=4), "price": 80, "zs_zg": 112}
    sell_anchor = {"dt": base + timedelta(minutes=4), "price": 300, "zs_zd": 112}

    for bis in _structures(base, bi_factory):
        signals = get_all_signals(
            czsc_factory(bis), "30分钟",
            buy1_anchor=anchor,
            sell1_anchor=sell_anchor,
        )
        assert set(signals) == set(allowed)
        for key, value in signals.items():
            parts = value.split("_")
            assert len(parts) == 4
            assert parts[0] in allowed[key]
            assert parts[1] == "任意"
            assert parts[2] == "任意"
            assert parts[3].isdigit()


def test_mirrored_price_series_maps_buy_points_to_sell_points(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1, 9, 0)
    first_bis = [
        bi_factory(Direction.Up, 90, 130, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 95, 125, base + timedelta(minutes=1), base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 100, 120, base + timedelta(minutes=2), base + timedelta(minutes=3)),
        bi_factory(Direction.Down, 70, 99, base + timedelta(minutes=3), base + timedelta(minutes=4)),
        bi_factory(Direction.Up, 80, 119, base + timedelta(minutes=4), base + timedelta(minutes=5)),
    ]
    second_bis = [
        bi_factory(Direction.Up, 90, 130, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 95, 125, base + timedelta(minutes=1), base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 100, 120, base + timedelta(minutes=2), base + timedelta(minutes=3)),
        bi_factory(Direction.Down, 70, 99, base + timedelta(minutes=3), base + timedelta(minutes=4)),
        bi_factory(Direction.Up, 80, 105, base + timedelta(minutes=4), base + timedelta(minutes=5)),
        bi_factory(Direction.Down, 75, 95, base + timedelta(minutes=5), base + timedelta(minutes=6)),
        bi_factory(Direction.Up, 85, 110, base + timedelta(minutes=6), base + timedelta(minutes=7)),
    ]
    third_bis = [
        bi_factory(Direction.Up, 90, 130, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 95, 125, base + timedelta(minutes=1), base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 100, 120, base + timedelta(minutes=2), base + timedelta(minutes=3)),
        bi_factory(Direction.Up, 121, 150, base + timedelta(minutes=3), base + timedelta(minutes=4)),
        bi_factory(Direction.Down, 121, 140, base + timedelta(minutes=4), base + timedelta(minutes=5)),
        bi_factory(Direction.Up, 141, 155, base + timedelta(minutes=5), base + timedelta(minutes=6)),
    ]

    cases = [
        (first_bis, None, "30分钟_D1BSP_一买V260615", "30分钟_D1BSP_一卖V260615", {"一买确认": "一卖确认", "一买候选": "一卖候选", "非一买": "非一卖"}),
        (second_bis, {"dt_idx": 3, "price": 70, "zs_zg": 120, "zs_zd": 100}, "30分钟_D1BSP_二买V260615", "30分钟_D1BSP_二卖V260615", {"二买确认": "二卖确认", "二买候选": "二卖候选", "非二买": "非二卖"}),
        (third_bis, None, "30分钟_D1BSP_三买阶段V260615", "30分钟_D1BSP_三卖阶段V260615", {"三买确认": "三卖确认", "回抽不入中枢": "反抽不入中枢", "离开中枢": "离开中枢", "非三买": "非三卖"}),
    ]
    for bis, anchor_spec, buy_key, sell_key, value_map in cases:
        mirrored = _mirror_bis(bis, bi_factory)
        if "三买阶段" in buy_key:
            buy_v1 = next(iter(signal_third_buy(czsc_factory(bis), "30分钟").values())).split("_")[0]
            sell_v1 = next(iter(signal_third_sell(czsc_factory(mirrored), "30分钟").values())).split("_")[0]
            assert sell_v1 == value_map[buy_v1]
            continue
        buy_anchor = None
        sell_anchor = None
        if anchor_spec:
            idx = anchor_spec["dt_idx"]
            buy_anchor = {"dt": bis[idx].edt, "price": anchor_spec["price"], "zs_zg": anchor_spec["zs_zg"], "zs_zd": anchor_spec["zs_zd"]}
            sell_anchor = {"dt": mirrored[idx].edt, "price": mirrored[idx].high, "zs_zg": -anchor_spec["zs_zd"], "zs_zd": -anchor_spec["zs_zg"]}
        buy_signals = get_all_signals(czsc_factory(bis), "30分钟", buy1_anchor=buy_anchor)
        sell_signals = get_all_signals(czsc_factory(mirrored), "30分钟", sell1_anchor=sell_anchor)
        buy_v1 = buy_signals[buy_key].split("_")[0]
        sell_v1 = sell_signals[sell_key].split("_")[0]
        assert sell_v1 == value_map[buy_v1]
