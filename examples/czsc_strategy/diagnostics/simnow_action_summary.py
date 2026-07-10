from __future__ import annotations

from typing import Any


def _record_reason(row: dict[str, Any]) -> str:
    """Extract the primary reason for a daily record's status."""
    if row.get("skip_reason"):
        return str(row["skip_reason"])
    consistency = row.get("consistency") or {}
    if consistency.get("reason"):
        return str(consistency["reason"])
    thresholds = row.get("thresholds") or {}
    if thresholds.get("status") in {"warning", "halt"}:
        bad = [
            str(item.get("metric"))
            for item in thresholds.get("rows", [])
            if item.get("level") in {"warning", "halt"}
        ]
        return ",".join(bad) if bad else str(thresholds.get("status"))
    return ""


def _pass_gaps(record: dict[str, Any]) -> list[str]:
    """List the gates that prevent a pass row from being a valid observation."""
    gaps: list[str] = []
    if record.get("status") != "pass":
        gaps.append("status is not pass")
    consistency = record.get("consistency") or {}
    if not consistency.get("matched"):
        gaps.append("consistency not matched")
    thresholds = record.get("thresholds") or {}
    if thresholds.get("status") != "pass":
        gaps.append(f"thresholds {thresholds.get('status')}")
    safety = record.get("order_safety") or {}
    if safety.get("status") != "pass":
        gaps.append(f"order_safety {safety.get('status')}")
    subscription = record.get("subscription_coverage") or {}
    if subscription.get("missing_symbols"):
        gaps.append(
            f"missing subscriptions: {','.join(str(x) for x in subscription['missing_symbols'])}"
        )
    kline = record.get("kline_coverage") or {}
    if kline.get("missing_symbols"):
        gaps.append(f"missing kline: {','.join(str(x) for x in kline['missing_symbols'])}")
    if kline.get("short_symbols"):
        gaps.append(f"short kline: {','.join(str(x) for x in kline['short_symbols'])}")
    return gaps


def action_recommendation(record: dict[str, Any]) -> dict[str, Any]:
    """Return a human-readable action recommendation for a single daily record."""
    status = str(record.get("status") or "unknown")
    reason = _record_reason(record)
    counts = bool(record.get("valid_observation"))
    if status == "skipped":
        severity = "info"
        if reason == "simnow_no_ticks":
            action = "可能是节假日、非交易时段或无行情；建议下一个有效交易时段重跑。"
        elif reason == "ctp_disconnect_097_no_snapshot":
            action = "CTP 连接失败；建议检查 SimNow 服务、网络、账号状态。"
        elif reason == "simnow_no_snapshot":
            action = "无有效快照；建议检查交易时段和连接日志。"
        else:
            action = "当日未产生有效市场数据；建议检查交易时段和连接日志。"
    elif status == "pending":
        severity = "medium"
        if reason == "historical_db_lag":
            action = "历史 DB 未覆盖当天；建议等待或执行 backfill。"
        elif reason == "event_surface_mismatch":
            action = "SimNow live capture 与 replay 事件面不一致；建议核对 strategy event surface 与 raw account surface 的对比规则。"
        elif reason == "subscription_incomplete":
            missing = record.get("subscription_coverage", {}).get("missing_symbols", [])
            action = (
                f"缺少订阅品种：{','.join(str(x) for x in missing)}；"
                f"建议检查 simnow_contract_map.json 和订阅结果。"
            )
        elif reason == "kline_coverage_incomplete":
            missing = record.get("kline_coverage", {}).get("missing_symbols", [])
            action = (
                f"缺少 K 线品种：{','.join(str(x) for x in missing)}；"
                f"建议在活跃交易时段重新采集。"
            )
        elif reason == "kline_coverage_too_short":
            short = record.get("kline_coverage", {}).get("short_symbols", [])
            min_bars = record.get("kline_coverage", {}).get("min_bars_per_symbol")
            action = (
                f"K 线覆盖不足品种：{','.join(str(x) for x in short)}"
                f"（阈值 {min_bars} 根）；建议延长 DurationSeconds。"
            )
        elif reason == "simnow_or_replay_export_missing":
            action = "缺少 capture 或 replay JSON；建议检查 wrapper 输出。"
        else:
            action = "观察条件未满足；建议查看详细日志。"
    elif status == "halt":
        severity = "critical"
        if reason == "workflow_order_safety_breach":
            action = "观察流程疑似下单，必须停止观察并人工审查。"
        else:
            rows = record.get("thresholds", {}).get("rows", [])
            bad = [row for row in rows if row.get("level") in {"warning", "halt"}]
            parts = [f"{row['metric']}={row['value']:.4f}{row['unit']}" for row in bad]
            action = f"阈值触发：{', '.join(parts)}；建议检查风险敞口并复核阈值配置。"
    elif status == "pass":
        if counts:
            severity = "ok"
            action = "计入 20 日有效观察。"
        else:
            severity = "warning"
            gaps = _pass_gaps(record)
            action = "status=pass 但仍有 gate 未满足：" + "; ".join(gaps) + "。"
    else:
        severity = "unknown"
        action = "未知状态；建议人工复查。"
    return {
        "date": str(record.get("date") or ""),
        "status": status,
        "reason": reason,
        "severity": severity,
        "action": action,
        "counts_for_20d": counts,
    }


def build_action_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a chronological action summary for a list of daily records."""
    ordered = sorted(records, key=lambda x: str(x.get("date", "")))
    return [action_recommendation(row) for row in ordered]
