"""czsc_strategy 测试共享 fixture。

本模块为 `tests/unit`、`tests/integration`、`tests/performance` 提供合成数据与测试替身，
避免单元测试依赖真实历史数据库或实盘行情。

核心 fixture：

- `FakeBI` / `FakeCZSC`：轻量 dataclass 替身，模拟 czsc 的 BI/CZSC 对象，
  用于不触发 czsc 内部复杂笔构造的信号分支测试。
- `strict_czsc_factory`：在 `FakeCZSC` 构造时校验已确认笔方向严格交替，
  关闭曾被历史 bug 利用的"连续同向笔" fixture 漏洞。
- `bi_factory` / `czsc_factory`：快速构造 FakeBI / FakeCZSC 的工厂。
- `synthetic_1m_bars` / `mini_backtest_bars`：由随机游走合成的 1 分钟 RawBar，
  用于数据适配器、重采样、回测引擎等不依赖真实数据库的测试。
- `memory_db`：基于 `tmp_path` 的内存（临时文件）SQLite 数据库，
  表结构模拟 `{symbol}_1M_raw`，供 data_adapter 与回测入口测试使用。
- `real_db_path`：本地历史 SQLite 数据库路径，默认指向 `chan_strategy/config.py`
  中的 `SQLITE_DB_PATH`，可通过环境变量 `CHAN_SQLITE_DB_PATH` 覆盖；
  仅被标记为 `realdb` 的集成/性能测试使用。

pytest 自定义：

- `pytest_configure` 注册 `realdb`（需要本地历史数据库）和 `slow`（长时运行）两个 marker。
"""
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from czsc import Direction, Freq, RawBar


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
    def __init__(self, bis=None, last_bi_extend=False, bars_raw=None, bi_list=None, validate_alternating: bool = False):
        self.finished_bis = list(bis or [])
        self.last_bi_extend = last_bi_extend
        self.bars_raw = list(bars_raw or [])
        self.bi_list = list(bi_list if bi_list is not None else self.finished_bis)
        if validate_alternating:
            _validate_confirmed_bi_directions(self.bi_list)


def _validate_confirmed_bi_directions(bis: list[FakeBI]) -> None:
    """Assert that confirmed BI directions strictly alternate.

    This invariant closes the fixture loophole exploited by the H3 dead branch:
    consecutive same-direction confirmed BIs do not occur on real data.
    """
    for i in range(1, len(bis)):
        prev_dir = bis[i - 1].direction
        curr_dir = bis[i].direction
        if prev_dir == curr_dir:
            raise ValueError(
                f"Confirmed BI directions must alternate, found {prev_dir.name} "
                f"followed by {curr_dir.name} at index {i}."
            )


@pytest.fixture
def strict_czsc_factory():
    """Return a FakeCZSC factory that validates alternating BI directions."""
    def _factory(bis=None, **kwargs):
        return FakeCZSC(bis=bis, validate_alternating=True, **kwargs)
    return _factory


def make_raw_bar(i, dt, open_=100.0, close=None, high=None, low=None, freq=Freq.F1, vol=None, symbol="TEST"):
    close = open_ if close is None else close
    high = max(open_, close) + 1 if high is None else high
    low = min(open_, close) - 1 if low is None else low
    vol = (100 + i) if vol is None else vol
    return RawBar(
        symbol=symbol,
        id=i,
        dt=dt,
        freq=freq,
        open=open_,
        high=high,
        low=low,
        close=close,
        vol=vol,
        amount=vol * close,
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
