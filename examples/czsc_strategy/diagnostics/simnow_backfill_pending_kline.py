from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from chan_strategy.config import SQLITE_DB_PATH  # noqa: E402
from simnow_contract_map_meta import contract_map_provenance, load_contract_map_payload  # noqa: E402
from simnow_daily_monitor import DEFAULT_LEDGER, read_ledger, write_json  # noqa: E402
from simnow_replay_readiness import DEFAULT_CONTRACT_MAP, load_enabled_symbols  # noqa: E402
from simnow_tick_bars import apply_contract_map_override, aggregate_ticks_to_1m, load_json, summarize_bars  # noqa: E402


DEFAULT_PLAN = HERE / "simnow_kline_backfill_plan.json"
DEFAULT_THRESHOLDS = HERE / "simnow_risk_thresholds.json"
DEFAULT_PROMOTION_REPORT = HERE / "simnow_20d_promotion_decision.md"
DEFAULT_LEDGER_SUMMARY = HERE / "simnow_ledger_summary.json"


def _pending_reason(record: dict[str, Any]) -> str:
    consistency = record.get("consistency") or {}
    return str(consistency.get("reason") or record.get("skip_reason") or "")


def pending_kline_dates(records: list[dict[str, Any]], requested_dates: set[str] | None = None) -> list[str]:
    """Return pending ledger dates blocked by kline coverage gates."""
    dates: list[str] = []
    for record in records:
        trade_date = str(record.get("date") or "")
        if not trade_date:
            continue
        if requested_dates is not None and trade_date not in requested_dates:
            continue
        if record.get("status") != "pending":
            continue
        if _pending_reason(record) not in {"kline_coverage_incomplete", "kline_coverage_too_short"}:
            continue
        dates.append(trade_date)
    return sorted(set(dates))


def _paths_for_date(out_dir: Path, trade_date: str) -> dict[str, Path]:
    return {
        "simnow_json": out_dir / f"simnow_export_{trade_date}.json",
        "replay_json": out_dir / f"simnow_replay_{trade_date}.json",
        "kline_json": out_dir / f"simnow_kline_update_{trade_date}.json",
        "record_json": out_dir / f"simnow_record_{trade_date}.json",
        "report_md": out_dir / f"simnow_report_{trade_date}.md",
    }


def _recompute_kline_summary(
    simnow_json: Path,
    contract_map_path: Path,
    min_bars_per_symbol: int,
    db_path: Path,
) -> dict[str, Any]:
    payload = load_json(simnow_json)
    contract_map = load_contract_map_payload(contract_map_path)
    effective = apply_contract_map_override(payload, contract_map)
    bars = aggregate_ticks_to_1m(effective)
    summary = summarize_bars(db_path, bars, effective, min_bars_per_symbol=min_bars_per_symbol)
    summary["simnow_json"] = str(simnow_json)
    summary["contract_map_json"] = str(contract_map_path)
    return summary


def build_backfill_plan(
    ledger_path: Path,
    out_dir: Path,
    contract_map_path: Path,
    min_bars_per_symbol: int,
    db_path: Path = Path(SQLITE_DB_PATH),
    requested_dates: set[str] | None = None,
) -> dict[str, Any]:
    records = read_ledger(ledger_path)
    dates = pending_kline_dates(records, requested_dates=requested_dates)
    current_enabled_symbols = load_enabled_symbols(contract_map_path)
    provenance = contract_map_provenance(contract_map_path)
    rows = []
    for trade_date in dates:
        paths = _paths_for_date(out_dir, trade_date)
        simnow_exists = paths["simnow_json"].exists()
        row: dict[str, Any] = {
            "date": trade_date,
            "simnow_json": str(paths["simnow_json"]),
            "simnow_json_exists": simnow_exists,
            "kline_json": str(paths["kline_json"]),
            "replay_json": str(paths["replay_json"]),
            "record_json": str(paths["record_json"]),
            "report_md": str(paths["report_md"]),
            "current_expected_symbols": current_enabled_symbols,
        }
        if not simnow_exists:
            row["action"] = "missing_simnow_export"
        else:
            recomputed = _recompute_kline_summary(paths["simnow_json"], contract_map_path, min_bars_per_symbol, db_path)
            row["recomputed_missing_symbols"] = recomputed["missing_symbols"]
            row["recomputed_short_symbols"] = recomputed["short_symbols"]
            if recomputed["missing_symbols"] or recomputed["short_symbols"]:
                row["action"] = "still_blocked_after_recompute"
            else:
                row["action"] = "ready_to_recompute"
        rows.append(row)
    return {
        "ledger": str(ledger_path),
        "out_dir": str(out_dir),
        "db_path": str(db_path),
        "contract_map": str(contract_map_path),
        "symbols": current_enabled_symbols,
        "contract_map_provenance": provenance,
        "min_bars_per_symbol": min_bars_per_symbol,
        "pending_kline_days": len(rows),
        "rows": rows,
    }


def _run_checked(args: list[str], accepted_exit_codes: set[int] | None = None) -> None:
    accepted_exit_codes = accepted_exit_codes or {0}
    result = subprocess.run(args, cwd=HERE.parents[2], check=False)
    if result.returncode not in accepted_exit_codes:
        raise RuntimeError(f"command failed with exit code {result.returncode}: {' '.join(args)}")


def _refresh_summary_artifacts(rows: list[dict[str, Any]], ledger_path: Path, promotion_report: Path) -> None:
    if not rows:
        return

    out_dir = Path(rows[0]["simnow_json"]).parent
    ledger_summary = out_dir / DEFAULT_LEDGER_SUMMARY.name
    _run_checked([
        sys.executable,
        str(HERE / "simnow_ledger_summary.py"),
        "--ledger",
        str(ledger_path),
        "--out-json",
        str(ledger_summary),
    ])
    _run_checked([
        sys.executable,
        str(HERE / "simnow_promotion_decision.py"),
        "--ledger",
        str(ledger_path),
        "--report-md",
        str(promotion_report),
    ])
    for row in rows:
        trade_date = row["date"]
        historical_db_update = out_dir / f"simnow_historical_db_update_{trade_date}.json"
        run_summary = out_dir / f"simnow_run_summary_{trade_date}.json"
        daily_brief = out_dir / f"simnow_daily_brief_{trade_date}.md"
        _run_checked([
            sys.executable,
            str(HERE / "simnow_run_summary.py"),
            "--date",
            trade_date,
            "--out-dir",
            str(out_dir),
            "--out-json",
            str(run_summary),
            "--ledger",
            str(ledger_path),
            "--ledger-summary",
            str(ledger_summary),
            "--historical-db-update",
            str(historical_db_update),
        ])
        _run_checked([
            sys.executable,
            str(HERE / "simnow_daily_brief.py"),
            "--date",
            trade_date,
            "--run-summary",
            str(run_summary),
            "--out-md",
            str(daily_brief),
        ])
        _run_checked([
            sys.executable,
            str(HERE / "simnow_summary_consistency.py"),
            "--date",
            trade_date,
            "--run-summary",
            str(run_summary),
            "--record-json",
            str(out_dir / f"simnow_record_{trade_date}.json"),
            "--ledger-summary",
            str(ledger_summary),
            "--daily-brief",
            str(daily_brief),
            "--report-md",
            str(out_dir / f"simnow_report_{trade_date}.md"),
            "--kline-json",
            str(out_dir / f"simnow_kline_update_{trade_date}.json"),
        ])


def execute_backfill(
    plan: dict[str, Any],
    thresholds_path: Path,
    ledger_path: Path,
    promotion_report: Path,
) -> dict[str, Any]:
    results = []
    executed_rows: list[dict[str, Any]] = []
    for row in plan["rows"]:
        if row["action"] != "ready_to_recompute":
            results.append({**row, "executed": False})
            continue
        trade_date = row["date"]
        _run_checked([
            sys.executable,
            str(HERE / "simnow_tick_bars.py"),
            "--simnow-json",
            row["simnow_json"],
            "--summary-json",
            row["kline_json"],
            "--contract-map-json",
            plan["contract_map"],
            "--min-bars-per-symbol",
            str(plan["min_bars_per_symbol"]),
        ])
        monitor_args = [
            sys.executable,
            str(HERE / "simnow_daily_monitor.py"),
            "--date",
            trade_date,
            "--simnow-json",
            row["simnow_json"],
            "--kline-json",
            row["kline_json"],
            "--thresholds",
            str(thresholds_path),
            "--ledger",
            str(ledger_path),
            "--record-json",
            row["record_json"],
            "--report-md",
            row["report_md"],
        ]
        if Path(row["replay_json"]).exists():
            monitor_args += ["--replay-json", row["replay_json"]]
        _run_checked(monitor_args, accepted_exit_codes={0, 2})
        refreshed = {**row, "action": "recomputed", "executed": True}
        results.append(refreshed)
        executed_rows.append(refreshed)
    _refresh_summary_artifacts(executed_rows, ledger_path, promotion_report)
    return {**plan, "rows": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-evaluate pending SimNow kline gates using the current formal contract map.")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--out-dir", type=Path, default=HERE)
    parser.add_argument("--contract-map", type=Path, default=DEFAULT_CONTRACT_MAP)
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--min-bars-per-symbol", type=int, default=30)
    parser.add_argument("--date", action="append", default=[])
    parser.add_argument("--out-json", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    parser.add_argument("--promotion-report", type=Path, default=DEFAULT_PROMOTION_REPORT)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    requested_dates = set(args.date) if args.date else None
    plan = build_backfill_plan(
        ledger_path=args.ledger,
        out_dir=args.out_dir,
        contract_map_path=args.contract_map,
        min_bars_per_symbol=args.min_bars_per_symbol,
        db_path=args.db_path,
        requested_dates=requested_dates,
    )
    if args.execute:
        plan = execute_backfill(plan, args.thresholds, args.ledger, args.promotion_report)
    write_json(args.out_json, plan)
    print(json.dumps({
        "execute": args.execute,
        "pending_kline_days": plan["pending_kline_days"],
        "actions": {row["date"]: row["action"] for row in plan["rows"]},
        "out_json": str(args.out_json),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
