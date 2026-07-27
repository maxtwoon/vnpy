import json
import sys
from pathlib import Path

import pytest


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_risk_halt_decision import (  # noqa: E402
    build_decision_record,
    render_decision_markdown,
    validate_decision_record,
)


def _review_pack() -> dict:
    return {
        "date": "2026-07-24",
        "applicable": True,
        "review_status": "requires_manual_review",
        "automation_status": "halt",
        "automation_reason": "consecutive_loss_abs_pct",
        "automation_action": "stop automation and review manually",
        "manual_review": {
            "required": True,
            "decision_options": [
                "keep_halted",
                "adjust_thresholds_with_documented_rationale",
                "retire_candidate",
                "reset_observation_window_after_strategy_change",
            ],
        },
        "halt_metadata": {
            "rule_id": "threshold_breach",
            "family": "strategy_risk",
            "severity": "critical",
            "trigger_metrics": ["consecutive_loss_abs_pct"],
        },
        "consecutive_loss": {
            "complete": True,
            "rows_available": True,
            "days": 6,
            "start_date": "2023-06-19",
            "end_date": "2023-06-28",
            "abs_cumulative_return_pct": 0.1217590817,
        },
    }


def test_build_decision_record_template_is_pending_and_auditable():
    record = build_decision_record(_review_pack())

    assert record["date"] == "2026-07-24"
    assert record["decision_status"] == "pending_decision"
    assert record["selected_decision"] == ""
    assert record["requires_observation_window_reset"] is None
    assert record["source_review"]["automation_reason"] == "consecutive_loss_abs_pct"
    assert record["source_review"]["halt_trigger_metrics"] == ["consecutive_loss_abs_pct"]
    assert record["allowed_decisions"] == [
        "keep_halted",
        "adjust_thresholds_with_documented_rationale",
        "retire_candidate",
        "reset_observation_window_after_strategy_change",
    ]
    assert "operator_name" in record["required_fields"]
    assert "rationale" in record["required_fields"]
    assert "password" not in json.dumps(record, ensure_ascii=False).lower()


def test_validate_decision_record_accepts_documented_choice():
    record = build_decision_record(_review_pack())
    record["decision_status"] = "decided"
    record["selected_decision"] = "keep_halted"
    record["requires_observation_window_reset"] = False
    record["operator_name"] = "risk-reviewer"
    record["rationale"] = "Risk threshold halt is still valid."

    assert validate_decision_record(record) == []


def test_validate_decision_record_rejects_invalid_choice_and_missing_fields():
    record = build_decision_record(_review_pack())
    record["decision_status"] = "decided"
    record["selected_decision"] = "resume_observation"

    errors = validate_decision_record(record)

    assert "selected_decision_not_allowed" in errors
    assert "operator_name_required" in errors
    assert "rationale_required" in errors
    assert "requires_observation_window_reset_required" in errors


def test_render_decision_markdown_contains_required_fields_and_options():
    text = render_decision_markdown(build_decision_record(_review_pack()))

    assert "# SimNow Risk Halt Decision Record - 2026-07-24" in text
    assert "decision_status: `pending_decision`" in text
    assert "`keep_halted`" in text
    assert "`reset_observation_window_after_strategy_change`" in text
    assert "operator_name" in text
    assert "rationale" in text
