import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from czsc.objects import Direction, Freq, RawBar


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))


@dataclass
class FakeBI:
    direction: Direction
    low: float
    high: float
    sdt: datetime
    edt: datetime
    raw_bars: list = field(default_factory=list)


class FakeCZSC:
    def __init__(self, bis=None, last_bi_extend=False, bars_raw=None, bi_list=None):
        self.finished_bis = list(bis or [])
        self.last_bi_extend = last_bi_extend
        self.bars_raw = list(bars_raw or [])
        self.bi_list = list(bi_list if bi_list is not None else self.finished_bis)


def make_raw_bar(i, dt, open_=100.0, close=None, high=None, low=None, freq=Freq.F1):
    close = open_ if close is None else close
    high = max(open_, close) + 1 if high is None else high
    low = min(open_, close) - 1 if low is None else low
    return RawBar(
        symbol="TEST",
        id=i,
        dt=dt,
        freq=freq,
        open=open_,
        high=high,
        low=low,
        close=close,
        vol=100 + i,
        amount=(100 + i) * close,
    )


def make_bi(direction, low, high, sdt, edt, close=None):
    close = high if close is None and direction == Direction.Up else close
    close = low if close is None else close
    raw = [make_raw_bar(0, edt, open_=(low + high) / 2, close=close, high=high, low=low)]
    return FakeBI(direction=direction, low=low, high=high, sdt=sdt, edt=edt, raw_bars=raw)


@pytest.fixture
def bi_factory():
    return make_bi


@pytest.fixture
def czsc_factory():
    return FakeCZSC


@pytest.fixture
def synthetic_1m_bars():
    def _make(days=3, per_day=240, start=datetime(2024, 1, 2, 9, 0)):
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
                bars.append(make_raw_bar(i, dt, open_=open_, close=close))
                price = close
                i += 1
        return bars
    return _make


@pytest.fixture
def mini_backtest_bars(synthetic_1m_bars):
    return synthetic_1m_bars(days=4, per_day=180)


@pytest.fixture
def memory_db(tmp_path):
    db = tmp_path / "bars.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "create table test_1M_raw (datetime text, symbol text, open real, high real, low real, close real, volume real, amount real)"
    )
    rows = []
    base = datetime(2024, 1, 2, 9, 0)
    for i in range(120):
        dt = base + timedelta(minutes=i)
        rows.append((dt.strftime("%Y-%m-%d %H:%M:%S"), "TEST", 100, 101, 99, 100 + i * 0.01, 1000, 100000))
    conn.executemany("insert into test_1M_raw values (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def real_db_path():
    default = Path(r"D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db")
    return Path(os.getenv("CHAN_SQLITE_DB_PATH", default))


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: requires local historical sqlite database")
    config.addinivalue_line("markers", "slow: long-running tests")
