from datetime import datetime

from chan_strategy.backtest_engine import BacktestEngine


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
