from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from simnow_action_summary import _record_reason
from simnow_observation_window import load_observation_start_date
from simnow_promotion_decision import decide_promotion


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE
DEFAULT_LEDGER = HERE / "simnow_observation_ledger.jsonl"

SENSITIVE_KEY_PATTERNS = {"密码", "授权码", "auth_code", "password", "BrokerID", "username", "UserID"}
SENSITIVE_VALUE_FRAGMENTS = {"setting_masked"}

SAFE_LEDGER_SUMMARY_FIELDS = {
    "generated_at",
    "min_days",
    "observation_start_date",
    "excluded_before_start_count",
    "total_rows",
    "valid_observation_days",
    "pending_days",
    "skipped_days",
    "halt_days",
    "failed_days",
    "latest_date",
    "latest_valid_date",
    "consecutive_valid_days",
    "ready_to_expand",
    "promotion_blockers",
    "reason_counts",
    "automation_status_counts",
    "latest_action",
    "next_action",
}


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file if it exists; otherwise return an empty dict."""
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file if it exists; otherwise return an empty list."""
    if not path or not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_ledger_summary(path: Path) -> dict[str, Any]:
    """Load a ledger summary JSON if it exists; otherwise return an empty dict."""
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def default_artifact_paths(date: str, out_dir: Path) -> dict[str, Path]:
    """Return the default artifact paths for a given observation date."""
    return {
        "capture_json": out_dir / f"simnow_export_{date}.json",
        "kline_json": out_dir / f"simnow_kline_update_{date}.json",
        "replay_json": out_dir / f"simnow_replay_{date}.json",
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


def extract_record_summary(record: dict[str, Any]) -> dict[str, Any]:
    """Summarize the daily monitor record JSON."""
    threshold_rows = []
    for row in (record.get("thresholds", {}).get("rows") or []):
        threshold_rows.append({
            "metric": row.get("metric", ""),
            "value": row.get("value"),
            "level": row.get("level", ""),
            "unit": row.get("unit", ""),
        })
    return {
        "status": record.get("status", ""),
        "valid_observation": bool(record.get("valid_observation")),
        "reason": _record_reason(record),
        "threshold_status": record.get("thresholds", {}).get("status", ""),
        "order_safety_status": record.get("order_safety", {}).get("status", ""),
        "consistency_matched": bool(record.get("consistency", {}).get("matched")),
        "threshold_rows": threshold_rows,
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


def classify_automation_status(summary: dict[str, Any]) -> dict[str, Any]:
    """Derive the external automation status from a run summary.

    Returns a dict with:
      - automation_status: valid | skipped | pending | halt | failed
      - automation_exit_code: 0 | 10 | 20 | 30 | 40
      - automation_reason: the underlying record reason, if available
      - automation_action: a short English recommendation for the automation platform
    """
    record = summary.get("record") or {}
    status = str(record.get("status") or "")
    reason = str(record.get("reason") or "")
    valid = bool(record.get("valid_observation"))

    if status == "pass" and valid:
        return {
            "automation_status": "valid",
            "automation_exit_code": 0,
            "automation_reason": reason,
            "automation_action": "counts_for_20d",
        }
    if status == "skipped":
        return {
            "automation_status": "skipped",
            "automation_exit_code": 10,
            "automation_reason": reason,
            "automation_action": "no valid market data / rerun next valid session",
        }
    if status == "pending":
        return {
            "automation_status": "pending",
            "automation_exit_code": 20,
            "automation_reason": reason,
            "automation_action": "resolve pending gate before counting",
        }
    if status == "halt":
        return {
            "automation_status": "halt",
            "automation_exit_code": 30,
            "automation_reason": reason,
            "automation_action": "stop automation and review manually",
        }
    return {
        "automation_status": "failed",
        "automation_exit_code": 40,
        "automation_reason": reason or "missing critical artifact or unknown status",
        "automation_action": "missing critical artifact or unknown status",
    }


def _safe_ledger_summary(ledger_summary: dict[str, Any]) -> dict[str, Any]:
    """Return only the safe aggregate fields from a ledger summary."""
    safe: dict[str, Any] = {"available": True}
    for key in SAFE_LEDGER_SUMMARY_FIELDS:
        if key in ledger_summary:
            safe[key] = ledger_summary[key]
    return safe


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
    record = load_json(files.get("record_json"))
    promotion = promotion_summary or {}

    if ledger_summary:
        ledger_section: dict[str, Any] = _safe_ledger_summary(ledger_summary)
    else:
        ledger_section = {"available": False, "reason": "missing_ledger_summary"}

    core = {
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": {name: str(path) for name, path in files.items()},
        "capture": extract_capture_summary(capture),
        "environment_capture": extract_environment_capture(capture),
        "account_contamination": extract_account_contamination(capture),
        "historical_db_update": extract_historical_db_update_summary(historical_db_update),
        "kline": extract_kline_summary(kline),
        "record": extract_record_summary(record),
        "delayed_replay": extract_delayed_replay_summary(replay, record),
        "promotion": {
            "ready_to_expand": bool(promotion.get("ready_to_expand")),
            "valid_observation_days": int(promotion.get("valid_observation_days", 0)),
            "observed_days": int(promotion.get("observed_days", 0)),
            "observation_start_date": promotion.get("observation_start_date", ""),
            "excluded_before_start_count": int(promotion.get("excluded_before_start_count", 0)),
            "promotion_blockers": list(promotion.get("promotion_blockers") or []),
            "top_blocking_actions": list(promotion.get("top_blocking_actions") or []),
        },
        "ledger_summary": ledger_section,
    }
    automation = classify_automation_status(core)
    summary = {**automation, **core}

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
