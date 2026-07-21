"""A99: Pin the SimNow readiness Sharpe threshold at the enforced value 0.3.

Reconciles the docstring / optimization-suggestion wording with the actually
enforced check (``checks["夏普比率>=0.3"]``). These are the first tests covering
``SimNowReadinessChecker.check_readiness`` and
``generate_optimization_suggestions``.
"""
from chan_strategy.validation import (
    SimNowReadinessChecker,
    generate_optimization_suggestions,
)


SHARPE_CHECK_KEY = "夏普比率>=0.3"


def _sharpe_check(sharpe_ratio: float) -> dict:
    """Run check_readiness with a minimal report varying only sharpe_ratio."""
    report = {"sharpe_ratio": sharpe_ratio}
    result = SimNowReadinessChecker().check_readiness(report)
    return result["checks"][SHARPE_CHECK_KEY]


def _sharpe_suggestions(sharpe_ratio: float) -> list:
    """Return only Sharpe-related suggestions for the given sharpe_ratio."""
    report = {"sharpe_ratio": sharpe_ratio}
    suggestions = generate_optimization_suggestions(report, {})
    return [s for s in suggestions if "夏普" in s]


def test_check_readiness_sharpe_at_boundary_passes():
    """sharpe_ratio == 0.3 exactly passes the enforced gate."""
    check = _sharpe_check(0.3)
    assert check["passed"] is True


def test_check_readiness_sharpe_below_boundary_fails():
    """sharpe_ratio just below 0.3 fails the enforced gate."""
    check = _sharpe_check(0.29)
    assert check["passed"] is False


def test_suggestions_no_sharpe_warning_at_boundary():
    """sharpe_ratio == 0.3 passes, so no Sharpe suggestion is generated."""
    assert _sharpe_suggestions(0.3) == []


def test_suggestions_sharpe_warning_below_boundary_uses_03():
    """sharpe_ratio < 0.3 generates the Sharpe suggestion referencing <0.3."""
    suggestions = _sharpe_suggestions(0.29)
    assert len(suggestions) == 1
    assert "<0.3" in suggestions[0]
    assert "<0.5" not in suggestions[0]


# ---------------------------------------------------------------------------
# A101: hard-gate vs soft-quota semantics + fail-closed on untested hard gates
# ---------------------------------------------------------------------------


def _passing_report(**overrides) -> dict:
    """A backtest report where every report-derived check passes."""
    report = {
        "total_trades": 150,
        "win_rate": 0.50,
        "profit_factor": 1.5,
        "max_drawdown_pct": 10.0,
        "sharpe_ratio": 1.0,
    }
    report.update(overrides)
    return report


def _passing_stability_kwargs() -> dict:
    """All three stability checks + OOS explicitly supplied and passing."""
    return {
        "incremental_consistency": {"passed": True},
        "no_repaint": {"passed": True},
        "signal_freeze": {"passed": True},
        "oos_result": {
            "degradation": {"win_rate": 0.0, "profit_factor": 0.0},
            "out_sample": {"win_rate": 0.50},
        },
    }


def test_readiness_quota_win_rate_failure_still_ready():
    """A failing quota check (win_rate) does not by itself veto readiness.

    Documents the INTENTIONAL soft-quota design: conditions 5-10 only feed
    ``passed_count``; with all four hard gates passing and passed_count >= 7,
    ``ready`` stays True even though win_rate < 45%.
    """
    result = SimNowReadinessChecker().check_readiness(
        _passing_report(win_rate=0.40),
        **_passing_stability_kwargs(),
    )
    assert result["checks"]["胜率>=45%"]["passed"] is False
    # All-pass case yields 9 (条件10 is always None); the failing win_rate
    # contributes exactly one less.
    assert result["passed_count"] == 8
    assert result["ready"] is True


def test_readiness_untested_stability_check_blocks_ready():
    """Fail-closed regression: an omitted (None) hard gate must not pass.

    Two stability checks explicitly pass and signal_freeze is omitted, with
    every other check passing (passed_count == 8 >= 7). Before the A101 fix
    (``is not False``) the untested check silently counted as passing and
    ``ready`` was True; now an unproven hard gate blocks readiness.
    """
    kwargs = _passing_stability_kwargs()
    del kwargs["signal_freeze"]
    result = SimNowReadinessChecker().check_readiness(_passing_report(), **kwargs)
    assert result["checks"]["冻结快照确定性检查"]["passed"] is None
    assert result["passed_count"] == 8
    assert result["ready"] is False


def test_readiness_all_gates_passing_ready_true():
    """Positive case: ready is True when all hard gates explicitly pass."""
    result = SimNowReadinessChecker().check_readiness(
        _passing_report(),
        **_passing_stability_kwargs(),
    )
    assert result["passed_count"] == 9
    assert result["ready"] is True
