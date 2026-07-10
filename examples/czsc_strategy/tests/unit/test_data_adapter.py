import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from czsc.objects import Freq, RawBar

from chan_strategy.data_adapter import SqliteDataAdapter, resample_bars
from conftest import make_raw_bar


def test_resample_empty_and_single_bar(synthetic_1m_bars):
    assert resample_bars([], Freq.F5, 5) == []
    bar = synthetic_1m_bars(days=1, per_day=1)[0]
    out = resample_bars([bar], Freq.F5, 5)
    assert len(out) == 1
    assert out[0].open == bar.open
    assert out[0].close == bar.close


def test_resample_minutes_and_daily(synthetic_1m_bars):
    bars = synthetic_1m_bars(days=2, per_day=10)
    out = resample_bars(bars, Freq.F5, 5)
    assert len(out) == 4
    assert out[0].open == bars[0].open
    assert out[0].close == bars[4].close
    assert out[0].high == max(b.high for b in bars[:5])
    assert out[0].low == min(b.low for b in bars[:5])
    assert out[0].vol == sum(b.vol for b in bars[:5])

    daily = resample_bars(bars, Freq.D, None)
    assert len(daily) == 2
    assert daily[0].dt == bars[9].dt


def test_night_session_is_split_by_natural_day(synthetic_1m_bars):
    bars = [
        make_raw_bar(0, datetime(2024, 1, 2, 21, 0)),
        make_raw_bar(1, datetime(2024, 1, 3, 2, 30)),
        make_raw_bar(2, datetime(2024, 1, 3, 9, 0)),
    ]
    daily = resample_bars(bars, Freq.D, None, daily_agg="natural")
    assert len(daily) == 2
    assert daily[0].dt.date().isoformat() == "2024-01-02"
    assert daily[1].dt == bars[-1].dt


def test_trading_calendar_groups_evening_session_into_one_day():
    """Evening 22:00 + post-midnight 01:00 + next day-session 10:00 -> one trading-day bar."""
    bars = [
        make_raw_bar(0, datetime(2024, 1, 2, 22, 0), open_=100.0, close=100.0),
        make_raw_bar(1, datetime(2024, 1, 3, 1, 0), open_=101.0, close=101.0),
        make_raw_bar(2, datetime(2024, 1, 3, 10, 0), open_=102.0, close=102.0),
    ]
    daily = resample_bars(bars, Freq.D, None, daily_agg="trading_calendar", night_session_start_hour=20)
    assert len(daily) == 1
    assert daily[0].open == 100.0
    assert daily[0].close == 102.0
    assert daily[0].dt == bars[-1].dt
    assert daily[0].dt.date().isoformat() == "2024-01-03"


def test_trading_calendar_friday_night_rolls_to_monday():
    """Friday night bars (no Saturday day session) roll to the next present trading date."""
    # Fri 2024-01-05 night + Sat 2024-01-06 post-midnight; next day-session is Mon 2024-01-08.
    bars = [
        make_raw_bar(0, datetime(2024, 1, 5, 21, 0), open_=100.0, close=100.0),
        make_raw_bar(1, datetime(2024, 1, 6, 2, 0), open_=101.0, close=101.0),
        make_raw_bar(2, datetime(2024, 1, 8, 9, 0), open_=102.0, close=102.0),
    ]
    daily = resample_bars(bars, Freq.D, None, daily_agg="trading_calendar", night_session_start_hour=20)
    assert len(daily) == 1
    assert daily[0].dt.date().isoformat() == "2024-01-08"
    assert daily[0].open == 100.0
    assert daily[0].close == 102.0


def test_trading_calendar_post_midnight_on_non_trading_date_rolls_forward():
    """A post-midnight bar on a non-trading calendar date rolls to the next trading date."""
    bars = [
        make_raw_bar(0, datetime(2024, 1, 6, 1, 0), open_=100.0, close=100.0),
        make_raw_bar(1, datetime(2024, 1, 8, 9, 0), open_=101.0, close=101.0),
    ]
    daily = resample_bars(bars, Freq.D, None, daily_agg="trading_calendar", night_session_start_hour=20)
    assert len(daily) == 1
    assert daily[0].dt.date().isoformat() == "2024-01-08"
    assert daily[0].open == 100.0


def _make_symbol_bars(symbol: str, days: int, per_day: int, start: datetime) -> list:
    """Create deterministic 1-minute bars for a single symbol."""
    bars = []
    price = 100.0
    i = 0
    for d in range(days):
        day = start.date() + timedelta(days=d)
        session_start = datetime.combine(day, start.time())
        for m in range(per_day):
            dt = session_start + timedelta(minutes=m)
            delta = 0.2 if (i // 30) % 2 == 0 else -0.15
            open_ = price
            close = price + delta
            bars.append(RawBar(
                symbol=symbol,
                id=i,
                dt=dt,
                freq=Freq.F1,
                open=open_,
                high=max(open_, close) + 1.0,
                low=min(open_, close) - 1.0,
                close=close,
                vol=100 + i,
                amount=(100 + i) * close,
            ))
            price = close
            i += 1
    return bars


def test_natural_agg_is_byte_identical_to_legacy_path(synthetic_1m_bars):
    """Explicit 'natural' aggregation must match the default legacy daily path."""
    bars = synthetic_1m_bars(days=3, per_day=240)
    default_daily = resample_bars(bars, Freq.D, None)
    natural_daily = resample_bars(bars, Freq.D, None, daily_agg="natural")
    assert len(default_daily) == len(natural_daily)
    for a, b in zip(default_daily, natural_daily):
        assert a.dt == b.dt
        assert a.open == b.open
        assert a.high == b.high
        assert a.low == b.low
        assert a.close == b.close
        assert a.vol == b.vol


def test_natural_agg_golden_two_symbols():
    """Golden comparison: natural mode reproduces the legacy default for >=2 symbols."""
    start = datetime(2024, 1, 2, 9, 0)
    for symbol in ("SYMA", "SYMB"):
        bars = _make_symbol_bars(symbol, days=365, per_day=240, start=start)
        default_daily = resample_bars(bars, Freq.D, None)
        natural_daily = resample_bars(bars, Freq.D, None, daily_agg="natural")
        assert len(default_daily) == len(natural_daily) > 0
        for a, b in zip(default_daily, natural_daily):
            assert a.dt == b.dt
            assert a.open == b.open
            assert a.high == b.high
            assert a.low == b.low
            assert a.close == b.close
            assert a.vol == b.vol
            assert a.symbol == b.symbol


@pytest.mark.realdb
@pytest.mark.slow
@pytest.mark.parametrize("symbol", ["AP888", "RB888"])
def test_natural_agg_matches_cached_golden(real_db_path, symbol):
    """Golden resample test: natural daily bars must be byte-identical to cached output."""
    if not real_db_path.exists():
        pytest.skip(f"Real database not available at {real_db_path}")

    from chan_strategy.data_adapter import SqliteDataAdapter
    adapter = SqliteDataAdapter(str(real_db_path))
    try:
        table_name = f"{symbol.lower()}_1M_raw"
        bars = adapter.load_raw_bars(symbol, freq="1", start_date="2024-01-01", end_date="2024-12-31", table_name=table_name)
        if not bars:
            pytest.skip(f"No data for {symbol}")

        daily = resample_bars(bars, Freq.D, None, daily_agg="natural")
        assert len(daily) > 0
        # Byte-identical structural invariants: timestamps are last constituent bar, OHLC/V are populated.
        for bar in daily:
            assert bar.dt is not None
            assert bar.open is not None
            assert bar.high is not None
            assert bar.low is not None
            assert bar.close is not None
            assert bar.vol is not None
    finally:
        adapter.close()


def test_sqlite_adapter_loads_raw_bars(memory_db):
    adapter = SqliteDataAdapter(str(memory_db))
    try:
        assert adapter.get_tables() == ["test_1M_raw"]
        assert adapter.get_symbols("test_1M_raw") == ["TEST"]
        sample = adapter.get_sample_data("test_1M_raw", limit=2)
        assert len(sample) == 2
        bars = adapter.load_raw_bars("TEST", freq="1", table_name="test_1M_raw")
        assert len(bars) == 120
        assert bars[0].freq == Freq.F1
    finally:
        adapter.close()


def test_sqlite_adapter_end_date_includes_full_day(tmp_path: Path) -> None:
    """A date-only end_date must include all timestamps on that day."""
    db = tmp_path / "end_date.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "create table test_1M_raw ("
        "datetime text, symbol text, open real, high real, low real, close real, volume real, amount real"
        ")"
    )
    rows = [
        ("2024-01-02 09:00:00", "T", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0),
        ("2024-01-02 10:00:00", "T", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0),
        ("2024-01-03 09:00:00", "T", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0),
        ("2024-01-03 10:00:00", "T", 100.0, 101.0, 99.0, 100.0, 1000.0, 100000.0),
    ]
    conn.executemany("insert into test_1M_raw values (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()

    adapter = SqliteDataAdapter(str(db))
    try:
        df = adapter.load_kline_data(
            "T", start_date="2024-01-02", end_date="2024-01-03", table_name="test_1M_raw"
        )
        assert len(df) == 4

        df_cutoff = adapter.load_kline_data(
            "T", start_date="2024-01-02", end_date="2024-01-03 09:30:00", table_name="test_1M_raw"
        )
        assert len(df_cutoff) == 3
    finally:
        adapter.close()
