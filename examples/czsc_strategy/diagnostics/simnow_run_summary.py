from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from simnow_action_summary import _record_reason
from simnow_artifact_loader import load_json_dict, load_jsonl_records
from simnow_automation_policy import (
    classify_automation_status,
    operator_explanation_cn,
    user_action_needed_reason_cn,
    needs_user_action,
)
from simnow_ledger_summary_schema import filter_safe_ledger_summary
from simnow_observation_window import load_observation_start_date
from simnow_promotion_decision import decide_promotion


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE
DEFAULT_LEDGER = HERE / "simnow_observation_ledger.jsonl"

SENSITIVE_KEY_PATTERNS = {"密码", "授权码", "auth_code", "password", "BrokerID", "username", "UserID"}
SENSITIVE_VALUE_FRAGMENTS = {"setting_masked"}

def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file if it exists; otherwise return an empty dict."""
    return load_json_dict(path)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file if it exists; otherwise return an empty list."""
    return load_jsonl_records(path)


def load_ledger_summary(path: Path) -> dict[str, Any]:
    """Load a ledger summary JSON if it exists; otherwise return an empty dict."""
    return load_json_dict(path)


def default_artifact_paths(date: str, out_dir: Path) -> dict[str, Path]:
    """Return the default artifact paths for a given observation date."""
    return {
        "capture_json": out_dir / f"simnow_export_{date}.json",
        "kline_json": out_dir / f"simnow_kline_update_{date}.json",
        "replay_json": out_dir / f"simnow_replay_{date}.json",
        "replay_readiness_json": out_dir / f"simnow_replay_readiness_{date}.json",
        "historical_db_update_json": out_dir / f"simnow_historical_db_update_{date}.json",
        "record_json": out_dir / f"simnow_record_{date}.json",
        "observation_report_md": out_dir / f"simnow_report_{date}.md",
        "promotion_report_md": out_dir / "simnow_20d_promotion_decision.md",
    }


def extract_capture_summary(capture: dict[str, Any]) -> dict[str, Any]:
    """Summarize the SimNow capture JSON without exposing raw private fields."""
    raw = capture.get("raw") or {}
    subscribed = raw.get("subscribed") or []
    return {
        "ticks": len(raw.get("ticks") or []),
        "contracts_count": int(raw.get("contracts_count", 0) or 0),
        "accounts": len(raw.get("accounts") or []),
        "positions": len(raw.get("positions") or []),
        "orders": len(raw.get("orders") or []),
        "trades": len(raw.get("trades") or []),
        "subscribed_count": len(subscribed),
    }


def extract_contract_map_provenance(capture: dict[str, Any]) -> dict[str, Any]:
    """Summarize which formal contract-map snapshot produced this capture."""
    meta = capture.get("meta") or {}
    provenance = meta.get("contract_map_provenance")
    if isinstance(provenance, dict):
        return {
            "path": str(provenance.get("path") or ""),
            "version": str(provenance.get("version") or ""),
            "effective_date": str(provenance.get("effective_date") or ""),
            "note": str(provenance.get("note") or ""),
            "enabled_symbols": list(provenance.get("enabled_symbols") or []),
            "enabled_count": int(provenance.get("enabled_count", 0) or 0),
        }

    contract_map = meta.get("contract_map") or {}
    enabled_symbols = sorted(
        str(symbol).upper()
        for symbol, row in contract_map.items()
        if not str(symbol).startswith("_") and isinstance(row, dict) and row.get("enabled", True)
    )
    return {
        "path": str(meta.get("contract_map_path") or ""),
        "version": "",
        "effective_date": "",
        "note": "",
        "enabled_symbols": enabled_symbols,
        "enabled_count": len(enabled_symbols),
    }


def extract_environment_capture(capture: dict[str, Any]) -> dict[str, Any]:
    """Summarize the read-only SimNow environment checks."""
    raw = capture.get("raw") or {}
    meta = capture.get("meta") or {}
    subscribed = raw.get("subscribed") or []
    tick_counts_by_symbol: dict[str, int] = {}
    symbol_lookup: dict[tuple[str, str], str] = {}
    vt_lookup: dict[str, str] = {}
    symbol_only_lookup: dict[str, str] = {}
    for row in subscribed:
        research_symbol = str(row.get("research_symbol") or "").upper()
        if not research_symbol:
            continue
        tick_counts_by_symbol[research_symbol] = 0
        symbol = str(row.get("symbol") or "").lower()
        exchange = str(row.get("exchange") or "").upper()
        vt_symbol = str(row.get("vt_symbol") or "")
        if symbol and exchange:
            symbol_lookup[(symbol, exchange)] = research_symbol
        if symbol and symbol not in symbol_only_lookup:
            symbol_only_lookup[symbol] = research_symbol
        if vt_symbol:
            vt_lookup[vt_symbol] = research_symbol
    for tick in raw.get("ticks") or []:
        vt_symbol = str(tick.get("vt_symbol") or "")
        symbol = str(tick.get("symbol") or "").lower()
        exchange = str(tick.get("exchange") or "").upper()
        research_symbol = (
            vt_lookup.get(vt_symbol)
            or symbol_lookup.get((symbol, exchange))
            or symbol_only_lookup.get(symbol)
            or (str(tick.get("symbol") or "").upper() if str(tick.get("symbol") or "").upper() in tick_counts_by_symbol else "")
        )
        if research_symbol:
            tick_counts_by_symbol[research_symbol] = tick_counts_by_symbol.get(research_symbol, 0) + 1
    zero_tick_subscribed_symbols = sorted(
        symbol for symbol, count in tick_counts_by_symbol.items()
        if count == 0
    )
    return {
        "ticks": len(raw.get("ticks") or []),
        "contracts_count": int(raw.get("contracts_count", 0) or 0),
        "accounts": len(raw.get("accounts") or []),
        "subscribed_count": len(subscribed),
        "read_only": meta.get("read_only") is True,
        "orders_sent_by_workflow": int(meta.get("orders_sent_by_workflow", 0) or 0),
        "tick_counts_by_symbol": tick_counts_by_symbol,
        "zero_tick_subscribed_symbols": zero_tick_subscribed_symbols,
    }


def extract_account_contamination(capture: dict[str, Any]) -> dict[str, Any]:
    """Report external SimNow account activity without treating it as strategy PnL."""
    raw = capture.get("raw") or {}
    orders = raw.get("orders") or []
    trades = raw.get("trades") or []
    positions = raw.get("positions") or []
    active_positions = [
        row for row in positions
        if abs(float((row or {}).get("volume", 0.0) or 0.0)) > 0
    ]
    position_symbols = sorted({
        str(row.get("symbol") or "")
        for row in active_positions
        if row.get("symbol")
    })
    return {
        "detected": bool(orders or trades or active_positions),
        "orders": len(orders),
        "trades": len(trades),
        "active_positions": len(active_positions),
        "position_symbols": position_symbols,
        "note": "SimNow account activity is external audit evidence only; it is not strategy PnL.",
    }


def extract_kline_summary(kline: dict[str, Any]) -> dict[str, Any]:
    """Summarize the kline update JSON."""
    return {
        "missing_symbols": list(kline.get("missing_symbols") or []),
        "short_symbols": list(kline.get("short_symbols") or []),
        "min_bars_per_symbol": kline.get("min_bars_per_symbol"),
    }


def extract_historical_db_update_summary(update: dict[str, Any]) -> dict[str, Any]:
    """Summarize the optional pre-observation historical DB update step."""
    if not update:
        return {
            "status": "skipped",
            "exit_code": None,
            "command": "",
            "started_at": "",
            "ended_at": "",
        }
    return {
        "status": str(update.get("status") or "unknown"),
        "exit_code": update.get("exit_code"),
        "command": str(update.get("command") or ""),
        "started_at": str(update.get("started_at") or ""),
        "ended_at": str(update.get("ended_at") or ""),
    }


def extract_formal_readiness(
    capture: dict[str, Any],
    kline: dict[str, Any],
    historical_db_update: dict[str, Any],
    replay: dict[str, Any],
    replay_readiness: dict[str, Any],
) -> dict[str, Any]:
    """Summarize whether formal-observation prerequisites were satisfied."""
    meta = capture.get("meta") or {}
    strategy_surface = meta.get("strategy_surface") or {}
    replay_meta = replay.get("meta") or {}

    historical_status = str(historical_db_update.get("status") or "skipped")
    historical_ready = historical_status == "passed"

    if replay_readiness:
        replay_ready = bool(replay_readiness.get("ready"))
        replay_latest_db_date = str(replay_readiness.get("latest_db_date") or "")
        replay_missing_or_lagged_symbols = list(replay_readiness.get("missing_or_lagged_symbols") or [])
    else:
        replay_ready = bool(replay_meta.get("replay_available"))
        replay_latest_db_date = str(replay_meta.get("latest_db_date") or "")
        replay_missing_or_lagged_symbols = list(replay_meta.get("missing_or_lagged_symbols") or [])

    kline_missing_symbols = list(kline.get("missing_symbols") or [])
    kline_short_symbols = list(kline.get("short_symbols") or [])
    kline_ready = not kline_missing_symbols and not kline_short_symbols

    blocking_reasons: list[str] = []
    if not historical_ready:
        blocking_reasons.append("historical_db_update_not_passed")
    if not replay_ready:
        blocking_reasons.append("replay_db_not_ready")
    if kline_missing_symbols:
        blocking_reasons.append("kline_missing_symbols")
    if kline_short_symbols:
        blocking_reasons.append("kline_short_symbols")

    return {
        "capture_started_at": str(meta.get("started_at") or ""),
        "capture_ended_at": str(meta.get("ended_at") or ""),
        "capture_duration_seconds": int(meta.get("duration_seconds", 0) or 0),
        "strategy_window_start": str(strategy_surface.get("window_start") or ""),
        "strategy_window_end": str(strategy_surface.get("window_end") or ""),
        "read_only_declared": meta.get("read_only") is True,
        "historical_db_update_status": historical_status,
        "historical_db_ready": historical_ready,
        "replay_db_ready": replay_ready,
        "replay_latest_db_date": replay_latest_db_date,
        "replay_missing_or_lagged_symbols": replay_missing_or_lagged_symbols,
        "kline_coverage_ready": kline_ready,
        "kline_missing_symbols": kline_missing_symbols,
        "kline_short_symbols": kline_short_symbols,
        "min_bars_per_symbol": kline.get("min_bars_per_symbol"),
        "overall_ready": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
    }


def _resolve_environment_observation(record: dict[str, Any], kline: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve environment-observation validity, with fallback for legacy records."""
    if "environment_observation_valid" in record or "environment_observation_reason" in record:
        return {
            "valid": bool(record.get("environment_observation_valid")),
            "reason": str(record.get("environment_observation_reason") or ""),
        }

    consistency = record.get("consistency") or {}
    safety = record.get("order_safety") or {}
    subscription = record.get("subscription_coverage") or {}
    kline = kline or record.get("kline_coverage") or {}
    skip_reason = str(record.get("skip_reason") or "")

    if skip_reason:
        return {"valid": False, "reason": skip_reason}
    if safety.get("status") != "pass":
        return {"valid": False, "reason": "order_safety_not_pass"}
    if subscription.get("missing_symbols"):
        return {"valid": False, "reason": "subscription_missing_symbols"}
    if kline.get("missing_symbols"):
        return {"valid": False, "reason": "kline_missing_symbols"}
    if kline.get("short_symbols"):
        return {"valid": False, "reason": "kline_short_symbols"}
    if consistency.get("matched") is not True:
        return {"valid": False, "reason": str(consistency.get("reason") or "consistency_not_matched")}
    return {"valid": True, "reason": ""}


def extract_record_summary(record: dict[str, Any], kline: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize the daily monitor record JSON."""
    threshold_rows = []
    for row in (record.get("thresholds", {}).get("rows") or []):
        normalized_row = {
            "metric": row.get("metric", ""),
            "value": row.get("value"),
            "level": row.get("level", ""),
            "unit": row.get("unit", ""),
        }
        for key in ("warning", "halt", "baseline"):
            if key in row and row.get(key) is not None:
                normalized_row[key] = row.get(key)
        threshold_rows.append(normalized_row)
    environment = _resolve_environment_observation(record, kline)
    halt = record.get("halt") or {}
    return {
        "status": record.get("status", ""),
        "valid_observation": bool(record.get("valid_observation")),
        "environment_observation_valid": environment["valid"],
        "environment_observation_reason": environment["reason"],
        "reason": _record_reason(record),
        "threshold_status": record.get("thresholds", {}).get("status", ""),
        "order_safety_status": record.get("order_safety", {}).get("status", ""),
        "consistency_matched": bool(record.get("consistency", {}).get("matched")),
        "threshold_rows": threshold_rows,
        "threshold_diagnostics": build_threshold_diagnostics(threshold_rows),
        "halt_rule_id": str(halt.get("rule_id") or ""),
        "halt_family": str(halt.get("family") or ""),
        "halt_severity": str(halt.get("severity") or ""),
        "halt_trigger_metrics": list(halt.get("trigger_metrics") or []),
        "halt_explained_cn": str(halt.get("explained_cn") or ""),
    }


def build_threshold_diagnostics(threshold_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Surface threshold gaps for warning/halt rows to aid manual risk review."""
    diagnostics: list[dict[str, Any]] = []
    for row in threshold_rows:
        level = str(row.get("level") or "")
        if level not in {"warning", "halt"}:
            continue
        value = float(row.get("value", 0.0) or 0.0)
        warning = float(row.get("warning", 0.0) or 0.0)
        halt = float(row.get("halt", 0.0) or 0.0)
        baseline = float(row.get("baseline", 0.0) or 0.0)
        warning_gap = value - warning
        halt_gap = value - halt
        warning_gap_pct_of_halt = 0.0
        if halt:
            warning_gap_pct_of_halt = warning_gap / halt
        diagnostics.append({
            "metric": str(row.get("metric") or ""),
            "level": level,
            "value": value,
            "warning": warning,
            "halt": halt,
            "baseline": baseline,
            "unit": str(row.get("unit") or ""),
            "warning_gap": warning_gap,
            "halt_gap": halt_gap,
            "warning_gap_pct_of_halt": warning_gap_pct_of_halt,
        })
    return diagnostics


def extract_environment_observation_summary(record: dict[str, Any], kline: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize whether the read-only environment observation itself succeeded."""
    environment = _resolve_environment_observation(record, kline)
    return {
        "valid": environment["valid"],
        "reason": environment["reason"],
        "counts_for_20d": bool(record.get("valid_observation")),
    }


def extract_delayed_replay_summary(replay: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Summarize the strategy-only delayed replay/virtual ledger result."""
    meta = replay.get("meta") or {}
    consistency = record.get("consistency") or {}
    return {
        "available": bool(meta.get("replay_available")),
        "status": record.get("status", ""),
        "valid_observation": bool(record.get("valid_observation")),
        "reason": str(consistency.get("reason") or record.get("skip_reason") or ""),
        "latest_db_date": str(meta.get("latest_db_date") or ""),
        "missing_or_lagged_symbols": list(meta.get("missing_or_lagged_symbols") or []),
        "signals": len(replay.get("signals") or []),
        "trades": len(replay.get("trades") or []),
        "positions": len(replay.get("positions") or []),
        "risk_source": "replay_only",
    }


def extract_risk_source_breakdown(replay: dict[str, Any]) -> dict[str, Any]:
    """Expose compact replay risk source details needed for manual review."""
    risk = replay.get("risk") or {}
    consecutive = risk.get("consecutive_loss") or risk.get("max_consecutive_loss") or {}
    rows = [
        {
            "date": str(row.get("date") or ""),
            "daily_return_pct": float(row.get("daily_return_pct", 0.0) or 0.0),
            "equity": float(row.get("equity", 0.0) or 0.0),
        }
        for row in consecutive.get("rows") or []
    ]
    days = int(consecutive.get("days", 0) or 0)
    cumulative_return_pct = float(consecutive.get("cumulative_return_pct", 0.0) or 0.0)
    available = bool(days or rows)
    rows_available = bool(rows)
    complete = bool(available and (days == 0 or len(rows) == days))
    reason = ""
    if available and not rows_available:
        reason = "missing_consecutive_loss_rows"
    elif available and not complete:
        reason = "incomplete_consecutive_loss_rows"
    return {
        "consecutive_loss": {
            "available": available,
            "complete": complete,
            "rows_available": rows_available,
            "reason": reason,
            "source": "delayed_replay.risk.consecutive_loss",
            "days": days,
            "cumulative_return_pct": cumulative_return_pct,
            "abs_cumulative_return_pct": abs(cumulative_return_pct),
            "start_date": str(consecutive.get("start_date") or ""),
            "end_date": str(consecutive.get("end_date") or ""),
            "rows": rows,
        }
    }


def build_run_summary(
    date: str,
    files: dict[str, Path],
    promotion_summary: dict[str, Any] | None = None,
    ledger_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a machine-readable run summary from existing daily artifacts.

    The summary only exposes aggregate counts and known gate results. It never
    includes raw tick payloads, contract maps, account IDs, passwords, or the
    full masked setting object.
    """
    capture = load_json(files.get("capture_json"))
    kline = load_json(files.get("kline_json"))
    historical_db_update = load_json(files.get("historical_db_update_json"))
    replay = load_json(files.get("replay_json"))
    replay_readiness = load_json(files.get("replay_readiness_json"))
    record = load_json(files.get("record_json"))
    promotion = promotion_summary or {}

    if ledger_summary:
        ledger_section: dict[str, Any] = filter_safe_ledger_summary(ledger_summary)
    else:
        ledger_section = {"available": False, "reason": "missing_ledger_summary"}

    core = {
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": {name: str(path) for name, path in files.items()},
        "capture": extract_capture_summary(capture),
        "contract_map_provenance": extract_contract_map_provenance(capture),
        "environment_capture": extract_environment_capture(capture),
        "account_contamination": extract_account_contamination(capture),
        "historical_db_update": extract_historical_db_update_summary(historical_db_update),
        "formal_readiness": extract_formal_readiness(
            capture,
            kline,
            historical_db_update,
            replay,
            replay_readiness,
        ),
        "kline": extract_kline_summary(kline),
        "record": extract_record_summary(record, kline),
        "environment_observation": extract_environment_observation_summary(record, kline),
        "delayed_replay": extract_delayed_replay_summary(replay, record),
        "risk_source_breakdown": extract_risk_source_breakdown(replay),
        "promotion": {
            "ready_to_expand": bool(promotion.get("ready_to_expand")),
            "valid_observation_days": int(promotion.get("valid_observation_days", 0)),
            "observed_days": int(promotion.get("observed_days", 0)),
            "observation_start_date": promotion.get("observation_start_date", ""),
            "excluded_before_start_count": int(promotion.get("excluded_before_start_count", 0)),
            "promotion_blockers": list(promotion.get("promotion_blockers") or []),
            "blocking_action_counts": dict(promotion.get("blocking_action_counts") or {}),
            "top_blocking_actions": list(promotion.get("top_blocking_actions") or []),
        },
        "ledger_summary": ledger_section,
    }
    automation = classify_automation_status(core)
    summary = {**automation, **core}
    summary["operator_explanation_cn"] = operator_explanation_cn(summary)
    summary["user_action_needed"] = needs_user_action(summary)
    summary["user_action_needed_reason_cn"] = user_action_needed_reason_cn(summary)

    sensitive = contains_sensitive_data(summary)
    if sensitive:
        raise RuntimeError(f"run summary contains sensitive data: {sensitive}")

    return summary


def _iter_summary_nodes(obj: Any, path: str = "") -> Any:
    """Yield (path, key_or_none, value) tuples for every scalar in the summary."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _iter_summary_nodes(value, f"{path}.{key}" if path else str(key))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _iter_summary_nodes(value, f"{path}[{index}]")
    else:
        yield path, obj


def contains_sensitive_data(summary: dict[str, Any]) -> list[str]:
    """Return a list of paths where sensitive data may have leaked into the summary."""
    findings: list[str] = []
    for path, value in _iter_summary_nodes(summary):
        # path ends with the key for dict scalars
        last_key = path.split(".")[-1] if "." in path else path
        if any(pattern.lower() in last_key.lower() for pattern in SENSITIVE_KEY_PATTERNS):
            findings.append(f"sensitive key at {path}")
        if isinstance(value, str):
            lower_value = value.lower()
            for fragment in SENSITIVE_VALUE_FRAGMENTS:
                if fragment.lower() in lower_value:
                    findings.append(f"sensitive value at {path}")
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate SimNow daily run artifacts into a machine-readable summary JSON."
    )
    parser.add_argument("--date", required=True, help="Observation date (YYYY-MM-DD).")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Directory containing artifact files.")
    parser.add_argument("--out-json", type=Path, help="Path to write the summary JSON.")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER, help="Formal observation ledger.")
    parser.add_argument("--ledger-summary", type=Path, help="Path to simnow_ledger_summary.json.")
    parser.add_argument("--historical-db-update", type=Path, help="Path to simnow_historical_db_update_YYYY-MM-DD.json.")
    args = parser.parse_args()

    files = default_artifact_paths(args.date, args.out_dir)
    if args.historical_db_update:
        files["historical_db_update_json"] = args.historical_db_update
    ledger_records = load_jsonl(args.ledger)
    start_date = load_observation_start_date()
    promotion_summary = decide_promotion(ledger_records, observation_start_date=start_date)
    ledger_summary_path = args.ledger_summary or (args.out_dir / "simnow_ledger_summary.json")
    ledger_summary = load_ledger_summary(ledger_summary_path)
    summary = build_run_summary(
        args.date, files, promotion_summary=promotion_summary, ledger_summary=ledger_summary
    )

    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
