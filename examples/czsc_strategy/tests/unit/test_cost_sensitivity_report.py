import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from diagnostics.cost_sensitivity_report import (  # noqa: E402
    cost_sensitivity_gate_verdict,
)


def _result(
    baseline_ret: float = 10.0,
    x15_ret: float = 7.0,
    x2_ret: float = 4.0,
) -> dict:
    def _rep(ret: float) -> dict:
        return {"total_return_pct": ret}

    baseline = _rep(baseline_ret)
    x1_5 = _rep(x15_ret)
    x2 = _rep(x2_ret)
    rel = ((x2_ret - baseline_ret) / baseline_ret * 100) if baseline_ret != 0 else None
    return {
        "symbols": {
            "SYM": {
                "x1.0": baseline,
                "x1.5": x1_5,
                "x2.0": x2,
                "deltas": {
                    "x1.0": {
                        "delta_return_pct": 0.0,
                        "relative_return_pct": 0.0,
                    },
                    "x1.5": {
                        "delta_return_pct": x15_ret - baseline_ret,
                        "relative_return_pct": ((x15_ret - baseline_ret) / baseline_ret * 100)
                        if baseline_ret != 0 else None,
                    },
                    "x2.0": {
                        "delta_return_pct": x2_ret - baseline_ret,
                        "relative_return_pct": rel,
                    },
                },
            }
        }
    }


def test_cost_sensitivity_gate_verdict_pass() -> None:
    verdict = cost_sensitivity_gate_verdict(_result(baseline_ret=10.0, x2_ret=4.0))
    assert verdict["overall_status"] == "pass"
    assert verdict["symbols"]["SYM"]["status"] == "pass"
    assert verdict["symbols"]["SYM"]["reasons"] == []


def test_cost_sensitivity_gate_verdict_fail_on_sign_flip() -> None:
    verdict = cost_sensitivity_gate_verdict(_result(baseline_ret=10.0, x2_ret=-2.0))
    assert verdict["overall_status"] == "fail"
    assert verdict["symbols"]["SYM"]["status"] == "fail"
    assert any("sign flip" in r for r in verdict["symbols"]["SYM"]["reasons"])


def test_cost_sensitivity_gate_verdict_warn_on_extreme_erosion() -> None:
    # 2x cost erodes 95% of baseline return -> relative_return_pct = -95
    verdict = cost_sensitivity_gate_verdict(_result(baseline_ret=10.0, x2_ret=0.5))
    assert verdict["overall_status"] == "warn"
    assert verdict["symbols"]["SYM"]["status"] == "warn"
    assert any("-95.00%" in r for r in verdict["symbols"]["SYM"]["reasons"])


def test_cost_sensitivity_gate_verdict_no_warn_when_baseline_negative() -> None:
    # Baseline negative, x2 less negative -> not a sign flip, relative metric skipped
    verdict = cost_sensitivity_gate_verdict(_result(baseline_ret=-10.0, x2_ret=-2.0))
    assert verdict["overall_status"] == "pass"
    assert verdict["symbols"]["SYM"]["status"] == "pass"


def test_cost_sensitivity_gate_verdict_fail_when_baseline_negative_and_x2_positive() -> None:
    verdict = cost_sensitivity_gate_verdict(_result(baseline_ret=-10.0, x2_ret=2.0))
    assert verdict["overall_status"] == "fail"
    assert verdict["symbols"]["SYM"]["status"] == "fail"


def test_cost_sensitivity_gate_verdict_fail_when_deltas_unavailable() -> None:
    result = {"symbols": {"SYM": {"deltas": {"error": "baseline report unavailable"}}}}
    verdict = cost_sensitivity_gate_verdict(result)
    assert verdict["overall_status"] == "fail"
    assert verdict["symbols"]["SYM"]["status"] == "fail"
