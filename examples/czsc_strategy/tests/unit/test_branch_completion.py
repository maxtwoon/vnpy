import sqlite3
from datetime import datetime, timedelta

import pytest
from czsc.objects import Direction

import chan_strategy.backtest_engine as be
from chan_strategy.backtest_engine import BacktestEngine, run_batch_backtest
from chan_strategy.data_adapter import SqliteDataAdapter
from chan_strategy.positions import Event, Factor, Operate, Position, Signal
from chan_strategy.signals import (
    signal_divergence_status,
    signal_first_buy,
    signal_risk_control,
    signal_zs_position,
    signal_zs_confirmation,
)
from chan_strategy.sell_signals import signal_second_buy, signal_third_buy


def ev(name, operate, sigs):
    return Event.load({"name": name, "operate": operate, "signals_all": sigs})


def zbase(base, bi_factory):
    return [
        bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1), close=100),
        bi_factory(Direction.Down, 94, 115, base, base + timedelta(minutes=2), close=100),
        bi_factory(Direction.Up, 96, 112, base, base + timedelta(minutes=3), close=100),
    ]


def zseed(base, bi_factory):
    """Five-bis seed with a confirmed first zhongshu ending at index 2."""
    return zbase(base, bi_factory) + [
        bi_factory(Direction.Up, 130, 150, base, base + timedelta(minutes=4), close=150),
        bi_factory(Direction.Down, 118, 140, base, base + timedelta(minutes=5), close=118),
    ]


def test_adapter_empty_defaults_and_numeric_dates(tmp_path):
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(db)
    conn.execute("create table t (datetime integer, symbol text, open real, high real, low real, close real)")
    conn.execute("insert into t values (1704067200000000000, 'T', 1, 2, 0, 1)")
    conn.commit()
    conn.close()

    adapter = SqliteDataAdapter(str(db))
    try:
        assert adapter.get_symbols(None) == ["T"]
        assert len(adapter.get_sample_data(None, 1)) == 1
        bars = adapter.load_raw_bars("T", table_name=None)
        assert len(bars) == 1
    finally:
        adapter.close()

    db2 = tmp_path / "empty2.db"
    sqlite3.connect(db2).close()
    adapter2 = SqliteDataAdapter(str(db2))
    try:
        assert adapter2.get_symbols(None) == []
        assert adapter2.get_sample_data(None).empty
        with pytest.raises(ValueError):
            adapter2.load_kline_data("T")
    finally:
        adapter2.close()


def test_factor_event_negative_any_all_not():
    assert not Factor("f", signals_all=[Signal("A_B_C_x_任意_任意_0")]).is_match({"A_B_C": "z_y_z_1"})
    assert not Factor("f", signals_any=[Signal("A_B_C_x_任意_任意_0")]).is_match({"A_B_C": "z_y_z_1"})
    assert not Factor("f", signals_not=[Signal("A_B_C_x_任意_任意_0")]).is_match({"A_B_C": "x_y_z_1"})
    assert not Event("e", Operate.LO, signals_any=[Signal("A_B_C_x_任意_任意_0")]).is_match({})


def test_position_short_risk_paths():
    now = datetime(2024, 1, 1)
    p = Position("s", "T", [], timeout=9, stop_loss=100, trailing_start=50)
    p._open_short(100, now)
    p.update({}, 98, now + timedelta(minutes=1))
    assert p.pos == -1
    p.update({}, 99, now + timedelta(minutes=2))
    assert p.pos == 0 and p.pairs[-1]["reason"] == "移动止损"

    p._open_short(100, now)
    p.update({}, 102, now + timedelta(minutes=2))
    assert p.pos == 0 and p.pairs[-1]["reason"] == "止损"

    p = Position("s2", "T", [], timeout=1, stop_loss=9999, trailing_start=9999)
    p._open_short(100, now)
    p.update({}, 100, now + timedelta(minutes=3))
    assert p.pos == 0 and p.pairs[-1]["reason"] == "超时"


def test_position_evaluate_and_combined_trades():
    p = Position("p", "T", [])
    now = datetime(2024, 1, 1)
    p._open_long(100, now)
    p._close_long(110, now + timedelta(minutes=1))
    p._open_long(100, now + timedelta(minutes=2))
    p._close_long(90, now + timedelta(minutes=3))
    stats = p.evaluate()
    assert stats["total_trades"] == 2
    assert stats["win_count"] == 1


def test_strategy_logs_and_anchor_fallback(czsc_factory, bi_factory, capsys):
    from chan_strategy.positions import ChanTimingStrategy

    base = datetime(2024, 1, 1)
    s = ChanTimingStrategy("T", enable_daily_filter=False)
    s._log_daily_trend({"日线_D1BI_方向V260615": "向上_任意_任意_0"}, base)
    assert "日线趋势" in capsys.readouterr().out
    s._last_buy1_anchor = {"dt": base, "price": 1, "zs_zd": None, "zs_zg": None}
    bis = zbase(base, bi_factory)
    s.update({}, 100, base, czsc_obj=czsc_factory(bis))
    assert s._last_buy1_anchor["zs_zd"] is not None


def test_signal_position_fallbacks(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    up = bi_factory(Direction.Up, 90, 110, base, base, close=110)
    up.raw_bars = []
    down = bi_factory(Direction.Down, 91, 109, base, base, close=91)
    down.raw_bars = []
    up.high = 130
    assert "中枢上方" in next(iter(signal_zs_position(czsc_factory(zbase(base, bi_factory) + [up])).values()))
    assert signal_zs_position(czsc_factory(zbase(base, bi_factory) + [down]))
    assert signal_zs_confirmation(czsc_factory([up, down]))


def test_divergence_and_first_buy_variants(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = zseed(base, bi_factory)
    down_leave = bi_factory(Direction.Down, 80, 100, base, base + timedelta(minutes=6))
    confirm_up = bi_factory(Direction.Up, 85, 105, base, base + timedelta(minutes=7))
    assert "疑似" in next(iter(signal_divergence_status(czsc_factory(bis + [down_leave])).values()))
    assert "一买候选" in next(iter(signal_first_buy(czsc_factory(bis + [down_leave])).values()))
    assert "一买确认" in next(iter(signal_first_buy(czsc_factory(bis + [down_leave, confirm_up])).values()))
    assert "非一买" in next(iter(signal_first_buy(czsc_factory(bis + [confirm_up])).values()))
    not_leave = bi_factory(Direction.Down, 97, 105, base, base + timedelta(minutes=6))
    assert "非一买" in next(iter(signal_first_buy(czsc_factory(bis + [not_leave])).values()))


def test_second_buy_early_returns_and_candidate(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = zbase(base, bi_factory)
    anchor = {"dt": base + timedelta(minutes=3), "price": 80, "zs_zg": 100}
    assert "非二买" in next(iter(signal_second_buy(czsc_factory(bis), buy1_anchor=anchor).values()))
    bad_rebound = bis + [
        bi_factory(Direction.Down, 80, 90, base, base + timedelta(minutes=4)),
        bi_factory(Direction.Down, 81, 91, base, base + timedelta(minutes=5)),
    ]
    assert "非二买" in next(iter(signal_second_buy(czsc_factory(bad_rebound), buy1_anchor=anchor).values()))
    candidate = bis + [
        bi_factory(Direction.Down, 80, 90, base, base + timedelta(minutes=4)),
        bi_factory(Direction.Up, 85, 110, base + timedelta(minutes=4), base + timedelta(minutes=5)),
        bi_factory(Direction.Down, 82, 95, base + timedelta(minutes=5), base + timedelta(minutes=6)),
    ]
    anchor = {"dt": base + timedelta(minutes=4), "price": 80, "zs_zg": 100}
    assert "二买候选" in next(iter(signal_second_buy(czsc_factory(candidate), buy1_anchor=anchor).values()))
    broken = candidate[:-1] + [bi_factory(Direction.Down, 79, 95, base, base + timedelta(minutes=6))]
    assert "非二买" in next(iter(signal_second_buy(czsc_factory(broken), buy1_anchor=anchor).values()))


def test_third_buy_stage_variants(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = zbase(base, bi_factory) + [bi_factory(Direction.Down, 80, 100, base, base + timedelta(minutes=4))]
    assert "非三买" in next(iter(signal_third_buy(czsc_factory(bis)).values()))
    leave = bis + [bi_factory(Direction.Up, 250, 300, base, base + timedelta(minutes=6))]
    assert "离开中枢" in next(iter(signal_third_buy(czsc_factory(leave)).values()))
    retrace = leave + [bi_factory(Direction.Down, 200, 280, base, base + timedelta(minutes=7))]
    assert "回抽不入中枢" in next(iter(signal_third_buy(czsc_factory(retrace)).values()))
    fail = leave + [bi_factory(Direction.Down, 90, 280, base, base + timedelta(minutes=7))]
    assert "非三买" in next(iter(signal_third_buy(czsc_factory(fail)).values()))
    late_fail = retrace + [
        bi_factory(Direction.Up, 281, 310, base, base + timedelta(minutes=8)),
        bi_factory(Direction.Down, 90, 100, base, base + timedelta(minutes=9)),
    ]
    assert "非三买" in next(iter(signal_third_buy(czsc_factory(late_fail)).values()))
    confirm = retrace + [bi_factory(Direction.Up, 281, 310, base, base + timedelta(minutes=8))]
    assert "三买确认" in next(iter(signal_third_buy(czsc_factory(confirm)).values()))


def test_risk_control_variants(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = zbase(base, bi_factory)
    low = bi_factory(Direction.Down, 80, 100, base, base + timedelta(minutes=4))
    low.raw_bars = []
    assert "结构失效" in next(iter(signal_risk_control(czsc_factory(bis + [low]), stop_loss_pct=0.01).values()))
    many = bis + [bi_factory(Direction.Up if i % 2 else Direction.Down, 97, 105, base, base + timedelta(minutes=4 + i)) for i in range(8)]
    assert "震荡超限" in next(iter(signal_risk_control(czsc_factory(many), stop_loss_pct=0.5).values()))


def test_backtest_engine_run_accounting_branches(monkeypatch, mini_backtest_bars, capsys):
    class FakePosition:
        def __init__(self, name, pos=0):
            self.name = name
            self.pos = pos
            self.cost = 100
            self.pairs = []
            self.count = 0

        def evaluate(self):
            return {"total_trades": len(self.pairs), "win_rate": 1, "profit_factor": 1}

    class FakeStrategy:
        def __init__(self, *args, **kwargs):
            self.positions = [FakePosition("一买多头", 1), FakePosition("二买多头", -1), FakePosition("三买多头", 0)]
            self.enable_daily_filter = kwargs.get("enable_daily_filter")

        def get_last_buy1_anchor(self):
            return None

        def get_last_sell1_anchor(self):
            return None

        def update(self, signals, price, dt, execution_price=None, czsc_obj=None,
                   bar_high=None, bar_low=None):
            p = self.positions[2]
            if len(p.pairs) == 0 and signals:
                p.pairs.append({"open_dt": dt, "close_dt": dt, "pnl_pct": 0.1, "bars_held": 1})

        def evaluate_all(self):
            return {p.name: p.evaluate() for p in self.positions}

        def get_combined_trades(self):
            out = []
            for p in self.positions:
                for pair in p.pairs:
                    q = pair.copy()
                    q["strategy"] = p.name
                    out.append(q)
            return out

    monkeypatch.setattr(be, "ChanTimingStrategy", FakeStrategy)
    monkeypatch.setitem(be.STRATEGY_CONFIG, "trade_freq", "30分钟")
    engine = BacktestEngine("T")
    engine.load_data = lambda: setattr(engine, "bars", mini_backtest_bars * 3) or True
    report = engine.run(warmup_bars=5)
    assert report["total_trades"] >= 1
    assert engine._cum_realized_pnl


def test_batch_error_branch(monkeypatch):
    monkeypatch.setattr(BacktestEngine, "run", lambda self: {"error": "bad"})
    df = run_batch_backtest(["X"])
    assert df.iloc[0]["error"] == "bad"
