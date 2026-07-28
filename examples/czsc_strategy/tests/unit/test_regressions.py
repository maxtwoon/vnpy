from datetime import datetime, timedelta

from czsc import CZSC
from czsc import Direction

from chan_strategy.positions import ChanTimingStrategy, create_first_buy_position, create_second_buy_position
from chan_strategy.signals import _get_confirmed_bi_list, signal_first_buy
from chan_strategy.sell_signals import signal_second_buy, signal_third_buy


def test_czsc_confirmed_bi_contract_is_still_available():
    assert hasattr(CZSC, "finished_bis")
    assert hasattr(CZSC, "last_bi_extend")


def test_get_confirmed_bi_list_drops_extending_tail(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = [
        bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 80, 110, base, base + timedelta(minutes=2)),
    ]
    assert _get_confirmed_bi_list(czsc_factory(bis, last_bi_extend=True)) == bis[:1]


def test_daily_filter_disabled_creates_positions_without_daily_keys():
    p1 = create_first_buy_position("TEST", enable_daily_filter=False)
    p2 = create_second_buy_position("TEST", enable_daily_filter=False)
    joined = " ".join(s.value for p in [p1, p2] for e in p.opens for s in e.signals_all + e.signals_any + e.signals_not)
    assert "日线_" not in joined


def test_second_buy_without_anchor_never_confirms(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = [
        bi_factory(Direction.Down, 80, 100, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=2)),
        bi_factory(Direction.Down, 85, 110, base, base + timedelta(minutes=3)),
        bi_factory(Direction.Up, 95, 130, base, base + timedelta(minutes=4)),
        bi_factory(Direction.Down, 96, 115, base, base + timedelta(minutes=5)),
    ]
    assert "二买确认" not in next(iter(signal_second_buy(czsc_factory(bis), buy1_anchor=None).values()))


def test_second_buy_open_event_does_not_require_divergence():
    pos = create_second_buy_position("TEST", enable_daily_filter=False)
    not_signals = " ".join(signal.key for event in pos.opens for signal in event.signals_not)
    assert "D1BI_背驰V260615" not in not_signals


def test_buy1_anchor_uses_confirmed_down_bi_low(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    strategy = ChanTimingStrategy("TEST", enable_daily_filter=False)
    signals = {
        "30分钟_D1BSP_一买V260615": "一买确认_任意_任意_80",
    }
    czsc = czsc_factory(
        [
            bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1)),
            bi_factory(Direction.Down, 70, 110, base, base + timedelta(minutes=2)),
        ]
    )
    strategy._record_buy1_anchor(signals, price=999, dt=base + timedelta(minutes=3), czsc_obj=czsc)
    assert strategy.get_last_buy1_anchor()["price"] == 70


def test_first_buy_uses_latest_center_with_following_leave_bi(czsc_factory, bi_factory):
    """recent 重叠中枢尾部可能无后续笔，一买应回退到有离开段的中枢。"""
    base = datetime(2024, 1, 1)
    bis = [
        bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 95, 115, base, base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 96, 112, base, base + timedelta(minutes=3)),
        bi_factory(Direction.Down, 70, 96, base, base + timedelta(minutes=4)),
        bi_factory(Direction.Up, 88, 103, base, base + timedelta(minutes=5)),
        bi_factory(Direction.Down, 90, 100, base, base + timedelta(minutes=6)),
    ]
    value = next(iter(signal_first_buy(czsc_factory(bis)).values()))
    assert value.split("_")[0] in {"一买候选", "一买确认"}


def test_third_buy_confirm_bi_is_not_reclassified_as_new_leave(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = [
        bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 94, 115, base, base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 96, 112, base, base + timedelta(minutes=3)),
        bi_factory(Direction.Up, 250, 300, base, base + timedelta(minutes=4)),
        bi_factory(Direction.Down, 200, 280, base, base + timedelta(minutes=5)),
        bi_factory(Direction.Up, 281, 310, base, base + timedelta(minutes=6)),
    ]

    value = next(iter(signal_third_buy(czsc_factory(bis)).values()))
    assert value.startswith("三买确认_")
