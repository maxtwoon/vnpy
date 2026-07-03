from datetime import datetime, timedelta

from czsc.objects import Direction

from chan_strategy.signals import (
    _get_confirmed_bi_list,
    build_zhongshu_from_bis,
    signal_first_buy,
)
from chan_strategy.sell_signals import (
    get_all_signals,
    signal_first_sell,
    signal_second_buy,
    signal_second_sell,
    signal_third_buy,
    signal_third_sell,
)


def make_struct(base, bi_factory):
    return [
        bi_factory(Direction.Up, 90, 110, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 92, 108, base + timedelta(minutes=1), base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 94, 106, base + timedelta(minutes=2), base + timedelta(minutes=3)),
        bi_factory(Direction.Down, 80, 100, base + timedelta(minutes=3), base + timedelta(minutes=4)),
        bi_factory(Direction.Up, 88, 103, base + timedelta(minutes=4), base + timedelta(minutes=5)),
    ]


def test_confirmed_bi_list_filters_last_extension(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = make_struct(base, bi_factory)
    assert _get_confirmed_bi_list(object()) == []
    assert _get_confirmed_bi_list(czsc_factory(bis, last_bi_extend=True)) == bis[:-1]
    assert _get_confirmed_bi_list(czsc_factory(bis)) == bis


def test_complete_classification_values(czsc_factory, bi_factory):
    cases = [
        czsc_factory([]),
        czsc_factory(make_struct(datetime(2024, 1, 1), bi_factory)[:2]),
        czsc_factory(make_struct(datetime(2024, 1, 1), bi_factory)),
    ]
    allowed = {
        "方向V260615": {"向上", "向下", "无有效笔"},
        "位置V260615": {"中枢上方", "中枢内", "中枢下方", "无中枢"},
        "数据状态V260615": {"充分", "不足"},
        "背驰V260615": {"无", "疑似", "确认", "失效"},
        "结构状态V260615": {"已确认", "未确认", "无中枢"},
    }
    for c in cases:
        signals = get_all_signals(c)
        for key, value in signals.items():
            suffix = key.split("_")[2]
            if suffix in allowed:
                assert value.split("_")[0] in allowed[suffix]


def test_first_second_third_buy_paths(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = make_struct(base, bi_factory) + [
        bi_factory(Direction.Down, 91, 96, base + timedelta(minutes=5), base + timedelta(minutes=6)),
        bi_factory(Direction.Up, 95, 111, base + timedelta(minutes=6), base + timedelta(minutes=7)),
    ]
    c = czsc_factory(bis)
    assert build_zhongshu_from_bis(bis)
    assert "一买" in next(iter(signal_first_buy(c).values()))
    assert "二买确认" not in next(iter(signal_second_buy(c, buy1_anchor=None).values()))
    anchor = {"dt": bis[3].edt, "price": 80, "zs_zg": 106, "zs_zd": 94}
    value = next(iter(signal_second_buy(c, buy1_anchor=anchor).values()))
    assert "二买" in value

    third_bis = bis[:3] + [
        bi_factory(Direction.Up, 100, 120, base + timedelta(minutes=3), base + timedelta(minutes=4)),
        bi_factory(Direction.Down, 107, 115, base + timedelta(minutes=4), base + timedelta(minutes=5)),
        bi_factory(Direction.Up, 110, 125, base + timedelta(minutes=5), base + timedelta(minutes=6)),
    ]
    tv = next(iter(signal_third_buy(czsc_factory(third_bis)).values()))
    assert tv.split("_")[0] in {"非三买", "离开中枢", "回抽不入中枢", "三买确认"}


def test_first_second_third_sell_paths(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    first_bis = [
        bi_factory(Direction.Up, 90, 130, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 95, 125, base + timedelta(minutes=1), base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 100, 120, base + timedelta(minutes=2), base + timedelta(minutes=3)),
        bi_factory(Direction.Up, 121, 150, base + timedelta(minutes=3), base + timedelta(minutes=4)),
        bi_factory(Direction.Down, 80, 119, base + timedelta(minutes=4), base + timedelta(minutes=5)),
    ]
    c = czsc_factory(first_bis)
    assert "一卖确认" in next(iter(signal_first_sell(c).values()))

    bis = first_bis[:-1] + [
        bi_factory(Direction.Down, 80, 119, base + timedelta(minutes=4), base + timedelta(minutes=5)),
        bi_factory(Direction.Up, 100, 145, base + timedelta(minutes=5), base + timedelta(minutes=6)),
        bi_factory(Direction.Down, 70, 110, base + timedelta(minutes=6), base + timedelta(minutes=7)),
    ]
    c = czsc_factory(bis)
    assert "二卖确认" not in next(iter(signal_second_sell(c, sell1_anchor=None).values()))
    anchor = {"dt": bis[3].edt, "price": 150, "zs_zg": 120, "zs_zd": 100}
    assert "二卖确认" in next(iter(signal_second_sell(c, sell1_anchor=anchor).values()))

    third_bis = bis[:3] + [
        bi_factory(Direction.Down, 80, 99, base + timedelta(minutes=3), base + timedelta(minutes=4)),
        bi_factory(Direction.Up, 85, 100, base + timedelta(minutes=4), base + timedelta(minutes=5)),
        bi_factory(Direction.Down, 70, 95, base + timedelta(minutes=5), base + timedelta(minutes=6)),
    ]
    tv = next(iter(signal_third_sell(czsc_factory(third_bis)).values()))
    assert tv.split("_")[0] == "三卖确认"
