from __future__ import annotations

from typing import Any


def _halt_trigger_metrics(record: dict[str, Any]) -> list[str]:
    thresholds = record.get("thresholds") or {}
    metrics = [
        str(row.get("metric") or "")
        for row in thresholds.get("rows", [])
        if row.get("level") == "halt" and str(row.get("metric") or "")
    ]
    if metrics:
        return metrics

    consistency = record.get("consistency") or {}
    reason = str(consistency.get("reason") or "")
    if reason and reason != "workflow_order_safety_breach":
        return [item for item in reason.split(",") if item]
    return []


def extract_halt_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Return a unified halt metadata block for halted records."""
    if str(record.get("status") or "") != "halt":
        return {}

    order_safety = record.get("order_safety") or {}
    consistency = record.get("consistency") or {}
    if (
        order_safety.get("status") == "halt"
        or str(consistency.get("reason") or "") == "workflow_order_safety_breach"
    ):
        return {
            "rule_id": "workflow_order_safety_breach",
            "family": "order_safety",
            "severity": "critical",
            "trigger_metrics": [],
            "explained_cn": "只读观察流程检测到下单动作，必须停止自动化并人工复核。",
        }

    trigger_metrics = _halt_trigger_metrics(record)
    metrics_text = ",".join(trigger_metrics) if trigger_metrics else "unknown_metric"
    return {
        "rule_id": "threshold_breach",
        "family": "strategy_risk",
        "severity": "critical",
        "trigger_metrics": trigger_metrics,
        "explained_cn": f"风险阈值触发停线：{metrics_text}。",
    }


def halt_family(record: dict[str, Any]) -> str:
    """Return the unified halt family for aggregate statistics."""
    halt = record.get("halt") or {}
    family = str(halt.get("family") or "")
    if family:
        return family
    meta = extract_halt_metadata(record)
    return str(meta.get("family") or "")
