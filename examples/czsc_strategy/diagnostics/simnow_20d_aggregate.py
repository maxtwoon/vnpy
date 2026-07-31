from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from simnow_action_summary import _record_reason, build_action_summary
from simnow_halt_metadata import halt_family
from simnow_observation_rules import is_valid_observation
from simnow_observation_window import filter_records_by_start
from simnow_reason_governance import build_reason_governance


def _count_by(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = value or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _consecutive_clean_days(records: list[dict[str, Any]]) -> int:
    count = 0
    for row in reversed(records):
        if is_valid_observation(row):
            count += 1
        else:
            break
    return count


def build_20d_aggregate(
    records: list[dict[str, Any]],
    *,
    min_days: int,
    observation_start_date: str | None = None,
    matched_day_predicate: Callable[[dict[str, Any]], bool],
    halt_day_predicate: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    all_records = sorted(records, key=lambda row: str(row.get("date", "")))
    ordered = sorted(filter_records_by_start(all_records, observation_start_date), key=lambda row: str(row.get("date", "")))
    excluded_before_start_count = len(all_records) - len(ordered)
    recent = ordered[-min_days:]
    observed_days = len(recent)
    valid_days = sum(1 for row in recent if is_valid_observation(row))
    pass_days = sum(1 for row in recent if row.get("status") == "pass")
    pending_days = sum(1 for row in recent if row.get("status") == "pending")
    skipped_days = sum(1 for row in recent if row.get("status") == "skipped")
    matched_days = sum(1 for row in recent if matched_day_predicate(row))
    halt_days = sum(1 for row in recent if halt_day_predicate(row))
    warning_days = sum(1 for row in recent if row.get("thresholds", {}).get("status") == "warning")
    status_counts = _count_by([str(row.get("status") or "unknown") for row in recent])
    halt_family_counts = _count_by([
        halt_family(row)
        for row in recent
        if halt_family(row)
    ])
    reason_counts = _count_by([
        _record_reason(row)
        for row in recent
        if row.get("status") in {"pending", "skipped"} or row.get("thresholds", {}).get("status") in {"warning", "halt"}
    ])
    last_valid = next((row for row in reversed(ordered) if is_valid_observation(row)), None)
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
    action_summary = build_action_summary(recent)
    blocking_rows = [
        row for row in action_summary
        if not row["counts_for_20d"] and row.get("reason")
    ]
    action_counts_counter = Counter(
        str(row["action_class"])
        for row in blocking_rows
        if row.get("action_class")
    )
    reason_counts_counter = Counter(str(row["reason"]) for row in blocking_rows)
    reason_governance = build_reason_governance(dict(reason_counts_counter))
    reason_meta = {
        str(row["reason"]): {
            "action_class": str(row.get("action_class") or ""),
            "blocker_class": str(row.get("blocker_class") or ""),
            "governance_class": str(
                reason_governance["reason_meta"].get(str(row["reason"]), {}).get("governance_class", "")
            ),
            "reasonableness": str(
                reason_governance["reason_meta"].get(str(row["reason"]), {}).get("reasonableness", "")
            ),
        }
        for row in blocking_rows
        if row.get("reason")
    }
    top_blocking_actions = [
        {
            "reason": reason,
            "count": count,
            "action_class": reason_meta.get(reason, {}).get("action_class", ""),
            "blocker_class": reason_meta.get(reason, {}).get("blocker_class", ""),
            "governance_class": reason_meta.get(reason, {}).get("governance_class", ""),
            "reasonableness": reason_meta.get(reason, {}).get("reasonableness", ""),
        }
        for reason, count in reason_counts_counter.most_common(3)
    ]
    return {
        "required_days": min_days,
        "observation_start_date": observation_start_date or "",
        "excluded_before_start_count": excluded_before_start_count,
        "observed_days": observed_days,
        "valid_observation_days": valid_days,
        "status_counts": status_counts,
        "pass_days": pass_days,
        "pending_days": pending_days,
        "skipped_days": skipped_days,
        "consistency_matched_days": matched_days,
        "warning_days": warning_days,
        "halt_days": halt_days,
        "latest_record_date": str(ordered[-1].get("date")) if ordered else "",
        "last_valid_observation_date": str(last_valid.get("date")) if last_valid else "",
        "consecutive_clean_days": _consecutive_clean_days(ordered),
        "promotion_blockers": blockers,
        "reason_counts": reason_counts,
        "reason_governance_counts": reason_governance["reason_governance_counts"],
        "reasonableness_counts": reason_governance["reasonableness_counts"],
        "reason_rationality_verdict": reason_governance["reason_rationality_verdict"],
        "reason_rationality_cn": reason_governance["reason_rationality_cn"],
        "pareto_summary": reason_governance["pareto_summary"],
        "halt_family_counts": halt_family_counts,
        "ready_to_expand": ready,
        "action_summary": action_summary,
        "action_summary_count": len(action_summary),
        "blocking_action_counts": dict(sorted(action_counts_counter.items())),
        "top_blocking_actions": top_blocking_actions,
        "records": recent,
    }
