from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]


FILES = {
    "base_gate": HERE / "platform_stability_goal_status_sc025_final.json",
    "cost2_sets": HERE / "platform_final_robustness_cost2_symbol_sets.json",
    "cost2_neighbor": HERE / "platform_final_robustness_cost2_sc_neighbor.json",
    "date_variants": HERE / "platform_final_robustness_date_variants.json",
    "risk": HERE / "simnow_precheck_risk_report.json",
}


def _run(cmd: list[str], cwd: Path = ROOT, timeout: int | None = None) -> None:
    print("RUN", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True, timeout=timeout)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_artifacts(generate_missing: bool, run_pytest: bool) -> None:
    if generate_missing:
        if not FILES["base_gate"].exists():
            _run([
                sys.executable,
                "examples/czsc_strategy/diagnostics/check_platform_stability_goal.py",
                "--sc-neighbor", "examples/czsc_strategy/diagnostics/sc_short_weight_neighborhood_final_candidate_sc025.json",
                "--symbol-sets", "examples/czsc_strategy/diagnostics/platform_short_symbol_candidates_sc025_final_full.json",
                "--candidate", "sc025_a_zn010_sc3buy_half",
                "--out-json", str(FILES["base_gate"]),
            ], timeout=120)
        if not FILES["cost2_sets"].exists():
            _run([
                sys.executable,
                "examples/czsc_strategy/diagnostics/platform_final_robustness_check.py",
                "--sections", "cost2_symbol_sets",
                "--out-json", str(FILES["cost2_sets"]),
                "--out-md", str(HERE / "platform_final_robustness_cost2_symbol_sets.md"),
            ], timeout=2400)
        if not FILES["cost2_neighbor"].exists():
            _run([
                sys.executable,
                "examples/czsc_strategy/diagnostics/platform_final_robustness_check.py",
                "--sections", "cost2_sc_neighbor",
                "--out-json", str(FILES["cost2_neighbor"]),
                "--out-md", str(HERE / "platform_final_robustness_cost2_sc_neighbor.md"),
            ], timeout=5400)
        if not FILES["date_variants"].exists():
            _run([
                sys.executable,
                "examples/czsc_strategy/diagnostics/platform_final_robustness_check.py",
                "--sections", "date_variants",
                "--out-json", str(FILES["date_variants"]),
                "--out-md", str(HERE / "platform_final_robustness_date_variants.md"),
            ], timeout=2400)
        if not FILES["risk"].exists():
            _run([
                sys.executable,
                "examples/czsc_strategy/diagnostics/simnow_precheck_risk_report.py",
                "--out-json", str(FILES["risk"]),
                "--out-md", str(HERE / "simnow_precheck_risk_report.md"),
            ], timeout=1200)
    missing = [name for name, path in FILES.items() if not path.exists()]
    if missing:
        raise SystemExit(f"missing artifacts: {', '.join(missing)}")
    if run_pytest:
        _run([sys.executable, "-m", "pytest", "examples/czsc_strategy/tests", "-q"], timeout=1200)


def build_status(pytest_ran: bool) -> dict[str, Any]:
    base = _load(FILES["base_gate"])
    cost2_sets = _load(FILES["cost2_sets"])
    cost2_neighbor = _load(FILES["cost2_neighbor"])
    date_variants = _load(FILES["date_variants"])
    risk = _load(FILES["risk"])
    checks = {
        "base_gate": bool(base.get("passed")),
        "cost2_symbol_sets": bool(cost2_sets.get("passed")),
        "cost2_sc_neighbor": bool(cost2_neighbor.get("passed")),
        "date_variants": bool(date_variants.get("passed")),
        "dominant_symbol_audit": (
            cost2_sets.get("dominant_symbol_audit", {}).get("passed")
            and cost2_neighbor.get("dominant_symbol_audit", {}).get("passed")
            and date_variants.get("dominant_symbol_audit", {}).get("passed")
        ),
        "risk_report_present": bool(risk.get("portfolio_risk")),
        "pytest": pytest_ran,
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "base": {
            "sc_neighbor": f"{base['sc_neighbor']['pass_count']}/{base['sc_neighbor']['total']}",
            "all5_wf": f"{base['symbol_sets']['walk_forward_positive']}/{base['symbol_sets']['walk_forward_total']}",
            "symbol_sets": f"{base['symbol_sets']['symbol_set_pass_count']}/{base['symbol_sets']['symbol_set_total']}",
        },
        "cost2": {
            "sc_neighbor": f"{cost2_neighbor['cost_slippage_2x_sc_neighbor']['pass_count']}/{cost2_neighbor['cost_slippage_2x_sc_neighbor']['total']}",
            "all5_wf": f"{cost2_sets['cost_slippage_2x_symbol_sets']['all5_walk_forward_positive']}/{cost2_sets['cost_slippage_2x_symbol_sets']['all5_walk_forward_total']}",
            "symbol_sets": f"{cost2_sets['cost_slippage_2x_symbol_sets']['symbol_set_pass_count']}/{cost2_sets['cost_slippage_2x_symbol_sets']['symbol_set_total']}",
        },
        "date_variants": f"{date_variants['date_variants_2x']['pass_count']}/{date_variants['date_variants_2x']['total']}",
        "risk": risk["portfolio_risk"],
    }


def write_markdown(status: dict[str, Any], out: Path) -> None:
    risk = status["risk"]
    lines = [
        "# SimNow Precheck Acceptance",
        "",
        f"**PASSED: `{status['passed']}`**",
        "",
        "## Gates",
        "",
        "| gate | result |",
        "|---|---:|",
        f"| base SC neighborhood | {status['base']['sc_neighbor']} |",
        f"| base all5 WF | {status['base']['all5_wf']} |",
        f"| base symbol sets | {status['base']['symbol_sets']} |",
        f"| cost2 SC neighborhood | {status['cost2']['sc_neighbor']} |",
        f"| cost2 all5 WF | {status['cost2']['all5_wf']} |",
        f"| cost2 symbol sets | {status['cost2']['symbol_sets']} |",
        f"| date variants | {status['date_variants']} |",
        "",
        "## Risk Snapshot",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| max_single_day_loss_pct | {risk['max_single_day_loss_pct']:.2f}% |",
        f"| max_consecutive_loss_days | {risk['max_consecutive_loss']['days']} |",
        f"| max_drawdown_pct | {risk['max_drawdown_pct']:.2f}% |",
        f"| max_gross_exposure | {risk['max_gross_exposure'] * 100:.2f}% |",
        f"| max_net_exposure_abs | {risk['max_net_exposure'] * 100:.2f}% |",
        f"| both_long_short_days | {risk['both_long_short_days']} |",
        f"| symbol_top1_abs_share | {risk['symbol_concentration']['top1_abs_share']:.2%} |",
        f"| strategy_top1_abs_share | {risk['strategy_concentration']['top1_abs_share']:.2%} |",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "|---|---|",
    ]
    for name, ok in status["checks"].items():
        lines.append(f"| {name} | {ok} |")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or verify the SimNow precheck acceptance package.")
    parser.add_argument("--generate-missing", action="store_true")
    parser.add_argument("--run-pytest", action="store_true")
    parser.add_argument("--out-json", type=Path, default=HERE / "simnow_precheck_acceptance.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "simnow_precheck_acceptance.md")
    args = parser.parse_args()

    _ensure_artifacts(args.generate_missing, args.run_pytest)
    status = build_status(pytest_ran=args.run_pytest)
    args.out_json.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(status, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    if not status["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
