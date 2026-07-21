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
