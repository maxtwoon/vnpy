from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def _read_symbol_scans(paths: list[Path]) -> list[tuple[str, dict[str, Any]]]:
    scans = []
    for path in paths:
        if path.exists():
            scans.append((path.name, _load(path)))
    return scans


def build_report(platform_path: Path, symbol_scan_paths: list[Path]) -> dict[str, Any]:
    platform = _load(platform_path)
    scans = _read_symbol_scans(symbol_scan_paths)

    failing_checks: Counter[str] = Counter()
    set_rows = []
    for source, scan in scans:
        for name, row in scan.get("rows", {}).items():
            status = row.get("goal_status", {})
            checks = status.get("checks", {})
            fails = [key for key, passed in checks.items() if not passed]
            failing_checks.update(fails)
            metrics = row.get("out_sample", {}).get("metrics", {})
            wf = row.get("walk_forward", {})
            set_rows.append({
                "source": source,
                "set": name,
                "passed": bool(status.get("passed")),
                "symbols": row.get("symbols", []),
                "failing_checks": fails,
                "return_pct": metrics.get("return_pct", 0.0),
                "profit_factor": metrics.get("profit_factor", 0.0),
                "sharpe": metrics.get("sharpe", 0.0),
                "calmar": metrics.get("calmar", 0.0),
                "walk_forward": f"{wf.get('positive_windows', 0)}/{wf.get('total_windows', 0)}",
            })

    weak_windows = sorted(
        platform.get("time_stability", {}).get("rows", []),
        key=lambda item: float(item.get("return_pct", 0.0)),
    )
    param_rows = platform.get("parameter_stability", {}).get("rows", [])
    return {
        "candidate": platform.get("candidate"),
        "verdict": platform.get("verdict"),
        "failure_counts": dict(failing_checks.most_common()),
        "weak_windows": weak_windows,
        "symbol_sets": set_rows,
        "parameter_rows": param_rows,
        "priority": [
            "Repair walk-forward robustness first; it is the most common failure across adjacent symbol sets.",
            "Focus diagnostics on 2023H1, 2026YTD, and 2022H1 before adding new parameters.",
            "Treat SC short weight as a secondary lever; current failures are mostly window robustness rather than OOS headline metrics.",
            "Prefer candidate rules that improve no_RB, no_SC, no_ZN, and core_AP_A_ZN together.",
        ],
    }


def write_markdown(report: dict[str, Any], out: Path) -> None:
    lines = [
        "# Platform Failure Attribution",
        "",
        f"- candidate: `{report['candidate']}`",
        f"- verdict: `{report['verdict']}`",
        "",
        "## Failure Counts Across Symbol Sets",
        "",
        "| check | count |",
        "|---|---:|",
    ]
    for check, count in report["failure_counts"].items():
        lines.append(f"| {check} | {count} |")

    lines.extend([
        "",
        "## Weak Time Windows",
        "",
        "| window | return | PF | sharpe | calmar | trades |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for row in report["weak_windows"]:
        lines.append(
            f"| {row['window']} | {_fmt(float(row['return_pct']))}% | "
            f"{_fmt(float(row['profit_factor']))} | {_fmt(float(row['sharpe']))} | "
            f"{_fmt(float(row['calmar']))} | {row['trades']} |"
        )

    lines.extend([
        "",
        "## Symbol-Set Details",
        "",
        "| set | pass | symbols | return | PF | sharpe | calmar | WF | failing_checks |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in report["symbol_sets"]:
        lines.append(
            f"| {row['set']} | {row['passed']} | {', '.join(row['symbols'])} | "
            f"{_fmt(float(row['return_pct']))}% | {_fmt(float(row['profit_factor']))} | "
            f"{_fmt(float(row['sharpe']))} | {_fmt(float(row['calmar']))} | "
            f"{row['walk_forward']} | {', '.join(row['failing_checks']) or '-'} |"
        )

    lines.extend([
        "",
        "## Priority",
        "",
    ])
    for item in report["priority"]:
        lines.append(f"- {item}")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize why the current platform candidate fails stability.")
    parser.add_argument("--platform", type=Path, default=HERE / "platform_stability_review.json")
    parser.add_argument(
        "--symbol-scans",
        nargs="*",
        type=Path,
        default=[
            HERE / "symbol_set_stability_scan.json",
            HERE / "symbol_set_stability_scan_extra.json",
        ],
    )
    parser.add_argument("--out-json", type=Path, default=HERE / "platform_failure_attribution.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "platform_failure_attribution.md")
    args = parser.parse_args()

    report = build_report(args.platform, args.symbol_scans)
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
