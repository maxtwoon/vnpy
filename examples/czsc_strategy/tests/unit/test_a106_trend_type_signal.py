from datetime import datetime, timedelta

from czsc import Direction

from chan_strategy.sell_signals import get_all_signals
from chan_strategy.signals import signal_trend_type


FREQ = "30分钟"
KEY = f"{FREQ}_D1ZS_走势类型V260729"


def _bis_from_ranges(bi_factory, ranges: list[tuple[float, float]]):
    base = datetime(2024, 1, 1, 9, 0)
    out = []
    for i, (low, high) in enumerate(ranges):
        direction = Direction.Up if i % 2 == 0 else Direction.Down
        out.append(
            bi_factory(
                direction,
                low,
                high,
                base + timedelta(minutes=i),
                base + timedelta(minutes=i + 1),
            )
        )
    return out


def _v1(czsc_factory, bis: list) -> str:
    return signal_trend_type(czsc_factory(bis), freq=FREQ)[KEY].split("_")[0]


def test_trend_type_is_exhaustive_and_mutually_exclusive_on_synthetic_fixtures(czsc_factory, bi_factory):
    cases = {
        "无中枢": [],
        "盘整": [(8, 14), (9, 13), (10, 12), (18, 24), (30, 36)],
        "上涨趋势": [(8, 14), (9, 13), (10, 12), (18, 24), (19, 23), (20, 22)],
        "下跌趋势": [(18, 24), (19, 23), (20, 22), (8, 14), (9, 13), (10, 12)],
        "中枢延伸": [(8, 16), (9, 15), (10, 14), (11, 17), (12, 18), (13, 19)],
    }

    seen = set()
    for expected, ranges in cases.items():
        value = _v1(czsc_factory, _bis_from_ranges(bi_factory, ranges))
        assert value == expected
        seen.add(value)

    assert seen == {"无中枢", "盘整", "上涨趋势", "下跌趋势", "中枢延伸"}


def test_raised_but_overlapped_centers_are_extension_not_uptrend(czsc_factory, bi_factory):
    bis = _bis_from_ranges(
        bi_factory,
        [(8, 16), (9, 15), (10, 14), (11, 17), (12, 18), (13, 19)],
    )

    assert _v1(czsc_factory, bis) == "中枢延伸"


def test_trend_type_uses_confirmed_bi_prefix_only(czsc_factory, bi_factory):
    confirmed = _bis_from_ranges(
        bi_factory,
        [(8, 14), (9, 13), (10, 12), (18, 24), (19, 23), (20, 22)],
    )
    extending_tail = _bis_from_ranges(bi_factory, [(1, 50)])

    stable_value = signal_trend_type(czsc_factory(confirmed), freq=FREQ)
    with_unconfirmed_tail = signal_trend_type(
        czsc_factory(confirmed + extending_tail, last_bi_extend=True),
        freq=FREQ,
    )

    assert with_unconfirmed_tail == stable_value


def test_trend_type_is_not_consumed_by_default_signal_aggregation(czsc_factory, bi_factory):
    bis = _bis_from_ranges(
        bi_factory,
        [(8, 14), (9, 13), (10, 12), (18, 24), (19, 23), (20, 22)],
    )

    assert KEY not in get_all_signals(czsc_factory(bis), freq=FREQ)
