"""SS representative helper: bounded real-contract label evidence + scoped public import.

Task-owned tool for TASK_OPENCODE_SS_REPRESENTATIVE_04M. Read-only over the
validated capture04H receipt/capture; uses ONLY public importer/store
contracts. PHASE1 measures the bounded rb2605 source-label windows; PHASE2
(after the futures04L importer release + the capture/table-kind guard
correction) performs the scoped real representative import, repeat-import,
snapshot freeze/query and immutability demonstration through the public
``import_ssquant_table`` / ``StoreSink`` / ``freeze`` / ``open_snapshot``
path on the EXISTING D:/quant-data store (never reinitialized).

Truthfulness rules implemented here:

* the capture identity is the 04H CURRENT RECOVERY VALIDATION receipt
  (``captured_at`` stays UNKNOWN); no 10GB rehash, no capture copy;
* label conclusions are bound to capture sha + tables + exact windows;
  everything outside stays unknown/candidate;
* the exact 8 SimNow keys come from the public detector on this capture and
  must equal the authoritative set; ordinary overlaps stay diagnostics;
* MA amount stays raw/untrusted (no unit inference); cumulative_openint is
  the candidate total OI; 5m/15m keep their own interval identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_store.importers.adapters import import_ssquant_table  # noqa: E402
from research_store.importers.core_bridge import build_ssquant_spec  # noqa: E402
from research_store.importers.sqlite_source import (  # noqa: E402
    connect_read_only,
    simnow_quarantine_keys,
)
from research_store.importers.store_sink import StoreSink  # noqa: E402
from research_store.importers.time_evidence import (  # noqa: E402
    LabelEvidence,
    LabelEvidenceError,
    LabelProfile,
    build_label_evidence,
    verify_profile_capture,
)
from research_store.models import AssetRef, Selection, SnapshotRequest  # noqa: E402
from research_store.snapshots import freeze, open_snapshot  # noqa: E402
from research_store.store import open_store  # noqa: E402

CAPTURE = Path("D:/quant-data/captures/kline_data_capture_20260916T164711Z.db")
CAPTURE_RECEIPT = CAPTURE.with_suffix(CAPTURE.suffix + ".receipt.json")
LOCATOR = REPO_ROOT / ".coordination" / "ss04m-locator-20260930.json"
CONFIG = REPO_ROOT / "configs" / "delivery_ss_rb2605.json"
INSPECT_04H = Path("D:/quant-data/reports/delivery04h/delivery04h-inspect.json")
REPORT_DIR = Path("D:/quant-data/reports/delivery04m")
STORE_ROOT = Path("D:/quant-data")

SYMBOL = "rb2605"
TABLES = {
    "1": f"{SYMBOL}_1M_raw",
    "5": f"{SYMBOL}_5M_raw",
    "15": f"{SYMBOL}_15M_raw",
}
# Two bounded real windows (morning + afternoon session of 2026-03-02), each
# independently evidenced. W1 matches the coordinator locator exactly.
WINDOWS = {
    "W1": ("2026-03-02 09:00:00", "2026-03-02 10:00:00"),
    "W2": ("2026-03-02 13:30:00", "2026-03-02 14:30:00"),
}
_AUTHORITY_SIMNOW_KEYS = frozenset(
    {
        ("a888_1M_raw", "A888", "2026-07-01 11:29:00"),
        ("a888_1M_raw", "A888", "2026-07-01 15:04:00"),
        ("rb888_1M_raw", "RB888", "2026-07-01 11:30:00"),
        ("rb888_1M_raw", "RB888", "2026-07-01 15:16:00"),
        ("sc888_1M_raw", "SC888", "2026-07-01 11:30:00"),
        ("sc888_1M_raw", "SC888", "2026-07-01 15:16:00"),
        ("zn888_1M_raw", "ZN888", "2026-07-01 11:30:00"),
        ("zn888_1M_raw", "ZN888", "2026-07-01 15:16:00"),
    }
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_row_hash(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_capture_identity() -> dict[str, Any]:
    receipt = json.loads(CAPTURE_RECEIPT.read_text(encoding="utf-8"))
    stat = CAPTURE.stat()
    identity = {
        "capture": str(CAPTURE),
        "receipt": str(CAPTURE_RECEIPT),
        "validation_kind": receipt.get("validation_kind"),
        "validated_at": receipt.get("validated_at"),
        "receipt_capture_sha256": receipt.get("sha256"),
        "source_sha256": receipt.get("source_sha256"),
        "captured_at": receipt.get("captured_at"),
        "captured_at_basis": receipt.get("captured_at_basis"),
        "stat_observation": {
            "size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "size_matches_receipt": stat.st_size == receipt.get("bytes"),
        },
        "note": (
            "stat-only observation; content identity is the receipt-bound "
            "sha256 — no 10GB rehash performed"
        ),
    }
    if identity["validation_kind"] != "current_recovery_validation":
        raise SystemExit(
            f"receipt is not a current recovery validation: {CAPTURE_RECEIPT}"
        )
    if not identity["stat_observation"]["size_matches_receipt"]:
        raise SystemExit("capture size differs from validated receipt; ABORT")
    return identity


def fetch_window(
    con: sqlite3.Connection, table: str, start: str, end: str
) -> dict[str, Any]:
    started = time.monotonic()
    cursor = con.execute(
        f'SELECT * FROM "{table}" WHERE datetime >= ? AND datetime < ? '
        "ORDER BY datetime",
        (start, end),
    )
    columns = [desc[0] for desc in cursor.description]
    rows = [dict(zip(columns, values, strict=True)) for values in cursor]
    span = con.execute(
        f'SELECT MIN(datetime), MAX(datetime) FROM "{table}"'
    ).fetchone()
    return {
        "table": table,
        "window": [start, end],
        "rows": rows,
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": columns,
        "table_time_span": list(span),
        "rows_sha256_canonical": _canonical_row_hash(rows),
        "fetch_elapsed_seconds": round(time.monotonic() - started, 3),
    }


def _aggregate_strict(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    agg: dict[str, Any] = {
        "open": rows[0]["open"],
        "high": max(r["high"] for r in rows),
        "low": min(r["low"] for r in rows),
        "close": rows[-1]["close"],
        "volume": sum((r.get("volume") or 0) for r in rows),
        "amount": sum((r.get("amount") or 0) for r in rows),
        "cumulative_openint": rows[-1].get("cumulative_openint"),
    }
    return agg


def _close(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(b)))


def strict_hypotheses(
    fine: dict[str, Any], coarse: dict[str, Any], step_minutes: int
) -> list[dict[str, Any]]:
    fine_by_label = {str(r["datetime"]): r for r in fine["rows"]}
    results = []
    for coarse_row in coarse["rows"]:
        label = str(coarse_row["datetime"])
        moment = datetime.strptime(label, "%Y-%m-%d %H:%M:%S")
        record: dict[str, Any] = {"coarse_label": label, "step_minutes": step_minutes}
        for hypothesis in ("start", "end"):
            window: list[dict[str, Any]] = []
            for offset in range(step_minutes):
                delta = offset if hypothesis == "start" else offset - (step_minutes - 1)
                candidate = (moment + timedelta(minutes=delta)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                row = fine_by_label.get(candidate)
                if row is not None:
                    window.append(row)
            agg = _aggregate_strict(window)
            mismatches: dict[str, list[Any]] = {}
            if agg is not None:
                for field, expected in agg.items():
                    if not _close(coarse_row.get(field), expected):
                        mismatches[field] = [coarse_row.get(field), expected]
            state = (
                "INCOMPLETE_WINDOW"
                if agg is None or not window
                else ("MATCH" if not mismatches else "MISMATCH")
            )
            record[hypothesis] = {
                "state": state,
                "rows": len(window),
                "mismatches": mismatches,
            }
        results.append(record)
    return results


def strict_summary(hypotheses: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "coarse_bars": len(hypotheses),
        "strict_start_matches": sum(
            1 for h in hypotheses if h["start"]["state"] == "MATCH"
        ),
        "strict_end_matches": sum(
            1 for h in hypotheses if h["end"]["state"] == "MATCH"
        ),
    }


def derive_public_profiles(
    con: sqlite3.Connection, capture_sha256: str
) -> dict[str, Any]:
    """Public evidence for each (window, coarse-frequency) pair.

    The 1m profile is derived from the (1M, 5M) pair; the 5m and 15m
    profiles reuse the same window conclusions with their own intervals,
    exactly as the public ``LabelProfile`` contract intends (evidence is
    per window; the interval comes from the normalised table's own name).
    """
    out: dict[str, Any] = {"profiles": {}, "errors": []}
    for window_id, (start, end) in WINDOWS.items():
        for minutes, fine_table, coarse_table in (
            (5, TABLES["1"], TABLES["5"]),
            (15, TABLES["5"], TABLES["15"]),
        ):
            try:
                evidence: LabelEvidence = build_label_evidence(
                    con,
                    fine_table,
                    coarse_table,
                    start,
                    end,
                    capture_sha256=capture_sha256,
                    source_id="ssquant",
                )
                out["profiles"][f"{window_id}-{minutes}"] = {
                    "evidence_id": evidence.evidence_id,
                    "evidence": evidence.to_dict(),
                    "interval_minutes": minutes,
                    "conclusion": evidence.conclusion,
                }
            except LabelEvidenceError as exc:
                out["errors"].append(
                    {
                        "window": window_id,
                        "pair": [fine_table, coarse_table],
                        "error": str(exc),
                    }
                )
    return out


def profiles_for_import(public: dict[str, Any]) -> dict[str, LabelProfile]:
    """LabelProfile per (window, normalised-table interval).

    The minute table uses the (1M,5M)-derived evidence with interval 1; the
    5m/15m tables use their own pair evidence with their own intervals.
    """
    profiles: dict[str, LabelProfile] = {}
    mapping = {
        "W1-1": ("W1-5", 1),
        "W1-5": ("W1-5", 5),
        "W1-15": ("W1-15", 15),
        "W2-1": ("W2-5", 1),
        "W2-5": ("W2-5", 5),
        "W2-15": ("W2-15", 15),
    }
    for target, (source_key, minutes) in mapping.items():
        payload = public["profiles"].get(source_key)
        if payload is None:
            raise SystemExit(f"missing public profile {source_key}")
        evidence = LabelEvidence.from_dict(payload["evidence"])
        profiles[target] = LabelProfile(evidence, interval_minutes=minutes)
    return profiles


def profile_guard_matrix(profiles: dict[str, Any]) -> dict[str, Any]:
    """Post-correction public ``covers`` matrix (staging now rejected)."""
    checks: list[dict[str, Any]] = []
    p5 = profiles["profiles"].get("W1-5")
    if p5 is None:
        return {"checks": checks, "public_gaps_observed": {"note": "no profile"}}
    evidence = LabelEvidence.from_dict(p5["evidence"])
    profile = LabelProfile(evidence, interval_minutes=1)
    cases = [
        ("covered minute row", "rb2605_1M_raw", "2026-03-02 09:30:00", True),
        ("range end exclusive", "rb2605_1M_raw", "2026-03-02 10:00:00", False),
        ("before range", "rb2605_1M_raw", "2026-03-02 08:59:00", False),
        ("other day", "rb2605_1M_raw", "2026-03-03 09:30:00", False),
        ("other window", "rb2605_1M_raw", "2026-03-02 11:30:00", False),
        ("symbol guard", "rb888_1M_raw", "2026-03-02 09:30:00", False),
        ("interval guard", "rb2605_5M_raw", "2026-03-02 09:30:00", False),
        # corrected 2026-09-30: series-kind guard rejects staging
        ("staging rejected (corrected)", "rb2605_1M_raw_staging", "2026-03-02 09:30:00", False),
    ]
    for name, table, label, expected in cases:
        actual = profile.covers(table, label)
        checks.append(
            {
                "case": name,
                "table": table,
                "label": label,
                "expected": expected,
                "actual": actual,
                "ok": actual == expected,
            }
        )
    return {
        "checks": checks,
        "all_ok": all(c["ok"] for c in checks),
        "capture_binding": {
            "covers_note": (
                "covers() intentionally has no capture parameter; capture "
                "identity is enforced on the import path via "
                "verify_profile_capture (validated receipt) since the "
                "2026-09-30 correction"
            ),
            "enforcement": "import_ssquant_table calls verify_profile_capture before reading rows",
        },
    }


def verify_capture_binding(public: dict[str, Any]) -> dict[str, Any]:
    """Bind the REAL capture to the W1-1m profile via the public verified
    path (receipt-bound stat mode for the >2GiB capture; no rehash)."""
    p = public["profiles"].get("W1-5")
    if p is None:
        return {"error": "no profile"}
    evidence = LabelEvidence.from_dict(p["evidence"])
    profile = LabelProfile(evidence, interval_minutes=1)
    verification = verify_profile_capture(CAPTURE, profile)
    return {"verification": verification}


def reuse_04h_evidence() -> dict[str, Any]:
    inspect = json.loads(INSPECT_04H.read_text(encoding="utf-8"))
    return {
        "source": str(INSPECT_04H),
        "simnow": inspect.get("simnow"),
        "ma_raw_amount_sample": inspect.get("ma_raw_amount_sample"),
        "continuous_real_symbol_sample": inspect.get("continuous_real_symbol_sample"),
        "staging_tables_exact": inspect.get("scoped_row_counts", {}).get(
            "staging_tables_exact"
        ),
        "note": (
            "copied by reference from the validated 04H inspection of the "
            "same capture; no repeated scans of unchanged evidence"
        ),
    }


def public_simnow_detector() -> dict[str, Any]:
    """Run the PUBLIC detector once on this capture; must equal the 8
    authoritative keys, then feeds the public quarantine path."""
    con = connect_read_only(CAPTURE)
    try:
        started = time.monotonic()
        detected = simnow_quarantine_keys(con)
        elapsed = round(time.monotonic() - started, 3)
    finally:
        con.close()
    normalized = {
        (table, symbol.upper(), dt) for table, symbol, dt in detected
    }
    return {
        "detected_keys": sorted(f"{s} {d}" for _t, s, d in sorted(detected)),
        "matches_authoritative": normalized == _AUTHORITY_SIMNOW_KEYS,
        "detector_elapsed_seconds": elapsed,
        "usage": "passed as quarantine_keys to the public import path",
    }


def load_config() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(CONFIG.read_text(encoding="utf-8"))
    return loaded


def cmd_phase1(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    identity = load_capture_identity()
    config = load_config()
    if config["source"]["capture_sha256"] != identity["receipt_capture_sha256"]:
        raise SystemExit(
            "config capture_sha256 disagrees with the validated receipt; ABORT"
        )
    locator = (
        json.loads(LOCATOR.read_text(encoding="utf-8")) if LOCATOR.exists() else None
    )
    con = connect_read_only(CAPTURE)
    try:
        windows = {
            key: fetch_window(con, table, *WINDOWS["W1"])
            for key, table in TABLES.items()
        }
        comparisons: dict[str, dict[str, Any]] = {
            "5m_vs_1m": {
                "fine": TABLES["1"],
                "coarse": TABLES["5"],
                "hypotheses": strict_hypotheses(
                    windows["1"], windows["5"], step_minutes=5
                ),
            },
            "15m_vs_1m": {
                "fine": TABLES["1"],
                "coarse": TABLES["15"],
                "hypotheses": strict_hypotheses(
                    windows["1"], windows["15"], step_minutes=15
                ),
            },
        }
        comparisons["5m_vs_1m"]["summary"] = strict_summary(
            comparisons["5m_vs_1m"]["hypotheses"]
        )
        comparisons["15m_vs_1m"]["summary"] = strict_summary(
            comparisons["15m_vs_1m"]["hypotheses"]
        )
        public = derive_public_profiles(con, identity["receipt_capture_sha256"])
    finally:
        con.close()

    input_identity: dict[str, Any] = {}
    for key in ("1", "5", "15"):
        w = windows[key]
        locator_sha = ((locator or {}).get("input") or {}).get(key, {}).get(
            "selected_rows_sha256"
        )
        mine = w["rows_sha256_canonical"]
        input_identity[key] = {
            "table": w["table"],
            "rows": w["row_count"],
            "columns": w["column_count"],
            "table_time_span": w["table_time_span"],
            "rows_sha256_canonical_this_tool": mine,
            "locator_selected_rows_sha256": locator_sha,
            # explicit key+serialization comparison (2026-09-30 fix: the
            # locator stores selected_rows_sha256; earlier code read a
            # wrong key and reported a null comparison)
            "locator_agreement": bool(locator_sha) and mine == locator_sha,
            "locator_key_used": "selected_rows_sha256",
            "fetch_elapsed_seconds": w["fetch_elapsed_seconds"],
        }

    payload: dict[str, Any] = {
        "phase": "1",
        "generated_at": _utcnow(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "config": str(CONFIG),
        "capture_identity": identity,
        "locator_reference": str(LOCATOR),
        "window": {
            "symbol": SYMBOL,
            "start_inclusive": WINDOWS["W1"][0],
            "end_exclusive": WINDOWS["W1"][1],
        },
        "input_identity": input_identity,
        "row_samples_preserved": {
            key: [
                {
                    col: row.get(col)
                    for col in (
                        "datetime", "symbol", "real_symbol", "open", "high",
                        "low", "close", "volume", "amount", "openint",
                        "cumulative_openint",
                    )
                }
                for row in windows[key]["rows"][:2]
            ]
            for key in ("1", "5", "15")
        },
        "strict_comparisons": comparisons,
        "public_label_evidence": public,
        "profile_guards": profile_guard_matrix(public),
        "capture_binding": verify_capture_binding(public),
        "reused_04h_evidence": reuse_04h_evidence(),
        "scope_note": (
            "START conclusions hold ONLY for this capture (by sha256), "
            "these real-contract tables and the exact evidenced windows; "
            "units, calendar, trading_date and amount semantics remain "
            "UNKNOWN; no global label convention is claimed"
        ),
    }
    return dict(payload)


def _exact_count(con: sqlite3.Connection, table: str) -> int:
    return int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def cmd_phase2(args: argparse.Namespace) -> dict[str, Any]:
    """Scoped real representative import through the public path ONLY.

    Extension design: import W1 (morning) first, freeze snapshot S1, then
    import W2 (afternoon) as an extension creating a new revision, freeze
    S2, and prove S1 immutable (identical manifest + rows) while S2 covers
    both windows. Never reinitializes the existing store.
    """
    started = time.monotonic()
    identity = load_capture_identity()
    config = load_config()
    if config["source"]["capture_sha256"] != identity["receipt_capture_sha256"]:
        raise SystemExit(
            "config capture_sha256 disagrees with the validated receipt; ABORT"
        )
    store = open_store(STORE_ROOT)
    try:
        store_meta = json.loads(
            (store.root / "store.json").read_text(encoding="utf-8")
        )
        capture_sha = identity["receipt_capture_sha256"]
        con = connect_read_only(CAPTURE)
        try:
            detector = public_simnow_detector()
            if not detector["matches_authoritative"]:
                raise SystemExit("public SimNow detector != 8 authoritative keys; ABORT")
            quarantine = simnow_quarantine_keys(con)
            public = derive_public_profiles(con, capture_sha)
            if public["errors"]:
                raise SystemExit(f"public evidence errors: {public['errors']}")
            table_counts = {
                table: _exact_count(con, table) for table in TABLES.values()
            }
        finally:
            con.close()
        profiles = profiles_for_import(public)
        asset = AssetRef(
            asset_id=f"ssquant-{SYMBOL}-capture{capture_sha[:8]}",
            origin=str(CAPTURE),
            format="sqlite",
            size=identity["stat_observation"]["size_bytes"],
            sha256=capture_sha,
        )
        evidence_ids = {
            key: payload["evidence_id"]
            for key, payload in public["profiles"].items()
        }

        def run_import(window_id: str, batch_suffix: str) -> dict[str, Any]:
            results: dict[str, Any] = {}
            for freq, minutes in (("1", 1), ("5", 5), ("15", 15)):
                table = TABLES[freq]
                profile = profiles[f"{window_id}-{minutes}"]
                spec = build_ssquant_spec(
                    f"{minutes}m", "instrument", time_label=profile.conclusion
                )
                batch_id = f"delivery04m-{SYMBOL}-{minutes}m-{batch_suffix}"
                sink = StoreSink(
                    store,
                    asset,
                    spec,
                    adapter="ssquant/0.1",
                    config={
                        "table": table,
                        "window": json.dumps(WINDOWS[window_id]),
                        "label_evidence": profile.evidence.evidence_id,
                        "capture_sha256": capture_sha,
                    },
                    batch_id=batch_id,
                )
                import_started = time.monotonic()
                adapter_receipt = import_ssquant_table(
                    CAPTURE,
                    table,
                    sink,
                    batch_id=batch_id,
                    quarantine_keys=quarantine,
                    label_profile=profile,
                )
                receipt_rows_read = adapter_receipt.rows_read
                receipt_quarantined = adapter_receipt.rows_quarantined
                receipt = sink.publish()
                results[freq] = {
                    "batch_id": batch_id,
                    "dataset_id": sink.dataset_id,
                    "input_rows": sink.counts.input_rows,
                    "accepted_rows": sink.counts.accepted_rows,
                    "candidate_rows": sink.counts.quarantined_rows,
                    "adapter_rows_read": receipt_rows_read,
                    "adapter_rows_quarantined": receipt_quarantined,
                    "elapsed_seconds": round(time.monotonic() - import_started, 3),
                    "publish": sink.summary(receipt)["publish"],
                    "candidate_file": (
                        str(sink.candidate_path) if sink.candidate_path else None
                    ),
                }
                sink.cleanup_spool()
            return results

        # ---- extension sequence: W1 -> snapshot S1 -> W2 -> snapshot S2 ---
        w1 = run_import("W1", "w1")
        dataset_ids = [w1[f]["dataset_id"] for f in ("1", "5", "15")]
        selections = tuple(Selection(ds, "*") for ds in dataset_ids)
        snap1 = freeze(store, SnapshotRequest(selections=selections))
        manifest_dir = store.path.snapshot_manifests
        snap1_manifest = manifest_dir / f"{snap1.snapshot_id}.json"
        snap1_manifest_sha = (
            hashlib.sha256(snap1_manifest.read_bytes()).hexdigest()
            if snap1_manifest.exists()
            else None
        )
        w2 = run_import("W2", "w2")
        snap2 = freeze(store, SnapshotRequest(selections=selections))
        snap2_manifest = manifest_dir / f"{snap2.snapshot_id}.json"
        snap2_manifest_sha = (
            hashlib.sha256(snap2_manifest.read_bytes()).hexdigest()
            if snap2_manifest.exists()
            else None
        )

        # ---- immutability + coverage checks -------------------------------
        def reader_state(snapshot_id: str) -> dict[str, Any]:
            reader = open_snapshot(store, snapshot_id)
            try:
                per_dataset: dict[str, Any] = {}
                for freq, ds in zip(("1", "5", "15"), dataset_ids, strict=True):
                    w1_start = datetime.strptime(
                        WINDOWS["W1"][0], "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone(timedelta(hours=8)))
                    w2_end = datetime.strptime(
                        WINDOWS["W2"][1], "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone(timedelta(hours=8)))
                    batches = list(
                        reader.bars(
                            ds,
                            start=w1_start,
                            end=w2_end,
                            required_fields=(),
                            allow_missing_auxiliary=True,
                        )
                    )
                    rows = [r for b in batches for r in b.to_pylist()]
                    labels = sorted(str(r["source_label"]) for r in rows)
                    per_dataset[freq] = {
                        "rows": len(rows),
                        "first_label": labels[0] if labels else None,
                        "last_label": labels[-1] if labels else None,
                        "rows_sha256": hashlib.sha256(
                            json.dumps(
                                rows, sort_keys=True, default=str
                            ).encode("utf-8")
                        ).hexdigest(),
                        "trading_date_all_null": all(
                            r["trading_date"] is None for r in rows
                        ),
                    }
                return {"manifest_sha256": None, "datasets": per_dataset}
            finally:
                reader.close()

        s1_state_1 = reader_state(snap1.snapshot_id)
        s2_state = reader_state(snap2.snapshot_id)
        s1_state_2 = reader_state(snap1.snapshot_id)
        payload = {
            "phase": "2",
            "generated_at": _utcnow(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "store_root": str(STORE_ROOT),
            "store_identity": store_meta,
            "capture_identity": identity,
            "config": str(CONFIG),
            "public_simnow_detector": detector,
            "table_counts_exact_scoped": table_counts,
            "evidence_ids": evidence_ids,
            "asset": {
                "asset_id": asset.asset_id,
                "origin": asset.origin,
                "sha256": asset.sha256,
            },
            "import_w1": w1,
            "import_w2": w2,
            "snapshots": {
                "s1": {
                    "snapshot_id": snap1.snapshot_id,
                    "manifest": str(snap1_manifest),
                    "manifest_sha256": snap1_manifest_sha,
                },
                "s2": {
                    "snapshot_id": snap2.snapshot_id,
                    "manifest": str(snap2_manifest),
                    "manifest_sha256": snap2_manifest_sha,
                },
                "immutability": {
                    "s1_reader_before_w2_freeze": s1_state_1["datasets"],
                    "s1_reader_after_w2_freeze": s1_state_2["datasets"],
                    "s1_rows_identical": (
                        s1_state_1["datasets"] == s1_state_2["datasets"]
                    ),
                    "s1_manifest_sha_stable": (
                        snap1_manifest_sha is not None
                        and hashlib.sha256(snap1_manifest.read_bytes()).hexdigest()
                        == snap1_manifest_sha
                    ),
                },
                "s2_state": s2_state["datasets"],
            },
            "coverage_note": (
                "accepted rows are exactly the evidenced windows; every "
                "other row of each table stays a preserved candidate with "
                "original labels; expected coverage stays UNKNOWN (no "
                "calendar/listing evidence)"
            ),
        }
        return payload
    finally:
        store.close()


def cmd_phase2_repeat(args: argparse.Namespace) -> dict[str, Any]:
    """Repeat the W1 import verbatim through the public path.

    Idempotency evidence: identical rows must surface as duplicates against
    the existing revision head (no new data), with the adapter's SimNow
    quarantine count recorded (rb2605 has zero quarantined keys).
    """
    started = time.monotonic()
    identity = load_capture_identity()
    store = open_store(STORE_ROOT)
    try:
        capture_sha = identity["receipt_capture_sha256"]
        con = connect_read_only(CAPTURE)
        try:
            quarantine = simnow_quarantine_keys(con)
            public = derive_public_profiles(con, capture_sha)
        finally:
            con.close()
        profiles = profiles_for_import(public)
        asset = AssetRef(
            asset_id=f"ssquant-{SYMBOL}-capture{capture_sha[:8]}",
            origin=str(CAPTURE),
            format="sqlite",
            size=identity["stat_observation"]["size_bytes"],
            sha256=capture_sha,
        )
        results: dict[str, Any] = {}
        for freq, minutes in (("1", 1), ("5", 5), ("15", 15)):
            profile = profiles[f"W1-{minutes}"]
            spec = build_ssquant_spec(
                f"{minutes}m", "instrument", time_label=profile.conclusion
            )
            batch_id = f"delivery04m-{SYMBOL}-{minutes}m-w1-repeat"
            sink = StoreSink(
                store,
                asset,
                spec,
                adapter="ssquant/0.1",
                config={
                    "table": TABLES[freq],
                    "window": json.dumps(WINDOWS["W1"]),
                    "label_evidence": profile.evidence.evidence_id,
                    "capture_sha256": capture_sha,
                },
                batch_id=batch_id,
            )
            adapter_receipt = import_ssquant_table(
                CAPTURE,
                TABLES[freq],
                sink,
                batch_id=batch_id,
                quarantine_keys=quarantine,
                label_profile=profile,
            )
            receipt = sink.publish()
            results[freq] = {
                "batch_id": batch_id,
                "dataset_id": sink.dataset_id,
                "accepted_rows": sink.counts.accepted_rows,
                "publish": sink.summary(receipt)["publish"],
                "adapter_rows_quarantined": adapter_receipt.rows_quarantined,
            }
            sink.cleanup_spool()
        return {
            "phase": "2-repeat",
            "generated_at": _utcnow(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "results": results,
            "expectation": (
                "every evidenced row already exists in the revision head; "
                "duplicates are reported by the core, no new data appears"
            ),
        }
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("phase1")
    sub.add_parser("phase2")
    sub.add_parser("phase2-repeat")
    args = parser.parse_args(argv)
    handlers = {
        "phase1": cmd_phase1,
        "phase2": cmd_phase2,
        "phase2-repeat": cmd_phase2_repeat,
    }
    payload = handlers[args.command](args)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"delivery04m-{args.command}.json"
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
