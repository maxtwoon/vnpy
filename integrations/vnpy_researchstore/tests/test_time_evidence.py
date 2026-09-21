"""Scoped SSQuant time-label evidence tests.

Distinguishes: evidence-qualified scope (real bounds published),
outside-scope refusal with candidate preservation, inconclusive evidence
refusal, and source-label inspection queries vs normalized bar-time queries.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from _rs_import_bootstrap import PYARROW_AVAILABLE

from research_store.importers.adapters import import_ssquant_table
from research_store.importers.core_bridge import build_ssquant_spec, to_core_row
from research_store.importers.normalize import normalize_ssquant_row
from research_store.importers.store_sink import StoreSink, iter_candidates
from research_store.importers.time_evidence import (
    LabelEvidenceError,
    LabelProfile,
    build_label_evidence,
)
from research_store.models import AssetRef, compute_dataset_id
from research_store.store import init_store

pytestmark = pytest.mark.skipif(not PYARROW_AVAILABLE, reason="pyarrow required")

FINE = "rb888_1M_raw"
COARSE = "rb888_5M_raw"

_FINE_ROWS = [
    # datetime, open, high, low, close, volume
    ("2026-02-24 09:31:00", 1.0, 1.5, 0.9, 1.2, 10.0),
    ("2026-02-24 09:32:00", 1.2, 1.8, 1.1, 1.6, 20.0),
    ("2026-02-24 09:33:00", 1.6, 1.9, 1.4, 1.5, 30.0),
    ("2026-02-24 09:34:00", 1.5, 1.7, 1.3, 1.4, 40.0),
    ("2026-02-24 09:35:00", 1.4, 1.6, 1.2, 1.3, 50.0),
]
# END hypothesis: 5m bar at 09:35 aggregates 1m 09:31..09:35
_COARSE_END = ("2026-02-24 09:35:00", 1.0, 1.9, 0.9, 1.3, 150.0)
# START hypothesis: 5m bar at 09:31 aggregates 1m 09:31..09:35
_COARSE_START = ("2026-02-24 09:31:00", 1.0, 1.9, 0.9, 1.3, 150.0)


def _make_capture(tmp_path: Path, coarse_row: tuple) -> Path:
    db = tmp_path / "capture.db"
    con = sqlite3.connect(db)
    for table in (FINE, COARSE):
        con.execute(
            f'CREATE TABLE "{table}" (datetime TEXT, symbol TEXT, open REAL,'
            " high REAL, low REAL, close REAL, volume REAL, amount REAL,"
            " openint REAL, real_symbol TEXT)"
        )
    con.executemany(
        f'INSERT INTO "{FINE}" VALUES (?, "rb888", ?, ?, ?, ?, ?, 0, 0, NULL)',
        _FINE_ROWS,
    )
    con.execute(
        f'INSERT INTO "{COARSE}" VALUES (?, "rb888", ?, ?, ?, ?, ?, 0, 0, NULL)',
        coarse_row,
    )
    con.commit()
    con.close()
    return db


def _evidence(db: Path, **kwargs) -> object:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return build_label_evidence(
            con,
            FINE,
            COARSE,
            "2026-02-24 09:00:00",
            "2026-02-24 10:00:00",
            **kwargs,
        )
    finally:
        con.close()


def test_evidence_concludes_end_labels(tmp_path: Path) -> None:
    db = _make_capture(tmp_path, _COARSE_END)
    evidence = _evidence(db)
    assert evidence.conclusion == "end"
    assert evidence.bars_compared == 1
    assert evidence.evidence_id.startswith("ev-")
    # evidence identity is stable for identical scope+data
    assert _evidence(db).evidence_id == evidence.evidence_id


def test_evidence_concludes_start_labels(tmp_path: Path) -> None:
    db = _make_capture(tmp_path, _COARSE_START)
    assert _evidence(db).conclusion == "start"


def test_inconclusive_evidence_refuses_to_guess(tmp_path: Path) -> None:
    bad = ("2026-02-24 09:35:00", 9.0, 9.9, 8.9, 9.3, 999.0)
    db = _make_capture(tmp_path, bad)
    with pytest.raises(LabelEvidenceError, match="inconclusive"):
        _evidence(db)


def test_empty_range_refused(tmp_path: Path) -> None:
    db = _make_capture(tmp_path, _COARSE_END)
    with pytest.raises(LabelEvidenceError, match="no coarse bars"):
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            build_label_evidence(
                con, FINE, COARSE, "2026-03-01 00:00:00", "2026-03-02 00:00:00"
            )
        finally:
            con.close()


def _raw(label: str) -> dict:
    return {
        "datetime": label,
        "symbol": "rb888",
        "open": 1.0,
        "high": 1.5,
        "low": 0.9,
        "close": 1.2,
        "volume": 10.0,
        "amount": 100.0,
    }


def test_profile_resolves_bounds_in_scope(tmp_path: Path) -> None:
    db = _make_capture(tmp_path, _COARSE_END)
    evidence = _evidence(db, capture_sha256="abc123")
    profile = LabelProfile(evidence, interval_minutes=1)
    row = normalize_ssquant_row(
        _raw("2026-02-24 09:31:00"), table=FINE, batch_id="b", series_kind="continuous_888",
        label_profile=profile,
    )
    assert row["bar_start_ns"] is not None
    # END label: 09:31 covers 09:30-09:31 Shanghai
    assert (row["bar_end_ns"] - row["bar_start_ns"]) == 60 * 1_000_000_000
    assert row["trading_date"] is None  # still no calendar evidence
    assert "trading_date_unknown_no_calendar" in row["quality_flags"]
    assert "source_time_label_unknown" not in row["quality_flags"]
    assert row["extensions"]["label_evidence"] == evidence.evidence_id
    # evidenced rows are publishable minute candidates
    core = to_core_row(row, "ds-x", "asset", "batch", interval="1m")
    assert core["trading_date"] is None


def test_outside_scope_stays_honest_candidate(tmp_path: Path) -> None:
    db = _make_capture(tmp_path, _COARSE_END)
    profile = LabelProfile(_evidence(db), interval_minutes=1)
    row = normalize_ssquant_row(
        _raw("2026-05-04 09:31:00"),  # outside the evidenced range
        table=FINE, batch_id="b", series_kind="continuous_888",
        label_profile=profile,
    )
    assert row["bar_start_ns"] is None
    assert "outside_label_evidence_scope" in row["quality_flags"]
    assert "source_time_label_unknown" in row["quality_flags"]


def test_evidenced_publish_and_label_vs_time_queries(tmp_path: Path) -> None:
    """Evidence-qualified scope publishes; source-label inspection stays
    distinct from normalized bar-time queries."""
    db = _make_capture(tmp_path, _COARSE_END)
    evidence = _evidence(db, capture_sha256="")
    profile = LabelProfile(evidence, interval_minutes=1)
    store = init_store(tmp_path / "store")
    try:
        spec = build_ssquant_spec("1m", "continuous_888", time_label=evidence.conclusion)
        asset = AssetRef(
            asset_id="asset-capture",
            origin=str(db),
            format="sqlite",
            size=db.stat().st_size,
            sha256="0" * 64,
        )
        sink = StoreSink(
            store, asset, spec, adapter="ssquant/0.1",
            config={"table": FINE, "label_evidence": evidence.evidence_id},
            batch_id="b-ss",
        )
        import_ssquant_table(db, FINE, sink, batch_id="b-ss", label_profile=profile)
        receipt = sink.publish()
        assert receipt is not None
        assert receipt.state.value == "published"
        assert receipt.accepted_rows == 5
        dataset_id = compute_dataset_id(spec)
        # evidenced semantics produce a DIFFERENT dataset than unevidenced
        assert dataset_id != compute_dataset_id(build_ssquant_spec("1m", "continuous_888"))

        # normalized bar-time query through the real reader
        from datetime import datetime, timezone

        from research_store.snapshots import freeze, open_snapshot
        from research_store.models import Selection, SnapshotRequest

        ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
        reader = open_snapshot(store, ref.snapshot_id)
        try:
            start = datetime(2026, 2, 24, 1, 29, tzinfo=timezone.utc)  # 09:29 +0800
            end = datetime(2026, 2, 24, 1, 31, tzinfo=timezone.utc)  # 09:31 +0800
            batches = list(
                reader.bars(
                    dataset_id, start=start, end=end,
                    required_fields=(), allow_missing_auxiliary=True,
                )
            )
            rows = [r for b in batches for r in b.to_pylist()]
            assert len(rows) == 1
            assert rows[0]["source_label"] == "2026-02-24 09:31:00"
            assert rows[0]["trading_date"] is None  # minute NULL roundtrip
        finally:
            reader.close()

        # source-label inspection query: original label, not normalized time
        from research_store.coverage import fetch_by_source_labels

        by_label = fetch_by_source_labels(store, dataset_id, ["2026-02-24 09:33:00"])
        assert len(by_label) == 1
        assert by_label[0]["volume"] == 30.0
        assert json.loads(by_label[0]["extensions_json"])["label_evidence"] == evidence.evidence_id
    finally:
        store.close()


def test_unevidenced_rows_become_preserved_candidates(tmp_path: Path) -> None:
    db = _make_capture(tmp_path, _COARSE_END)
    store = init_store(tmp_path / "store")
    try:
        spec = build_ssquant_spec("1m", "continuous_888")  # unknown labels
        asset = AssetRef(
            asset_id="asset-capture",
            origin=str(db),
            format="sqlite",
            size=db.stat().st_size,
            sha256="0" * 64,
        )
        sink = StoreSink(
            store, asset, spec, adapter="ssquant/0.1",
            config={"table": FINE}, batch_id="b-ss-cand",
        )
        import_ssquant_table(db, FINE, sink, batch_id="b-ss-cand")
        receipt = sink.publish()
        assert receipt is None  # nothing publishable without evidence
        assert sink.candidate_path is not None
        candidates = list(iter_candidates(sink.candidate_path))
        assert len(candidates) == 5
        # original labels and payload preserved verbatim
        assert candidates[0]["candidate"]["source_label"] == "2026-02-24 09:31:00"
        assert candidates[0]["candidate"]["open"] == 1.0
        assert "CoreBridgeError" in candidates[0]["reason"]
    finally:
        store.close()
