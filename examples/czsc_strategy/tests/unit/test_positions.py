from datetime import datetime, timedelta


from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.positions import (
    ChanTimingStrategy,
    Event,
    Operate,
    Position,
    _research_second_buy_allowed,
    _research_symbol_key,
    _research_trailing_params,
    create_first_buy_position,
    create_first_sell_position,
    create_second_sell_position,
    create_third_sell_position,
    normalize_exit_reason,
)


def event(name, operate, signals_all=None):
    return Event.load({"name": name, "operate": operate, "signals_all": signals_all or []})


def test_position_open_close_stop_timeout_and_short():
    sig_open = "A_B_C_x_任意_任意_0"
    sig_close = "A_B_D_y_任意_任意_0"
    p = Position("p", "T", [event("open", "开多", [sig_open])], [event("close", "平多", [sig_close])], timeout=3, stop_loss=100)
    now = datetime(2024, 1, 1)
    p.update({"A_B_C": "x_a_b_1"}, 100, now, execution_price=101)
    assert p.pos == 1 and p.cost == 101
    p.update({}, 102, now + timedelta(minutes=1))
    assert p.pos == 1
    p.update({}, 99, now + timedelta(minutes=2))
    assert p.pos == 0 and p.pairs[-1]["reason"] == "止损"

    p.update({"A_B_C": "x_a_b_1"}, 100, now + timedelta(minutes=3))
    p.update({}, 100, now + timedelta(minutes=4))
    p.update({}, 100, now + timedelta(minutes=5))
    assert p.pos == 0 and p.pairs[-1]["reason"] == "超时"

    s = Position("s", "T", [event("so", "开空", [sig_open])], [event("sc", "平空", [sig_close])])
    s.update({"A_B_C": "x_a_b_1"}, 100, now)
    assert s.pos == -1
    s.update({"A_B_D": "y_a_b_1"}, 90, now + timedelta(minutes=1))
    assert s.pos == 0 and s.pairs[-1]["pnl_pct"] > 0


def test_trailing_stop_and_interval():
    sig = "A_B_C_x_任意_任意_0"
    p = Position("p", "T", [event("open", "开多", [sig])], timeout=99, trailing_start=100, trailing_drawback_pct=0.5, interval=3600)
    now = datetime(2024, 1, 1)
    p.update({"A_B_C": "x_a_b_1"}, 100, now)
    p.update({}, 102, now + timedelta(minutes=1))
    assert p.trailing_active
    p.update({}, 101, now + timedelta(minutes=2))
    assert p.pos == 0 and p.pairs[-1]["reason"] == "移动止损"
    p.update({"A_B_C": "x_a_b_1"}, 100, now + timedelta(minutes=10))
    assert p.pos == 0


def test_position_direct_construction_uses_config_trailing_defaults():
    """A93/M5: directly-constructed Position() (no create_* factory) must not
    silently use orphan defaults (150/0.4); None-sentinel defaults resolve
    from STRATEGY_CONFIG like commission_rate/slippage already do."""
    sig = "A_B_C_x_任意_任意_0"
    original = dict(STRATEGY_CONFIG)
    try:
        # Defaults resolve from STRATEGY_CONFIG when omitted.
        STRATEGY_CONFIG["trailing_start_bp"] = 300
        STRATEGY_CONFIG["trailing_drawback_pct"] = 0.25
        p = Position("p", "T", [event("open", "开多", [sig])])
        assert p.trailing_start == STRATEGY_CONFIG["trailing_start_bp"] == 300
        assert p.trailing_drawback_pct == STRATEGY_CONFIG["trailing_drawback_pct"] == 0.25

        # None-sentinel explicitly passed also resolves from config (and tracks it).
        STRATEGY_CONFIG["trailing_start_bp"] = 450
        STRATEGY_CONFIG["trailing_drawback_pct"] = 0.35
        q = Position("q", "T", [event("open", "开多", [sig])],
                     trailing_start=None, trailing_drawback_pct=None)
        assert q.trailing_start == STRATEGY_CONFIG["trailing_start_bp"] == 450
        assert q.trailing_drawback_pct == STRATEGY_CONFIG["trailing_drawback_pct"] == 0.35

        # Explicit overrides still win over config (test/override path preserved).
        r = Position("r", "T", [event("open", "开多", [sig])],
                     trailing_start=100, trailing_drawback_pct=0.5)
        assert r.trailing_start == 100
        assert r.trailing_drawback_pct == 0.5
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def test_normalize_exit_reason_codes():
    assert normalize_exit_reason("姝㈡崯") == "stop_loss"
    assert normalize_exit_reason("瓒呮椂") == "timeout"
    assert normalize_exit_reason("绉诲姩姝㈡崯") == "trailing_stop"
    assert normalize_exit_reason("信号平仓-方向反转") == "signal_exit"
    assert normalize_exit_reason("结构风控") == "risk_exit"
    assert normalize_exit_reason("其他") == "other"
    assert normalize_exit_reason("") == "unknown"


def test_enable_short_controls_position_count():
    long_only = ChanTimingStrategy("TEST", enable_daily_filter=False, enable_short=False)
    with_short = ChanTimingStrategy("TEST", enable_daily_filter=False, enable_short=True)

    assert [p.name for p in long_only.positions] == ["一买多头", "二买多头", "三买多头"]
    assert [p.name for p in with_short.positions] == [
        "一买多头", "二买多头", "三买多头",
        "一卖空头", "二卖空头", "三卖空头",
    ]



def test_enable_short_symbols_limit_config():
    original = dict(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG["enable_short"] = True
        STRATEGY_CONFIG["enable_short_symbols"] = ["RB888", "SC888"]

        rb = ChanTimingStrategy("rb888.SHFE", enable_daily_filter=False)
        ap = ChanTimingStrategy("AP888", enable_daily_filter=False)
        forced = ChanTimingStrategy("AP888", enable_daily_filter=False, enable_short=True)

        assert rb.enable_short is True
        assert len(rb.positions) == 6
        assert ap.enable_short is False
        assert len(ap.positions) == 3
        assert forced.enable_short is True
        assert len(forced.positions) == 6

        STRATEGY_CONFIG["enable_short_symbols"] = None
        all_enabled = ChanTimingStrategy("AP888", enable_daily_filter=False)
        assert all_enabled.enable_short is True
        assert len(all_enabled.positions) == 6
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)

def test_research_symbol_key_and_trailing_params():
    original = dict(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG["trailing_start_bp"] = 300
        STRATEGY_CONFIG["trailing_drawback_pct"] = 0.25
        STRATEGY_CONFIG.pop("trailing_overrides", None)

        assert _research_symbol_key("rb888.SHFE") == "RB888"
        assert _research_symbol_key("") == ""
        assert _research_trailing_params("RB888") == (300, 0.25)

        STRATEGY_CONFIG["trailing_overrides"] = {
            "RB888": (150, 0.15),
            "SC888": {"trailing_start_bp": 200, "trailing_drawback_pct": 0.2},
            "A888": [1],
        }
        assert _research_trailing_params("rb888") == (150, 0.15)
        assert _research_trailing_params("SC888") == (200, 0.2)
        assert _research_trailing_params("A888") == (300, 0.25)

        pos = create_first_buy_position("RB888", enable_daily_filter=False)
        assert pos.trailing_start == 150
        assert pos.trailing_drawback_pct == 0.15
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def test_research_second_buy_allowed_config():
    original = dict(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG.pop("enable_2buy_symbols", None)
        STRATEGY_CONFIG.pop("max_2buy_entry_vs_anchor_pct", None)
        assert _research_second_buy_allowed("RB888", None, None)

        STRATEGY_CONFIG["enable_2buy_symbols"] = ["AP888"]
        assert not _research_second_buy_allowed("RB888", {"price": 100}, 101)
        assert _research_second_buy_allowed("AP888", {"price": 100}, 101)

        STRATEGY_CONFIG["max_2buy_entry_vs_anchor_pct"] = 0.03
        assert _research_second_buy_allowed("AP888", {"price": 100}, 103)
        assert not _research_second_buy_allowed("AP888", {"price": 100}, 104)
        assert _research_second_buy_allowed("AP888", {}, 104)
        assert _research_second_buy_allowed("AP888", {"price": 100}, None)
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def test_strategy_update_second_buy_research_gates():
    class DummyPosition:
        def __init__(self, pos=0, pairs=None):
            self.pos = pos
            self.pairs = list(pairs or [])
            self.calls = []

        def update(self, signals, price, dt, execution_price=None,
                   bar_high=None, bar_low=None, equity_at_entry=None,
                   total_open_margin=None, atr=None, rollover_open_blocked=False):
            self.calls.append((signals, price, dt, execution_price))

    original = dict(STRATEGY_CONFIG)
    try:
        dt = datetime(2024, 1, 1)
        signals = {"k": "v"}

        strategy = ChanTimingStrategy("RB888", enable_daily_filter=False, enable_short=False)
        buy1 = DummyPosition()
        buy2 = DummyPosition()
        buy3 = DummyPosition()
        strategy._positions = [buy1, buy2, buy3]
        strategy.update(signals, 100, dt, execution_price=101)
        assert buy2.calls[-1][0] == {}

        STRATEGY_CONFIG["enable_2buy_symbols"] = ["AP888"]
        strategy.buy1_history.append({"price": 100})
        strategy._last_buy1_anchor = {"price": 100}
        strategy.update(signals, 100, dt, execution_price=101)
        assert buy2.calls[-1][0] == {}

        buy2.pos = 1
        strategy.update(signals, 100, dt, execution_price=101)
        assert buy2.calls[-1][0] == signals
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def test_sell_positions_use_short_operates_and_mirrored_exit_filters():
    positions = [
        create_first_sell_position("TEST", enable_daily_filter=False),
        create_second_sell_position("TEST", enable_daily_filter=False),
        create_third_sell_position("TEST", enable_daily_filter=False),
    ]

    assert all(pos.opens[0].operate == Operate.SO for pos in positions)
    assert all(pos.exits[0].operate == Operate.SC for pos in positions)

    first_exit_values = [s.value for s in positions[0].exits[0].factors[0].signals_any]
    assert any("中枢上方" in value for value in first_exit_values)
    assert any("中枢内" in value for value in first_exit_values)
    assert not any("中枢下方" in value for value in first_exit_values)
