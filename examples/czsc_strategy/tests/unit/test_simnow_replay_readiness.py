import sqlite3
import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_replay_readiness import build_readiness  # noqa: E402


def _make_db(path: Path, max_dt: str) -> None:
    with sqlite3.connect(path) as conn:
        for symbol in ["AP888", "RB888"]:
            table = f"{symbol.lower()}_1M_raw"
            conn.execute(f"CREATE TABLE {table} (datetime TEXT)")
            conn.execute(f"INSERT INTO {table} VALUES (?)", ("2026-01-01 09:00:00",))
            conn.execute(f"INSERT INTO {table} VALUES (?)", (max_dt,))


def test_replay_readiness_detects_ready_database(tmp_path):
    db_path = tmp_path / "bars.db"
    _make_db(db_path, "2026-06-27 15:00:00")

    payload = build_readiness(db_path, "2026-06-27", ["AP888", "RB888"])

    assert payload["ready"] is True
    assert payload["latest_db_date"] == "2026-06-27"
    assert payload["missing_or_lagged_symbols"] == []


def test_replay_readiness_detects_lagged_database(tmp_path):
    db_path = tmp_path / "bars.db"
    _make_db(db_path, "2026-04-25 15:00:00")

    payload = build_readiness(db_path, "2026-06-27", ["AP888", "RB888"])

    assert payload["ready"] is False
    assert payload["latest_db_date"] == "2026-04-25"
    assert payload["missing_or_lagged_symbols"] == ["AP888", "RB888"]
