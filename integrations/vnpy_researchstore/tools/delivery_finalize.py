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

#: Each entry binds its CURRENT truthful status to machine evidence. ``facts``
#: are dotted paths extracted from the (JSON) evidence at run time; ``note``
#: explains the status in plain language. Prose-only claims (developer/test
#: counts quoted in handoffs) are recorded in the note as claims, never as
#: extracted facts.
MATRIX: list[dict[str, Any]] = [
    {
        "wp": "WP04",
        "check_id": "etf-same-snapshot-consumer-loop",
        "dimension": "real-data consumer loop (core + Database + both Alpha + CTA/Portfolio)",
        "status": MEASURED,
        "evidence": [f"{COORD}/delivery04f-dev/opencode-loop.rerun.stdout.json"],
        "facts": {
            "status": "status",
            "checks_total": "checks.length",
            "store_id": "store_id",
            "snapshot_id": "snapshot_id",
            "dataset_daily": "dataset_ids.daily",
            "dataset_minute": "dataset_ids.minute",
            "runner_sha256": "runner_sha256",
            "config_identity": "config_identity",
            "vnpy_origin": "environment.vnpy_module_file",
            "elapsed_seconds": "elapsed_seconds",
        },
        "note": (
            "16/16 checks PASS on snap-030369f20bd18303 (checks.length is the "
            "runner's check count; the per-check names/passes are in the file). "
            "Bare native symbols only; compound-symbol workaround never used."
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
            "Repeat imports preserved alongside originals; the loop check "
            "import_idempotency_and_repair_index re-proved identity at rerun "
            "time. 1m: 117,120 input/accepted rows (same keys verified)."
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
            "first_verify_failures": "failures.length",
        },
        "note": (
            "verify counts are STORE-GLOBAL work-unit counts of that verify "
            "run, not per-snapshot object counts. The rerun loop's verify "
            "reported 40 revisions / 40 objects after other owners published "
            "more; the snapshot manifest itself pins 3 selections."
        ),
    },
    {
        "wp": "WP06",
        "check_id": "native-symbol-resolution-real",
        "dimension": "bare native symbol reads on the real snapshot",
        "status": MEASURED,
        "evidence": [f"{COORD}/delivery04f-dev/opencode-loop.rerun.stdout.json"],
        "facts": {
            "bare_stamp_check": "checks",
            "overview_native_symbols": "overview",
        },
        "fact_note": (
            "checks/overview are recorded whole; the named checks "
            "native_bare_symbol_stamping and suffixed_identity_crosscheck PASS "
            "inside that file. Developer 77-test count lives in "
            "opencode-native06-handoff.md prose and is NOT re-asserted here."
        ),
        "note": (
            "native06 read-time resolution verified on real data by the loop "
            "checks; independent Claude qualified/native recheck verdict PASS "
            "(QUALIFIED_NATIVE_RECHECK_06.md)."
        ),
    },
    {
        "wp": "WP02",
        "check_id": "source-root-inventory",
        "dimension": "both source roots inventoried (files/bytes/kinds)",
        "status": MEASURED,
        "evidence": [
            f"{REPORTS}/delivery04d/delivery04d-evidence.json",
            f"{REPORTS}/delivery04a/delivery04a-inventory.json",
            f"{REPORTS}/delivery04a/delivery04a-inventory-FAILURE.json",
        ],
        "facts": {
            "holo_file_count": "holographic_summary.file_count",
            "holo_bytes": "holographic_summary.bytes",
            "ssquant_file_count": "ssquant.file_count",
            "ssquant_bytes": "ssquant.bytes",
            "rq_packages_listed": "rq_packages.length",
            "return_status": "return_status",
        },
        "note": (
            "Hash policy: no bulk hashing of the 54GB tree; formal imports "
            "hash actual input. The preserved 04a inventory FAILURE record "
            "is kept visible (fixed by delivery04b)."
        ),
    },
    {
        "wp": "WP02",
        "check_id": "inventory-failed-record-preservation",
        "dimension": "broken archive-list elements stay visible (04B fix)",
        "status": MEASURED,
        "evidence": [f"{REPORTS}/delivery04b/delivery04b-evidence.json"],
        "facts": {"task": "task", "qualification": "qualification"},
        "note": "failed_records/unrecognized_records counts preserved by fix.",
    },
    {
        "wp": "WP04",
        "check_id": "delivery04k-representatives",
        "dimension": "stock raw target=store, JQ 33-col/NULL, ETF 133 repaired keys, P4 catalog",
        "status": MEASURED,
        "evidence": [
            f"{REPORTS}/delivery04k/stock.json",
            f"{REPORTS}/delivery04k/jq.json",
            f"{REPORTS}/delivery04k/etf.json",
            f"{REPORTS}/delivery04k/catalog.json",
            f"{REPORTS}/delivery04k/futures.json",
        ],
        "facts": {
            "stock_case": "case",
            "stock_ended_utc": "ended_utc",
            "jq_case": "case",
            "etf_disputed_entry": "etf.disputed_entry",
        },
        "note": (
            "Per-report assertions/coverage are machine fields inside each "
            "file. JQ adjustment stays unknown; P4 catalog coverage is not "
            "import qualification. futures.json carries the measured label "
            "conflict that 04L must resolve."
        ),
    },
    {
        "wp": "WP07",
        "check_id": "ss-capture-stage",
        "dimension": "SSQuant 10.22GB capture validation",
        "status": PARTIAL,
        "evidence": [f"{REPORTS}/delivery04h/delivery04h-verify-capture-stage.json"],
        "facts": {
            "stage_status": "status",
            "capture_path": "capture",
            "source_size_bytes": "stages.0.source.size_bytes",
            "capture_size_bytes": "stages.0.capture.size_bytes",
            "updated_at": "updated_at",
        },
        "note": (
            "Stage receipt status=validated (measured). Still OWNED ELSEWHERE: "
            "strict SQLite-header allowance + unchanged-input recovery receipt "
            "(capture04H) must finish before this becomes a reusable capture "
            "acceptance."
        ),
    },
    {
        "wp": "WP07",
        "check_id": "ss-representative-import",
        "dimension": "SS 1/5/15m isolation, SimNow8 key, MA untrusted amount",
        "status": PENDING,
        "evidence": [],
        "facts": {},
        "note": "Owned by SS04M; no receipt exists yet — nothing is claimed.",
    },
    {
        "wp": "WP08",
        "check_id": "rq-futures-night-trading-date",
        "dimension": "A2505 exact source trading_date mapping; END/START direction",
        "status": PENDING,
        "evidence": [f"{REPORTS}/delivery04k/futures.json"],
        "facts": {"defect_repro": "defect_repro", "implementation_request": "implementation_request"},
        "note": (
            "Measured label conflict is bound; the public normalizer/spec fix "
            "(default END label -> UNKNOWN + scoped time evidence) is owned by "
            "futures04L. Until then the futures direction stays UNKNOWN."
        ),
    },
    {
        "wp": "WP08",
        "check_id": "recording-engineering-durable-instance",
        "dimension": "journal admission/stop/recover/replay/seal on a durable store session",
        "status": PENDING,
        "evidence": [],
        "facts": {},
        "note": (
            "D:/quant-data/journals is empty: no durable real-store session "
            "exists, so no instance recorder_replay config is shipped (a "
            "placeholder session ID would be fabrication). Engineering loops "
            "are covered by the scoped test suites; recorder03D B1 + "
            "installed-entrypoint acceptance pending. LIVE gateway recording: "
            "LIVE_NOT_RUN."
        ),
    },
    {
        "wp": "WP10",
        "check_id": "final-stable-checks",
        "dimension": "datasource suite, ruff/mypy both integrations, build, sync_check",
        "status": NOT_RUN,
        "evidence": [],
        "facts": {},
        "note": (
            "Phase 2 only: requires stable completed dependencies (04H/04L/"
            "02IA/03D/04M). Deliberately not run in phase 1; no partial or "
            "broad moving-package test was executed."
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
            "No calendar/listing evidence is available anywhere in scope; "
            "expected coverage stays UNKNOWN. Observed min/max dates never "
            "imply completeness."
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
        "phase": 1,
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


def render_html(matrix: dict[str, Any], title: str = "WP10 delivery report (phase 1)") -> str:
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
th, td {{ border: 1px solid #bbb; padding: 6px; vertical-align: top; text-align: left; }}
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
