import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_ledger_summary_schema import (  # noqa: E402
    build_daily_brief_20d_lines,
    filter_safe_ledger_summary,
)


def _ledger_summary() -> dict:
    return {
        "generated_at": "2026-07-22T10:00:00+08:00",
        "min_days": 20,
        "observation_start_date": "2026-07-14",
        "excluded_before_start_count": 12,
        "total_rows": 5,
        "valid_observation_days": 3,
        "pending_days": 2,
        "skipped_days": 1,
        "halt_days": 0,
        "failed_days": 0,
        "latest_date": "2026-07-22",
        "latest_valid_date": "2026-07-21",
        "consecutive_valid_days": 2,
        "ready_to_expand": False,
        "promotion_blockers": ["need_17_more_valid_observation_days"],
        "reason_counts": {"historical_db_lag": 2},
        "reason_governance_counts": {
            "data_readiness_gap": 2,
            "expected_market_or_session": 1,
        },
        "reasonableness_counts": {
            "reasonable": 3,
        },
        "reason_rationality_verdict": "mostly_reasonable_non_code",
        "reason_rationality_cn": "最近阻塞日主要由环境、时段或数据准备因素构成，不应直接视为代码失败。",
        "pareto_summary": {
            "top1_reason": "historical_db_lag",
            "top1_share_pct": 66.7,
            "top3_share_pct": 100.0,
            "total_blocking_days": 3,
            "top3_blocking_days": 3,
            "summary_cn": "前 3 个阻塞原因占 100.0%（3/3），其中首要原因 historical_db_lag 占 66.7%。",
        },
        "operational_bucket_counts": {
            "data_pending_days": 2,
            "trading_session_skipped_days": 1,
        },
        "blocking_action_counts": {
            "rerun_next_session": 1,
            "wait_for_data": 2,
        },
        "automation_status_counts": {"pending": 2, "valid": 3},
        "latest_action": {
            "reason": "historical_db_lag",
            "action_class": "wait_for_data",
            "blocker_class": "wait",
        },
        "next_action": "resolve latest pending reason",
        "next_action_class": "wait_for_data",
        "latest_record": {"status": "pending"},
        "unsafe_field": "should_not_pass_through",
    }


def test_filter_safe_ledger_summary_keeps_only_allowed_fields():
    filtered = filter_safe_ledger_summary(_ledger_summary())

    assert filtered["available"] is True
    assert filtered["min_days"] == 20
    assert filtered["valid_observation_days"] == 3
    assert filtered["next_action_class"] == "wait_for_data"
    assert filtered["blocking_action_counts"] == {
        "rerun_next_session": 1,
        "wait_for_data": 2,
    }
    assert filtered["reason_governance_counts"] == {
        "data_readiness_gap": 2,
        "expected_market_or_session": 1,
    }
    assert filtered["reason_rationality_verdict"] == "mostly_reasonable_non_code"
    assert "unsafe_field" not in filtered
    assert "latest_record" not in filtered


def test_build_daily_brief_20d_lines_renders_shared_progress_fields():
    lines = build_daily_brief_20d_lines(filter_safe_ledger_summary(_ledger_summary()))

    assert "- valid_observation_days: `3/20`" in lines
    assert "- consecutive_valid_days: `2`" in lines
    assert "- ready_to_expand: `false`" in lines
    assert "- observation_start_date: `2026-07-14`" in lines
    assert "- excluded_before_start_count: `12`" in lines
    assert "- next_action: `resolve latest pending reason`" in lines
    assert "- next_action_class: `wait_for_data`" in lines
    assert "- promotion_blockers: `need_17_more_valid_observation_days`" in lines
    assert "- reason_rationality_verdict: `mostly_reasonable_non_code`" in lines
    assert "- pareto_summary.top3_share_pct: `100.0`" in lines
    assert "- reason_governance_counts.data_readiness_gap: `2`" in lines
    assert "- reason_governance_counts.expected_market_or_session: `1`" in lines
    assert "- blocking_action_counts.rerun_next_session: `1`" in lines
    assert "- blocking_action_counts.wait_for_data: `2`" in lines
    assert "- operational_bucket_counts.data_pending_days: `2`" in lines
    assert "- operational_bucket_counts.trading_session_skipped_days: `1`" in lines


def test_build_daily_brief_20d_lines_handles_missing_ledger_summary():
    assert build_daily_brief_20d_lines({"available": False, "reason": "missing_ledger_summary"}) == [
        "- ledger_summary 不可用: `missing_ledger_summary`"
    ]
