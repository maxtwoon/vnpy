from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from simnow_20d_aggregate import build_20d_aggregate
from declassify_historical_reports import build_banner
from simnow_action_summary import build_action_summary
from simnow_observation_window import load_observation_start_date


HERE = Path(__file__).resolve().parent
DEFAULT_LEDGER = HERE / "simnow_observation_ledger.jsonl"
DEFAULT_REPORT = HERE / "simnow_20d_promotion_decision.md"
DEFAULT_MIN_DAYS = 20


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def decide_promotion(
    records: list[dict[str, Any]],
    min_days: int = DEFAULT_MIN_DAYS,
    observation_start_date: str | None = None,
) -> dict[str, Any]:
    return build_20d_aggregate(
        records,
        min_days=min_days,
        observation_start_date=observation_start_date,
        matched_day_predicate=lambda row: bool(row.get("consistency", {}).get("matched")),
        halt_day_predicate=lambda row: row.get("thresholds", {}).get("status") == "halt",
    )


def write_report(summary: dict[str, Any], out: Path) -> None:
    lines = [
        "# SimNow 20-Day Promotion Decision",
        "",
        build_banner().rstrip("\n"),
        "",
        f"- ready_to_expand: `{summary['ready_to_expand']}`",
        f"- observation_start_date: `{summary.get('observation_start_date', '')}`",
        f"- excluded_before_start_count: `{summary.get('excluded_before_start_count', 0)}`",
        f"- observed_days: `{summary['observed_days']}/{summary['required_days']}`",
        f"- valid_observation_days: `{summary['valid_observation_days']}/{summary['required_days']}`",
        f"- pass_days: `{summary['pass_days']}`",
        f"- pending_days: `{summary['pending_days']}`",
        f"- skipped_days: `{summary['skipped_days']}`",
        f"- consistency_matched_days: `{summary['consistency_matched_days']}`",
        f"- warning_days: `{summary['warning_days']}`",
        f"- halt_days: `{summary['halt_days']}`",
        f"- last_valid_observation_date: `{summary['last_valid_observation_date']}`",
        f"- promotion_blockers: `{', '.join(summary['promotion_blockers']) or 'none'}`",
        "",
        "## Status Counts",
        "",
        "| status | days |",
        "|---|---:|",
    ]
    for status, count in summary["status_counts"].items():
        lines.append(f"| {status} | {count} |")
    lines.extend(["", "## Pending / Skipped Reasons", "", "| reason | days |", "|---|---:|"])
    if summary["reason_counts"]:
        for reason, count in summary["reason_counts"].items():
            lines.append(f"| {reason} | {count} |")
    else:
        lines.append("| none | 0 |")
    lines.extend(["", "## Blocking Action Counts", "", "| action_class | days |", "|---|---:|"])
    if summary["blocking_action_counts"]:
        for action_class, count in summary["blocking_action_counts"].items():
            lines.append(f"| {action_class} | {count} |")
    else:
        lines.append("| none | 0 |")
    lines.extend([
        "",
        "## Top Blocking Actions",
        "",
        "| reason | days | action_class | blocker_class | governance_class | reasonableness |",
        "|---|---:|---|---|---|---|",
    ])
    if summary["top_blocking_actions"]:
        for row in summary["top_blocking_actions"]:
            lines.append(
                f"| {row['reason']} | {row['count']} | {row['action_class']} | {row['blocker_class']} | {row.get('governance_class', '')} | {row.get('reasonableness', '')} |"
            )
    else:
        lines.append("| none | 0 | none | none | none | none |")
    lines.extend([
        "",
        "## Reason Governance",
        "",
        f"- reason_rationality_verdict: `{summary.get('reason_rationality_verdict', '')}`",
        f"- reason_rationality_cn: `{summary.get('reason_rationality_cn', '')}`",
        f"- pareto_summary.top3_share_pct: `{summary.get('pareto_summary', {}).get('top3_share_pct', 0.0)}`",
        f"- pareto_summary.summary_cn: `{summary.get('pareto_summary', {}).get('summary_cn', '')}`",
        "",
        "| governance_class | days |",
        "|---|---:|",
    ])
    if summary.get("reason_governance_counts"):
        for governance_class, count in summary["reason_governance_counts"].items():
            lines.append(f"| {governance_class} | {count} |")
    else:
        lines.append("| none | 0 |")
    lines.append("")
    lines.append("## Action Summary")
    lines.append("")
    lines.append("| date | status | reason | severity | action_class | blocker_class | action | counts_for_20d |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for rec in summary["action_summary"]:
        lines.append(
            f"| {rec['date']} | {rec['status']} | {rec['reason']} | {rec['severity']} | {rec['action_class']} | {rec['blocker_class']} | {rec['action']} | {rec['counts_for_20d']} |"
        )
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    if summary["ready_to_expand"]:
        lines.append("- Candidate can expand beyond observation.")
    else:
        lines.append("- Candidate cannot expand yet.")
        for blocker in summary["promotion_blockers"]:
            lines.append(f"- blocker: {blocker}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Decide whether the SimNow candidate can expand beyond observation.")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--min-days", type=int, default=DEFAULT_MIN_DAYS)
    parser.add_argument(
        "--observation-start-date",
        default=None,
        help="Only count ledger rows on or after this date. Defaults to simnow_observation_window.json.",
    )
    args = parser.parse_args()

    records = load_jsonl(args.ledger)
    start_date = args.observation_start_date
    if start_date is None:
        start_date = load_observation_start_date()
    summary = decide_promotion(records, min_days=args.min_days, observation_start_date=start_date)
    write_report(summary, args.report_md)
    print(json.dumps({
        "ready_to_expand": summary["ready_to_expand"],
        "observation_start_date": summary["observation_start_date"],
        "excluded_before_start_count": summary["excluded_before_start_count"],
        "observed_days": summary["observed_days"],
        "valid_observation_days": summary["valid_observation_days"],
        "pass_days": summary["pass_days"],
        "pending_days": summary["pending_days"],
        "skipped_days": summary["skipped_days"],
        "last_valid_observation_date": summary["last_valid_observation_date"],
        "promotion_blockers": summary["promotion_blockers"],
        "action_summary_count": summary["action_summary_count"],
        "blocking_action_counts": summary["blocking_action_counts"],
        "top_blocking_actions": summary["top_blocking_actions"],
        "reason_governance_counts": summary["reason_governance_counts"],
        "reasonableness_counts": summary["reasonableness_counts"],
        "reason_rationality_verdict": summary["reason_rationality_verdict"],
        "reason_rationality_cn": summary["reason_rationality_cn"],
        "pareto_summary": summary["pareto_summary"],
        "report": str(args.report_md),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
