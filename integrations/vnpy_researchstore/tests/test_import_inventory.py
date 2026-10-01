from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research_store.importers.inventory import (
    classify_file,
    scan_directory,
    scan_rq_package,
)


def test_classify_file() -> None:
    assert classify_file("rqdatac_etf_lof_1m_2016.tar.zst") == "archive_tar_zst"
    assert classify_file("all_a_daily_2025.csv.gz") == "gzip_csv"
    assert classify_file("kline_data.db") == "sqlite_db"
    assert classify_file("universe.json") == "json"
    assert classify_file("x.tar.zst.sha256") == "sha256_sidecar"
    assert classify_file("update.py") == "script_executable"


def _make_package(tmp_path: Path, *, corrupt: bool = False) -> Path:
    package = tmp_path / "pkg"
    package.mkdir()
    original = b"dummy-tar-content-2011"
    payload = original + (b"tampered" if corrupt else b"")
    archive = package / "rqdatac_etf_lof_1d_2011.tar.zst"
    archive.write_bytes(payload)
    digest = hashlib.sha256(original).hexdigest()
    (package / "rqdatac_etf_lof_1d_2011.tar.zst.sha256").write_text(
        f"{digest}  rqdatac_etf_lof_1d_2011.tar.zst\n", encoding="utf-8"
    )
    manifest = {
        "start_date": "2011-08-02",
        "end_date": "2026-07-31",
        "adjust_type": "none",
        "archives": [
            {
                "file": "rqdatac_etf_lof_1d_2011.tar.zst",
                "bytes": len(payload),
                "sha256": digest,
            },
            {
                "file": "rqdatac_etf_lof_1d_2012.tar.zst",
                "bytes": 5,
                "sha256": "0" * 64,
            },
        ],
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return package


def test_scan_rq_package_ok(tmp_path: Path) -> None:
    package = _make_package(tmp_path)
    inventory = scan_rq_package(package, verify_hashes=True)
    summary = inventory.summary()
    assert summary["archives_listed"] == 2
    assert summary["archives_missing"] == 1
    assert summary["hash_failures"] == []
    assert summary["verified_hashes"] == 1
    assert summary["adjust_type"] == "none"


def test_scan_rq_package_detects_hash_failure(tmp_path: Path) -> None:
    package = _make_package(tmp_path, corrupt=True)
    inventory = scan_rq_package(package, verify_hashes=True)
    assert inventory.hash_failures == ["rqdatac_etf_lof_1d_2011.tar.zst"]


def test_scan_rq_package_version_conflict_caveat(tmp_path: Path) -> None:
    package = _make_package(tmp_path)
    # sidecar claims a different (older) digest than the manifest lists
    sidecar = package / "rqdatac_etf_lof_1d_2011.tar.zst.sha256"
    sidecar.write_text(
        hashlib.sha256(b"different-content").hexdigest() + "  x\n", encoding="utf-8"
    )
    inventory = scan_rq_package(package, verify_hashes=False)
    assert any("version conflict" in caveat for caveat in inventory.caveats)


def test_scan_directory_classification_and_sidecars(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "rqdata").mkdir(parents=True)
    (root / "rqdata" / "a.tar.zst").write_bytes(b"12345")
    (root / "rqdata" / "a.tar.zst.sha256").write_text(
        hashlib.sha256(b"12345").hexdigest() + "  a.tar.zst\n", encoding="utf-8"
    )
    (root / "notes.log").write_text("x", encoding="utf-8")
    (root / "bad.sha256").write_text("nothex", encoding="utf-8")
    report = scan_directory(root)
    kinds = {entry.path: entry.kind for entry in report.files}
    assert kinds["rqdata/a.tar.zst"] == "archive_tar_zst"
    assert kinds["notes.log"] == "log"
    entry = next(e for e in report.files if e.path.endswith("a.tar.zst"))
    assert entry.sidecar_status == "present_unverified"
    bad = next(e for e in report.files if e.path == "bad.sha256")
    assert bad.sidecar_status == "absent"
    assert report.summary()["file_count"] == 4


# Structural copy of the real failed-record element in
# D:/BaiduNetdiskDownload/全息日线/rqdata/rqdatac_a_share_pit_events_full_history_20260804/manifest.json
# (archives[96]): a LIST of failed fetch records, not an archive descriptor.
REAL_FAILED_RECORD_SHAPE = [
    {
        "kind": "failed",
        "worker": 4,
        "dataset": "stk_performance_letters",
        "year": 2017,
        "error": "stk_performance_letters 2017 batch 0: permission denied: get_announcement_v2",
    }
]


def _make_package_with_failed_records(tmp_path: Path) -> Path:
    """Package whose manifest embeds the real failed-record list shape plus
    valid and missing archive descriptors — the exact structure that used to
    abort ``scan_source_roots`` with ``TypeError``."""
    package = tmp_path / "pkg_pit"
    package.mkdir()
    original = b"dummy-pit-content-2016"
    archive = package / "rqdatac_pit_events_2016.tar.zst"
    archive.write_bytes(original)
    digest = hashlib.sha256(original).hexdigest()
    manifest = {
        "start_date": "2016-01-01",
        "end_date": "2026-06-30",
        "adjust_type": "none",
        "archives": [
            {
                "file": "rqdatac_pit_events_2016.tar.zst",
                "bytes": len(original),
                "sha256": digest,
            },
            REAL_FAILED_RECORD_SHAPE,  # list element: failed fetch records
            {
                "file": "rqdatac_pit_events_2017.tar.zst",
                "bytes": 5,
                "sha256": "0" * 64,
            },
        ],
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return package


def test_scan_rq_package_handles_real_failed_record_shape(tmp_path: Path) -> None:
    """Regression for the actual 04A blocker: a list-of-failed-records element
    must be preserved as structured failed records, valid archives must still
    be verified, and counts must reconcile."""
    package = _make_package_with_failed_records(tmp_path)
    inventory = scan_rq_package(package, verify_hashes=True)
    summary = inventory.summary()
    # valid archive descriptor still processed and hash-verified
    assert summary["archives_listed"] == 2
    assert summary["verified_hashes"] == 1
    assert summary["archives_missing"] == 1
    assert summary["hash_failures"] == []
    # failed record preserved with dataset/year/error visible, not discarded
    assert summary["failed_records"] == 1
    assert summary["unrecognized_records"] == 0
    (failed,) = inventory.failed_records
    assert failed["dataset"] == "stk_performance_letters"
    assert failed["year"] == 2017
    assert "permission denied" in (failed["error"] or "")
    assert failed["kind"] == "failed"
    assert any("stk_performance_letters" in c and "2017" in c for c in inventory.caveats)


def test_scan_rq_package_preserves_failed_record_and_continues(tmp_path: Path) -> None:
    """The failed record must not prevent later archive descriptors from being
    inventoried (the 2017 descriptor comes AFTER the failed element)."""
    package = _make_package_with_failed_records(tmp_path)
    inventory = scan_rq_package(package, verify_hashes=False)
    listed = [record["file"] for record in inventory.archives]
    assert listed == [
        "rqdatac_pit_events_2016.tar.zst",
        "rqdatac_pit_events_2017.tar.zst",
    ]
    assert inventory.missing_archives == ["rqdatac_pit_events_2017.tar.zst"]


def test_scan_rq_package_unrecognized_entries_stay_visible(tmp_path: Path) -> None:
    """Non-dict, non-list archives entries are preserved, not dropped and not
    promoted to archives."""
    package = tmp_path / "pkg_weird"
    package.mkdir()
    manifest = {
        "archives": [
            "just-a-string-entry",
            42,
            {"no_file_key": True},
            {"file": ""},
        ],
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    inventory = scan_rq_package(package, verify_hashes=False)
    summary = inventory.summary()
    assert summary["archives_listed"] == 0
    assert summary["unrecognized_records"] == 4
    assert len(inventory.unrecognized_records) == 4
    assert summary["failed_records"] == 0


def test_scan_rq_package_refuses_path_escape(tmp_path: Path) -> None:
    """An archive descriptor whose file path escapes the package root is
    refused (never hashed), recorded with a caveat and a per-record marker."""
    package = tmp_path / "pkg_escape"
    package.mkdir()
    manifest = {
        "archives": [
            {"file": "../outside.tar.zst", "bytes": 1, "sha256": "0" * 64},
        ],
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    inventory = scan_rq_package(package, verify_hashes=True)
    summary = inventory.summary()
    assert summary["archives_listed"] == 1
    assert summary["archives_missing"] == 1
    assert summary["verified_hashes"] == 0
    assert inventory.archives[0]["path_refused"] is True
    assert any("escapes package root" in c for c in inventory.caveats)


# --- F1 regressions: nested dataset layout, ambiguity, dataset traversal ---


def _write_manifest(package: Path, archives: list) -> None:
    (package / "manifest.json").write_text(
        json.dumps({"archives": archives}), encoding="utf-8"
    )


def test_scan_rq_package_resolves_nested_dataset_layout(tmp_path: Path) -> None:
    """Real RQ layout: manifest entries carry ``dataset`` and archives live at
    ``<package>/<dataset>/<file>``. The resolver must find them there (this is
    the exact shape the 04C review proved we falsely reported missing)."""
    package = tmp_path / "pkg_nested"
    (package / "basis_1d").mkdir(parents=True)
    payload = b"nested-basis-2010"
    (package / "basis_1d" / "rqdatac_basis_1d_2010.tar.zst").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    _write_manifest(
        package,
        [
            {
                "dataset": "basis_1d",
                "file": "rqdatac_basis_1d_2010.tar.zst",
                "bytes": len(payload),
                "sha256": digest,
            },
        ],
    )
    inventory = scan_rq_package(package, verify_hashes=True)
    summary = inventory.summary()
    assert summary["archives_listed"] == 1
    assert summary["archives_missing"] == 0
    assert summary["verified_hashes"] == 1
    assert summary["hash_failures"] == []
    (record,) = inventory.archives
    assert record["resolved_path"] == "basis_1d/rqdatac_basis_1d_2010.tar.zst"
    assert record["bytes_actual"] == len(payload)


def test_scan_rq_package_preserves_flat_layout(tmp_path: Path) -> None:
    """Flat-layout packages (7 of 9 real ones) must keep working: no dataset
    dir, archive directly at package root."""
    package = tmp_path / "pkg_flat"
    package.mkdir()
    payload = b"flat-etf-2011"
    (package / "rqdatac_etf_lof_1d_2011.tar.zst").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    _write_manifest(
        package,
        [
            {
                "file": "rqdatac_etf_lof_1d_2011.tar.zst",
                "bytes": len(payload),
                "sha256": digest,
            },
        ],
    )
    inventory = scan_rq_package(package, verify_hashes=True)
    summary = inventory.summary()
    assert summary["archives_listed"] == 1
    assert summary["archives_missing"] == 0
    assert summary["verified_hashes"] == 1
    (record,) = inventory.archives
    assert record["resolved_path"] == "rqdatac_etf_lof_1d_2011.tar.zst"


def test_scan_rq_package_nested_missing_is_truthful(tmp_path: Path) -> None:
    """A descriptor whose dataset dir does not exist (the real PIT ``shares``
    case) stays a truthful missing — nested fallback to flat finds nothing."""
    package = tmp_path / "pkg_nested_missing"
    package.mkdir()
    _write_manifest(
        package,
        [
            {
                "dataset": "shares",
                "file": "rqdatac_shares_1990.tar.zst",
                "bytes": 5,
                "sha256": "0" * 64,
            },
        ],
    )
    inventory = scan_rq_package(package, verify_hashes=False)
    summary = inventory.summary()
    assert summary["archives_listed"] == 1
    assert summary["archives_missing"] == 1
    assert inventory.archives[0].get("path_refused") is None


def test_scan_rq_package_ambiguous_flat_vs_nested_conflict(tmp_path: Path) -> None:
    """If BOTH the nested and the flat candidate exist with DIFFERENT content,
    the resolver must surface a version-conflict caveat, not silently choose."""
    package = tmp_path / "pkg_ambiguous"
    (package / "basis_1d").mkdir(parents=True)
    (package / "basis_1d" / "rqdatac_basis_1d_2010.tar.zst").write_bytes(
        b"nested-version"
    )
    (package / "rqdatac_basis_1d_2010.tar.zst").write_bytes(b"flat-version")
    _write_manifest(
        package,
        [{"dataset": "basis_1d", "file": "rqdatac_basis_1d_2010.tar.zst"}],
    )
    inventory = scan_rq_package(package, verify_hashes=False)
    summary = inventory.summary()
    assert summary["archives_listed"] == 1
    assert summary["archives_missing"] == 0
    assert any("ambiguous archive location" in c for c in inventory.caveats)
    assert any("version conflict" in c for c in inventory.caveats)


def test_scan_rq_package_refuses_dataset_traversal(tmp_path: Path) -> None:
    """A ``dataset`` value that escapes the package root is refused before any
    candidate path is built — the file value never gets a chance to be read."""
    package = tmp_path / "pkg_dataset_escape"
    package.mkdir()
    _write_manifest(
        package,
        [{"dataset": "../elsewhere", "file": "rqdatac_x_2010.tar.zst"}],
    )
    inventory = scan_rq_package(package, verify_hashes=False)
    summary = inventory.summary()
    assert summary["archives_listed"] == 1
    assert summary["archives_missing"] == 1
    assert inventory.archives[0]["path_refused"] is True
    assert any("dataset name escapes package root" in c for c in inventory.caveats)


def test_scan_rq_package_ignores_historical_absolute_manifest_path(tmp_path: Path) -> None:
    """The manifest ``path`` field names the original build machine
    (e.g. /mnt/tool_aggregator_storage/...). It must never be followed; the
    resolver only looks inside the package root."""
    package = tmp_path / "pkg_abs_path"
    package.mkdir()
    payload = b"real-content"
    (package / "rqdatac_x_2010.tar.zst").write_bytes(payload)
    _write_manifest(
        package,
        [
            {
                "dataset": "basis_1d",
                "file": "rqdatac_x_2010.tar.zst",
                # historical absolute path from the build machine; must be ignored
                "path": "/mnt/tool_aggregator_storage/rqdatac/basis_1d/rqdatac_x_2010.tar.zst",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        ],
    )
    inventory = scan_rq_package(package, verify_hashes=True)
    summary = inventory.summary()
    assert summary["archives_listed"] == 1
    assert summary["archives_missing"] == 0
    assert summary["verified_hashes"] == 1
