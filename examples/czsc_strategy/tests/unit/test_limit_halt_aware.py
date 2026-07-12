"""A51 — Limit-halt tagging ``aware`` unit and equivalence tests.

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from chan_strategy import backtest_engine as backtest_module
from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.limit_config import SYMBOL_LIMIT_CONFIG, _bar_at_limit
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

    at_limit, upper, lower = _bar_at_limit(at_limit_bar, prev_close, limit_pct)
    assert at_limit is True
    assert upper == pytest.approx(105.0)
    assert lower == pytest.approx(95.0)

    not_at_limit, _, _ = _bar_at_limit(normal_bar, prev_close, limit_pct)
    assert not_at_limit is False


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
