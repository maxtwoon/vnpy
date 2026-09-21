"""WP10K delivery representatives — one reusable runner for bounded real evidence.

Runs the remaining representative real-data demonstrations assigned to
OpenCode in TASK_OPENCODE_DELIVERY_REPRESENTATIVES_04K.md, each as an
independent, resumable case that writes one machine-readable JSON evidence
file under ``reports/delivery04k`` of the store:

* ``stock``   — historical real Client raw receipts through the public
  ``vnpy_datasource.storage.save_history(target="store")`` path (no new
  provider query, no zero-filled BarData conversion), with public readback
  and repeated-import idempotency counts.
* ``futures`` — RQ real contract A2505 bounded night scope. Per the
  superseding FUTURES_TIME_REVIEW_04IB.md the minute label direction is
  UNKNOWN, so NO canonical bounds are constructed and NO canonical bars
  are published or frozen. The case demonstrates: bounded streaming of the
  two located members through public readers, the exact keyed
  ``(order_book_id == dominant_id, source datetime)`` trading-date join
  (1035 rows, Friday-night mappings), duplicate/unmatched/conflict counts,
  contract versus dominant-series isolation, preservation of the real rows
  on the public StoreSink candidate/inspection path with original labels,
  and a PRECISE public-API reproduction of the importer's hardcoded END
  label behaviour returned to the coordinator as an implementation request.
* ``jq``      — JoinQuant holographic daily 33-column sample streamed from
  one real gzip member with every source field/NULL preserved and
  ``factor=1.0 => adjustment UNKNOWN``; bounded public import/query only.
* ``etf``     — real repaired-base sample for one security/year with the
  full 133-key correction index loaded BEFORE the base archive, explicit
  old/new/upstream candidates, default-qualified exclusion behaviour and a
  single explicitly-allowed disputed key (never a global gap allowance).
* ``catalog`` — P4 catalog-only truth: measured inventory04D categories
  (missing convertible 4911-row refetch overlay/audit, index-2014
  manifest/sidecar version conflict, 37 missing preferred-shares years,
  PIT knowledge-time ambiguity) re-verified by bounded read-only checks.
  No import is performed and no bulk re-hash is done.

Only public APIs are used: ``research_store`` core (store/import/freeze/
reader/importers) and ``vnpy_datasource.storage.save_history``. No CLI,
native, recording or capture entrypoints of other owners are touched, and
no existing importer/core/normalizer module is edited.

Usage:
    python tools/delivery_representatives.py --config <config.json> --case stock

Every case prints its evidence JSON on stdout and writes it to
``<reports_dir>/<case>.json``. Exit code is nonzero when the case errors;
failing assertions keep exit code 0 but mark the case status FAIL_* in the
evidence file (failures are never rewritten into successes).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CASES = ("env", "stock", "futures", "jq", "etf", "catalog", "report")


# ---------------------------------------------------------------------------
# Small shared helpers (pure where possible; unit-tested offline)
# ---------------------------------------------------------------------------


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return sha256_file(path)


def validate_config(raw: Any) -> list[str]:
    """Structural validation of the runner config (pure, offline-testable)."""
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["config must be a JSON object"]
    for key in ("store_root", "reports_dir", "runtime_dir"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            errors.append(f"config.{key} must be a non-empty string")
    for section in ("stock", "futures", "jq", "etf", "catalog"):
        value = raw.get(section)
        if value is None:
            continue
        if not isinstance(value, dict):
            errors.append(f"config.{section} must be an object")
    stock = raw.get("stock") or {}
    for key in ("input_dir", "inputs", "expected_sha256"):
        if key not in stock:
            errors.append(f"config.stock.{key} is required")
    futures = raw.get("futures") or {}
    for key in (
        "root",
        "contract_archive",
        "dominant_archive",
        "contract_member",
        "dominant_member",
        "instrument",
        "window",
        "expected_window_rows",
        "friday_night",
    ):
        if key not in futures:
            errors.append(f"config.futures.{key} is required")
    jq = raw.get("jq") or {}
    for key in ("daily_dir", "year", "instrument", "window"):
        if key not in jq:
            errors.append(f"config.jq.{key} is required")
    etf = raw.get("etf") or {}
    for key in ("package_dir", "frequency", "year", "instrument", "disputed_key"):
        if key not in etf:
            errors.append(f"config.etf.{key} is required")
    catalog = raw.get("catalog") or {}
    for key in ("inventory04d", "rq_root", "pit_package", "index_package"):
        if key not in catalog:
            errors.append(f"config.catalog.{key} is required")
    return errors


def load_config(path: str | os.PathLike[str]) -> tuple[dict[str, Any], str]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = validate_config(raw)
    if errors:
        raise SystemExit(f"config {path} invalid: {errors}")
    identity = sha256_bytes(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return raw, identity


def peak_rss_mb() -> float | None:
    try:
        import psutil

        return round(psutil.Process().memory_info().peak_wset / (1024 * 1024), 1)
    except Exception:  # noqa: BLE001 - diagnostics must never fail a case
        return None


def module_code_hashes() -> dict[str, str]:
    """Hashes of the actually-loaded research_store/vnpy_datasource modules."""
    hashes: dict[str, str] = {}
    for module in list(sys.modules.values()):
        origin = getattr(module, "__file__", None)
        if not origin:
            continue
        normalised = str(Path(origin).resolve())
        if "research_store" in normalised or "vnpy_datasource" in normalised:
            if normalised.endswith(".py"):
                try:
                    hashes[normalised] = sha256_file(normalised)
                except OSError:
                    continue
    return dict(sorted(hashes.items()))


def shanghai_label_to_utc(label: str) -> datetime:
    """Asia/Shanghai wall-clock label -> aware UTC datetime."""
    from research_store.importers.normalize import SHANGHAI_TZ

    text = label.strip().replace("T", " ")
    fmt = "%Y-%m-%d %H:%M:%S" if " " in text else "%Y-%m-%d"
    naive = datetime.strptime(text, fmt)
    return naive.replace(tzinfo=SHANGHAI_TZ).astimezone(timezone.utc)


def assertion(
    name: str, expected: Any, actual: Any, passed: bool
) -> dict[str, Any]:
    return {
        "name": name,
        "expected": expected,
        "actual": actual,
        "pass": bool(passed),
    }


def new_case_frame(
    case: str, config_path: str, config_identity: str
) -> dict[str, Any]:
    return {
        "case": case,
        "task": "TASK_OPENCODE_DELIVERY_REPRESENTATIVES_04K.md",
        "command": (
            "tools/delivery_representatives.py --config "
            f"{config_path} --case {case}"
        ),
        "config_path": str(Path(config_path).resolve()),
        "config_sha256": sha256_file(config_path),
        "config_identity": config_identity,
        "started_utc": utc_now_iso(),
        "python": sys.executable,
        "status": "RUNNING",
        "assertions": [],
        "limitations": [],
        "software_failures": [],
    }


def finish_case_frame(frame: dict[str, Any], started: float) -> dict[str, Any]:
    frame["ended_utc"] = utc_now_iso()
    frame["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    frame["peak_rss_mb"] = peak_rss_mb()
    frame["code_hashes_loaded"] = module_code_hashes()
    failed = [a for a in frame["assertions"] if not a["pass"]]
    if frame["software_failures"]:
        frame["status"] = "FAIL_SOFTWARE"
    elif failed:
        frame["status"] = "FAIL_ASSERTIONS"
    else:
        frame["status"] = "PASS"
    return frame


def batch_config_payload(store: Any, batch_id: str) -> dict[str, Any] | None:
    row = store.catalog.query_one(
        "SELECT config_json FROM batches WHERE batch_id=?", (batch_id,)
    )
    if row is None or row["config_json"] is None:
        return None
    return json.loads(str(row["config_json"]))


def stream_member_rows(
    archive: Path, member_name: str, staging_dir: Path
) -> tuple[str, int, list[dict[str, Any]]]:
    """Spool exactly one validated archive member and return its rows.

    Composes the public ``research_store.importers.safeio`` building blocks
    (``open_tar_zst`` / ``validate_member`` / ``spool_member``) — the same
    primitives ``iter_tar_zst_parquet`` applies — restricted to the single
    member the assigned evidence locates, so the bounded scope never reads
    neighbouring members' content. Members before the target are validated
    but not read. Returns (member_sha256, member_bytes, rows).
    """
    import pyarrow.parquet as pq

    from research_store.importers.safeio import (
        open_tar_zst,
        spool_member,
        validate_member,
    )

    staging_dir.mkdir(parents=True, exist_ok=True)
    spooled: Path | None = None
    tf = open_tar_zst(archive)
    try:
        for member in tf:
            if member.isdir():
                continue
            validate_member(member)
            if member.name != member_name:
                continue
            spooled = spool_member(tf, member, staging_dir)
            break
    finally:
        tf.close()
    if spooled is None:
        raise SystemExit(f"member {member_name!r} not found in {archive}")
    try:
        member_sha = sha256_file(spooled)
        member_bytes = spooled.stat().st_size
        table = pq.read_table(spooled)
        return member_sha, member_bytes, table.to_pylist()
    finally:
        spooled.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Case 1 — historical real Client raw-stock target=store
# ---------------------------------------------------------------------------


def run_stock(config: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    from research_store import open_snapshot, open_store
    from vnpy_datasource.storage import save_history

    section = config["stock"]
    input_dir = Path(section["input_dir"])
    store_root = str(Path(config["store_root"]).resolve())

    store = open_store(store_root)
    store_id = store.store_id
    datasets_before = store.catalog.query_one("SELECT COUNT(*) AS n FROM datasets")["n"]
    store.close()

    results: list[dict[str, Any]] = []
    for file_name, symbol in section["inputs"].items():
        path = input_dir / file_name
        payload_bytes = path.read_bytes()
        input_sha = sha256_bytes(payload_bytes)
        expected_sha = (section.get("expected_sha256") or {}).get(file_name)
        frame["assertions"].append(
            assertion(
                f"{file_name}: input sha256 matches REAL_INPUT_CANDIDATES locator",
                expected_sha,
                input_sha,
                expected_sha == input_sha,
            )
        )
        result = json.loads(payload_bytes.decode("utf-8"))
        registry_sha = str(result.get("registry_sha256") or "")

        saved_first = save_history(result, symbol, "store", store_root)
        saved_repeat = save_history(result, symbol, "store", store_root)

        store = open_store(store_root)
        dataset_id = saved_first["dataset_id"]
        capture_path = Path(saved_first["capture"])
        capture_equal = json.loads(capture_path.read_text(encoding="utf-8")) == result
        batch_config = batch_config_payload(store, saved_first["batch_id"])
        snapshot_id = saved_first["snapshot_id"]

        records = result.get("records", [])
        actual_by_label: dict[str, dict[str, Any]] = {}
        snapshot = open_snapshot(store, snapshot_id)
        for batch in snapshot.bars(
            dataset_id, required_fields=(), allow_missing_auxiliary=True
        ):
            for row in batch.to_pylist():
                actual_by_label[row["source_label"]] = row
        snapshot.close()

        measures = ("open", "high", "low", "close", "volume", "turnover")
        readback_rows = len(actual_by_label)
        values_equal = readback_rows == len(records)
        missing = [r.get("datetime") for r in records if r.get("datetime") not in actual_by_label]
        if missing:
            values_equal = False
        for record in records:
            seen = actual_by_label.get(record.get("datetime"))
            if seen is None:
                continue
            for field in measures:
                raw_value = record.get(field)
                expected_value = None if raw_value is None else float(raw_value)
                seen_value = seen[field]
                if (seen_value is None) != (expected_value is None):
                    values_equal = False
                elif seen_value is not None and seen_value != expected_value:
                    values_equal = False
        store.close()

        frame["assertions"].append(
            assertion(
                f"{file_name}: store capture preserves the raw result verbatim",
                True,
                capture_equal,
                capture_equal,
            )
        )
        frame["assertions"].append(
            assertion(
                f"{file_name}: historical registry_sha256 preserved in batch config",
                registry_sha,
                (batch_config or {}).get("registry_sha256"),
                (batch_config or {}).get("registry_sha256") == registry_sha,
            )
        )
        frame["assertions"].append(
            assertion(
                f"{file_name}: public readback row count",
                len(records),
                readback_rows,
                readback_rows == len(records) and not missing,
            )
        )
        frame["assertions"].append(
            assertion(
                f"{file_name}: readback values equal raw records (no reconversion)",
                True,
                values_equal,
                values_equal,
            )
        )
        frame["assertions"].append(
            assertion(
                f"{file_name}: repeated import replays idempotently to same ids",
                {
                    "dataset_id": dataset_id,
                    "batch_id": saved_first["batch_id"],
                    "snapshot_id": snapshot_id,
                },
                {
                    "dataset_id": saved_repeat.get("dataset_id"),
                    "batch_id": saved_repeat.get("batch_id"),
                    "snapshot_id": saved_repeat.get("snapshot_id"),
                },
                (
                    saved_repeat.get("dataset_id") == dataset_id
                    and saved_repeat.get("batch_id") == saved_first["batch_id"]
                    and saved_repeat.get("snapshot_id") == snapshot_id
                ),
            )
        )
        results.append(
            {
                "file": file_name,
                "symbol": symbol,
                "input_sha256": input_sha,
                "registry_sha256": registry_sha,
                "dataset_id": dataset_id,
                "batch_id": saved_first["batch_id"],
                "snapshot_id": snapshot_id,
                "capture": str(capture_path),
                "capture_sha256": sha256_file(capture_path),
                "first_import": saved_first,
                "repeat_import": saved_repeat,
                "readback_rows": readback_rows,
            }
        )

    store = open_store(store_root)
    datasets_after = store.catalog.query_one("SELECT COUNT(*) AS n FROM datasets")["n"]
    store.close()
    frame["store_id"] = store_id
    frame["datasets_before"] = datasets_before
    frame["datasets_after"] = datasets_after
    frame["outputs"] = results
    frame["coverage"] = {
        "observed": "10 daily rows per input, read back through SnapshotReader",
        "expected": (
            "10 daily rows per input; calendar completeness beyond the source "
            "window is observed_rows_only_not_calendar_verified per "
            "REAL_INPUT_CANDIDATES.md, so expected stays UNKNOWN beyond it"
        ),
    }
    frame["limitations"].append(
        "These historical receipts contain no NULL turnover in their windows; "
        "NULL roundtrip is covered by separate synthetic focused tests, not here."
    )
    return frame


# ---------------------------------------------------------------------------
# Case 2 — RQ real futures A2505 bounded night scope (04IB: label UNKNOWN)
# ---------------------------------------------------------------------------


def run_futures(config: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    """04L public-API futures representative (repairs the 04K diagnostic).

    Per FUTURES_TIME_REVIEW_04IB the minute label direction is UNKNOWN, so
    this case runs the repaired public default path: every real A2505-scope
    row from the two located members keeps its original label, carries NO
    canonical bounds and routes through StoreSink's public candidate path.
    The exact-key trading-date transfer runs through the PUBLIC adapter
    (``import_rq_futures(date_mapper=...)``) and survives on the candidate
    rows. Nothing canonical is published or frozen. The 04K manual
    bounds-strip workaround is gone; the 04K futures.json stays archived
    history (DIAGNOSTIC_ONLY disposition).
    """
    from research_store import AssetRef, compute_dataset_id, open_store
    from research_store.importers.adapters import import_rq_futures
    from research_store.importers.core_bridge import build_rq_futures_spec
    from research_store.importers.dominant_map import (
        ContractDateMapper,
        DominantMapping,
    )
    from research_store.importers.normalize import normalize_rq_futures_row
    from research_store.importers.sink import CountingSink
    from research_store.importers.store_sink import StoreSink, iter_candidates

    section = config["futures"]
    root = Path(section["root"])
    contract_archive = root / section["contract_archive"]
    dominant_archive = root / section["dominant_archive"]
    instrument = section["instrument"]
    window = section["window"]
    runtime = Path(config["runtime_dir"]) / "futures"
    reports_dir = Path(config["reports_dir"])

    review_path = Path(
        section.get("review_04ib", "FUTURES_TIME_REVIEW_04IB.md")
    )
    review_disposition_path = Path(
        section.get(
            "review_04ib_disposition",
            "FUTURES_TIME_REVIEW_04IB_DISPOSITION.md",
        )
    )
    prior_04k = Path(reports_dir / "futures-04k-diagnostic.json")
    frame["consumed_evidence"] = {
        "review_04ib": {
            "path": str(review_path),
            "sha256": sha256_file(review_path),
            "label_convention": "UNKNOWN (supersedes 04I END resolution)",
        },
        "review_04ib_disposition": {
            "path": str(review_disposition_path),
            "sha256": sha256_file(review_disposition_path),
        },
        "prior_04k_diagnostic": {
            "path": str(prior_04k),
            "sha256": sha256_file(prior_04k) if prior_04k.is_file() else None,
            "disposition": (
                "DIAGNOSTIC_ONLY_MANUAL_BOUNDS_STRIP_NOT_PUBLIC_IMPORTER_"
                "ACCEPTANCE; kept distinct from this repaired public-API run"
            ),
        },
        "hash_reuse": (
            "archive hashes reused from 04IB without rehash; only the spooled "
            "members read here are hashed against the 04IB member records"
        ),
    }

    store = open_store(str(Path(config["store_root"]).resolve()))
    store_id = store.store_id
    datasets_before = store.catalog.query_one("SELECT COUNT(*) AS n FROM datasets")["n"]

    # -- after-fix public behavior first: default UNKNOWN --------------------
    sample_record = None
    member_rows_cache: dict[str, tuple[str, int, list[dict[str, Any]]]] = {}

    def member_rows(archive: Path, member: str, tag: str):
        if tag not in member_rows_cache:
            member_rows_cache[tag] = stream_member_rows(
                archive, member, runtime / "staging" / tag
            )
        return member_rows_cache[tag]

    expected_members = section.get("expected_member_sha256") or {}

    # -- phase 1: bounded member scans + dominant mapping build --------------
    mapper_by_side: dict[str, ContractDateMapper] = {}
    for side, _dataset, archive, member_key in (
        ("contract", "contract_1m_none", contract_archive, "contract"),
        ("dominant", "dominant_1m_none", dominant_archive, "dominant"),
    ):
        member = section[f"{member_key}_member"]
        member_sha, member_bytes, member_all_rows = member_rows(
            archive, member, member_key
        )
        expected = expected_members.get(member_key)
        if expected:
            frame["assertions"].append(
                assertion(
                    f"{side} member sha256 matches FUTURES_TIME_REVIEW_04IB record",
                    expected,
                    member_sha,
                    expected == member_sha,
                )
            )
        frame.setdefault("member_scan", {})[f"{side}"] = {
            "archive": archive.name,
            "member": member,
            "member_sha256": member_sha,
            "member_bytes": member_bytes,
            "member_rows_total": len(member_all_rows),
        }
        if side == "contract":
            sample_record = next(
                (
                    row
                    for row in member_all_rows
                    if str(row.get("order_book_id") or "") == instrument
                ),
                None,
            )
        else:
            # member-scoped dominant mapping (evidence inspection only):
            # retains every A2505 key from the located member for the public
            # date_mapper transfer on the contract side. Built BEFORE the
            # contract import so the public adapter receives the mapper.
            mapping = DominantMapping()
            for record in member_all_rows:
                if str(record.get("dominant_id") or "") != instrument:
                    continue
                trading_date = record.get("trading_date")
                if trading_date is None:
                    continue
                mapping.add(
                    instrument,
                    str(record.get("datetime"))[:19],
                    str(trading_date)[:10],
                )
            frame["dominant_mapping_member_scope"] = mapping.stats()
            mapper_by_side["contract"] = ContractDateMapper(mapping)

    # -- candidate imports through the PUBLIC adapter (both sides scoped to
    # the located members; all rows default-UNKNOWN -> candidates) ----------
    candidate_reports: dict[str, Any] = {}
    for side, dataset, archive, member_key in (
        ("contract", "contract_1m_none", contract_archive, "contract"),
        ("dominant", "dominant_1m_none", dominant_archive, "dominant"),
    ):
        member = section[f"{member_key}_member"]
        member_sha, member_bytes, _member_all_rows = member_rows(
            archive, member, member_key
        )
        batch_id = f"delivery04l-rq-{side}-candidates"
        spec = build_rq_futures_spec(dataset, "1m")  # default UNKNOWN
        sink = StoreSink(
            store,
            AssetRef(
                asset_id=f"asset-rq-{side}-{member_sha[:16]}",
                origin=str(archive),
                format="tar_zst_parquet_member",
                size=member_bytes,
                sha256=member_sha,
            ),
            spec,
            adapter="rq_futures/0.1",
            config={
                "archive": archive.name,
                "archive_sha256_reuse_04ib": (
                    section.get("recorded_archive_sha256_reuse_not_rehashed", {})
                    .get("contract" if side == "contract" else "dominant")
                ),
                "member": member,
                "member_sha256": member_sha,
                "members_filter": [member],
                "label_status": "unknown_per_FUTURES_TIME_REVIEW_04IB",
                "publication": "forbidden_until_label_resolved",
            },
            batch_id=batch_id,
            spool_dir=runtime / "spool" / batch_id,
            candidate_dir=reports_dir / "candidates",
        )
        receipt = import_rq_futures(
            root / archive.parent.name,
            dataset,
            sink,
            batch_id=batch_id,
            staging_dir=runtime / "adapter_staging" / batch_id,
            years=[
                int(
                    re.search(
                        r"(\d{4})\.tar\.zst$", archive.name
                    ).group(1)
                )
            ],
            members={member},
            date_mapper=mapper_by_side.get(side),
        )
        publish = sink.publish()
        summary = sink.summary(publish)
        candidate_reports[side] = {
            "spec": spec,
            "summary": summary,
            "adapter_receipt": {
                "rows_read": receipt.rows_read,
                "rows_accepted": receipt.rows_accepted,
                "members_ok": receipt.members_ok,
                "members_failed": receipt.members_failed,
                "extras": {
                    key: value
                    for key, value in receipt.extras.items()
                    if key != "trading_date_transfer"
                },
                "trading_date_transfer": receipt.extras.get("trading_date_transfer"),
            },
            "dataset_id": compute_dataset_id(spec),
            "candidates": list(iter_candidates(summary["candidate_file"]))
            if summary["candidate_file"]
            else [],
        }

    # -- after-fix behavior assertions ---------------------------------------
    contract_report = candidate_reports["contract"]
    dominant_report = candidate_reports["dominant"]
    frame["assertions"].append(
        assertion(
            "after-fix: default spec declares UNKNOWN minute labels",
            "unknown",
            contract_report["spec"].source_time_label.value,
            contract_report["spec"].source_time_label.value == "unknown",
        )
    )
    spec_ids = {
        label: compute_dataset_id(
            build_rq_futures_spec("contract_1m_none", "1m", time_label=label)
        )
        for label in ("unknown", "start", "end")
    }
    frame["assertions"].append(
        assertion(
            "after-fix: UNKNOWN/START/END never share one semantic identity",
            3,
            len(set(spec_ids.values())),
            len(set(spec_ids.values())) == 3,
        )
    )
    if sample_record is not None:
        fixed_row = normalize_rq_futures_row(
            sample_record,
            dataset="contract_1m_none",
            archive=contract_archive.name,
            member=section["contract_member"],
            batch_id="delivery04l-after-fix-probe",
            interval_minutes=1,
        )
        frame["after_fix_probe"] = {
            "source_label": fixed_row["source_label"],
            "bar_start_ns": fixed_row["bar_start_ns"],
            "bar_end_ns": fixed_row["bar_end_ns"],
            "quality_flags": fixed_row["quality_flags"],
        }
        frame["assertions"].append(
            assertion(
                "after-fix: normalizer returns UNKNOWN bounds + standard flag",
                {"bounds": [None, None], "flag": "source_time_label_unknown"},
                {
                    "bounds": [
                        fixed_row["bar_start_ns"],
                        fixed_row["bar_end_ns"],
                    ],
                    "flag": (
                        "source_time_label_unknown"
                        in fixed_row["quality_flags"]
                    ),
                },
                fixed_row["bar_start_ns"] is None
                and fixed_row["bar_end_ns"] is None
                and "source_time_label_unknown" in fixed_row["quality_flags"],
            )
        )
    # adapter pairing verification: declared END without evidence is refused
    pairing_refusal: str | None = None
    try:
        probe_store = open_store(str(Path(config["store_root"]).resolve()))
        probe_spec = build_rq_futures_spec(
            "contract_1m_none", "1m", time_label="end"
        )
        probe_sink = StoreSink(
            probe_store,
            AssetRef(
                asset_id="asset-pairing-probe",
                origin=str(contract_archive),
                format="tar_zst_parquet_member",
                size=0,
                sha256=section.get("expected_member_sha256", {}).get(
                    "contract", "0" * 64
                ),
            ),
            probe_spec,
            adapter="rq_futures/0.1",
            config={"probe": "declared_end_without_evidence"},
            batch_id="delivery04l-pairing-probe",
            spool_dir=runtime / "spool" / "pairing-probe",
            candidate_dir=reports_dir / "candidates",
        )
        import_rq_futures(
            root / contract_archive.parent.name,
            "contract_1m_none",
            probe_sink,
            batch_id="delivery04l-pairing-probe",
            staging_dir=runtime / "adapter_staging" / "pairing-probe",
            years=[2025],
            members={section["contract_member"]},
        )
        probe_store.close()
    except ValueError as exc:
        pairing_refusal = str(exc)
    except Exception as exc:  # noqa: BLE001 - any other failure is recorded
        pairing_refusal = f"unexpected {type(exc).__name__}: {exc}"
    frame["pairing_verification_probe"] = {
        "note": (
            "declared-END spec without evidence refused by the public adapter "
            "before any row is read (probe sink; no store writes occur)"
        ),
        "refusal": pairing_refusal,
    }

    # -- exact-key join facts read back from the public candidates ------------
    start, end = window["start"], window["end"]
    contract_candidates = {
        entry["candidate"]["source_label"]: entry["candidate"]
        for entry in contract_report["candidates"]
        if str(entry["candidate"].get("instrument")) == instrument
    }
    dominant_candidate_rows = [
        entry["candidate"]
        for entry in dominant_report["candidates"]
        if str(entry["candidate"].get("instrument")) == instrument
    ]
    dominant_by_label = {
        str(row["source_label"])[:19]: row for row in dominant_candidate_rows
    }
    in_window = [
        label
        for label in contract_candidates
        if start <= str(label)[:19] < end
    ]
    matched_window = [
        label
        for label in in_window
        if contract_candidates[label].get("trading_date")
    ]
    close_mismatches = 0
    for label in matched_window:
        dominant = dominant_by_label.get(str(label)[:19])
        if dominant is not None:
            contract_close = contract_candidates[label].get("close")
            if contract_close is not None and dominant.get("close") is not None:
                if float(contract_close) != float(dominant["close"]):
                    close_mismatches += 1
    frame["assertions"].append(
        assertion(
            "exact keyed join in window matches the 04IB-verified 1035 rows",
            section.get("expected_window_rows"),
            {
                "contract_candidates_in_window": len(in_window),
                "dominant_candidates_in_window": sum(
                    1
                    for label in dominant_by_label
                    if start <= label < end
                ),
                "matched_with_source_trading_date": len(matched_window),
            },
            len(in_window) == section.get("expected_window_rows")
            and len(matched_window) == section.get("expected_window_rows"),
        )
    )
    friday_results = []
    for check in section.get("friday_night", []):
        candidate = contract_candidates.get(check["label"])
        friday_results.append(
            {
                "label": check["label"],
                "expected_trading_date": check["trading_date"],
                "actual_trading_date": (
                    None if candidate is None else candidate.get("trading_date")
                ),
                "bounds_stay_null": candidate is not None
                and candidate["bar_start_ns"] is None,
                "pass": candidate is not None
                and candidate.get("trading_date") == check["trading_date"]
                and candidate["bar_start_ns"] is None,
            }
        )
    frame["assertions"].append(
        assertion(
            "Friday-night date transfer through the public date_mapper path",
            True,
            friday_results,
            bool(friday_results) and all(check["pass"] for check in friday_results),
        )
    )
    mapper_stats = contract_report["adapter_receipt"]["trading_date_transfer"] or {}
    frame["assertions"].append(
        assertion(
            "duplicate mapping keys and close mismatches stay zero in window",
            {"duplicate_keys": 0, "close_mismatches": 0},
            {
                "duplicate_keys": frame["dominant_mapping_member_scope"][
                    "duplicate_keys"
                ],
                "close_mismatches": close_mismatches,
            },
            frame["dominant_mapping_member_scope"]["duplicate_keys"] == 0
            and close_mismatches == 0,
        )
    )
    frame["assertions"].append(
        assertion(
            "unmatched contract keys keep trading_date NULL (candidate, honest)",
            mapper_stats.get("unmatched_keys"),
            sum(
                1
                for entry in contract_report["candidates"]
                if str(entry["candidate"].get("instrument")) == instrument
                and entry["candidate"].get("trading_date") is None
            ),
            mapper_stats.get("unmatched_keys")
            == sum(
                1
                for entry in contract_report["candidates"]
                if str(entry["candidate"].get("instrument")) == instrument
                and entry["candidate"].get("trading_date") is None
            ),
        )
    )

    # -- isolation, candidate retention, no canonical publication -------------
    dataset_contract = contract_report["dataset_id"]
    dataset_dominant = dominant_report["dataset_id"]
    frame["assertions"].append(
        assertion(
            "contract and dominant-series dataset identities are isolated",
            {"datasets_differ": True, "series_kinds": ["instrument", "dominant"]},
            {
                "datasets_differ": dataset_contract != dataset_dominant,
                "series_kinds": [
                    contract_report["spec"].series_kind,
                    dominant_report["spec"].series_kind,
                ],
            },
            dataset_contract != dataset_dominant
            and contract_report["spec"].series_kind == "instrument"
            and dominant_report["spec"].series_kind == "dominant",
        )
    )
    for side, report in (
        ("contract", contract_report),
        ("dominant", dominant_report),
    ):
        summary = report["summary"]
        counts = summary["counts"]
        frame["assertions"].append(
            assertion(
                f"{side}: all rows retained on the public candidate path, "
                "nothing published",
                {
                    "candidate_rows": counts["input_rows"],
                    "publish_state": "no_publishable_rows",
                },
                {
                    "candidate_rows": counts["candidate_rows"],
                    "publish_state": summary["publish"]["state"],
                },
                counts["candidate_rows"] == counts["input_rows"]
                and counts["input_rows"] > 0
                and summary["publish"]["state"] == "no_publishable_rows",
            )
        )
    store_batches = store.catalog.query_all(
        "SELECT batch_id FROM batches WHERE batch_id LIKE 'delivery04l-rq-%'"
    )
    datasets_after = store.catalog.query_one("SELECT COUNT(*) AS n FROM datasets")["n"]
    store.close()
    frame["assertions"].append(
        assertion(
            "no canonical futures batch/dataset entered the store",
            {"futures_batches": 0, "datasets_delta": 0},
            {
                "futures_batches": len(store_batches),
                "datasets_delta": datasets_after - datasets_before,
            },
            len(store_batches) == 0 and datasets_after == datasets_before,
        )
    )

    frame["store_id"] = store_id
    frame["outputs"] = {
        "generation": "04L-public-api (04K diagnostic kept separate)",
        "dataset_id_contract_unpublished": dataset_contract,
        "dataset_id_dominant_unpublished": dataset_dominant,
        "spec_ids_by_declared_label": spec_ids,
        "candidates": {
            side: {
                "candidate_file": report["summary"]["candidate_file"],
                "candidate_sha256": (
                    sha256_file(report["summary"]["candidate_file"])
                    if report["summary"]["candidate_file"]
                    else None
                ),
                "rows": report["summary"]["counts"]["candidate_rows"],
                "failures": report["summary"]["failures"],
            }
            for side, report in candidate_reports.items()
        },
        "adapter_receipts": {
            side: report["adapter_receipt"]
            for side, report in candidate_reports.items()
        },
        "join_from_candidates": {
            "contract_candidates_in_window": len(in_window),
            "matched_with_source_trading_date": len(matched_window),
            "close_mismatches": close_mismatches,
            "friday_night_checks": friday_results,
        },
        "published": False,
    }
    frame["coverage"] = {
        "observed": (
            f"{len(in_window)} contract and "
            f"{sum(1 for label in dominant_by_label if start <= label < end)} "
            f"dominant {instrument} candidates in the assigned window; "
            f"{contract_report['summary']['counts']['candidate_rows']} "
            "contract and "
            f"{dominant_report['summary']['counts']['candidate_rows']} "
            "dominant rows retained as candidates from the located members"
        ),
        "expected": (
            "UNKNOWN: label direction UNKNOWN per 04IB; no session calendar "
            "or multiplier history evidenced; expected stays unknown and no "
            "canonical bounds exist"
        ),
    }
    frame["limitations"].extend(
        [
            (
                "One contract, two bounded members; A2505 rows in other hash "
                "shards were not scanned, so presence outside the located "
                "members is UNKNOWN, not zero."
            ),
            (
                "Multiplier 10 and sampled turnover arithmetic remain "
                "observations from the 2026-08-03 universe snapshot; "
                "historical validity for the window is UNKNOWN."
            ),
            (
                "Dominant roll/selection rule unknown (rule_version empty); "
                "continuous prices were never substituted for the contract."
            ),
            (
                "The real A2505 window stays a source candidate: no "
                "FuturesLabelScope exists for it because no independent label "
                "evidence has been accepted; synthetic scoped conversion is "
                "proven by focused tests only."
            ),
        ]
    )
    return frame

# ---------------------------------------------------------------------------
# Case 3 — JQ holographic daily 33-column sample
# ---------------------------------------------------------------------------


def run_jq(config: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    from research_store import (
        AssetRef,
        Selection,
        SnapshotRequest,
        freeze,
        open_snapshot,
        open_store,
    )
    from research_store.importers.adapters import import_jq_daily
    from research_store.importers.core_bridge import build_jq_daily_spec
    from research_store.importers.safeio import iter_gzip_csv_chunks
    from research_store.importers.store_sink import StoreSink

    section = config["jq"]
    daily_dir = Path(section["daily_dir"])
    year = int(section["year"])
    instrument = section["instrument"]
    window = section["window"]
    reports_dir = Path(config["reports_dir"])

    members = sorted(daily_dir.glob(f"all_a_daily_{year}.csv.gz"))
    if len(members) != 1:
        raise SystemExit(f"expected exactly one gzip member for {year}: {members}")
    member = members[0]
    member_sha = sha256_file(member)

    total_rows = 0
    instrument_rows: list[dict[str, str]] = []
    sample_row: dict[str, str] | None = None
    sample_columns: list[str] | None = None
    null_fields_in_sample = 0
    for chunk in iter_gzip_csv_chunks(member, chunk_rows=100_000):
        total_rows += len(chunk)
        for raw in chunk:
            if raw.get("code") == instrument:
                instrument_rows.append(raw)
                if sample_row is None:
                    sample_row = raw
                    sample_columns = list(raw.keys())
                    null_fields_in_sample = sum(
                        1 for value in raw.values() if value == "" or value is None
                    )
    frame["member_scan"] = {
        "member": member.name,
        "member_sha256": member_sha,
        "member_bytes": member.stat().st_size,
        "total_rows": total_rows,
        f"rows_for_{instrument}": len(instrument_rows),
        "columns": sample_columns,
        "column_count": len(sample_columns or []),
    }
    frame["assertions"].append(
        assertion(
            "gzip member carries the documented 33 columns",
            33,
            len(sample_columns or []),
            len(sample_columns or []) == 33,
        )
    )

    store = open_store(str(Path(config["store_root"]).resolve()))
    store_id = store.store_id
    batch_id = "delivery04k-jq-daily-sample"
    spec = build_jq_daily_spec()
    asset = AssetRef(
        asset_id=f"asset-jq-{member_sha[:16]}",
        origin=str(member),
        format="gzip_csv",
        size=member.stat().st_size,
        sha256=member_sha,
    )
    sink = StoreSink(
        store,
        asset,
        spec,
        adapter="jq_daily/0.1",
        config={
            "member": member.name,
            "member_sha256": member_sha,
            "year": str(year),
            "instrument_scope": instrument,
            "member_total_rows": str(total_rows),
        },
        batch_id=batch_id,
        candidate_dir=reports_dir / "candidates",
    )
    receipt = import_jq_daily(
        daily_dir,
        sink,
        batch_id,
        years=[year],
        instruments={instrument},
    )
    publish = sink.publish()
    summary = sink.summary(publish)
    dataset_id = summary["dataset_id"]
    snapshot_ref = freeze(
        store,
        SnapshotRequest(
            selections=(Selection(dataset_id, "*"),),
            required_fields=("open", "high", "low", "close", "volume"),
        ),
    )
    snapshot_id = snapshot_ref.snapshot_id

    start_utc = shanghai_label_to_utc(window["start"])
    end_utc = shanghai_label_to_utc(window["end"])
    reader = open_snapshot(store, snapshot_id)
    readback: dict[str, dict[str, Any]] = {}
    for batch in reader.bars(
        dataset_id,
        instruments=[instrument],
        start=start_utc,
        end=end_utc,
        required_fields=("open", "high", "low", "close", "volume"),
    ):
        for row in batch.to_pylist():
            readback[str(row["trading_date"])] = row
    reader.close()
    store.close()

    window_expected = [
        raw for raw in instrument_rows if window["start"] <= raw["date"] < window["end"]
    ]
    frame["assertions"].append(
        assertion(
            "public query readback count equals source rows in window",
            len(window_expected),
            len(readback),
            len(readback) == len(window_expected) and bool(window_expected),
        )
    )
    field_check: dict[str, Any] = {"ok": False, "details": {}}
    if sample_row is not None and sample_row["date"] in readback:
        row = readback[sample_row["date"]]
        canonical = {"code", "date", "open", "high", "low", "close", "volume", "money"}
        extensions = json.loads(row["extensions_json"] or "{}")
        mismatched = [
            key
            for key, value in sample_row.items()
            if key not in canonical and extensions.get(key) != value
        ]
        try:
            factor_is_one = float(extensions.get("factor", "nan")) == 1.0
        except (TypeError, ValueError):
            factor_is_one = False
        field_check = {
            "ok": not mismatched and factor_is_one,
            "mismatched_fields": mismatched,
            "null_fields_preserved": null_fields_in_sample,
            "factor_verbatim": extensions.get("factor"),
            "factor_is_one": factor_is_one,
            "adjustment_status": extensions.get("adjustment_status"),
        }
    frame["assertions"].append(
        assertion(
            "every non-OHLCV source field preserved verbatim (incl. NULLs, factor)",
            True,
            field_check,
            bool(field_check.get("ok")),
        )
    )
    frame["assertions"].append(
        assertion(
            "dataset adjustment stays UNKNOWN (factor all 1.0)",
            "unknown",
            spec.adjustment.value,
            spec.adjustment.value == "unknown",
        )
    )

    frame["store_id"] = store_id
    frame["outputs"] = {
        "import": summary,
        "adapter_receipt": {
            "rows_read": receipt.rows_read,
            "rows_accepted": receipt.rows_accepted,
            "members_ok": receipt.members_ok,
        },
        "dataset_id": dataset_id,
        "snapshot_id": snapshot_id,
        "sample_source_row": sample_row,
        "sample_field_check": field_check,
    }
    frame["coverage"] = {
        "observed": (
            f"{len(instrument_rows)} daily rows for {instrument} in the {year} "
            f"member; {len(readback)} read back in the query window"
        ),
        "expected": (
            "UNKNOWN: no trading calendar/listing/suspension evidence for this "
            "security is established locally; observed range is not completeness"
        ),
    }
    frame["limitations"].append(
        "Query success is observational only: unknown adjustment blocks any "
        "default return-backtest qualification for this dataset."
    )
    return frame


# ---------------------------------------------------------------------------
# Case 4 — real ETF repaired base with the disputed key
# ---------------------------------------------------------------------------


def run_etf(config: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    from research_store import (
        AssetRef,
        KnownGap,
        Selection,
        SnapshotRequest,
        freeze,
        open_snapshot,
        open_store,
    )
    from research_store.importers.adapters import import_rq_etf
    from research_store.importers.core_bridge import build_rq_etf_spec
    from research_store.importers.repair_index import load_repair_index
    from research_store.importers.safeio import verify_sha256_sidecar
    from research_store.importers.store_sink import StoreSink

    section = config["etf"]
    package = Path(section["package_dir"])
    frequency = section["frequency"]
    year = int(section["year"])
    instrument = section["instrument"]
    disputed = section["disputed_key"]
    reports_dir = Path(config["reports_dir"])

    # Correction index loaded BEFORE the base archive (contract requirement).
    index = load_repair_index(package, section.get("audit_csv"))
    frame["repair_index"] = index.stats()
    entry = index.get(disputed["instrument"], disputed["label"])
    entry_ok = entry is not None and entry.disputed
    frame["assertions"].append(
        assertion(
            "disputed key present in the current-source correction index",
            {"present": True, "disputed": True},
            {
                "present": entry is not None,
                "disputed": None if entry is None else entry.disputed,
            },
            entry_ok,
        )
    )
    if entry is not None:
        frame["disputed_entry"] = {
            "instrument": entry.instrument,
            "label": entry.label,
            "rule": entry.rule,
            "old": entry.old,
            "new": entry.new,
            "upstream_refetch": {
                key.removesuffix("_upstream_refetch"): value
                for key, value in (entry.upstream or {}).items()
                if key.endswith("_upstream_refetch")
            },
        }
    repaired_for_scope = sum(
        1
        for key in index.entries
        if key[0] == instrument and key[1].startswith(str(year))
    )

    archive = package / f"rqdatac_etf_lof_{frequency}_{year}.tar.zst"
    archive_sha = verify_sha256_sidecar(archive)

    store = open_store(str(Path(config["store_root"]).resolve()))
    store_id = store.store_id
    batch_id = "delivery04k-etf-repaired-base"
    spec = build_rq_etf_spec(frequency)
    asset = AssetRef(
        asset_id=f"asset-rq-etf-{archive_sha[:16]}",
        origin=str(archive),
        format="tar_zst_csv",
        size=archive.stat().st_size,
        sha256=archive_sha,
    )
    sink = StoreSink(
        store,
        asset,
        spec,
        adapter="rq_etf/0.1",
        config={
            "archive": archive.name,
            "archive_sha256": archive_sha,
            "frequency": frequency,
            "year": str(year),
            "instrument_scope": instrument,
            "repair_date": index.repair_date,
            "repair_index_loaded": "before base archive",
        },
        batch_id=batch_id,
        candidate_dir=reports_dir / "candidates",
    )
    receipt = import_rq_etf(
        package,
        sink,
        batch_id,
        frequency=frequency,
        years=[year],
        instruments={instrument},
        repair_index=index,
    )
    publish = sink.publish()
    summary = sink.summary(publish)
    dataset_id = summary["dataset_id"]

    # Snapshot WITHOUT any gap allowance: default qualified policy active.
    snapshot_ref = freeze(
        store,
        SnapshotRequest(
            selections=(Selection(dataset_id, "*"),),
            required_fields=("open", "high", "low", "close", "volume"),
        ),
    )
    snapshot_id = snapshot_ref.snapshot_id
    reader = open_snapshot(store, snapshot_id)
    exclusions = [
        e
        for e in reader.default_qualified_exclusions(dataset_id)
        if e.get("instrument") == instrument
    ]
    disputed_exclusion = next(
        (e for e in exclusions if e.get("source_label") == disputed["label"]), None
    )
    frame["assertions"].append(
        assertion(
            "freeze captures the repaired key(s) in default_qualified_exclusions",
            {"exclusions_for_scope": repaired_for_scope, "disputed_present": True},
            {
                "exclusions_for_scope": len(exclusions),
                "disputed_present": disputed_exclusion is not None,
            },
            disputed_exclusion is not None and len(exclusions) == repaired_for_scope,
        )
    )

    gap_start = datetime.fromtimestamp(
        int(disputed_exclusion["start_ns"]) / 1_000_000_000, tz=timezone.utc
    )
    gap_end = datetime.fromtimestamp(
        int(disputed_exclusion["end_ns"]) / 1_000_000_000, tz=timezone.utc
    )
    refused_error: str | None = None
    try:
        for _batch in reader.bars(
            dataset_id,
            instruments=[instrument],
            start=gap_start - timedelta(minutes=1),
            end=gap_end + timedelta(minutes=1),
        ):
            pass
    except Exception as exc:  # noqa: BLE001 - the refusal itself is the evidence
        refused_error = f"{type(exc).__name__}: {exc}"
    frame["assertions"].append(
        assertion(
            "qualified read intersecting the disputed key is refused",
            "CoverageGapError",
            (refused_error or "no error").split(":", 1)[0],
            bool(refused_error) and refused_error.startswith("CoverageGapError"),
        )
    )

    day_text = disputed["label"][:10]
    day_start = shanghai_label_to_utc(f"{day_text} 00:00:00")
    day_end = day_start + timedelta(days=1)
    observational_rows: list[dict[str, Any]] = []
    for batch in reader.bars(
        dataset_id,
        instruments=[instrument],
        start=day_start,
        end=day_end,
        required_fields=("open", "high", "low", "close", "volume"),
        include_default_excluded=True,
    ):
        observational_rows.extend(batch.to_pylist())
    disputed_row = next(
        (row for row in observational_rows if row["source_label"] == disputed["label"]),
        None,
    )
    dispute_values_ok = False
    dispute_extension: dict[str, Any] | None = None
    if disputed_row is not None:
        # to_core_row keeps the repair provenance in field_quality (next to
        # the flags), the remaining source columns in extensions_json.
        quality = json.loads(disputed_row["field_quality"] or "{}")
        extensions = json.loads(disputed_row["extensions_json"] or "{}")
        repair = quality.get("repair") or extensions.get("repair") or {}
        upstream = repair.get("upstream_refetch") or {}
        dispute_extension = {
            "rule": repair.get("rule"),
            "repaired_volume": disputed_row["volume"],
            "repaired_amount": disputed_row["turnover"],
            "upstream_refetch": upstream,
            "flags": quality.get("flags"),
        }
        dispute_values_ok = (
            disputed_row["volume"] == 0.0
            and disputed_row["turnover"] == 0.0
            and float(upstream.get("volume")) == 15000.0
            and float(upstream.get("amount")) == 15840.0
        )
    frame["assertions"].append(
        assertion(
            "observational read keeps repaired 0/0 with old/new/upstream candidates",
            {"present": True, "repaired": [0.0, 0.0], "upstream": [15000.0, 15840.0]},
            {
                "present": disputed_row is not None,
                "repaired": (
                    None
                    if disputed_row is None
                    else [disputed_row["volume"], disputed_row["turnover"]]
                ),
                "extension": dispute_extension,
            },
            dispute_values_ok,
        )
    )
    reader.close()

    # Second snapshot: ONLY the disputed interval explicitly allowed.
    snapshot_allowed = freeze(
        store,
        SnapshotRequest(
            selections=(Selection(dataset_id, "*"),),
            required_fields=("open", "high", "low", "close", "volume"),
            allow_known_gaps=(
                KnownGap(
                    dataset_id,
                    int(disputed_exclusion["start_ns"]),
                    int(disputed_exclusion["end_ns"]),
                    reason=(
                        "disputed repaired key 160105.XSHE 2017-09-19 13:01 kept "
                        "out of default qualified data; repaired 0/0 vs upstream "
                        "15000/15840 candidates preserved; gap visible"
                    ),
                ),
            ),
        ),
    )
    reader2 = open_snapshot(store, snapshot_allowed.snapshot_id)
    qualified_rows: list[dict[str, Any]] = []
    for batch in reader2.bars(
        dataset_id,
        instruments=[instrument],
        start=day_start,
        end=day_end,
        required_fields=("open", "high", "low", "close", "volume"),
    ):
        qualified_rows.extend(batch.to_pylist())
    disputed_still_gone = all(
        row["source_label"] != disputed["label"] for row in qualified_rows
    )
    frame["assertions"].append(
        assertion(
            "allowed-gap snapshot reads the day minus exactly the disputed row",
            {
                "qualified_rows": len(observational_rows) - 1,
                "disputed_present": False,
            },
            {
                "qualified_rows": len(qualified_rows),
                "disputed_present": not disputed_still_gone,
            },
            len(qualified_rows) == len(observational_rows) - 1 and disputed_still_gone,
        )
    )
    # The next day still carries its default-qualified exclusions: a plain
    # qualified read refuses them (no global allowance), while the
    # observational count shows the rows are there, inspectable.
    next_day_start = day_end
    next_day_end = next_day_start + timedelta(days=1)
    next_day_observational = 0
    next_refusal: str | None = None
    try:
        for batch in reader2.bars(
            dataset_id,
            instruments=[instrument],
            start=next_day_start,
            end=next_day_end,
            required_fields=("open", "high", "low", "close", "volume"),
        ):
            next_day_observational += batch.num_rows
    except Exception as exc:  # noqa: BLE001 - refusal is acceptable evidence
        next_refusal = f"{type(exc).__name__}: {exc}"
    next_day_observational_count = 0
    for batch in reader2.bars(
        dataset_id,
        instruments=[instrument],
        start=next_day_start,
        end=next_day_end,
        required_fields=("open", "high", "low", "close", "volume"),
        include_default_excluded=True,
    ):
        next_day_observational_count += batch.num_rows
    frame["assertions"].append(
        assertion(
            "no global gap allowance: away from the allowed interval the "
            "snapshot behaves normally (qualified next-day read returns the "
            "full observational count when no other repaired key exists "
            "there; a refusal would be the honest outcome if one did)",
            {
                "observational_next_day_rows": next_day_observational_count,
                "qualified_next_day_rows": next_day_observational_count,
            },
            {
                "observational_next_day_rows": next_day_observational_count,
                "qualified_next_day_rows": (
                    None if next_refusal else next_day_observational
                ),
                "qualified_refusal": next_refusal,
                "other_repaired_keys_in_scope": repaired_for_scope - 1,
            },
            next_day_observational_count > 0
            and (
                next_refusal is not None
                or next_day_observational == next_day_observational_count
            ),
        )
    )
    reader2.close()
    store.close()

    frame["store_id"] = store_id
    frame["outputs"] = {
        "import": summary,
        "adapter_receipt": {
            "rows_read": receipt.rows_read,
            "rows_accepted": receipt.rows_accepted,
            "members_ok": receipt.members_ok,
            "members_failed": receipt.members_failed,
            "repair_stats": receipt.extras.get("repair_stats"),
        },
        "dataset_id": dataset_id,
        "snapshot_id_strict": snapshot_id,
        "snapshot_id_allowed_gap": snapshot_allowed.snapshot_id,
        "exclusions_for_scope": len(exclusions),
        "disputed_gap_ns": [
            int(disputed_exclusion["start_ns"]),
            int(disputed_exclusion["end_ns"]),
        ]
        if disputed_exclusion
        else None,
        "qualified_refusal": refused_error,
        "next_day": {
            "observational_rows": next_day_observational_count,
            "qualified_refusal": next_refusal,
        },
    }
    frame["coverage"] = {
        "observed": (
            f"{summary['counts']['accepted_rows']} accepted 1m rows for "
            f"{instrument} {year}; qualified day read "
            f"{len(qualified_rows)}/{len(observational_rows)} rows around the "
            "disputed key"
        ),
        "expected": (
            "UNKNOWN: no session calendar evidence for this ETF; min/max is "
            "not completeness"
        ),
    }
    frame["limitations"].append(
        "Only the one disputed interval was allowed in the second snapshot; "
        "every other repaired key stays default-excluded with visible gaps."
    )
    return frame


# ---------------------------------------------------------------------------
# Case 5 — P4 catalog-only truth
# ---------------------------------------------------------------------------


def run_catalog(config: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    from research_store import open_store
    from research_store.importers.inventory import HOLO_CAVEATS, scan_rq_package
    from research_store.importers.safeio import file_sha256, read_sha256_sidecar

    section = config["catalog"]
    rq_root = Path(section["rq_root"])

    inventory04d_path = Path(section["inventory04d"])
    inventory04d = json.loads(inventory04d_path.read_text(encoding="utf-8"))
    frame["inventory04d"] = {
        "path": str(inventory04d_path),
        "sha256": sha256_file(inventory04d_path),
        "generated_at": inventory04d.get("generated_at"),
        "rq_packages": {
            pkg["package"]: {
                "listed": pkg["archives_listed"],
                "missing": pkg["archives_missing"],
            }
            for pkg in inventory04d["roots"]["rq_packages"]
        },
    }

    store = open_store(str(Path(config["store_root"]).resolve()))
    datasets_before = store.catalog.query_one("SELECT COUNT(*) AS n FROM datasets")["n"]
    store.close()

    # (a) preferred shares: re-derive the missing year archives (no hashing)
    pit_dir = rq_root / section["pit_package"]
    pit_scan = scan_rq_package(pit_dir)
    missing_names = set(pit_scan.missing_archives)
    missing_by_dataset: dict[str, int] = {}
    missing_years: set[str] = set()
    for record in pit_scan.archives:
        if record.get("file") in missing_names:
            dataset = str(record.get("dataset"))
            missing_by_dataset[dataset] = missing_by_dataset.get(dataset, 0) + 1
            year_match = re.search(r"(\d{4})", str(record.get("file", "")))
            if year_match:
                missing_years.add(year_match.group(1))
    frame["pit"] = {
        "package": pit_dir.name,
        "listed": len(pit_scan.archives),
        "missing": len(pit_scan.missing_archives),
        "missing_by_dataset": missing_by_dataset,
        "missing_years": sorted(missing_years),
        "failed_records": [
            str(item) for item in getattr(pit_scan, "failed_records", [])
        ],
        "shares_dir_exists": (pit_dir / "shares").exists(),
    }
    expected_missing = section.get("expected_pit_missing")
    frame["assertions"].append(
        assertion(
            "preferred-shares years missing from the PIT package (older-source "
            "fallback unverified)",
            expected_missing,
            {"missing": len(pit_scan.missing_archives), "datasets": missing_by_dataset},
            expected_missing in (None, len(pit_scan.missing_archives))
            and set(missing_by_dataset) == {"shares"},
        )
    )

    # (b) index 2014 archive: actual sha vs sidecar vs root manifest
    index_dir = rq_root / section["index_package"]
    index_archive = index_dir / section["index_2014_archive"]
    actual_sha = file_sha256(index_archive)
    sidecar_sha = read_sha256_sidecar(Path(str(index_archive) + ".sha256"))
    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_sha = next(
        (
            entry["sha256"]
            for entry in manifest.get("archives", [])
            if isinstance(entry, dict) and entry.get("file") == index_archive.name
        ),
        None,
    )
    frame["index_2014"] = {
        "archive": index_archive.name,
        "bytes": index_archive.stat().st_size,
        "sha256_actual": actual_sha,
        "sha256_sidecar": sidecar_sha,
        "sha256_root_manifest": manifest_sha,
    }
    frame["assertions"].append(
        assertion(
            "index 2014: actual sha matches sidecar but differs from root "
            "manifest (version conflict preserved, not corruption)",
            {"actual_eq_sidecar": True, "actual_ne_manifest": True},
            {
                "actual_eq_sidecar": actual_sha == sidecar_sha,
                "actual_ne_manifest": manifest_sha is not None
                and actual_sha != manifest_sha,
            },
            actual_sha == sidecar_sha
            and manifest_sha is not None
            and actual_sha != manifest_sha,
        )
    )

    # (c) convertible 4911-row refetch overlay/audit missing locally
    conv_dir = rq_root / section["convertible_package"]
    conv_manifest_path = conv_dir / section["convertible_refetch_manifest"]
    conv_manifest = json.loads(conv_manifest_path.read_text(encoding="utf-8"))
    declared = [
        entry
        for entry in conv_manifest.get("files", [])
        if str(entry.get("path", "")).startswith("03_convertible")
    ]
    supplement_root = conv_manifest_path.parent
    present_declared: list[str] = []
    missing_declared: list[dict[str, Any]] = []
    for entry in declared:
        target = supplement_root / entry["path"]
        if target.is_file():
            present_declared.append(entry["path"])
        else:
            missing_declared.append(
                {
                    "path": entry["path"],
                    "bytes_declared": entry.get("bytes"),
                    "sha256_declared": entry.get("sha256"),
                }
            )
    rows_declared = (
        conv_manifest.get("datasets", {}).get("03_convertible", {}).get("input_change_rows")
    )
    frame["convertible"] = {
        "refetch_manifest": str(conv_manifest_path),
        "sha256": sha256_file(conv_manifest_path),
        "input_change_rows_declared": rows_declared,
        "declared_files": len(declared),
        "present_locally": present_declared,
        "missing_locally": missing_declared,
    }
    frame["assertions"].append(
        assertion(
            "convertible 4911-row refetch overlay/audit declared but absent "
            "locally (catalog-only candidate)",
            {"rows": 4911, "missing_declared_files": len(declared)},
            {"rows": rows_declared, "missing_declared_files": len(missing_declared)},
            rows_declared == 4911
            and len(missing_declared) == len(declared)
            and bool(declared),
        )
    )

    # (d) PIT knowledge-time ambiguity stays an explicit, preserved UNKNOWN
    frame["pit_knowledge_time"] = {
        "status": "UNKNOWN_PRESERVED",
        "fact": (
            "Same report quarter appears with info_date 2025-04-19 and "
            "2026-04-25 in the source PIT sample (execution contract); "
            "knowledge time is therefore ambiguous without announcement-level "
            "evidence, and upserts by (security, quarter) only are forbidden."
        ),
        "verification": (
            "catalog-only in v0.1; no bounded import or member de-archiving "
            "was performed in this case, so the fact stays at documented "
            "inventory level (inventory04D / HOLO_CAVEATS), not row-verified here"
        ),
    }

    store = open_store(str(Path(config["store_root"]).resolve()))
    datasets_after = store.catalog.query_one("SELECT COUNT(*) AS n FROM datasets")["n"]
    store.close()
    frame["assertions"].append(
        assertion(
            "catalog-only case created no datasets/batches (no import)",
            datasets_before,
            datasets_after,
            datasets_before == datasets_after,
        )
    )
    frame["documented_caveats"] = list(HOLO_CAVEATS)
    frame["coverage"] = {
        "observed": "catalog/archive-presence level only; no bars imported",
        "expected": (
            "UNKNOWN for every category here (calendar/listing/announcement "
            "evidence absent)"
        ),
    }
    frame["limitations"].append(
        "These categories stay catalog-only/candidates: no import capability "
        "was demonstrated for them and none is claimed."
    )
    return frame


# ---------------------------------------------------------------------------
# Case 0 — environment; and the aggregation report
# ---------------------------------------------------------------------------


def run_env(config: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    import platform

    frame["environment"] = {
        "python": sys.version,
        "platform": platform.platform(),
        "executable": sys.executable,
        "cwd": os.getcwd(),
    }
    dependencies: dict[str, str] = {}
    for name in ("pyarrow", "duckdb", "zstandard", "polars", "pandas", "psutil"):
        try:
            module = __import__(name)
            dependencies[name] = str(getattr(module, "__version__", "unknown"))
        except Exception as exc:  # noqa: BLE001
            dependencies[name] = f"unavailable: {exc}"
    frame["dependencies"] = dependencies
    frame["research_store_version"] = __import__("research_store").__version__
    git_head = Path("D:/repo/vnpy/.git/HEAD")
    if git_head.is_file():
        ref = git_head.read_text(encoding="utf-8").strip()
        frame["git_head_ref"] = ref
        ref_path = git_head.parent / ref.split("ref: ")[-1]
        if ref_path.is_file():
            frame["git_head"] = ref_path.read_text(encoding="utf-8").strip()
    from research_store import open_store

    store = open_store(str(Path(config["store_root"]).resolve()))
    frame["store"] = {
        "root": str(store.root),
        "store_id": store.store_id,
        "never_reinitialized": True,
    }
    store.close()
    frame["assertions"].append(
        assertion(
            "runner runs inside the plugin .venv",
            True,
            sys.executable,
            "venv" in sys.executable.lower(),
        )
    )
    return frame


def run_report(config: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    reports_dir = Path(config["reports_dir"])
    cases: dict[str, Any] = {}
    for case in ("env", "stock", "futures", "jq", "etf", "catalog"):
        path = reports_dir / f"{case}.json"
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            cases[case] = {
                "status": payload.get("status"),
                "sha256": sha256_file(path),
                "elapsed_seconds": payload.get("elapsed_seconds"),
                "assertions_failed": [
                    a["name"] for a in payload.get("assertions", []) if not a["pass"]
                ],
            }
    software_failures: list[str] = []
    source_limitations: list[str] = []
    for case in cases:
        detail = json.loads((reports_dir / f"{case}.json").read_text(encoding="utf-8"))
        for failure in detail.get("software_failures", []):
            software_failures.append(f"{case}: {failure}")
        for limitation in detail.get("limitations", []):
            source_limitations.append(f"{case}: {limitation}")
    frame["cases"] = cases
    frame["software_failures"] = software_failures
    frame["source_data_limitations"] = source_limitations
    frame["claim"] = {
        "first_usable_etf_native_snapshot": (
            "NOT_CLAIMED (owned by delivery04F/final delivery owner)"
        ),
        "full_WP10": "NOT_CLAIMED",
        "futures_canonical_bars": (
            "NOT_PUBLISHED: label direction UNKNOWN per 04IB; candidate path "
            "only, defect repro returned to root"
        ),
        "scope": (
            "bounded representative real-source evidence per "
            "TASK_OPENCODE_DELIVERY_REPRESENTATIVES_04K.md"
        ),
    }
    frame["status"] = (
        "PASS"
        if cases and all(c.get("status") == "PASS" for c in cases.values())
        else "PARTIAL"
    )
    return frame


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--case", required=True, choices=CASES)
    args = parser.parse_args(argv)

    config, identity = load_config(args.config)
    reports_dir = Path(config["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)

    runners = {
        "env": run_env,
        "stock": run_stock,
        "futures": run_futures,
        "jq": run_jq,
        "etf": run_etf,
        "catalog": run_catalog,
        "report": run_report,
    }
    frame = new_case_frame(args.case, args.config, identity)
    started = time.perf_counter()
    try:
        frame = runners[args.case](config, frame)
    except Exception as exc:  # noqa: BLE001 - record and fail loudly
        frame["software_failures"].append(f"{type(exc).__name__}: {exc}")
        import traceback

        frame["traceback"] = traceback.format_exc()
    frame = finish_case_frame(frame, started)
    evidence_path = reports_dir / f"{args.case}.json"
    write_json_atomic(evidence_path, frame)
    print(
        json.dumps(
            frame, indent=2, sort_keys=True, ensure_ascii=False, default=str
        )
    )
    if frame["status"].startswith("FAIL_SOFTWARE"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
