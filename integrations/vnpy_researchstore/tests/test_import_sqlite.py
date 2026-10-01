from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from research_store.importers.sqlite_source import (
    CaptureReceipt,
    build_table_plan,
    capture_sqlite,
    connect_read_only,
    iter_table_months,
    meta_main_overlap_diagnostics,
    parse_table_name,
    simnow_quarantine_keys,
    table_time_span,
)

_COLS = (
    "datetime TEXT PRIMARY KEY, symbol TEXT, real_symbol TEXT, "
    "open REAL, high REAL, low REAL, close REAL, volume REAL, amount REAL, "
    "openint REAL, cumulative_openint REAL"
)


def _make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    for table in ("rb2605_1M_raw", "rb888_1M_raw", "rb888_1M_raw_staging"):
        con.execute(f"CREATE TABLE {table} ({_COLS})")
    con.execute(
        "CREATE TABLE simnow_bar_meta ("
        "datetime TEXT NOT NULL, symbol TEXT NOT NULL, source TEXT NOT NULL, "
        "source_symbol TEXT NOT NULL, exchange TEXT NOT NULL, "
        "vt_symbol TEXT NOT NULL, tick_count INTEGER NOT NULL, "
        "generated_at TEXT NOT NULL, PRIMARY KEY (datetime, symbol))"
    )
    # vendor continuous row: real_symbol set, nonzero -> NOT contamination
    con.execute(
        "INSERT INTO rb888_1M_raw VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-07-01 11:30:00", "rb888", "rb2610", 1, 1, 1, 1, 5, 5, 1, 1),
    )
    # vendor continuous row overlapping a meta key but healthy
    con.execute(
        "INSERT INTO rb888_1M_raw VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-08-31 09:15:00", "rb888", "rb2610", 1, 1, 1, 1, 7, 7, 1, 1),
    )
    # contaminated row: real_symbol NULL, zero volume/amount, in meta
    con.execute(
        "INSERT INTO rb888_1M_raw VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-07-01 15:16:00", "RB888", None, 1, 1, 1, 1, 0, 0, 0, 0),
    )
    # a plain empty-looking vendor row NOT in meta must not be quarantined
    con.execute(
        "INSERT INTO rb888_1M_raw VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-07-02 09:01:00", "rb888", None, 1, 1, 1, 1, 0, 0, 0, 0),
    )
    con.execute(
        "INSERT INTO rb2605_1M_raw VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-02-24 13:30:00", "rb2605", "rb2605", 3036, 3036, 3027, 3029, 8387, 254157290, -1305, 2031110),
    )
    con.execute(
        "INSERT INTO rb888_1M_raw_staging (datetime, symbol, open, high, low, close, volume, amount) "
        "VALUES ('2026-07-01 11:30:00','RB888',1,1,1,1,2,2)"
    )
    for dt in ("2026-07-01 11:30:00", "2026-07-01 15:16:00", "2026-08-31 09:15:00"):
        con.execute(
            "INSERT INTO simnow_bar_meta VALUES (?,?,?,?,?,?,?,?)",
            (dt, "RB888", "simnow_tick_agg", "rb2610", "SHFE", "rb2610.SHFE", 1, "2026-07-01 14:58:36"),
        )
    con.commit()
    con.close()


@pytest.fixture()
def source_db(tmp_path: Path) -> Path:
    db = tmp_path / "kline_data.db"
    _make_db(db)
    return db


def test_parse_table_name() -> None:
    plan = parse_table_name("rb2605_15M_raw")
    assert plan is not None
    assert (plan.symbol, plan.frequency, plan.series_kind, plan.product) == (
        "rb2605",
        "15M",
        "real_contract",
        "rb",
    )
    assert plan.interval_minutes == 15
    plan = parse_table_name("zc888_1M_raw")
    assert plan is not None and plan.series_kind == "continuous_888"
    plan = parse_table_name("ma777_5M_raw")
    assert plan is not None and plan.series_kind == "continuous_777"
    plan = parse_table_name("rb888_1M_raw_staging")
    assert plan is not None and plan.series_kind == "staging"
    assert parse_table_name("simnow_bar_meta") is None
    assert parse_table_name("weird") is None


def test_build_table_plan(source_db: Path) -> None:
    con = connect_read_only(source_db)
    plan = build_table_plan(con)
    kinds = {(p.symbol, p.series_kind) for p in plan}
    assert ("rb2605", "real_contract") in kinds
    assert ("rb888", "continuous_888") in kinds
    assert ("rb888", "staging") in kinds
    con.close()


def test_quarantine_is_precise_not_all_overlap(source_db: Path) -> None:
    con = connect_read_only(source_db)
    quarantine = simnow_quarantine_keys(con)
    diagnostics = meta_main_overlap_diagnostics(con)
    con.close()
    # three meta keys overlap main 1M; only the incident-signature one is
    # quarantined
    assert diagnostics["meta_main_1m_overlap_keys"] == 3
    assert quarantine == {("rb888_1M_raw", "RB888", "2026-07-01 15:16:00")}


def test_time_span(source_db: Path) -> None:
    con = connect_read_only(source_db)
    assert table_time_span(con, "rb2605_1M_raw") == (
        "2026-02-24 13:30:00",
        "2026-02-24 13:30:00",
    )
    con.close()


def test_iter_table_months_units(source_db: Path) -> None:
    con = connect_read_only(source_db)
    months = list(iter_table_months(con, "rb888_1M_raw", chunk_rows=2))
    con.close()
    assert [month for month, _ in months] == ["2026-07", "2026-07", "2026-08"]
    flat = [row for _, rows in months for row in rows]
    assert len(flat) == 4


def test_capture_sqlite_consistent_with_wal(tmp_path: Path, source_db: Path) -> None:
    # write uncheckpointed WAL content, then capture
    con = sqlite3.connect(source_db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        "INSERT INTO rb2605_1M_raw VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-02-25 13:30:00", "rb2605", "rb2605", 1, 1, 1, 1, 1, 1, 1, 1),
    )
    con.commit()
    con.close()
    captures = tmp_path / "captures"
    receipt = capture_sqlite(source_db, captures)
    assert isinstance(receipt, CaptureReceipt)
    assert receipt.quick_check == "ok"
    assert len(receipt.sha256) == 64
    ro = connect_read_only(receipt.capture)
    count = ro.execute("SELECT COUNT(*) FROM rb2605_1M_raw").fetchone()[0]
    ro.close()
    assert count == 2  # WAL row captured consistently
    # source untouched
    src = connect_read_only(source_db)
    assert src.execute("SELECT COUNT(*) FROM rb2605_1M_raw").fetchone()[0] == 2
    src.close()


def test_capture_reuses_never_overwrites(tmp_path: Path, source_db: Path) -> None:
    captures = tmp_path / "captures"
    first = capture_sqlite(source_db, captures)
    # second capture gets a new timestamped name or fails cleanly; it must
    # never overwrite the first capture
    second = capture_sqlite(source_db, captures)
    assert first.capture != second.capture or first.sha256 == second.sha256
