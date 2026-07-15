"""A81 — Unified acceptance gate unit tests.

Validates that ``unified_acceptance_gate`` combines the three A71 verdict
``overall_status`` values and the report ``mode_label`` into a single
top-level ``pass``/``warn``/``fail`` judgment.

RESEARCH-ONLY, not a trading recommendation.
"""
from __future__ import annotations

from chan_strategy.backtest_engine import unified_acceptance_gate


def _verdict(overall_status: str, reasons: list[str] | None = None) -> dict:
    return {"overall_status": overall_status, "reasons": reasons or []}


def test_all_pass_and_non_research_label_returns_pass() -> None:
    result = unified_acceptance_gate(
        _verdict("pass"),
        _verdict("pass"),
        _verdict("pass"),
        {"mode_label": "PARTIAL_PRODUCTION_FEATURES(sizing_model=risk)"},
    )
    assert result["overall_status"] == "pass"
    assert result["reasons"] == []


def test_any_fail_returns_fail() -> None:
    for failing in ("oos", "perturbation", "cost"):
        verdicts = {
            "oos": _verdict("pass"),
            "perturbation": _verdict("pass"),
            "cost": _verdict("pass"),
        }
        verdicts[failing] = _verdict("fail", [f"{failing} issue"])
        result = unified_acceptance_gate(
            verdicts["oos"],
            verdicts["perturbation"],
            verdicts["cost"],
            {"mode_label": "PARTIAL_PRODUCTION_FEATURES(sizing_model=risk)"},
        )
        assert result["overall_status"] == "fail", f"expected fail when {failing} fails"
        assert any(failing in reason for reason in result["reasons"])


def test_research_baseline_returns_fail_regardless_of_verdicts() -> None:
    result = unified_acceptance_gate(
        _verdict("pass"),
        _verdict("pass"),
        _verdict("pass"),
        {"mode_label": "RESEARCH_BASELINE"},
    )
    assert result["overall_status"] == "fail"
    assert any("RESEARCH_BASELINE" in reason for reason in result["reasons"])


def test_fail_overrides_warn_and_research_baseline_overrides_all() -> None:
    # First, warn with no fail -> warn.
    result = unified_acceptance_gate(
        _verdict("warn", ["drawdown expansion"]),
        _verdict("pass"),
        _verdict("pass"),
        {"mode_label": "PARTIAL_PRODUCTION_FEATURES(sizing_model=risk)"},
    )
    assert result["overall_status"] == "warn"
    assert any("oos" in reason for reason in result["reasons"])

    # Then, warn + fail -> fail.
    result = unified_acceptance_gate(
        _verdict("warn", ["drawdown expansion"]),
        _verdict("fail", ["sign flip"]),
        _verdict("pass"),
        {"mode_label": "PARTIAL_PRODUCTION_FEATURES(sizing_model=risk)"},
    )
    assert result["overall_status"] == "fail"

    # Research baseline -> fail even when all verdicts pass.
    result = unified_acceptance_gate(
        _verdict("pass"),
        _verdict("pass"),
        _verdict("pass"),
        {"mode_label": "RESEARCH_BASELINE"},
    )
    assert result["overall_status"] == "fail"


def test_warn_propagates_when_no_fail() -> None:
    for warning_source in ("oos", "perturbation", "cost"):
        verdicts = {
            "oos": _verdict("pass"),
            "perturbation": _verdict("pass"),
            "cost": _verdict("pass"),
        }
        verdicts[warning_source] = _verdict("warn", [f"{warning_source} warning"])
        result = unified_acceptance_gate(
            verdicts["oos"],
            verdicts["perturbation"],
            verdicts["cost"],
            {"mode_label": "FORMAL_EVALUATION"},
        )
        assert result["overall_status"] == "warn", f"expected warn when {warning_source} warns"
        assert any(warning_source in reason for reason in result["reasons"])


def test_missing_overall_status_defaults_to_pass() -> None:
    result = unified_acceptance_gate(
        {},
        {},
        {},
        {"mode_label": "PARTIAL_PRODUCTION_FEATURES(sizing_model=risk)"},
    )
    assert result["overall_status"] == "pass"


def test_empty_mode_label_does_not_fail() -> None:
    result = unified_acceptance_gate(
        _verdict("pass"),
        _verdict("pass"),
        _verdict("pass"),
        {"mode_label": ""},
    )
    assert result["overall_status"] == "pass"


def test_research_baseline_reason_propagates_even_with_fail_verdicts() -> None:
    result = unified_acceptance_gate(
        _verdict("fail", ["sign flip"]),
        _verdict("fail", ["parameter fragility"]),
        _verdict("fail", ["cost sign flip"]),
        {"mode_label": "RESEARCH_BASELINE"},
    )
    assert result["overall_status"] == "fail"
    # The RESEARCH_BASELINE reason is returned immediately, before verdict reasons.
    assert any("RESEARCH_BASELINE" in reason for reason in result["reasons"])
