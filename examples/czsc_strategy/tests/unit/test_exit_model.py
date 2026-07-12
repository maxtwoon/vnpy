"""A47 P8a — Exit-model unit tests.

Verifies the ``structural_atr`` exit model (partial take-profit + ATR trailing)
and confirms that ``legacy`` remains byte-identical to the historical baseline
at the unit level.

RESEARCH-ONLY, not a trading recommendation.
"""
from datetime import datetime, timedelta

import pytest

from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.positions import Event, Operate, Position


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


def _event(name: str, operate: str, signals_all: list[str] | None = None) -> Event:
    return Event.load({"name": name, "operate": operate, "signals_all": signals_all or []})


def _signal_key(signal: str) -> str:
    """Return the czsc signal key (first three underscore-separated parts)."""
    return "_".join(signal.split("_")[:3])


def _signal_value(signal: str) -> str:
    """Return the czsc signal value (remaining underscore-separated parts)."""
    return "_".join(signal.split("_")[3:])


def _signal_match(signal: str) -> dict:
    """Return a signals_dict entry that matches the given signal pattern."""
    return {_signal_key(signal): _signal_value(signal).replace("任意", "a")}


def _directional_target_event(name: str, operate: str, signal: str) -> Event:
    """Build a partial-TP style event matching a single directional signal."""
    event = Event.load({
        "name": name,
        "operate": operate,
        "signals_all": [],
        "signals_any": [],
        "signals_not": [],
        "factors": [{
            "name": "target",
            "signals_all": [signal],
            "signals_any": [],
            "signals_not": [],
        }],
    })
    event.is_partial_tp = True
    return event


def test_legacy_uses_percentage_trailing_stop():
    STRATEGY_CONFIG["exit_model"] = "legacy"
    sig_open = "A_B_C_x_任意_任意_0"
    p = Position(
        "p", "T",
        [_event("open", "开多", [sig_open])],
        timeout=99, trailing_start=100, trailing_drawback_pct=0.5,
    )
    now = datetime(2024, 1, 1)
    p.update(_signal_match(sig_open), 100, now)
    p.update({}, 102, now + timedelta(minutes=1))
    assert p.trailing_active
    p.update({}, 101, now + timedelta(minutes=2))
    assert p.pos == 0
    assert p.pairs[-1]["reason"] == "移动止损"
    assert p.pairs[-1]["reason_code"] == "trailing_stop"


def test_structural_atr_partial_tp_long():
    STRATEGY_CONFIG["exit_model"] = "structural_atr"
    STRATEGY_CONFIG["partial_tp_frac"] = 0.5
    STRATEGY_CONFIG["atr_trail_mult"] = 3.0

    sig_open = "A_B_C_x_任意_任意_0"
    sig_target = "A_B_D_y_任意_任意_0"
    partial_event = _directional_target_event("partial-tp", "平多", sig_target)
    partial_event.operate = Operate.LC
    p = Position(
        "p", "T",
        [_event("open", "开多", [sig_open])],
        exits=[partial_event],
        timeout=99, stop_loss=1000,
    )
    now = datetime(2024, 1, 1)
    p.update(_signal_match(sig_open), 100, now)
    assert p.pos == 1
    assert p.volume == 1

    p.update(_signal_match(sig_target), 110, now + timedelta(minutes=1))
    assert p.pos == 1
    assert p.volume == pytest.approx(0.5)
    assert len(p.pairs) == 1
    assert p.pairs[-1]["is_partial_tp"] is True
    assert p.pairs[-1]["volume"] == pytest.approx(0.5)
    assert p.pairs[-1]["reason_code"] == "partial_tp"


def test_structural_atr_partial_tp_short():
    STRATEGY_CONFIG["exit_model"] = "structural_atr"
    STRATEGY_CONFIG["partial_tp_frac"] = 0.5
    STRATEGY_CONFIG["atr_trail_mult"] = 3.0

    sig_open = "A_B_C_x_任意_任意_0"
    sig_target = "A_B_D_y_任意_任意_0"
    partial_event = _directional_target_event("partial-tp", "平空", sig_target)
    partial_event.operate = Operate.SC
    p = Position(
        "p", "T",
        [_event("open", "开空", [sig_open])],
        exits=[partial_event],
        timeout=99, stop_loss=1000,
    )
    now = datetime(2024, 1, 1)
    p.update(_signal_match(sig_open), 100, now)
    assert p.pos == -1
    assert p.volume == 1

    p.update(_signal_match(sig_target), 90, now + timedelta(minutes=1))
    assert p.pos == -1
    assert p.volume == pytest.approx(0.5)
    assert p.pairs[-1]["is_partial_tp"] is True
    assert p.pairs[-1]["volume"] == pytest.approx(0.5)


def test_structural_atr_atr_trailing_long():
    STRATEGY_CONFIG["exit_model"] = "structural_atr"
    STRATEGY_CONFIG["partial_tp_frac"] = 0.5
    STRATEGY_CONFIG["atr_trail_mult"] = 2.0

    sig_open = "A_B_C_x_任意_任意_0"
    sig_target = "A_B_D_y_任意_任意_0"
    partial_event = _directional_target_event("partial-tp", "平多", sig_target)
    partial_event.operate = Operate.LC
    p = Position(
        "p", "T",
        [_event("open", "开多", [sig_open])],
        exits=[partial_event],
        timeout=99, stop_loss=1000,
    )
    now = datetime(2024, 1, 1)
    p.update(_signal_match(sig_open), 100, now)
    # partial TP at 110, peak = 110
    p.update(_signal_match(sig_target), 110, now + timedelta(minutes=1))
    assert p.volume == pytest.approx(0.5)

    # peak 110, atr=2, mult=2.0 -> trail = 110 - 4 = 106
    # price 106.5 is above trail, no exit
    p.update({}, 106.5, now + timedelta(minutes=2), atr=2.0)
    assert p.pos == 1

    # price drops to 105.5, below trail -> ATR trailing exit
    p.update({}, 105.5, now + timedelta(minutes=3), atr=2.0)
    assert p.pos == 0
    assert p.pairs[-1]["reason"] == "ATR移动止损"
    assert p.pairs[-1]["reason_code"] == "atr_trailing_stop"
    assert p.pairs[-1]["volume"] == pytest.approx(0.5)


def test_structural_atr_atr_trailing_short():
    STRATEGY_CONFIG["exit_model"] = "structural_atr"
    STRATEGY_CONFIG["partial_tp_frac"] = 0.5
    STRATEGY_CONFIG["atr_trail_mult"] = 2.0

    sig_open = "A_B_C_x_任意_任意_0"
    sig_target = "A_B_D_y_任意_任意_0"
    partial_event = _directional_target_event("partial-tp", "平空", sig_target)
    partial_event.operate = Operate.SC
    p = Position(
        "p", "T",
        [_event("open", "开空", [sig_open])],
        exits=[partial_event],
        timeout=99, stop_loss=1000,
    )
    now = datetime(2024, 1, 1)
    p.update(_signal_match(sig_open), 100, now)
    # partial TP at 90, trough = 90
    p.update(_signal_match(sig_target), 90, now + timedelta(minutes=1))
    assert p.volume == pytest.approx(0.5)

    # trough 90, atr=2, mult=2.0 -> trail = 90 + 4 = 94
    p.update({}, 93.5, now + timedelta(minutes=2), atr=2.0)
    assert p.pos == -1

    p.update({}, 95.5, now + timedelta(minutes=3), atr=2.0)
    assert p.pos == 0
    assert p.pairs[-1]["reason_code"] == "atr_trailing_stop"


def test_structural_stop_fires_under_both_exit_models():
    sig_open = "A_B_C_x_任意_任意_0"
    sig_structural = "A_B_E_z_任意_任意_0"
    for model in ("legacy", "structural_atr"):
        STRATEGY_CONFIG["exit_model"] = model
        p = Position(
            "p", "T",
            [_event("open", "开多", [sig_open])],
            [_event("close", "平多", [sig_structural])],
            timeout=99, stop_loss=1000,
        )
        now = datetime(2024, 1, 1)
        p.update(_signal_match(sig_open), 100, now)
        p.update(_signal_match(sig_structural), 95, now + timedelta(minutes=1))
        assert p.pos == 0
        assert p.pairs[-1]["reason"].startswith("信号平仓")


def test_fixed_stop_loss_fires_under_both_exit_models():
    sig_open = "A_B_C_x_任意_任意_0"
    for model in ("legacy", "structural_atr"):
        STRATEGY_CONFIG["exit_model"] = model
        p = Position(
            "p", "T",
            [_event("open", "开多", [sig_open])],
            timeout=99, stop_loss=100,
        )
        now = datetime(2024, 1, 1)
        p.update(_signal_match(sig_open), 100, now)
        p.update({}, 98.9, now + timedelta(minutes=1))
        assert p.pos == 0
        assert p.pairs[-1]["reason"] == "止损"
        assert p.pairs[-1]["reason_code"] == "stop_loss"


def test_timeout_fires_under_both_exit_models():
    sig_open = "A_B_C_x_任意_任意_0"
    for model in ("legacy", "structural_atr"):
        STRATEGY_CONFIG["exit_model"] = model
        p = Position(
            "p", "T",
            [_event("open", "开多", [sig_open])],
            timeout=3, stop_loss=1000,
        )
        now = datetime(2024, 1, 1)
        p.update(_signal_match(sig_open), 100, now)
        p.update({}, 100, now + timedelta(minutes=1))
        p.update({}, 100, now + timedelta(minutes=2))
        assert p.pos == 0
        assert p.pairs[-1]["reason"] == "超时"
        assert p.pairs[-1]["reason_code"] == "timeout"
