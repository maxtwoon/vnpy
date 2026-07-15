from datetime import datetime, timedelta

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


def _set_config_keys(STRATEGY_CONFIG, overrides):
    saved = {}
    for key, value in overrides.items():
        saved[key] = STRATEGY_CONFIG.get(key)
        STRATEGY_CONFIG[key] = value
    return saved


def _restore_config_keys(STRATEGY_CONFIG, saved):
    for key, value in saved.items():
        if value is None:
            STRATEGY_CONFIG.pop(key, None)
        else:
            STRATEGY_CONFIG[key] = value


def test_generate_report_mode_label_research_baseline():
    from chan_strategy.config import STRATEGY_CONFIG

    saved = _set_config_keys(
        STRATEGY_CONFIG,
        {"sizing_model": "research", "limit_halt_model": "off", "portfolio_risk": "off"},
    )
    try:
        engine = BacktestEngine("T", initial_capital=1000)
        engine.equity_curve = [{"dt": datetime(2024, 1, 1), "equity": 1000, "price": 1, "positions": 0}]
        engine.strategy = FakeStrategy([])
        report = engine.generate_report()
        assert report["mode_label"] == "RESEARCH_BASELINE"
        assert report["limit_halt_model"] == "off"
        assert report["portfolio_risk"] == "off"
    finally:
        _restore_config_keys(STRATEGY_CONFIG, saved)


@pytest.mark.parametrize(
    "overrides,expected_label",
    [
        ({"sizing_model": "risk"}, "PARTIAL_PRODUCTION_FEATURES(sizing_model=risk)"),
        ({"limit_halt_model": "enforce"}, "PARTIAL_PRODUCTION_FEATURES(limit_halt_model=enforce)"),
        ({"portfolio_risk": "on"}, "PARTIAL_PRODUCTION_FEATURES(portfolio_risk=on)"),
        (
            {"sizing_model": "risk", "limit_halt_model": "enforce"},
            "PARTIAL_PRODUCTION_FEATURES(sizing_model=risk,limit_halt_model=enforce)",
        ),
        (
            {"sizing_model": "risk", "portfolio_risk": "on"},
            "PARTIAL_PRODUCTION_FEATURES(sizing_model=risk,portfolio_risk=on)",
        ),
        (
            {"limit_halt_model": "aware", "portfolio_risk": "on"},
            "PARTIAL_PRODUCTION_FEATURES(limit_halt_model=aware,portfolio_risk=on)",
        ),
        (
            {"sizing_model": "risk", "limit_halt_model": "enforce", "portfolio_risk": "on"},
            "PARTIAL_PRODUCTION_FEATURES(sizing_model=risk,limit_halt_model=enforce,portfolio_risk=on)",
        ),
    ],
)
def test_generate_report_mode_label_names_deviating_dimensions(overrides, expected_label):
    from chan_strategy.config import STRATEGY_CONFIG

    saved = _set_config_keys(STRATEGY_CONFIG, overrides)
    try:
        engine = BacktestEngine("T", initial_capital=1000)
        engine.equity_curve = [{"dt": datetime(2024, 1, 1), "equity": 1000, "price": 1, "positions": 0}]
        engine.strategy = FakeStrategy([])
        report = engine.generate_report()
        assert report["mode_label"] == expected_label
    finally:
        _restore_config_keys(STRATEGY_CONFIG, saved)


def test_print_report_shows_mode_label_and_research_baseline_disclaimer(capsys):
    engine = BacktestEngine("T", initial_capital=1000)
    engine.equity_curve = [{"dt": datetime(2024, 1, 1), "equity": 1000, "price": 1, "positions": 0}]
    engine.strategy = FakeStrategy([])
    report = engine.generate_report()
    engine.print_report(report)
    out = capsys.readouterr().out
    assert "模式标签: RESEARCH_BASELINE" in out
    assert "本报告为 RESEARCH_BASELINE（研究基线），不构成生产/可交易证据" in out


def test_print_report_shows_non_baseline_mode_label(capsys):
    from chan_strategy.config import STRATEGY_CONFIG

    saved = _set_config_keys(STRATEGY_CONFIG, {"sizing_model": "risk"})
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
        engine.print_report(report)
        out = capsys.readouterr().out
        assert "模式标签: PARTIAL_PRODUCTION_FEATURES(sizing_model=risk)" in out
        assert "RESEARCH_BASELINE" not in out
    finally:
        _restore_config_keys(STRATEGY_CONFIG, saved)
