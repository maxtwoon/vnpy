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


@pytest.mark.parametrize(
    "direction,open_op,close_op,open_price,partial_price,trail_exit_price",
    [
        ("long", "开多", "平多", 100, 110, 105),
        ("short", "开空", "平空", 100, 90, 95),
    ],
)
def test_risk_mode_skipped_partial_tp_makes_atr_trailing_reachable(
    direction, open_op, close_op, open_price, partial_price, trail_exit_price,
    monkeypatch,
):
    """A49 regression: risk-mode 1-lot position skips partial TP, ATR trailing
    must still be reachable on the very next bar.

    Before the fix, ``_partial_tp_done`` stayed False after the skip, so the
    ``elif self._check_atr_trailing_stop(...)`` branch in ``Position.update``
    was never entered again.  After the fix, the flag is set and the trailing
    check fires on the next bar.
    """
    STRATEGY_CONFIG["exit_model"] = "structural_atr"
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["partial_tp_frac"] = 0.5
    STRATEGY_CONFIG["atr_trail_mult"] = 2.0

    # Force a 1-lot risk-mode position so floor(1 * 0.5) == 0 and the partial
    # TP scale-out is skipped (no actual volume changes hands).
    monkeypatch.setattr(
        Position, "_size_open",
        lambda self, price, equity_at_entry, total_open_margin: (1, 1),
    )

    sig_open = "A_B_C_x_任意_任意_0"
    sig_target = "A_B_D_y_任意_任意_0"
    partial_event = _directional_target_event("partial-tp", close_op, sig_target)
    partial_event.operate = Operate.LC if direction == "long" else Operate.SC

    p = Position(
        "p", "T",
        [_event("open", open_op, [sig_open])],
        exits=[partial_event],
        timeout=99, stop_loss=1000,
    )

    calls: list[tuple[float, float | None]] = []
    original_check = Position._check_atr_trailing_stop

    def counting_check(self, price, atr):
        calls.append((price, atr))
        return original_check(self, price, atr)

    monkeypatch.setattr(
        Position, "_check_atr_trailing_stop", counting_check
    )

    now = datetime(2024, 1, 1)
    p.update(_signal_match(sig_open), open_price, now, equity_at_entry=10000)
    assert p.pos == (1 if direction == "long" else -1)
    assert p.volume == 1

    # Bar with the partial-TP signal: scale-out is skipped due to lot flooring.
    p.update(_signal_match(sig_target), partial_price, now + timedelta(minutes=1))
    assert p._partial_tp_done is True
    assert len(p.pairs) == 0
    assert p.volume == 1
    # The trailing-stop branch is unreachable on the skipped-partial bar itself.
    assert len(calls) == 0

    # Next bar: ATR trailing must be reachable and, with price beyond the trail,
    # close the remaining position.
    p.update({}, trail_exit_price, now + timedelta(minutes=2), atr=2.0)
    assert len(calls) == 1
    assert p.pos == 0
    assert p.pairs[-1]["reason_code"] == "atr_trailing_stop"


@pytest.mark.parametrize(
    "direction,open_op,close_op,open_price,partial_price",
    [
        ("long", "开多", "平多", 100, 110),
        ("short", "开空", "平空", 100, 90),
    ],
)
def test_structural_atr_partial_tp_cost_rate_not_scaled_by_fraction(
    direction, open_op, close_op, open_price, partial_price, monkeypatch,
):
    """A55: partial-TP cost must use the undivided round-trip rate.

    Before the fix ``transaction_cost`` was multiplied by ``scale_fraction``;
    the pnl_currency formula then multiplied by ``scale_volume`` again, giving
    a double-discount.  After the fix the rate equals ``2*commission + slippage``
    exactly, matching ``_close_long`` / ``_close_short``.
    """
    STRATEGY_CONFIG["exit_model"] = "structural_atr"
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["partial_tp_frac"] = 0.5
    STRATEGY_CONFIG["atr_trail_mult"] = 3.0

    # Fix a 10-lot position with multiplier 10 so arithmetic is explicit.
    monkeypatch.setattr(
        Position, "_size_open",
        lambda self, price, equity_at_entry, total_open_margin: (10, 10),
    )

    sig_open = "A_B_C_x_任意_任意_0"
    sig_target = "A_B_D_y_任意_任意_0"
    partial_event = _directional_target_event("partial-tp", close_op, sig_target)
    partial_event.operate = Operate.LC if direction == "long" else Operate.SC

    p = Position(
        "p", "T",
        [_event("open", open_op, [sig_open])],
        exits=[partial_event],
        timeout=99, stop_loss=1000,
        commission_rate=0.0001, slippage=0.0005,
    )

    now = datetime(2024, 1, 1)
    p.update(_signal_match(sig_open), open_price, now, equity_at_entry=100000)
    assert p.pos == (1 if direction == "long" else -1)
    assert p.volume == 10

    p.update(_signal_match(sig_target), partial_price, now + timedelta(minutes=1))
    assert p.pos == (1 if direction == "long" else -1)
    assert p.volume == 5
    assert len(p.pairs) == 1

    pair = p.pairs[0]
    scale_volume = 5
    multiplier = 10
    full_rate = 2 * 0.0001 + 0.0005  # undivided round-trip cost rate
    expected_cost = full_rate * open_price * scale_volume * multiplier

    if direction == "long":
        gross_currency = (partial_price - open_price) * scale_volume * multiplier
    else:
        gross_currency = (open_price - partial_price) * scale_volume * multiplier

    expected_pnl_currency = gross_currency - expected_cost
    expected_pnl_pct = expected_pnl_currency / (open_price * scale_volume * multiplier)

    assert pair["pnl_currency"] == pytest.approx(expected_pnl_currency, rel=1e-12)
    assert pair["pnl_pct"] == pytest.approx(expected_pnl_pct, rel=1e-12)


@pytest.mark.parametrize(
    "direction,open_op,close_op,open_price,partial_price,final_price",
    [
        ("long", "开多", "平多", 100, 110, 110),
        ("short", "开空", "平空", 100, 90, 90),
    ],
)
def test_structural_atr_partial_tp_plus_final_cost_conservation(
    direction, open_op, close_op, open_price, partial_price, final_price, monkeypatch,
):
    """A55 conservation test: splitting an exit into partial+final must not be
    cheaper in total than a single full close of the same total volume.
    """
    STRATEGY_CONFIG["exit_model"] = "structural_atr"
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["partial_tp_frac"] = 0.5
    STRATEGY_CONFIG["atr_trail_mult"] = 3.0

    monkeypatch.setattr(
        Position, "_size_open",
        lambda self, price, equity_at_entry, total_open_margin: (10, 10),
    )

    sig_open = "A_B_C_x_任意_任意_0"
    sig_target = "A_B_D_y_任意_任意_0"
    sig_close = "A_B_E_z_任意_任意_0"

    partial_event = _directional_target_event("partial-tp", close_op, sig_target)
    partial_event.operate = Operate.LC if direction == "long" else Operate.SC
    close_event = _event("close", close_op, [sig_close])

    p = Position(
        "p", "T",
        [_event("open", open_op, [sig_open])],
        exits=[partial_event, close_event],
        timeout=99, stop_loss=1000,
        commission_rate=0.0001, slippage=0.0005,
    )

    now = datetime(2024, 1, 1)
    p.update(_signal_match(sig_open), open_price, now, equity_at_entry=100000)
    assert p.volume == 10

    # Partial TP closes 5 lots.
    p.update(_signal_match(sig_target), partial_price, now + timedelta(minutes=1))
    assert p.volume == 5
    assert len(p.pairs) == 1

    # Final signal close closes the remaining 5 lots.
    p.update(_signal_match(sig_close), final_price, now + timedelta(minutes=2))
    assert p.pos == 0
    assert len(p.pairs) == 2

    full_rate = 2 * 0.0001 + 0.0005
    single_full_cost = full_rate * open_price * 10 * 10

    def cost_of(pair: dict) -> float:
        """Return the transaction-cost portion of a pair's pnl_currency."""
        if direction == "long":
            gross = (pair["close_price"] - pair["open_price"]) * pair["volume"] * pair["contract_multiplier"]
        else:
            gross = (pair["open_price"] - pair["close_price"]) * pair["volume"] * pair["contract_multiplier"]
        return gross - pair["pnl_currency"]

    total_cost = sum(cost_of(pair) for pair in p.pairs)
    assert total_cost >= single_full_cost - 1e-12


@pytest.mark.parametrize(
    "direction,open_op,close_op",
    [
        ("long", "开多", "平多"),
        ("short", "开空", "平空"),
    ],
)
def test_close_trade_record_volume_matches_closed_lots(direction, open_op, close_op, monkeypatch):
    """A55 bundled audit-log fix: ``TradeRecord.volume`` on close must reflect
    the actual closed lots, not the default 1 reset after ``_close_long`` /
    ``_close_short``.
    """
    STRATEGY_CONFIG["exit_model"] = "legacy"
    STRATEGY_CONFIG["sizing_model"] = "risk"

    monkeypatch.setattr(
        Position, "_size_open",
        lambda self, price, equity_at_entry, total_open_margin: (7, 10),
    )

    sig_open = "A_B_C_x_任意_任意_0"
    sig_close = "A_B_D_y_任意_任意_0"
    p = Position(
        "p", "T",
        [_event("open", open_op, [sig_open])],
        [_event("close", close_op, [sig_close])],
        timeout=99, stop_loss=1000,
    )

    now = datetime(2024, 1, 1)
    p.update(_signal_match(sig_open), 100, now, equity_at_entry=100000)
    assert p.volume == 7

    p.update(_signal_match(sig_close), 110, now + timedelta(minutes=1))
    assert p.pos == 0
    assert p.trades[-1].volume == 7
    assert p.trades[-2].volume == 7  # open record also used the sized lot count
