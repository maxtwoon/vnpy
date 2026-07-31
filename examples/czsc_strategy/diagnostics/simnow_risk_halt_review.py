from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from declassify_historical_reports import build_banner
from simnow_artifact_loader import load_json_dict
from simnow_daily_brief_schema import format_bool, format_symbols, safe_get


HERE = Path(__file__).resolve().parent


DECISION_OPTIONS = [
    "keep_halted",
    "adjust_thresholds_with_documented_rationale",
    "retire_candidate",
    "reset_observation_window_after_strategy_change",
]


def build_review_pack(summary: dict[str, Any]) -> dict[str, Any]:
    """Build a safe manual-review packet from the authoritative run summary."""
    status = str(summary.get("automation_status") or "")
    reason = str(summary.get("automation_reason") or "")
    is_risk_halt = status == "halt" and reason != "workflow_order_safety_breach"
    consecutive = safe_get(summary, "risk_source_breakdown", "consecutive_loss", default={})
    threshold_diagnostics = list(safe_get(summary, "record", "threshold_diagnostics", default=[]))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": str(summary.get("date") or "unknown"),
        "applicable": is_risk_halt,
        "review_status": "requires_manual_review" if is_risk_halt else "not_applicable",
        "automation_status": status,
        "automation_exit_code": int(summary.get("automation_exit_code", 40) or 0),
        "automation_reason": reason,
        "automation_action": str(summary.get("automation_action") or ""),
        "automation_action_class": str(summary.get("automation_action_class") or ""),
        "automation_blocker_class": str(summary.get("automation_blocker_class") or ""),
        "manual_review": {
            "required": bool(is_risk_halt or summary.get("user_action_needed")),
            "reason": reason,
            "decision_options": DECISION_OPTIONS if is_risk_halt else [],
            "must_not_do": [
                "do_not_count_as_valid_observation",
                "do_not_resume_formal_observation_until_reviewed",
                "do_not_use_simnow_account_pnl_as_strategy_pnl",
            ] if is_risk_halt else [],
        },
        "safety_snapshot": {
            "read_only": bool(safe_get(summary, "environment_capture", "read_only", default=False)),
            "orders_sent_by_workflow": int(
                safe_get(summary, "environment_capture", "orders_sent_by_workflow", default=0) or 0
            ),
            "orders": int(safe_get(summary, "capture", "orders", default=0) or 0),
            "trades": int(safe_get(summary, "capture", "trades", default=0) or 0),
            "order_safety_status": str(safe_get(summary, "record", "order_safety_status", default="")),
        },
        "environment_snapshot": {
            "formal_readiness_overall_ready": bool(
                safe_get(summary, "formal_readiness", "overall_ready", default=False)
            ),
            "formal_readiness_blocking_reasons": list(
                safe_get(summary, "formal_readiness", "blocking_reasons", default=[])
            ),
            "ticks": int(safe_get(summary, "environment_capture", "ticks", default=0) or 0),
            "contracts_count": int(safe_get(summary, "environment_capture", "contracts_count", default=0) or 0),
            "subscribed_count": int(safe_get(summary, "environment_capture", "subscribed_count", default=0) or 0),
            "zero_tick_subscribed_symbols": list(
                safe_get(summary, "environment_capture", "zero_tick_subscribed_symbols", default=[])
            ),
        },
        "delayed_replay": {
            "available": bool(safe_get(summary, "delayed_replay", "available", default=False)),
            "status": str(safe_get(summary, "delayed_replay", "status", default="")),
            "reason": str(safe_get(summary, "delayed_replay", "reason", default="")),
            "latest_db_date": str(safe_get(summary, "delayed_replay", "latest_db_date", default="")),
            "signals": int(safe_get(summary, "delayed_replay", "signals", default=0) or 0),
            "trades": int(safe_get(summary, "delayed_replay", "trades", default=0) or 0),
            "positions": int(safe_get(summary, "delayed_replay", "positions", default=0) or 0),
            "risk_source": str(safe_get(summary, "delayed_replay", "risk_source", default="replay_only")),
        },
        "halt_metadata": {
            "rule_id": str(safe_get(summary, "record", "halt_rule_id", default="")),
            "family": str(safe_get(summary, "record", "halt_family", default="")),
            "severity": str(safe_get(summary, "record", "halt_severity", default="")),
            "trigger_metrics": list(safe_get(summary, "record", "halt_trigger_metrics", default=[])),
        },
        "threshold_diagnostics": threshold_diagnostics,
        "consecutive_loss": consecutive,
    }


def render_review_markdown(pack: dict[str, Any]) -> str:
    """Render a concise human-readable risk-halt review packet."""
    consecutive = pack.get("consecutive_loss") or {}
    lines = [
        f"# SimNow 风险停线人工复核包 - {pack.get('date', 'unknown')}",
        "",
        build_banner().rstrip("\n"),
        "",
        "## 最终状态",
        "",
        f"- applicable: `{format_bool(pack.get('applicable'))}`",
        f"- review_status: `{pack.get('review_status', '')}`",
        f"- automation_status: `{pack.get('automation_status', '')}`",
        f"- automation_exit_code: `{pack.get('automation_exit_code', '')}`",
        f"- automation_reason: `{pack.get('automation_reason', '')}`",
        f"- automation_action: `{pack.get('automation_action', '')}`",
        f"- automation_action_class: `{pack.get('automation_action_class', '')}`",
        f"- automation_blocker_class: `{pack.get('automation_blocker_class', '')}`",
        "",
        "## 安全快照",
        "",
        f"- read_only: `{format_bool(safe_get(pack, 'safety_snapshot', 'read_only', default=False))}`",
        f"- orders_sent_by_workflow: `{safe_get(pack, 'safety_snapshot', 'orders_sent_by_workflow', default=0)}`",
        f"- orders: `{safe_get(pack, 'safety_snapshot', 'orders', default=0)}`",
        f"- trades: `{safe_get(pack, 'safety_snapshot', 'trades', default=0)}`",
        f"- order_safety_status: `{safe_get(pack, 'safety_snapshot', 'order_safety_status', default='')}`",
        "",
        "## 环境与回放",
        "",
        f"- formal_readiness.overall_ready: `{format_bool(safe_get(pack, 'environment_snapshot', 'formal_readiness_overall_ready', default=False))}`",
        f"- formal_readiness.blocking_reasons: `{format_symbols(safe_get(pack, 'environment_snapshot', 'formal_readiness_blocking_reasons', default=[]))}`",
        f"- ticks: `{safe_get(pack, 'environment_snapshot', 'ticks', default=0)}`",
        f"- contracts_count: `{safe_get(pack, 'environment_snapshot', 'contracts_count', default=0)}`",
        f"- subscribed_count: `{safe_get(pack, 'environment_snapshot', 'subscribed_count', default=0)}`",
        f"- delayed_replay.available: `{format_bool(safe_get(pack, 'delayed_replay', 'available', default=False))}`",
        f"- delayed_replay.latest_db_date: `{safe_get(pack, 'delayed_replay', 'latest_db_date', default='')}`",
        f"- delayed_replay.risk_source: `{safe_get(pack, 'delayed_replay', 'risk_source', default='')}`",
        "",
        "## 阈值诊断",
        "",
    ]
    diagnostics = list(pack.get("threshold_diagnostics") or [])
    if diagnostics:
        for row in diagnostics:
            unit = str(row.get("unit") or "")
            lines.append(
                f"- {row.get('metric', '')}: `{row.get('level', '')}` "
                f"value=`{float(row.get('value', 0.0) or 0.0):.4f}{unit}`, "
                f"warning=`{float(row.get('warning', 0.0) or 0.0):.4f}{unit}`, "
                f"halt=`{float(row.get('halt', 0.0) or 0.0):.4f}{unit}`, "
                f"halt_gap=`{float(row.get('halt_gap', 0.0) or 0.0):.4f}{unit}`"
            )
    else:
        lines.append("- 无")

    lines.extend([
        "",
        "## 连续亏损来源",
        "",
        f"- complete: `{format_bool(consecutive.get('complete'))}`",
        f"- rows_available: `{format_bool(consecutive.get('rows_available'))}`",
        f"- reason: `{consecutive.get('reason', '') or '无'}`",
        f"- source: `{consecutive.get('source', '')}`",
        f"- days: `{int(consecutive.get('days', 0) or 0)}`",
        f"- start_date: `{consecutive.get('start_date', '') or '无'}`",
        f"- end_date: `{consecutive.get('end_date', '') or '无'}`",
        f"- cumulative_return_pct: `{float(consecutive.get('cumulative_return_pct', 0.0) or 0.0):.4f}%`",
        f"- abs_cumulative_return_pct: `{float(consecutive.get('abs_cumulative_return_pct', 0.0) or 0.0):.4f}%`",
    ])
    rows = list(consecutive.get("rows") or [])
    if rows:
        lines.append("- rows:")
        for row in rows:
            lines.append(
                f"- {row.get('date', '')}: daily_return=`{float(row.get('daily_return_pct', 0.0) or 0.0):.4f}%`, "
                f"equity=`{float(row.get('equity', 0.0) or 0.0):.4f}`"
            )
    else:
        lines.append("- rows: `无`")

    lines.extend([
        "",
        "## 人工决策选项",
        "",
    ])
    for option in safe_get(pack, "manual_review", "decision_options", default=[]):
        lines.append(f"- `{option}`")
    if not safe_get(pack, "manual_review", "decision_options", default=[]):
        lines.append("- 无需人工风险停线决策")

    lines.extend([
        "",
        "## 禁止事项",
        "",
    ])
    for item in safe_get(pack, "manual_review", "must_not_do", default=[]):
        lines.append(f"- `{item}`")
    if not safe_get(pack, "manual_review", "must_not_do", default=[]):
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a SimNow risk-halt manual review packet.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--run-summary", type=Path)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()

    run_summary = args.run_summary or HERE / f"simnow_run_summary_{args.date}.json"
    out_json = args.out_json or HERE / f"simnow_risk_halt_review_{args.date}.json"
    out_md = args.out_md or HERE / f"simnow_risk_halt_review_{args.date}.md"
    pack = build_review_pack(load_json_dict(run_summary))

    out_json.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_review_markdown(pack), encoding="utf-8")
    print(json.dumps({
        "date": pack["date"],
        "applicable": pack["applicable"],
        "review_status": pack["review_status"],
        "out_json": str(out_json),
        "out_md": str(out_md),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
