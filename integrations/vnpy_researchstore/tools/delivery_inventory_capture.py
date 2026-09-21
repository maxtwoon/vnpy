"""Delivery helper: source inventory + consistent SSQuant capture + bounded inspection.

Task-owned tool for the delivery04 chain (04A helper, recovered/completed by
capture04H). Reuses the public importer/core APIs
(``research_store.importers.inventory`` / ``sqlite_source`` / ``safeio`` and
``research_store.store``) — no duplicated parsers or catalog logic.

Subcommands:

* ``env``           — record interpreter / dependency versions / code hashes /
  disk state into a JSON evidence file.
* ``inventory``     — machine-readable inventory of BOTH complete source roots
  plus catalog-only categories; streaming archive-member enumeration
  (metadata only, no extraction) for the named candidate archives.
* ``capture``       — consistent read-only SQLite backup of the SSQuant
  ``kline_data.db`` into the store ``captures/`` directory via
  :func:`capture_sqlite` (quick_check + sha256 included). Refuses to
  duplicate an already-valid capture for the same source size when
  ``--reuse`` is given.
* ``verify-capture``— recover an interrupted capture candidate IN PLACE: staged
  ``PRAGMA quick_check`` (mode=ro) + SHA-256(capture) + SHA-256(source) with
  visible progress. Writes the missing receipt ONLY if quick_check is ok and
  the hashes match (byte-identity with the unchanged source). On any failure
  the candidate is preserved untouched and failure evidence is written; run
  ``capture`` afterwards for a single fresh official backup. Never treats
  size/mtime/WAL state/schema probes as success. Never bypasses a live WAL
  (no ``immutable=1``) and never flat-copies source files.
* ``inspect``       — bounded read-only inspection of the CAPTURED database:
  table classification counts, 1/5/15m distinction, exact SimNow 8-key
  quarantine rule, meta/main overlap diagnostics (never quarantine), a
  bounded MA raw-amount VWAP sample, real_symbol / cumulative_openint scoped
  observations, per-class source columns and scoped time-range locators. No
  arbitrary full-table scans: row counts are exact only for explicitly
  scoped tables and capped elsewhere.

All outputs are JSON under ``D:/quant-data/reports/delivery04h/`` by default.
Nothing here imports, publishes, freezes, or mutates any source or store data
beyond the capture file itself and the receipt sidecar this tool owns.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import sys
import time
import traceback
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_store.importers.inventory import (  # noqa: E402
    HOLO_CAVEATS,
    SSQUANT_CAVEATS,
    scan_directory,
    scan_rq_package,
)
from research_store.importers.inventory import _utcnow_iso as _inv_utcnow_iso  # noqa: E402
from research_store.importers.safeio import (  # noqa: E402
    file_sha256,
    open_tar_zst,
    validate_member,
)
from research_store.importers.sqlite_source import (  # noqa: E402
    SIMNOW_INCIDENT_KEYS,
    build_table_plan,
    capture_sqlite,
    connect_read_only,
    meta_main_overlap_diagnostics,
    simnow_quarantine_keys,
    table_schema,
    table_time_span,
)
from research_store.store import open_store  # noqa: E402

SSQUANT_ROOT = Path("D:/BaiduNetdiskDownload/新数据库/ssquant数据库_20260425")
HOLO_ROOT = Path("D:/BaiduNetdiskDownload/全息日线")
SSQUANT_DB = SSQUANT_ROOT / "kline_data.db"
STORE_ROOT = Path("D:/quant-data")
DEFAULT_REPORT_DIR = STORE_ROOT / "reports" / "delivery04h"
DEFAULT_CAPTURE = (
    STORE_ROOT / "captures" / "kline_data_capture_20260916T164711Z.db"
)

# Code whose hashes pin this run's behaviour (existing product modules reused).
PINNED_CODE_FILES = (
    "research_store/importers/inventory.py",
    "research_store/importers/sqlite_source.py",
    "research_store/importers/safeio.py",
    "research_store/store.py",
    "tools/delivery_inventory_capture.py",
)

# Named candidate archives from .coordination/FUTURES_INPUT_CANDIDATES.md whose
# members are enumerated by streaming (metadata only; the parquet member is
# hashed because later WP10 work formally uses it).
FUTURES_CANDIDATE_ARCHIVES = (
    HOLO_ROOT
    / "rqdata/rqdatac_china_futures_research_full_history_20260804"
    / "contract_1m_none/rqdatac_contract_1m_none_2025.tar.zst",
    HOLO_ROOT
    / "rqdata/rqdatac_china_futures_research_full_history_20260804"
    / "dominant_1m_none/rqdatac_dominant_1m_none_2025.tar.zst",
)

FUTURES_CANDIDATE_EXPECTED = {
    "rqdatac_contract_1m_none_2025.tar.zst": {
        "archive_sha256": "ec4c2aa7ffe401a255e70ef719d60ddead84f55c75bf6ac8514ccaed8c4da862",
        "archive_bytes": 662207309,
        "member": "2025/unit_0000.parquet",
    },
    "rqdatac_dominant_1m_none_2025.tar.zst": {
        "archive_sha256": "f9954338f75257d3d2aa3e364a469a9657615fb051e4a5a45941a10ff1be380d",
        "archive_bytes": 124306799,
        "member": "2025/unit_0000.parquet",
    },
}

# Bounded MA raw-amount sample: one recent calendar month, capped rows. The
# table is DISCOVERED per capture (prefer the vendor continuous series the
# known MA-amount caveat refers to); the historical plan name ma2605_1M_raw
# does not exist on the recovered capture.
MA_SAMPLE_TABLE = "ma2605_1M_raw"
MA_SAMPLE_MONTH_PREFIX = "2026-06"
MA_SAMPLE_ROW_CAP = 20_000

# Bounded row-count cap for scoped representative tables.
SCOPED_COUNT_CAP = 2_000_000
# Bounded sample cap for real_symbol distribution observations.
REAL_SYMBOL_SAMPLE_CAP = 50_000

_HASH_BLOCK = 1024 * 1024
_HASH_PROGRESS_SECONDS = 30.0
# SQLite database header length (https://www.sqlite.org/fileformat2.html).
# Byte-identity for reuse is judged per FIELD, not by blanket exclusion:
# only the fields the official online backup API legitimately rewrites on
# the destination may differ; every other byte must match exactly.
_DB_HEADER_BYTES = 100

# (name, offset, length, policy) — policy "backup_rewrite" fields MAY differ
# (measured on the recovered candidate); "match" fields MUST be identical.
# Offsets per the SQLite file-format spec; all multi-byte fields big-endian.
_DB_HEADER_FIELDS: tuple[tuple[str, int, int, str], ...] = (
    ("magic", 0, 16, "match"),
    ("page_size", 16, 2, "match"),
    ("file_format_write_version", 18, 1, "match"),
    ("file_format_read_version", 19, 1, "match"),
    ("reserved_bytes_per_page", 20, 1, "match"),
    ("max_embedded_payload_fraction", 21, 1, "match"),
    ("min_embedded_payload_fraction", 22, 1, "match"),
    ("leaf_payload_fraction", 23, 1, "match"),
    ("file_change_counter", 24, 4, "backup_rewrite"),
    ("database_size_pages", 28, 4, "match"),
    ("first_freelist_trunk_page", 32, 4, "match"),
    ("freelist_page_count", 36, 4, "match"),
    ("schema_cookie", 40, 4, "backup_rewrite"),
    ("schema_format_number", 44, 4, "match"),
    ("default_page_cache_size", 48, 4, "match"),
    ("largest_root_btree_page", 52, 4, "match"),
    ("text_encoding", 56, 4, "match"),
    ("user_version", 60, 4, "match"),
    ("incremental_vacuum_mode", 64, 4, "match"),
    ("application_id", 68, 4, "match"),
    ("reserved_zero_region", 72, 20, "match"),
    ("version_valid_for", 92, 4, "backup_rewrite"),
    ("sqlite_version_number", 96, 4, "match"),
)

_SQLITE_MAGIC = b"SQLite format 3\x00"

# Attempt-1 quick_check evidence (this task, 2026-09-17T01:16:21Z): its
# result is reusable ONLY when re-bound to the unchanged candidate
# whole-file SHA256 and stable sidecar state, via the persisted stage file.
ATTEMPT1_STAGE_EVIDENCE = "delivery04h-verify-capture-stage-attempt1-mismatch.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _elapsed_since(start: float) -> float:
    return round(time.monotonic() - start, 3)


def _write_json(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def _disk_state(path: Path) -> dict[str, Any]:
    usage = shutil.disk_usage(path.anchor or str(path))
    return {
        "drive": path.anchor or str(path),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "checked_at": _utcnow(),
    }


def _file_stats(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds"),
    }


def _sidecar_stats(db: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db) + suffix)
        out[suffix] = _file_stats(sidecar) if sidecar.exists() else None
    return out


def _sha256_pair_with_progress(
    path: Path, log: Callable[[str], None], label: str
) -> tuple[str, str, float]:
    """Streaming SHA-256 with visible progress, in two digests.

    Returns ``(full_hex, remainder_from_header_hex, elapsed_seconds)``.
    ``remainder_from_header`` excludes the first ``_DB_HEADER_BYTES`` bytes
    of the file — the SQLite database header fields that the official
    online backup API legitimately rewrites on the destination (file change
    counter, schema cookie, version-valid-for). Data-page corruption still
    changes the remainder digest.
    """
    full = hashlib.sha256()
    remainder = hashlib.sha256()
    size = path.stat().st_size
    started = time.monotonic()
    last_mark = started
    done = 0
    skipped = 0
    with path.open("rb") as fh:
        while True:
            block = fh.read(_HASH_BLOCK)
            if not block:
                break
            full.update(block)
            take_from = max(0, _DB_HEADER_BYTES - skipped)
            if len(block) > take_from:
                remainder.update(block[take_from:])
            skipped += len(block)
            done += len(block)
            now = time.monotonic()
            if now - last_mark >= _HASH_PROGRESS_SECONDS:
                elapsed = now - started
                rate = done / max(elapsed, 1e-9) / 1024 / 1024
                log(
                    f"hash {label}: {done}/{size} bytes "
                    f"({done / 1024**3:.1f} GiB) elapsed={elapsed:.0f}s "
                    f"rate={rate:.0f} MiB/s"
                )
                last_mark = now
    elapsed = time.monotonic() - started
    log(
        f"hash {label}: complete {size} bytes "
        f"({size / 1024**3:.2f} GiB) elapsed={elapsed:.1f}s"
    )
    return full.hexdigest(), remainder.hexdigest(), elapsed


def _header_diff_offsets(cap_path: Path, src_path: Path) -> list[int]:
    """Byte offsets that differ within the first ``_DB_HEADER_BYTES``."""
    with cap_path.open("rb") as fc, src_path.open("rb") as fs:
        head_c = fc.read(_DB_HEADER_BYTES)
        head_s = fs.read(_DB_HEADER_BYTES)
    return [i for i in range(min(len(head_c), len(head_s))) if head_c[i] != head_s[i]]


def _header_field_comparison(cap_path: Path, src_path: Path) -> dict[str, Any]:
    """Per-field comparison of the 100-byte SQLite database header.

    Every field is decoded from both files. ``match``-policy fields must be
    byte-identical; only ``backup_rewrite``-policy fields (the exact offsets
    the official online backup API rewrites on the destination: file change
    counter 24-27, schema cookie 40-43, version-valid-for 92-95) MAY differ.
    Any differing byte outside those fields — page size, encoding, schema
    format, page count, magic, reserved bytes, anything — is rejected even
    if the remainder of the file hashes equal.
    """
    with cap_path.open("rb") as fc, src_path.open("rb") as fs:
        head_c = fc.read(_DB_HEADER_BYTES)
        head_s = fs.read(_DB_HEADER_BYTES)

    def decode(head: bytes, offset: int, length: int) -> str:
        raw = head[offset : offset + length]
        if length == 1:
            return str(raw[0])
        return str(int.from_bytes(raw, "big"))

    fields: list[dict[str, Any]] = []
    diff_offsets: list[int] = []
    for name, offset, length, policy in _DB_HEADER_FIELDS:
        equal = head_c[offset : offset + length] == head_s[offset : offset + length]
        field_diffs = [
            offset + i
            for i in range(length)
            if head_c[offset + i] != head_s[offset + i]
        ]
        diff_offsets.extend(field_diffs)
        fields.append(
            {
                "name": name,
                "offset": offset,
                "length": length,
                "policy": policy,
                "capture_value": decode(head_c, offset, length),
                "source_value": decode(head_s, offset, length),
                "equal": equal,
                "allowed_diff": policy == "backup_rewrite",
                "diff_offsets": field_diffs,
            }
        )
    magic_ok = (
        head_c[0:16] == _SQLITE_MAGIC and head_s[0:16] == _SQLITE_MAGIC
    )
    reserved_zero_ok = head_c[72:92] == b"\x00" * 20 and head_s[72:92] == b"\x00" * 20
    unapproved = [
        f
        for f in fields
        if f["policy"] == "match" and not f["equal"]
    ]
    return {
        "fields": fields,
        "diff_offsets": diff_offsets,
        "unapproved_diff_fields": [f["name"] for f in unapproved],
        "unapproved_diff_offsets": [
            off for f in unapproved for off in f["diff_offsets"]
        ],
        "magic_ok": magic_ok,
        "reserved_zero_region_ok": reserved_zero_ok,
        "approved": bool(magic_ok and reserved_zero_ok and not unapproved),
    }


def _attempt1_quick_check_reuse(
    report_dir: Path, capture_full_sha: str, capture_sidecars: dict[str, Any]
) -> dict[str, Any] | None:
    """Bind the attempt-1 completed ``quick_check='ok'`` to unchanged facts.

    Reuse is valid ONLY when the persisted attempt-1 stage evidence shows a
    completed ``ok`` quick_check whose hash_capture SHA256 equals the
    candidate's CURRENT whole-file SHA256, and the candidate sidecar state
    (0-byte ``-wal``, unchanged ``-shm`` size) still matches what the
    attempt-1 scan observed. Otherwise a fresh scan is required.
    """
    path = Path(report_dir) / ATTEMPT1_STAGE_EVIDENCE
    if not path.exists():
        return None
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    hash_stage = next(
        (s for s in evidence.get("stages", []) if s.get("stage") == "hash_capture"),
        None,
    )
    check_stage = next(
        (s for s in evidence.get("stages", []) if s.get("stage") == "quick_check"),
        None,
    )
    stats_stage = next(
        (s for s in evidence.get("stages", []) if s.get("stage") == "stats"),
        None,
    )
    if hash_stage is None or check_stage is None:
        return None
    if check_stage.get("quick_check") != "ok":
        return None
    recorded_sha = hash_stage.get("sha256")
    if not recorded_sha or recorded_sha != capture_full_sha:
        return None
    attempt_sidecars = (stats_stage or {}).get("capture_sidecars") or {}
    attempt_wal = (attempt_sidecars.get("-wal") or {}).get("size_bytes")
    attempt_shm = (attempt_sidecars.get("-shm") or {}).get("size_bytes")
    now_wal = (capture_sidecars.get("-wal") or {}).get("size_bytes")
    now_shm = (capture_sidecars.get("-shm") or {}).get("size_bytes")
    if now_wal not in (0, None) or attempt_wal not in (0, None):
        return None
    if attempt_shm != now_shm:
        return None
    return {
        "basis": (
            "reused_attempt1_bound_to_unchanged_candidate_sha256_and_sidecar_state"
        ),
        "quick_check": "ok",
        "attempt1_completed_at": check_stage.get("finished_at"),
        "attempt1_candidate_sha256": recorded_sha,
        "attempt1_journal_mode": check_stage.get("capture_journal_mode"),
        "attempt1_sidecar_state": {
            "-wal": attempt_wal,
            "-shm": attempt_shm,
        },
        "current_sidecar_state": {
            "-wal": now_wal,
            "-shm": now_shm,
        },
        "attempt1_evidence": str(path),
    }


def cmd_env(args: argparse.Namespace) -> dict[str, Any]:
    store = open_store(args.store)
    try:
        store_meta = json.loads(
            (store.root / "store.json").read_text(encoding="utf-8")
        )
        code_hashes = {}
        for rel in PINNED_CODE_FILES:
            target = REPO_ROOT / rel
            code_hashes[rel] = (
                file_sha256(target) if target.exists() else None
            )
        deps = {}
        for name in ("pyarrow", "duckdb", "zstandard"):
            mod = __import__(name)
            deps[name] = {
                "version": getattr(mod, "__version__", "?"),
                "origin": getattr(mod, "__file__", None),
            }
        import research_store

        payload: dict[str, Any] = {
            "recorded_at": _utcnow(),
            "cwd": os.getcwd(),
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "store_root": str(store.root),
            "store_identity": store_meta,
            "dependency_modules": deps,
            "research_store_origin": research_store.__file__,
            "code_hashes_sha256": code_hashes,
            "disk": _disk_state(STORE_ROOT),
            "source_roots": {
                "ssquant": {
                    "root": str(SSQUANT_ROOT),
                    "exists": SSQUANT_ROOT.is_dir(),
                    "main_db": str(SSQUANT_DB),
                    "main_db_bytes": SSQUANT_DB.stat().st_size
                    if SSQUANT_DB.exists()
                    else None,
                },
                "holographic": {
                    "root": str(HOLO_ROOT),
                    "exists": HOLO_ROOT.is_dir(),
                },
            },
        }
        return payload
    finally:
        store.close()


def _enumerate_archive_members(archive: Path) -> dict[str, Any]:
    """Stream one .tar.zst and collect member metadata (no extraction)."""
    started = time.monotonic()
    members = 0
    total_bytes = 0
    sample_names: list[str] = []
    parquet_member_sha: str | None = None
    expected = FUTURES_CANDIDATE_EXPECTED.get(archive.name, {})
    tf = open_tar_zst(archive)
    try:
        for member in tf:
            if member.isdir():
                continue
            validate_member(member)
            members += 1
            total_bytes += member.size
            if len(sample_names) < 10:
                sample_names.append(member.name)
            if member.name == expected.get("member") and parquet_member_sha is None:
                digest = hashlib.sha256()
                fileobj = tf.extractfile(member)
                if fileobj is None:
                    raise ValueError(f"member has no content: {member.name!r}")
                while True:
                    block = fileobj.read(1024 * 1024)
                    if not block:
                        break
                    digest.update(block)
                parquet_member_sha = digest.hexdigest()
    finally:
        tf.close()
    elapsed = time.monotonic() - started
    return {
        "archive": str(archive),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": file_sha256(archive),
        "member_count": members,
        "member_uncompressed_bytes": total_bytes,
        "member_name_sample": sample_names,
        "expected_member_sha256": expected.get("member_sha256"),
        "parquet_member_sha256": parquet_member_sha,
        "enumerate_elapsed_seconds": round(elapsed, 3),
    }


def _scan_rq_packages_safe(holo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Scan each RQ package individually so one malformed manifest cannot
    abort the whole inventory. Failures are recorded, not hidden."""
    summaries: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    rq_root = holo_root / "rqdata"
    if not rq_root.is_dir():
        return summaries, failures
    for package_dir in sorted(rq_root.iterdir()):
        if not package_dir.is_dir():
            continue
        try:
            summaries.append(
                scan_rq_package(package_dir, verify_hashes=False).summary()
            )
        except Exception as exc:  # noqa: BLE001 - report, never hide
            failures.append(
                {
                    "package": package_dir.name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return summaries, failures


def cmd_inventory(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    ssquant = scan_directory(SSQUANT_ROOT)
    ssquant.caveats.extend(SSQUANT_CAVEATS)
    holo = scan_directory(HOLO_ROOT)
    holo.caveats.extend(HOLO_CAVEATS)
    rq_packages, rq_failures = _scan_rq_packages_safe(HOLO_ROOT)
    roots = {
        "generated_at": _inv_utcnow_iso(),
        "ssquant": ssquant.summary(),
        "holographic": holo.summary(),
        "rq_packages": rq_packages,
        "rq_package_failures": rq_failures,
        "reconciliation_reference": (
            "D:/quant-data/reports/delivery04d/delivery04d-inventory.json "
            "(corrected public inventory, inventory04E PASS)"
        ),
    }
    archives = []
    for archive in FUTURES_CANDIDATE_ARCHIVES:
        archives.append(_enumerate_archive_members(archive))
    payload = {
        "generated_at": _utcnow(),
        "scan_elapsed_seconds": round(time.monotonic() - started, 3),
        "hash_policy": (
            "no bulk hashing of the 54GB tree; json/sidecar files hashed by "
            "scan_directory; formally-used parquet members hashed via streaming"
        ),
        "roots": roots,
        "futures_candidate_archives": archives,
        "locator_notes": {
            "real_input_candidates": ".coordination/REAL_INPUT_CANDIDATES.md",
            "futures_input_candidates": ".coordination/FUTURES_INPUT_CANDIDATES.md",
            "note": (
                "locator hashes reproduced/extended here; they are not "
                "storage acceptance and not current verification of semantics"
            ),
        },
    }
    return payload


def _find_reusable_capture(captures_dir: Path, source_size: int) -> Path | None:
    """Return the newest capture whose sidecar receipt matches source size."""
    candidates = sorted(captures_dir.glob("*_capture_*.db"), key=os.path.getmtime)
    for capture in reversed(candidates):
        receipt_path = capture.with_suffix(capture.suffix + ".receipt.json")
        if not receipt_path.exists():
            continue
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            receipt.get("source_size") == source_size
            and receipt.get("quick_check") == "ok"
            and receipt.get("sha256")
            and capture.stat().st_size == receipt.get("bytes")
        ):
            return capture
    return None


def cmd_capture(args: argparse.Namespace) -> dict[str, Any]:
    store = open_store(args.store)
    try:
        source_size = SSQUANT_DB.stat().st_size
        free_before = _disk_state(STORE_ROOT)
        if free_before["free_bytes"] < source_size * 2:
            raise SystemExit(
                f"insufficient free space: {free_before['free_bytes']} < "
                f"2x source {source_size}"
            )
        reusable = (
            _find_reusable_capture(store.path.captures, source_size)
            if args.reuse
            else None
        )
        if reusable is not None:
            receipt = json.loads(
                reusable.with_suffix(reusable.suffix + ".receipt.json").read_text(
                    encoding="utf-8"
                )
            )
            receipt["reused_existing_capture"] = str(reusable)
            return dict(receipt)
        started = time.monotonic()
        receipt = capture_sqlite(SSQUANT_DB, store.path.captures)
        elapsed = time.monotonic() - started
        payload = {
            "source": receipt.source,
            "capture": receipt.capture,
            "bytes": receipt.bytes,
            "sha256": receipt.sha256,
            "quick_check": receipt.quick_check,
            "captured_at": receipt.captured_at,
            "source_size": receipt.source_size,
            "capture_elapsed_seconds": round(elapsed, 3),
            "free_bytes_before": free_before["free_bytes"],
            "free_bytes_after": _disk_state(STORE_ROOT)["free_bytes"],
        }
        capture_path = Path(receipt.capture)
        _write_json(payload, capture_path.with_suffix(capture_path.suffix + ".receipt.json"))
        return payload
    finally:
        store.close()


def cmd_verify_capture(args: argparse.Namespace) -> dict[str, Any]:
    """Staged in-place validation of an interrupted capture candidate.

    Issues a CURRENT RECOVERY VALIDATION receipt. Reuse is justified ONLY
    when: sizes match; quick_check is ``ok`` (either a fresh ``mode=ro``
    scan, or the attempt-1 result re-bound to the unchanged candidate
    whole-file SHA256 and stable sidecars — never a blind reuse); the
    source is unchanged during hashing; every 100-byte database-header
    field is byte-identical EXCEPT the exact offsets the official backup
    API legitimately rewrites (file change counter 24-27, schema cookie
    40-43, version-valid-for 92-95) — page size, encoding, schema format,
    page count, magic, reserved bytes and all other unapproved bytes must
    match; and SHA-256 from byte 100 to EOF is identical for capture and
    source. Any failure preserves the candidate and writes failure
    evidence. ``captured_at`` stays UNKNOWN: the historical completion
    time of the old worker is not established and never invented.
    """
    capture = Path(args.capture)
    source = SSQUANT_DB
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    log_path = report_dir / "delivery04h-verify-progress.log"
    stage_path = report_dir / "delivery04h-verify-capture-stage.json"
    started = time.monotonic()
    stages: list[dict[str, Any]] = []

    def log(message: str) -> None:
        line = f"{_utcnow()} {message}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def save_stage(status: str, **extra: Any) -> None:
        payload: dict[str, Any] = {
            "status": status,
            "updated_at": _utcnow(),
            "elapsed_seconds": _elapsed_since(started),
            "capture": str(capture),
            "source": str(source),
            "stages": stages,
            "progress_log": str(log_path),
            "diagnosis": ".coordination/delivery04h-stage-diagnosis.md",
        }
        payload.update(extra)
        _write_json(payload, stage_path)

    if not capture.exists():
        raise SystemExit(f"capture candidate not found: {capture}")
    if not source.exists():
        raise SystemExit(f"source database not found: {source}")

    # ---- stage 1: stats -------------------------------------------------
    log("stage 1/5 stats: measuring source/capture/sidecar state")
    stage: dict[str, Any] = {"stage": "stats", "started_at": _utcnow()}
    source_stats = _file_stats(source)
    capture_stats = _file_stats(capture)
    source_sidecars_before = _sidecar_stats(source)
    capture_sidecars_before = _sidecar_stats(capture)
    size_match = capture_stats["size_bytes"] == source_stats["size_bytes"]
    stage.update(
        {
            "finished_at": _utcnow(),
            "source": source_stats,
            "capture": capture_stats,
            "source_sidecars": source_sidecars_before,
            "capture_sidecars": capture_sidecars_before,
            "size_match": size_match,
        }
    )
    stages.append(stage)
    log(
        f"stage 1/5 stats: source={source_stats['size_bytes']}B "
        f"capture={capture_stats['size_bytes']}B size_match={size_match}"
    )
    save_stage("running")
    if not size_match:
        failure = {
            "validated": False,
            "reason": (
                "capture size differs from source; copy phase did not "
                "complete; candidate PRESERVED for manual disposition"
            ),
            "stages": stages,
        }
        _write_json(
            failure, report_dir / "delivery04h-verify-capture-FAILURE.json"
        )
        save_stage("failed")
        raise SystemExit(
            f"capture size {capture_stats['size_bytes']} != source size "
            f"{source_stats['size_bytes']}; candidate preserved, no receipt"
        )

    # ---- stage 2: hash capture ------------------------------------------
    log("stage 2/5 hash-capture: streaming SHA-256 over the capture")
    stage = {"stage": "hash_capture", "started_at": _utcnow()}
    capture_sha, capture_remainder_sha, capture_elapsed = _sha256_pair_with_progress(
        capture, log, "capture"
    )
    stage.update(
        {
            "finished_at": _utcnow(),
            "sha256": capture_sha,
            "remainder_from_header_sha256": capture_remainder_sha,
            "elapsed_seconds": round(capture_elapsed, 3),
        }
    )
    stages.append(stage)
    save_stage("running")

    # ---- stage 3: quick_check (mode=ro, or bound reuse) ------------------
    reuse = _attempt1_quick_check_reuse(
        report_dir, capture_sha, capture_sidecars_before
    )
    stage = {"stage": "quick_check", "started_at": _utcnow()}
    if reuse is not None:
        check = reuse["quick_check"]
        journal_mode = reuse["attempt1_journal_mode"]
        quick_check_basis: dict[str, Any] = reuse
        stage.update(
            {
                "finished_at": _utcnow(),
                "quick_check": check,
                "capture_journal_mode": journal_mode,
                "quick_check_basis": quick_check_basis,
                "note": (
                    "attempt-1 completed quick_check REUSED: bound to the "
                    "unchanged candidate whole-file SHA256 and stable "
                    "sidecar state; the ~23-minute page scan was NOT "
                    "repeated"
                ),
            }
        )
        log(
            "stage 3/5 quick-check: REUSED attempt-1 'ok' (bound to "
            f"unchanged candidate sha256 {capture_sha}); rescan skipped"
        )
    else:
        log("stage 3/5 quick-check: PRAGMA quick_check(1) on mode=ro connection")
        con = sqlite3.connect(f"file:{capture.as_posix()}?mode=ro", uri=True)
        try:
            try:
                journal_mode = con.execute("PRAGMA journal_mode").fetchone()[0]
                check = con.execute("PRAGMA quick_check(1)").fetchone()[0]
            except sqlite3.Error as exc:
                journal_mode = "unreadable"
                check = f"error: {exc}"
        finally:
            con.close()
        quick_check_basis = {
            "basis": "fresh_scan_this_validation",
            "candidate_sha256_at_scan": capture_sha,
        }
        stage.update(
            {
                "finished_at": _utcnow(),
                "quick_check": check,
                "capture_journal_mode": journal_mode,
                "quick_check_basis": quick_check_basis,
                "capture_sidecars_after": _sidecar_stats(capture),
                "note": (
                    "mode=ro open of a WAL-mode capture may touch the -shm "
                    "sidecar mtime; content checks stay read-only and the "
                    "live source WAL is never bypassed"
                ),
            }
        )
        log(f"stage 3/5 quick-check: result={check!r} journal_mode={journal_mode}")
    stages.append(stage)
    save_stage("running")

    # ---- stage 4: hash source --------------------------------------------
    log("stage 4/5 hash-source: streaming SHA-256 over the source main file")
    stage = {"stage": "hash_source", "started_at": _utcnow()}
    source_sha, source_remainder_sha, source_elapsed = _sha256_pair_with_progress(
        source, log, "source"
    )
    source_sidecars_after = _sidecar_stats(source)
    source_stats_after = _file_stats(source)
    source_wal_before = (source_sidecars_before["-wal"] or {}).get("size_bytes")
    source_wal_after = (source_sidecars_after["-wal"] or {}).get("size_bytes")
    unchanged = (
        source_stats_after["size_bytes"] == source_stats["size_bytes"]
        and source_stats_after["mtime_utc"] == source_stats["mtime_utc"]
        and source_wal_before == source_wal_after
    )
    stage.update(
        {
            "finished_at": _utcnow(),
            "sha256": source_sha,
            "remainder_from_header_sha256": source_remainder_sha,
            "elapsed_seconds": round(source_elapsed, 3),
            "source_stats_after": source_stats_after,
            "source_sidecars_after": source_sidecars_after,
            "source_unchanged_during_hash": unchanged,
        }
    )
    stages.append(stage)
    log(f"stage 4/5 hash-source: complete, source_unchanged={unchanged}")
    save_stage("running")

    # ---- stage 5: verdict -------------------------------------------------
    log("stage 5/5 verdict: comparing hashes and issuing/preserving receipt")
    header_cmp = _header_field_comparison(capture, source)
    header_diff = header_cmp["diff_offsets"]
    remainder_match = capture_remainder_sha == source_remainder_sha
    check_ok = check == "ok"
    validated = bool(
        size_match
        and check_ok
        and remainder_match
        and unchanged
        and header_cmp["approved"]
    )
    verdict = {
        "stage": "verdict",
        "started_at": _utcnow(),
        "finished_at": _utcnow(),
        "quick_check_ok": check_ok,
        "remainder_from_header_match": remainder_match,
        "header_approved": header_cmp["approved"],
        "header_diff_offsets": header_diff,
        "header_unapproved_diff_fields": header_cmp["unapproved_diff_fields"],
        "source_unchanged": unchanged,
        "validated": validated,
        "identity_note": (
            "byte-identity is judged per FIELD across the 100-byte header "
            "(only backup-rewritten change counter / schema cookie / "
            "version-valid-for may differ) plus SHA-256 equality from byte "
            f"{_DB_HEADER_BYTES} to EOF; all data pages must be identical"
        ),
    }
    stages.append(verdict)

    total_elapsed = _elapsed_since(started)
    if not validated:
        failure = {
            "validated": False,
            "reason": (
                f"quick_check={check!r} remainder_match={remainder_match} "
                f"size_match={size_match} source_unchanged={unchanged} "
                f"header_approved={header_cmp['approved']}; candidate "
                "PRESERVED unverified, no receipt written; run a single "
                "fresh official mode=ro backup via the capture command"
            ),
            "capture_sha256": capture_sha,
            "source_sha256": source_sha,
            "capture_remainder_sha256": capture_remainder_sha,
            "source_remainder_sha256": source_remainder_sha,
            "header_field_comparison": header_cmp,
            "stages": stages,
        }
        _write_json(
            failure, report_dir / "delivery04h-verify-capture-FAILURE.json"
        )
        save_stage("failed")
        raise SystemExit("capture validation failed; candidate preserved")

    capture_mtime_utc = capture_stats["mtime_utc"]
    receipt = {
        "validation_kind": "current_recovery_validation",
        "source": str(source),
        "capture": str(capture),
        "bytes": capture_stats["size_bytes"],
        "sha256": capture_sha,
        "quick_check": check,
        "quick_check_basis": quick_check_basis,
        "captured_at": None,
        "captured_at_basis": (
            "UNKNOWN — the original 04A backup completion timestamp was "
            "never recorded (session quota-interrupted before any receipt); "
            "the capture file mtime is recorded below as an observation "
            "only, NOT as captured_at proof"
        ),
        "observed_capture_mtime_utc": capture_mtime_utc,
        "source_size": source_stats["size_bytes"],
        "source_sha256": source_sha,
        "capture_remainder_sha256_from_header": capture_remainder_sha,
        "source_remainder_sha256_from_header": source_remainder_sha,
        "header_field_comparison": header_cmp,
        "validated_at": _utcnow(),
        "validation_elapsed_seconds": total_elapsed,
        "validation": {
            "method": (
                "current recovery validation of the preserved interrupted "
                "candidate: staged quick_check (attempt-1 result reused "
                "only when bound to the unchanged candidate whole-file "
                "SHA256 and stable sidecars) + per-field header comparison "
                "(only backup-rewritten change counter 24-27 / schema "
                "cookie 40-43 / version-valid-for 92-95 may differ) + "
                "SHA-256 byte-identity from byte 100 to EOF against the "
                "unchanged source; source WAL 0 bytes before/after; no "
                "immutable bypass, no flat copy"
            ),
            "identity_note": verdict["identity_note"],
            "origin": "recovered_interrupted_delivery04a_backup",
            "historical_completion": (
                "UNKNOWN — this receipt validates the candidate's CURRENT "
                "content; it does not claim the old worker completed"
            ),
            "first_attempt_preserved": str(
                report_dir / "delivery04h-verify-capture-FAILURE-attempt1-mismatch.json"
            ),
            "diagnosis": ".coordination/delivery04h-stage-diagnosis.md",
            "stage_evidence": str(stage_path),
            "progress_log": str(log_path),
            "capture_journal_mode": journal_mode,
            "hash_capture_elapsed_seconds": round(capture_elapsed, 3),
            "hash_source_elapsed_seconds": round(source_elapsed, 3),
            "source_wal_bytes_before": source_wal_before,
            "source_wal_bytes_after": source_wal_after,
        },
    }
    receipt_path = capture.with_suffix(capture.suffix + ".receipt.json")
    _write_json(receipt, receipt_path)
    save_stage("validated", receipt=str(receipt_path))
    log(f"stage 5/5 verdict: VALIDATED, receipt written to {receipt_path}")
    return {
        "validated": True,
        "validation_kind": "current_recovery_validation",
        "capture": str(capture),
        "sha256": capture_sha,
        "source_sha256": source_sha,
        "remainder_from_header_match": remainder_match,
        "header_approved": header_cmp["approved"],
        "header_diff_offsets": header_diff,
        "quick_check": check,
        "quick_check_reused": reuse is not None,
        "bytes": capture_stats["size_bytes"],
        "source_size": source_stats["size_bytes"],
        "validated_at": receipt["validated_at"],
        "validation_elapsed_seconds": total_elapsed,
        "receipt": str(receipt_path),
    }


def _count_rows(con: Any, table: str) -> int:
    quoted = _quote_ident(table)
    return int(con.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])


def _quote_ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"unsafe identifier: {name!r}")
    return f'"{name}"'


def _capped_row_count(con: Any, table: str, cap: int) -> dict[str, int | bool]:
    """Row count bounded at ``cap`` rows: exact below the cap, >=cap above."""
    quoted = _quote_ident(table)
    counted = int(
        con.execute(
            f"SELECT COUNT(*) FROM (SELECT 1 FROM {quoted} LIMIT ?)", (cap,)
        ).fetchone()[0]
    )
    return {
        "row_count": counted,
        "exact": counted < cap,
        "cap": cap,
    }


def _table_indexes(con: Any, table: str) -> list[str]:
    return [
        row[0]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
            (table,),
        )
    ]


def _representative_tables(plan: list[Any]) -> list[Any]:
    """One table per (series_kind, frequency) combination, deterministic."""
    seen: dict[tuple[str, str], Any] = {}
    for p in plan:
        seen.setdefault((p.series_kind, p.frequency), p)
    return [seen[key] for key in sorted(seen)]


def _find_ma_sample_table(plan: list[Any]) -> tuple[str | None, str]:
    """Discover the MA product 1M table for the bounded amount sample.

    Prefers the vendor continuous series (continuous_888, then 777) that the
    known "MA amount untrusted" caveat refers to; falls back to any
    real-contract MA table. Returns ``(table_or_None, basis_note)``.
    """
    by_kind: dict[str, str] = {}
    for p in plan:
        if p.product == "ma" and p.frequency == "1M":
            by_kind.setdefault(p.series_kind, p.table)
    for kind in ("continuous_888", "continuous_777", "real_contract"):
        if kind in by_kind:
            return by_kind[kind], f"discovered ma* 1M table ({kind})"
    return None, "no ma* 1M raw table exists on this capture"


def cmd_inspect(args: argparse.Namespace) -> dict[str, Any]:
    """Bounded read-only inspection of a validated capture.

    Scope is deliberate: classification counts from the schema, exact counts
    only for the meta/staging tables and capped counts for a small
    representative locator set, plus scoped SimNow / MA / real_symbol /
    cumulative_openint observations. No arbitrary full-table scans, no
    global coverage claims.
    """
    capture = Path(args.capture)
    con = connect_read_only(capture)
    started = time.monotonic()
    try:
        # ---- classification (schema-level, cheap) -----------------------
        plan = build_table_plan(con)
        by_kind: Counter[str] = Counter(p.series_kind for p in plan)
        by_freq: Counter[str] = Counter(p.frequency for p in plan)
        kind_freq: Counter[str] = Counter(
            f"{p.series_kind}/{p.frequency}" for p in plan
        )

        # ---- exact SimNow 8-key rule + overlap diagnostics ---------------
        mark = time.monotonic()
        quarantine = sorted(simnow_quarantine_keys(con))
        overlaps = meta_main_overlap_diagnostics(con)
        simnow_elapsed = _elapsed_since(mark)
        meta_rows = _count_rows(con, "simnow_bar_meta")
        meta_symbols = [
            row[0]
            for row in con.execute(
                "SELECT DISTINCT symbol FROM simnow_bar_meta ORDER BY symbol"
            )
        ]
        meta_span = con.execute(
            "SELECT MIN(datetime), MAX(datetime) FROM simnow_bar_meta"
        ).fetchone()

        # ---- scoped locator tables ---------------------------------------
        plan_by_table = {p.table: p for p in plan}
        locator_plan: dict[str, Any] = {}
        for p in _representative_tables(plan):
            locator_plan[p.table] = p
        ma_table, ma_basis = _find_ma_sample_table(plan)
        incident_tables = [
            f"{symbol.lower()}_1M_raw" for symbol, _ in sorted(SIMNOW_INCIDENT_KEYS)
        ]
        if ma_table is not None:
            incident_tables.append(ma_table)
        for table in incident_tables:
            if table in plan_by_table:
                locator_plan[table] = plan_by_table[table]
        locator_tables: dict[str, dict[str, Any]] = {}
        counts_started = time.monotonic()
        for table in sorted(locator_plan):
            mark = time.monotonic()
            indexes = _table_indexes(con, table)
            span = table_time_span(con, table)
            count = _capped_row_count(con, table, SCOPED_COUNT_CAP)
            locator_tables[table] = {
                "series_kind": locator_plan[table].series_kind,
                "frequency": locator_plan[table].frequency,
                "indexes": indexes,
                "time_span_first": span[0],
                "time_span_last": span[1],
                "row_scope": count,
                "elapsed_seconds": _elapsed_since(mark),
            }
        counts_elapsed = time.monotonic() - counts_started

        # ---- exact staging counts (small, scoped) -------------------------
        staging_counts = {
            p.table: _count_rows(con, p.table)
            for p in plan
            if p.series_kind == "staging"
        }

        # ---- source columns per series kind -------------------------------
        columns_by_kind: dict[str, list[tuple[str, str]]] = {}
        seen: set[str] = set()
        for p in plan:
            if p.series_kind in seen:
                continue
            seen.add(p.series_kind)
            columns_by_kind[p.series_kind] = table_schema(con, p.table)
        real_cols = columns_by_kind.get("real_contract", [])

        # ---- bounded MA raw-amount sample ---------------------------------
        ma_sample: dict[str, Any] = {
            "table": ma_table,
            "selection_basis": ma_basis,
        }
        if ma_table is not None and ma_table != MA_SAMPLE_TABLE:
            ma_sample["planned_table_absent_note"] = (
                f"historically planned {MA_SAMPLE_TABLE} does not exist on "
                "this capture; the sample uses the discovered table above"
            )
        exists = (
            con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (ma_table,),
            ).fetchone()
            if ma_table is not None
            else None
        )
        if ma_table is not None and exists is not None:
            mark = time.monotonic()
            total = _count_rows(con, ma_table)
            rows = con.execute(
                f"SELECT datetime, open, high, low, close, volume, amount, "
                f"openint, cumulative_openint, real_symbol "
                f"FROM {_quote_ident(ma_table)} WHERE datetime LIKE ? "
                f"ORDER BY datetime LIMIT ?",
                (MA_SAMPLE_MONTH_PREFIX + "%", MA_SAMPLE_ROW_CAP),
            ).fetchall()
            checked = 0
            outside = 0
            null_amount = 0
            zero_volume = 0
            cum_null = 0
            cum_negative = 0
            cum_values: list[float] = []
            oin_negative = 0
            real_symbol_null = 0
            for _dt, _open, high, low, _close, vol, amt, oin, cum, rsym in rows:
                if rsym is None:
                    real_symbol_null += 1
                if cum is None:
                    cum_null += 1
                else:
                    if cum < 0:
                        cum_negative += 1
                    if len(cum_values) < 3:
                        cum_values.append(cum)
                if oin is not None and oin < 0:
                    oin_negative += 1
                if amt is None:
                    null_amount += 1
                    continue
                if not vol:
                    zero_volume += 1
                    continue
                vwap = amt / vol
                checked += 1
                if (low is not None and vwap < low) or (
                    high is not None and vwap > high
                ):
                    outside += 1
            first, last = table_time_span(con, ma_table)
            ma_sample.update(
                {
                    "month_prefix": MA_SAMPLE_MONTH_PREFIX,
                    "table_rows_total": total,
                    "sample_first_datetime": rows[0][0] if rows else None,
                    "sample_last_datetime": rows[-1][0] if rows else None,
                    "sample_rows": len(rows),
                    "vwap_checked_rows": checked,
                    "vwap_outside_ohlc_rows": outside,
                    "null_amount_rows": null_amount,
                    "zero_volume_rows": zero_volume,
                    "real_symbol_null_rows_in_sample": real_symbol_null,
                    "cumulative_openint_null_rows_in_sample": cum_null,
                    "cumulative_openint_negative_rows_in_sample": cum_negative,
                    "cumulative_openint_sample_values": cum_values,
                    "openint_negative_rows_in_sample": oin_negative,
                    "time_span_first": first,
                    "time_span_last": last,
                    "elapsed_seconds": _elapsed_since(mark),
                    "note": (
                        "raw amount/volume VWAP vs same-row OHLC and raw "
                        "cumulative_openint/openint values; raw evidence "
                        "only, no unit or multiplier inference; "
                        "cumulative_openint treated as candidate total OI"
                    ),
                }
            )
        else:
            ma_sample["error"] = (
                "no MA sample table exists on this capture"
                if ma_table is None
                else "selected MA table missing on capture"
            )

        # ---- real_symbol distribution on one vendor-continuous table -----
        real_symbol_obs: dict[str, Any] = {"table": "a888_1M_raw"}
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            ("a888_1M_raw",),
        ).fetchone()
        if exists:
            mark = time.monotonic()
            rows = con.execute(
                "SELECT real_symbol FROM "
                "(SELECT real_symbol FROM a888_1M_raw LIMIT ?)",
                (REAL_SYMBOL_SAMPLE_CAP,),
            ).fetchall()
            nulls = sum(1 for (r,) in rows if r is None)
            distinct = [
                r[0]
                for r in con.execute(
                    "SELECT DISTINCT real_symbol FROM "
                    "(SELECT real_symbol FROM a888_1M_raw LIMIT ?) "
                    "WHERE real_symbol IS NOT NULL LIMIT 20",
                    (REAL_SYMBOL_SAMPLE_CAP,),
                )
            ]
            real_symbol_obs.update(
                {
                    "sample_rows": len(rows),
                    "null_real_symbol_rows": nulls,
                    "distinct_real_symbol_sample": distinct,
                    "sample_cap": REAL_SYMBOL_SAMPLE_CAP,
                    "elapsed_seconds": _elapsed_since(mark),
                    "note": (
                        "rowid-ordered head sample; evidence that the vendor "
                        "continuous series carries real_symbol identity, not "
                        "a coverage claim"
                    ),
                }
            )
        else:
            real_symbol_obs["error"] = "table missing on capture"

        payload: dict[str, Any] = {
            "inspected_at": _utcnow(),
            "capture": str(capture),
            "inspection_elapsed_seconds": _elapsed_since(started),
            "classification": {
                "tables_total": len(plan),
                "by_series_kind": dict(by_kind),
                "by_frequency": dict(by_freq),
                "by_kind_frequency": dict(kind_freq),
            },
            "simnow": {
                "authoritative_incident_keys": sorted(
                    f"{s} {d}" for s, d in sorted(SIMNOW_INCIDENT_KEYS)
                ),
                "quarantine_keys_detected": [
                    f"{s} {d}" for _t, s, d in quarantine
                ],
                "quarantine_matches_authoritative": {
                    f"{s} {d}" for _t, s, d in quarantine
                }
                == {f"{s} {d}" for s, d in SIMNOW_INCIDENT_KEYS},
                "meta_rows_exact": meta_rows,
                "meta_distinct_symbols": meta_symbols,
                "meta_datetime_min": meta_span[0],
                "meta_datetime_max": meta_span[1],
                "detector_elapsed_seconds": simnow_elapsed,
                "overlap_diagnostics": overlaps,
                "overlap_note": (
                    "ordinary meta/main time overlaps are diagnostics only, "
                    "never contamination; quarantine uses ONLY the exact "
                    "meta-key + NULL real_symbol + zero volume/amount rule"
                ),
            },
            "ma_raw_amount_sample": ma_sample,
            "continuous_real_symbol_sample": real_symbol_obs,
            "columns_by_kind": {
                k: [list(col) for col in v] for k, v in columns_by_kind.items()
            },
            "columns_note": (
                f"real_contract representative has {len(real_cols)} columns; "
                "trailing Chinese-named columns are mojibake in the source "
                "schema and are preserved verbatim, never renamed"
            ),
            "scoped_row_counts": {
                "staging_tables_exact": staging_counts,
                "locator_tables_capped": {
                    t: v["row_scope"] for t, v in locator_tables.items()
                },
                "scoped_elapsed_seconds": round(counts_elapsed, 3),
                "scope_note": (
                    "row counts are exact for meta/staging and capped "
                    f"(cap={SCOPED_COUNT_CAP}) for the locator set only; "
                    "remaining tables are NOT counted here (no arbitrary "
                    "full-table scans; totals are established at import "
                    "time per table)"
                ),
            },
            "locator_tables": locator_tables,
            "log_claim_note": (
                "68,022,890 was LOG-reported; this inspection does not "
                "claim a verified global row total"
            ),
        }
        return payload
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=str(STORE_ROOT))
    parser.add_argument(
        "--report-dir", default=str(DEFAULT_REPORT_DIR),
        help="JSON output directory",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("env")
    sub.add_parser("inventory")
    cap = sub.add_parser("capture")
    cap.add_argument(
        "--reuse",
        action="store_true",
        help="reuse a valid completed capture for the same source size",
    )
    ver = sub.add_parser("verify-capture")
    ver.add_argument(
        "--capture",
        default=str(DEFAULT_CAPTURE),
        help="interrupted capture candidate to validate in place",
    )
    insp = sub.add_parser("inspect")
    insp.add_argument("--capture", required=True, help="capture .db path")

    args = parser.parse_args(argv)
    report_dir = Path(args.report_dir)
    handlers = {
        "env": cmd_env,
        "inventory": cmd_inventory,
        "capture": cmd_capture,
        "verify-capture": cmd_verify_capture,
        "inspect": cmd_inspect,
    }
    started = time.monotonic()
    try:
        payload = handlers[args.command](args)
    except Exception:
        failure = {
            "command": args.command,
            "failed_at": _utcnow(),
            "traceback": traceback.format_exc(),
        }
        _write_json(failure, report_dir / f"delivery04h-{args.command}-FAILURE.json")
        raise
    payload = dict(payload)
    payload["tool_command"] = args.command
    payload["tool_elapsed_seconds"] = _elapsed_since(started)
    out = _write_json(payload, report_dir / f"delivery04h-{args.command}.json")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
