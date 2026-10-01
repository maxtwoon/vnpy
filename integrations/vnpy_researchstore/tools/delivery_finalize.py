"""WP10 delivery04n — final assembly helper (phase 1).

Two read-only subcommands that assemble EXISTING measured evidence into the
final delivery artifacts. The helper never runs imports, freezes, or any
store write, never fabricates IDs, and never converts a handoff prose claim
into a measured fact: every matrix fact is extracted from a machine-readable
evidence file at run time, with the evidence file's sha256 bound into the
output. Missing evidence degrades the entry to EVIDENCE_MISSING instead of
silently passing.

Subcommands:

* ``report``  — build the phase verification matrix (JSON) plus a lightweight
  standalone HTML report under ``reports/delivery04n`` from the declared
  evidence map (see ``MATRIX`` below).
* ``check-configs`` — read-only validation of the real instance configs under
  ``D:/quant-data/configs`` (and repository templates): existing paths, store
  identity, snapshot manifests, dataset selections. Emits JSON verdicts.

No vnpy import, no network, no gateway. Stdlib plus the ``research_store``
public read API only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

# Statuses used in the verification matrix. A status is DECLARED truthfully
# by the matrix definition below and can only DEGRADE (to EVIDENCE_MISSING)
# when its bound evidence disappears — it is never upgraded by this helper.
MEASURED = "MEASURED"
PARTIAL = "PARTIAL"
PENDING = "PENDING"
NOT_RUN = "NOT_RUN"
UNKNOWN = "UNKNOWN"
LIVE_NOT_RUN = "LIVE_NOT_RUN"
EVIDENCE_MISSING = "EVIDENCE_MISSING"
#: a preserved historical record (e.g. a fixed failure) kept visible as
#: history — never a current claim
HISTORICAL = "HISTORICAL"

#: statuses that mean "this claim is NOT currently demonstrated"
OPEN_STATUSES = {PENDING, NOT_RUN, UNKNOWN, LIVE_NOT_RUN, EVIDENCE_MISSING}

INTEGRATION_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Evidence fact extraction
# ---------------------------------------------------------------------------


def read_json_lenient(path: Path) -> Any:
    """Read evidence JSON written by different owners' shells.

    Handles UTF-8/ASCII, UTF-16 with BOM (PowerShell redirection) and ASCII
    with GBK-encoded non-ASCII bytes. The files stay read-only.
    """

    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return json.loads(raw.decode("utf-16"))
    errors = []
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return json.loads(raw.decode(encoding))
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            errors.append(f"{encoding}: {exc}")
    raise ValueError(f"cannot decode {path}: {errors}")


def select_fact(data: Any, dotted: str) -> Any:
    """Extract a fact at a dotted path; integer segments index lists."""

    current = data
    for part in dotted.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        else:
            return None
    return current


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Verification matrix (phase 1 truth)
# ---------------------------------------------------------------------------

Q = "D:/quant-data"
COORD = "D:/repo/vnpy/integrations/vnpy_researchstore/.coordination"
REPORTS = "D:/quant-data/reports"
DS = "D:/repo/vnpy/integrations/vnpy_datasource"

#: Each entry binds its CURRENT truthful status to machine evidence. ``facts``
#: are dotted paths extracted from the (JSON) evidence at run time; ``note``
#: explains the status in plain language. Prose-only claims (developer/test
#: counts quoted in handoffs) are recorded in the note as claims, never as
#: extracted facts.
MATRIX: list[dict[str, Any]] = [
    {
        "wp": "WP04",
        "check_id": "etf-same-snapshot-consumer-loop-current-runtime",
        "dimension": "real-data consumer loop on the CURRENT registered runtime (core + Database + both Alpha + CTA/Portfolio)",
        "status": MEASURED,
        "evidence": [f"{COORD}/etf-current-runtime-20260930/utf8-run/result.json"],
        "facts": {
            "status": "status",
            "checks_total": "checks.length",
            "store_id": "store_id",
            "snapshot_id": "snapshot_id",
            "dataset_daily": "dataset_ids.daily",
            "dataset_minute": "dataset_ids.minute",
            "elapsed_seconds": "elapsed_seconds",
        },
        "note": (
            "16/16 checks PASS, 27.927s, on snap-030369f20bd18303 in the "
            "registered vnpy-alpha 3.14 runtime with hash-pinned local "
            "duckdb/zstandard/CTA/portfolio overlays only (no shared-env "
            "merge). Original source import/repeat/repair receipts are "
            "reused and re-checked by the loop. Bare native symbols only."
        ),
    },
    {
        "wp": "WP04",
        "check_id": "etf-same-snapshot-consumer-loop-first-plugin-runtime",
        "dimension": "historical: first delivery04f loop run in the plugin .venv runtime",
        "status": HISTORICAL,
        "evidence": [f"{COORD}/delivery04f-dev/opencode-loop.rerun.stdout.json"],
        "facts": {
            "status": "status",
            "checks_total": "checks.length",
            "runner_sha256": "runner_sha256",
        },
        "note": (
            "Historical 16/16 PASS retained for lineage; superseded as the "
            "current claim by etf-same-snapshot-consumer-loop-current-runtime. "
            "The 13/16 first run stays preserved at "
            "opencode-loop.preserved-FAIL.stdout.json (runner assertion "
            "defects, review-dispositioned; never overwritten)."
        ),
    },
    {
        "wp": "WP03",
        "check_id": "etf-import-idempotency-repair-index",
        "dimension": "real import counts, repeat-import idempotency, 133-key repair index",
        "status": MEASURED,
        "evidence": [
            f"{COORD}/delivery04f-dev/import-1d.stdout.json",
            f"{COORD}/delivery04f-dev/import-1d-repeat.stdout.json",
            f"{COORD}/delivery04f-dev/import-1m.stdout.json",
            f"{COORD}/delivery04f-dev/import-1m-repeat.stdout.json",
        ],
        "facts": {
            "daily_dataset": "imports.0.dataset_id",
            "daily_input_rows": "imports.0.counts.input_rows",
            "daily_accepted_rows": "imports.0.counts.accepted_rows",
            "daily_idempotency_key": "imports.0.publish.idempotency_key",
            "daily_repaired_keys": "imports.0.adapter_receipt.extras.repair_stats.repaired_keys",
        },
        "note": (
            "Original receipts reused (never re-imported); the current-runtime "
            "loop re-checks their identity. 1m: 117,120 input/accepted rows. "
            "Finished source imports were NOT rerun for final04N."
        ),
    },
    {
        "wp": "WP03",
        "check_id": "etf-snapshot-freeze-verify",
        "dimension": "freeze + snapshot integrity verification",
        "status": MEASURED,
        "evidence": [
            f"{COORD}/delivery04f-dev/freeze.stdout.json",
            f"{COORD}/delivery04f-dev/verify.stdout.json",
            f"{Q}/manifests/snapshots/snap-030369f20bd18303.json",
        ],
        "facts": {
            "freeze_snapshot_id": "snapshot_id",
            "freeze_datasets": "datasets.length",
            "first_verify_revisions": "revisions_checked",
            "first_verify_objects": "objects_checked",
        },
        "note": (
            "verify counts are STORE-GLOBAL work units of that verify run, "
            "not per-snapshot object counts. Snapshot manifest pins 3 "
            "selections; the store verifies clean in the current-runtime loop."
        ),
    },
    {
        "wp": "WP06",
        "check_id": "native-symbol-resolution-real",
        "dimension": "bare native symbol reads on the real snapshot",
        "status": MEASURED,
        "evidence": [f"{COORD}/etf-current-runtime-20260930/utf8-run/result.json"],
        "facts": {},
        "fact_note": (
            "The bound file carries the named checks native_bare_symbol_stamping "
            "and suffixed_identity_crosscheck as PASS inside checks[]. "
            "Developer 77-test counts live in handoff prose and are NOT "
            "re-asserted here."
        ),
        "note": (
            "native06 read-time resolution verified on real data; independent "
            "Claude qualified/native recheck verdict PASS "
            "(QUALIFIED_NATIVE_RECHECK_06.md). Unknown vendor suffix stays an "
            "ordinary empty result; unmapped labels refuse explicitly."
        ),
    },
    {
        "wp": "WP02",
        "check_id": "source-root-inventory",
        "dimension": "both source roots inventoried (files/bytes/kinds)",
        "status": MEASURED,
        "evidence": [
            f"{REPORTS}/delivery04d/delivery04d-evidence.json",
            f"{REPORTS}/delivery04a/delivery04a-inventory-FAILURE.json",
        ],
        "facts": {
            "holo_file_count": "holographic_summary.file_count",
            "holo_bytes": "holographic_summary.bytes",
            "ssquant_file_count": "ssquant.file_count",
            "ssquant_bytes": "ssquant.bytes",
            "rq_packages_listed": "rq_packages.length",
        },
        "note": (
            "SS 123 files / 19,667,963,677 bytes; holographic 3,608 files / "
            "53,907,819,144 bytes. No bulk hashing; formal imports hash actual "
            "input. The 04a inventory FAILURE record is retained as history "
            "(fixed by delivery04b)."
        ),
    },
    {
        "wp": "WP04",
        "check_id": "delivery04k-representatives",
        "dimension": "stock raw target=store, JQ 33-col/NULL, ETF 133 repaired keys, P4 catalog (historical measured representatives)",
        "status": MEASURED,
        "evidence": [
            f"{REPORTS}/delivery04k/stock.json",
            f"{REPORTS}/delivery04k/jq.json",
            f"{REPORTS}/delivery04k/etf.json",
            f"{REPORTS}/delivery04k/catalog.json",
        ],
        "facts": {
            "stock_case": "case",
            "stock_ended_utc": "ended_utc",
            "etf_disputed_entry": "disputed_entry",
        },
        "note": (
            "Historical measured representatives retained; JQ adjustment stays "
            "unknown; P4 catalog coverage is NOT import qualification. The "
            "futures representative is superseded by the delivery04l final "
            "case below."
        ),
    },
    {
        "wp": "WP08",
        "check_id": "futures-final-real-case",
        "dimension": "A2505 exact source trading_date mapping; contract/dominant candidates; window joins",
        "status": MEASURED,
        "evidence": [f"{REPORTS}/delivery04l-final-20260930/futures-final.json"],
        "facts": {
            "status": "status",
            "store_id": "store_id",
            "elapsed_seconds": "elapsed_seconds",
            "peak_rss_mb": "peak_rss_mb",
        },
        "note": (
            "PASS 14/14, 59.838s, zero canonical publication. Contains "
            "222,180 contract + 392,640 dominant candidates and 1,035 window "
            "joins. Independent actual Claude scoped PASS "
            "(review-futures04l-final-20260930/REVIEW_FUTURES04L_FINAL_20260930.md). "
            "The futures time-label direction remains UNKNOWN by design: the "
            "public normalizer/spec default is UNKNOWN and scoped time "
            "evidence is the only qualifier."
        ),
    },
    {
        "wp": "WP08",
        "check_id": "futures-historical-fail-assertions",
        "dimension": "historical: delivery04l fixed-case runner mismatch",
        "status": HISTORICAL,
        "evidence": [f"{REPORTS}/delivery04l-fixed-20260930/futures-fixed-final.json"],
        "facts": {"status": "status"},
        "note": (
            "FAIL_ASSERTIONS (exit 1) preserved unchanged as history: the "
            "runner compared all-instrument unmatched 199,425 against "
            "A2505-only null 7,125. Superseded by futures-final-real-case; "
            "never copied over."
        ),
    },
    {
        "wp": "WP07",
        "check_id": "ss-capture-04h-terminal",
        "dimension": "SSQuant 10.22GB capture validation + current recovery receipt",
        "status": MEASURED,
        "evidence": [
            f"{REPORTS}/delivery04h/delivery04h-verify-capture.json",
            f"{REPORTS}/delivery04h/delivery04h-verify-capture-stage.json",
        ],
        "facts": {
            "stage_status": "status",
            "capture_path": "capture",
            "source_size_bytes": "stages.0.source.size_bytes",
        },
        "note": (
            "capture04H is terminal with the current recovery receipt; the "
            "original captured_at uncertainty remains recorded. Reused as-is - "
            "no new 10GB copy or hash was performed for final04N."
        ),
    },
    {
        "wp": "WP07",
        "check_id": "ss-representative-import-rb2605",
        "dimension": "real rb2605 import/repeat/freeze/query/immutability; 1/5/15m isolation; SimNow8 quarantine",
        "status": MEASURED,
        "evidence": [
            f"{REPORTS}/delivery04m/delivery04m-phase2.json",
            f"{REPORTS}/delivery04m/delivery04m-phase2-repeat.json",
            f"{REPORTS}/delivery04m/delivery04m-simnow-quarantine.json",
        ],
        "facts": {
            "phase": "phase",
            "elapsed_seconds": "elapsed_seconds",
            "simnow_all_eight_quarantined": "all_eight_keys_quarantined",
            "simnow_total_quarantined": "total_quarantined_rows",
        },
        "note": (
            "Independent scoped PASS (claude-ss04m-20260930): S1 "
            "snap-ec86298119e47e9c (60/12/4 rows), S2 snap-ab182160a7c6eb31 "
            "(120/24/8 rows); 1/5/15m remain separate datasets; exact 8 "
            "SimNow keys quarantined. Scope = the evidenced windows ONLY; "
            "calendar, units and broader eligibility stay unknown. Old "
            "numeric-turnover v1 snapshots remain immutable history; "
            "semantic-v2 supersedes for new usage."
        ),
    },
    {
        "wp": "WP07",
        "check_id": "ss-turnover-normalization-postfix",
        "dimension": "MA/raw missing-turnover normalization; Alpha entrypoint behavior on the postfix snapshot",
        "status": MEASURED,
        "evidence": [f"{COORD}/ss04m-postfix-root-read-20260930.json"],
        "facts": {},
        "fact_note": (
            "Snapshot snap-0d3404a3803d93cf, 1m "
            "ds-07199d36904cd3bf728896e1c3f4783e: 60 positive rows / 60 NULL "
            "turnover with raw amounts retained; 5m "
            "ds-5ff33396aeb6833347ee073b9e85abf4; 15m "
            "ds-3c2eced2f6eabed43eb7cbb979438eee."
        ),
        "note": (
            "Fresh root registered-Alpha verification exit 0. BOTH public "
            "Alpha methods with default options raise StoreError unmapped "
            "exchange - the earlier identity refusal - NOT a VWAP-specific "
            "exception; no VWAP-specific exception was reached. MA 4,745 "
            "candidate-only rows normalized NULL (no fabricated bounds). "
            "Independent review exec40881 PASS (40 tests); earlier provisional "
            "claims (rows_read 0, Alpha ImportError, native 0 bars) are "
            "superseded/stale and the helper/report corrections were made "
            "honestly rather than copied."
        ),
    },
    {
        "wp": "WP08",
        "check_id": "recorder-engineering-durable-synthetic-session",
        "dimension": "durable synthetic engineering session: installed same-session flow, seal, replay; F1/F2 closure; EOF/retry + retention repairs",
        "status": MEASURED,
        "evidence": [
            f"{COORD}/recorder03d-installed-20260930/quantdata_same_session.result.json",
            f"{COORD}/recorder03d-installed-20260930/flow_same_session.result.json",
            f"{COORD}/claude-recorder-fix-20260930/result.json",
            f"{COORD}/REVIEW_RECORDER_20260930.md",
            f"{COORD}/REVIEW_RETENTION_20260930.md",
        ],
        "facts": {
            "durable_status": "status",
        },
        "note": (
            "Explicitly SYNTHETIC engineering proof on the real store "
            "store-398306491d834f99: session sess-d7c9ad113b2e42f5 (CLOSED, "
            "sealed batch-0ddd90b14eca4cde ticks + batch-61efad21d3b04f95 "
            "bars), snapshot snap-7914084cde1ff139, 5 ticks + 2 bars. F1/F2 "
            "installed defects fixed with independent scoped PASS "
            "(claude-recorder-fix-20260930); recorder.py sha256 "
            "118fbcb932bb8e5f...; r2 wheel b2fb7dbb65ad1af8... Recorder "
            "EOF/retry repair: independent scoped PASS (7 launcher + 38 "
            "related tests). Coverage/retention repair: independent scoped "
            "PASS (40 tests). Old key/value-formatted sessions remain "
            "replayable but cannot seal; repeated recover-session creates "
            "distinct successors (advise inspect first, --no-successor for "
            "report-only repeats). This is NOT real market history and NOT "
            "live capture."
        ),
    },
    {
        "wp": "WP10",
        "check_id": "report-recording-visibility-fix",
        "dimension": "public store report shows durable journal-only sessions; catalog-only retained; errors visible; successor lineage correct for catalog-only root parents",
        "status": MEASURED,
        "evidence": [
            f"{COORD}/delivery04n-dev/repro_postfix.stdout.json",
            f"{COORD}/delivery04n-dev/store-report.stdout.json",
            f"{COORD}/delivery04n-dev/report_catalog_lineage_postfix.json",
        ],
        "facts": {
            "probe_report_status": "report_status",
            "probe_committed_seq": "report_entry.committed_seq",
            "real_store_recording_status": "report.recording.status",
            "real_store_journal_sessions": "report.recording.counts.journal_sessions",
            "lineage_fixed": "lineage_fixed",
            "lineage_parent_successors": "actual_successors.length",
        },
        "note": (
            "Authorized bounded fix in research_store/report.py: durable "
            "journal-only sessions visible (journal authority), catalog-only "
            "rows retained with missing-journal errors, duplicate ids "
            "reconciled (catalog status kept visible), committed watermark + "
            "successor lineage exposed, live counters null (never zero), "
            "unreadable/partial journals visible as errors, read-only reads "
            "(no lock file, no catalog writes). Root-found lineage defect "
            "CLOSED: successor lineage is computed for EVERY entry by "
            "comparing other.predecessor_session_id to entry.session_id with "
            "no predecessor prerequisite, so catalog-only root parents keep "
            "their durable children and non-root parents never list siblings "
            "(root failed repro report_catalog_lineage_probe.json preserved "
            "showing actual []; post-fix probe lineage_fixed=true; 3 lineage "
            "regression tests). Real-store report shows sess-d7c9ad113b2e42f5 "
            "CLOSED committed 5. Pre-fix public repro preserved unchanged at "
            "repro_recording_report_20260930.json; focused tests in "
            "tests/test_report_recording_sessions.py (12)."
        ),
    },
    {
        "wp": "WP10",
        "check_id": "datasource-suite-and-cta-engineering",
        "dimension": "vnpy_datasource current suite; CTA bars/trades engineering run",
        "status": MEASURED,
        "evidence": [
            f"{DS}/VERIFICATION.md",
            f"{DS}/output/closeout-20260930-cta/result.json",
            f"{COORD}/delivery04n-dev/checks-final/pytest-datasource-venv.txt",
        ],
        "facts": {
            "cta_input_rows": "input_rows",
            "cta_replay_rows": "replay_rows",
            "cta_total_trade_count": "metrics.total_trade_count",
            "source_database_unchanged": "source_database_unchanged",
        },
        "fact_note": (
            "Suite at FINAL source state rerun by final04N in the plugin .venv: "
            "101 passed (pytest-datasource-venv.txt, exit 0; pre-existing pytz "
            "warning). Owner-run 2026-09-30 closeout on registered Python "
            "3.14.7 also records 101 passed + root sync_check PASS + the CTA "
            "replay (integrations/vnpy_datasource/VERIFICATION.md). CTA "
            "engineering run: 659 bars / 47 simulated trades with unchanged "
            "source and working-copy hashes - engineering only, no strategy "
            "efficacy claim."
        ),
        "note": "Runtimes recorded separately; never equated.",
    },
    {
        "wp": "WP10",
        "check_id": "final-package-build-and-installed-smoke",
        "dimension": "final wheel/sdist rebuild after SS/report corrections + non-editable installed origins + installed report smoke",
        "status": MEASURED,
        "evidence": [
            f"{COORD}/delivery04n-dev/final-build.json",
            f"{COORD}/delivery04n-dev/installed-smoke.json",
        ],
        "facts": {
            "sdist_sha256": "artifacts.sdist_sha256",
            "wheel_sha256": "artifacts.wheel_sha256",
            "report_fix_in_wheel": "installed.report_fix_present",
        },
        "note": (
            "Built with the disposable build-env-20260930 (used read-only, no "
            "env modification); installed with --no-deps into a disposable "
            "venv whose dependency imports resolve read-only from the base "
            "environment; no shared environment was modified and no network "
            "was used. Provisional r1/r2 artifacts remain as history."
        ),
    },
    {
        "wp": "WP10",
        "check_id": "affected-checks-current",
        "dimension": "affected focused checks at final source state (48 focused tests, datasource suite, ruff both integrations, scoped mypy, root sync_check, 24-file baseline identity)",
        "status": PARTIAL,
        "evidence": [
            f"{COORD}/delivery04n-dev/checks-final/summary.json",
            f"{COORD}/delivery04n-dev/checks-final/pytest-focused.txt",
            f"{COORD}/delivery04n-dev/checks-final/ruff-plugin.txt",
            f"{COORD}/delivery04n-dev/checks-final/ruff-datasource.txt",
            f"{COORD}/delivery04n-dev/checks-final/mypy-scoped.txt",
            f"{COORD}/delivery04n-dev/checks-final/sync-check.txt",
            f"{COORD}/delivery04n-dev/checks-final/datasource-baseline-check.json",
        ],
        "facts": {
            "focused_passed": "pytest_focused.passed",
            "datasource_suite_passed": "pytest_datasource_final_state.passed",
            "ruff_plugin_exit": "ruff_plugin.exit_code",
            "ruff_datasource_exit": "ruff_datasource.exit_code",
            "mypy_exit": "mypy_scoped.exit_code",
            "sync_check_exit": "sync_check_root.exit_code",
            "baseline_matched": "datasource_baseline_identity.matched",
            "baseline_entries": "datasource_baseline_identity.entries",
        },
        "fact_note": (
            "All bound outputs are actual command runs at FINAL source state: "
            "48 focused tests; datasource suite 101 passed (plugin .venv, exit "
            "0); ruff exit 0 on BOTH integrations; scoped mypy exit 0; root "
            "sync_check exit 0 (PASS with the pre-existing informational "
            "docs/archive warning). 24-file baseline identity: 13/24 match, 11 "
            "files legitimately evolved since the 2026-09-16 snapshot "
            "(documented in datasource VERIFICATION.md dated sections) - so "
            "the old baseline is NOT a current identity proof and the suite "
            "was rerun at final state instead of reusing stale identity."
        ),
        "note": (
            "PARTIAL only because no single-runtime whole-package equivalence "
            "is claimed (environment disposition 2026-09-30: 408/27 with "
            "missing Alpha/portfolio dependencies; isolated Alpha/portfolio "
            "runtimes cover those scopes) and pytest-in-installed-env was not "
            "run. Independent Claude final audit is the next gate."
        ),
    },
    {
        "wp": "WP10",
        "check_id": "live-gateway-recording",
        "dimension": "real gateway capture",
        "status": LIVE_NOT_RUN,
        "evidence": [],
        "facts": {},
        "note": "No authorized live run; label must stay visible.",
    },
    {
        "wp": "WP03",
        "check_id": "expected-coverage",
        "dimension": "market calendar/listing/session evidence",
        "status": UNKNOWN,
        "evidence": [],
        "facts": {},
        "note": (
            "No calendar/listing evidence exists anywhere in scope; expected "
            "coverage stays UNKNOWN. Observed min/max dates never imply "
            "completeness."
        ),
    },
]


def build_matrix(matrix: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Extract bound facts from evidence; degrade status on missing evidence."""

    entries: list[dict[str, Any]] = []
    for spec in matrix if matrix is not None else MATRIX:
        entry: dict[str, Any] = {
            "wp": spec["wp"],
            "check_id": spec["check_id"],
            "dimension": spec["dimension"],
            "status": spec["status"],
            "note": spec["note"],
            "evidence": [],
            "facts": {},
        }
        degraded = False
        details: list[str] = []
        for raw_path in spec.get("evidence", []):
            path = Path(raw_path)
            info: dict[str, Any] = {"path": raw_path}
            if not path.is_file():
                info["exists"] = False
                degraded = True
                details.append(f"missing evidence file: {raw_path}")
                entry["evidence"].append(info)
                continue
            info["exists"] = True
            info["sha256"] = sha256_file(path)
            info["size"] = path.stat().st_size
            if path.suffix.lower() == ".json":
                try:
                    read_json_lenient(path)
                    info["json"] = True
                except (ValueError, OSError) as exc:
                    info["json"] = False
                    info["error"] = str(exc)
                    degraded = True
                    details.append(f"unreadable JSON evidence: {raw_path}: {exc}")
            entry["evidence"].append(info)
        for name, dotted in spec.get("facts", {}).items():
            if dotted.endswith(".length"):
                base = dotted[: -len(".length")]
                value = select_fact_any(entry, spec, base)
                entry["facts"][name] = len(value) if isinstance(value, list) else None
                continue
            value = select_fact_any(entry, spec, dotted)
            entry["facts"][name] = value
            if value is None and spec.get("evidence"):
                details.append(f"fact {name!r} not found at {dotted!r}")
        if "fact_note" in spec:
            entry["fact_note"] = spec["fact_note"]
        if degraded and spec["status"] not in OPEN_STATUSES:
            entry["status"] = EVIDENCE_MISSING
        entry["degradation"] = details
        entries.append(entry)
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return {
        "phase": "final",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generator": "tools/delivery_finalize.py report",
        "generator_sha256": sha256_file(Path(__file__)),
        "rule": (
            "facts are extracted from the bound evidence files at run time; a "
            "missing/unreadable evidence file degrades MEASURED/PARTIAL to "
            "EVIDENCE_MISSING. Prose claims are never upgraded to facts."
        ),
        "status_counts": counts,
        "entries": entries,
    }


def select_fact_any(entry: dict[str, Any], spec: dict[str, Any], dotted: str) -> Any:
    """Try each bound evidence file until the dotted path resolves."""

    for raw_path in spec.get("evidence", []):
        if not raw_path.lower().endswith(".json"):
            continue
        path = Path(raw_path)
        if not path.is_file():
            continue
        try:
            data = read_json_lenient(path)
        except (ValueError, OSError):
            continue
        value = select_fact(data, dotted)
        if value is not None:
            return value
    return None


# ---------------------------------------------------------------------------
# Minimal standalone HTML rendering
# ---------------------------------------------------------------------------

_STATUS_COLORS = {
    MEASURED: "#0a7d32",
    PARTIAL: "#b06000",
    PENDING: "#8a8a8a",
    NOT_RUN: "#8a8a8a",
    UNKNOWN: "#7a5c00",
    LIVE_NOT_RUN: "#555555",
    EVIDENCE_MISSING: "#b00020",
}


def _esc(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_html(matrix: dict[str, Any], title: str = "WP10 delivery report (final)") -> str:
    rows = []
    for entry in matrix["entries"]:
        color = _STATUS_COLORS.get(entry["status"], "#000000")
        facts = _esc(json.dumps(entry["facts"], ensure_ascii=False, default=str))
        evidence = "<br>".join(
            f"{_esc(e['path'])} "
            f"{'[sha256 ' + _esc(e['sha256'][:12]) + '…]' if e.get('sha256') else '[MISSING]'}"
            for e in entry["evidence"]
        ) or "<em>none bound yet</em>"
        degradation = _esc("; ".join(entry["degradation"]))
        rows.append(
            "<tr>"
            f"<td>{_esc(entry['wp'])}</td>"
            f"<td>{_esc(entry['check_id'])}</td>"
            f"<td>{_esc(entry['dimension'])}</td>"
            f'<td style="color:{color};font-weight:bold">{_esc(entry["status"])}</td>'
            f"<td>{facts}</td>"
            f"<td>{evidence}</td>"
            f"<td>{_esc(entry['note'])}"
            + (f"<br><strong>degradation:</strong> {degradation}" if degradation else "")
            + "</td></tr>"
        )
    counts = " ".join(
        f"<span class='count'>{_esc(status)}: {count}</span>"
        for status, count in sorted(matrix["status_counts"].items())
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<style>
body {{ font-family: sans-serif; margin: 1.5em; color: #1a1a1a; }}
h1 {{ font-size: 1.4em; }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.85em; }}
th, td {{ border: 1px solid #bbb; padding: 6px; vertical-align: top; text-align: left; overflow-wrap: anywhere; word-break: break-word; }}
th {{ background: #eee; }}
.count {{ margin-right: 1em; background: #f2f2f2; padding: 2px 8px; border-radius: 4px; }}
.meta {{ color: #555; font-size: 0.85em; }}
</style>
</head>
<body>
<h1>{_esc(title)}</h1>
<p class="meta">generated {_esc(matrix["generated_at"])} by {_esc(matrix["generator"])}<br>
{_esc(matrix["rule"])}</p>
<p>{counts}</p>
<table>
<tr><th>WP</th><th>check_id</th><th>dimension</th><th>status</th>
<th>extracted facts</th><th>bound evidence</th><th>note</th></tr>
{chr(10).join(rows)}
</table>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Instance-config validation (read-only)
# ---------------------------------------------------------------------------


def _load_manifests(store_root: Path) -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    manifest_dir = store_root / "manifests" / "snapshots"
    if manifest_dir.is_dir():
        for path in manifest_dir.glob("snap-*.json"):
            try:
                manifests[path.stem] = read_json_lenient(path)
            except (ValueError, OSError):
                continue
    return manifests


def validate_instance_config(
    config_path: Path,
    store_root: Path,
    manifests: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Read-only validation of one instance/template config.

    Detects the config kind from its keys and checks only what is visible:
    existing paths, store identity, snapshot manifests and dataset
    selections. Missing optional things are reported as ``pending_items``
    (e.g. a recorder session that no run has produced yet) — never as IDs.
    """

    problems: list[str] = []
    pending_items: list[str] = []
    checks: dict[str, Any] = {}
    try:
        raw = read_json_lenient(config_path)
    except (ValueError, OSError) as exc:
        return {
            "config": str(config_path),
            "kind": "unreadable",
            "problems": [f"cannot read config: {exc}"],
            "pending_items": [],
        }
    if not isinstance(raw, dict):
        return {
            "config": str(config_path),
            "kind": "invalid",
            "problems": ["config is not a JSON object"],
            "pending_items": [],
        }
    store_id = None
    store_file = store_root / "store.json"
    if store_file.is_file():
        try:
            store_id = read_json_lenient(store_file).get("store_id")
        except (ValueError, OSError) as exc:
            problems.append(f"store.json unreadable: {exc}")
    checks["store_id"] = store_id

    if "selections" in raw and "required_fields" in raw:
        kind = "snapshot_request"
        for selection in raw["selections"]:
            dataset_id, partition = selection
            found = [
                manifest
                for manifest in manifests.values()
                if any(
                    sel["dataset_id"] == dataset_id and sel["partition"] == partition
                    for sel in manifest.get("selections", [])
                )
            ]
            if found:
                checks[f"selection {dataset_id} {partition}"] = "published"
            else:
                pending_items.append(
                    f"selection {dataset_id} {partition}: not in any local "
                    "snapshot manifest (import/freeze needed before use)"
                )
    elif "batches" in raw or "frequencies" in raw:
        kind = "import_config"
        source_root = raw.get("source_root") or raw.get("asset", {}).get("origin")
        if source_root:
            checks["source_root_exists"] = Path(source_root).is_dir()
            if not checks["source_root_exists"]:
                problems.append(f"source_root missing on disk: {source_root}")
        audit = raw.get("repair_index", {}).get("audit_csv")
        if audit:
            checks["repair_index_csv_exists"] = Path(audit).is_file()
            if not checks["repair_index_csv_exists"]:
                problems.append(f"repair index CSV missing: {audit}")
    elif "session_id" in raw and "store_root" in raw:
        kind = "recording_replay"
        store_root_path = Path(raw["store_root"]) if Path(raw["store_root"]).is_absolute() else store_root
        journal = store_root_path / "journals" / f"{raw['session_id']}.sqlite"
        checks["journal_present"] = journal.is_file()
        if not journal.is_file():
            problems.append(f"journal file missing for session: {raw['session_id']}")
        snapshot_id = raw.get("snapshot_id")
        if snapshot_id:
            if snapshot_id in manifests:
                checks["snapshot_manifest"] = "present"
            else:
                problems.append(f"snapshot manifest not found: {snapshot_id}")
    elif "lab_path" in raw and "dataset_ids" in raw:
        kind = "loop_config"
        snapshot_id = raw.get("snapshot_id")
        manifest = manifests.get(snapshot_id)
        if manifest is None:
            problems.append(f"snapshot manifest not found: {snapshot_id}")
        else:
            published = {
                (sel["dataset_id"], sel["partition"])
                for sel in manifest.get("selections", [])
            }
            for interval, dataset_id in (raw.get("dataset_ids") or {}).items():
                ok = any(key[0] == dataset_id for key in published)
                checks[f"dataset_ids.{interval}"] = "published" if ok else "not published"
                if not ok:
                    problems.append(f"dataset {interval}={dataset_id} not in snapshot manifest")
    elif "snapshot_id" in raw and "runtime_dir" in raw:
        kind = "bootstrap_config"
        snapshot_id = raw["snapshot_id"]
        if snapshot_id in manifests:
            checks["snapshot_manifest"] = "present"
        else:
            problems.append(f"snapshot manifest not found: {snapshot_id}")
        for key in ("repo_path", "integration_path"):
            value = raw.get(key)
            if value and not Path(value).is_dir():
                problems.append(f"{key} missing on disk: {value}")
    else:
        kind = "unknown"
        problems.append("config kind not recognized; no validation performed")

    return {
        "config": str(config_path),
        "kind": kind,
        "checks": checks,
        "problems": problems,
        "pending_items": pending_items,
    }


def check_configs(configs_dir: Path, store_root: Path) -> dict[str, Any]:
    manifests = _load_manifests(store_root)
    results = []
    for path in sorted(configs_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        results.append(validate_instance_config(path, store_root, manifests))
    problems = sum(1 for r in results if r["problems"])
    return {
        "configs_dir": str(configs_dir),
        "store_root": str(store_root),
        "store_id": (
            read_json_lenient(store_root / "store.json").get("store_id")
            if (store_root / "store.json").is_file()
            else None
        ),
        "snapshots_seen": sorted(manifests),
        "configs_checked": len(results),
        "configs_with_problems": problems,
        "results": results,
        "rule": (
            "read-only checks; pending_items mark real work that has not run "
            "yet (e.g. unpublished selections, missing durable recording "
            "sessions). No ID is invented and no pending item is counted as a "
            "failure of existing evidence."
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="delivery04n final assembly helper")
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report", help="build matrix JSON + HTML from bound evidence")
    report.add_argument("--output-dir", default=str(INTEGRATION_ROOT / "reports" / "delivery04n"))
    check = sub.add_parser("check-configs", help="read-only instance-config validation")
    check.add_argument("--configs-dir", default="D:/quant-data/configs")
    check.add_argument("--store-root", default="D:/quant-data")
    check.add_argument("--output")
    args = parser.parse_args(argv)
    started = time.time()
    if args.command == "report":
        matrix = build_matrix()
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        matrix["elapsed_seconds"] = round(time.time() - started, 3)
        json_path = out_dir / "verification-matrix.json"
        html_path = out_dir / "delivery04n-report.html"
        json_path.write_text(json.dumps(matrix, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        html_path.write_text(render_html(matrix), encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "matrix": str(json_path),
                    "html": str(html_path),
                    "status_counts": matrix["status_counts"],
                    "elapsed_seconds": matrix["elapsed_seconds"],
                },
                indent=2,
            )
        )
        return 0
    if args.command == "check-configs":
        result = check_configs(Path(args.configs_dir), Path(args.store_root))
        result["elapsed_seconds"] = round(time.time() - started, 3)
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            result["written"] = str(out)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0 if result["configs_with_problems"] == 0 else 2
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
