import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import pytest
from czsc.objects import Direction, Freq

import chan_strategy.positions as positions_module
import chan_strategy.backtest_engine as backtest_module
import chan_strategy.signals as signals_module
from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.data_adapter import SqliteDataAdapter, resample_bars
from chan_strategy.positions import (
    ChanTimingStrategy,
    Event,
    Operate,
    Position,
    Signal,
)
from chan_strategy.signals import (
    _get_confirmed_bi_list,
    _get_confirming_bi,
    signal_bi_direction,
    signal_divergence_status,
    signal_first_buy,
    signal_risk_control,
    signal_second_buy,
    signal_zs_confirmation,
)
from chan_strategy.sell_signals import get_all_signals, signal_third_buy


def zbase(base, bi_factory):
    return [
        bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1), close=100),
        bi_factory(Direction.Down, 94, 115, base, base + timedelta(minutes=2), close=100),
        bi_factory(Direction.Up, 96, 112, base, base + timedelta(minutes=3), close=100),
    ]


def make_event(name, operate, signal_value="a_b_c_x_y_z_0"):
    return Event(name=name, operate=operate, signals_all=[Signal(signal_value)])


def test_data_adapter_remaining_branches(tmp_path, synthetic_1m_bars):
    bars = synthetic_1m_bars(days=2, per_day=3)
    assert resample_bars([], Freq.F5, 5) == []
    assert len(resample_bars(bars[:1], Freq.F5, 5)) == 1
    assert len(resample_bars(bars, Freq.D)) == 2

    db = tmp_path / "freq.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "create table k (datetime text, symbol text, freq text, open real, high real, low real, close real)"
    )
    conn.executemany(
        "insert into k values (?,?,?,?,?,?,?)",
        [
            ("2024-01-01", "A", "1", 1, 2, 0.5, 1.5),
            ("2024-01-02", "A", "5", 2, 3, 1.5, 2.5),
        ],
    )
    conn.commit()
    conn.close()

    adapter = SqliteDataAdapter(str(db))
    try:
        assert len(adapter.load_kline_data("A", freq="5", table_name="k")) == 1
        assert adapter.get_symbols("k") == ["A"]
        assert not adapter.get_sample_data("k", limit=1).empty
    finally:
        adapter.close()


def test_load_raw_bars_timestamp_and_bad_string(monkeypatch, tmp_path):
    adapter = SqliteDataAdapter(str(tmp_path / "x.db"))
    df = pd.DataFrame(
        [
            {
                "datetime": "bad-date",
                "symbol": "A",
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
            },
            {
                "datetime": pd.Timestamp("2024-01-02 09:30:00"),
                "symbol": "A",
                "open": 2,
                "high": 3,
                "low": 1,
                "close": 2.5,
            },
        ]
    )
    monkeypatch.setattr(adapter, "load_kline_data", lambda *args, **kwargs: df)
    bars = adapter.load_raw_bars("A", freq="unknown", table_name="ignored")
    assert len(bars) == 1
    assert bars[0].freq == Freq.D
    assert bars[0].vol == 0
    assert bars[0].amount == 0


def test_backtest_load_data_and_empty_report(memory_db):
    engine = BacktestEngine(
        symbol="TEST",
        db_path=str(memory_db),
        table_name="test_1M_raw",
        freq="1",
        start_date="2024-01-02",
        end_date="2024-01-03",
    )
    assert engine.load_data() is True
    assert "error" in engine.generate_report()

    empty = BacktestEngine(symbol="TEST", db_path=str(memory_db), table_name="test_1M_raw")
    assert "error" in empty.generate_report()

    missing = BacktestEngine(symbol="NOPE", db_path=str(memory_db))
    missing._find_table = lambda adapter: ""
    assert missing.load_data() is False


def test_backtest_run_daily_increment_and_progress(monkeypatch, synthetic_1m_bars):
    engine = BacktestEngine(symbol="TEST", db_path="unused")
    bars = synthetic_1m_bars(days=12, per_day=60)

    class FakeRunCZSC:
        def __init__(self, bars):
            self.bars_raw = list(bars)
            self.bi_list = [object()]

        def update(self, bar):
            self.bars_raw.append(bar)

    def fake_load_data():
        engine.bars = bars
        return True

    monkeypatch.setattr(engine, "load_data", fake_load_data)
    monkeypatch.setattr(backtest_module, "CZSC", FakeRunCZSC)
    monkeypatch.setattr(backtest_module, "get_all_signals", lambda c, freq, buy1_anchor=None, sell1_anchor=None: {f"{freq}_dummy": "ok"})
    monkeypatch.setitem(backtest_module.STRATEGY_CONFIG, "trade_freq", "1分钟")
    monkeypatch.setitem(backtest_module.STRATEGY_CONFIG, "filter_freq", "日线")
    report = engine.run(warmup_bars=180)
    assert "error" not in report
    assert engine.czsc_obj is not None
    assert any(k.startswith("日线_") for row in engine.signal_history for k in row["signals"])


def test_backtest_report_sharpe_boundaries():
    engine = BacktestEngine(symbol="TEST", db_path="unused")
    dt = datetime(2024, 1, 1)
    engine.bars = [object()]
    engine.strategy = ChanTimingStrategy("TEST", enable_daily_filter=False)
    engine.strategy.positions[0].pairs.append(
        {"open_dt": dt, "close_dt": dt, "open_price": 1, "close_price": 2, "pnl_pct": 0.01, "bars_held": 1}
    )
    engine.equity_curve = [{"dt": dt, "equity": 101_000, "price": 1, "positions": 0}]
    assert engine.generate_report()["sharpe_ratio"] == 0

    engine.equity_curve = [
        {"dt": dt + timedelta(days=i), "equity": 101_000, "price": 1, "positions": 0}
        for i in range(3)
    ]
    assert engine.generate_report()["sharpe_ratio"] == 0


def test_position_short_interval_and_risk_branches():
    dt = datetime(2024, 1, 1, 9, 0)
    sig = {"a_b_c": "x_y_z_0"}
    pos = Position(
        name="short",
        symbol="T",
        opens=[make_event("short-open", Operate.SO)],
        exits=[make_event("short-close", Operate.SC)],
        timeout=10,
        stop_loss=100,
        trailing_start=50,
        trailing_drawback_pct=0.5,
    )
    pos.update(sig, 100, dt)
    assert pos.pos == -1
    pos.update(sig, 99, dt + timedelta(minutes=1))
    assert pos.pos == 0
    assert pos.pairs[-1]["pnl_pct"] > 0

    blocked = Position(
        name="blocked",
        symbol="T",
        opens=[make_event("open", Operate.LO)],
        interval=3600,
    )
    blocked.last_open_dt = dt
    blocked.update(sig, 100, dt + timedelta(minutes=1))
    assert blocked.pos == 0
    blocked.update(sig, 100, dt + timedelta(hours=2))
    assert blocked.pos == 1

    flat = Position(name="flat", symbol="T", opens=[])
    flat._update_trailing(100)
    assert flat._check_stop_loss(100) is False
    assert flat._check_trailing_stop(100) is False
    flat.cost = 100
    flat.pos = 0
    flat._update_trailing(100)
    flat.trailing_active = True
    assert flat._check_trailing_stop(100) is False
    assert flat._check_stop_loss(100) is False

    short_stop = Position(name="short-stop", symbol="T", opens=[])
    short_stop._open_short(100, dt)
    assert short_stop._check_stop_loss(120) is True
    short_stop._close_short(120, dt + timedelta(minutes=1), "manual")
    assert short_stop.pos == 0

    short_timeout = Position(name="short-timeout", symbol="T", opens=[], timeout=1, stop_loss=9999)
    short_timeout._open_short(100, dt)
    short_timeout.update({}, 100, dt + timedelta(minutes=1))
    assert short_timeout.pos == 0

    short_trail = Position(name="short-trail", symbol="T", opens=[], trailing_start=50, trailing_drawback_pct=0.5)
    short_trail._open_short(100, dt)
    short_trail.update({}, 99, dt + timedelta(minutes=1))
    short_trail.update({}, 99.6, dt + timedelta(minutes=2))
    assert short_trail.pos == 0


def test_signal_helpers_and_classification_edges(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    assert _get_confirmed_bi_list(object()) == []
    assert _get_confirming_bi([], 0, Direction.Up) is None
    assert _get_confirming_bi([bi_factory(Direction.Up, 1, 2, base, base)], -1, Direction.Up) is None
    assert _get_confirming_bi(
        [bi_factory(Direction.Up, 1, 2, base, base), bi_factory(Direction.Down, 1, 2, base, base)],
        0,
        Direction.Up,
    ) is None
    assert _get_confirming_bi(
        [
            bi_factory(Direction.Up, 1, 2, base, base),
            bi_factory(Direction.Up, 1, 2, base, base),
            bi_factory(Direction.Down, 1, 2, base, base),
        ],
        0,
        Direction.Up,
    ) is None

    up = bi_factory(Direction.Up, 1, 2, base, base)
    down = bi_factory(Direction.Down, 1, 2, base, base)
    assert "向上" in next(iter(signal_bi_direction(czsc_factory([up])).values()))
    assert "向下" in next(iter(signal_bi_direction(czsc_factory([down])).values()))

    assert "未确认" in next(iter(signal_zs_confirmation(czsc_factory([up, down])).values()))
    assert "无中枢" in next(iter(signal_zs_confirmation(czsc_factory([up])).values()))
    assert "非一买" in next(iter(signal_first_buy(czsc_factory(zbase(base, bi_factory))).values()))
    assert "非一买" in next(
        iter(signal_first_buy(czsc_factory(zbase(base, bi_factory) + [bi_factory(Direction.Up, 130, 150, base, base)])).values())
    )

    no_leave = zbase(base, bi_factory) + [bi_factory(Direction.Down, 100, 110, base, base)]
    assert "非一买" in next(iter(signal_first_buy(czsc_factory(no_leave)).values()))

    enter = bi_factory(Direction.Down, 50, 120, base, base)
    div = [enter] + zbase(base + timedelta(minutes=1), bi_factory) + [
        bi_factory(Direction.Down, 80, 93, base, base + timedelta(minutes=10)),
    ]
    assert "疑似" in next(iter(signal_divergence_status(czsc_factory(div)).values()))

    failed = [enter] + zbase(base + timedelta(minutes=1), bi_factory) + [
        bi_factory(Direction.Down, 80, 93, base, base + timedelta(minutes=10)),
        bi_factory(Direction.Down, 70, 90, base, base + timedelta(minutes=11)),
    ]
    assert next(iter(signal_divergence_status(czsc_factory(failed)).values())).split("_")[0] in {"疑似", "失效"}

    assert "已确认" in next(iter(signal_zs_confirmation(czsc_factory(zbase(base, bi_factory))).values()))


def test_signal_branches_with_injected_zhongshu(monkeypatch, czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)

    monkeypatch.setattr(signals_module, "build_zhongshu_from_bis", lambda bis, **kwargs: [{"n_bis": 2}])
    assert "未确认" in next(iter(signal_zs_confirmation(czsc_factory(zbase(base, bi_factory))).values()))

    div_bis = [
        bi_factory(Direction.Up, 1, 101, base, base),
        bi_factory(Direction.Up, 90, 120, base, base),
        bi_factory(Direction.Down, 94, 115, base, base),
        bi_factory(Direction.Up, 96, 112, base, base),
        bi_factory(Direction.Down, 90, 100, base, base),
        bi_factory(Direction.Down, 80, 200, base, base),
    ]
    monkeypatch.setattr(
        signals_module,
        "build_zhongshu_from_bis",
        lambda bis, **kwargs: [{"zd": 96, "zg": 112, "start_idx": 1, "end_idx": 3, "n_bis": 3}],
    )
    assert "失效" in next(iter(signal_divergence_status(czsc_factory(div_bis)).values()))

    up_div_bis = div_bis[:4] + [bi_factory(Direction.Up, 100, 130, base, base)]
    assert "疑似" in next(iter(signal_divergence_status(czsc_factory(up_div_bis)).values()))

    non_weak_first = div_bis[:4] + [bi_factory(Direction.Down, 10, 200, base, base)]
    assert "非一买" in next(iter(signal_first_buy(czsc_factory(non_weak_first)).values()))

    first_no_down = div_bis[:4] + [bi_factory(Direction.Up, 120, 130, base, base)]
    assert "非一买" in next(iter(signal_first_buy(czsc_factory(first_no_down)).values()))

    first_start_gt_zero = div_bis[:4] + [
        bi_factory(Direction.Down, 80, 90, base, base),
        bi_factory(Direction.Up, 85, 100, base, base),
    ]
    assert next(iter(signal_first_buy(czsc_factory(first_start_gt_zero)).values())).split("_")[0] in {"一买候选", "一买确认"}

    no_up_leave = div_bis[:4] + [bi_factory(Direction.Down, 80, 90, base, base)]
    assert "非三买" in next(iter(signal_third_buy(czsc_factory(no_up_leave)).values()))

    failed_retrace = div_bis[:4] + [
        bi_factory(Direction.Up, 120, 130, base, base),
        bi_factory(Direction.Down, 80, 90, base, base),
        bi_factory(Direction.Up, 100, 112, base, base),
    ]
    assert "非三买" in next(iter(signal_third_buy(czsc_factory(failed_retrace)).values()))

    no_retrace_up = div_bis[:4] + [
        bi_factory(Direction.Up, 120, 130, base, base),
        bi_factory(Direction.Up, 100, 112, base, base),
    ]
    assert "离开中枢" in next(iter(signal_third_buy(czsc_factory(no_retrace_up)).values()))

    risk_bis = zbase(base, bi_factory)
    risk_bis[-1].raw_bars = []
    assert next(iter(signal_risk_control(czsc_factory(risk_bis)).values()))


def test_second_and_third_buy_remaining_edges(czsc_factory, bi_factory):
    base = datetime(2024, 1, 1)
    bis = zbase(base, bi_factory)
    anchor = {"dt": base + timedelta(minutes=3), "price": 94, "zs_zg": 112}

    assert "非二买" in next(iter(signal_second_buy(czsc_factory(bis), buy1_anchor=anchor).values()))
    assert "非二买" in next(iter(signal_second_buy(czsc_factory([
        bi_factory(Direction.Up, 90, 120, base, base),
        bi_factory(Direction.Up, 91, 121, base, base),
        bi_factory(Direction.Up, 92, 122, base, base),
        bi_factory(Direction.Up, 93, 123, base, base),
        bi_factory(Direction.Up, 94, 124, base, base),
    ]), buy1_anchor={"price": 94, "zs_zg": 112}).values()))
    assert "非二买" in next(iter(signal_second_buy(czsc_factory(bis + [
        bi_factory(Direction.Down, 80, 100, base, base + timedelta(minutes=4)),
        bi_factory(Direction.Down, 95, 105, base, base + timedelta(minutes=5)),
    ]), buy1_anchor=anchor).values()))

    no_retrace = bis + [
        bi_factory(Direction.Down, 94, 105, base, base + timedelta(minutes=4)),
        bi_factory(Direction.Up, 100, 130, base, base + timedelta(minutes=5)),
    ]
    anchor2 = {"dt": base + timedelta(minutes=4), "price": 94, "zs_zg": 112}
    assert "非二买" in next(iter(signal_second_buy(czsc_factory(no_retrace), buy1_anchor=anchor2).values()))

    wrong_rebound = [
        bi_factory(Direction.Down, 94, 105, base, base),
        bi_factory(Direction.Down, 95, 106, base, base),
        bi_factory(Direction.Up, 96, 120, base, base),
        bi_factory(Direction.Down, 97, 110, base, base),
        bi_factory(Direction.Up, 98, 130, base, base),
    ]
    assert "非二买" in next(iter(signal_second_buy(czsc_factory(wrong_rebound), buy1_anchor={"price": 94, "zs_zg": 112}).values()))

    wrong_retrace = [
        bi_factory(Direction.Down, 94, 105, base, base),
        bi_factory(Direction.Up, 95, 130, base, base),
        bi_factory(Direction.Up, 96, 140, base, base),
        bi_factory(Direction.Down, 97, 110, base, base),
        bi_factory(Direction.Up, 98, 130, base, base),
    ]
    assert "非二买" in next(iter(signal_second_buy(czsc_factory(wrong_retrace), buy1_anchor={"price": 94, "zs_zg": 112}).values()))

    no_retrace_at_tail = [
        bi_factory(Direction.Up, 90, 120, base, base),
        bi_factory(Direction.Up, 91, 121, base, base),
        bi_factory(Direction.Up, 92, 122, base, base),
        bi_factory(Direction.Down, 94, 105, base, base),
        bi_factory(Direction.Up, 95, 130, base, base),
    ]
    assert "非二买" in next(iter(signal_second_buy(czsc_factory(no_retrace_at_tail), buy1_anchor={"price": 94, "zs_zg": 112}).values()))

    bad_confirm = [
        bi_factory(Direction.Up, 90, 120, base, base),
        bi_factory(Direction.Down, 94, 105, base, base),
        bi_factory(Direction.Up, 95, 130, base, base),
        bi_factory(Direction.Down, 96, 120, base, base),
        bi_factory(Direction.Up, 90, 130, base, base),
    ]
    assert "非二买" in next(iter(signal_second_buy(czsc_factory(bad_confirm), buy1_anchor={"price": 94, "zs_zg": 112}).values()))

    stale = no_retrace + [
        bi_factory(Direction.Down, 96, 120, base, base + timedelta(minutes=6)),
        bi_factory(Direction.Up, 97, 125, base, base + timedelta(minutes=7)),
        bi_factory(Direction.Down, 98, 122, base, base + timedelta(minutes=8)),
    ]
    assert "非二买" in next(iter(signal_second_buy(czsc_factory(stale), buy1_anchor=anchor2).values()))

    stale_clean = [
        bi_factory(Direction.Up, 90, 120, base, base),
        bi_factory(Direction.Down, 94, 105, base, base),
        bi_factory(Direction.Up, 95, 130, base, base),
        bi_factory(Direction.Down, 96, 120, base, base),
        bi_factory(Direction.Up, 97, 130, base, base),
        bi_factory(Direction.Down, 98, 125, base, base),
    ]
    assert "非二买" in next(iter(signal_second_buy(czsc_factory(stale_clean), buy1_anchor={"price": 94, "zs_zg": 112}).values()))

    assert "非三买" in next(iter(signal_third_buy(czsc_factory(zbase(base, bi_factory))).values()))
    no_up_leave = zbase(base, bi_factory) + [bi_factory(Direction.Down, 80, 100, base, base + timedelta(minutes=4))]
    assert "非三买" in next(iter(signal_third_buy(czsc_factory(no_up_leave)).values()))
    leave_then_up = zbase(base, bi_factory) + [
        bi_factory(Direction.Up, 130, 150, base, base + timedelta(minutes=4)),
        bi_factory(Direction.Up, 151, 160, base, base + timedelta(minutes=5)),
    ]
    assert "离开中枢" in next(iter(signal_third_buy(czsc_factory(leave_then_up)).values()))

    zseed = zbase(base, bi_factory) + [
        bi_factory(Direction.Up, 250, 300, base, base + timedelta(minutes=4)),
        bi_factory(Direction.Down, 200, 280, base, base + timedelta(minutes=5)),
        bi_factory(Direction.Up, 112, 112, base, base + timedelta(minutes=6)),
        bi_factory(Direction.Up, 112, 112, base, base + timedelta(minutes=7)),
    ]
    assert "回抽不入中枢" in next(iter(signal_third_buy(czsc_factory(zseed)).values()))


def test_get_all_signals_and_strategy_daily_anchor_branches(czsc_factory, bi_factory, monkeypatch):
    base = datetime(2024, 1, 1)
    c = czsc_factory(zbase(base, bi_factory))
    assert len(get_all_signals(c, buy1_anchor=None)) == 13

    strategy = ChanTimingStrategy("T", enable_daily_filter=False)
    logs = []
    strategy.write_log = logs.append
    strategy._log_daily_trend({}, base)
    monkeypatch.setitem(positions_module.STRATEGY_CONFIG, "filter_freq", "日线")
    strategy._log_daily_trend({"日线_D1BI_方向V260615": "向下_任意_任意_0"}, base)
    strategy._log_daily_trend({"日线_D1BI_方向V260615": "向下_任意_任意_0"}, base)
    assert len(logs) == 1

    strategy.positions[0].pairs.append(
        {"open_dt": base, "close_dt": base, "open_price": 1, "close_price": 2, "pnl_pct": 0.1, "bars_held": 1}
    )
    assert strategy.get_combined_trades()[0]["strategy"] == strategy.positions[0].name

    fallback = ChanTimingStrategy("T", enable_daily_filter=False)
    fallback._last_buy1_anchor = {"dt": base, "price": 200, "zs_zd": None, "zs_zg": None}
    fallback.update({}, 100, base, czsc_obj=czsc_factory(zbase(base, bi_factory)))
    assert fallback._last_buy1_anchor["zs_zd"] is not None

    matched = ChanTimingStrategy("T", enable_daily_filter=False)
    matched._last_buy1_anchor = {"dt": base, "price": 80, "zs_zd": None, "zs_zg": None}
    matched.update({}, 100, base, czsc_obj=czsc_factory(zbase(base, bi_factory)))
    assert matched._last_buy1_anchor["zs_zd"] is not None
