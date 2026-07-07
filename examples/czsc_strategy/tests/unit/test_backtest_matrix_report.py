import sys
import sqlite3
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from diagnostics.backtest_matrix_report import _dominant_symbol  # noqa: E402


def _make_db(tmp_path: Path, rows: list[tuple[str, str]]) -> Path:
    db = tmp_path / "mixed.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "create table ap888_1M_raw ("
        "datetime text, symbol text, open real, high real, low real, close real, volume real, amount real"
        ")"
    )
    typed_rows = [
        (dt, sym, 100.0, 101.0, 99.0, 100.0, 1.0, 1.0)
        for dt, sym in rows
    ]
    conn.executemany(
        "insert into ap888_1M_raw values (?,?,?,?,?,?,?,?)",
        typed_rows,
    )
    conn.commit()
    conn.close()
    return db


def test_dominant_symbol_prefers_symbol_that_covers_end_date(tmp_path: Path) -> None:
    """When one symbol stops before the target date, choose the one that reaches it."""
    rows = [
        # Older uppercase series: more rows but ends before 2026-07-06.
        (f"2022-01-04 09:{i:02d}:00", "AP888") for i in range(60)
    ] + [
        # Newer lowercase series: fewer rows but covers 2026-07-06.
        (f"2026-07-06 09:{i:02d}:00", "ap888") for i in range(30)
    ]
    db = _make_db(tmp_path, rows)
    assert _dominant_symbol(db, "ap888_1M_raw", "2022-01-01", "2026-07-06") == "ap888"


def test_dominant_symbol_falls_back_to_latest_bar_when_none_cover_end(tmp_path: Path) -> None:
    """If no symbol reaches the end date, pick the one with the latest bar."""
    rows = [
        (f"2022-01-04 09:{i:02d}:00", "AP888") for i in range(60)
    ] + [
        (f"2026-06-30 09:{i:02d}:00", "ap888") for i in range(10)
    ]
    db = _make_db(tmp_path, rows)
    assert _dominant_symbol(db, "ap888_1M_raw", "2022-01-01", "2026-07-06") == "ap888"


def test_dominant_symbol_returns_only_symbol_when_single_series(tmp_path: Path) -> None:
    rows = [
        (f"2026-07-06 09:{i:02d}:00", "rb888") for i in range(10)
    ]
    db = _make_db(tmp_path, rows)
    assert _dominant_symbol(db, "ap888_1M_raw", "2022-01-01", "2026-07-06") == "rb888"
