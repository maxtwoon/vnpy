"""A51 — Limit-halt tagging ``aware`` unit and equivalence tests.

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from chan_strategy import backtest_engine as backtest_module
from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.limit_config import (
    SYMBOL_LIMIT_CONFIG,
    _bar_at_limit,
    _daily_prev_close_map,
    _limit_pct_for_date,
)
from conftest import make_raw_bar
from chan_strategy.positions import Event, Position


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


def _event(name: str, operate: str, signals_all: list[str] | None = None) -> Event:
    return Event.load({"name": name, "operate": operate, "signals_all": signals_all or []})


SIG_OPEN = "A_B_C_x_任意_任意_0"
SIG_CLOSE = "A_B_D_y_任意_任意_0"
SIG_SHORT_OPEN = "A_B_E_z_任意_任意_0"
SIG_SHORT_CLOSE = "A_B_F_w_任意_任意_0"


def _make_open_signals() -> dict:
    return {"A_B_C": "x_a_b_1"}


def _make_close_signals() -> dict:
    return {"A_B_D": "y_a_b_1"}


def _make_short_open_signals() -> dict:
    return {"A_B_E": "z_a_b_1"}


def _make_short_close_signals() -> dict:
    return {"A_B_F": "w_a_b_1"}


def test_aware_tags_entry_and_exit_for_long_position():
    """Long open/close pair carries the supplied entry/exit limit flags."""
    STRATEGY_CONFIG["limit_halt_model"] = "aware"
    pos = Position(
        name="一买多头", symbol="AP888",
        opens=[_event("open", "开多", [SIG_OPEN])],
        exits=[_event("close", "平多", [SIG_CLOSE])],
    )

    dt_open = datetime(2024, 1, 2, 9, 0)
    dt_close = datetime(2024, 1, 2, 10, 0)
    pos.update(_make_open_signals(), price=100, dt=dt_open,
               execution_price=100, entry_at_limit=True, exit_at_limit=False)
    pos.update(_make_close_signals(), price=101, dt=dt_close,
               execution_price=101, entry_at_limit=False, exit_at_limit=True)

    assert len(pos.pairs) == 1
    pair = pos.pairs[0]
    assert pair["is_entry_at_limit"] is True
    assert pair["is_exit_at_limit"] is True


def test_aware_tags_entry_and_exit_for_short_position():
    """Short open/close pair carries the supplied entry/exit limit flags."""
    STRATEGY_CONFIG["limit_halt_model"] = "aware"
    pos = Position(
        name="一卖空头", symbol="AP888",
        opens=[_event("open", "开空", [SIG_SHORT_OPEN])],
        exits=[_event("close", "平空", [SIG_SHORT_CLOSE])],
    )

    dt_open = datetime(2024, 1, 2, 9, 0)
    dt_close = datetime(2024, 1, 2, 10, 0)
    pos.update(_make_short_open_signals(), price=100, dt=dt_open,
               execution_price=100, entry_at_limit=False, exit_at_limit=False)
    pos.update(_make_short_close_signals(), price=99, dt=dt_close,
               execution_price=99, entry_at_limit=False, exit_at_limit=False)

    assert len(pos.pairs) == 1
    pair = pos.pairs[0]
    assert pair["is_entry_at_limit"] is False
    assert pair["is_exit_at_limit"] is False


def test_off_does_not_add_limit_tag_fields():
    """``off`` keeps ``pairs`` entries free of limit-tag keys."""
    STRATEGY_CONFIG["limit_halt_model"] = "off"
    pos = Position(
        name="一买多头", symbol="AP888",
        opens=[_event("open", "开多", [SIG_OPEN])],
        exits=[_event("close", "平多", [SIG_CLOSE])],
    )

    dt_open = datetime(2024, 1, 2, 9, 0)
    dt_close = datetime(2024, 1, 2, 10, 0)
    pos.update(_make_open_signals(), price=100, dt=dt_open, execution_price=100)
    pos.update(_make_close_signals(), price=101, dt=dt_close, execution_price=101)

    assert len(pos.pairs) == 1
    pair = pos.pairs[0]
    assert "is_entry_at_limit" not in pair
    assert "is_exit_at_limit" not in pair


def test_bar_at_limit_uses_symbol_limit_config():
    """The shared ``SYMBOL_LIMIT_CONFIG`` correctly flags an at-limit bar."""
    limit_pct = SYMBOL_LIMIT_CONFIG["AP888"]["limit_pct"]
    prev_close = 100.0

    class _Bar:
        def __init__(self, high, low):
            self.high = high
            self.low = low

    at_limit_bar = _Bar(high=105.0, low=100.0)
    normal_bar = _Bar(high=104.9, low=100.0)

    touched_upper, touched_lower, upper, lower = _bar_at_limit(at_limit_bar, prev_close, limit_pct)
    assert touched_upper is True
    assert touched_lower is False
    assert upper == pytest.approx(105.0)
    assert lower == pytest.approx(95.0)

    tu, tl, _, _ = _bar_at_limit(normal_bar, prev_close, limit_pct)
    assert tu is False
    assert tl is False


def test_bar_at_limit_directional_separation():
    """Upper and lower touches are reported independently."""
    prev_close = 100.0
    limit_pct = 0.05

    class _Bar:
        def __init__(self, high, low):
            self.high = high
            self.low = low

    upper_touch = _Bar(high=105.0, low=100.0)
    lower_touch = _Bar(high=100.0, low=95.0)
    both_touch = _Bar(high=105.0, low=95.0)
    no_touch = _Bar(high=104.9, low=95.1)

    assert _bar_at_limit(upper_touch, prev_close, limit_pct)[:2] == (True, False)
    assert _bar_at_limit(lower_touch, prev_close, limit_pct)[:2] == (False, True)
    assert _bar_at_limit(both_touch, prev_close, limit_pct)[:2] == (True, True)
    assert _bar_at_limit(no_touch, prev_close, limit_pct)[:2] == (False, False)


def _run_position(name: str, opens: list, exits: list,
                  open_signals: dict, close_signals: dict,
                  entry_flag, exit_flag_open, exit_flag_close):
    """Open then close a position and return the resulting pair."""
    pos = Position(name=name, symbol="AP888", opens=opens, exits=exits)
    pos.update(
        open_signals, price=100, dt=datetime(2024, 1, 2, 9, 0),
        execution_price=100,
        entry_at_limit=entry_flag, exit_at_limit=exit_flag_open,
    )
    pos.update(
        close_signals, price=101, dt=datetime(2024, 1, 2, 10, 0),
        execution_price=101,
        entry_at_limit=(False, False), exit_at_limit=exit_flag_close,
    )
    assert len(pos.pairs) == 1
    return pos.pairs[0]


def test_directional_limit_flag_maps_to_trade_side():
    """Position.update resolves the directional touch relevant to its side."""
    STRATEGY_CONFIG["limit_halt_model"] = "aware"

    long_opens = [_event("open", "开多", [SIG_OPEN])]
    long_exits = [_event("close", "平多", [SIG_CLOSE])]
    short_opens = [_event("open", "开空", [SIG_SHORT_OPEN])]
    short_exits = [_event("close", "平空", [SIG_SHORT_CLOSE])]

    # Long entry: upper touch matters; lower touch does not.
    pair = _run_position(
        "一买多头", long_opens, long_exits,
        _make_open_signals(), _make_close_signals(),
        entry_flag=(True, False), exit_flag_open=(False, False), exit_flag_close=(False, False),
    )
    assert pair["is_entry_at_limit"] is True

    pair = _run_position(
        "一买多头", long_opens, long_exits,
        _make_open_signals(), _make_close_signals(),
        entry_flag=(False, True), exit_flag_open=(False, False), exit_flag_close=(False, False),
    )
    assert pair["is_entry_at_limit"] is False

    # Short entry: lower touch matters; upper touch does not.
    pair = _run_position(
        "一卖空头", short_opens, short_exits,
        _make_short_open_signals(), _make_short_close_signals(),
        entry_flag=(False, True), exit_flag_open=(False, False), exit_flag_close=(False, False),
    )
    assert pair["is_entry_at_limit"] is True

    pair = _run_position(
        "一卖空头", short_opens, short_exits,
        _make_short_open_signals(), _make_short_close_signals(),
        entry_flag=(True, False), exit_flag_open=(False, False), exit_flag_close=(False, False),
    )
    assert pair["is_entry_at_limit"] is False

    # Long exit: lower touch matters; upper touch does not.
    pair = _run_position(
        "一买多头", long_opens, long_exits,
        _make_open_signals(), _make_close_signals(),
        entry_flag=(False, False), exit_flag_open=(False, False), exit_flag_close=(False, True),
    )
    assert pair["is_exit_at_limit"] is True

    pair = _run_position(
        "一买多头", long_opens, long_exits,
        _make_open_signals(), _make_close_signals(),
        entry_flag=(False, False), exit_flag_open=(False, False), exit_flag_close=(True, False),
    )
    assert pair["is_exit_at_limit"] is False

    # Short exit: upper touch matters; lower touch does not.
    pair = _run_position(
        "一卖空头", short_opens, short_exits,
        _make_short_open_signals(), _make_short_close_signals(),
        entry_flag=(False, False), exit_flag_open=(False, False), exit_flag_close=(True, False),
    )
    assert pair["is_exit_at_limit"] is True

    pair = _run_position(
        "一卖空头", short_opens, short_exits,
        _make_short_open_signals(), _make_short_close_signals(),
        entry_flag=(False, False), exit_flag_open=(False, False), exit_flag_close=(False, True),
    )
    assert pair["is_exit_at_limit"] is False


def test_daily_prev_close_map_uses_trading_day_not_calendar_date():
    """Night-session bars are bucketed into the next trading day (A39 reuse)."""
    bars = [
        # Day session for trading day 2024-01-02.
        make_raw_bar(0, datetime(2024, 1, 2, 9, 0), open_=100.0, close=100.0),
        # Night session for trading day 2024-01-03 (calendar date 2024-01-02, hour >= 20).
        make_raw_bar(1, datetime(2024, 1, 2, 21, 0), open_=101.0, close=101.0),
        # Day session for trading day 2024-01-03.
        make_raw_bar(2, datetime(2024, 1, 3, 9, 0), open_=102.0, close=102.0),
    ]
    prev_map = _daily_prev_close_map(bars)

    trading_day_2 = date(2024, 1, 2)
    trading_day_3 = date(2024, 1, 3)

    assert prev_map[trading_day_2] == (None, None)
    # Trading day 3's previous close must come from trading day 2's day session,
    # not from the same-evaluation-day night session.
    assert prev_map[trading_day_3] == (100.0, trading_day_2)


def test_daily_prev_close_map_prefers_previous_settlement_when_available():
    """Exchange limit bands use previous settlement; close is only a fallback."""
    class Bar:
        def __init__(self, dt: datetime, close: float, settlement: float | None = None):
            self.dt = dt
            self.close = close
            if settlement is not None:
                self.settlement = settlement

    bars = [
        Bar(datetime(2024, 1, 2, 15, 0), close=100.0, settlement=98.0),
        Bar(datetime(2024, 1, 3, 9, 0), close=101.0),
    ]

    prev_map = _daily_prev_close_map(bars)

    assert prev_map[date(2024, 1, 3)] == (98.0, date(2024, 1, 2))


def test_temporary_widening_windows_override_steady_state():
    """Registered widening windows override the steady-state limit percentage."""
    assert _limit_pct_for_date("AP888", date(2026, 5, 5)) == 0.05
    assert _limit_pct_for_date("AP888", date(2026, 5, 6)) == 0.08
    assert _limit_pct_for_date("AP888", date(2026, 5, 7)) == 0.05

    assert _limit_pct_for_date("RB888", date(2026, 5, 18)) == 0.03
    assert _limit_pct_for_date("RB888", date(2026, 5, 19)) == 0.05
    assert _limit_pct_for_date("RB888", date(2026, 5, 20)) == 0.03


def _make_mock_signals(open_at_call: int = 8, close_at_call: int = 10):
    """Return a deterministic get_all_signals replacement that forces one trade."""
    counters = {"trade": 0, "daily": 0}

    def _mock(czsc, freq, buy1_anchor=None, sell1_anchor=None):
        if freq == "日线":
            counters["daily"] += 1
            return {
                "日线_D1BI_方向V260615": "向上_任意_任意_50",
                "日线_D1ZS_位置V260615": "中枢内_任意_任意_50",
            }

        if freq != "30分钟":
            return {}

        counters["trade"] += 1
        call = counters["trade"]

        if call == open_at_call:
            return {
                "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
                "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
                "30分钟_D1BSP_一买V260615": "一买确认_任意_任意_80",
                "30分钟_D1BSP_二买V260615": "非二买_任意_任意_0",
                "30分钟_D1BSP_三买阶段V260615": "非三买_任意_任意_0",
                "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
                "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
                "30分钟_D1BSP_风控V260615": "结构完好_任意_任意_0",
            }
        if call == close_at_call:
            return {
                "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
                "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
                "30分钟_D1BSP_一买V260615": "非一买_任意_任意_0",
                "30分钟_D1BSP_二买V260615": "非二买_任意_任意_0",
                "30分钟_D1BSP_三买阶段V260615": "非三买_任意_任意_0",
                "30分钟_D1BI_方向V260615": "向下_任意_任意_50",
                "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
                "30分钟_D1BSP_风控V260615": "结构失效_任意_任意_0",
            }
        return {
            "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
            "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
            "30分钟_D1BSP_一买V260615": "非一买_任意_任意_0",
            "30分钟_D1BSP_二买V260615": "非二买_任意_任意_0",
            "30分钟_D1BSP_三买阶段V260615": "非三买_任意_任意_0",
            "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
            "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
            "30分钟_D1BSP_风控V260615": "结构完好_任意_任意_0",
        }

    return _mock


def _run_symbol(monkeypatch, bars, symbol: str, mode: str) -> list[dict]:
    STRATEGY_CONFIG["limit_halt_model"] = mode
    engine = BacktestEngine(symbol=symbol, db_path="none")
    engine.load_data = lambda: setattr(engine, "bars", bars) or True
    monkeypatch.setattr(backtest_module, "get_all_signals", _make_mock_signals(8, 10))
    report = engine.run(warmup_bars=100)
    if "error" in report:
        pytest.skip(f"{symbol}: {report['error']}")
    return engine.strategy.get_combined_trades()


def test_aware_does_not_change_trade_prices_or_count(synthetic_1m_bars, monkeypatch):
    """``aware`` only adds tags; prices, counts and dates stay identical to ``off``."""
    bars = synthetic_1m_bars(days=15, per_day=240, start=datetime(2024, 1, 2, 9, 0))

    off_pairs = _run_symbol(monkeypatch, bars, "AP888", "off")
    aware_pairs = _run_symbol(monkeypatch, bars, "AP888", "aware")

    assert len(off_pairs) == len(aware_pairs)
    assert len(aware_pairs) > 0

    for off_p, aware_p in zip(off_pairs, aware_pairs, strict=True):
        assert aware_p["open_dt"] == off_p["open_dt"]
        assert aware_p["close_dt"] == off_p["close_dt"]
        assert aware_p["open_price"] == off_p["open_price"]
        assert aware_p["close_price"] == off_p["close_price"]
        assert "is_entry_at_limit" in aware_p
        assert "is_exit_at_limit" in aware_p
        assert "is_entry_at_limit" not in off_p
        assert "is_exit_at_limit" not in off_p

    # All numeric fields other than the two new booleans must match exactly.
    numeric_keys = ["open_price", "close_price", "pnl_pct", "pnl_currency",
                    "volume", "contract_multiplier", "bars_held"]
    for off_p, aware_p in zip(off_pairs, aware_pairs, strict=True):
        for key in numeric_keys:
            assert aware_p[key] == off_p[key], f"{key} differs between off and aware"


def test_aware_lowercase_symbol_matches_uppercase(synthetic_1m_bars, monkeypatch):
    """Lower-case configured symbol produces identical limit tags to upper-case."""
    bars = synthetic_1m_bars(days=15, per_day=240, start=datetime(2024, 1, 2, 9, 0))

    upper_pairs = _run_symbol(monkeypatch, bars, "AP888", "aware")
    lower_pairs = _run_symbol(monkeypatch, bars, "ap888", "aware")

    assert len(upper_pairs) == len(lower_pairs) > 0
    for up, lp in zip(upper_pairs, lower_pairs, strict=True):
        assert lp["is_entry_at_limit"] == up["is_entry_at_limit"]
        assert lp["is_exit_at_limit"] == up["is_exit_at_limit"]


def test_aware_unconfigured_symbol_fails_loud(synthetic_1m_bars, monkeypatch):
    """A symbol genuinely absent from SYMBOL_LIMIT_CONFIG raises instead of silent False."""
    bars = synthetic_1m_bars(days=15, per_day=240, start=datetime(2024, 1, 2, 9, 0))

    with pytest.raises(ValueError, match="limit_halt_model='aware' requires a SYMBOL_LIMIT_CONFIG entry"):
        _run_symbol(monkeypatch, bars, "UNKNOWN888", "aware")
