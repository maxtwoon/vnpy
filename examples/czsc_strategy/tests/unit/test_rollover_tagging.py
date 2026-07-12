"""A52 — Rollover-window tagging ``on`` unit and equivalence tests.

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from chan_strategy import backtest_engine as backtest_module
from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


def _make_rollover_db(
    tmp_path: Path,
    symbol: str = "AP888",
    start: datetime = datetime(2024, 1, 2, 9, 0),
    days: int = 25,
    transition_offset: int = 14,
) -> Path:
    """Create a tiny SQLite DB with a single rollover transition.

    The synthetic 1M rows are only used for transition detection and trading-date
    enumeration; the actual backtest bars are supplied in-memory by the
    ``synthetic_1m_bars`` fixture.
    """
    db = tmp_path / "rollover.db"
    conn = sqlite3.connect(db)
    conn.execute(
        f"CREATE TABLE {symbol.lower()}_1M_raw ("
        "datetime TEXT, symbol TEXT, open REAL, high REAL, low REAL, "
        "close REAL, volume REAL, amount REAL, real_symbol TEXT)"
    )
    rows = []
    for d in range(days):
        day = start + timedelta(days=d)
        real_symbol = (
            f"{symbol[:2].upper()}2401" if d < transition_offset else f"{symbol[:2].upper()}2405"
        )
        rows.append(
            (
                day.strftime("%Y-%m-%d %H:%M:%S"),
                symbol,
                100.0,
                101.0,
                99.0,
                100.0,
                1000.0,
                100000.0,
                real_symbol,
            )
        )
    conn.executemany(f"INSERT INTO {symbol.lower()}_1M_raw VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return db


def _make_mock_signals(open_at_call: int = 16, close_at_call: int = 18):
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


def _run_symbol(monkeypatch, bars, db_path: Path, mode: str, open_at: int = 16, close_at: int = 18) -> list[dict]:
    STRATEGY_CONFIG["rollover_stat_tagging"] = mode
    engine = BacktestEngine(
        symbol="AP888",
        db_path=str(db_path),
        start_date="2024-01-02",
        end_date="2024-01-26",
    )
    engine.load_data = lambda: setattr(engine, "bars", bars) or True
    monkeypatch.setattr(backtest_module, "get_all_signals", _make_mock_signals(open_at, close_at))
    report = engine.run(warmup_bars=100)
    if "error" in report:
        pytest.skip(f"AP888: {report['error']}")
    return engine.strategy.get_combined_trades()


def test_on_tags_trade_inside_rollover_window(synthetic_1m_bars, monkeypatch, tmp_path):
    """A trade whose open/close falls in the exclusion window is tagged True."""
    bars = synthetic_1m_bars(days=25, per_day=240, start=datetime(2024, 1, 2, 9, 0))
    db = _make_rollover_db(tmp_path, transition_offset=14)

    pairs = _run_symbol(monkeypatch, bars, db, "on", open_at=16, close_at=18)
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["is_rollover_window"] is True
    assert pair["open_dt"].date() == date(2024, 1, 16)
    assert pair["close_dt"].date() == date(2024, 1, 16)


def test_on_does_not_tag_trade_outside_rollover_window(synthetic_1m_bars, monkeypatch, tmp_path):
    """A trade whose open/close are outside the exclusion window is tagged False."""
    bars = synthetic_1m_bars(days=25, per_day=240, start=datetime(2024, 1, 2, 9, 0))
    db = _make_rollover_db(tmp_path, transition_offset=14)

    # open_at=2/close_at=3 executes around bar 102/103, which is 2024-01-14 —
    # before the Jan 15-17 exclusion window.
    pairs = _run_symbol(monkeypatch, bars, db, "on", open_at=2, close_at=3)
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["is_rollover_window"] is False
    assert pair["open_dt"].date() == date(2024, 1, 14)
    assert pair["close_dt"].date() == date(2024, 1, 14)


def test_on_does_not_change_trade_prices_or_count(synthetic_1m_bars, monkeypatch, tmp_path):
    """``on`` only adds tags; prices, counts and dates stay identical to ``off``."""
    bars = synthetic_1m_bars(days=25, per_day=240, start=datetime(2024, 1, 2, 9, 0))
    db = _make_rollover_db(tmp_path, transition_offset=14)

    off_pairs = _run_symbol(monkeypatch, bars, db, "off", open_at=16, close_at=18)
    on_pairs = _run_symbol(monkeypatch, bars, db, "on", open_at=16, close_at=18)

    assert len(off_pairs) == len(on_pairs)
    assert len(on_pairs) > 0

    for off_p, on_p in zip(off_pairs, on_pairs, strict=True):
        assert on_p["open_dt"] == off_p["open_dt"]
        assert on_p["close_dt"] == off_p["close_dt"]
        assert on_p["open_price"] == off_p["open_price"]
        assert on_p["close_price"] == off_p["close_price"]
        assert "is_rollover_window" in on_p
        assert "is_rollover_window" not in off_p

    numeric_keys = ["open_price", "close_price", "pnl_pct", "pnl_currency",
                    "volume", "contract_multiplier", "bars_held"]
    for off_p, on_p in zip(off_pairs, on_pairs, strict=True):
        for key in numeric_keys:
            assert on_p[key] == off_p[key], f"{key} differs between off and on"


def test_off_does_not_add_rollover_tag_field(synthetic_1m_bars, monkeypatch, tmp_path):
    """``off`` keeps ``pairs`` entries free of the rollover tag key."""
    bars = synthetic_1m_bars(days=25, per_day=240, start=datetime(2024, 1, 2, 9, 0))
    db = _make_rollover_db(tmp_path, transition_offset=14)

    pairs = _run_symbol(monkeypatch, bars, db, "off", open_at=16, close_at=18)
    assert len(pairs) == 1
    assert "is_rollover_window" not in pairs[0]
