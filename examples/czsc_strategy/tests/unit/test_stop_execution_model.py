"""A38 Phase 1 - touch-based (intrabar) stop execution model.

Covers the STRATEGY_CONFIG["stop_execution_model"] switch on Position:
- "close" (default) delegates to the unchanged _check_stop_loss and fills at the
  close price -> byte-identical to the historical baseline (intrabar bar extremes
  are ignored).
- "intrabar" triggers on the current bar's low (long) / high (short) crossing the
  stop level derived from entry cost, and fills at min/max(trigger, close) with an
  optional stop_penalty_bp adverse slippage.
"""
from datetime import datetime

import pytest

from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.positions import Position

NOW = datetime(2024, 1, 1, 10, 0)


@pytest.fixture(autouse=True)
def restore_stop_config():
    """Save/restore the stop-execution config so tests never leak global state."""
    saved = {
        "stop_execution_model": STRATEGY_CONFIG.get("stop_execution_model", "close"),
        "stop_penalty_bp": STRATEGY_CONFIG.get("stop_penalty_bp", 0),
    }
    yield
    STRATEGY_CONFIG.update(saved)


def _pos(stop_loss=300):
    # No opens/exits: we drive risk directly; stop_loss=300bp (3%).
    return Position("t", "X", opens=[], exits=[], timeout=10_000, stop_loss=stop_loss)


def _last_close_price(p):
    assert p.pairs, "expected a closed pair"
    return p.pairs[-1]["close_price"]


# ----------------------------------------------------------------- intrabar long
def test_intrabar_long_triggers_on_low_fills_at_trigger():
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    STRATEGY_CONFIG["stop_penalty_bp"] = 0
    p = _pos()
    p._open_long(100.0, NOW)          # trigger level = 100*(1-0.03) = 97
    # close (98) is above the stop, but the bar low (96) pierced it.
    p.update({}, price=98.0, dt=NOW, bar_high=99.0, bar_low=96.0)
    assert p.pos == 0
    assert p.pairs[-1]["reason"] == "止损"
    assert _last_close_price(p) == pytest.approx(97.0)   # min(trigger=97, close=98)


def test_intrabar_long_no_trigger_when_low_above_level():
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    p = _pos()
    p._open_long(100.0, NOW)
    p.update({}, price=98.0, dt=NOW, bar_high=99.0, bar_low=97.5)  # 97.5 > 97
    assert p.pos == 1
    assert not p.pairs


def test_intrabar_long_gap_through_fills_at_close():
    """When the close gaps below the trigger, fill degrades to the worse close."""
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    STRATEGY_CONFIG["stop_penalty_bp"] = 0
    p = _pos()
    p._open_long(100.0, NOW)
    p.update({}, price=95.0, dt=NOW, bar_high=99.0, bar_low=94.0)
    assert p.pos == 0
    assert _last_close_price(p) == pytest.approx(95.0)   # min(97, 95) = 95


def test_intrabar_long_penalty_worsens_fill():
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    STRATEGY_CONFIG["stop_penalty_bp"] = 10          # 10bp adverse
    p = _pos()
    p._open_long(100.0, NOW)
    p.update({}, price=98.0, dt=NOW, bar_high=99.0, bar_low=96.0)
    assert _last_close_price(p) == pytest.approx(97.0 * (1 - 0.001))


# ---------------------------------------------------------------- intrabar short
def test_intrabar_short_triggers_on_high_fills_at_trigger():
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    STRATEGY_CONFIG["stop_penalty_bp"] = 0
    p = _pos()
    p._open_short(100.0, NOW)         # trigger = 100*(1+0.03) = 103
    p.update({}, price=102.0, dt=NOW, bar_high=104.0, bar_low=101.0)
    assert p.pos == 0
    assert _last_close_price(p) == pytest.approx(103.0)  # max(103, 102)


def test_intrabar_short_penalty_worsens_fill():
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    STRATEGY_CONFIG["stop_penalty_bp"] = 10
    p = _pos()
    p._open_short(100.0, NOW)
    p.update({}, price=102.0, dt=NOW, bar_high=104.0, bar_low=101.0)
    assert _last_close_price(p) == pytest.approx(103.0 * (1 + 0.001))


# ------------------------------------------------------- close model = baseline
def test_close_model_ignores_intrabar_low():
    """close model must not consult bar extremes (byte-identical baseline)."""
    STRATEGY_CONFIG["stop_execution_model"] = "close"
    p = _pos()
    p._open_long(100.0, NOW)
    # bar low pierced 97, but close (98) is above the stop -> no trigger under close.
    p.update({}, price=98.0, dt=NOW, bar_high=99.0, bar_low=96.0)
    assert p.pos == 1
    assert not p.pairs


def test_close_model_triggers_on_close_and_fills_at_close():
    STRATEGY_CONFIG["stop_execution_model"] = "close"
    p = _pos()
    p._open_long(100.0, NOW)
    p.update({}, price=96.0, dt=NOW, bar_high=99.0, bar_low=95.0)
    assert p.pos == 0
    assert _last_close_price(p) == pytest.approx(96.0)   # fills at close price


def test_intrabar_missing_bar_extremes_falls_back_to_close():
    """intrabar requested but bar_low None -> safe fallback to close check."""
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    p = _pos()
    p._open_long(100.0, NOW)
    p.update({}, price=98.0, dt=NOW)     # no bar extremes; 98 > 97 -> no trigger
    assert p.pos == 1
    p.update({}, price=96.0, dt=NOW)     # 96 <= 97 -> close-style trigger
    assert p.pos == 0
    assert _last_close_price(p) == pytest.approx(96.0)


# ------------------------------------------------- close-model equivalence proof
def _run_sequence(pass_extremes):
    """Drive an identical open+risk sequence; optionally pass bar extremes."""
    STRATEGY_CONFIG["stop_execution_model"] = "close"
    p = _pos()
    p._open_long(100.0, NOW)
    prices = [101.0, 99.0, 96.5, 98.0]   # last-but-one pierces the 97 stop on close
    for px in prices:
        if p.pos == 0:
            break
        if pass_extremes:
            p.update({}, price=px, dt=NOW, bar_high=px + 2, bar_low=px - 2)
        else:
            p.update({}, price=px, dt=NOW)
    return [(pr["close_price"], pr["reason"]) for pr in p.pairs]


def test_close_model_byte_identical_with_and_without_bar_extremes():
    """Passing bar high/low must not change close-model outcomes at all."""
    assert _run_sequence(pass_extremes=False) == _run_sequence(pass_extremes=True)
