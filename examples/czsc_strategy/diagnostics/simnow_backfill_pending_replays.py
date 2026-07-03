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
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS  # noqa: E402
from simnow_daily_monitor import DEFAULT_LEDGER, read_ledger, write_json  # noqa: E402
from simnow_replay_readiness import build_readiness  # noqa: E402


DEFAULT_PLAN = HERE / "simnow_backfill_plan.json"
DEFAULT_THRESHOLDS = HERE / "simnow_risk_thresholds.json"
DEFAULT_PROMOTION_REPORT = HERE / "simnow_20d_promotion_decision.md"


def _pending_reason(record: dict[str, Any]) -> str:
    consistency = record.get("consistency") or {}
    replay = record.get("replay") or {}
    meta = replay.get("meta") or {}
    return str(
        consistency.get("reason")
        or meta.get("replay_unavailable_reason")
        or record.get("skip_reason")
        or ""
    )


def pending_replay_dates(records: list[dict[str, Any]], requested_dates: set[str] | None = None) -> list[str]:
    """Return pending ledger dates blocked only by historical DB lag."""
    dates: list[str] = []
    for record in records:
        trade_date = str(record.get("date") or "")
        if not trade_date:
            continue
        if requested_dates is not None and trade_date not in requested_dates:
            continue
        if record.get("status") != "pending":
            continue
        if _pending_reason(record) != "historical_db_lag":
            continue
        dates.append(trade_date)
    return sorted(set(dates))


def _paths_for_date(out_dir: Path, trade_date: str) -> dict[str, Path]:
    return {
        "simnow_json": out_dir / f"simnow_export_{trade_date}.json",
        "replay_json": out_dir / f"simnow_replay_{trade_date}.json",
        "record_json": out_dir / f"simnow_record_{trade_date}.json",
        "report_md": out_dir / f"simnow_report_{trade_date}.md",
    }


def build_backfill_plan(
    ledger_path: Path,
    db_path: Path,
    out_dir: Path,
    symbols: list[str],
    requested_dates: set[str] | None = None,
) -> dict[str, Any]:
    records = read_ledger(ledger_path)
    dates = pending_replay_dates(records, requested_dates=requested_dates)
    rows = []
    for trade_date in dates:
        readiness = build_readiness(db_path, trade_date, symbols)
        paths = _paths_for_date(out_dir, trade_date)
        simnow_exists = paths["simnow_json"].exists()
        if not readiness["ready"]:
            action = "waiting_for_db"
        elif not simnow_exists:
            action = "missing_simnow_export"
        else:
            action = "ready_to_backfill"
        rows.append({
            "date": trade_date,
            "action": action,
            "ready": readiness["ready"],
            "latest_db_date": readiness["latest_db_date"],
            "missing_or_lagged_symbols": readiness["missing_or_lagged_symbols"],
            "simnow_json": str(paths["simnow_json"]),
            "simnow_json_exists": simnow_exists,
            "replay_json": str(paths["replay_json"]),
            "record_json": str(paths["record_json"]),
            "report_md": str(paths["report_md"]),
        })
    return {
        "ledger": str(ledger_path),
        "db_path": str(db_path),
        "symbols": symbols,
        "pending_historical_db_lag_days": len(rows),
        "rows": rows,
    }


def _run_checked(args: list[str]) -> None:
    result = subprocess.run(args, cwd=HERE.parents[2], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"command failed with exit code {result.returncode}: {' '.join(args)}")


def execute_backfill(plan: dict[str, Any], ledger_path: Path, thresholds_path: Path, promotion_report: Path) -> dict[str, Any]:
    results = []
    for row in plan["rows"]:
        if row["action"] != "ready_to_backfill":
            results.append({**row, "executed": False})
            continue
        trade_date = row["date"]
        _run_checked([
            sys.executable,
            str(HERE / "export_simnow_replay_snapshot.py"),
            "--date",
            trade_date,
            "--end",
            trade_date,
            "--out-json",
            row["replay_json"],
        ])
        _run_checked([
            sys.executable,
            str(HERE / "simnow_daily_monitor.py"),
            "--date",
            trade_date,
            "--simnow-json",
            row["simnow_json"],
            "--replay-json",
            row["replay_json"],
            "--thresholds",
            str(thresholds_path),
            "--ledger",
            str(ledger_path),
            "--record-json",
            row["record_json"],
            "--report-md",
            row["report_md"],
        ])
        results.append({**row, "action": "backfilled", "executed": True})
    _run_checked([
        sys.executable,
        str(HERE / "simnow_promotion_decision.py"),
        "--ledger",
        str(ledger_path),
        "--report-md",
        str(promotion_report),
    ])
    return {**plan, "rows": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill pending SimNow replay checks once historical DB data arrives.")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--out-dir", type=Path, default=HERE)
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--date", action="append", default=[])
    parser.add_argument("--out-json", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    parser.add_argument("--promotion-report", type=Path, default=DEFAULT_PROMOTION_REPORT)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    requested_dates = set(args.date) if args.date else None
    plan = build_backfill_plan(
        ledger_path=args.ledger,
        db_path=args.db_path,
        out_dir=args.out_dir,
        symbols=args.symbols,
        requested_dates=requested_dates,
    )
    if args.execute:
        plan = execute_backfill(plan, args.ledger, args.thresholds, args.promotion_report)
    write_json(args.out_json, plan)
    print(json.dumps({
        "execute": args.execute,
        "pending_historical_db_lag_days": plan["pending_historical_db_lag_days"],
        "actions": {row["date"]: row["action"] for row in plan["rows"]},
        "out_json": str(args.out_json),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
