from datetime import datetime

import chan_strategy.backtest_engine as backtest_module
from chan_strategy.backtest_engine import BacktestEngine


class _RecordingStrategy:
    def __init__(self, *args, **kwargs) -> None:
        self.updates = []
        self.positions = []

    def update(self, signals, price, dt, **kwargs):
        self.updates.append({
            "signals": dict(signals),
            "price": price,
            "dt": dt,
            "execution_price": kwargs.get("execution_price"),
        })

    def get_position_status(self):
        return {"open_positions": 0}

    def get_last_buy1_anchor(self):
        return None

    def get_last_sell1_anchor(self):
        return None

    def evaluate_all(self):
        return {}

    def get_combined_trades(self):
        return []


def test_backtest_run_is_idempotent_with_mini_fixture(mini_backtest_bars):
    engine = BacktestEngine("TEST", db_path="none")
    engine.load_data = lambda: setattr(engine, "bars", mini_backtest_bars) or True
    r1 = engine.run(warmup_bars=5)
    c1 = list(engine.equity_curve)
    r2 = engine.run(warmup_bars=5)
    assert "error" not in r1
    assert r1["total_trades"] == r2["total_trades"]
    assert c1 == engine.equity_curve


def test_short_data_error(mini_backtest_bars):
    engine = BacktestEngine("TEST", db_path="none")
    engine.load_data = lambda: setattr(engine, "bars", mini_backtest_bars[:50]) or True
    assert "error" in engine.run(warmup_bars=5)


def test_signal_generated_on_bar_executes_next_bar_open(monkeypatch, mini_backtest_bars):
    warmup_bars = 5
    calls = 0

    def fake_get_all_signals(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"1buy": True}
        return {}

    strategy = _RecordingStrategy()
    engine = BacktestEngine("TEST", db_path="none")
    engine.load_data = lambda: setattr(engine, "bars", mini_backtest_bars) or True

    monkeypatch.setattr(backtest_module, "get_all_signals", fake_get_all_signals)
    monkeypatch.setattr(backtest_module, "ChanTimingStrategy", lambda *args, **kwargs: strategy)

    result = engine.run(warmup_bars=warmup_bars)

    assert "error" not in result
    signal_bar = engine.trade_bars[warmup_bars]
    expected_execution_bar = engine.trade_bars[warmup_bars + 1]
    assert strategy.updates[0]["signals"] == {}
    assert strategy.updates[0]["dt"] == signal_bar.dt
    assert strategy.updates[1]["signals"] == {"1buy": True}
    assert strategy.updates[1]["dt"] == expected_execution_bar.dt
    assert strategy.updates[1]["execution_price"] == expected_execution_bar.open
