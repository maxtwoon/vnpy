import sys
from pathlib import Path
from typing import Any


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_20d_aggregate import build_20d_aggregate  # noqa: E402


def _valid_record(date: str) -> dict[str, Any]:
    return {
        "date": date,
        "status": "pass",
        "valid_observation": True,
        "consistency": {"matched": True, "verified": True},
        "thresholds": {"status": "pass"},
        "order_safety": {"status": "pass"},
        "subscription_coverage": {"missing_symbols": []},
        "kline_coverage": {"missing_symbols": [], "short_symbols": []},
    }


def _pending_record(date: str, reason: str) -> dict[str, Any]:
    return {
        "date": date,
        "status": "pending",
        "valid_observation": False,
        "consistency": {"matched": False, "verified": False, "reason": reason},
        "thresholds": {"status": "pass"},
        "order_safety": {"status": "pass"},
        "subscription_coverage": {"missing_symbols": []},
        "kline_coverage": {"missing_symbols": [], "short_symbols": []},
    }


def _skipped_record(date: str, reason: str) -> dict[str, Any]:
    return {
        "date": date,
        "status": "skipped",
        "valid_observation": False,
        "skip_reason": reason,
        "thresholds": {"status": "pass"},
        "order_safety": {"status": "pass"},
        "subscription_coverage": {"missing_symbols": []},
        "kline_coverage": {"missing_symbols": [], "short_symbols": []},
    }


def _halt_record(date: str, reason: str) -> dict[str, Any]:
    halt = {
        "rule_id": "workflow_order_safety_breach" if reason == "workflow_order_safety_breach" else "threshold_breach",
        "family": "order_safety" if reason == "workflow_order_safety_breach" else "strategy_risk",
        "severity": "critical",
        "trigger_metrics": [] if reason == "workflow_order_safety_breach" else [reason],
        "explained_cn": "只读观察流程检测到下单动作，必须停止自动化并人工复核。"
        if reason == "workflow_order_safety_breach"
        else f"风险阈值触发停线：{reason}。",
    }
    return {
        "date": date,
        "status": "halt",
        "valid_observation": False,
        "consistency": {"matched": False, "verified": True, "reason": reason},
        "thresholds": {"status": "halt"},
        "order_safety": {"status": "halt"},
        "halt": halt,
        "subscription_coverage": {"missing_symbols": []},
        "kline_coverage": {"missing_symbols": [], "short_symbols": []},
    }


def test_build_20d_aggregate_returns_common_summary_fields():
    records = [
        _valid_record("2026-07-18"),
        _pending_record("2026-07-19", "historical_db_lag"),
        _skipped_record("2026-07-20", "simnow_no_ticks"),
        _halt_record("2026-07-21", "workflow_order_safety_breach"),
    ]

    summary = build_20d_aggregate(
        records,
        min_days=4,
        matched_day_predicate=lambda row: (
            row.get("consistency", {}).get("matched") is True
            and row.get("consistency", {}).get("verified") is True
        ),
        halt_day_predicate=lambda row: (
            row.get("thresholds", {}).get("status") == "halt"
            or row.get("order_safety", {}).get("status") == "halt"
        ),
    )

    assert summary["required_days"] == 4
    assert summary["observed_days"] == 4
    assert summary["valid_observation_days"] == 1
    assert summary["pass_days"] == 1
    assert summary["pending_days"] == 1
    assert summary["skipped_days"] == 1
    assert summary["consistency_matched_days"] == 1
    assert summary["warning_days"] == 0
    assert summary["halt_days"] == 1
    assert summary["status_counts"] == {
        "halt": 1,
        "pass": 1,
        "pending": 1,
        "skipped": 1,
    }
    assert summary["reason_counts"] == {
        "historical_db_lag": 1,
        "simnow_no_ticks": 1,
        "workflow_order_safety_breach": 1,
    }
    assert summary["last_valid_observation_date"] == "2026-07-18"
    assert summary["ready_to_expand"] is False
    assert summary["promotion_blockers"] == [
        "need_3_more_valid_observation_days",
        "pending_days_present",
        "skipped_days_present",
        "non_pass_days_present",
        "consistency_not_fully_matched",
        "halt_threshold_breached",
    ]
    assert summary["action_summary_count"] == 4
    assert summary["blocking_action_counts"] == {
        "manual_review_required": 1,
        "rerun_next_session": 1,
        "wait_for_data": 1,
    }
    assert summary["top_blocking_actions"] == [
        {
            "reason": "historical_db_lag",
            "count": 1,
            "action_class": "wait_for_data",
            "blocker_class": "wait",
            "governance_class": "data_readiness_gap",
            "reasonableness": "reasonable",
        },
        {
            "reason": "simnow_no_ticks",
            "count": 1,
            "action_class": "rerun_next_session",
            "blocker_class": "wait",
            "governance_class": "expected_market_or_session",
            "reasonableness": "reasonable",
        },
        {
            "reason": "workflow_order_safety_breach",
            "count": 1,
            "action_class": "manual_review_required",
            "blocker_class": "review_now",
            "governance_class": "workflow_safety_halt",
            "reasonableness": "needs_fix",
        },
    ]
    assert summary["halt_family_counts"] == {"order_safety": 1}
    assert summary["reason_governance_counts"] == {
        "data_readiness_gap": 1,
        "expected_market_or_session": 1,
        "workflow_safety_halt": 1,
    }
    assert summary["reasonableness_counts"] == {
        "needs_fix": 1,
        "reasonable": 2,
    }
    assert summary["reason_rationality_verdict"] == "mostly_reasonable_non_code"
    assert "不应直接视为代码失败" in summary["reason_rationality_cn"]
    assert summary["pareto_summary"] == {
        "top1_reason": "historical_db_lag",
        "top1_share_pct": 33.3,
        "top3_share_pct": 100.0,
        "total_blocking_days": 3,
        "top3_blocking_days": 3,
        "summary_cn": "前 3 个阻塞原因占 100.0%（3/3），其中首要原因 historical_db_lag 占 33.3%。",
    }


def test_build_20d_aggregate_preserves_configurable_matched_and_halt_predicates():
    records = [_valid_record(f"2026-07-{day:02d}") for day in range(1, 19)]
    order_safety_halt = _valid_record("2026-07-19")
    order_safety_halt["status"] = "halt"
    order_safety_halt["valid_observation"] = False
    order_safety_halt["order_safety"] = {"status": "halt"}
    order_safety_halt["consistency"]["reason"] = "workflow_order_safety_breach"

    unverified_match = _valid_record("2026-07-20")
    unverified_match["valid_observation"] = False
    unverified_match["consistency"] = {
        "matched": True,
        "verified": False,
        "reason": "consistency_provenance_unverified",
    }
    records.extend([order_safety_halt, unverified_match])

    monitor_like = build_20d_aggregate(
        records,
        min_days=20,
        matched_day_predicate=lambda row: (
            row.get("consistency", {}).get("matched") is True
            and row.get("consistency", {}).get("verified") is True
        ),
        halt_day_predicate=lambda row: (
            row.get("thresholds", {}).get("status") == "halt"
            or row.get("order_safety", {}).get("status") == "halt"
        ),
    )
    promotion_like = build_20d_aggregate(
        records,
        min_days=20,
        matched_day_predicate=lambda row: bool(row.get("consistency", {}).get("matched")),
        halt_day_predicate=lambda row: row.get("thresholds", {}).get("status") == "halt",
    )

    assert monitor_like["ready_to_expand"] is False
    assert promotion_like["ready_to_expand"] is False
    assert monitor_like["valid_observation_days"] == 18
    assert promotion_like["valid_observation_days"] == 18
    assert monitor_like["halt_days"] == 1
    assert promotion_like["halt_days"] == 0
    assert monitor_like["consistency_matched_days"] == 19
    assert promotion_like["consistency_matched_days"] == 20
