"""A80 — Unparseable-row counting in data adapter and backtest report.

Validates that rows whose datetime cannot be parsed are counted (but still
skipped unchanged) and that the count surfaces in ``generate_report()`` for
both the default and formal-evaluation paths.

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from chan_strategy.backtest_engine import BacktestEngine, formal_evaluation_config
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.data_adapter import SqliteDataAdapter


def _build_a80_db(db_path: Path, rows: list[tuple]) -> Path:
    """Create a temporary SQLite db with the standard 1M raw schema."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "create table test_1M_raw ("
        "datetime text, symbol text, open real, high real, low real, "
        "close real, volume real, amount real)"
    )
    conn.executemany("insert into test_1M_raw values (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return db_path


def _make_valid_rows(count: int, start: datetime, symbol: str = "TEST") -> list[tuple]:
    rows: list[tuple] = []
    for i in range(count):
        dt = start + timedelta(minutes=i)
        rows.append(
            (
                dt.strftime("%Y-%m-%d %H:%M:%S"),
                symbol,
                100.0,
                101.0,
                99.0,
                100.0 + i * 0.01,
                1000.0,
                100000.0,
            )
        )
    return rows


def test_load_raw_bars_counts_unparseable_rows(tmp_path: Path) -> None:
    """Rows with unparseable datetime strings are counted and skipped."""
    valid = [
        ("2024-01-02 09:00:00", "TEST", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0),
        ("2024-01-02 09:01:00", "TEST", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0),
        ("2024-01-02 09:02:00", "TEST", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0),
    ]
    # Prefix bad timestamps with a parseable date so they survive the
    # SQL date-range filter and are actually seen by the parser.
    bad = [
        ("2024-01-02 bad-time", "TEST", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0),
        ("2024-01-02 25:00:00", "TEST", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0),
    ]
    db = _build_a80_db(tmp_path / "unparseable.db", valid + bad)

    adapter = SqliteDataAdapter(str(db))
    try:
        count_holder: list[int] = [-1]
        bars = adapter.load_raw_bars(
            "TEST", freq="1", table_name="test_1M_raw", unparseable_count=count_holder
        )
        assert len(bars) == len(valid)
        assert count_holder[0] == len(bad)

        # Without the out-parameter the API still returns only the bars.
        bars_no_count = adapter.load_raw_bars(
            "TEST", freq="1", table_name="test_1M_raw"
        )
        assert len(bars_no_count) == len(valid)
    finally:
        adapter.close()


def test_clean_dataset_has_zero_unparseable_rows(tmp_path: Path) -> None:
    """A fully parseable dataset reports zero skipped rows."""
    rows = _make_valid_rows(10, datetime(2024, 1, 2, 9, 0))
    db = _build_a80_db(tmp_path / "clean.db", rows)

    adapter = SqliteDataAdapter(str(db))
    try:
        count_holder: list[int] = [-1]
        bars = adapter.load_raw_bars(
            "TEST", freq="1", table_name="test_1M_raw", unparseable_count=count_holder
        )
        assert len(bars) == len(rows)
        assert count_holder[0] == 0
    finally:
        adapter.close()


def test_backtest_report_includes_unparseable_rows_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``generate_report()`` exposes the skipped-row count after a run."""
    valid_rows = _make_valid_rows(150, datetime(2024, 1, 2, 9, 0))
    bad_rows = [
        ("2024-01-02 bad-time-1", "TEST", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0),
        ("2024-01-02 bad-time-2", "TEST", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0),
    ]
    db = _build_a80_db(tmp_path / "report.db", valid_rows + bad_rows)

    # Run with the 1-minute bar as the trade frequency so the small fixture has
    # enough bars to pass the warmup checks.
    monkeypatch.setitem(STRATEGY_CONFIG, "trade_freq", "1分钟")
    engine = BacktestEngine(
        symbol="TEST",
        db_path=str(db),
        table_name="test_1M_raw",
        freq="1",
    )
    report = engine.run(warmup_bars=20)

    assert "error" not in report
    assert engine.unparseable_rows_skipped == len(bad_rows)
    assert report["unparseable_rows_skipped"] == len(bad_rows)


def test_formal_evaluation_report_includes_unparseable_rows_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The formal-evaluation path also surfaces the skipped-row count."""
    symbol = "AP888"
    valid_rows = _make_valid_rows(150, datetime(2024, 1, 2, 9, 0), symbol=symbol)
    bad_rows = [
        ("2024-01-02 malformed", symbol, 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0),
    ]
    db = _build_a80_db(tmp_path / "formal.db", valid_rows + bad_rows)

    monkeypatch.setitem(STRATEGY_CONFIG, "trade_freq", "1分钟")
    engine = BacktestEngine(
        symbol=symbol,
        db_path=str(db),
        table_name="test_1M_raw",
        freq="1",
    )
    with formal_evaluation_config():
        report = engine.run(warmup_bars=20)

    assert "error" not in report
    assert report["unparseable_rows_skipped"] == len(bad_rows)
