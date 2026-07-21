"""A76 — Rollover-window open gating unit tests.

Validates that ``rollover_open_gating="on"`` blocks new long/short opens on
bars whose trading date falls inside the rollover exclusion window, only
under formal-evaluation mode by default, without affecting exits or
risk-control of already-open positions. Also verifies that a rollover
detection failure fails closed (ValueError) instead of silently degrading
(A97, audit M2 + H2 mitigation).

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from chan_strategy import backtest_engine as backtest_module
from chan_strategy.backtest_engine import BacktestEngine, formal_evaluation_config
from chan_strategy.config import STRATEGY_CONFIG


@pytest.fixture(autouse=True)
def restore_config():
    """Snapshot and restore the whole STRATEGY_CONFIG so tests never leak."""
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
    """Create a tiny SQLite DB with a single rollover transition."""
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


def _run_symbol(
    monkeypatch,
    bars,
    db_path: Path,
    gating: str,
    open_at: int = 16,
    close_at: int = 18,
) -> tuple[list[dict], dict]:
    STRATEGY_CONFIG["rollover_open_gating"] = gating
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
    return engine.strategy.get_combined_trades(), report


# ------------------------------------------------------------------ config / context manager


def test_default_config_has_rollover_open_gating_off():
    assert STRATEGY_CONFIG.get("rollover_open_gating") == "off"


def test_formal_evaluation_config_enables_rollover_open_gating():
    STRATEGY_CONFIG["rollover_open_gating"] = "off"
    with formal_evaluation_config():
        assert STRATEGY_CONFIG["rollover_open_gating"] == "on"
    assert STRATEGY_CONFIG["rollover_open_gating"] == "off"


# ------------------------------------------------------------------ gating behavior


def test_gating_blocks_new_long_open_inside_rollover_window(synthetic_1m_bars, monkeypatch, tmp_path):
    """A new long open scheduled inside the exclusion window is rejected when gating is on."""
    bars = synthetic_1m_bars(days=25, per_day=240, start=datetime(2024, 1, 2, 9, 0))
    db = _make_rollover_db(tmp_path, transition_offset=14)

    pairs, report = _run_symbol(monkeypatch, bars, db, gating="on", open_at=16, close_at=18)

    assert len(pairs) == 0
    assert report["rollover_open_gating"] == "on"
    assert report.get("rollover_open_gating_rejected_opens", {}).get("一买多头", 0) >= 1


def test_gating_allows_new_long_open_in_default_path(synthetic_1m_bars, monkeypatch, tmp_path):
    """The same signal produces a trade when gating is off."""
    bars = synthetic_1m_bars(days=25, per_day=240, start=datetime(2024, 1, 2, 9, 0))
    db = _make_rollover_db(tmp_path, transition_offset=14)

    pairs, report = _run_symbol(monkeypatch, bars, db, gating="off", open_at=16, close_at=18)

    assert len(pairs) == 1
    assert report["rollover_open_gating"] == "off"
    assert "rollover_open_gating_rejected_opens" not in report
    pair = pairs[0]
    assert pair["open_dt"].date() == date(2024, 1, 16)


def test_gating_does_not_affect_exit_of_already_open_position(synthetic_1m_bars, monkeypatch, tmp_path):
    """A position opened before the window closes normally inside the window."""
    bars = synthetic_1m_bars(days=25, per_day=240, start=datetime(2024, 1, 2, 9, 0))
    db = _make_rollover_db(tmp_path, transition_offset=14)

    # Disable fixed stop and trailing stop so the position survives until the
    # injected close signal. The synthetic 30-min bars move several percent per
    # bar, which would otherwise trigger the default 200BP/300BP thresholds.
    STRATEGY_CONFIG["stop_loss_1buy"] = 100000
    STRATEGY_CONFIG["trailing_start_bp"] = 100000

    # open_at=2 -> opens on 2024-01-14 (before the Jan 15-17 exclusion window).
    # close_at=9 -> closes on 2024-01-15 (inside the exclusion window).
    pairs, report = _run_symbol(monkeypatch, bars, db, gating="on", open_at=2, close_at=9)

    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["open_dt"].date() == date(2024, 1, 14)
    assert pair["close_dt"].date() == date(2024, 1, 15)
    assert report.get("rollover_open_gating_rejected_opens", {}).get("一买多头", 0) == 0


# ------------------------------------------------------------------ fail-closed on detection failure


def test_gating_reports_unavailable_when_metadata_missing(synthetic_1m_bars, monkeypatch, tmp_path):
    """A97: if the metadata DB is missing, gating='on' fails closed with ValueError.

    Detection failure must not silently downgrade an explicitly protected run
    into an unprotected one; the caller gets a ValueError naming the failure
    reason and the explicit opt-out (rollover_open_gating='off').
    """
    bars = synthetic_1m_bars(days=25, per_day=240, start=datetime(2024, 1, 2, 9, 0))
    db = tmp_path / "nonexistent.db"

    with pytest.raises(ValueError, match=r"rollover_open_gating='on'.*detection was unavailable"):
        _run_symbol(monkeypatch, bars, db, gating="on", open_at=16, close_at=18)


def test_gating_off_does_not_add_audit_fields(synthetic_1m_bars, monkeypatch, tmp_path):
    """The gating audit fields are absent when the feature is off."""
    bars = synthetic_1m_bars(days=25, per_day=240, start=datetime(2024, 1, 2, 9, 0))
    db = _make_rollover_db(tmp_path, transition_offset=14)

    pairs, report = _run_symbol(monkeypatch, bars, db, gating="off", open_at=16, close_at=18)

    assert len(pairs) == 1
    assert "rollover_open_gating_rejected_opens" not in report
    assert "rollover_open_gating_unavailable" not in report


# ------------------------------------------------------------------ mode label


def test_run_formal_evaluation_mode_label_includes_rollover_gating(monkeypatch):
    """The formal-evaluation mode label names the rollover open-gating dimension."""
    from datetime import datetime as dt

    monkeypatch.setattr(BacktestEngine, "run", lambda self: {"ok": True})
    monkeypatch.setattr(BacktestEngine, "print_report", lambda self, report=None: None)

    engine = BacktestEngine("T", initial_capital=1000)
    engine.bars = []
    engine.equity_curve = [
        {"dt": dt(2024, 1, 1), "equity": 1000, "price": 1, "positions": 0},
    ]

    class FakeStrategy:
        def evaluate_all(self):
            return {"fake": {"total_trades": 0, "win_rate": 0, "profit_factor": 0}}

        def get_combined_trades(self):
            return []

    engine.strategy = FakeStrategy()

    with formal_evaluation_config():
        report = engine.generate_report()

    assert report["sizing_model"] == "risk"
    assert report["limit_halt_model"] == "enforce"
    assert report["rollover_open_gating"] == "on"
    assert report["mode_label"] == (
        "PARTIAL_PRODUCTION_FEATURES(sizing_model=risk,limit_halt_model=enforce,rollover_open_gating=on)"
    )
