from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class StabilityGate:
    min_param_neighbor_pass_ratio: float = 2 / 3
    min_positive_walk_forward_ratio: float = 2 / 3
    max_negative_window_count: int = 2
    min_symbol_set_pass_ratio: float = 2 / 3


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _param_stability(neighborhood: dict[str, Any], gate: StabilityGate) -> dict[str, Any]:
    rows = []
    pass_count = 0
    for multiplier, item in sorted(neighborhood.get("multipliers", {}).items(), key=lambda kv: _as_float(kv[0])):
        passed = bool(item.get("goal_status", {}).get("passed"))
        if passed:
            pass_count += 1
        metrics = item.get("out_sample", {}).get("metrics", {})
        wf = item.get("walk_forward", {})
        rows.append({
            "multiplier": multiplier,
            "passed": passed,
            "trades": metrics.get("trades", 0),
            "profit_factor": metrics.get("profit_factor", 0.0),
            "sharpe": metrics.get("sharpe", 0.0),
            "calmar": metrics.get("calmar", 0.0),
            "walk_forward": f"{wf.get('positive_windows', 0)}/{wf.get('total_windows', 0)}",
        })

    total = len(rows)
    pass_ratio = pass_count / total if total else 0.0
    return {
        "passed": pass_ratio >= gate.min_param_neighbor_pass_ratio,
        "pass_count": pass_count,
        "total": total,
        "pass_ratio": pass_ratio,
        "rows": rows,
    }


def _time_stability(goal_report: dict[str, Any], gate: StabilityGate) -> dict[str, Any]:
    wf = goal_report.get("walk_forward", {})
    windows = wf.get("windows", {})
    rows = []
    negative_count = 0
    for name, metrics in windows.items():
        ret = _as_float(metrics.get("return_pct"))
        if ret <= 0:
            negative_count += 1
        rows.append({
            "window": name,
            "return_pct": ret,
            "profit_factor": metrics.get("profit_factor", 0.0),
            "sharpe": metrics.get("sharpe", 0.0),
            "calmar": metrics.get("calmar", 0.0),
            "trades": metrics.get("trades", 0),
        })
    positive_ratio = _as_float(wf.get("positive_ratio"))
    return {
        "passed": (
            positive_ratio >= gate.min_positive_walk_forward_ratio
            and negative_count <= gate.max_negative_window_count
        ),
        "positive_windows": wf.get("positive_windows", 0),
        "total_windows": wf.get("total_windows", len(rows)),
        "positive_ratio": positive_ratio,
        "negative_count": negative_count,
        "rows": rows,
    }


def _symbol_set_stability(
    goal_report: dict[str, Any],
    gate: StabilityGate,
    symbol_scans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if symbol_scans:
        rows = []
        for symbol_scan in symbol_scans:
            evidence = symbol_scan.get("source_file", "symbol_set_stability_scan.json")
            for name, item in symbol_scan.get("rows", {}).items():
                rows.append({
                    "set": name,
                    "symbols": item.get("symbols", []),
                    "passed": bool(item.get("goal_status", {}).get("passed")),
                    "evidence": evidence,
                })
        pass_count = sum(1 for row in rows if row["passed"])
        total = len(rows)
        pass_ratio = pass_count / total if total else 0.0
        return {
            "passed": pass_ratio >= gate.min_symbol_set_pass_ratio,
            "pass_count": pass_count,
            "total": total,
            "pass_ratio": pass_ratio,
            "rows": rows,
            "missing": [],
        }

    symbols = goal_report.get("symbols", [])
    canonical_passed = bool(goal_report.get("goal_status", {}).get("passed"))
    rows = [{
        "set": "canonical_all_symbols",
        "symbols": symbols,
        "passed": canonical_passed,
        "evidence": "portfolio_goal_expanded_short_sc_0847.json",
    }]
    total = max(3, len(rows))
    pass_ratio = (1 if canonical_passed else 0) / total
    return {
        "passed": pass_ratio >= gate.min_symbol_set_pass_ratio,
        "pass_count": 1 if canonical_passed else 0,
        "total": total,
        "pass_ratio": pass_ratio,
        "rows": rows,
        "missing": [
            "adjacent symbol-set tests are not yet available",
            "need all5 / no_RB / no_SC / core_AP_A_ZN / no_AP / no_A evaluations",
        ],
    }


def build_review(
    goal_report_path: Path,
    neighborhood_path: Path,
    symbol_scan_paths: list[Path] | None = None,
) -> dict[str, Any]:
    gate = StabilityGate()
    goal_report = _load_json(goal_report_path)
    neighborhood = _load_json(neighborhood_path)
    symbol_scans = []
    for path in symbol_scan_paths or []:
        if path.exists():
            scan = _load_json(path)
            scan["source_file"] = path.name
            symbol_scans.append(scan)
    param = _param_stability(neighborhood, gate)
    time = _time_stability(goal_report, gate)
    symbols = _symbol_set_stability(goal_report, gate, symbol_scans)
    overall = param["passed"] and time["passed"] and symbols["passed"]
    return {
        "candidate": goal_report.get("scenario", "unknown"),
        "gate": gate.__dict__,
        "overall_passed": overall,
        "parameter_stability": param,
        "time_stability": time,
        "symbol_set_stability": symbols,
        "verdict": (
            "stable_platform"
            if overall
            else "not_a_stable_platform_yet"
        ),
    }


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def write_markdown(review: dict[str, Any], out: Path) -> None:
    param = review["parameter_stability"]
    time = review["time_stability"]
    symbols = review["symbol_set_stability"]
    lines = [
        "# Platform Stability Review",
        "",
        f"- candidate: `{review['candidate']}`",
        f"- verdict: `{review['verdict']}`",
        f"- overall_passed: `{review['overall_passed']}`",
        "",
        "## Gate",
        "",
        "- Parameter neighborhood: at least two thirds of tested adjacent points must pass.",
        "- Time windows: at least two thirds positive, with no more than two non-positive windows.",
        "- Symbol selection: at least two thirds of adjacent symbol sets must pass.",
        "",
        "## Parameter Neighborhood",
        "",
        f"- passed: `{param['passed']}`",
        f"- pass ratio: `{param['pass_count']}/{param['total']}` = `{_fmt_pct(param['pass_ratio'])}`",
        "",
        "| multiplier | pass | trades | PF | sharpe | calmar | WF |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in param["rows"]:
        lines.append(
            f"| {row['multiplier']} | {row['passed']} | {row['trades']} | "
            f"{float(row['profit_factor']):.2f} | {float(row['sharpe']):.2f} | "
            f"{float(row['calmar']):.2f} | {row['walk_forward']} |"
        )
    lines.extend([
        "",
        "## Time Stability",
        "",
        f"- passed: `{time['passed']}`",
        f"- positive windows: `{time['positive_windows']}/{time['total_windows']}` = `{_fmt_pct(time['positive_ratio'])}`",
        f"- non-positive windows: `{time['negative_count']}`",
        "",
        "| window | return | PF | sharpe | calmar | trades |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for row in time["rows"]:
        lines.append(
            f"| {row['window']} | {float(row['return_pct']):.2f}% | "
            f"{float(row['profit_factor']):.2f} | {float(row['sharpe']):.2f} | "
            f"{float(row['calmar']):.2f} | {row['trades']} |"
        )
    lines.extend([
        "",
        "## Symbol-Set Stability",
        "",
        f"- passed: `{symbols['passed']}`",
        f"- proven pass ratio: `{symbols['pass_count']}/{symbols['total']}` = `{_fmt_pct(symbols['pass_ratio'])}`",
        "",
        "| set | symbols | pass | evidence |",
        "|---|---|---|---|",
    ])
    for row in symbols["rows"]:
        lines.append(
            f"| {row['set']} | {', '.join(row['symbols'])} | {row['passed']} | {row['evidence']} |"
        )
    lines.extend([
        "",
        "### Missing Symbol Evidence",
        "",
    ])
    for item in symbols["missing"]:
        lines.append(f"- {item}")
    lines.extend([
        "",
        "## Next Optimization Target",
        "",
        "The current candidate is a narrow feasible point. The next search should optimize for a platform: "
        "multiple adjacent SC short weights, multiple adjacent half-year windows, and multiple adjacent symbol sets "
        "must pass together before promotion.",
    ])
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Review whether a candidate forms a stable parameter/time/symbol platform.")
    parser.add_argument(
        "--goal-report",
        type=Path,
        default=HERE / "portfolio_goal_expanded_short_sc_0847.json",
    )
    parser.add_argument(
        "--neighborhood",
        type=Path,
        default=HERE / "sc_short_weight_neighborhood.json",
    )
    parser.add_argument(
        "--symbol-scans",
        type=Path,
        nargs="*",
        default=[
            HERE / "symbol_set_stability_scan.json",
            HERE / "symbol_set_stability_scan_extra.json",
        ],
    )
    parser.add_argument("--out-json", type=Path, default=HERE / "platform_stability_review.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "platform_stability_review.md")
    args = parser.parse_args()

    review = build_review(args.goal_report, args.neighborhood, args.symbol_scans)
    args.out_json.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(review, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")
    print(f"verdict={review['verdict']}")


if __name__ == "__main__":
    main()
