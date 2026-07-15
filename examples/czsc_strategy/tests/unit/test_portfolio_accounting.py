from datetime import datetime

import pytest

import chan_strategy.backtest_engine as backtest_module
from chan_strategy.backtest_engine import BacktestEngine


class FakeCZSC:
    def __init__(self, bars):
        self.bars = list(bars)
        self.bi_list = []

    def update(self, bar):
        self.bars.append(bar)


class FakePosition:
    def __init__(self, name):
        self.name = name
        self.pos = 0
        self.cost = 0
        self.pairs = []

    def evaluate(self):
        return {"total_trades": len(self.pairs), "win_rate": 0, "profit_factor": 0}


class FakeStrategy:
    def __init__(
        self, symbol, freq, commission_rate, slippage,
        enable_daily_filter, enable_short=None,
    ):
        self.positions = [
            FakePosition("一买多头"),
            FakePosition("二买多头"),
            FakePosition("三买多头"),
        ]
        self.update_count = 0

    def update(self, signals, price, dt, execution_price=None, czsc_obj=None,
               bar_high=None, bar_low=None, equity_at_entry=None,
               total_open_margin=None, rollover_open_blocked=False):
        self.update_count += 1
        if self.update_count == 1:
            self.positions[0].pairs.append({"open_dt": dt, "close_dt": dt, "pnl_pct": 0.10, "bars_held": 1})
        elif self.update_count == 2:
            self.positions[1].pairs.append({"open_dt": dt, "close_dt": dt, "pnl_pct": 0.10, "bars_held": 1})
        elif self.update_count == 3:
            self.positions[2].pairs.append({"open_dt": dt, "close_dt": dt, "pnl_pct": -0.05, "bars_held": 1})

    def get_last_buy1_anchor(self):
        return None

    def get_last_sell1_anchor(self):
        return None

    def evaluate_all(self):
        return {p.name: p.evaluate() for p in self.positions}

    def get_combined_trades(self):
        trades = []
        for pos in self.positions:
            for pair in pos.pairs:
                item = pair.copy()
                item["strategy"] = pos.name
                trades.append(item)
        return trades


def test_portfolio_weighted_realized_pnl_golden_number(monkeypatch, synthetic_1m_bars):
    bars = synthetic_1m_bars(days=1, per_day=120, start=datetime(2024, 1, 2, 9, 0))
    engine = BacktestEngine("TEST", initial_capital=1_000_000)

    def fake_load_data():
        engine.bars = bars
        return True

    monkeypatch.setattr(engine, "load_data", fake_load_data)
    monkeypatch.setattr(backtest_module, "CZSC", FakeCZSC)
    monkeypatch.setattr(backtest_module, "ChanTimingStrategy", FakeStrategy)
    monkeypatch.setattr(backtest_module, "get_all_signals", lambda *args, **kwargs: {})
    monkeypatch.setitem(backtest_module.STRATEGY_CONFIG, "trade_freq", "1分钟")
    monkeypatch.setitem(backtest_module.STRATEGY_CONFIG, "filter_freq", "日线")
    monkeypatch.setitem(backtest_module.STRATEGY_CONFIG, "pos_1buy", 0.10)
    monkeypatch.setitem(backtest_module.STRATEGY_CONFIG, "pos_2buy", 0.20)
    monkeypatch.setitem(backtest_module.STRATEGY_CONFIG, "pos_3buy", 0.30)

    report = engine.run(warmup_bars=100)

    # 1buy: 0.10 * 1,000,000 * 10% = +10,000
    # 2buy: 0.20 * 1,000,000 * 10% = +20,000
    # 3buy: 0.30 * 1,000,000 * -5% = -15,000
    # Total realized PnL = +15,000
    assert report["final_equity"] == pytest.approx(1_015_000)
    assert engine._cum_realized_pnl == {
        "一买多头": pytest.approx(10_000),
        "二买多头": pytest.approx(20_000),
        "三买多头": pytest.approx(-15_000),
    }
    assert engine._pair_counts == {"一买多头": 1, "二买多头": 1, "三买多头": 1}
