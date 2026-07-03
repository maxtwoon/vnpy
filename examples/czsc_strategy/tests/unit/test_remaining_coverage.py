from datetime import datetime, timedelta

import pytest
from czsc.objects import Direction

import chan_strategy.signals as base_signals
from chan_strategy.positions import ChanTimingStrategy, _daily_trend_filter_signals
from chan_strategy.sell_signals import (
    signal_first_sell,
    signal_second_buy,
    signal_second_sell,
    signal_short_risk_control,
    signal_third_sell,
)


def _zbase(base, bi_factory):
    return [
        bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1), close=100),
        bi_factory(Direction.Down, 94, 115, base, base + timedelta(minutes=2), close=100),
        bi_factory(Direction.Up, 96, 112, base, base + timedelta(minutes=3), close=100),
    ]


def _bi(bi_factory, direction, low, high, base, start_minute, close=None):
    return bi_factory(
        direction,
        low,
        high,
        base + timedelta(minutes=start_minute),
        base + timedelta(minutes=start_minute + 1),
        close=close,
    )


def _v(signal):
    return next(iter(signal.values())).split("_")[0]


def test_daily_filter_rejects_unknown_direction():
    with pytest.raises(ValueError):
        _daily_trend_filter_signals(direction="sideways")


def test_strategy_sell_anchor_recording_and_short_update_paths(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = _zbase(base, bi_factory) + [
        bi_factory(Direction.Up, 130, 150, base, base + timedelta(minutes=4), close=150),
        bi_factory(Direction.Down, 120, 145, base, base + timedelta(minutes=5), close=120),
    ]
    c = czsc_factory(bis)
    sig = {"30分钟_D1BSP_一卖V260615": "一卖确认_任意_任意_80"}
    st = ChanTimingStrategy("TEST", enable_daily_filter=False, enable_short=True)

    st._record_sell1_anchor(sig, 140, base + timedelta(minutes=6), czsc_obj=c)
    assert st._last_sell1_anchor["price"] == 150
    st._record_sell1_anchor(sig, 140, base + timedelta(minutes=6), czsc_obj=c)
    assert len(st.sell1_history) == 1
    st._record_sell1_anchor(sig, 141, base + timedelta(minutes=9), czsc_obj=None)
    assert st._last_sell1_anchor["price"] == 141
    only_down = czsc_factory([_bi(bi_factory, Direction.Down, 80, 100, base, 10)])
    st._record_sell1_anchor(sig, 142, base + timedelta(minutes=10), czsc_obj=only_down)
    assert st._last_sell1_anchor["price"] == 142

    st.update(sig, 140, base + timedelta(minutes=7), czsc_obj=c)
    assert st._last_sell1_anchor["zs_zg"] is not None
    st.update({}, 140, base + timedelta(minutes=7), czsc_obj=c)

    fallback = ChanTimingStrategy("TEST", enable_daily_filter=False, enable_short=True)
    fallback._last_sell1_anchor = {"dt": base, "price": 50, "zs_zd": None, "zs_zg": None}
    fallback.update({}, 100, base + timedelta(minutes=8), czsc_obj=c)
    assert fallback._last_sell1_anchor["zs_zg"] is not None
    empty_zs = ChanTimingStrategy("TEST", enable_daily_filter=False, enable_short=True)
    empty_zs._last_sell1_anchor = {"dt": base, "price": 150, "zs_zd": None, "zs_zg": None}
    empty_zs.update({}, 100, base + timedelta(minutes=8), czsc_obj=czsc_factory([]))
    assert empty_zs._last_sell1_anchor["zs_zg"] is None

    no_anchor = ChanTimingStrategy("TEST", enable_daily_filter=False, enable_short=True)
    no_anchor.update({}, 100, base, czsc_obj=c)
    assert len(no_anchor.positions) == 6


def test_base_second_buy_edge_branches(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = _zbase(base, bi_factory) + [
        _bi(bi_factory, Direction.Down, 80, 90, base, 4),
        _bi(bi_factory, Direction.Up, 85, 110, base, 5),
        _bi(bi_factory, Direction.Down, 79, 95, base, 6),
    ]
    assert _v(base_signals.signal_second_buy(czsc_factory(bis), buy1_anchor=None)) == "非二买"
    anchor = {"dt": bis[3].edt, "price": 80, "zs_zg": 112}
    assert _v(base_signals.signal_second_buy(czsc_factory(bis), buy1_anchor=anchor)) == "非二买"

    candidate = bis[:-1] + [_bi(bi_factory, Direction.Down, 81, 95, base, 6)]
    assert _v(base_signals.signal_second_buy(czsc_factory(candidate), buy1_anchor=anchor)) == "二买候选"

    confirm_bad = candidate + [_bi(bi_factory, Direction.Up, 80, 120, base, 7)]
    assert _v(base_signals.signal_second_buy(czsc_factory(confirm_bad), buy1_anchor=anchor)) == "非二买"

    confirm_ok = candidate + [_bi(bi_factory, Direction.Up, 82, 120, base, 7)]
    assert _v(base_signals.signal_second_buy(czsc_factory(confirm_ok), buy1_anchor=anchor)) == "二买确认"


def test_base_third_buy_edge_branches(czsc_factory, bi_factory, monkeypatch):
    base = datetime(2024, 1, 1)
    seed = _zbase(base, bi_factory)
    monkeypatch.setattr(
        base_signals,
        "build_zhongshu_from_bis",
        lambda bis, **kwargs: [{"zd": 96, "zg": 112, "start_idx": 0, "end_idx": 2, "n_bis": 3}],
    )
    assert _v(base_signals.signal_third_buy(czsc_factory(seed))) == "非三买"

    leave = seed + [
        _bi(bi_factory, Direction.Up, 130, 150, base, 4),
        _bi(bi_factory, Direction.Up, 131, 151, base, 5),
    ]
    assert _v(base_signals.signal_third_buy(czsc_factory(leave))) == "离开中枢"

    failed = leave[:4] + [_bi(bi_factory, Direction.Down, 90, 140, base, 5)]
    assert _v(base_signals.signal_third_buy(czsc_factory(failed))) == "非三买"

    retrace = leave[:4] + [_bi(bi_factory, Direction.Down, 121, 140, base, 5)]
    assert _v(base_signals.signal_third_buy(czsc_factory(retrace))) == "回抽不入中枢"

    confirm = retrace + [_bi(bi_factory, Direction.Up, 130, 160, base, 6)]
    assert _v(base_signals.signal_third_buy(czsc_factory(confirm))) == "三买确认"

    later_break = retrace + [
        _bi(bi_factory, Direction.Up, 130, 160, base, 6),
        _bi(bi_factory, Direction.Down, 90, 120, base, 7),
    ]
    assert _v(base_signals.signal_third_buy(czsc_factory(later_break))) in {"非三买", "三买确认"}

    monkeypatch.setattr(
        base_signals,
        "build_zhongshu_from_bis",
        lambda bis, **kwargs: [{"zd": 96, "zg": 112, "start_idx": 0, "end_idx": len(bis) - 1, "n_bis": 3}],
    )
    assert _v(base_signals.signal_third_buy(czsc_factory(confirm))) == "非三买"

    monkeypatch.setattr(
        base_signals,
        "build_zhongshu_from_bis",
        lambda bis, **kwargs: [{"zd": 96, "zg": 112, "start_idx": 0, "end_idx": 2, "n_bis": 3}],
    )
    no_leave = seed + [
        _bi(bi_factory, Direction.Down, 100, 111, base, 4),
        _bi(bi_factory, Direction.Down, 99, 110, base, 5),
    ]
    assert _v(base_signals.signal_third_buy(czsc_factory(no_leave))) == "非三买"


def test_base_get_all_signals(czsc_factory, bi_factory):
    sigs = base_signals.get_all_signals(czsc_factory(_zbase(datetime(2024, 1, 1), bi_factory)))
    assert "30分钟_D1BSP_三买阶段V260615" in sigs


def test_sell_signal_edge_branches(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    seed = _zbase(base, bi_factory)

    assert _v(signal_second_buy(czsc_factory(seed), buy1_anchor={"price": 80, "zs_zg": 112})) == "非二买"
    compact_anchor = {"dt": base + timedelta(minutes=10), "price": 80, "zs_zg": 112}
    compact_wrong_rebound = [
        _bi(bi_factory, Direction.Up, 90, 120, base, 0),
        _bi(bi_factory, Direction.Down, 80, 100, base, 1),
        _bi(bi_factory, Direction.Down, 90, 101, base, 2),
        _bi(bi_factory, Direction.Down, 91, 102, base, 3),
        _bi(bi_factory, Direction.Up, 83, 120, base, 4),
    ]
    assert _v(signal_second_buy(czsc_factory(compact_wrong_rebound), buy1_anchor=compact_anchor)) == "非二买"
    compact_bad_confirm = [
        _bi(bi_factory, Direction.Up, 90, 120, base, 0),
        _bi(bi_factory, Direction.Down, 80, 100, base, 1),
        _bi(bi_factory, Direction.Up, 85, 110, base, 2),
        _bi(bi_factory, Direction.Down, 81, 95, base, 3),
        _bi(bi_factory, Direction.Up, 80, 120, base, 4),
    ]
    timely_buy_anchor = {"dt": base + timedelta(minutes=2), "price": 80, "zs_zg": 112}
    assert _v(signal_second_buy(czsc_factory(compact_bad_confirm), buy1_anchor=timely_buy_anchor)) == "非二买"
    compact_stale = compact_bad_confirm[:-1] + [_bi(bi_factory, Direction.Down, 82, 96, base, 4)]
    assert _v(signal_second_buy(czsc_factory(compact_stale), buy1_anchor=timely_buy_anchor)) == "非二买"
    buy_anchor = {"dt": base + timedelta(minutes=4), "price": 80, "zs_zg": 112}
    wrong_rebound = seed + [
        _bi(bi_factory, Direction.Down, 80, 90, base, 4),
        _bi(bi_factory, Direction.Down, 81, 91, base, 5),
        _bi(bi_factory, Direction.Up, 82, 120, base, 6),
    ]
    assert _v(signal_second_buy(czsc_factory(wrong_rebound), buy1_anchor=buy_anchor)) == "非二买"
    bad_confirm = seed + [
        _bi(bi_factory, Direction.Down, 80, 90, base, 4),
        _bi(bi_factory, Direction.Up, 85, 110, base, 5),
        _bi(bi_factory, Direction.Down, 81, 95, base, 6),
        _bi(bi_factory, Direction.Up, 80, 120, base, 7),
    ]
    assert _v(signal_second_buy(czsc_factory(bad_confirm), buy1_anchor=buy_anchor)) == "非二买"
    stale_buy = bad_confirm + [_bi(bi_factory, Direction.Down, 82, 96, base, 8)]
    assert _v(signal_second_buy(czsc_factory(stale_buy), buy1_anchor=buy_anchor)) == "非二买"

    first_candidate = seed + [_bi(bi_factory, Direction.Up, 130, 150, base, 4)]
    assert _v(signal_first_sell(czsc_factory(first_candidate))) in {"一卖候选", "非一卖"}
    first_confirm = first_candidate + [_bi(bi_factory, Direction.Down, 120, 145, base, 5)]
    assert _v(signal_first_sell(czsc_factory(first_confirm))) in {"一卖确认", "一卖候选", "非一卖"}
    strong_leave = seed + [
        _bi(bi_factory, Direction.Up, 130, 300, base, 4),
        _bi(bi_factory, Direction.Up, 131, 301, base, 5),
    ]
    assert _v(signal_first_sell(czsc_factory(strong_leave))) == "非一卖"
    weak_no_confirm = seed + [
        _bi(bi_factory, Direction.Up, 121, 130, base, 4),
        _bi(bi_factory, Direction.Up, 122, 131, base, 5),
    ]
    assert _v(signal_first_sell(czsc_factory(weak_no_confirm))) == "一卖候选"

    sell_anchor = {"dt": first_candidate[-1].edt, "price": 150, "zs_zd": 96}
    second_candidate = first_candidate + [
        _bi(bi_factory, Direction.Down, 100, 130, base, 5),
        _bi(bi_factory, Direction.Up, 120, 149, base, 6),
    ]
    assert _v(signal_second_sell(czsc_factory(second_candidate), sell1_anchor=sell_anchor)) == "二卖候选"
    second_confirm = second_candidate + [_bi(bi_factory, Direction.Down, 90, 140, base, 7)]
    assert _v(signal_second_sell(czsc_factory(second_confirm), sell1_anchor=sell_anchor)) == "二卖确认"
    too_short_anchor = {"dt": seed[-1].edt, "price": seed[-1].high, "zs_zd": 96}
    assert _v(signal_second_sell(czsc_factory(seed + [_bi(bi_factory, Direction.Down, 80, 90, base, 4)]), sell1_anchor=too_short_anchor)) == "非二卖"
    late_anchor = {"dt": first_candidate[-1].edt, "price": first_candidate[-1].high, "zs_zd": 96}
    assert _v(signal_second_sell(czsc_factory(first_candidate + [_bi(bi_factory, Direction.Down, 80, 90, base, 5)]), sell1_anchor=late_anchor)) == "非二卖"
    wrong_decline = first_candidate + [
        _bi(bi_factory, Direction.Up, 130, 149, base, 5),
        _bi(bi_factory, Direction.Down, 90, 120, base, 6),
    ]
    assert _v(signal_second_sell(czsc_factory(wrong_decline), sell1_anchor=sell_anchor)) == "非二卖"
    bad_second_confirm = second_candidate + [_bi(bi_factory, Direction.Down, 90, 151, base, 7)]
    assert _v(signal_second_sell(czsc_factory(bad_second_confirm), sell1_anchor=sell_anchor)) == "非二卖"
    stale_second = second_candidate + [
        _bi(bi_factory, Direction.Up, 121, 148, base, 7),
    ]
    assert _v(signal_second_sell(czsc_factory(stale_second), sell1_anchor=sell_anchor)) == "非二卖"
    bad_rebound = first_candidate + [
        _bi(bi_factory, Direction.Down, 100, 130, base, 5),
        _bi(bi_factory, Direction.Up, 120, 151, base, 6),
    ]
    assert _v(signal_second_sell(czsc_factory(bad_rebound), sell1_anchor=sell_anchor)) == "非二卖"

    third_leave = seed + [
        _bi(bi_factory, Direction.Down, 70, 90, base, 4),
        _bi(bi_factory, Direction.Down, 69, 89, base, 5),
    ]
    assert _v(signal_third_sell(czsc_factory(third_leave))) == "离开中枢"
    third_fail = third_leave[:4] + [_bi(bi_factory, Direction.Up, 80, 100, base, 5)]
    assert _v(signal_third_sell(czsc_factory(third_fail))) == "非三卖"
    third_rebound = third_leave[:4] + [_bi(bi_factory, Direction.Up, 70, 90, base, 5)]
    assert _v(signal_third_sell(czsc_factory(third_rebound))) == "反抽不入中枢"
    third_confirm = third_rebound + [_bi(bi_factory, Direction.Down, 60, 80, base, 6)]
    assert _v(signal_third_sell(czsc_factory(third_confirm))) == "三卖确认"
    third_later_fail = third_rebound + [
        _bi(bi_factory, Direction.Down, 60, 80, base, 6),
        _bi(bi_factory, Direction.Up, 100, 130, base, 7),
    ]
    assert _v(signal_third_sell(czsc_factory(third_later_fail))) in {"非三卖", "三卖确认"}
    third_invalid_after_rebound = third_rebound + [_bi(bi_factory, Direction.Up, 100, 130, base, 6)]
    assert _v(signal_third_sell(czsc_factory(third_invalid_after_rebound))) == "非三卖"


def test_short_risk_control_edge_branches(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    seed = _zbase(base, bi_factory)
    assert _v(signal_short_risk_control(czsc_factory([]))) == "结构完好"

    up_break = seed + [bi_factory(Direction.Up, 130, 150, base, base + timedelta(minutes=4), close=150)]
    assert _v(signal_short_risk_control(czsc_factory(up_break), stop_loss_pct=0.01)) == "结构失效"

    many = seed + [
        bi_factory(Direction.Up if i % 2 else Direction.Down, 97, 105, base, base + timedelta(minutes=4 + i))
        for i in range(8)
    ]
    assert _v(signal_short_risk_control(czsc_factory(many), stop_loss_pct=0.5)) == "震荡超限"

    no_raw_up = _bi(bi_factory, Direction.Up, 130, 150, base, 4)
    no_raw_up.raw_bars = []
    assert _v(signal_short_risk_control(czsc_factory(seed + [no_raw_up]), stop_loss_pct=0.01)) == "结构失效"
    no_raw_down = _bi(bi_factory, Direction.Down, 90, 100, base, 4)
    no_raw_down.raw_bars = []
    assert _v(signal_short_risk_control(czsc_factory(seed + [no_raw_down]), stop_loss_pct=0.5)) == "结构完好"
