"""Scoped SSQuant time-label evidence tests.

Distinguishes: evidence-qualified scope (real bounds published),
outside-scope refusal with candidate preservation, inconclusive evidence
refusal, and source-label inspection queries vs normalized bar-time queries.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
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
    verify_profile_capture,
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


def _attach_receipt(db: Path) -> dict:
    """Attach a producer-format validated-capture receipt (test fixture
    standing in for the capture recovery tool's output). The verifier
    re-hashes the file, so only the file's TRUE sha256 passes."""
    receipt = {
        "validation_kind": "current_recovery_validation",
        "source": "synthetic-source.db",
        "capture": str(db),
        "bytes": db.stat().st_size,
        "sha256": hashlib.sha256(db.read_bytes()).hexdigest(),
        "quick_check": "ok",
        "captured_at": None,
        "captured_at_basis": "UNKNOWN (test fixture)",
        "observed_capture_mtime_utc": datetime.fromtimestamp(
            db.stat().st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds"),
        "validated_at": "2026-09-17T00:00:00+00:00",
    }
    db.with_suffix(db.suffix + ".receipt.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    return receipt


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
    # Evidence and receipt must bind the SAME content identity: the actual
    # file hash (the verifier re-checks it for captures <= 2GiB).
    sha = hashlib.sha256(db.read_bytes()).hexdigest()
    evidence = _evidence(db, capture_sha256=sha)
    _attach_receipt(db)
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


# ---------------------------------------------------------------------------
# capture/table-kind binding guards (04M scope correction, 2026-09-30)
# ---------------------------------------------------------------------------


def test_profile_rejects_tables_outside_evidenced_family(tmp_path: Path) -> None:
    """A real-contract evidence never qualifies staging tables, and a
    continuous evidence never qualifies real-contract tables."""
    db = _make_capture(tmp_path, _COARSE_END)
    continuous_profile = LabelProfile(_evidence(db), interval_minutes=1)
    assert continuous_profile.covers(FINE, "2026-02-24 09:31:00")
    # different symbol / interval / range still guarded
    assert not continuous_profile.covers("rb2605_1M_raw", "2026-02-24 09:31:00")
    assert not continuous_profile.covers(FINE, "2026-02-24 10:00:00")
    assert not continuous_profile.covers("rb888_5M_raw", "2026-02-24 09:31:00")


def test_real_contract_profile_rejects_staging(tmp_path: Path) -> None:
    """The 04M production case: rb2605 real-contract evidence must not
    qualify the same symbol's staging table (previously a public gap)."""
    db = tmp_path / "rb.db"
    con = sqlite3.connect(db)
    for table in ("rb2605_1M_raw", "rb2605_5M_raw", "rb2605_1M_raw_staging"):
        con.execute(
            f'CREATE TABLE "{table}" (datetime TEXT PRIMARY KEY, symbol TEXT,'
            " real_symbol TEXT, open REAL, high REAL, low REAL, close REAL,"
            " volume REAL, amount REAL, openint REAL, cumulative_openint REAL)"
        )
    for minute in range(5):
        row = (
            f"2026-03-02 09:0{minute}:00", "rb2605", "rb2605",
            100 + minute, 101 + minute, 99 + minute, 100 + minute,
            1, 1000, 0, 500,
        )
        con.execute('INSERT INTO rb2605_1M_raw VALUES (?,?,?,?,?,?,?,?,?,?,?)', row)
        con.execute('INSERT INTO rb2605_1M_raw_staging VALUES (?,?,?,?,?,?,?,?,?,?,?)', row)
    con.execute(
        'INSERT INTO rb2605_5M_raw VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        ("2026-03-02 09:00:00", "rb2605", "rb2605", 100, 105, 99, 104, 5, 5000, 0, 500),
    )
    con.commit()
    con.close()
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        evidence = build_label_evidence(
            con, "rb2605_1M_raw", "rb2605_5M_raw",
            "2026-03-02 09:00:00", "2026-03-02 09:05:00",
            capture_sha256="a" * 64,
        )
    finally:
        con.close()
    profile = LabelProfile(evidence, interval_minutes=1)
    assert profile.covers("rb2605_1M_raw", "2026-03-02 09:01:00")
    # the corrected guard: staging of the same symbol/interval/range
    assert not profile.covers("rb2605_1M_raw_staging", "2026-03-02 09:01:00")


def test_import_refuses_profile_from_different_capture(tmp_path: Path) -> None:
    """The opened capture must be receipt-bound to the profile's evidence;
    a different capture (even with identical schema) is refused safely."""
    from research_store.importers.sink import CountingSink

    db_a = _make_capture(tmp_path, _COARSE_END)
    db_b = tmp_path / "other.db"
    db_b.write_bytes(db_a.read_bytes()[:-1] + b"\x00")  # same schema, other bytes
    sha_a = hashlib.sha256(db_a.read_bytes()).hexdigest()
    profile = LabelProfile(_evidence(db_a, capture_sha256=sha_a), interval_minutes=1)

    # capture B has no validated receipt at all
    with pytest.raises(LabelEvidenceError, match="no validated-capture receipt"):
        import_ssquant_table(db_b, FINE, CountingSink(), "b1", label_profile=profile)
    # copying capture A's (valid) receipt to B still fails: path identity differs
    import shutil

    _attach_receipt(db_a)
    shutil.copy2(
        db_a.with_suffix(db_a.suffix + ".receipt.json"),
        db_b.with_suffix(db_b.suffix + ".receipt.json"),
    )
    with pytest.raises(LabelEvidenceError, match="different file"):
        import_ssquant_table(db_b, FINE, CountingSink(), "b2", label_profile=profile)


def test_import_positive_with_receipt_and_tamper_refusals(tmp_path: Path) -> None:
    """Positive path works with a true validated receipt; tampered receipt
    content or file identity is refused before any row is read."""
    from research_store.importers.sink import CountingSink

    db = _make_capture(tmp_path, _COARSE_END)
    sha = hashlib.sha256(db.read_bytes()).hexdigest()
    profile = LabelProfile(_evidence(db, capture_sha256=sha), interval_minutes=1)

    # evidence bound to a hash that does not match the receipt must fail
    _attach_receipt(db)
    bad_profile = LabelProfile(
        _evidence(db, capture_sha256="f" * 64), interval_minutes=1
    )
    with pytest.raises(LabelEvidenceError, match="does not match the validated"):
        import_ssquant_table(db, FINE, CountingSink(), "t1", label_profile=bad_profile)

    # evidence bound to the receipt's actual sha256 works and gives bounds
    sink = CountingSink()
    receipt = import_ssquant_table(db, FINE, sink, "t2", label_profile=profile)
    assert receipt.rows_read == 5
    assert all(r["bar_start_ns"] is not None for r in sink.rows)

    # tampering with the receipt content is detected (sha no longer matches)
    receipt_path = db.with_suffix(db.suffix + ".receipt.json")
    tampered = json.loads(receipt_path.read_text(encoding="utf-8"))
    tampered["sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(LabelEvidenceError, match="does not match the validated"):
        import_ssquant_table(db, FINE, CountingSink(), "t3", label_profile=profile)
    _attach_receipt(db)  # restore

    # modifying the file after validation is detected via size
    db.write_bytes(db.read_bytes() + b"\x00")
    with pytest.raises(LabelEvidenceError, match="size"):
        import_ssquant_table(db, FINE, CountingSink(), "t4", label_profile=profile)


def test_staging_import_with_profile_stays_candidate(tmp_path: Path) -> None:
    """Wrong-kind case fails safely: staging rows with a real-contract
    profile get NO canonical bounds and stay preserved candidates."""
    db = tmp_path / "rb.db"
    con = sqlite3.connect(db)
    for table in ("rb2605_1M_raw", "rb2605_5M_raw", "rb2605_1M_raw_staging"):
        con.execute(
            f'CREATE TABLE "{table}" (datetime TEXT PRIMARY KEY, symbol TEXT,'
            " real_symbol TEXT, open REAL, high REAL, low REAL, close REAL,"
            " volume REAL, amount REAL, openint REAL, cumulative_openint REAL)"
        )
    for minute in range(5):
        row = (
            f"2026-03-02 09:0{minute}:00", "rb2605", "rb2605",
            100 + minute, 101 + minute, 99 + minute, 100 + minute,
            1, 1000, 0, 500,
        )
        con.execute("INSERT INTO rb2605_1M_raw VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        con.execute("INSERT INTO rb2605_1M_raw_staging VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
    con.execute(
        "INSERT INTO rb2605_5M_raw VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-03-02 09:00:00", "rb2605", "rb2605", 100, 105, 99, 104, 5, 5000, 0, 500),
    )
    con.commit()
    con.close()
    sha = hashlib.sha256(db.read_bytes()).hexdigest()
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        evidence = build_label_evidence(
            con, "rb2605_1M_raw", "rb2605_5M_raw",
            "2026-03-02 09:00:00", "2026-03-02 09:05:00",
            capture_sha256=sha,
        )
    finally:
        con.close()
    _attach_receipt(db)
    profile = LabelProfile(evidence, interval_minutes=1)
    store = init_store(tmp_path / "store")
    try:
        spec = build_ssquant_spec("1m", "staging", time_label=evidence.conclusion)
        asset = AssetRef(
            asset_id="asset-staging",
            origin=str(db),
            format="sqlite",
            size=db.stat().st_size,
            sha256=sha,
        )
        sink = StoreSink(
            store, asset, spec, adapter="ssquant/0.1",
            config={"table": "rb2605_1M_raw_staging"}, batch_id="b-staging",
        )
        import_ssquant_table(
            db, "rb2605_1M_raw_staging", sink, batch_id="b-staging",
            label_profile=profile,
        )
        publish = sink.publish()
        # nothing publishable: staging rows are never given canonical bounds
        assert publish is None
        candidates = list(iter_candidates(sink.candidate_path))
        assert len(candidates) == 5
        first = candidates[0]["candidate"]
        assert first["bar_start_ns"] is None
        assert "outside_label_evidence_scope" in first["quality_flags"]
    finally:
        store.close()


def test_verify_profile_capture_modes(tmp_path: Path, monkeypatch) -> None:
    """Small captures are re-hashed; the >threshold receipt-bound mode is
    explicit policy and still rejects modified files via the mtime guard."""
    from research_store.importers import time_evidence as te

    db = _make_capture(tmp_path, _COARSE_END)
    sha = hashlib.sha256(db.read_bytes()).hexdigest()
    profile = LabelProfile(_evidence(db, capture_sha256=sha), interval_minutes=1)
    _attach_receipt(db)

    # default mode for a small capture: full sha256 rehash
    verified = verify_profile_capture(db, profile)
    assert verified["identity_mode"] == "full_sha256_rehash"

    # >threshold mode: explicit receipt+stat binding (the 10GB capture policy)
    monkeypatch.setattr(te, "_FULL_REHASH_MAX_BYTES", 1)
    verified = verify_profile_capture(db, profile)
    assert verified["identity_mode"] == "receipt_bound_stat"
    assert "identity_note" in verified

    # a file touched AFTER validation is refused even in receipt-bound mode
    import os

    os.utime(db, ns=(db.stat().st_atime_ns, db.stat().st_mtime_ns + 2_000_000_000))
    with pytest.raises(LabelEvidenceError, match="modified after validation"):
        verify_profile_capture(db, profile)

