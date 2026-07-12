from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from chan_strategy.backtest_engine import BacktestEngine


class FakeStrategy:
    def __init__(self, pairs):
        self._pairs = pairs

    def evaluate_all(self):
        return {"fake": {"total_trades": len(self._pairs), "win_rate": 0.5, "profit_factor": 2}}

    def get_combined_trades(self):
        return list(self._pairs)


def test_generate_report_golden_numbers(synthetic_1m_bars):
    engine = BacktestEngine("T", initial_capital=1000)
    engine.bars = synthetic_1m_bars(days=1, per_day=3)
    base = datetime(2024, 1, 1)
    pairs = [
        {"open_dt": base, "close_dt": base, "pnl_pct": 0.10, "bars_held": 1, "strategy": "fake"},
        {"open_dt": base, "close_dt": base + timedelta(days=1), "pnl_pct": -0.05, "bars_held": 2, "strategy": "fake"},
        {"open_dt": base, "close_dt": base + timedelta(days=2), "pnl_pct": 0.02, "bars_held": 3, "strategy": "fake"},
    ]
    engine.strategy = FakeStrategy(pairs)
    engine.equity_curve = [
        {"dt": base, "equity": 1000, "price": 1, "positions": 0},
        {"dt": base + timedelta(days=1), "equity": 1100, "price": 1, "positions": 0},
        {"dt": base + timedelta(days=2), "equity": 1040, "price": 1, "positions": 0},
    ]
    report = engine.generate_report()
    assert report["total_trades"] == 3
    assert report["win_rate"] == pytest.approx(2 / 3)
    assert report["profit_factor"] == pytest.approx(0.12 / 0.05)
    assert report["avg_bars_held"] == pytest.approx(2)
    assert report["final_equity"] == 1040
    assert report["total_return_pct"] == pytest.approx(4.0)
    assert report["max_drawdown_pct"] == pytest.approx((1100 - 1040) / 1100 * 100)


def test_generate_report_empty_and_unexecuted():
    engine = BacktestEngine("T", initial_capital=1000)
    assert "error" in engine.generate_report()
    engine.equity_curve = [{"dt": datetime(2024, 1, 1), "equity": 1000, "price": 1, "positions": 0}]
    engine.strategy = FakeStrategy([])
    report = engine.generate_report()
    assert report["total_trades"] == 0
    assert report["final_equity"] == 1000


def test_generate_report_includes_sizing_caveat_for_research():
    engine = BacktestEngine("T", initial_capital=1000)
    engine.equity_curve = [{"dt": datetime(2024, 1, 1), "equity": 1000, "price": 1, "positions": 0}]
    engine.strategy = FakeStrategy([])
    report = engine.generate_report()
    assert report["sizing_model"] == "research"
    assert report["sizing_caveat"] == (
        "当前为信号研究模式（方向型仓位+事后加权），"
        "未建模合约乘数/资金上限/复利，仅评估信号有效性。"
    )


def test_generate_report_sizing_caveat_is_none_for_risk():
    from chan_strategy.config import STRATEGY_CONFIG

    saved = STRATEGY_CONFIG.get("sizing_model")
    STRATEGY_CONFIG["sizing_model"] = "risk"
    try:
        engine = BacktestEngine("T", initial_capital=1000)
        engine.equity_curve = [
            {
                "dt": datetime(2024, 1, 1),
                "equity": 1000,
                "price": 1,
                "positions": 0,
                "total_open_margin": 0.0,
                "margin_utilization_pct": 0.0,
            }
        ]
        engine.strategy = FakeStrategy([])
        report = engine.generate_report()
        assert report["sizing_model"] == "risk"
        assert report["sizing_caveat"] is None
    finally:
        if saved is None:
            STRATEGY_CONFIG.pop("sizing_model", None)
        else:
            STRATEGY_CONFIG["sizing_model"] = saved
