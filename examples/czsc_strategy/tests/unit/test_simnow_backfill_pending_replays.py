import json
import sqlite3
import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_backfill_pending_replays import build_backfill_plan, pending_replay_dates  # noqa: E402


def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


def _make_db(path: Path, max_dt: str) -> None:
    with sqlite3.connect(path) as conn:
        for symbol in ["AP888", "RB888"]:
            table = f"{symbol.lower()}_1M_raw"
            conn.execute(f"CREATE TABLE {table} (datetime TEXT)")
            conn.execute(f"INSERT INTO {table} VALUES (?)", ("2026-01-01 09:00:00",))
            conn.execute(f"INSERT INTO {table} VALUES (?)", (max_dt,))


def test_pending_replay_dates_only_selects_historical_db_lag_pending_rows():
    rows = [
        {"date": "2026-06-21", "status": "pass", "consistency": {"reason": ""}},
        {"date": "2026-06-22", "status": "pending", "consistency": {"reason": "historical_db_lag"}},
        {"date": "2026-06-23", "status": "pending", "consistency": {"reason": "simnow_or_replay_export_missing"}},
        {"date": "2026-06-24", "status": "skipped", "skip_reason": "ctp_disconnect_097_no_snapshot"},
        {
            "date": "2026-06-25",
            "status": "pending",
            "replay": {"meta": {"replay_unavailable_reason": "historical_db_lag"}},
        },
    ]

    assert pending_replay_dates(rows) == ["2026-06-22", "2026-06-25"]
    assert pending_replay_dates(rows, requested_dates={"2026-06-25"}) == ["2026-06-25"]


def test_backfill_plan_waits_for_lagged_database(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    db_path = tmp_path / "bars.db"
    out_dir = tmp_path / "diagnostics"
    out_dir.mkdir()
    _write_ledger(ledger, [
        {"date": "2026-06-27", "status": "pending", "consistency": {"reason": "historical_db_lag"}},
    ])
    _make_db(db_path, "2026-04-25 15:00:00")
    (out_dir / "simnow_export_2026-06-27.json").write_text("{}", encoding="utf-8")

    plan = build_backfill_plan(ledger, db_path, out_dir, ["AP888", "RB888"])

    row = plan["rows"][0]
    assert row["date"] == "2026-06-27"
    assert row["action"] == "waiting_for_db"
    assert row["ready"] is False
    assert row["latest_db_date"] == "2026-04-25"
    assert row["missing_or_lagged_symbols"] == ["AP888", "RB888"]


def test_backfill_plan_marks_ready_when_db_and_capture_exist(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    db_path = tmp_path / "bars.db"
    out_dir = tmp_path / "diagnostics"
    out_dir.mkdir()
    _write_ledger(ledger, [
        {"date": "2026-06-27", "status": "pending", "consistency": {"reason": "historical_db_lag"}},
    ])
    _make_db(db_path, "2026-06-27 15:00:00")
    (out_dir / "simnow_export_2026-06-27.json").write_text("{}", encoding="utf-8")

    plan = build_backfill_plan(ledger, db_path, out_dir, ["AP888", "RB888"])

    row = plan["rows"][0]
    assert row["action"] == "ready_to_backfill"
    assert row["ready"] is True
    assert row["simnow_json_exists"] is True


def test_backfill_plan_requires_capture_export(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    db_path = tmp_path / "bars.db"
    out_dir = tmp_path / "diagnostics"
    out_dir.mkdir()
    _write_ledger(ledger, [
        {"date": "2026-06-27", "status": "pending", "consistency": {"reason": "historical_db_lag"}},
    ])
    _make_db(db_path, "2026-06-27 15:00:00")

    plan = build_backfill_plan(ledger, db_path, out_dir, ["AP888", "RB888"])

    row = plan["rows"][0]
    assert row["action"] == "missing_simnow_export"
    assert row["ready"] is True
    assert row["simnow_json_exists"] is False
