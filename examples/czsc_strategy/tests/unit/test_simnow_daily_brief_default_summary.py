import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_daily_brief_default_summary import (  # noqa: E402
    build_missing_run_summary_payload,
    normalize_daily_brief_summary,
    resolve_failed_action_text,
)


def test_build_missing_run_summary_payload_matches_daily_brief_contract():
    assert build_missing_run_summary_payload() == {
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


def test_normalize_daily_brief_summary_uses_missing_summary_payload():
    assert normalize_daily_brief_summary({}) == build_missing_run_summary_payload()


def test_normalize_daily_brief_summary_defaults_failed_exit_code():
    normalized = normalize_daily_brief_summary(
        {
            "date": "2026-07-22",
            "automation_status": "failed",
            "automation_reason": "wrapper_failed",
            "automation_action": "inspect artifacts",
        }
    )

    assert normalized["automation_exit_code"] == 40


def test_normalize_daily_brief_summary_defaults_nonfailed_exit_code_to_zero():
    normalized = normalize_daily_brief_summary(
        {
            "date": "2026-07-22",
            "automation_status": "pending",
            "automation_reason": "kline_coverage_incomplete",
            "automation_action": "wait for data",
        }
    )

    assert normalized["automation_exit_code"] == 0


def test_normalize_daily_brief_summary_preserves_explicit_exit_code():
    normalized = normalize_daily_brief_summary(
        {
            "date": "2026-07-22",
            "automation_status": "pending",
            "automation_exit_code": 20,
            "automation_reason": "kline_coverage_incomplete",
            "automation_action": "wait for data",
        }
    )

    assert normalized["automation_exit_code"] == 20


def test_resolve_failed_action_text_preserves_explicit_action():
    assert resolve_failed_action_text(
        {
            "automation_status": "failed",
            "automation_action": "inspect artifacts",
        }
    ) == "inspect artifacts"


def test_resolve_failed_action_text_uses_canonical_fallback_when_missing():
    assert resolve_failed_action_text(
        {
            "automation_status": "failed",
            "automation_action": "",
        }
    ) == "请检查 wrapper 输出和 artifact 完整性。"
