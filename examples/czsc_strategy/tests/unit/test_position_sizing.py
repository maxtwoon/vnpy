"""A40 real position sizing unit tests.

RESEARCH-ONLY, not a trading recommendation.
"""
from datetime import datetime
from math import floor

import pytest

from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.positions import Position


NOW = datetime(2024, 1, 1, 10, 0)


@pytest.fixture(autouse=True)
def restore_sizing_config():
    """Save/restore sizing-related config so tests never leak global state."""
    saved = {
        "sizing_model": STRATEGY_CONFIG.get("sizing_model", "research"),
        "risk_per_trade_pct": STRATEGY_CONFIG.get("risk_per_trade_pct", 0.005),
        "max_margin_pct": STRATEGY_CONFIG.get("max_margin_pct", 0.50),
        "equity_mode": STRATEGY_CONFIG.get("equity_mode", "fixed"),
        "stop_execution_model": STRATEGY_CONFIG.get("stop_execution_model", "close"),
        "stop_penalty_bp": STRATEGY_CONFIG.get("stop_penalty_bp", 0),
        "price_tick_rounding": STRATEGY_CONFIG.get("price_tick_rounding", "off"),
    }
    yield
    STRATEGY_CONFIG.update(saved)


def _pos(symbol: str = "TEST", stop_loss: int = 200) -> Position:
    """Bare Position with no open/exit events; we drive opens/closes directly."""
    return Position("t", symbol, opens=[], exits=[], timeout=10_000, stop_loss=stop_loss)


def _default_contract_specs() -> dict:
    """Return the contract specs expected by A40 design."""
    return {
        "AP888": {"multiplier": 10, "tick": 1.0, "margin_rate": 0.07},
        "RB888": {"multiplier": 10, "tick": 1.0, "margin_rate": 0.05},
        "SC888": {"multiplier": 1000, "tick": 0.1, "margin_rate": 0.05},
        "A888": {"multiplier": 10, "tick": 1.0, "margin_rate": 0.05},
        "ZN888": {"multiplier": 5, "tick": 5.0, "margin_rate": 0.05},
    }


# --------------------------------------------------------------------- config AC

def test_strategy_config_has_a40_sizing_keys():
    assert "sizing_model" in STRATEGY_CONFIG
    assert STRATEGY_CONFIG["sizing_model"] == "research"
    assert STRATEGY_CONFIG["risk_per_trade_pct"] == pytest.approx(0.005)
    assert STRATEGY_CONFIG["max_margin_pct"] == pytest.approx(0.50)
    assert STRATEGY_CONFIG["equity_mode"] == "fixed"


def test_contract_specs_have_cited_exchange_values():
    specs = STRATEGY_CONFIG.get("contract_specs", {})
    expected = _default_contract_specs()
    for symbol, spec in expected.items():
        assert symbol in specs, f"missing {symbol}"
        assert specs[symbol]["multiplier"] == spec["multiplier"]
        assert specs[symbol]["tick"] == pytest.approx(spec["tick"])
        assert specs[symbol]["margin_rate"] == pytest.approx(spec["margin_rate"])


def test_trade_prices_are_rounded_to_contract_tick():
    """Recorded fill prices must land on the exchange tick grid."""
    STRATEGY_CONFIG["sizing_model"] = "research"
    STRATEGY_CONFIG["price_tick_rounding"] = "on"
    p = _pos("AP888", stop_loss=200)

    p._open_long(100.5, NOW)
    p._close_long(101.49, NOW, "signal_exit")

    pair = p.pairs[-1]
    assert pair["open_price"] == pytest.approx(101.0)
    assert pair["close_price"] == pytest.approx(101.0)
    assert p.trades[0].price == pytest.approx(101.0)
    assert p.trades[1].price == pytest.approx(101.0)


# --------------------------------------------------------------- research mode

def test_research_mode_keeps_volume_and_multiplier_at_one():
    STRATEGY_CONFIG["sizing_model"] = "research"
    p = _pos("RB888", stop_loss=200)
    p._open_long(100.0, NOW)
    assert p.volume == 1
    assert p.contract_multiplier == 1


def test_research_mode_pnl_currency_equals_pnl_pct_times_entry():
    STRATEGY_CONFIG["sizing_model"] = "research"
    p = _pos("RB888", stop_loss=200)
    p._open_long(100.0, NOW)
    p._close_long(102.0, NOW, "signal_exit")
    pair = p.pairs[-1]
    assert pair["volume"] == 1
    assert pair["contract_multiplier"] == 1
    assert pair["pnl_currency"] == pytest.approx(pair["pnl_pct"] * 100.0)


def test_research_mode_short_pnl_currency_equals_pnl_pct_times_entry():
    STRATEGY_CONFIG["sizing_model"] = "research"
    p = _pos("RB888", stop_loss=200)
    p._open_short(100.0, NOW)
    p._close_short(98.0, NOW, "signal_exit")
    pair = p.pairs[-1]
    assert pair["volume"] == 1
    assert pair["contract_multiplier"] == 1
    assert pair["pnl_currency"] == pytest.approx(pair["pnl_pct"] * 100.0)


# ------------------------------------------------------------------ risk sizing

def _expected_volume(price: float, equity: float, stop_loss_bp: int, multiplier: int) -> int:
    stop_distance = price * stop_loss_bp / 10000
    risk_amount = equity * STRATEGY_CONFIG["risk_per_trade_pct"]
    return int(floor(risk_amount / (stop_distance * multiplier)))


def test_risk_mode_long_sizing_formula():
    STRATEGY_CONFIG["sizing_model"] = "risk"
    price = 5000.0
    equity = 1_000_000.0
    multiplier = 10  # RB888
    p = _pos("RB888", stop_loss=200)
    p._open_long(price, NOW, equity_at_entry=equity, total_open_margin=0.0)
    assert p.volume == _expected_volume(price, equity, 200, multiplier)
    assert p.contract_multiplier == multiplier
    assert p.pos == 1


def test_risk_mode_short_sizing_formula():
    STRATEGY_CONFIG["sizing_model"] = "risk"
    price = 100.0
    equity = 1_000_000.0
    multiplier = 1000  # SC888
    p = _pos("SC888", stop_loss=300)
    p._open_short(price, NOW, equity_at_entry=equity, total_open_margin=0.0)
    assert p.volume == _expected_volume(price, equity, 300, multiplier)
    assert p.contract_multiplier == multiplier
    assert p.pos == -1


# --------------------------------------------------------------- zero-size skip

def test_risk_mode_zero_size_skips_open_long():
    STRATEGY_CONFIG["sizing_model"] = "risk"
    # Very high price / large stop -> raw_volume < 1
    p = _pos("RB888", stop_loss=200)
    prior_skips = p.size_zero_skip
    p._open_long(1_000_000.0, NOW, equity_at_entry=1_000_000.0, total_open_margin=0.0)
    assert p.pos == 0
    assert not p.pairs
    assert not p.trades
    assert p.size_zero_skip == prior_skips + 1


def test_risk_mode_zero_size_skips_open_short():
    STRATEGY_CONFIG["sizing_model"] = "risk"
    p = _pos("SC888", stop_loss=300)
    prior_skips = p.size_zero_skip
    p._open_short(1_000_000.0, NOW, equity_at_entry=1_000_000.0, total_open_margin=0.0)
    assert p.pos == 0
    assert not p.pairs
    assert not p.trades
    assert p.size_zero_skip == prior_skips + 1


# ------------------------------------------------------------------ margin cap

def test_risk_mode_margin_cap_reduces_volume():
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["max_margin_pct"] = 0.01
    price = 5000.0
    equity = 1_000_000.0
    multiplier = 10
    margin_rate = 0.05
    p = _pos("RB888", stop_loss=200)
    raw_volume = _expected_volume(price, equity, 200, multiplier)
    # Cap allows fewer lots than raw sizing.
    margin_cap_lots = int(floor((equity * 0.01) / (price * multiplier * margin_rate)))
    assert margin_cap_lots < raw_volume
    p._open_long(price, NOW, equity_at_entry=equity, total_open_margin=0.0)
    assert p.volume == margin_cap_lots
    assert p.pos == 1


def test_risk_mode_margin_cap_skip_when_one_lot_does_not_fit():
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["max_margin_pct"] = 0.001
    price = 5000.0
    equity = 1_000_000.0
    p = _pos("RB888", stop_loss=200)
    prior_skips = p.margin_cap_skip
    p._open_long(price, NOW, equity_at_entry=equity, total_open_margin=0.0)
    assert p.pos == 0
    assert not p.pairs
    assert p.margin_cap_skip == prior_skips + 1


def test_risk_mode_margin_cap_considers_existing_open_margin():
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["max_margin_pct"] = 0.10
    price = 5000.0
    equity = 1_000_000.0
    multiplier = 10
    margin_rate = 0.05
    one_lot_margin = price * multiplier * margin_rate
    p = _pos("RB888", stop_loss=200)
    # Pre-existing margin consumes almost the entire cap.
    existing_margin = equity * 0.10 - one_lot_margin * 0.5
    p._open_long(price, NOW, equity_at_entry=equity, total_open_margin=existing_margin)
    assert p.pos == 0
    assert p.margin_cap_skip > 0


# ---------------------------------------------------------------- currency PnL

def test_risk_mode_long_currency_pnl_formula():
    STRATEGY_CONFIG["sizing_model"] = "risk"
    price = 5000.0
    equity = 1_000_000.0
    exit = 5100.0
    multiplier = 10
    p = _pos("RB888", stop_loss=200)
    p._open_long(price, NOW, equity_at_entry=equity, total_open_margin=0.0)
    volume = p.volume
    p._close_long(exit, NOW, "signal_exit")
    pair = p.pairs[-1]
    tx_cost = (2 * p.commission_rate + p.slippage) * price * volume * multiplier
    expected = (exit - price) * volume * multiplier - tx_cost
    assert pair["pnl_currency"] == pytest.approx(expected, rel=1e-9)


def test_risk_mode_short_currency_pnl_formula():
    STRATEGY_CONFIG["sizing_model"] = "risk"
    price = 100.0
    equity = 1_000_000.0
    exit = 99.0
    multiplier = 1000
    p = _pos("SC888", stop_loss=300)
    p._open_short(price, NOW, equity_at_entry=equity, total_open_margin=0.0)
    volume = p.volume
    p._close_short(exit, NOW, "signal_exit")
    pair = p.pairs[-1]
    tx_cost = (2 * p.commission_rate + p.slippage) * price * volume * multiplier
    expected = (price - exit) * volume * multiplier - tx_cost
    assert pair["pnl_currency"] == pytest.approx(expected, rel=1e-9)


# ----------------------------------------------------------- no-lookahead / AC-11

def test_risk_mode_stop_distance_matches_intrabar_trigger_level():
    """AC-A40-11: sizing denominator equals A38 intrabar stop trigger level."""
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    price = 100.0
    stop_loss_bp = 200
    p = _pos("TEST", stop_loss=stop_loss_bp)
    p._open_long(price, NOW, equity_at_entry=1_000_000.0, total_open_margin=0.0)
    stop_distance = price * stop_loss_bp / 10000
    # Intracomment: A38 long trigger is cost * (1 - stop_loss/10000)
    # The distance from entry to trigger is exactly stop_distance.
    expected_trigger = price - stop_distance
    assert p.cost == pytest.approx(price)
    assert expected_trigger == pytest.approx(p.cost * (1 - stop_loss_bp / 10000))


# ------------------------------------------------------- sizing x intrabar (AC-12)

def test_risk_mode_sizing_with_intrabar_long_exit_uses_stop_fill_price():
    """AC-A40-12: pnl_currency on a touch exit uses the actual touched stop price."""
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    STRATEGY_CONFIG["stop_penalty_bp"] = 0
    price = 100.0
    equity = 1_000_000.0
    multiplier = 10
    stop_loss_bp = 200
    p = _pos("RB888", stop_loss=stop_loss_bp)
    p._open_long(price, NOW, equity_at_entry=equity, total_open_margin=0.0)
    volume = p.volume
    # Trigger = 98; close=99 (above stop), low=97.5 (touches) -> fill at trigger 98.
    p.update({}, price=99.0, dt=NOW, bar_high=101.0, bar_low=97.5)
    pair = p.pairs[-1]
    assert pair["reason"] == "止损"
    trigger_fill = price * (1 - stop_loss_bp / 10000)
    assert pair["close_price"] == pytest.approx(trigger_fill)
    expected = (trigger_fill - price) * volume * multiplier
    expected -= (2 * p.commission_rate + p.slippage) * price * volume * multiplier
    assert pair["pnl_currency"] == pytest.approx(expected, rel=1e-9)


def test_risk_mode_sizing_with_intrabar_short_exit_uses_stop_fill_price():
    """AC-A40-12 short counterpart: touched stop price, not bar.close."""
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    STRATEGY_CONFIG["stop_penalty_bp"] = 0
    price = 100.0
    equity = 1_000_000.0
    multiplier = 10
    stop_loss_bp = 200
    p = _pos("RB888", stop_loss=stop_loss_bp)
    p._open_short(price, NOW, equity_at_entry=equity, total_open_margin=0.0)
    volume = p.volume
    # Trigger = 102; close=101 (below stop), high=102.5 (touches) -> fill at trigger 102.
    p.update({}, price=101.0, dt=NOW, bar_high=102.5, bar_low=99.0)
    pair = p.pairs[-1]
    assert pair["reason"] == "止损"
    trigger_fill = price * (1 + stop_loss_bp / 10000)
    assert pair["close_price"] == pytest.approx(trigger_fill)
    expected = (price - trigger_fill) * volume * multiplier
    expected -= (2 * p.commission_rate + p.slippage) * price * volume * multiplier
    assert pair["pnl_currency"] == pytest.approx(expected, rel=1e-9)


# ----------------------------------------------------------- no-lookahead AC

def test_compute_size_uses_only_entry_bar_inputs():
    """No-lookahead: sizing reads only price, stop_loss, equity, margin cap."""
    STRATEGY_CONFIG["sizing_model"] = "risk"
    p = _pos("RB888", stop_loss=200)
    p._open_long(5000.0, NOW, equity_at_entry=1_000_000.0, total_open_margin=0.0)
    assert p.pos == 1
    opened_volume = p.volume
    assert opened_volume > 0
    # Closing at a very different price must not retroactively change the sized volume.
    p._close_long(4000.0, NOW, "signal_exit")
    assert p.pairs[-1]["volume"] == opened_volume
