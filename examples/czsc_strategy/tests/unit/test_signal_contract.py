from chan_strategy.positions import Event, Factor, Signal
from chan_strategy.sell_signals import get_all_signals


def test_signal_key_and_value_matching():
    sig = Signal("30分钟_D1BI_方向V260615_向上_任意_任意_50")
    assert sig.key == "30分钟_D1BI_方向V260615"
    assert sig.signal_value == "向上_任意_任意_50"
    assert sig.is_match({"30分钟_D1BI_方向V260615": "向上_foo_bar_10"})
    assert not sig.is_match({"30分钟_D1BI_方向V260615": "向下_foo_bar_10"})
    assert not sig.is_match({})


def test_factor_and_event_boolean_logic():
    signals = {
        "A_B_C": "x_y_z_1",
        "A_B_D": "yes_y_z_1",
        "A_B_E": "no_y_z_1",
    }
    factor = Factor(
        name="f",
        signals_all=[Signal("A_B_C_x_任意_任意_0")],
        signals_any=[Signal("A_B_D_yes_任意_任意_0")],
        signals_not=[Signal("A_B_E_bad_任意_任意_0")],
    )
    assert factor.is_match(signals)
    event = Event(name="e", operate=None, factors=[factor])
    assert event.is_match(signals)
    event2 = Event(name="e2", operate=None, signals_not=[Signal("A_B_E_no_任意_任意_0")])
    assert not event2.is_match(signals)


def test_get_all_signals_contract(czsc_factory):
    signals = get_all_signals(czsc_factory([]), "30分钟")
    assert signals
    for key, value in signals.items():
        full = f"{key}_{value}"
        parts = full.split("_")
        assert len(parts) == 7
        assert all("_" not in p for p in parts)
