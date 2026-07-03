import pandas as pd

from chan_strategy.backtest_engine import BacktestEngine, run_batch_backtest, run_single_backtest


def test_freq_helpers_and_print_report(capsys):
    engine = BacktestEngine("T", freq="daily")
    assert engine._get_freq_name() == "日线"
    assert engine._freq_to_minutes("unknown") == 30
    assert engine._freq_name_to_czsc_freq("unknown")

    engine.print_report({"error": "boom"})
    assert "boom" in capsys.readouterr().out

    report = {
        "symbol": "T",
        "freq": "1",
        "period": "p",
        "total_bars": 1,
        "traded_bars": 1,
        "total_trades": 0,
        "final_equity": 1,
        "sub_strategies": {"a": {"total_trades": 0}},
    }
    engine.print_report(report)
    assert "T" in capsys.readouterr().out


def test_backtest_engine_accepts_enable_short():
    engine = BacktestEngine("T", enable_short=True)
    assert engine.enable_short is True


def test_run_single_and_batch_forward_enable_short(monkeypatch):
    seen = []

    def fake_run(self):
        seen.append((self.symbol, self.enable_short))
        return {
            "symbol": self.symbol,
            "total_trades": 1,
            "win_rate": 1,
            "profit_factor": 2,
            "total_return_pct": 3,
            "max_drawdown_pct": 4,
            "sharpe_ratio": 5,
        }

    monkeypatch.setattr(BacktestEngine, "run", fake_run)
    monkeypatch.setattr(BacktestEngine, "print_report", lambda self, report=None: None)

    assert run_single_backtest("A", enable_short=True)["symbol"] == "A"
    df = run_batch_backtest(["A", "B"], enable_short=True)

    assert isinstance(df, pd.DataFrame)
    assert list(df["symbol"]) == ["A", "B"]
    assert seen == [("A", True), ("A", True), ("B", True)]
