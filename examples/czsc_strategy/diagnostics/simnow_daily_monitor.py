from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from simnow_observation_rules import is_valid_observation


HERE = Path(__file__).resolve().parent
DEFAULT_BASELINE = HERE / "simnow_precheck_risk_report.json"
DEFAULT_THRESHOLDS = HERE / "simnow_risk_thresholds.json"
DEFAULT_LEDGER = HERE / "simnow_observation_ledger.jsonl"
DEFAULT_REPORT = HERE / "simnow_20d_observation_report.md"

WATCH_SYMBOLS = {"SC888", "AP888", "A888", "ZN888"}
WATCH_STRATEGY_KEYWORDS = {
    "SC_SHORT": ("SC888", ("sell", "short", "卖", "空")),
    "AP_TRAILING": ("AP888", ("trailing", "移动止损")),
    "A_TRAILING": ("A888", ("trailing", "移动止损")),
    "ZN_SHORT": ("ZN888", ("sell", "short", "卖", "空")),
    "SECOND_BUY_LONG": (None, ("二买", "second_buy")),
}


@dataclass(frozen=True)
class Threshold:
    name: str
    baseline: float
    warning: float
    halt: float
    direction: str
    unit: str = ""


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _risk_root(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("portfolio_risk") or payload.get("risk") or payload


def _abs_pct(value: float | int | None) -> float:
    return abs(float(value or 0.0))


def build_thresholds(baseline_payload: dict[str, Any], warning_ratio: float = 0.9) -> dict[str, Threshold]:
    """Build SimNow observation thresholds from the accepted historical baseline.

    Warning fires at 90% of the accepted baseline by default; halt fires when
    the accepted baseline is exceeded. Loss and drawdown metrics are compared
    by absolute adverse magnitude.
    """
    risk = _risk_root(baseline_payload)
    consecutive = risk.get("max_consecutive_loss") or {}
    symbol_conc = risk.get("symbol_concentration") or {}
    strategy_conc = risk.get("strategy_concentration") or {}
    specs = {
        "single_day_loss_abs_pct": (_abs_pct(risk.get("max_single_day_loss_pct")), "high", "%"),
        "drawdown_abs_pct": (_abs_pct(risk.get("max_drawdown_pct")), "high", "%"),
        "gross_exposure": (float(risk.get("max_gross_exposure", 0.0)), "high", ""),
        "net_exposure_abs": (_abs_pct(risk.get("max_net_exposure", 0.0)), "high", ""),
        "both_long_short_symbols": (float(risk.get("max_both_long_short_symbols", 0)), "high", ""),
        "consecutive_loss_days": (float(consecutive.get("days", 0)), "high", "days"),
        "consecutive_loss_abs_pct": (_abs_pct(consecutive.get("cumulative_return_pct")), "high", "%"),
        "symbol_top1_abs_share": (float(symbol_conc.get("top1_abs_share", 0.0)), "high", ""),
        "strategy_top1_abs_share": (float(strategy_conc.get("top1_abs_share", 0.0)), "high", ""),
    }
    return {
        name: Threshold(
            name=name,
            baseline=baseline,
            warning=baseline * warning_ratio,
            halt=baseline,
            direction=direction,
            unit=unit,
        )
        for name, (baseline, direction, unit) in specs.items()
    }


def load_thresholds_config(path: Path) -> dict[str, Threshold]:
    payload = load_json(path)
    metrics = payload.get("metrics") or {}
    if not metrics:
        raise ValueError(f"threshold config has no metrics: {path}")
    thresholds: dict[str, Threshold] = {}
    for name, row in metrics.items():
        thresholds[name] = Threshold(
            name=name,
            baseline=float(row["baseline"]),
            warning=float(row["warning"]),
            halt=float(row["halt"]),
            direction=str(row.get("direction", "high")),
            unit=str(row.get("unit", "")),
        )
    return thresholds


def normalize_daily_metrics(raw: dict[str, Any]) -> dict[str, float]:
    """Normalize daily/rolling risk fields for threshold checks."""
    if not raw:
        return {}
    consecutive = raw.get("max_consecutive_loss") or raw.get("consecutive_loss") or {}
    symbol_conc = raw.get("symbol_concentration") or {}
    strategy_conc = raw.get("strategy_concentration") or {}
    return {
        "single_day_loss_abs_pct": _abs_pct(raw.get("daily_return_pct", raw.get("max_single_day_loss_pct"))),
        "drawdown_abs_pct": _abs_pct(raw.get("drawdown_pct", raw.get("max_drawdown_pct"))),
        "gross_exposure": float(raw.get("gross_exposure", raw.get("max_gross_exposure", 0.0)) or 0.0),
        "net_exposure_abs": _abs_pct(raw.get("net_exposure", raw.get("max_net_exposure", 0.0))),
        "both_long_short_symbols": float(
            raw.get("both_long_short_symbols", raw.get("max_both_long_short_symbols", 0)) or 0
        ),
        "consecutive_loss_days": float(consecutive.get("days", raw.get("consecutive_loss_days", 0)) or 0),
        "consecutive_loss_abs_pct": _abs_pct(
            consecutive.get("cumulative_return_pct", raw.get("consecutive_loss_return_pct", 0.0))
        ),
        "symbol_top1_abs_share": float(symbol_conc.get("top1_abs_share", raw.get("symbol_top1_abs_share", 0.0)) or 0.0),
        "strategy_top1_abs_share": float(
            strategy_conc.get("top1_abs_share", raw.get("strategy_top1_abs_share", 0.0)) or 0.0
        ),
    }


def evaluate_thresholds(metrics: dict[str, float], thresholds: dict[str, Threshold]) -> dict[str, Any]:
    rows = []
    status = "pass"
    for name, threshold in thresholds.items():
        value = float(metrics.get(name, 0.0))
        level = "pass"
        if value > threshold.halt:
            level = "halt"
            status = "halt"
        elif value >= threshold.warning and status != "halt":
            level = "warning"
            status = "warning"
        rows.append({
            "metric": name,
            "value": value,
            "warning": threshold.warning,
            "halt": threshold.halt,
            "baseline": threshold.baseline,
            "level": level,
            "unit": threshold.unit,
        })
    return {"status": status, "rows": rows}


def _event_key(event: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(event.get("dt") or event.get("datetime") or event.get("time") or ""),
        str(event.get("symbol") or ""),
        str(event.get("strategy") or event.get("position") or ""),
        str(event.get("operate") or event.get("action") or ""),
    )


def compare_simnow_replay(simnow: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    """Compare exported SimNow events with replay events on signal/trade/position surfaces."""
    if replay.get("meta", {}).get("replay_available") is False:
        reason = replay.get("meta", {}).get("replay_unavailable_reason") or "replay_unavailable"
        return {
            "matched": False,
            "details": {},
            "reason": reason,
        }
    categories = ["signals", "trades", "positions"]
    details = {}
    all_match = True
    for category in categories:
        left = {_event_key(x): x for x in simnow.get(category, [])}
        right = {_event_key(x): x for x in replay.get(category, [])}
        missing = sorted(right.keys() - left.keys())
        extra = sorted(left.keys() - right.keys())
        matched = not missing and not extra
        all_match = all_match and matched
        details[category] = {
            "matched": matched,
            "simnow_count": len(left),
            "replay_count": len(right),
            "missing_in_simnow": [list(x) for x in missing],
            "extra_in_simnow": [list(x) for x in extra],
        }
    return {"matched": all_match, "details": details}


def attribution_watch(record: dict[str, Any]) -> dict[str, Any]:
    """Highlight the risk buckets that should be watched during the 20-day SimNow observation."""
    trades = record.get("simnow", {}).get("trades") or record.get("replay", {}).get("trades") or []
    rows: dict[str, dict[str, Any]] = {
        name: {"count": 0, "pnl_pct": 0.0}
        for name in WATCH_STRATEGY_KEYWORDS
    }
    for trade in trades:
        symbol = str(trade.get("symbol") or "").upper()
        strategy = str(trade.get("strategy") or trade.get("reason") or trade.get("operate") or "")
        pnl = float(trade.get("pnl_pct", trade.get("weighted_pnl_pct", 0.0)) or 0.0)
        for bucket, (want_symbol, keywords) in WATCH_STRATEGY_KEYWORDS.items():
            symbol_ok = want_symbol is None or symbol == want_symbol
            keyword_ok = any(key.lower() in strategy.lower() for key in keywords)
            if symbol_ok and keyword_ok:
                rows[bucket]["count"] += 1
                rows[bucket]["pnl_pct"] += pnl
    return rows


def _capture_skip_reason(simnow: dict[str, Any]) -> str:
    raw = simnow.get("raw") or {}
    ticks = raw.get("ticks") or []
    contracts_count = int(raw.get("contracts_count", 0) or 0)
    accounts = raw.get("accounts") or []
    positions = raw.get("positions") or []
    subscribed = raw.get("subscribed") or []
    logs = raw.get("logs") or []
    if ticks:
        return ""
    if contracts_count or accounts or positions or subscribed:
        return "simnow_no_ticks"
    if any("097" in str(row.get("msg") or "") for row in logs):
        return "ctp_disconnect_097_no_snapshot"
    if logs:
        return "simnow_no_snapshot"
    return "simnow_no_snapshot"


def subscription_coverage(simnow: dict[str, Any]) -> dict[str, Any]:
    contract_map = simnow.get("meta", {}).get("contract_map") or {}
    expected = sorted(
        str(symbol).upper()
        for symbol, row in contract_map.items()
        if isinstance(row, dict) and row.get("enabled", True)
    )
    subscribed_rows = simnow.get("raw", {}).get("subscribed") or []
    subscribed = sorted({
        str(row.get("research_symbol") or "").upper()
        for row in subscribed_rows
        if row.get("research_symbol")
    })
    return {
        "expected_symbols": expected,
        "subscribed_symbols": subscribed,
        "missing_symbols": sorted(set(expected) - set(subscribed)),
    }


def order_safety(simnow: dict[str, Any]) -> dict[str, Any]:
    """Verify the observation workflow stayed read-only.

    Raw account orders/trades are audit evidence only. They may include manual,
    historical, or broker-side callbacks, so the hard gate is whether this
    workflow declared read-only mode and recorded zero order actions of its own.
    """
    meta = simnow.get("meta") or {}
    raw = simnow.get("raw") or {}
    read_only = meta.get("read_only")
    orders_sent = int(meta.get("orders_sent_by_workflow", 0) or 0)
    actions = meta.get("workflow_order_actions") or []
    status = "pass" if read_only is True else "unknown"
    reasons = []
    if read_only is False:
        status = "halt"
        reasons.append("read_only_disabled")
    elif read_only is None:
        reasons.append("read_only_not_declared")
    if orders_sent != 0 or actions:
        status = "halt"
        reasons.append("workflow_order_actions_present")
    return {
        "status": status,
        "read_only": read_only is True,
        "orders_sent_by_workflow": orders_sent,
        "workflow_order_actions": actions,
        "observed_raw_orders": len(raw.get("orders") or []),
        "observed_raw_trades": len(raw.get("trades") or []),
        "reasons": reasons,
    }


def make_record(
    trade_date: str,
    baseline_payload: dict[str, Any],
    simnow: dict[str, Any] | None = None,
    replay: dict[str, Any] | None = None,
    kline: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
    thresholds: dict[str, Threshold] | None = None,
) -> dict[str, Any]:
    simnow = simnow or {}
    replay = replay or {}
    kline = kline or {}
    thresholds = thresholds or build_thresholds(baseline_payload)
    metrics = normalize_daily_metrics(risk or simnow.get("risk") or replay.get("risk") or {})
    threshold_result = evaluate_thresholds(metrics, thresholds)
    skip_reason = _capture_skip_reason(simnow) if simnow else ""
    subscription = subscription_coverage(simnow) if simnow else {}
    safety = order_safety(simnow) if simnow else {}
    if skip_reason:
        consistency = {
            "matched": False,
            "details": {},
            "reason": skip_reason,
        }
    else:
        consistency = compare_simnow_replay(simnow, replay) if simnow and replay else {
            "matched": False,
            "details": {},
            "reason": "simnow_or_replay_export_missing",
        }
    if not skip_reason and subscription.get("missing_symbols"):
        consistency = {
            **consistency,
            "matched": False,
            "reason": "subscription_incomplete",
            "subscription_missing_symbols": subscription.get("missing_symbols", []),
        }
    elif not skip_reason and kline.get("missing_symbols"):
        consistency = {
            **consistency,
            "matched": False,
            "reason": "kline_coverage_incomplete",
            "kline_missing_symbols": kline.get("missing_symbols", []),
        }
    elif not skip_reason and kline.get("short_symbols"):
        consistency = {
            **consistency,
            "matched": False,
            "reason": "kline_coverage_too_short",
            "kline_short_symbols": kline.get("short_symbols", []),
            "min_bars_per_symbol": kline.get("min_bars_per_symbol"),
        }
    if safety.get("status") == "halt":
        consistency = {
            **consistency,
            "matched": False,
            "reason": "workflow_order_safety_breach",
            "order_safety_reasons": safety.get("reasons", []),
        }
    record = {
        "date": trade_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate": baseline_payload.get("candidate"),
        "simnow": simnow,
        "replay": replay,
        "subscription_coverage": subscription,
        "order_safety": safety,
        "kline_coverage": kline,
        "risk_metrics": metrics,
        "thresholds": threshold_result,
        "consistency": consistency,
    }
    record["attribution_watch"] = attribution_watch(record)
    record["skip_reason"] = skip_reason
    if skip_reason:
        record["status"] = "skipped"
    else:
        record["status"] = "halt" if threshold_result["status"] == "halt" or safety.get("status") == "halt" else (
            "pass" if consistency.get("matched") else "pending"
        )
    record["valid_observation"] = is_valid_observation(record)
    return record


def append_ledger(path: Path, record: dict[str, Any]) -> None:
    upsert_ledger(path, record)


def upsert_ledger(path: Path, record: dict[str, Any]) -> None:
    trade_date = str(record.get("date") or "")
    if not trade_date:
        raise ValueError("ledger record must contain a non-empty date")
    records = read_ledger(path)
    replaced = False
    next_records: list[dict[str, Any]] = []
    for row in records:
        if str(row.get("date") or "") == trade_date:
            if not replaced:
                next_records.append(record)
                replaced = True
            continue
        next_records.append(row)
    if not replaced:
        next_records.append(record)
    next_records.sort(key=lambda x: str(x.get("date", "")))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in next_records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _record_reason(row: dict[str, Any]) -> str:
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


def _count_by(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = value or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _consecutive_clean_days(records: list[dict[str, Any]]) -> int:
    count = 0
    for row in reversed(records):
        if is_valid_observation(row):
            count += 1
        else:
            break
    return count


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


def build_20d_report(records: list[dict[str, Any]], min_days: int = 20) -> dict[str, Any]:
    ordered = sorted(records, key=lambda x: str(x.get("date", "")))
    recent = ordered[-min_days:]
    status_counts = _count_by([str(row.get("status") or "unknown") for row in recent])
    pass_days = sum(1 for row in recent if row.get("status") == "pass")
    valid_days = sum(1 for row in recent if is_valid_observation(row))
    pending_days = sum(1 for row in recent if row.get("status") == "pending")
    skipped_days = sum(1 for row in recent if row.get("status") == "skipped")
    matched_days = sum(1 for row in recent if row.get("consistency", {}).get("matched"))
    halt_days = sum(
        1
        for row in recent
        if row.get("thresholds", {}).get("status") == "halt" or row.get("order_safety", {}).get("status") == "halt"
    )
    warning_days = sum(1 for row in recent if row.get("thresholds", {}).get("status") == "warning")
    last_valid = next((row for row in reversed(ordered) if is_valid_observation(row)), None)
    clean_streak = _consecutive_clean_days(ordered)
    blockers = []
    if valid_days < min_days:
        blockers.append(f"need_{min_days - valid_days}_more_valid_observation_days")
    if pending_days:
        blockers.append("pending_days_present")
    if skipped_days:
        blockers.append("skipped_days_present")
    if pass_days != len(recent):
        blockers.append("non_pass_days_present")
    if matched_days != len(recent):
        blockers.append("consistency_not_fully_matched")
    if halt_days:
        blockers.append("halt_threshold_breached")
    ready = not blockers
    reason_counts = _count_by([
        _record_reason(row)
        for row in recent
        if row.get("status") in {"pending", "skipped"} or row.get("thresholds", {}).get("status") in {"warning", "halt"}
    ])
    return {
        "required_days": min_days,
        "observed_days": len(recent),
        "valid_observation_days": valid_days,
        "status_counts": status_counts,
        "pass_days": pass_days,
        "pending_days": pending_days,
        "skipped_days": skipped_days,
        "consistency_matched_days": matched_days,
        "warning_days": warning_days,
        "halt_days": halt_days,
        "latest_record_date": str(ordered[-1].get("date")) if ordered else "",
        "last_valid_observation_date": str(last_valid.get("date")) if last_valid else "",
        "consecutive_clean_days": clean_streak,
        "promotion_blockers": blockers,
        "reason_counts": reason_counts,
        "ready_to_expand": ready,
        "records": recent,
    }


def write_20d_markdown(summary: dict[str, Any], out: Path) -> None:
    lines = [
        "# SimNow 20-Day Observation Report",
        "",
        f"- observed_days: `{summary['observed_days']}/{summary['required_days']}`",
        f"- valid_observation_days: `{summary['valid_observation_days']}/{summary['required_days']}`",
        f"- pass_days: `{summary['pass_days']}`",
        f"- pending_days: `{summary['pending_days']}`",
        f"- skipped_days: `{summary['skipped_days']}`",
        f"- consistency_matched_days: `{summary['consistency_matched_days']}`",
        f"- warning_days: `{summary['warning_days']}`",
        f"- halt_days: `{summary['halt_days']}`",
        f"- latest_record_date: `{summary['latest_record_date']}`",
        f"- last_valid_observation_date: `{summary['last_valid_observation_date']}`",
        f"- consecutive_clean_days: `{summary['consecutive_clean_days']}`",
        f"- ready_to_expand: `{summary['ready_to_expand']}`",
        f"- promotion_blockers: `{', '.join(summary['promotion_blockers']) or 'none'}`",
        "",
        "## Status Counts",
        "",
        "| status | days |",
        "|---|---:|",
    ]
    for status, count in summary["status_counts"].items():
        lines.append(f"| {status} | {count} |")
    lines.extend(["", "## Pending / Skipped / Risk Reasons", "", "| reason | days |", "|---|---:|"])
    if summary["reason_counts"]:
        for reason, count in summary["reason_counts"].items():
            lines.append(f"| {reason} | {count} |")
    else:
        lines.append("| none | 0 |")
    lines.extend(["", "## Action Summary", "", "| date | status | reason | severity | action | counts_for_20d |", "|---|---|---|---|---|---|"])
    for rec in build_action_summary(summary["records"]):
        lines.append(
            f"| {rec['date']} | {rec['status']} | {rec['reason']} | {rec['severity']} | {rec['action']} | {rec['counts_for_20d']} |"
        )
    lines.extend([
        "",
        "## Recent Records",
        "",
        "| date | valid | status | reason | consistency | threshold | order_safety | workflow_orders | raw_orders | raw_trades | subscription_missing | kline_missing | kline_short | gross | day_loss_abs | symbol_top1 | strategy_top1 |",
        "|---|---|---|---|---|---|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|",
    ])
    for row in summary["records"]:
        metrics = row.get("risk_metrics", {})
        safety = row.get("order_safety") or {}
        subscription_missing_symbols = row.get("subscription_coverage", {}).get("missing_symbols") or []
        missing_symbols = row.get("kline_coverage", {}).get("missing_symbols") or []
        short_symbols = row.get("kline_coverage", {}).get("short_symbols") or []
        subscription_missing = ",".join(str(x) for x in subscription_missing_symbols) if subscription_missing_symbols else ""
        kline_missing = ",".join(str(x) for x in missing_symbols) if missing_symbols else ""
        kline_short = ",".join(str(x) for x in short_symbols) if short_symbols else ""
        lines.append(
            f"| {row.get('date')} | {is_valid_observation(row)} | {row.get('status')} | {_record_reason(row)} | {row.get('consistency', {}).get('matched')} | "
            f"{row.get('thresholds', {}).get('status')} | {safety.get('status', '')} | {safety.get('orders_sent_by_workflow', 0)} | "
            f"{safety.get('observed_raw_orders', 0)} | {safety.get('observed_raw_trades', 0)} | {subscription_missing} | {kline_missing} | {kline_short} | {metrics.get('gross_exposure', 0):.2%} | "
            f"{metrics.get('single_day_loss_abs_pct', 0):.2f}% | {metrics.get('symbol_top1_abs_share', 0):.2%} | "
            f"{metrics.get('strategy_top1_abs_share', 0):.2%} |"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def _today() -> str:
    return date.today().isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain daily SimNow observation ledger for the final candidate.")
    parser.add_argument("--date", default=_today())
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    parser.add_argument("--simnow-json", type=Path)
    parser.add_argument("--replay-json", type=Path)
    parser.add_argument("--kline-json", type=Path)
    parser.add_argument("--risk-json", type=Path)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--record-json", type=Path)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--no-append", action="store_true")
    parser.add_argument("--min-days", type=int, default=20)
    args = parser.parse_args()

    baseline = load_json(args.baseline)
    thresholds = load_thresholds_config(args.thresholds) if args.thresholds and args.thresholds.exists() else None
    simnow = load_json(args.simnow_json) if args.simnow_json else None
    replay = load_json(args.replay_json) if args.replay_json else None
    kline = load_json(args.kline_json) if args.kline_json else None
    risk = load_json(args.risk_json) if args.risk_json else None
    record = make_record(args.date, baseline, simnow=simnow, replay=replay, kline=kline, risk=risk, thresholds=thresholds)
    if args.record_json:
        write_json(args.record_json, record)
    if not args.no_append:
        append_ledger(args.ledger, record)
    summary = build_20d_report(read_ledger(args.ledger), min_days=args.min_days)
    write_20d_markdown(summary, args.report_md)
    print(json.dumps({
        "record_status": record["status"],
        "threshold_status": record["thresholds"]["status"],
        "consistency_matched": record["consistency"].get("matched"),
        "observed_days": summary["observed_days"],
        "valid_observation_days": summary["valid_observation_days"],
        "pending_days": summary["pending_days"],
        "skipped_days": summary["skipped_days"],
        "last_valid_observation_date": summary["last_valid_observation_date"],
        "consecutive_clean_days": summary["consecutive_clean_days"],
        "ready_to_expand": summary["ready_to_expand"],
        "promotion_blockers": summary["promotion_blockers"],
        "ledger_write": "skipped" if args.no_append else "upsert",
        "ledger": str(args.ledger),
        "report": str(args.report_md),
    }, ensure_ascii=False, indent=2))
    if record["status"] == "halt":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
