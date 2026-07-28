"""Regression test for the second-buy anchor-time filter bug."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from czsc import Direction

from chan_strategy.signals import signal_second_buy
from chan_strategy.positions import ChanTimingStrategy


def _make_bi(direction, low, high, sdt, edt):
    """Create a minimal BI-like object for signal_second_buy.

    czsc 1.0.0rc8 exposes ``FakeBI`` as a Rust type that cannot be instantiated
    from Python, so tests use a local SimpleNamespace stand-in with the same
    attribute surface.
    """
    return SimpleNamespace(
        symbol="TEST",
        direction=direction,
        low=low,
        high=high,
        sdt=sdt,
        edt=edt,
        power=abs(high - low),
    )


def make_bi(direction, low, high, sdt, edt):
    """Create a minimal BI-like object for signal_second_buy."""
    return _make_bi(direction, low, high, sdt, edt)


def build_mock_bis(base):
    """Build a finished_bi list that forms a valid 二买 after a 一买 anchor."""
    return [
        make_bi(Direction.Up,   90, 100, base,            base + timedelta(hours=1)),
        make_bi(Direction.Down, 85, 95,  base + timedelta(hours=1), base + timedelta(hours=2)),
        make_bi(Direction.Up,   92, 98,  base + timedelta(hours=2), base + timedelta(hours=3)),
        make_bi(Direction.Down, 80, 88,  base + timedelta(hours=3), base + timedelta(hours=4)),  # 一买低点
        make_bi(Direction.Up,   95, 105, base + timedelta(hours=4), base + timedelta(hours=5)),  # 反弹突破 zg=100
        make_bi(Direction.Down, 101, 103, base + timedelta(hours=5), base + timedelta(hours=6)),  # 回抽不入中枢
        make_bi(Direction.Up,   102, 108, base + timedelta(hours=6), base + timedelta(hours=7)),  # 确认向上笔
    ]


def test_second_buy_not_killed_by_anchor_time():
    """二买结构成立时，锚点时间过滤不应误杀信号。"""
    base = datetime(2024, 1, 1)
    bis = build_mock_bis(base)

    class MockCZSC:
        finished_bis = bis
        last_bi_extend = False

    # 模拟 positions._record_buy1_anchor 记录的 dt：为一买向下笔结束时间
    anchor = {
        "dt": base + timedelta(hours=4),
        "price": 80.0,
        "zs_zg": 100.0,
        "zs_zd": 90.0,
    }

    result = signal_second_buy(MockCZSC(), freq="30分钟", buy1_anchor=anchor)
    value = list(result.values())[0]
    print("signal_second_buy result:", value)
    assert "二买确认" in value, f"Expected 二买确认 signal, got {value}"


def test_buy1_anchor_dt_is_bi_end():
    """一买锚点的时间应记录为对应向下笔的结束时间，而不是信号出现时的 bar 时间。"""
    base = datetime(2024, 1, 1)
    # 一买确认出现时，已确认笔只到确认向上笔，尚未形成二买回抽/确认
    bis = [
        make_bi(Direction.Up,   90, 100, base,            base + timedelta(hours=1)),
        make_bi(Direction.Down, 85, 95,  base + timedelta(hours=1), base + timedelta(hours=2)),
        make_bi(Direction.Up,   92, 98,  base + timedelta(hours=2), base + timedelta(hours=3)),
        make_bi(Direction.Down, 80, 88,  base + timedelta(hours=3), base + timedelta(hours=4)),  # 一买低点
        make_bi(Direction.Up,   95, 105, base + timedelta(hours=4), base + timedelta(hours=5)),  # 确认向上笔
    ]

    class MockCZSC:
        finished_bis = bis
        last_bi_extend = False

    strategy = ChanTimingStrategy(symbol="TEST", freq="30分钟")
    signals_dict = {"30分钟_D1BSP_一买V260615": "一买确认_任意_任意_80"}
    # dt 故意设置为一买确认出现时的 bar 时间（晚于向下笔结束时间）
    signal_dt = base + timedelta(hours=7)
    strategy.update(signals_dict, price=108.0, dt=signal_dt, czsc_obj=MockCZSC())

    anchor = strategy.get_last_buy1_anchor()
    assert anchor is not None, "一买锚点未被记录"
    assert anchor["price"] == 80.0, f"锚点价格应为 80.0，得到 {anchor['price']}"
    assert anchor["dt"] == base + timedelta(hours=4), (
        f"锚点时间应为向下笔结束时间 {base + timedelta(hours=4)}，"
        f"得到 {anchor['dt']}"
    )
    print("test_buy1_anchor_dt_is_bi_end passed:", anchor)


def test_second_buy_inside_zs():
    """二买允许回抽进入中枢，只要回抽不创新低。"""
    base = datetime(2024, 1, 1)
    # 一买低点 80，中枢 zg=100/zd=90
    # 反弹仅进入中枢内部（high=99 < zg=100），回抽进入中枢（low=93 < zg=100 但 > 80）
    bis = [
        make_bi(Direction.Up,   90, 100, base,            base + timedelta(hours=1)),
        make_bi(Direction.Down, 85, 95,  base + timedelta(hours=1), base + timedelta(hours=2)),
        make_bi(Direction.Up,   92, 98,  base + timedelta(hours=2), base + timedelta(hours=3)),
        make_bi(Direction.Down, 80, 88,  base + timedelta(hours=3), base + timedelta(hours=4)),  # 一买低点
        make_bi(Direction.Up,   94, 99,  base + timedelta(hours=4), base + timedelta(hours=5)),  # 反弹未突破 zg
        make_bi(Direction.Down, 91, 93,  base + timedelta(hours=5), base + timedelta(hours=6)),  # 回抽进入中枢但不创新低
        make_bi(Direction.Up,   96, 102, base + timedelta(hours=6), base + timedelta(hours=7)),  # 确认向上笔
    ]

    class MockCZSC:
        finished_bis = bis
        last_bi_extend = False

    anchor = {
        "dt": base + timedelta(hours=4),
        "price": 80.0,
        "zs_zd": 90.0,
        "zs_zg": 100.0,
    }

    result = signal_second_buy(MockCZSC(), freq="30分钟", buy1_anchor=anchor)
    value = list(result.values())[0]
    print("signal_second_buy inside-zs result:", value)
    assert "二买确认" in value, (
        f"Expected 二买确认 when retracement enters zs but doesn't make new low, got {value}"
    )


if __name__ == "__main__":
    test_second_buy_not_killed_by_anchor_time()
    test_buy1_anchor_dt_is_bi_end()
    test_second_buy_inside_zs()
    print("\nAll regression tests passed.")
