from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from simnow_action_summary import build_action_summary
from simnow_observation_rules import is_valid_observation


HERE = Path(__file__).resolve().parent
DEFAULT_LEDGER = HERE / "simnow_observation_ledger.jsonl"
DEFAULT_REPORT = HERE / "simnow_20d_promotion_decision.md"
DEFAULT_MIN_DAYS = 20


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _count_by(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = value or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def decide_promotion(records: list[dict[str, Any]], min_days: int = DEFAULT_MIN_DAYS) -> dict[str, Any]:
    ordered = sorted(records, key=lambda row: str(row.get("date", "")))
    recent = ordered[-min_days:]
    observed_days = len(recent)
    pass_days = sum(1 for row in recent if row.get("status") == "pass")
    valid_days = sum(1 for row in recent if is_valid_observation(row))
    pending_days = sum(1 for row in recent if row.get("status") == "pending")
    skipped_days = sum(1 for row in recent if row.get("status") == "skipped")
    matched_days = sum(1 for row in recent if row.get("consistency", {}).get("matched"))
    halt_days = sum(1 for row in recent if row.get("thresholds", {}).get("status") == "halt")
    warning_days = sum(1 for row in recent if row.get("thresholds", {}).get("status") == "warning")
    blockers: list[str] = []
    if valid_days < min_days:
        blockers.append(f"need_{min_days - valid_days}_more_valid_observation_days")
    if pending_days:
        blockers.append("pending_days_present")
    if skipped_days:
        blockers.append("skipped_days_present")
    if pass_days != observed_days:
        blockers.append("non_pass_days_present")
    if matched_days != observed_days:
        blockers.append("consistency_not_fully_matched")
    if halt_days:
        blockers.append("halt_threshold_breached")
    ready = not blockers
    status_counts = _count_by([str(row.get("status") or "unknown") for row in recent])
    reason_counts = _count_by([
        str(row.get("consistency", {}).get("reason") or row.get("skip_reason") or "")
        for row in recent
        if row.get("status") in {"pending", "skipped"} or row.get("consistency", {}).get("reason") or row.get("skip_reason")
    ])
    last_valid = next((row for row in reversed(ordered) if is_valid_observation(row)), None)
    action_summary = build_action_summary(recent)
    blocking_reasons = [
        str(row["reason"])
        for row in action_summary
        if not row["counts_for_20d"] and row.get("reason")
    ]
    reason_counts_counter = Counter(blocking_reasons)
    top_blocking_actions = [
        {"reason": reason, "count": count}
        for reason, count in reason_counts_counter.most_common(3)
    ]
    return {
        "required_days": min_days,
        "observed_days": observed_days,
        "valid_observation_days": valid_days,
        "pass_days": pass_days,
        "pending_days": pending_days,
        "skipped_days": skipped_days,
        "consistency_matched_days": matched_days,
        "warning_days": warning_days,
        "halt_days": halt_days,
        "status_counts": status_counts,
        "reason_counts": reason_counts,
        "last_valid_observation_date": str(last_valid.get("date")) if last_valid else "",
        "ready_to_expand": ready,
        "promotion_blockers": blockers,
        "action_summary": action_summary,
        "action_summary_count": len(action_summary),
        "top_blocking_actions": top_blocking_actions,
        "records": recent,
    }


def write_report(summary: dict[str, Any], out: Path) -> None:
    lines = [
        "# SimNow 20-Day Promotion Decision",
        "",
        f"- ready_to_expand: `{summary['ready_to_expand']}`",
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
    lines.append("")
    lines.append("## Action Summary")
    lines.append("")
    lines.append("| date | status | reason | severity | action | counts_for_20d |")
    lines.append("|---|---|---|---|---|---|")
    for rec in summary["action_summary"]:
        lines.append(
            f"| {rec['date']} | {rec['status']} | {rec['reason']} | {rec['severity']} | {rec['action']} | {rec['counts_for_20d']} |"
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
    args = parser.parse_args()

    records = load_jsonl(args.ledger)
    summary = decide_promotion(records, min_days=args.min_days)
    write_report(summary, args.report_md)
    print(json.dumps({
        "ready_to_expand": summary["ready_to_expand"],
        "observed_days": summary["observed_days"],
        "valid_observation_days": summary["valid_observation_days"],
        "pass_days": summary["pass_days"],
        "pending_days": summary["pending_days"],
        "skipped_days": summary["skipped_days"],
        "last_valid_observation_date": summary["last_valid_observation_date"],
        "promotion_blockers": summary["promotion_blockers"],
        "action_summary_count": summary["action_summary_count"],
        "top_blocking_actions": summary["top_blocking_actions"],
        "report": str(args.report_md),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
