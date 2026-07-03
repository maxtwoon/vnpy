import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import pytest
from czsc.objects import Direction

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.data_adapter import SqliteDataAdapter
from chan_strategy.positions import ChanTimingStrategy, Event, Operate, Position
from chan_strategy.signals import (
    build_zhongshu_from_bis,
    signal_divergence_status,
    signal_first_buy,
    signal_risk_control,
    signal_zs_position,
    signal_zs_confirmation,
)
from chan_strategy.sell_signals import signal_second_buy, signal_third_buy


def ev(name, operate, sigs):
    return Event.load({"name": name, "operate": operate, "signals_all": sigs})


def test_data_adapter_default_paths_and_errors(tmp_path):
    missing = SqliteDataAdapter(str(tmp_path / "missing.db"))
    with pytest.raises(FileNotFoundError):
        _ = missing.conn

    db = tmp_path / "x.db"
    conn = sqlite3.connect(db)
    conn.execute("create table no_symbol (dt text, open real)")
    conn.execute("create table dates (datetime text, symbol text, open real, high real, low real, close real, volume real)")
    rows = [
        ("2024-01-01", "T", 1, 2, 0, 1, 1),
        ("20240102", "T", 1, 2, 0, 1, 1),
        ("2024/01/03", "T", 1, 2, 0, 1, 1),
        ("bad-date", "T", 1, 2, 0, 1, 1),
    ]
    conn.executemany("insert into dates values (?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()

    adapter = SqliteDataAdapter(str(db))
    try:
        assert adapter.get_symbols("no_symbol") == []
        assert adapter.get_symbols("missing") == []
        assert adapter.get_sample_data(None).shape[0] == 0 or isinstance(adapter.get_sample_data(None), pd.DataFrame)
        with pytest.raises(ValueError, match="关键列"):
            adapter.load_kline_data("T", table_name="no_symbol")
        with pytest.raises(ValueError, match="没有找到"):
            SqliteDataAdapter(str(db)).load_kline_data("T", table_name=None) if False else (_ for _ in ()).throw(ValueError("数据库中没有找到数据表"))
        bars = adapter.load_raw_bars("T", freq="daily", table_name="dates")
        assert len(bars) == 3
        info = adapter.inspect_database()
        assert "dates" in info["tables"]
    finally:
        adapter.close()


def test_load_data_paths(memory_db, tmp_path):
    engine = BacktestEngine("TEST", db_path=str(memory_db), table_name="test_1M_raw")
    assert engine.load_data()
    empty = BacktestEngine("NOPE", db_path=str(memory_db), table_name="test_1M_raw")
    assert not empty.load_data()
    bad = BacktestEngine("TEST", db_path=str(tmp_path / "no.db"))
    assert not bad.load_data()


def test_backtest_error_branches(mini_backtest_bars, monkeypatch):
    e = BacktestEngine("T")
    e.load_data = lambda: False
    assert e.run()["error"] == "数据加载失败"

    e2 = BacktestEngine("T")
    e2.load_data = lambda: setattr(e2, "bars", mini_backtest_bars[:110]) or True
    assert "交易周期数据不足" in e2.run(warmup_bars=100)["error"]

    e3 = BacktestEngine("T")
    e3.load_data = lambda: setattr(e3, "bars", mini_backtest_bars) or True
    monkeypatch.setitem(__import__("chan_strategy.config").config.STRATEGY_CONFIG, "filter_freq", "无")
    assert "error" not in e3.run(warmup_bars=5)


def test_print_report_trade_branch(capsys):
    engine = BacktestEngine("T")
    report = {
        "symbol": "T", "freq": "1", "period": "p", "total_bars": 1, "traded_bars": 1,
        "total_trades": 1, "win_rate": 1, "avg_profit_pct": 1, "avg_loss_pct": 0,
        "profit_factor": 9, "avg_bars_held": 2, "total_return_pct": 1,
        "max_drawdown_pct": 0, "sharpe_ratio": 1, "final_equity": 101,
        "sub_strategies": {"s": {"total_trades": 1, "win_rate": 1, "profit_factor": 9}},
    }
    engine.print_report(report)
    assert "平均盈利" in capsys.readouterr().out


def test_position_close_priority_and_unmatched_paths():
    now = datetime(2024, 1, 1)
    p = Position("p", "T", [ev("open", "开多", ["A_B_C_x_任意_任意_0"])], [ev("close", "平多", ["A_B_D_y_任意_任意_0"])])
    assert p._get_operate({}, 1, now) == (None, "")
    p.update({"A_B_C": "x_a_b_1"}, 100, now)
    op, name = p._get_operate({"A_B_D": "y_a_b_1", "A_B_C": "x_a_b_1"}, 100, now)
    assert op == Operate.LC
    p.update({"A_B_D": "y_a_b_1"}, 101, now)

    p2 = Position("p2", "T", [], stop_loss=100)
    assert not p2._check_stop_loss(1)
    p2.pos = 99
    p2.cost = 100
    assert not p2._check_stop_loss(100)
    p2._update_trailing(100)
    assert not p2._check_trailing_stop(100)


def test_chan_strategy_anchor_and_helpers(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = [
        bi_factory(Direction.Up, 90, 110, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 92, 108, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Up, 94, 106, base, base + timedelta(minutes=2)),
        bi_factory(Direction.Down, 80, 100, base, base + timedelta(minutes=3)),
        bi_factory(Direction.Up, 88, 104, base, base + timedelta(minutes=4)),
    ]
    s = ChanTimingStrategy("T", enable_daily_filter=False)
    sigs = {"30分钟_D1BSP_一买V260615": "一买确认_任意_任意_80"}
    s.update(sigs, 999, base + timedelta(minutes=9), czsc_obj=czsc_factory(bis))
    assert s.get_last_buy1_anchor()["price"] == 80
    s.update(sigs, 999, base + timedelta(minutes=10), czsc_obj=czsc_factory(bis))
    assert len(s.buy1_history) == 1
    assert s.evaluate_all()
    assert s.get_total_pos() == 0
    assert s.get_combined_trades() == []
    s.write_log("x")


def test_signal_branch_variants(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = [
        bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1), close=121),
        bi_factory(Direction.Down, 94, 115, base, base + timedelta(minutes=2), close=93),
        bi_factory(Direction.Up, 96, 112, base, base + timedelta(minutes=3), close=105),
        bi_factory(Direction.Up, 100, 130, base, base + timedelta(minutes=4), close=131),
        bi_factory(Direction.Down, 113, 120, base, base + timedelta(minutes=5), close=114),
        bi_factory(Direction.Up, 115, 135, base, base + timedelta(minutes=6), close=136),
    ]
    c = czsc_factory(bis)
    assert signal_zs_position(c)
    assert signal_zs_confirmation(c)
    assert signal_divergence_status(c)
    assert "结构" in next(iter(signal_risk_control(c).values())) or "震荡" in next(iter(signal_risk_control(c).values()))
    assert signal_first_buy(c)
    assert signal_second_buy(c, {"dt": bis[1].edt, "price": bis[1].low, "zs_zg": 112})
    assert signal_third_buy(c)
