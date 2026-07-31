from __future__ import annotations

from typing import Any


SAFE_LEDGER_SUMMARY_FIELDS = {
    "generated_at",
    "min_days",
    "observation_start_date",
    "excluded_before_start_count",
    "total_rows",
    "valid_observation_days",
    "pending_days",
    "skipped_days",
    "halt_days",
    "failed_days",
    "latest_date",
    "latest_valid_date",
    "consecutive_valid_days",
    "ready_to_expand",
    "promotion_blockers",
    "reason_counts",
    "reason_governance_counts",
    "reasonableness_counts",
    "reason_rationality_verdict",
    "reason_rationality_cn",
    "pareto_summary",
    "operational_bucket_counts",
    "blocking_action_counts",
    "automation_status_counts",
    "latest_action",
    "next_action",
    "next_action_class",
}


def _missing_text(value: Any) -> str:
    return str(value) if value not in (None, "") else "无"


def filter_safe_ledger_summary(ledger_summary: dict[str, Any]) -> dict[str, Any]:
    """Return only the safe aggregate fields from a ledger summary."""
    safe: dict[str, Any] = {"available": True}
    for key in SAFE_LEDGER_SUMMARY_FIELDS:
        if key in ledger_summary:
            safe[key] = ledger_summary[key]
    return safe


def build_daily_brief_20d_lines(ledger_summary: dict[str, Any]) -> list[str]:
    """Render the stable 20-day progress lines for the daily brief."""
    if not ledger_summary.get("available"):
        return [f"- ledger_summary 不可用: `{_missing_text(ledger_summary.get('reason'))}`"]

    min_days = ledger_summary.get("min_days", 20)
    blockers = ledger_summary.get("promotion_blockers") or []
    lines = [
        f"- valid_observation_days: `{ledger_summary.get('valid_observation_days', 0)}/{min_days}`",
        f"- consecutive_valid_days: `{ledger_summary.get('consecutive_valid_days', 0)}`",
        f"- ready_to_expand: `{str(bool(ledger_summary.get('ready_to_expand', False))).lower()}`",
        f"- observation_start_date: `{_missing_text(ledger_summary.get('observation_start_date'))}`",
        f"- excluded_before_start_count: `{_missing_text(ledger_summary.get('excluded_before_start_count'))}`",
        f"- next_action: `{_missing_text(ledger_summary.get('next_action'))}`",
        f"- next_action_class: `{_missing_text(ledger_summary.get('next_action_class'))}`",
        f"- promotion_blockers: `{','.join(str(b) for b in blockers) or '无'}`",
        f"- reason_rationality_verdict: `{_missing_text(ledger_summary.get('reason_rationality_verdict'))}`",
        f"- pareto_summary.top3_share_pct: `{_missing_text((ledger_summary.get('pareto_summary') or {}).get('top3_share_pct'))}`",
    ]

    reason_governance_counts = ledger_summary.get("reason_governance_counts") or {}
    for key in sorted(reason_governance_counts):
        lines.append(f"- reason_governance_counts.{key}: `{reason_governance_counts[key]}`")

    blocking_action_counts = ledger_summary.get("blocking_action_counts") or {}
    for key in sorted(blocking_action_counts):
        lines.append(f"- blocking_action_counts.{key}: `{blocking_action_counts[key]}`")

    operational_bucket_counts = ledger_summary.get("operational_bucket_counts") or {}
    for key in sorted(operational_bucket_counts):
        lines.append(f"- operational_bucket_counts.{key}: `{operational_bucket_counts[key]}`")

    return lines
