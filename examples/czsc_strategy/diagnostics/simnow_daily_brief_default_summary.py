from __future__ import annotations


def build_missing_run_summary_payload() -> dict:
    """Build the fallback payload used when the run summary JSON is missing."""
    return {
        "date": "unknown",
        "automation_status": "failed",
        "automation_exit_code": 40,
        "automation_reason": "missing run summary JSON",
        "automation_action": "check wrapper output and artifact completeness",
        "automation_action_class": "unknown",
        "automation_blocker_class": "review_now",
        "record": {},
        "kline": {},
        "promotion": {},
    }


def normalize_daily_brief_summary(summary: dict) -> dict:
    """Normalize a daily-brief summary with canonical fallback defaults."""
    if not summary:
        return build_missing_run_summary_payload()

    if "automation_exit_code" in summary:
        return summary

    status = summary.get("automation_status", "failed")
    default_exit = 40 if status == "failed" else 0
    return {**summary, "automation_exit_code": default_exit}


def resolve_failed_action_text(summary: dict) -> str:
    """Resolve the canonical failed-state action text."""
    action = summary.get("automation_action") or ""
    if action:
        return action
    return "请检查 wrapper 输出和 artifact 完整性。"
