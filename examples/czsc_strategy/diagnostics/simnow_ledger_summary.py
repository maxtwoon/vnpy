from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from simnow_action_summary import build_action_summary, _record_reason
from simnow_observation_rules import is_valid_observation
from simnow_observation_window import filter_records_by_start, load_observation_start_date


HERE = Path(__file__).resolve().parent
DEFAULT_LEDGER = HERE / "simnow_observation_ledger.jsonl"
DEFAULT_OUT_JSON = HERE / "simnow_ledger_summary.json"
DEFAULT_MIN_DAYS = 20

SENSITIVE_KEY_PATTERNS = {"密码", "授权码", "auth_code", "password", "BrokerID", "username", "UserID"}
SENSITIVE_VALUE_FRAGMENTS = {"setting_masked"}


def load_ledger(path: Path) -> list[dict[str, Any]]:
    """Load the observation ledger JSONL if it exists; otherwise return an empty list."""
    if not path or not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def _automation_status(record: dict[str, Any]) -> str:
    """Map a ledger record to the run-summary automation status vocabulary."""
    status = str(record.get("status") or "")
    valid = bool(record.get("valid_observation"))
    if status == "pass" and valid:
        return "valid"
    if status in {"skipped", "pending", "halt"}:
        return status
    return "failed"


def _record_safe_latest(record: dict[str, Any]) -> dict[str, Any]:
    """Return only the safe, summary-level fields from the latest record.

    Preserves the minimum context (reason, missing symbols, threshold rows) so
    action_recommendation can produce reason-specific text without exposing raw
    capture fields, DB paths, or contract maps.
    """
    status = str(record.get("status") or "")
    safe: dict[str, Any] = {
        "date": str(record.get("date") or ""),
        "status": status,
        "valid_observation": bool(record.get("valid_observation")),
        "automation_status": _automation_status(record),
    }

    if status == "skipped" and record.get("skip_reason"):
        safe["skip_reason"] = str(record["skip_reason"])
    elif record.get("consistency", {}).get("reason"):
        safe["consistency"] = {"reason": str(record["consistency"]["reason"])}

    thresholds = record.get("thresholds") or {}
    safe["thresholds"] = {"status": str(thresholds.get("status", ""))}
    if thresholds.get("rows"):
        safe["thresholds"]["rows"] = [
            {
                "metric": str(row.get("metric", "")),
                "value": row.get("value"),
                "unit": str(row.get("unit", "")),
                "level": str(row.get("level", "")),
            }
            for row in thresholds["rows"]
        ]

    subscription = record.get("subscription_coverage") or {}
    if subscription.get("missing_symbols"):
        safe["subscription_coverage"] = {
            "missing_symbols": list(subscription["missing_symbols"])
        }

    kline = record.get("kline_coverage") or {}
    kline_safe: dict[str, Any] = {}
    if kline.get("missing_symbols"):
        kline_safe["missing_symbols"] = list(kline["missing_symbols"])
    if kline.get("short_symbols"):
        kline_safe["short_symbols"] = list(kline["short_symbols"])
    if kline.get("min_bars_per_symbol") is not None:
        kline_safe["min_bars_per_symbol"] = kline["min_bars_per_symbol"]
    if kline_safe:
        safe["kline_coverage"] = kline_safe

    return safe


def _count_consecutive_valid_days(ordered: list[dict[str, Any]]) -> int:
    """Count trailing consecutive valid trading-day rows in the ledger.

    A record counts as valid when `status == "pass"` and `valid_observation`
    is true, which is the same rule used to flag valid observation days in the
    ledger. Weekends and exchange holidays do not break the streak; only a
    non-valid record (pending, skipped, halt, failed, or valid_observation=false)
    stops the count.
    """
    count = 0
    for row in reversed(ordered):
        if row.get("status") == "pass" and bool(row.get("valid_observation")):
            count += 1
        else:
            break
    return count


def build_ledger_summary(
    records: list[dict[str, Any]],
    min_days: int = DEFAULT_MIN_DAYS,
    observation_start_date: str | None = None,
) -> dict[str, Any]:
    """Build a machine-readable summary of the SimNow observation ledger.

    The summary only exposes aggregate counts and selected safe fields from the
    latest record. It never includes raw tick payloads, contract maps, account IDs,
    passwords, or the full masked setting object.
    """
    all_records = sorted(records, key=lambda row: str(row.get("date", "")))
    ordered = sorted(filter_records_by_start(all_records, observation_start_date), key=lambda row: str(row.get("date", "")))
    total_rows = len(ordered)
    excluded_before_start_count = len(all_records) - len(ordered)

    valid_days = sum(1 for row in ordered if is_valid_observation(row))
    pending_days = sum(1 for row in ordered if _automation_status(row) == "pending")
    skipped_days = sum(1 for row in ordered if _automation_status(row) == "skipped")
    halt_days = sum(1 for row in ordered if _automation_status(row) == "halt")
    failed_days = sum(1 for row in ordered if _automation_status(row) == "failed")

    latest_record = ordered[-1] if ordered else {}
    latest_valid = next((row for row in reversed(ordered) if is_valid_observation(row)), None)

    status_counts = dict(sorted(Counter(_automation_status(row) for row in ordered).items()))
    reason_counts = dict(sorted(Counter(
        _record_reason(row) for row in ordered if _record_reason(row)
    ).items()))

    blockers: list[str] = []
    if valid_days < min_days:
        blockers.append(f"need_{min_days - valid_days}_more_valid_observation_days")
    if pending_days:
        blockers.append("pending_days_present")
    if skipped_days:
        blockers.append("skipped_days_present")
    if halt_days:
        blockers.append("halt_days_present")
    if failed_days:
        blockers.append("failed_days_present")

    ready_to_expand = (
        valid_days >= min_days
        and pending_days == 0
        and skipped_days == 0
        and halt_days == 0
        and failed_days == 0
    )

    latest_action: dict[str, Any] = {}
    if latest_record:
        latest_action = build_action_summary([_record_safe_latest(latest_record)])[0]

    latest_status = _automation_status(latest_record)
    if not latest_record:
        next_action = "continue daily observation"
    elif ready_to_expand:
        next_action = "review promotion readiness"
    elif latest_status == "pending":
        next_action = "resolve latest pending reason"
    elif latest_status == "skipped":
        next_action = "wait for next valid session"
    elif latest_status in {"halt", "failed"}:
        next_action = "manual review required"
    else:
        next_action = "continue daily observation"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_days": min_days,
        "observation_start_date": observation_start_date or "",
        "excluded_before_start_count": excluded_before_start_count,
        "total_rows": total_rows,
        "valid_observation_days": valid_days,
        "pending_days": pending_days,
        "skipped_days": skipped_days,
        "halt_days": halt_days,
        "failed_days": failed_days,
        "latest_date": str(latest_record.get("date")) if latest_record else "",
        "latest_valid_date": str(latest_valid.get("date")) if latest_valid else "",
        "consecutive_valid_days": _count_consecutive_valid_days(ordered),
        "ready_to_expand": ready_to_expand,
        "promotion_blockers": blockers,
        "reason_counts": reason_counts,
        "automation_status_counts": status_counts,
        "latest_record": _record_safe_latest(latest_record) if latest_record else {},
        "latest_action": latest_action,
        "next_action": next_action,
    }


def _iter_summary_nodes(obj: Any, path: str = "") -> Any:
    """Yield (path, value) tuples for every scalar in the summary."""
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
        description="Generate a machine-readable summary of the SimNow observation ledger."
    )
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER, help="Path to simnow_observation_ledger.jsonl.")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON, help="Path to write the summary JSON.")
    parser.add_argument("--min-days", type=int, default=DEFAULT_MIN_DAYS, help="Minimum valid observation days required.")
    parser.add_argument(
        "--observation-start-date",
        default=None,
        help="Only count ledger rows on or after this date. Defaults to simnow_observation_window.json.",
    )
    args = parser.parse_args()

    records = load_ledger(args.ledger)
    start_date = args.observation_start_date
    if start_date is None:
        start_date = load_observation_start_date()
    summary = build_ledger_summary(records, min_days=args.min_days, observation_start_date=start_date)

    sensitive = contains_sensitive_data(summary)
    if sensitive:
        raise RuntimeError(f"ledger summary contains sensitive data: {sensitive}")

    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
