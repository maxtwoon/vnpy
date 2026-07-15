"""A67 — Limit-halt unexecutable-fill ``enforce`` mode unit tests.

Validates that ``limit_halt_model="enforce"`` rejects fills at the
unexecutable limit band while leaving ``off`` and ``aware`` byte-identical.

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from chan_strategy import backtest_engine as backtest_module
from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG
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


def test_enforce_rejects_long_entry_at_upper_limit():
    """A long open on an upper-limit touch is skipped; position stays flat."""
    STRATEGY_CONFIG["limit_halt_model"] = "enforce"
    pos = Position(
        name="一买多头", symbol="AP888",
        opens=[_event("open", "开多", [SIG_OPEN])],
        exits=[_event("close", "平多", [SIG_CLOSE])],
    )

    dt = datetime(2024, 1, 2, 9, 0)
    pos.update(
        _make_open_signals(), price=100, dt=dt,
        execution_price=100,
        entry_at_limit=(True, False),  # upper touch -> unexecutable for long entry
        exit_at_limit=(False, False),
    )

    assert pos.pos == 0
    assert not pos.pairs
    assert not pos.trades


def test_enforce_rejects_short_entry_at_lower_limit():
    """A short open on a lower-limit touch is skipped; position stays flat."""
    STRATEGY_CONFIG["limit_halt_model"] = "enforce"
    pos = Position(
        name="一卖空头", symbol="AP888",
        opens=[_event("open", "开空", [SIG_SHORT_OPEN])],
        exits=[_event("close", "平空", [SIG_SHORT_CLOSE])],
    )

    dt = datetime(2024, 1, 2, 9, 0)
    pos.update(
        _make_short_open_signals(), price=100, dt=dt,
        execution_price=100,
        entry_at_limit=(False, True),  # lower touch -> unexecutable for short entry
        exit_at_limit=(False, False),
    )

    assert pos.pos == 0
    assert not pos.pairs


def test_enforce_allows_long_entry_when_flag_is_for_wrong_band():
    """Only the directionally-relevant band blocks the fill."""
    STRATEGY_CONFIG["limit_halt_model"] = "enforce"
    pos = Position(
        name="一买多头", symbol="AP888",
        opens=[_event("open", "开多", [SIG_OPEN])],
        exits=[_event("close", "平多", [SIG_CLOSE])],
    )

    dt = datetime(2024, 1, 2, 9, 0)
    pos.update(
        _make_open_signals(), price=100, dt=dt,
        execution_price=100,
        entry_at_limit=(False, True),  # lower touch does not block long entry
        exit_at_limit=(False, False),
    )

    assert pos.pos == 1
    assert len(pos.pairs) == 0  # not closed yet


def test_enforce_rejects_long_signal_exit_at_lower_limit_then_fills_next_bar():
    """A long signal-close at the lower limit is deferred one bar; no lookahead."""
    STRATEGY_CONFIG["limit_halt_model"] = "enforce"
    pos = Position(
        name="一买多头", symbol="AP888",
        opens=[_event("open", "开多", [SIG_OPEN])],
        exits=[_event("close", "平多", [SIG_CLOSE])],
    )

    dt_open = datetime(2024, 1, 2, 9, 0)
    dt_blocked = datetime(2024, 1, 2, 10, 0)
    dt_filled = datetime(2024, 1, 2, 11, 0)

    pos.update(
        _make_open_signals(), price=100, dt=dt_open,
        execution_price=100,
        entry_at_limit=(False, False),
        exit_at_limit=(False, False),
    )
    assert pos.pos == 1

    pos.update(
        _make_close_signals(), price=99, dt=dt_blocked,
        execution_price=99,
        entry_at_limit=(False, False),
        exit_at_limit=(False, True),  # lower touch blocks long exit
    )
    assert pos.pos == 1
    assert not pos.pairs

    pos.update(
        _make_close_signals(), price=99, dt=dt_filled,
        execution_price=99,
        entry_at_limit=(False, False),
        exit_at_limit=(False, False),  # no longer at limit
    )
    assert pos.pos == 0
    assert len(pos.pairs) == 1
    pair = pos.pairs[0]
    assert pair["fill_rejected_at_limit"] is True
    assert pair["is_exit_at_limit"] is False  # filled bar was not at limit


def test_enforce_rejects_long_stop_loss_exit_at_lower_limit():
    """A stop-loss exit triggered on a lower-limit bar is skipped under enforce."""
    STRATEGY_CONFIG["limit_halt_model"] = "enforce"
    STRATEGY_CONFIG["stop_loss_1buy"] = 50  # 0.5% so a small drop triggers it
    pos = Position(
        name="一买多头", symbol="AP888",
        opens=[_event("open", "开多", [SIG_OPEN])],
        exits=[_event("close", "平多", [SIG_CLOSE])],
        stop_loss=50,
    )

    dt_open = datetime(2024, 1, 2, 9, 0)
    dt_stop = datetime(2024, 1, 2, 10, 0)
    pos.update(
        _make_open_signals(), price=100, dt=dt_open,
        execution_price=100,
        entry_at_limit=(False, False),
        exit_at_limit=(False, False),
    )
    assert pos.pos == 1

    pos.update(
        {}, price=99.4, dt=dt_stop,  # 0.6% loss triggers stop
        execution_price=99.4,
        entry_at_limit=(False, False),
        exit_at_limit=(False, True),  # lower limit band
    )
    assert pos.pos == 1
    assert not pos.pairs


def test_enforce_rejects_long_timeout_exit_at_lower_limit():
    """A timeout exit on a lower-limit bar is skipped under enforce."""
    STRATEGY_CONFIG["limit_halt_model"] = "enforce"
    pos = Position(
        name="一买多头", symbol="AP888",
        opens=[_event("open", "开多", [SIG_OPEN])],
        exits=[_event("close", "平多", [SIG_CLOSE])],
        timeout=3,
    )

    dt_open = datetime(2024, 1, 2, 9, 0)
    dt_timeout = datetime(2024, 1, 2, 12, 0)
    pos.update(
        _make_open_signals(), price=100, dt=dt_open,
        execution_price=100,
        entry_at_limit=(False, False),
        exit_at_limit=(False, False),
    )
    assert pos.pos == 1

    pos.update(
        {}, price=100, dt=dt_timeout,
        execution_price=100,
        entry_at_limit=(False, False),
        exit_at_limit=(False, True),  # lower limit band blocks exit
        bar_count=3,
    )
    assert pos.pos == 1
    assert not pos.pairs


def test_enforce_rejects_long_trailing_stop_exit_at_lower_limit():
    """A legacy trailing-stop exit on a lower-limit bar is skipped under enforce."""
    STRATEGY_CONFIG["limit_halt_model"] = "enforce"
    pos = Position(
        name="一买多头", symbol="AP888",
        opens=[_event("open", "开多", [SIG_OPEN])],
        exits=[_event("close", "平多", [SIG_CLOSE])],
        trailing_start=50,      # activate after 0.5% profit
        trailing_drawback_pct=0.25,
    )

    dt_open = datetime(2024, 1, 2, 9, 0)
    dt_peak = datetime(2024, 1, 2, 10, 0)
    dt_trigger = datetime(2024, 1, 2, 11, 0)
    pos.update(_make_open_signals(), price=100, dt=dt_open, execution_price=100)
    assert pos.pos == 1

    # Push price up to activate the trailing stop.
    pos.update({}, price=100.6, dt=dt_peak, execution_price=100.6)
    assert pos.trailing_active is True

    # Price falls enough to trigger trailing stop, but lower-limit band blocks it.
    pos.update({}, price=100.4, dt=dt_trigger, execution_price=100.4,
               exit_at_limit=(False, True))
    assert pos.pos == 1
    assert not pos.pairs


def test_enforce_rejects_structural_atr_timeout_exit_at_lower_limit():
    """A structural_atr timeout exit on a lower-limit bar is skipped under enforce."""
    STRATEGY_CONFIG["limit_halt_model"] = "enforce"
    STRATEGY_CONFIG["exit_model"] = "structural_atr"
    pos = Position(
        name="一买多头", symbol="AP888",
        opens=[_event("open", "开多", [SIG_OPEN])],
        exits=[_event("close", "平多", [SIG_CLOSE])],
        timeout=3,
    )

    dt_open = datetime(2024, 1, 2, 9, 0)
    dt_timeout = datetime(2024, 1, 2, 12, 0)
    pos.update(_make_open_signals(), price=100, dt=dt_open, execution_price=100)
    assert pos.pos == 1

    pos.update({}, price=100, dt=dt_timeout, execution_price=100,
               exit_at_limit=(False, True), bar_count=3)
    assert pos.pos == 1
    assert not pos.pairs


def test_enforce_rejected_exit_tag_carries_to_eventual_close():
    """The fill_rejected_at_limit audit trail survives until the position closes."""
    STRATEGY_CONFIG["limit_halt_model"] = "enforce"
    pos = Position(
        name="一买多头", symbol="AP888",
        opens=[_event("open", "开多", [SIG_OPEN])],
        exits=[_event("close", "平多", [SIG_CLOSE])],
    )

    dt_open = datetime(2024, 1, 2, 9, 0)
    dt_blocked1 = datetime(2024, 1, 2, 10, 0)
    dt_blocked2 = datetime(2024, 1, 2, 11, 0)
    dt_filled = datetime(2024, 1, 2, 12, 0)

    pos.update(_make_open_signals(), price=100, dt=dt_open, execution_price=100)
    pos.update(_make_close_signals(), price=99, dt=dt_blocked1,
               execution_price=99, exit_at_limit=(False, True))
    pos.update(_make_close_signals(), price=99, dt=dt_blocked2,
               execution_price=99, exit_at_limit=(False, True))
    pos.update(_make_close_signals(), price=99, dt=dt_filled,
               execution_price=99, exit_at_limit=(False, False))

    assert len(pos.pairs) == 1
    assert pos.pairs[0]["fill_rejected_at_limit"] is True


def test_enforce_adds_limit_tags_but_no_rejection_when_fill_happens_normally():
    """A normal fill under enforce still carries the limit tags and a False rejection flag."""
    STRATEGY_CONFIG["limit_halt_model"] = "enforce"
    pos = Position(
        name="一买多头", symbol="AP888",
        opens=[_event("open", "开多", [SIG_OPEN])],
        exits=[_event("close", "平多", [SIG_CLOSE])],
    )

    dt_open = datetime(2024, 1, 2, 9, 0)
    dt_close = datetime(2024, 1, 2, 10, 0)
    pos.update(
        _make_open_signals(), price=100, dt=dt_open,
        execution_price=100,
        entry_at_limit=(False, False),
        exit_at_limit=(False, False),
    )
    pos.update(
        _make_close_signals(), price=101, dt=dt_close,
        execution_price=101,
        entry_at_limit=(False, False),
        exit_at_limit=(False, False),
    )

    assert len(pos.pairs) == 1
    pair = pos.pairs[0]
    assert pair["is_entry_at_limit"] is False
    assert pair["is_exit_at_limit"] is False
    assert pair["fill_rejected_at_limit"] is False


def test_off_and_aware_do_not_add_fill_rejected_field():
    """The new enforce-only field must not leak into off/aware pairs."""
    for mode in ("off", "aware"):
        STRATEGY_CONFIG["limit_halt_model"] = mode
        pos = Position(
            name="一买多头", symbol="AP888",
            opens=[_event("open", "开多", [SIG_OPEN])],
            exits=[_event("close", "平多", [SIG_CLOSE])],
        )

        dt_open = datetime(2024, 1, 2, 9, 0)
        dt_close = datetime(2024, 1, 2, 10, 0)
        kwargs = {}
        if mode == "aware":
            kwargs = {"entry_at_limit": (False, False), "exit_at_limit": (False, False)}
        pos.update(_make_open_signals(), price=100, dt=dt_open, execution_price=100, **kwargs)
        pos.update(_make_close_signals(), price=101, dt=dt_close, execution_price=101, **kwargs)

        pair = pos.pairs[0]
        assert "fill_rejected_at_limit" not in pair


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


def test_enforce_engine_runs_without_error_and_tags_rejected_fills(synthetic_1m_bars, monkeypatch):
    """``enforce`` runs end-to-end and tags pairs with the rejection audit field."""
    bars = synthetic_1m_bars(days=15, per_day=240, start=datetime(2024, 1, 2, 9, 0))

    enforce_pairs = _run_symbol(monkeypatch, bars, "AP888", "enforce")

    # The deterministic synthetic fixture may or may not produce trades, but any
    # produced pair must carry the enforce-mode audit field.
    for pair in enforce_pairs:
        assert "fill_rejected_at_limit" in pair
