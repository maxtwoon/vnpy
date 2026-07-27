import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

import simnow_automation_policy as policy_mod  # noqa: E402
import simnow_daily_brief as brief_mod  # noqa: E402
import simnow_run_summary as summary_mod  # noqa: E402


def _pending_summary(reason: str = "kline_coverage_incomplete") -> dict:
    return {
        "record": {
            "status": "pending",
            "valid_observation": False,
            "reason": reason,
            "threshold_status": "pass",
            "threshold_rows": [],
        },
        "kline": {
            "missing_symbols": ["AP888"] if reason == "kline_coverage_incomplete" else [],
            "short_symbols": [],
            "min_bars_per_symbol": 30,
        },
    }


def test_run_summary_and_daily_brief_use_shared_automation_policy_functions():
    assert summary_mod.classify_automation_status is policy_mod.classify_automation_status
    assert brief_mod.needs_user_action is policy_mod.needs_user_action


def test_classify_automation_status_pending_uses_shared_policy():
    result = policy_mod.classify_automation_status(_pending_summary())

    assert result["automation_status"] == "pending"
    assert result["automation_exit_code"] == 20
    assert result["automation_reason"] == "kline_coverage_incomplete"
    assert result["automation_action"] == "resolve pending gate before counting"
    assert result["automation_action_class"] == "wait_for_data"
    assert result["automation_blocker_class"] == "wait"


def test_needs_user_action_uses_structured_blocker_class_first():
    assert policy_mod.needs_user_action({
        "automation_status": "pending",
        "automation_reason": "historical_db_lag",
        "automation_blocker_class": "review_now",
    }) is True
    assert policy_mod.needs_user_action({
        "automation_status": "pending",
        "automation_reason": "subscription_incomplete",
        "automation_blocker_class": "wait",
    }) is True


def test_conclusion_text_matches_shared_status_policy():
    pending_text = policy_mod.conclusion_text(
        {"automation_status": "pending"},
        "resolve pending gate before counting",
    )
    skipped_text = policy_mod.conclusion_text(
        {"automation_status": "skipped"},
        "no valid market data / rerun next valid session",
    )
    halt_text = policy_mod.conclusion_text(
        {"automation_status": "halt"},
        "stop automation and review manually",
    )

    assert "resolve pending gate before counting" in pending_text
    assert "rerun next valid session" in skipped_text
    assert "stop automation and review manually" in halt_text
