"""Unit tests for A37 exit-event restructure (Phases 1 and 2)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from czsc.objects import Direction

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.positions import (
    create_first_buy_position,
    create_first_sell_position,
    create_second_buy_position,
    create_second_sell_position,
    create_third_buy_position,
    create_third_sell_position,
)
from chan_strategy.validation import EXHAUSTIVE_SIGNAL_CATEGORIES
from diagnostics.phase1_dead_factor_equivalence import _baseline_factories, _diff_trades


def _exit_factors_contain_signal(position, signal_fragment: str) -> bool:
    """Return True if any exit-event factor contains ``signal_fragment``."""
    return any(
        signal_fragment in signal.value
        for event in position.exits
        for factor in event.factors
        for signal in factor.signals_all + factor.signals_any + factor.signals_not
    )


def _event_signals_any(event) -> list[str]:
    """Return all signal values referenced by an event at event level."""
    return [signal.value for signal in event.signals_any]


# ---------------------------------------------------------------------------
# Phase 1: dead-factor removal
# ---------------------------------------------------------------------------


def test_second_buy_exit_has_no_dead_divergence_failure_factor() -> None:
    """The removed dead factor '方向反转且在中枢内' must not appear in 二买平多."""
    pos = create_second_buy_position("TEST", enable_daily_filter=False)
    assert len(pos.exits) >= 1
    assert not _exit_factors_contain_signal(pos, "背驰V260615_失效")
    factor_names = {f.name for f in pos.exits[0].factors}
    assert "方向反转且在中枢内" not in factor_names


def test_second_sell_exit_has_no_dead_divergence_failure_factor() -> None:
    """The removed dead factor '方向反转且在中枢内' must not appear in 二卖平空."""
    pos = create_second_sell_position("TEST", enable_daily_filter=False)
    assert len(pos.exits) >= 1
    assert not _exit_factors_contain_signal(pos, "背驰V260615_失效")
    factor_names = {f.name for f in pos.exits[0].factors}
    assert "方向反转且在中枢内" not in factor_names


def test_strict_factory_rejects_consecutive_same_direction_bis(
    strict_czsc_factory, bi_factory
) -> None:
    """Confirmed BI directions must alternate; consecutive same direction is invalid."""
    base = datetime(2024, 1, 1)
    with pytest.raises(ValueError, match="directions must alternate"):
        strict_czsc_factory([
            bi_factory(Direction.Up, 90, 120, base, base + timedelta(minutes=1)),
            bi_factory(Direction.Up, 91, 121, base, base + timedelta(minutes=2)),
        ])


# ---------------------------------------------------------------------------
# Phase 2: legacy mode keeps Phase 1 event structures
# ---------------------------------------------------------------------------


@pytest.fixture
def ensure_legacy_semantics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force exit_event_semantics to legacy for the duration of a test."""
    monkeypatch.setitem(STRATEGY_CONFIG, "exit_event_semantics", "legacy")


@pytest.mark.parametrize("factory", [
    create_first_buy_position,
    create_second_buy_position,
    create_third_buy_position,
    create_first_sell_position,
    create_second_sell_position,
    create_third_sell_position,
])
def test_legacy_mode_emits_single_exit_event(factory, ensure_legacy_semantics) -> None:
    """Legacy semantics must keep the Phase 1 single-event structure."""
    pos = factory("TEST", enable_daily_filter=False)
    assert len(pos.exits) == 1
    assert pos.exits[0].signals_all == []
    assert pos.exits[0].signals_not == []
    assert pos.exits[0].factors


@pytest.mark.parametrize("factory", [
    create_second_buy_position,
    create_second_sell_position,
])
def test_legacy_mode_has_no_dead_factor(factory, ensure_legacy_semantics) -> None:
    """Legacy mode is behavior-identical to Phase 1: no dead divergence factor."""
    pos = factory("TEST", enable_daily_filter=False)
    assert not _exit_factors_contain_signal(pos, "背驰V260615_失效")


# ---------------------------------------------------------------------------
# Phase 2: restructured mode emits two independent exit events
# ---------------------------------------------------------------------------


@pytest.fixture
def restructured_semantics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force exit_event_semantics to restructured for the duration of a test."""
    monkeypatch.setitem(STRATEGY_CONFIG, "exit_event_semantics", "restructured")


@pytest.mark.parametrize("factory", [
    create_first_buy_position,
    create_second_buy_position,
    create_third_buy_position,
    create_first_sell_position,
    create_second_sell_position,
    create_third_sell_position,
])
def test_restructured_mode_emits_two_exit_events(factory, restructured_semantics) -> None:
    """Restructured semantics emits exactly two exit events per position."""
    pos = factory("TEST", enable_daily_filter=False)
    assert len(pos.exits) == 2
    names = {e.name for e in pos.exits}
    assert any("结构" in n for n in names)
    assert any("方向" in n for n in names)


@pytest.mark.parametrize("factory, structural_key", [
    (create_first_buy_position, "30分钟_D1BSP_风控RV260615"),
    (create_second_buy_position, "30分钟_D1BSP_风控RV260615"),
    (create_third_buy_position, "30分钟_D1BSP_风控RV260615"),
    (create_first_sell_position, "30分钟_D1BSP_空头风控RV260615"),
    (create_second_sell_position, "30分钟_D1BSP_空头风控RV260615"),
    (create_third_sell_position, "30分钟_D1BSP_空头风控RV260615"),
])
def test_restructured_structural_event_is_standalone(
    factory, structural_key: str, restructured_semantics
) -> None:
    """The structural exit event has no factors and gates on recent-mode structural failure."""
    pos = factory("TEST", enable_daily_filter=False)
    struct_event = next(e for e in pos.exits if "结构" in e.name)
    assert struct_event.factors == []
    assert any(structural_key in s.key for s in struct_event.signals_any)
    assert any("结构失效" in s.value for s in struct_event.signals_any)


def test_restructured_first_buy_keeps_oscillation_gate(restructured_semantics) -> None:
    """一买平多 structural event also keeps the segment-mode 震荡超限 gate."""
    pos = create_first_buy_position("TEST", enable_daily_filter=False)
    struct_event = next(e for e in pos.exits if "结构" in e.name)
    signals_any = _event_signals_any(struct_event)
    assert any("风控V260615_震荡超限" in v for v in signals_any)


def test_restructured_first_sell_keeps_oscillation_gate(restructured_semantics) -> None:
    """一卖平空 structural event also keeps the segment-mode 震荡超限 gate."""
    pos = create_first_sell_position("TEST", enable_daily_filter=False)
    struct_event = next(e for e in pos.exits if "结构" in e.name)
    signals_any = _event_signals_any(struct_event)
    assert any("空头风控V260615_震荡超限" in v for v in signals_any)


@pytest.mark.parametrize("factory", [
    create_first_buy_position,
    create_second_buy_position,
    create_third_buy_position,
    create_first_sell_position,
    create_second_sell_position,
    create_third_sell_position,
])
def test_restructured_directional_event_has_no_signals_any_gate(
    factory, restructured_semantics
) -> None:
    """The directional exit event must fire standalone (no event-level signals_any gate)."""
    pos = factory("TEST", enable_daily_filter=False)
    dir_event = next(e for e in pos.exits if "方向" in e.name)
    assert dir_event.signals_all == []
    assert dir_event.signals_any == []
    assert dir_event.signals_not == []
    assert dir_event.factors


# ---------------------------------------------------------------------------
# Phase 2: validation and reporting
# ---------------------------------------------------------------------------


def test_validation_exhaustiveness_includes_new_recent_risk_keys() -> None:
    """validation.py must register the new recent-mode risk signal keys."""
    assert "D1BSP_风控RV260615" in EXHAUSTIVE_SIGNAL_CATEGORIES
    assert "D1BSP_空头风控RV260615" in EXHAUSTIVE_SIGNAL_CATEGORIES
    expected = ["结构完好", "结构失效", "震荡超限"]
    assert EXHAUSTIVE_SIGNAL_CATEGORIES["D1BSP_风控RV260615"] == expected
    assert EXHAUSTIVE_SIGNAL_CATEGORIES["D1BSP_空头风控RV260615"] == expected


def test_backtest_report_header_includes_exit_event_semantics() -> None:
    """generate_report / print_report expose the active exit_event_semantics value."""
    engine = BacktestEngine(
        symbol="TEST",
        freq="1",
        start_date="2024-01-01",
        end_date="2024-01-02",
    )
    engine.bars = []
    engine.equity_curve = [
        {"dt": datetime(2024, 1, 1), "price": 100.0, "equity": 1000000.0},
        {"dt": datetime(2024, 1, 2), "price": 101.0, "equity": 1000000.0},
    ]

    class _FakeStrategy:
        def evaluate_all(self) -> dict[str, dict[str, Any]]:
            return {}

        def get_combined_trades(self) -> list[dict[str, Any]]:
            return []

    engine.strategy = _FakeStrategy()
    report = engine.generate_report()
    assert report["exit_event_semantics"] == STRATEGY_CONFIG.get("exit_event_semantics", "legacy")


# ---------------------------------------------------------------------------
# Phase 2: legacy default is behavior-equivalent to Phase 1 baseline
# ---------------------------------------------------------------------------


def _run_synthetic_second_buy_trades(factory) -> list[dict[str, Any]]:
    """Drive a 二买多头 position through open/close using synthetic signals.

    The close is triggered by the non-dead directional factor so that the dead
    factor (if present) cannot alter the outcome.
    """
    pos = factory("TEST", enable_daily_filter=False)
    dt = datetime(2024, 1, 1, 9, 0)
    # Open long via 二买确认 + 方向向上 + 中枢内
    open_signals = {
        "30分钟_D1ZS_数据状态V260615": "充分_任意_任意_100",
        "30分钟_D1ZS_结构状态V260615": "已确认_任意_任意_80",
        "30分钟_D1BSP_二买V260615": "二买确认_任意_任意_75",
        "30分钟_D1BI_方向V260615": "向上_任意_任意_50",
        "30分钟_D1ZS_位置V260615": "中枢内_任意_任意_50",
    }
    pos.update(open_signals, price=100.0, dt=dt, execution_price=100.0)
    assert pos.pos == 1

    # Close via structural signal + direction down + position below center
    close_signals = {
        "30分钟_D1BSP_风控V260615": "结构失效_任意_任意_95",
        "30分钟_D1BI_方向V260615": "向下_任意_任意_50",
        "30分钟_D1ZS_位置V260615": "中枢下方_任意_任意_30",
    }
    pos.update(close_signals, price=99.0, dt=dt + timedelta(hours=1), execution_price=99.0)
    assert pos.pos == 0
    for pair in pos.pairs:
        pair["strategy"] = "二买多头"
    return pos.pairs


def test_legacy_default_produces_empty_diff_vs_phase1_baseline() -> None:
    """Legacy mode (default) must be behavior-equivalent to the Phase 1 baseline."""
    assert STRATEGY_CONFIG.get("exit_event_semantics") == "legacy"
    current_pairs = _run_synthetic_second_buy_trades(create_second_buy_position)

    with _baseline_factories():
        baseline_pairs = _run_synthetic_second_buy_trades(create_second_buy_position)

    diff = _diff_trades(baseline_pairs, current_pairs)
    assert diff["summary"]["removed_count"] == 0
    assert diff["summary"]["added_count"] == 0
    assert diff["summary"]["changed_count"] == 0
