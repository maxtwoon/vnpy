from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from declassify_historical_reports import build_banner
from simnow_artifact_loader import load_json_dict


HERE = Path(__file__).resolve().parent

DEFAULT_ALLOWED_DECISIONS = [
    "keep_halted",
    "adjust_thresholds_with_documented_rationale",
    "retire_candidate",
    "reset_observation_window_after_strategy_change",
]
REQUIRED_FIELDS = [
    "operator_name",
    "rationale",
    "selected_decision",
    "requires_observation_window_reset",
]


def build_decision_record(review_pack: dict[str, Any]) -> dict[str, Any]:
    """Build an auditable manual decision template from a risk halt review pack."""
    manual_review = review_pack.get("manual_review") or {}
    halt_metadata = review_pack.get("halt_metadata") or {}
    consecutive_loss = review_pack.get("consecutive_loss") or {}
    allowed_decisions = list(manual_review.get("decision_options") or DEFAULT_ALLOWED_DECISIONS)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": str(review_pack.get("date") or "unknown"),
        "decision_status": "pending_decision",
        "selected_decision": "",
        "operator_name": "",
        "rationale": "",
        "requires_observation_window_reset": None,
        "next_formal_observation_allowed": False,
        "allowed_decisions": allowed_decisions,
        "required_fields": REQUIRED_FIELDS,
        "source_review": {
            "review_status": str(review_pack.get("review_status") or ""),
            "automation_status": str(review_pack.get("automation_status") or ""),
            "automation_reason": str(review_pack.get("automation_reason") or ""),
            "automation_action": str(review_pack.get("automation_action") or ""),
            "halt_rule_id": str(halt_metadata.get("rule_id") or ""),
            "halt_family": str(halt_metadata.get("family") or ""),
            "halt_severity": str(halt_metadata.get("severity") or ""),
            "halt_trigger_metrics": list(halt_metadata.get("trigger_metrics") or []),
            "consecutive_loss_complete": bool(consecutive_loss.get("complete")),
            "consecutive_loss_rows_available": bool(consecutive_loss.get("rows_available")),
            "consecutive_loss_days": int(consecutive_loss.get("days", 0) or 0),
            "consecutive_loss_start_date": str(consecutive_loss.get("start_date") or ""),
            "consecutive_loss_end_date": str(consecutive_loss.get("end_date") or ""),
            "consecutive_loss_abs_pct": float(consecutive_loss.get("abs_cumulative_return_pct", 0.0) or 0.0),
        },
        "guardrails": [
            "do_not_count_halt_as_valid_observation",
            "do_not_resume_without_decided_record",
            "reset_observation_window_after_any_strategy_or_threshold_change",
            "keep_simnow_workflow_read_only",
        ],
    }


def validate_decision_record(record: dict[str, Any]) -> list[str]:
    """Return machine-readable validation errors for a filled decision record."""
    if record.get("decision_status") != "decided":
        return ["decision_status_not_decided"]

    errors: list[str] = []
    allowed = set(record.get("allowed_decisions") or DEFAULT_ALLOWED_DECISIONS)
    if record.get("selected_decision") not in allowed:
        errors.append("selected_decision_not_allowed")
    if not str(record.get("operator_name") or "").strip():
        errors.append("operator_name_required")
    if not str(record.get("rationale") or "").strip():
        errors.append("rationale_required")
    if record.get("requires_observation_window_reset") is None:
        errors.append("requires_observation_window_reset_required")
    return errors


def render_decision_markdown(record: dict[str, Any]) -> str:
    """Render a fillable manual decision markdown record."""
    lines = [
        f"# SimNow Risk Halt Decision Record - {record.get('date', 'unknown')}",
        "",
        build_banner().rstrip("\n"),
        "",
        "## Decision State",
        "",
        f"- decision_status: `{record.get('decision_status', '')}`",
        f"- selected_decision: `{record.get('selected_decision', '') or 'TBD'}`",
        f"- operator_name: `{record.get('operator_name', '') or 'TBD'}`",
        f"- requires_observation_window_reset: `{record.get('requires_observation_window_reset')}`",
        f"- next_formal_observation_allowed: `{record.get('next_formal_observation_allowed')}`",
        "",
        "## Required Fields",
        "",
    ]
    for field in record.get("required_fields") or []:
        lines.append(f"- `{field}`")

    lines.extend([
        "",
        "## Allowed Decisions",
        "",
    ])
    for decision in record.get("allowed_decisions") or []:
        lines.append(f"- `{decision}`")

    source = record.get("source_review") or {}
    lines.extend([
        "",
        "## Source Review",
        "",
        f"- automation_status: `{source.get('automation_status', '')}`",
        f"- automation_reason: `{source.get('automation_reason', '')}`",
        f"- halt_trigger_metrics: `{','.join(str(x) for x in source.get('halt_trigger_metrics') or [])}`",
        f"- consecutive_loss_days: `{source.get('consecutive_loss_days', 0)}`",
        f"- consecutive_loss_start_date: `{source.get('consecutive_loss_start_date', '')}`",
        f"- consecutive_loss_end_date: `{source.get('consecutive_loss_end_date', '')}`",
        f"- consecutive_loss_abs_pct: `{float(source.get('consecutive_loss_abs_pct', 0.0) or 0.0):.4f}%`",
        "",
        "## Rationale",
        "",
        "TBD",
        "",
        "## Guardrails",
        "",
    ])
    for guardrail in record.get("guardrails") or []:
        lines.append(f"- `{guardrail}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or validate a SimNow risk-halt decision record.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--review-json", type=Path)
    parser.add_argument("--decision-json", type=Path)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    review_json = args.review_json or HERE / f"simnow_risk_halt_review_{args.date}.json"
    out_json = args.out_json or HERE / f"simnow_risk_halt_decision_{args.date}.json"
    out_md = args.out_md or HERE / f"simnow_risk_halt_decision_{args.date}.md"

    if args.validate:
        decision_json = args.decision_json or out_json
        record = load_json_dict(decision_json)
        errors = validate_decision_record(record)
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 2

    record = build_decision_record(load_json_dict(review_json))
    out_json.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_decision_markdown(record), encoding="utf-8")
    print(json.dumps({
        "date": record["date"],
        "decision_status": record["decision_status"],
        "out_json": str(out_json),
        "out_md": str(out_md),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
