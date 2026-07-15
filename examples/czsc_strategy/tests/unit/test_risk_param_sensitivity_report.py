import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from diagnostics.risk_param_sensitivity_report import (  # noqa: E402
    evaluate_perturbation_gate,
    perturbation_gate_verdict,
)


def _payload(
    baseline_ret: float = 10.0,
    variant_rets: dict[str, float] | None = None,
) -> dict:
    variant_rets = variant_rets or {"stop_loss_tight": 9.0, "stop_loss_loose": 11.0}
    reports: dict[str, dict] = {"baseline": {"total_return_pct": baseline_ret}}
    for name, ret in variant_rets.items():
        reports[name] = {"total_return_pct": ret}
    return {"symbols": {"SYM": reports}}


def test_perturbation_gate_verdict_pass_when_no_sign_flip() -> None:
    payload = _payload(baseline_ret=10.0, variant_rets={"loose": 11.0, "tight": 9.0})
    result = evaluate_perturbation_gate(payload)
    verdict = perturbation_gate_verdict(result)
    assert verdict["overall_status"] == "pass"
    assert verdict["symbols"]["SYM"]["status"] == "pass"
    assert verdict["symbols"]["SYM"]["reasons"] == []


def test_perturbation_gate_verdict_fail_on_variant_sign_flip() -> None:
    payload = _payload(baseline_ret=10.0, variant_rets={"loose": -2.0, "tight": 9.0})
    result = evaluate_perturbation_gate(payload)
    verdict = perturbation_gate_verdict(result)
    assert verdict["overall_status"] == "fail"
    assert verdict["symbols"]["SYM"]["status"] == "fail"
    assert any("loose" in r and "sign flip" in r for r in verdict["symbols"]["SYM"]["reasons"])


def test_perturbation_gate_verdict_pass_when_baseline_negative_and_variants_stay_negative() -> None:
    payload = _payload(baseline_ret=-10.0, variant_rets={"loose": -8.0, "tight": -12.0})
    result = evaluate_perturbation_gate(payload)
    verdict = perturbation_gate_verdict(result)
    assert verdict["overall_status"] == "pass"
    assert verdict["symbols"]["SYM"]["status"] == "pass"


def test_perturbation_gate_verdict_fail_when_baseline_negative_and_variant_turns_positive() -> None:
    payload = _payload(baseline_ret=-10.0, variant_rets={"loose": 1.0, "tight": -12.0})
    result = evaluate_perturbation_gate(payload)
    verdict = perturbation_gate_verdict(result)
    assert verdict["overall_status"] == "fail"
    assert verdict["symbols"]["SYM"]["status"] == "fail"
    assert any("loose" in r and "sign flip" in r for r in verdict["symbols"]["SYM"]["reasons"])
