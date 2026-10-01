"""Focused tests for the SS representative PHASE1 helper.

Synthetic capture-like SQLite fixtures only — no real capture, no store
writes, no network. The public time_evidence contract is exercised, never
replaced.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from research_store.importers.time_evidence import (
    LabelEvidenceError,
    LabelProfile,
    build_label_evidence,
)
from tools.delivery_ss_representative import (
    fetch_window,
    profile_guard_matrix,
    strict_hypotheses,
    strict_summary,
)

_BAR_COLS = (
    "datetime TEXT PRIMARY KEY, symbol TEXT, real_symbol TEXT, "
    "open REAL, high REAL, low REAL, close REAL, volume REAL, amount REAL, "
    "openint REAL, cumulative_openint REAL"
)


def _minute_rows(start_hour: int, count: int, base: float) -> list[dict]:
    rows = []
    for i in range(count):
        hh = start_hour + (i // 60)
        mm = i % 60
        rows.append(
            {
                "datetime": f"2026-03-02 {hh:02d}:{mm:02d}:00",
                "symbol": "rb2605",
                "real_symbol": "rb2605",
                "open": base + i,
                "high": base + i + 1,
                "low": base + i - 1,
                "close": base + i + 0.5,
                "volume": 100 + i,
                "amount": 1000.0 * (i + 1),
                "openint": 5,
                "cumulative_openint": 500 + i,
            }
        )
    return rows


def _aggregate_fine(fine: list[dict], step: int) -> list[dict]:
    """Build coarse bars under START labeling (label = window open)."""
    coarse = []
    for w in range(len(fine) // step):
        chunk = fine[w * step : (w + 1) * step]
        coarse.append(
            {
                "datetime": chunk[0]["datetime"],
                "symbol": "rb2605",
                "real_symbol": "rb2605",
                "open": chunk[0]["open"],
                "high": max(r["high"] for r in chunk),
                "low": min(r["low"] for r in chunk),
                "close": chunk[-1]["close"],
                "volume": sum(r["volume"] for r in chunk),
                "amount": sum(r["amount"] for r in chunk),
                "openint": chunk[-1]["openint"],
                "cumulative_openint": chunk[-1]["cumulative_openint"],
            }
        )
    return coarse


def _make_db(tmp_path: Path, coarse: list[dict]) -> Path:
    db = tmp_path / "capture.db"
    con = sqlite3.connect(db)
    fine = _minute_rows(9, 60, base=3000.0)
    con.execute(f"CREATE TABLE rb2605_1M_raw ({_BAR_COLS})")
    con.execute(f"CREATE TABLE rb2605_5M_raw ({_BAR_COLS})")
    con.execute(f"CREATE TABLE rb2605_15M_raw ({_BAR_COLS})")
    for table, rows in (
        ("rb2605_1M_raw", fine),
        ("rb2605_5M_raw", coarse[:12]),
        ("rb2605_15M_raw", coarse[12:16]),
    ):
        for r in rows:
            con.execute(
                f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                tuple(r.values()),
            )
    con.commit()
    con.close()
    return db


@pytest.fixture()
def start_labeled_db(tmp_path: Path) -> Path:
    fine = _minute_rows(9, 60, base=3000.0)
    coarse = _aggregate_fine(fine, 5) + _aggregate_fine(fine, 15)
    return _make_db(tmp_path, coarse)


def test_strict_hypotheses_start_labeled(start_labeled_db: Path) -> None:
    con = sqlite3.connect(f"file:{start_labeled_db.as_posix()}?mode=ro", uri=True)
    try:
        fine1 = fetch_window(con, "rb2605_1M_raw", "2026-03-02 09:00:00", "2026-03-02 10:00:00")
        fine5 = fetch_window(con, "rb2605_5M_raw", "2026-03-02 09:00:00", "2026-03-02 10:00:00")
        fine15 = fetch_window(con, "rb2605_15M_raw", "2026-03-02 09:00:00", "2026-03-02 10:00:00")
    finally:
        con.close()
    assert fine1["row_count"] == 60 and fine1["column_count"] == 11
    assert fine5["row_count"] == 12 and fine15["row_count"] == 4

    cmp5 = strict_hypotheses(fine1, fine5, step_minutes=5)
    summary5 = strict_summary(cmp5)
    assert summary5["coarse_bars"] == 12
    assert summary5["strict_start_matches"] == 12  # incl. amount + last OI
    assert summary5["strict_end_matches"] == 0

    cmp15 = strict_hypotheses(fine1, fine15, step_minutes=15)
    summary15 = strict_summary(cmp15)
    assert summary15["strict_start_matches"] == 4
    assert summary15["strict_end_matches"] == 0


def test_public_label_evidence_start_conclusion(start_labeled_db: Path) -> None:
    con = sqlite3.connect(f"file:{start_labeled_db.as_posix()}?mode=ro", uri=True)
    try:
        ev5 = build_label_evidence(
            con, "rb2605_1M_raw", "rb2605_5M_raw",
            "2026-03-02 09:00:00", "2026-03-02 10:00:00",
            capture_sha256="a" * 64,
        )
        ev15 = build_label_evidence(
            con, "rb2605_5M_raw", "rb2605_15M_raw",
            "2026-03-02 09:00:00", "2026-03-02 10:00:00",
            capture_sha256="a" * 64,
        )
    finally:
        con.close()
    assert ev5.conclusion == "start" and ev15.conclusion == "start"
    assert ev5.capture_sha256 == "a" * 64
    # Different capture identity produces a different evidence id.
    con = sqlite3.connect(f"file:{start_labeled_db.as_posix()}?mode=ro", uri=True)
    try:
        ev5_b = build_label_evidence(
            con, "rb2605_1M_raw", "rb2605_5M_raw",
            "2026-03-02 09:00:00", "2026-03-02 10:00:00",
            capture_sha256="b" * 64,
        )
    finally:
        con.close()
    assert ev5_b.evidence_id != ev5.evidence_id


def test_public_label_evidence_inconclusive_refuses(tmp_path: Path) -> None:
    """Ambiguous coarse bars must raise, never guess a convention."""
    fine = _minute_rows(9, 60, base=3000.0)
    coarse5 = _aggregate_fine(fine, 5)
    coarse5[3] = dict(coarse5[3])
    coarse5[3]["volume"] = coarse5[3]["volume"] + 1  # break one bar
    coarse15 = _aggregate_fine(fine, 15)
    coarse15[0] = dict(coarse15[0])
    coarse15[0]["open"] = 999999.0  # break one 15m bar
    db = _make_db(tmp_path, coarse5 + coarse15)
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        with pytest.raises(LabelEvidenceError, match="inconclusive"):
            build_label_evidence(
                con, "rb2605_1M_raw", "rb2605_5M_raw",
                "2026-03-02 09:00:00", "2026-03-02 10:00:00",
                capture_sha256="a" * 64,
            )
        with pytest.raises(LabelEvidenceError, match="inconclusive"):
            build_label_evidence(
                con, "rb2605_5M_raw", "rb2605_15M_raw",
                "2026-03-02 09:00:00", "2026-03-02 10:00:00",
                capture_sha256="a" * 64,
            )
    finally:
        con.close()


def test_profile_guard_matrix_after_correction(start_labeled_db: Path) -> None:
    con = sqlite3.connect(f"file:{start_labeled_db.as_posix()}?mode=ro", uri=True)
    try:
        evidence = build_label_evidence(
            con, "rb2605_1M_raw", "rb2605_5M_raw",
            "2026-03-02 09:00:00", "2026-03-02 10:00:00",
            capture_sha256="a" * 64,
        )
    finally:
        con.close()
    profiles = {"profiles": {"W1-5": {
        "evidence_id": evidence.evidence_id,
        "evidence": evidence.to_dict(),
    }}}
    matrix = profile_guard_matrix(profiles)
    assert matrix["all_ok"] is True
    cases = {c["case"]: c for c in matrix["checks"]}
    assert cases["covered minute row"]["actual"] is True
    assert cases["symbol guard"]["actual"] is False
    assert cases["interval guard"]["actual"] is False
    # corrected 2026-09-30: the series-kind guard rejects staging
    assert cases["staging rejected (corrected)"]["actual"] is False
    # capture binding is enforced on the import path, not inside covers()
    binding = matrix["capture_binding"]
    assert "verify_profile_capture" in binding["enforcement"]


def test_profile_covers_end_label_variant(tmp_path: Path) -> None:
    """An END-labeled source derives conclusion 'end' — never START."""
    fine = _minute_rows(9, 60, base=3000.0)
    by_label = {r["datetime"]: r for r in fine}
    labels = sorted(by_label)
    coarse = []
    for w in range(12):
        chunk = [by_label[labels[w * 5 + i]] for i in range(5)]
        end_label = chunk[-1]["datetime"]  # END labeling
        coarse.append(
            {
                "datetime": end_label,
                "symbol": "rb2605",
                "real_symbol": "rb2605",
                "open": chunk[0]["open"],
                "high": max(r["high"] for r in chunk),
                "low": min(r["low"] for r in chunk),
                "close": chunk[-1]["close"],
                "volume": sum(r["volume"] for r in chunk),
                "amount": sum(r["amount"] for r in chunk),
                "openint": chunk[-1]["openint"],
                "cumulative_openint": chunk[-1]["cumulative_openint"],
            }
        )
    db = _make_db(tmp_path, coarse + _aggregate_fine(fine, 15))
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        ev = build_label_evidence(
            con, "rb2605_1M_raw", "rb2605_5M_raw",
            "2026-03-02 09:00:00", "2026-03-02 10:00:00",
            capture_sha256="a" * 64,
        )
    finally:
        con.close()
    assert ev.conclusion == "end"
    profile = LabelProfile(ev, interval_minutes=1)
    # END-labeled rows carry the bar's closing label; the last window's END
    # label (09:59) is inside the range, so the minute table is covered.
    assert profile.covers("rb2605_1M_raw", "2026-03-02 09:59:00")


# ---------------------------------------------------------------------------
# SS04M completion: MA raw-amount/OI semantics, consumer refusal, SimNow
# quarantine ACTION (public paths only; synthetic fixtures)
# ---------------------------------------------------------------------------


def _ma_raw_row(label: str, amount: float, openint: float, cum: float) -> dict:
    return {
        "datetime": label,
        "symbol": "MA888",
        "real_symbol": "ma609",
        "open": 2400.0,
        "high": 2410.0,
        "low": 2390.0,
        "close": 2405.0,
        "volume": 100.0,
        "amount": amount,
        "openint": openint,
        "cumulative_openint": cum,
    }


def test_ma_normalize_preserves_raw_amount_and_oi() -> None:
    """Public SSQuant normalize: bad amount stays RAW evidence in extensions
    with the untrusted marker while the standardized turnover is MISSING;
    canonical OI comes from source openint (negatives flagged, never
    zeroed); cumulative_openint stays a separate passthrough candidate
    total OI; no bounds without evidence."""
    from research_store.importers.normalize import normalize_ssquant_row

    raw = _ma_raw_row("2026-06-01 09:01:00", 500000.0, -3.0, 712190.0)
    row = normalize_ssquant_row(
        raw, table="ma888_1M_raw", batch_id="b-ma",
        series_kind="continuous_888", label_profile=None,
    )
    assert row["turnover"] is None  # standardized measure MISSING
    assert row["extensions"]["amount"] == 500000.0  # raw, verbatim
    assert row["extensions"]["amount_untrusted"] is True
    assert row["open_interest"] == -3.0  # source OI, negative preserved
    assert "negative:open_interest" in row["quality_flags"]
    assert row["extensions"]["cumulative_openint"] == 712190.0
    assert row["bar_start_ns"] is None and row["bar_end_ns"] is None
    assert "source_time_label_unknown" in row["quality_flags"]


def test_ma_canonical_consumption_refused_at_bridge() -> None:
    """Without evidenced bounds the public bridge refuses canonical
    (VWAP-capable) consumption; rows route to the candidate path."""
    from research_store.importers.core_bridge import CoreBridgeError, to_core_row
    from research_store.importers.normalize import normalize_ssquant_row

    row = normalize_ssquant_row(
        _ma_raw_row("2026-06-01 09:01:00", 500000.0, 3.0, 712190.0),
        table="ma888_1M_raw", batch_id="b-ma",
        series_kind="continuous_888", label_profile=None,
    )
    with pytest.raises(CoreBridgeError, match="non-null bar bounds"):
        to_core_row(row, dataset_id="ds", asset_id="a", batch_id="b", interval="1m")


def test_default_consumer_semantics_refusal() -> None:
    """The native alpha consumer's actual public semantic gate refuses the
    real SSQuant dataset semantics (unknown units/adjustment): the
    VWAP-dependent default consumption refusal."""
    pytest.importorskip("vnpy")
    from research_store.importers.core_bridge import build_ssquant_spec
    from research_store.models import StoreError
    from vnpy_researchstore.native_common import (
        DatasetEntry,
        validate_dataset_semantics,
    )

    spec = build_ssquant_spec("1m", "instrument", time_label="start")
    semantic = {
        "source_id": spec.source_id,
        "record_kind": spec.record_kind.value,
        "interval": spec.interval.value,
        "adjustment": spec.adjustment.value,
        "timezone": spec.timezone,
        "source_time_label": spec.source_time_label.value,
        "volume_unit": spec.volume_unit,
        "turnover_unit": spec.turnover_unit,
    }
    entry = DatasetEntry(
        dataset_id="ds-ssquant-1m",
        semantic=semantic,
        partitions=("RB/2026-03",),
        rows=60,
        coverage_start_ns=1000,
        coverage_end_ns=2000,
    )
    with pytest.raises(StoreError) as excinfo:
        validate_dataset_semantics(entry, purpose="alpha", allow_missing_auxiliary=False)
    message = str(excinfo.value)
    assert "volume unit unknown" in message
    assert "turnover unit unknown" in message
    assert "price adjustment unknown" in message
    # even with auxiliary allowed, volume/adjustment unknown still refuse
    with pytest.raises(StoreError, match="volume unit unknown"):
        validate_dataset_semantics(entry, purpose="alpha", allow_missing_auxiliary=True)


def test_simnow_quarantine_action_removes_exact_rows(tmp_path: Path) -> None:
    """The exact 8 SimNow keys are proven through actual quarantine ACTION:
    refused by the public adapter and absent from the loaded rows."""
    from research_store.importers.adapters import import_ssquant_table
    from research_store.importers.sink import CountingSink
    from research_store.importers.sqlite_source import (
        SIMNOW_INCIDENT_KEYS,
        simnow_quarantine_keys,
    )

    db = tmp_path / "capture.db"
    con = sqlite3.connect(db)
    columns = (
        "(datetime TEXT PRIMARY KEY, symbol TEXT, real_symbol TEXT, "
        "open REAL, high REAL, low REAL, close REAL, volume REAL, "
        "amount REAL, openint REAL, cumulative_openint REAL)"
    )
    incident_by_table: dict[str, list[tuple[str, str]]] = {}
    tables = sorted({f"{s.lower()}_1M_raw" for s, _ in SIMNOW_INCIDENT_KEYS})
    for table in tables:
        con.execute(f'CREATE TABLE "{table}" {columns}')
    for symbol, dt in sorted(SIMNOW_INCIDENT_KEYS):
        table = f"{symbol.lower()}_1M_raw"
        incident_by_table.setdefault(table, []).append((symbol, dt))
        con.execute(
            f'INSERT INTO "{table}" VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (dt, symbol, None, 0, 0, 0, 0, 0, 0, 0, 0),
        )
    for table, keys in incident_by_table.items():
        # a healthy row in the same table must survive
        symbol = keys[0][0]
        con.execute(
            f'INSERT INTO "{table}" VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            ("2026-08-31 09:15:00", symbol, "rb2610", 1, 2, 0.5, 1.5, 7, 7, 1, 1),
        )
    con.execute(
        'CREATE TABLE simnow_bar_meta (datetime TEXT, symbol TEXT, source TEXT)'
    )
    for symbol, dt in sorted(SIMNOW_INCIDENT_KEYS):
        con.execute("INSERT INTO simnow_bar_meta VALUES (?,?, 'simnow')", (dt, symbol))
    con.commit()
    con.close()

    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        detected = simnow_quarantine_keys(con)
    finally:
        con.close()
    assert {f"{s} {d}" for _t, s, d in detected} == {
        f"{s} {d}" for s, d in SIMNOW_INCIDENT_KEYS
    }

    total_quarantined = 0
    for table, keys in incident_by_table.items():
        sink = CountingSink()
        receipt = import_ssquant_table(
            db, table, sink, batch_id=f"q-{table}", quarantine_keys=detected
        )
        assert receipt.rows_quarantined == len(keys)
        assert receipt.rows_read == 1  # only the healthy row survives
        loaded = {str(r["source_label"]) for r in sink.rows}
        for _symbol, dt in keys:
            assert dt not in loaded
        total_quarantined += receipt.rows_quarantined
    assert total_quarantined == 8
