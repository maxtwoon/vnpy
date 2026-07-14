from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from declassify_historical_reports import build_banner
from simnow_action_summary import _record_reason, build_action_summary
from simnow_monitor_config import SIMNOW_MONITOR_CONFIG
from simnow_observation_rules import is_valid_observation, valid_observation_reason
from simnow_observation_window import filter_records_by_start, load_observation_start_date
from simnow_strategy_surface import filter_events_to_window


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


def _is_zero_placeholder_risk(risk: dict[str, Any]) -> bool:
    """Return True when ``risk`` matches build_risk()'s known placeholder shape.

    The live capture cannot compute genuine daily return, drawdown, exposure,
    or concentration without portfolio-level context, so build_risk() hardcodes
    these fields to zero. This function detects that specific placeholder so
    downstream code never mistakes it for a real zero-risk measurement.
    """
    if not risk:
        return True
    consecutive = risk.get("consecutive_loss") or {}
    symbol_conc = risk.get("symbol_concentration") or {}
    strategy_conc = risk.get("strategy_concentration") or {}
    checks = [
        risk.get("daily_return_pct") in (0, 0.0, None),
        risk.get("drawdown_pct") in (0, 0.0, None),
        risk.get("gross_exposure") in (0, 0.0, None),
        risk.get("net_exposure") in (0, 0.0, None),
        risk.get("both_long_short_symbols") in (0, 0.0, None),
        consecutive.get("days") in (0, 0.0, None),
        consecutive.get("cumulative_return_pct") in (0, 0.0, None),
        symbol_conc.get("top1_abs_share") in (0, 0.0, None),
        strategy_conc.get("top1_abs_share") in (0, 0.0, None),
    ]
    return all(checks)


def select_risk_metrics(
    risk: dict[str, Any] | None,
    simnow: dict[str, Any],
    replay: dict[str, Any],
    mode: str = "replay_first",
) -> tuple[dict[str, Any], str]:
    """Return (raw_risk_dict, risk_source_label).

    Never silently prefers a known-placeholder simnow.risk block over a real
    replay-computed one. ``mode`` is read from ``SIMNOW_MONITOR_CONFIG``.
    """
    if risk is not None:
        return risk, "explicit_risk_json"
    simnow_risk = simnow.get("risk") or {}
    replay_risk = replay.get("risk") or {}
    simnow_is_placeholder = _is_zero_placeholder_risk(simnow_risk)
    if mode == "legacy_simnow_first":
        chosen = simnow_risk or replay_risk or {}
        if simnow_risk and simnow_is_placeholder:
            return chosen, "simnow_capture_placeholder"
        if simnow_risk:
            return chosen, "simnow_capture"
        if replay_risk:
            return chosen, "replay_computed"
        return chosen, "no_risk_available"
    # mode == "replay_first" (new default): prefer replay-computed risk
    # whenever simnow's own risk block is the known placeholder shape; a
    # genuinely non-placeholder simnow.risk (future capture format upgrade)
    # still wins over replay, since a real live measurement is more authoritative
    # than a replay approximation.
    if simnow_risk and not simnow_is_placeholder:
        return simnow_risk, "simnow_capture"
    if replay_risk:
        return replay_risk, "replay_computed"
    if simnow_risk:
        return simnow_risk, "simnow_capture_placeholder"
    return {}, "no_risk_available"


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


def evaluate_thresholds(
    metrics: dict[str, float],
    thresholds: dict[str, Threshold],
    risk_source: str = "",
) -> dict[str, Any]:
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
    # A known-placeholder risk block must never produce an authoritative "pass"
    # on its own. Downgrade to "unproven" so make_record treats it as pending.
    if risk_source == "simnow_capture_placeholder":
        status = "unproven"
    return {"status": status, "rows": rows, "risk_source": risk_source}


def _event_key(event: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(event.get("dt") or event.get("datetime") or event.get("time") or ""),
        str(event.get("symbol") or ""),
        str(event.get("strategy") or event.get("position") or ""),
        str(event.get("operate") or event.get("action") or ""),
    )


def _has_any_events(payload: dict[str, Any]) -> bool:
    """Return True if the payload has at least one signal/trade/position event."""
    return bool(payload.get("signals") or payload.get("trades") or payload.get("positions"))


def _empty_matched_details(simnow: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    """Return a details dict reporting all categories as trivially matched."""
    details: dict[str, Any] = {}
    for category in ["signals", "trades", "positions"]:
        simnow_count = len(simnow.get(category, []))
        replay_count = len(replay.get(category, []))
        details[category] = {
            "matched": True,
            "simnow_count": simnow_count,
            "replay_count": replay_count,
            "missing_in_simnow": [],
            "extra_in_simnow": [],
        }
    return details


def _windowed_replay(simnow: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    """Filter replay events to the live-capture comparison window when provided."""
    surface_meta = simnow.get("meta", {}).get("strategy_surface") or {}
    window_start = surface_meta.get("window_start")
    window_end = surface_meta.get("window_end")
    if not window_start or not window_end:
        return replay

    replay_copy = dict(replay)
    for category in ("signals", "trades", "positions"):
        replay_copy[category] = filter_events_to_window(list(replay.get(category) or []), window_start, window_end)
    meta = dict(replay_copy.get("meta") or {})
    meta["comparison_window_start"] = window_start
    meta["comparison_window_end"] = window_end
    replay_copy["meta"] = meta
    return replay_copy


def compare_simnow_replay(
    simnow: dict[str, Any],
    replay: dict[str, Any],
    *,
    source: str | None = None,
    consistency_source_mode: str = "replay_derived_allowed",
) -> dict[str, Any]:
    """Compare exported SimNow events with replay events on signal/trade/position surfaces.

    ``source`` is the strategy surface source (``captured_session`` for real
    captured CTP callbacks, ``windowed_strategy_replay`` for replay-derived).
    Under ``consistency_source_mode="require_captured"`` (the safe default),
    only ``captured_session`` surfaces may produce a ``matched`` verdict;
    replay-derived surfaces report ``status="unavailable"`` instead.
    """
    if source is None:
        source = simnow.get("meta", {}).get("strategy_surface", {}).get("source") or "windowed_strategy_replay"
    verified = consistency_source_mode == "require_captured" and source == "captured_session"
    if consistency_source_mode == "require_captured" and source != "captured_session":
        return {
            "status": "unavailable",
            "reason": "no_captured_session_data_only_replay_derived",
            "details": {},
            "verified": False,
        }
    replay = _windowed_replay(simnow, replay)
    replay_meta = replay.get("meta") or {}
    if replay_meta.get("replay_available") is False:
        reason = replay_meta.get("replay_unavailable_reason") or "replay_unavailable"
        # A day where both the live capture and the replay produced no
        # actionable events is considered consistent: the strategy simply did
        # not trade. This avoids penalising no-activity days while still
        # flagging days where one side has trades and the other does not.
        if reason == "no_replay_events_for_day" and not _has_any_events(simnow):
            return {
                "matched": True,
                "details": _empty_matched_details(simnow, replay),
                "reason": "no_actionable_events_on_either_side",
                "verified": verified,
            }
        return {
            "matched": False,
            "details": {},
            "reason": reason,
            "verified": verified,
        }
    # If the live capture recorded no events and the replay has no trades,
    # there is nothing actionable to compare. Position/signal snapshots are
    # informational only on a no-trade day.
    if not replay.get("trades") and not _has_any_events(simnow):
        return {
            "matched": True,
            "details": _empty_matched_details(simnow, replay),
            "reason": "no_actionable_events_on_either_side",
            "verified": verified,
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
    reason = "" if all_match else "event_surface_mismatch"
    return {"matched": all_match, "details": details, "reason": reason, "verified": verified}


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


def _is_legacy_read_only_capture(meta: dict[str, Any]) -> bool:
    """Return True only for pre-order-safety artifacts that had no order fields."""
    return (
        "read_only" not in meta
        and "orders_sent_by_workflow" not in meta
        and "workflow_order_actions" not in meta
        and "started_at" in meta
        and "ended_at" in meta
    )


def order_safety(simnow: dict[str, Any]) -> dict[str, Any]:
    """Verify the observation workflow stayed read-only.

    Raw account orders/trades are audit evidence only. They may include manual,
    historical, or broker-side callbacks, so the hard gate is whether this
    workflow declared read-only mode and recorded zero order actions of its own.
    """
    meta = simnow.get("meta") or {}
    raw = simnow.get("raw") or {}
    legacy_inferred = _is_legacy_read_only_capture(meta)
    read_only = meta.get("read_only")
    if legacy_inferred:
        read_only = True
    orders_sent = int(meta.get("orders_sent_by_workflow", 0) or 0)
    actions = meta.get("workflow_order_actions") or []
    status = "pass" if read_only is True else "unknown"
    reasons = []
    if read_only is False:
        status = "halt"
        reasons.append("read_only_disabled")
    elif read_only is None and not legacy_inferred:
        reasons.append("read_only_not_declared")
    if orders_sent != 0 or actions:
        status = "halt"
        reasons.append("workflow_order_actions_present")
    return {
        "status": status,
        "read_only": read_only is True,
        "orders_sent_by_workflow": orders_sent,
        "workflow_order_actions": actions,
        "legacy_inferred": legacy_inferred,
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
    monitor_config: dict[str, str] | None = None,
) -> dict[str, Any]:
    simnow = simnow or {}
    replay = replay or {}
    kline = kline or {}
    monitor_config = monitor_config or dict(SIMNOW_MONITOR_CONFIG)
    thresholds = thresholds or build_thresholds(baseline_payload)
    metrics, risk_source = select_risk_metrics(
        risk,
        simnow,
        replay,
        mode=monitor_config.get("risk_priority", "replay_first"),
    )
    metrics = normalize_daily_metrics(metrics)
    threshold_result = evaluate_thresholds(metrics, thresholds, risk_source=risk_source)
    skip_reason = _capture_skip_reason(simnow) if simnow else ""
    subscription = subscription_coverage(simnow) if simnow else {}
    safety = order_safety(simnow) if simnow else {}
    surface_source = simnow.get("meta", {}).get("strategy_surface", {}).get("source")
    if skip_reason:
        consistency = {
            "matched": False,
            "details": {},
            "reason": skip_reason,
        }
    else:
        consistency = compare_simnow_replay(
            simnow,
            replay,
            source=surface_source,
            consistency_source_mode=monitor_config.get("consistency_source_mode", "require_captured"),
        ) if simnow and replay else {
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
        "risk_source": risk_source,
        "thresholds": threshold_result,
        "consistency": consistency,
    }
    record["attribution_watch"] = attribution_watch(record)
    record["skip_reason"] = skip_reason
    if skip_reason:
        record["status"] = "skipped"
    elif threshold_result["status"] == "halt" or safety.get("status") == "halt":
        record["status"] = "halt"
    elif threshold_result["status"] == "unproven" or consistency.get("status") == "unavailable":
        # Core discipline: never silently default to "pass". A diagnostic that
        # cannot verify something must report pending/unproven/unavailable.
        record["status"] = "pending"
    else:
        record["status"] = "pass" if consistency.get("matched") else "pending"
    record["valid_observation"] = is_valid_observation(record)
    record["valid_observation_reason"] = valid_observation_reason(record) or ""
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


def build_20d_report(
    records: list[dict[str, Any]],
    min_days: int = 20,
    observation_start_date: str | None = None,
) -> dict[str, Any]:
    all_records = sorted(records, key=lambda x: str(x.get("date", "")))
    ordered = sorted(filter_records_by_start(all_records, observation_start_date), key=lambda x: str(x.get("date", "")))
    excluded_before_start_count = len(all_records) - len(ordered)
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
        "observation_start_date": observation_start_date or "",
        "excluded_before_start_count": excluded_before_start_count,
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


RESEARCH_ONLY_BANNER = "Diagnostic only, not a trading recommendation."


def write_20d_markdown(summary: dict[str, Any], out: Path) -> None:
    lines = [
        "# SimNow 20-Day Observation Report",
        "",
        build_banner().rstrip("\n"),
        "",
        f"> {RESEARCH_ONLY_BANNER}",
        "",
        f"- observation_start_date: `{summary.get('observation_start_date', '')}`",
        f"- excluded_before_start_count: `{summary.get('excluded_before_start_count', 0)}`",
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
    parser.add_argument(
        "--observation-start-date",
        default=None,
        help="Only count ledger rows on or after this date. Defaults to simnow_observation_window.json.",
    )
    parser.add_argument(
        "--risk-priority",
        choices=["replay_first", "legacy_simnow_first"],
        default=SIMNOW_MONITOR_CONFIG["risk_priority"],
        help="Risk source priority (default: replay_first).",
    )
    parser.add_argument(
        "--consistency-source-mode",
        choices=["require_captured", "replay_derived_allowed"],
        default=SIMNOW_MONITOR_CONFIG["consistency_source_mode"],
        help="Consistency surface source mode (default: require_captured).",
    )
    args = parser.parse_args()

    monitor_config = dict(SIMNOW_MONITOR_CONFIG)
    monitor_config["risk_priority"] = args.risk_priority
    monitor_config["consistency_source_mode"] = args.consistency_source_mode

    baseline = load_json(args.baseline)
    thresholds = load_thresholds_config(args.thresholds) if args.thresholds and args.thresholds.exists() else None
    simnow = load_json(args.simnow_json) if args.simnow_json else None
    replay = load_json(args.replay_json) if args.replay_json else None
    kline = load_json(args.kline_json) if args.kline_json else None
    risk = load_json(args.risk_json) if args.risk_json else None
    record = make_record(
        args.date,
        baseline,
        simnow=simnow,
        replay=replay,
        kline=kline,
        risk=risk,
        thresholds=thresholds,
        monitor_config=monitor_config,
    )
    if args.record_json:
        write_json(args.record_json, record)
    if not args.no_append:
        append_ledger(args.ledger, record)
    start_date = args.observation_start_date
    if start_date is None:
        start_date = load_observation_start_date()
    summary = build_20d_report(read_ledger(args.ledger), min_days=args.min_days, observation_start_date=start_date)
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
