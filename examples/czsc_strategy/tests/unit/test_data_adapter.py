from datetime import datetime, timedelta

from czsc.objects import Freq

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
    daily = resample_bars(bars, Freq.D, None)
    assert len(daily) == 2
    assert daily[0].dt.date().isoformat() == "2024-01-02"
    assert daily[1].dt == bars[-1].dt


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
