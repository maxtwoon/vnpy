"""Tests for the delivery helper (tools/delivery_inventory_capture.py).

All tests use synthetic inputs in tmp_path — no purchased bulk data, no
network, no D:/quant-data, no real source roots. The real 10.22GB capture is
exercised by the task run itself, not by unit tests.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sqlite3
import tarfile
from pathlib import Path

import zstandard

from research_store.importers.sqlite_source import (
    SIMNOW_INCIDENT_KEYS,
    build_table_plan,
    simnow_quarantine_keys,
)
from tools.delivery_inventory_capture import (
    _DB_HEADER_BYTES,
    _find_reusable_capture,
    _sha256_pair_with_progress,
    _utcnow,
    cmd_inspect,
    cmd_verify_capture,
)


def _make_ssquant_like_db(path: Path) -> None:
    """Small synthetic DB shaped like the SSQuant source (naming + meta)."""
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE a888_1M_raw (datetime TEXT PRIMARY KEY, symbol TEXT,"
        " real_symbol TEXT, open REAL, high REAL, low REAL, close REAL,"
        " volume REAL, amount REAL)"
    )
    con.execute(
        "CREATE TABLE ma2605_1M_raw (datetime TEXT PRIMARY KEY, symbol TEXT,"
        " real_symbol TEXT, open REAL, high REAL, low REAL, close REAL,"
        " volume REAL, amount REAL, openint REAL, cumulative_openint REAL)"
    )
    con.execute(
        "CREATE TABLE ma888_1M_raw (datetime TEXT PRIMARY KEY, symbol TEXT,"
        " real_symbol TEXT, open REAL, high REAL, low REAL, close REAL,"
        " volume REAL, amount REAL, openint REAL, cumulative_openint REAL)"
    )
    con.execute(
        "CREATE TABLE rb777_5M_raw (datetime TEXT PRIMARY KEY, symbol TEXT,"
        " real_symbol TEXT, open REAL, high REAL, low REAL, close REAL,"
        " volume REAL, amount REAL)"
    )
    con.execute(
        "CREATE TABLE rb2605_1M_raw_staging (datetime TEXT, symbol TEXT,"
        " volume REAL)"
    )
    con.execute(
        "CREATE TABLE simnow_bar_meta (datetime TEXT, symbol TEXT, source TEXT)"
    )
    # Vendor continuous rows in meta: one contaminated (exact incident key),
    # one ordinary healthy overlap (never quarantined).
    con.execute(
        "INSERT INTO a888_1M_raw VALUES ('2026-07-01 11:29:00','A888',NULL,"
        " 0,0,0,0,0,0)"
    )
    con.execute(
        "INSERT INTO a888_1M_raw VALUES ('2026-07-01 15:04:00','A888','A2609',"
        " 3500,3510,3490,3505,120,420000)"
    )
    # Real-contract rows (classification only; ma2605 is the historical plan
    # name that does not exist on the real capture).
    con.execute(
        "INSERT INTO ma2605_1M_raw VALUES ('2026-06-01 09:01:00','ma2605',"
        " 'ma2605', 2400,2410,2390,2405, 100, 500000, 5, 5000)"
    )
    # Vendor continuous MA rows: the bounded raw-amount sample table
    # (discovered as continuous_888). Row 1 VWAP outside OHLC (high side),
    # row 2 VWAP outside OHLC (low side) and negative openint.
    con.execute(
        "INSERT INTO ma888_1M_raw VALUES ('2026-06-01 09:01:00','MA888',"
        " 'ma609', 2400,2410,2390,2405, 100, 500000, 5, 5000)"
    )
    con.execute(
        "INSERT INTO ma888_1M_raw VALUES ('2026-06-01 09:02:00','MA888',"
        " 'ma609', 2400,2410,2390,2405, 100, 100000, -1, 4999)"
    )
    con.execute(
        "INSERT INTO rb2605_1M_raw_staging VALUES ('2026-07-01 11:30:00',"
        " 'RB888', 2)"
    )
    con.execute(
        "INSERT INTO simnow_bar_meta VALUES "
        "('2026-07-01 11:29:00','A888','simnow')"
    )
    con.execute(
        "INSERT INTO simnow_bar_meta VALUES "
        "('2026-07-01 15:04:00','A888','simnow')"
    )
    con.commit()
    con.close()


def test_build_table_plan_classification(tmp_path: Path) -> None:
    db = tmp_path / "kline_data.db"
    _make_ssquant_like_db(db)
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        plan = build_table_plan(con)
        by_table = {p.table: p for p in plan}
        assert by_table["a888_1M_raw"].series_kind == "continuous_888"
        assert by_table["a888_1M_raw"].frequency == "1M"
        assert by_table["ma2605_1M_raw"].series_kind == "real_contract"
        assert by_table["ma2605_1M_raw"].product == "ma"
        assert by_table["rb777_5M_raw"].series_kind == "continuous_777"
        assert by_table["rb2605_1M_raw_staging"].series_kind == "staging"
        assert "simnow_bar_meta" not in by_table
    finally:
        con.close()


def test_simnow_quarantine_exact_rule(tmp_path: Path) -> None:
    """Only meta keys with the incident signature (NULL real_symbol, zero
    volume/amount) are quarantined; ordinary overlaps are not."""
    db = tmp_path / "kline_data.db"
    _make_ssquant_like_db(db)
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        keys = simnow_quarantine_keys(con)
        assert keys == {("a888_1M_raw", "A888", "2026-07-01 11:29:00")}
        assert ("A888", "2026-07-01 11:29:00") in SIMNOW_INCIDENT_KEYS
    finally:
        con.close()


def test_find_reusable_capture(tmp_path: Path) -> None:
    captures = tmp_path / "captures"
    captures.mkdir()
    assert _find_reusable_capture(captures, source_size=5) is None

    good = captures / "kline_data_capture_20260916T000000Z.db"
    good.write_bytes(b"x" * 5)
    receipt = {
        "source_size": 5,
        "quick_check": "ok",
        "sha256": hashlib.sha256(b"x" * 5).hexdigest(),
        "bytes": 5,
    }
    good.with_suffix(good.suffix + ".receipt.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    assert _find_reusable_capture(captures, source_size=5) == good
    # Different source size must not reuse.
    assert _find_reusable_capture(captures, source_size=6) is None
    # Tampered capture (size mismatch vs receipt) must not reuse.
    good.write_bytes(b"x" * 4)
    assert _find_reusable_capture(captures, source_size=5) is None


def test_utcnow_is_utc_iso() -> None:
    stamp = _utcnow()
    assert stamp.endswith("+00:00")
    assert "T" in stamp


def _write_tar_zst(path: Path, members: dict[str, bytes]) -> str:
    buf = io.BytesIO()
    with tarfile.open(mode="w", fileobj=buf) as tf:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
    compressed = zstandard.ZstdCompressor().compress(buf.getvalue())
    path.write_bytes(compressed)
    return hashlib.sha256(compressed).hexdigest()


def test_enumerate_archive_members_metadata_only(tmp_path: Path) -> None:
    from tools.delivery_inventory_capture import _enumerate_archive_members

    archive = tmp_path / "rqdatac_contract_1m_none_2025.tar.zst"
    digest = _write_tar_zst(
        archive,
        {
            "2025/unit_0000.parquet": b"PAR0",
            "2025/unit_0000.json": b"{}",
            "2025/unit_0001.parquet": b"PAR1",
        },
    )
    result = _enumerate_archive_members(archive)
    assert result["member_count"] == 3
    assert result["archive_sha256"] == digest
    # The synthetic archive name matches a real expected-member mapping, so
    # the expected parquet member IS hashed (streaming, content-verified).
    assert result["parquet_member_sha256"] == hashlib.sha256(b"PAR0").hexdigest()
    assert result["member_uncompressed_bytes"] == len(b"PAR0") + 2 + len(b"PAR1")


# ---------------------------------------------------------------------------
# verify-capture (capture04H recovery path)
# ---------------------------------------------------------------------------


def _run_verify(
    tmp_path: Path, source_db: Path, capture_db: Path
) -> tuple[object, Path]:
    report_dir = tmp_path / "reports"
    args = type("Args", (), {})()
    args.capture = str(capture_db)
    args.report_dir = str(report_dir)
    result = cmd_verify_capture(args)
    return result, report_dir


def test_verify_capture_validates_candidate_and_writes_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    """A byte-identical, quick_check-ok candidate gets a receipt compatible
    with _find_reusable_capture, with measured provenance fields."""
    source_db = tmp_path / "kline_data.db"
    _make_ssquant_like_db(source_db)
    captures = tmp_path / "captures"
    captures.mkdir()
    capture_db = captures / "kline_data_capture_20260101T000000Z.db"
    shutil.copyfile(source_db, capture_db)
    # The verify flow derives provenance facts from SSQUANT_DB; point it at
    # the synthetic source so no real path is touched.
    monkeypatch.setattr(
        "tools.delivery_inventory_capture.SSQUANT_DB", source_db
    )
    result, report_dir = _run_verify(tmp_path, source_db, capture_db)
    assert result["validated"] is True
    assert result["validation_kind"] == "current_recovery_validation"
    assert result["remainder_from_header_match"] is True
    assert result["header_approved"] is True
    assert result["header_diff_offsets"] == []  # plain copy: identical header
    receipt = json.loads(
        capture_db.with_suffix(capture_db.suffix + ".receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["quick_check"] == "ok"
    assert receipt["bytes"] == capture_db.stat().st_size
    assert receipt["source_size"] == source_db.stat().st_size
    assert receipt["capture_remainder_sha256_from_header"] == (
        receipt["source_remainder_sha256_from_header"]
    )
    assert receipt["validation"]["origin"] == (
        "recovered_interrupted_delivery04a_backup"
    )
    # CURRENT RECOVERY VALIDATION: no historical completion is invented.
    assert receipt["captured_at"] is None
    assert receipt["captured_at_basis"].startswith("UNKNOWN")
    assert receipt["validation"]["historical_completion"].startswith("UNKNOWN")
    assert receipt["validated_at"].startswith("20")
    # Receipt is discoverable by the reuse path.
    found = _find_reusable_capture(captures, source_db.stat().st_size)
    assert found == capture_db
    # Stage evidence + failure evidence status is coherent.
    stage = json.loads(
        (report_dir / "delivery04h-verify-capture-stage.json").read_text(
            encoding="utf-8"
        )
    )
    assert stage["status"] == "validated"
    assert [s["stage"] for s in stage["stages"]] == [
        "stats",
        "hash_capture",
        "quick_check",
        "hash_source",
        "verdict",
    ]
    assert not (report_dir / "delivery04h-verify-capture-FAILURE.json").exists()


def test_verify_capture_preserves_candidate_on_hash_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    """A candidate that differs from the source must NOT get a receipt and
    must be preserved byte-for-byte."""
    source_db = tmp_path / "kline_data.db"
    _make_ssquant_like_db(source_db)
    captures = tmp_path / "captures"
    captures.mkdir()
    capture_db = captures / "kline_data_capture_20260101T000000Z.db"
    shutil.copyfile(source_db, capture_db)
    # Corrupt one byte in the middle without changing the size.
    raw = bytearray(capture_db.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    capture_db.write_bytes(bytes(raw))
    before = capture_db.read_bytes()
    monkeypatch.setattr(
        "tools.delivery_inventory_capture.SSQUANT_DB", source_db
    )
    try:
        _run_verify(tmp_path, source_db, capture_db)
        raised = False
    except SystemExit as exc:
        raised = True
        assert "validation failed" in str(exc)
    assert raised
    assert capture_db.read_bytes() == before  # preserved untouched
    assert not capture_db.with_suffix(
        capture_db.suffix + ".receipt.json"
    ).exists()
    failure = json.loads(
        (tmp_path / "reports" / "delivery04h-verify-capture-FAILURE.json")
        .read_text(encoding="utf-8")
    )
    assert failure["validated"] is False
    verdict = next(s for s in failure["stages"] if s["stage"] == "verdict")
    assert verdict["remainder_from_header_match"] is False
    assert verdict["quick_check_ok"] is True


def test_verify_capture_fails_fast_on_size_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    source_db = tmp_path / "kline_data.db"
    _make_ssquant_like_db(source_db)
    captures = tmp_path / "captures"
    captures.mkdir()
    capture_db = captures / "kline_data_capture_20260101T000000Z.db"
    shutil.copyfile(source_db, capture_db)
    capture_db.write_bytes(capture_db.read_bytes()[:-16])  # truncated copy
    monkeypatch.setattr(
        "tools.delivery_inventory_capture.SSQUANT_DB", source_db
    )
    try:
        _run_verify(tmp_path, source_db, capture_db)
        raised = False
    except SystemExit as exc:
        raised = True
        assert "size" in str(exc)
    assert raised
    failure = json.loads(
        (tmp_path / "reports" / "delivery04h-verify-capture-FAILURE.json")
        .read_text(encoding="utf-8")
    )
    assert failure["validated"] is False
    # Only the stats stage ran — no wasted hashing of an incomplete copy.
    stage = json.loads(
        (tmp_path / "reports" / "delivery04h-verify-capture-stage.json")
        .read_text(encoding="utf-8")
    )
    assert [s["stage"] for s in stage["stages"]] == ["stats"]


def test_sha256_pair_with_progress_matches_hashlib(tmp_path: Path) -> None:
    payload = b"z" * (1024 * 1024 * 3 + 17)
    path = tmp_path / "blob.bin"
    path.write_bytes(payload)
    lines: list[str] = []
    full, remainder, elapsed = _sha256_pair_with_progress(path, lines.append, "test")
    assert full == hashlib.sha256(payload).hexdigest()
    # Remainder excludes only the 100-byte DB header.
    assert remainder == hashlib.sha256(payload[_DB_HEADER_BYTES:]).hexdigest()
    assert elapsed >= 0.0
    assert lines and lines[-1].startswith("hash test: complete ")


def test_verify_capture_accepts_backup_header_rewrites(
    tmp_path: Path, monkeypatch
) -> None:
    """A candidate identical to the source except for the exact fields the
    SQLite online backup API rewrites (file change counter 24-27, schema
    cookie 40-43, version-valid-for 92-95) validates as a true backup, with
    the differing offsets recorded in the receipt."""
    source_db = tmp_path / "kline_data.db"
    _make_ssquant_like_db(source_db)
    captures = tmp_path / "captures"
    captures.mkdir()
    capture_db = captures / "kline_data_capture_20260101T000000Z.db"
    raw = bytearray(source_db.read_bytes())
    # Simulate what SQLite's backup API does: bump change counter, schema
    # cookie and version-valid-for (big-endian u32 fields).
    raw[24:28] = (int.from_bytes(raw[24:28], "big") + 1).to_bytes(4, "big")
    raw[40:44] = (int.from_bytes(raw[40:44], "big") + 1).to_bytes(4, "big")
    raw[92:96] = (int.from_bytes(raw[92:96], "big") + 1).to_bytes(4, "big")
    capture_db.write_bytes(bytes(raw))
    monkeypatch.setattr(
        "tools.delivery_inventory_capture.SSQUANT_DB", source_db
    )
    result, _report_dir = _run_verify(tmp_path, source_db, capture_db)
    assert result["validated"] is True
    assert result["header_approved"] is True
    assert result["remainder_from_header_match"] is True
    # Small counters: only the low-order big-endian bytes changed, all
    # within the three approved backup-rewrite fields.
    assert result["header_diff_offsets"] == [27, 43, 95]
    receipt = json.loads(
        capture_db.with_suffix(capture_db.suffix + ".receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["header_field_comparison"]["approved"] is True
    assert receipt["header_field_comparison"]["unapproved_diff_fields"] == []
    # Full-file hashes differ (by design); the receipt records both honestly.
    assert receipt["sha256"] != receipt["source_sha256"]


def test_verify_capture_rejects_unexpected_header_change(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression: an unexpected SEMANTIC header difference (page size)
    must fail validation even though the bytes beyond the header hash
    identically. The blanket 100-byte exclusion would wrongly accept this;
    the per-field allowlist must reject it."""
    source_db = tmp_path / "kline_data.db"
    _make_ssquant_like_db(source_db)
    captures = tmp_path / "captures"
    captures.mkdir()
    capture_db = captures / "kline_data_capture_20260101T000000Z.db"
    raw = bytearray(source_db.read_bytes())
    # Claim a different page size in the header (offsets 16-17, big-endian)
    # without touching any data page: a pure semantic lie.
    raw[16:18] = (8192).to_bytes(2, "big")
    capture_db.write_bytes(bytes(raw))
    before = capture_db.read_bytes()
    monkeypatch.setattr(
        "tools.delivery_inventory_capture.SSQUANT_DB", source_db
    )
    try:
        _run_verify(tmp_path, source_db, capture_db)
        raised = False
    except SystemExit as exc:
        raised = True
        assert "validation failed" in str(exc)
    assert raised
    assert capture_db.read_bytes() == before  # preserved untouched
    assert not capture_db.with_suffix(
        capture_db.suffix + ".receipt.json"
    ).exists()
    failure = json.loads(
        (tmp_path / "reports" / "delivery04h-verify-capture-FAILURE.json")
        .read_text(encoding="utf-8")
    )
    verdict = next(s for s in failure["stages"] if s["stage"] == "verdict")
    assert verdict["remainder_from_header_match"] is True  # data pages match
    assert verdict["header_approved"] is False
    assert verdict["header_unapproved_diff_fields"] == ["page_size"]
    assert verdict["header_diff_offsets"] == [16]
    assert failure["validated"] is False


def test_verify_capture_rejects_semantic_field_lie_in_encoding(
    tmp_path: Path, monkeypatch
) -> None:
    """Second semantic-header regression: a changed text-encoding field
    (offsets 56-59) is rejected even though all data pages are identical."""
    source_db = tmp_path / "kline_data.db"
    _make_ssquant_like_db(source_db)
    captures = tmp_path / "captures"
    captures.mkdir()
    capture_db = captures / "kline_data_capture_20260101T000000Z.db"
    raw = bytearray(source_db.read_bytes())
    raw[56:60] = (2).to_bytes(4, "big")  # claim UTF-16le instead of UTF-8
    capture_db.write_bytes(bytes(raw))
    monkeypatch.setattr(
        "tools.delivery_inventory_capture.SSQUANT_DB", source_db
    )
    try:
        _run_verify(tmp_path, source_db, capture_db)
        raised = False
    except SystemExit:
        raised = True
    assert raised
    failure = json.loads(
        (tmp_path / "reports" / "delivery04h-verify-capture-FAILURE.json")
        .read_text(encoding="utf-8")
    )
    verdict = next(s for s in failure["stages"] if s["stage"] == "verdict")
    assert verdict["header_unapproved_diff_fields"] == ["text_encoding"]


def test_attempt1_quick_check_reuse_binding(tmp_path: Path) -> None:
    """The attempt-1 quick_check result is reusable ONLY when bound to the
    unchanged candidate whole-file SHA256 and stable sidecar state."""
    from tools.delivery_inventory_capture import (
        _attempt1_quick_check_reuse,
    )

    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    evidence = {
        "stages": [
            {
                "stage": "hash_capture",
                "sha256": "a" * 64,
            },
            {
                "stage": "quick_check",
                "quick_check": "ok",
                "finished_at": "2026-09-17T01:16:21+00:00",
                "capture_journal_mode": "wal",
            },
            {
                "stage": "stats",
                "capture_sidecars": {"-wal": {"size_bytes": 0}, "-shm": {"size_bytes": 32768}},
            },
        ]
    }
    (report_dir / "delivery04h-verify-capture-stage-attempt1-mismatch.json").write_text(
        json.dumps(evidence), encoding="utf-8"
    )
    sidecars = {"-wal": {"size_bytes": 0}, "-shm": {"size_bytes": 32768}}
    reuse = _attempt1_quick_check_reuse(report_dir, "a" * 64, sidecars)
    assert reuse is not None
    assert reuse["quick_check"] == "ok"
    assert reuse["attempt1_completed_at"] == "2026-09-17T01:16:21+00:00"

    # Different candidate content: binding MUST fail -> fresh scan required.
    assert _attempt1_quick_check_reuse(report_dir, "b" * 64, sidecars) is None
    # Non-zero capture WAL: sidecar state diverged -> fresh scan required.
    dirty = {"-wal": {"size_bytes": 4096}, "-shm": {"size_bytes": 32768}}
    assert _attempt1_quick_check_reuse(report_dir, "a" * 64, dirty) is None
    # Changed -shm size: sidecar state diverged -> fresh scan required.
    shm_changed = {"-wal": {"size_bytes": 0}, "-shm": {"size_bytes": 65536}}
    assert _attempt1_quick_check_reuse(report_dir, "a" * 64, shm_changed) is None
    # Missing attempt-1 evidence file: fresh scan required.
    assert _attempt1_quick_check_reuse(
        tmp_path / "empty", "a" * 64, sidecars
    ) is None
    # quick_check not ok in evidence: never reusable.
    evidence["stages"][1]["quick_check"] = "corrupt"
    (report_dir / "delivery04h-verify-capture-stage-attempt1-mismatch.json").write_text(
        json.dumps(evidence), encoding="utf-8"
    )
    assert _attempt1_quick_check_reuse(report_dir, "a" * 64, sidecars) is None


# ---------------------------------------------------------------------------
# bounded inspect
# ---------------------------------------------------------------------------


def test_inspect_bounded_scope(tmp_path: Path) -> None:
    db = tmp_path / "kline_data.db"
    _make_ssquant_like_db(db)
    report_dir = tmp_path / "reports"
    args = type("Args", (), {})()
    args.capture = str(db)
    args.report_dir = str(report_dir)
    payload = cmd_inspect(args)

    classification = payload["classification"]
    assert classification["tables_total"] == 5
    assert classification["by_series_kind"] == {
        "continuous_888": 2,
        "real_contract": 1,
        "continuous_777": 1,
        "staging": 1,
    }
    assert classification["by_frequency"] == {"1M": 4, "5M": 1}

    simnow = payload["simnow"]
    assert simnow["quarantine_keys_detected"] == ["A888 2026-07-01 11:29:00"]
    assert simnow["quarantine_matches_authoritative"] is False  # synthetic db
    assert simnow["meta_rows_exact"] == 2
    assert simnow["overlap_diagnostics"]["meta_main_1m_overlap_keys"] == 2

    ma = payload["ma_raw_amount_sample"]
    # The sample table is DISCOVERED: continuous_888 preferred, so ma888
    # (not the historical plan name ma2605) is used, with an explicit note.
    assert ma["table"] == "ma888_1M_raw"
    assert "does not exist" in ma["planned_table_absent_note"]
    assert ma["table_rows_total"] == 2
    assert ma["sample_rows"] == 2
    # Row 1: vwap 500000/100 = 5000 > high 2410 -> outside OHLC.
    # Row 2: vwap 100000/100 = 1000 < low 2390 -> outside OHLC.
    assert ma["vwap_checked_rows"] == 2
    assert ma["vwap_outside_ohlc_rows"] == 2
    assert ma["cumulative_openint_negative_rows_in_sample"] == 0
    assert ma["openint_negative_rows_in_sample"] == 1
    assert ma["cumulative_openint_sample_values"] == [5000.0, 4999.0]
    assert ma["real_symbol_null_rows_in_sample"] == 0

    real_symbol = payload["continuous_real_symbol_sample"]
    assert real_symbol["sample_rows"] == 2
    assert real_symbol["null_real_symbol_rows"] == 1
    assert real_symbol["distinct_real_symbol_sample"] == ["A2609"]

    counts = payload["scoped_row_counts"]
    assert counts["staging_tables_exact"] == {"rb2605_1M_raw_staging": 1}
    assert counts["locator_tables_capped"]["ma888_1M_raw"]["row_count"] == 2
    assert counts["locator_tables_capped"]["ma888_1M_raw"]["exact"] is True

    locator = payload["locator_tables"]["ma888_1M_raw"]
    assert locator["time_span_first"] == "2026-06-01 09:01:00"
    assert locator["time_span_last"] == "2026-06-01 09:02:00"
    assert any("sqlite_autoindex" in name for name in locator["indexes"])

    # Original source columns are preserved verbatim per series kind.
    real_columns = [c[0] for c in payload["columns_by_kind"]["real_contract"]]
    assert real_columns[0] == "datetime"
    assert "cumulative_openint" in real_columns
    assert "openint" in real_columns
