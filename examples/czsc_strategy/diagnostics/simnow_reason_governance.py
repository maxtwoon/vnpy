from __future__ import annotations

from collections import Counter
from typing import Any


def classify_reason(reason: str) -> tuple[str, str]:
    """Classify a blocking reason into governance and reasonableness buckets."""
    if reason in {
        "simnow_no_ticks",
        "simnow_no_snapshot",
        "ctp_disconnect_097_no_snapshot",
    }:
        return "expected_market_or_session", "reasonable"
    if reason in {
        "historical_db_lag",
        "kline_coverage_incomplete",
        "kline_coverage_too_short",
    }:
        return "data_readiness_gap", "reasonable"
    if reason in {
        "subscription_incomplete",
        "event_surface_mismatch",
        "simnow_or_replay_export_missing",
        "no_captured_session_data_only_replay_derived",
    }:
        return "infra_or_mapping_gap", "needs_fix"
    if reason == "workflow_order_safety_breach":
        return "workflow_safety_halt", "needs_fix"
    if reason:
        return "risk_control_halt", "reasonable"
    return "unknown_blocker", "investigate"


def build_reason_governance(reason_counts: dict[str, int]) -> dict[str, Any]:
    """Build governance, reasonableness, and Pareto summaries for blocking reasons."""
    governance_counter: Counter[str] = Counter()
    reasonableness_counter: Counter[str] = Counter()
    sorted_reasons = sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
    top_actions: list[dict[str, str]] = []
    total = sum(int(count) for count in reason_counts.values())

    for reason, count in sorted_reasons:
        governance_class, reasonableness = classify_reason(str(reason))
        governance_counter[governance_class] += int(count)
        reasonableness_counter[reasonableness] += int(count)
        top_actions.append({
            "reason": str(reason),
            "governance_class": governance_class,
            "reasonableness": reasonableness,
        })

    if total == 0:
        pareto_summary = {
            "top1_reason": "",
            "top1_share_pct": 0.0,
            "top3_share_pct": 0.0,
            "total_blocking_days": 0,
            "top3_blocking_days": 0,
            "summary_cn": "最近 20 日无阻塞原因。",
        }
        return {
            "reason_governance_counts": {},
            "reasonableness_counts": {},
            "reason_rationality_verdict": "no_blockers",
            "reason_rationality_cn": "最近 20 日无阻塞原因。",
            "pareto_summary": pareto_summary,
            "reason_meta": {},
        }

    top1_reason, top1_count = sorted_reasons[0]
    top3_blocking_days = sum(count for _, count in sorted_reasons[:3])
    top1_share_pct = round(top1_count * 100 / total, 1)
    top3_share_pct = round(top3_blocking_days * 100 / total, 1)

    if reasonableness_counter.get("needs_fix", 0) == 0 and reasonableness_counter.get("investigate", 0) == 0:
        verdict = "mostly_reasonable_non_code"
        verdict_cn = "最近阻塞日主要由环境、时段或数据准备因素构成，不应直接视为代码失败。"
    elif reasonableness_counter.get("reasonable", 0) > reasonableness_counter.get("needs_fix", 0):
        verdict = "mostly_reasonable_non_code"
        verdict_cn = "最近阻塞日以非代码阻塞为主，但仍包含需要人工关注的异常项，不应直接视为代码失败。"
    elif reasonableness_counter.get("needs_fix", 0) >= reasonableness_counter.get("reasonable", 0):
        verdict = "mixed_action_required"
        verdict_cn = "最近阻塞日中需要修配置、流程或安全问题的占比较高，应优先处理可修复项。"
    elif reasonableness_counter.get("investigate", 0) > 0:
        verdict = "needs_investigation"
        verdict_cn = "最近阻塞日存在无法直接归类的原因，需要补充排查证据。"

    pareto_summary = {
        "top1_reason": str(top1_reason),
        "top1_share_pct": top1_share_pct,
        "top3_share_pct": top3_share_pct,
        "total_blocking_days": int(total),
        "top3_blocking_days": int(top3_blocking_days),
        "summary_cn": (
            f"前 {min(3, len(sorted_reasons))} 个阻塞原因占 {top3_share_pct:.1f}%（{top3_blocking_days}/{total}），"
            f"其中首要原因 {top1_reason} 占 {top1_share_pct:.1f}%。"
        ),
    }

    return {
        "reason_governance_counts": dict(sorted(governance_counter.items())),
        "reasonableness_counts": dict(sorted(reasonableness_counter.items())),
        "reason_rationality_verdict": verdict,
        "reason_rationality_cn": verdict_cn,
        "pareto_summary": pareto_summary,
        "reason_meta": {
            row["reason"]: {
                "governance_class": row["governance_class"],
                "reasonableness": row["reasonableness"],
            }
            for row in top_actions
        },
    }
