"""A74 — Formal-evaluation entry point unit tests.

Validates that the new formal-evaluation path overrides
``sizing_model="risk"`` and ``limit_halt_model="enforce"`` for the
run, leaves ``config.py`` defaults untouched, and restores the original
values even on exception.

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

import pytest

from chan_strategy.backtest_engine import (
    BacktestEngine,
    assert_not_research_baseline,
    formal_evaluation_config,
    run_formal_evaluation,
)
from chan_strategy.config import STRATEGY_CONFIG


@pytest.fixture(autouse=True)
def restore_config():
    """Snapshot and restore the whole STRATEGY_CONFIG so tests never leak."""
    original = dict(STRATEGY_CONFIG)
    yield
    STRATEGY_CONFIG.clear()
    STRATEGY_CONFIG.update(original)


# ------------------------------------------------------------------ context manager


def test_formal_evaluation_config_sets_risk_enforce_and_rollover_gating():
    STRATEGY_CONFIG["sizing_model"] = "research"
    STRATEGY_CONFIG["limit_halt_model"] = "off"
    STRATEGY_CONFIG["rollover_open_gating"] = "off"
    STRATEGY_CONFIG["stop_execution_model"] = "close"
    STRATEGY_CONFIG["daily_agg"] = "natural"
    STRATEGY_CONFIG["price_tick_rounding"] = "off"

    with formal_evaluation_config():
        assert STRATEGY_CONFIG["sizing_model"] == "risk"
        assert STRATEGY_CONFIG["limit_halt_model"] == "enforce"
        assert STRATEGY_CONFIG["rollover_open_gating"] == "on"
        assert STRATEGY_CONFIG["stop_execution_model"] == "intrabar"
        assert STRATEGY_CONFIG["daily_agg"] == "trading_calendar"
        assert STRATEGY_CONFIG["price_tick_rounding"] == "on"


def test_formal_evaluation_config_restores_original_values_on_success():
    STRATEGY_CONFIG["sizing_model"] = "research"
    STRATEGY_CONFIG["limit_halt_model"] = "off"
    STRATEGY_CONFIG["rollover_open_gating"] = "off"
    STRATEGY_CONFIG["stop_execution_model"] = "close"
    STRATEGY_CONFIG["daily_agg"] = "natural"
    STRATEGY_CONFIG["price_tick_rounding"] = "off"

    with formal_evaluation_config():
        pass

    assert STRATEGY_CONFIG["sizing_model"] == "research"
    assert STRATEGY_CONFIG["limit_halt_model"] == "off"
    assert STRATEGY_CONFIG["rollover_open_gating"] == "off"
    assert STRATEGY_CONFIG["stop_execution_model"] == "close"
    assert STRATEGY_CONFIG["daily_agg"] == "natural"
    assert STRATEGY_CONFIG["price_tick_rounding"] == "off"


def test_formal_evaluation_config_restores_original_values_on_exception():
    STRATEGY_CONFIG["sizing_model"] = "research"
    STRATEGY_CONFIG["limit_halt_model"] = "off"
    STRATEGY_CONFIG["rollover_open_gating"] = "off"
    STRATEGY_CONFIG["stop_execution_model"] = "close"
    STRATEGY_CONFIG["daily_agg"] = "natural"
    STRATEGY_CONFIG["price_tick_rounding"] = "off"

    class CustomError(Exception):
        pass

    with pytest.raises(CustomError):
        with formal_evaluation_config():
            assert STRATEGY_CONFIG["sizing_model"] == "risk"
            assert STRATEGY_CONFIG["limit_halt_model"] == "enforce"
            assert STRATEGY_CONFIG["rollover_open_gating"] == "on"
            assert STRATEGY_CONFIG["stop_execution_model"] == "intrabar"
            assert STRATEGY_CONFIG["daily_agg"] == "trading_calendar"
            assert STRATEGY_CONFIG["price_tick_rounding"] == "on"
            raise CustomError("boom")

    assert STRATEGY_CONFIG["sizing_model"] == "research"
    assert STRATEGY_CONFIG["limit_halt_model"] == "off"
    assert STRATEGY_CONFIG["rollover_open_gating"] == "off"
    assert STRATEGY_CONFIG["stop_execution_model"] == "close"
    assert STRATEGY_CONFIG["daily_agg"] == "natural"
    assert STRATEGY_CONFIG["price_tick_rounding"] == "off"


def test_formal_evaluation_config_restores_non_default_original_values():
    """If the caller already had non-default values, they must be preserved."""
    STRATEGY_CONFIG["sizing_model"] = "risk"
    STRATEGY_CONFIG["limit_halt_model"] = "aware"
    STRATEGY_CONFIG["rollover_open_gating"] = "on"
    STRATEGY_CONFIG["stop_execution_model"] = "intrabar"
    STRATEGY_CONFIG["daily_agg"] = "trading_calendar"
    STRATEGY_CONFIG["price_tick_rounding"] = "off"

    with formal_evaluation_config():
        assert STRATEGY_CONFIG["sizing_model"] == "risk"
        assert STRATEGY_CONFIG["limit_halt_model"] == "enforce"
        assert STRATEGY_CONFIG["rollover_open_gating"] == "on"
        assert STRATEGY_CONFIG["stop_execution_model"] == "intrabar"
        assert STRATEGY_CONFIG["daily_agg"] == "trading_calendar"
        assert STRATEGY_CONFIG["price_tick_rounding"] == "on"

    assert STRATEGY_CONFIG["sizing_model"] == "risk"
    assert STRATEGY_CONFIG["limit_halt_model"] == "aware"
    assert STRATEGY_CONFIG["rollover_open_gating"] == "on"
    assert STRATEGY_CONFIG["stop_execution_model"] == "intrabar"
    assert STRATEGY_CONFIG["daily_agg"] == "trading_calendar"
    assert STRATEGY_CONFIG["price_tick_rounding"] == "off"


def test_formal_evaluation_config_overrides_and_restores_daily_agg():
    """Dedicated coverage for the A79 daily_agg trading_calendar override."""
    STRATEGY_CONFIG["daily_agg"] = "natural"

    with formal_evaluation_config():
        assert STRATEGY_CONFIG["daily_agg"] == "trading_calendar"

    assert STRATEGY_CONFIG["daily_agg"] == "natural"


# --------------------------------------------------------------- entry point behavior


def test_run_formal_evaluation_uses_risk_and_enforce(monkeypatch):
    """The entry point runs under risk+enforce and reports a non-baseline label."""
    seen: list[dict] = []

    def fake_run(self):
        seen.append({
            "sizing_model": STRATEGY_CONFIG.get("sizing_model"),
            "limit_halt_model": STRATEGY_CONFIG.get("limit_halt_model"),
            "rollover_open_gating": STRATEGY_CONFIG.get("rollover_open_gating"),
            "stop_execution_model": STRATEGY_CONFIG.get("stop_execution_model"),
            "daily_agg": STRATEGY_CONFIG.get("daily_agg"),
        })
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

    # Pre-condition: defaults are untouched.
    assert STRATEGY_CONFIG["sizing_model"] == "research"
    assert STRATEGY_CONFIG["limit_halt_model"] == "off"
    assert STRATEGY_CONFIG["rollover_open_gating"] == "off"
    assert STRATEGY_CONFIG["stop_execution_model"] == "close"
    assert STRATEGY_CONFIG["daily_agg"] == "natural"

    report = run_formal_evaluation("AP888", table_name="ap888_1M_raw")

    # The fake run saw the overridden values.
    assert len(seen) == 1
    assert seen[0]["sizing_model"] == "risk"
    assert seen[0]["limit_halt_model"] == "enforce"
    assert seen[0]["rollover_open_gating"] == "on"
    assert seen[0]["stop_execution_model"] == "intrabar"
    assert seen[0]["daily_agg"] == "trading_calendar"

    # The entry point returns the report from run_single_backtest.
    assert report["symbol"] == "AP888"

    # Post-condition: defaults are restored.
    assert STRATEGY_CONFIG["sizing_model"] == "research"
    assert STRATEGY_CONFIG["limit_halt_model"] == "off"
    assert STRATEGY_CONFIG["rollover_open_gating"] == "off"
    assert STRATEGY_CONFIG["stop_execution_model"] == "close"
    assert STRATEGY_CONFIG["daily_agg"] == "natural"


def test_run_formal_evaluation_mode_label_is_non_baseline(monkeypatch):
    """A formal run's generate_report must not label the output as RESEARCH_BASELINE."""
    from datetime import datetime

    monkeypatch.setattr(BacktestEngine, "run", lambda self: {"ok": True})
    monkeypatch.setattr(BacktestEngine, "print_report", lambda self, report=None: None)

    engine = BacktestEngine("T", initial_capital=1000)
    engine.bars = []
    engine.equity_curve = [
        {"dt": datetime(2024, 1, 1), "equity": 1000, "price": 1, "positions": 0},
    ]

    class FakeStrategy:
        def evaluate_all(self):
            return {"fake": {"total_trades": 0, "win_rate": 0, "profit_factor": 0}}

        def get_combined_trades(self):
            return []

    engine.strategy = FakeStrategy()

    with formal_evaluation_config():
        report = engine.generate_report()

    assert report["sizing_model"] == "risk"
    assert report["limit_halt_model"] == "enforce"
    assert report["stop_execution_model"] == "intrabar"
    assert report["price_tick_rounding"] == "on"
    assert report["mode_label"] == (
        "PARTIAL_PRODUCTION_FEATURES(sizing_model=risk,limit_halt_model=enforce,rollover_open_gating=on)"
    )


def test_formal_report_discloses_limit_halt_touch_based_methodology(monkeypatch):
    """Formal reports must disclose the conservative high/low touch-based limit-halt model."""
    from datetime import datetime

    monkeypatch.setattr(BacktestEngine, "run", lambda self: {"ok": True})
    monkeypatch.setattr(BacktestEngine, "print_report", lambda self, report=None: None)

    engine = BacktestEngine("T", initial_capital=1000)
    engine.bars = []
    engine.equity_curve = [
        {"dt": datetime(2024, 1, 1), "equity": 1000, "price": 1, "positions": 0},
    ]

    class FakeStrategy:
        positions = []

        def evaluate_all(self):
            return {"fake": {"total_trades": 0, "win_rate": 0, "profit_factor": 0}}

        def get_combined_trades(self):
            return []

    engine.strategy = FakeStrategy()

    with formal_evaluation_config():
        report = engine.generate_report()

    methodology = report["limit_halt_methodology"]
    assert "high/low" in methodology
    assert "touch" in methodology
    assert "conservative" in methodology


def test_formal_report_discloses_limit_halt_temporary_window_verification_status(monkeypatch):
    """Formal reports must disclose that temporary widening windows need human verification."""
    from datetime import datetime

    monkeypatch.setattr(BacktestEngine, "run", lambda self: {"ok": True})
    monkeypatch.setattr(BacktestEngine, "print_report", lambda self, report=None: None)

    engine = BacktestEngine("T", initial_capital=1000)
    engine.bars = []
    engine.equity_curve = [
        {"dt": datetime(2024, 1, 1), "equity": 1000, "price": 1, "positions": 0},
    ]

    class FakeStrategy:
        positions = []

        def evaluate_all(self):
            return {"fake": {"total_trades": 0, "win_rate": 0, "profit_factor": 0}}

        def get_combined_trades(self):
            return []

    engine.strategy = FakeStrategy()

    with formal_evaluation_config():
        report = engine.generate_report()

    assert report["limit_halt_temporary_widening_status"] == "manual_confirmation_required"
    assert "temporary_widening_windows" in report["limit_halt_rule_caveat"]
    assert "not independently verified" in report["limit_halt_rule_caveat"]
    assert "primary exchange notice" in report["limit_halt_rule_caveat"]


def test_formal_report_discloses_margin_model_limitations(monkeypatch):
    """Risk-mode reports must expose margin-source and no-maintenance-margin caveats."""
    from datetime import datetime

    monkeypatch.setattr(BacktestEngine, "run", lambda self: {"ok": True})
    monkeypatch.setattr(BacktestEngine, "print_report", lambda self, report=None: None)

    engine = BacktestEngine("T", initial_capital=1000)
    engine.bars = []
    engine.equity_curve = [
        {
            "dt": datetime(2024, 1, 1),
            "equity": 1000,
            "price": 1,
            "positions": 0,
            "total_open_margin": 0,
            "margin_utilization_pct": 0,
        },
    ]

    class FakeStrategy:
        positions = []

        def evaluate_all(self):
            return {"fake": {"total_trades": 0, "win_rate": 0, "profit_factor": 0}}

        def get_combined_trades(self):
            return []

    engine.strategy = FakeStrategy()

    with formal_evaluation_config():
        report = engine.generate_report()

    assert report["margin_rate_source"] == "contract_specs.exchange_minimum_research"
    assert report["maintenance_margin_model"] == "not_modeled"
    assert report["broker_forced_liquidation_model"] == "not_modeled"
    assert "maintenance" in report["margin_model_caveat"]
    assert "broker" in report["margin_model_caveat"]


def test_formal_report_discloses_single_side_slippage_cost_model(monkeypatch):
    """Formal reports must expose that slippage is modeled once per round trip."""
    from datetime import datetime

    monkeypatch.setattr(BacktestEngine, "run", lambda self: {"ok": True})
    monkeypatch.setattr(BacktestEngine, "print_report", lambda self, report=None: None)

    engine = BacktestEngine("T", initial_capital=1000)
    engine.bars = []
    engine.equity_curve = [
        {"dt": datetime(2024, 1, 1), "equity": 1000, "price": 1, "positions": 0},
    ]

    class FakeStrategy:
        positions = []

        def evaluate_all(self):
            return {"fake": {"total_trades": 0, "win_rate": 0, "profit_factor": 0}}

        def get_combined_trades(self):
            return []

    engine.strategy = FakeStrategy()

    with formal_evaluation_config():
        report = engine.generate_report()

    assert report["transaction_cost_model"] == "round_trip_commission_plus_single_side_slippage"
    assert report["round_trip_cost_formula"] == "2 * commission_rate + slippage"
    assert report["slippage_application"] == "single_side_per_round_trip"
    assert "single-side" in report["slippage_model_caveat"]
    assert "round-trip" in report["slippage_model_caveat"]


def test_formal_report_discloses_independent_long_short_overlap_policy(monkeypatch):
    """Reports must disclose how simultaneous long/short exposure is audited."""
    from datetime import datetime

    monkeypatch.setattr(BacktestEngine, "run", lambda self: {"ok": True})
    monkeypatch.setattr(BacktestEngine, "print_report", lambda self, report=None: None)

    engine = BacktestEngine("T", initial_capital=1000)
    engine.bars = []
    engine.equity_curve = [
        {
            "dt": datetime(2024, 1, 1),
            "equity": 1000,
            "price": 1,
            "positions": 0,
            "both_long_short": True,
        },
    ]

    class FakeStrategy:
        positions = []

        def evaluate_all(self):
            return {"fake": {"total_trades": 0, "win_rate": 0, "profit_factor": 0}}

        def get_combined_trades(self):
            return []

    engine.strategy = FakeStrategy()

    with formal_evaluation_config():
        report = engine.generate_report()

    assert report["both_long_short_bars"] == 1
    assert report["long_short_overlap_policy"] == "independent_long_short_substrategies"
    assert report["long_short_overlap_metric"] == "both_long_short_bars"
    assert "enable_short=True" in report["long_short_overlap_caveat"]
    assert "regime_model=\"independent\"" in report["long_short_overlap_caveat"]


# --------------------------------------------------------------- research-baseline guard


def test_assert_not_research_baseline_raises_on_research_baseline():
    with pytest.raises(ValueError):
        assert_not_research_baseline({"mode_label": "RESEARCH_BASELINE"})


def test_assert_not_research_baseline_rejects_unknown_labels():
    # Only the PARTIAL_PRODUCTION_FEATURES(...) prefix produced by
    # _compute_mode_label() is a known-safe allow-list match.
    assert_not_research_baseline({"mode_label": "PARTIAL_PRODUCTION_FEATURES(sizing_model=risk)"})
    with pytest.raises(ValueError):
        assert_not_research_baseline({"mode_label": "FORMAL_EVALUATION"})
    with pytest.raises(ValueError):
        assert_not_research_baseline({"mode_label": "SOME_TYPO"})
    with pytest.raises(ValueError):
        assert_not_research_baseline({"mode_label": ""})
    with pytest.raises(ValueError):
        assert_not_research_baseline({"mode_label": None})
    with pytest.raises(ValueError):
        assert_not_research_baseline({})
