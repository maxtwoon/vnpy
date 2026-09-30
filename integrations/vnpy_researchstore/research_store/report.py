"""Standalone store report: machine-readable summary + simple HTML.

Reports assets, datasets, coverage timeline (observed bounds only), sources,
quality issues/conflicts, recording status and disk usage. Missing, unknown
and partial states are reported faithfully — nothing is smoothed into a PASS.
No bulk market data is embedded; only catalog metadata and manifest coverage
ranges are read.

Recording sessions (read-only, journal-authoritative): the durable
``<journals>/<session>.sqlite`` files are the authority for session
identity/status/watermarks; catalog-only rows (no journal file) are retained
honestly with the missing journal marked as an error. Journal reads open
SQLite in read-only URI mode — they never touch the ``.lock`` file, never
write, never run recovery, and never interrupt an active writer. Only
``session_meta``, the watermark row and ``MAX(seq)`` are read (metadata /
watermark reads, never a full event scan). Journal content is never
modified; a read-only connection to a WAL database may let SQLite create
empty ``-wal``/``-shm`` read sidecars, which carry no journal mutation.
Live in-memory admission counters (accepted/backlog/rejected/errors) are
NOT durable and are reported as ``null`` — never inferred as zero.
"""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .store import Store


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ns_to_iso(ns: int | None) -> str | None:
    if ns is None:
        return None
    return datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc).isoformat()


def _dir_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _read_journal_summary(journal_path: Path) -> dict[str, Any]:
    """Read-only metadata/watermark summary of one journal SQLite file.

    Returns a dict with durable fields and, when individual reads fail
    (e.g. a legacy journal without ``session_meta``), the missing fields as
    ``None`` plus a ``read_note``. Raises ``sqlite3.Error`` only when the
    file cannot be read as SQLite at all (corrupt/foreign file).
    """

    conn = sqlite3.connect(f"file:{journal_path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    notes: list[str] = []
    meta: dict[str, str] = {}
    committed_seq: int | None = None
    durable_last_seq: int | None = None
    try:
        try:
            meta = {
                str(row["key"]): str(row["value"])
                for row in conn.execute("SELECT key, value FROM session_meta")
            }
        except sqlite3.OperationalError as exc:
            notes.append(f"session_meta unreadable: {exc}")
        try:
            row = conn.execute("SELECT committed_seq FROM watermark").fetchone()
            committed_seq = int(row["committed_seq"]) if row is not None else None
        except sqlite3.OperationalError as exc:
            notes.append(f"watermark unreadable: {exc}")
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS m FROM events"
            ).fetchone()
            durable_last_seq = int(row["m"])
        except sqlite3.OperationalError as exc:
            notes.append(f"events unreadable: {exc}")
    finally:
        conn.close()
    return {
        "session_id": meta.get("session_id"),
        "state": meta.get("state"),
        "source_spec": meta.get("source_spec"),
        "calendar_spec": meta.get("calendar_spec"),
        "predecessor_session_id": meta.get("predecessor_session_id") or None,
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "committed_seq": committed_seq,
        "durable_last_seq": durable_last_seq,
        "read_note": "; ".join(notes) if notes else None,
    }


def _collect_recording(store: Store) -> dict[str, Any]:
    """Build the recording section: durable journals + catalog, reconciled.

    Durable journals are the authority; catalog-only historical sessions are
    retained with their missing journal marked as an error; duplicate ids
    merge into one entry whose ``status`` comes from the journal, with the
    catalog status kept visible as ``catalog_status``.
    """

    journals_dir = store.path.journals
    journal_files = (
        sorted(journals_dir.glob("*.sqlite")) if journals_dir.is_dir() else []
    )

    catalog_rows: dict[str, sqlite3.Row] = {}
    for row in store.catalog.query_all(
        "SELECT * FROM recording_sessions ORDER BY created_at"
    ):
        catalog_rows[str(row["session_id"])] = row

    summaries: dict[Path, dict[str, Any]] = {}
    for journal_path in journal_files:
        try:
            summaries[journal_path] = _read_journal_summary(journal_path)
        except sqlite3.Error as exc:
            summaries[journal_path] = {
                "error": f"unreadable journal: {type(exc).__name__}: {exc}"
            }

    entries: dict[str, dict[str, Any]] = {}
    for journal_path, summary in summaries.items():
        stem = journal_path.stem
        session_id = summary.get("session_id") or stem
        error = summary.get("error")
        if error is None and summary.get("session_id") is None:
            error = f"journal has no session_id metadata; using file name {stem!r}"
        catalog_row = catalog_rows.get(str(session_id))
        entry: dict[str, Any] = {
            "session_id": str(session_id),
            "authority": "journal",
            "status": (
                "unreadable_journal"
                if summary.get("error")
                else summary.get("state") or "unknown_journal_format"
            ),
            "durable_state": summary.get("state"),
            "catalog_status": (
                str(catalog_row["status"]) if catalog_row is not None else None
            ),
            "source_spec": summary.get("source_spec"),
            "calendar_spec": summary.get("calendar_spec"),
            "committed_seq": summary.get("committed_seq"),
            "durable_last_seq": summary.get("durable_last_seq"),
            "accepted_seq": None,
            "backlog": None,
            "rejected": None,
            "errors": None,
            "counters_note": (
                "live in-memory admission counters are not durable; null, "
                "never inferred zero"
            ),
            "predecessor_session_id": summary.get("predecessor_session_id"),
            "successor_session_ids": [],
            "created_at": summary.get("created_at"),
            "updated_at": summary.get("updated_at"),
            "journal_path": str(journal_path),
            "error": error,
            "read_note": summary.get("read_note"),
        }
        entries[str(session_id)] = entry

    for session_id, row in catalog_rows.items():
        if session_id in entries:
            continue  # duplicate: journal authority already carries catalog_status
        journal_path_value = str(row["journal_path"]) if row["journal_path"] else None
        entries[session_id] = {
            "session_id": session_id,
            "authority": "catalog_only",
            "status": str(row["status"]),
            "durable_state": None,
            "catalog_status": str(row["status"]),
            "source_spec": str(row["source_spec"]) if row["source_spec"] else None,
            "calendar_spec": str(row["calendar_spec"]) if row["calendar_spec"] else None,
            "committed_seq": None,
            "durable_last_seq": None,
            "accepted_seq": None,
            "backlog": None,
            "rejected": None,
            "errors": None,
            "counters_note": (
                "live in-memory admission counters are not durable; null, "
                "never inferred zero"
            ),
            "predecessor_session_id": (
                str(row["predecessor_session_id"])
                if row["predecessor_session_id"]
                else None
            ),
            "successor_session_ids": [],
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "journal_path": journal_path_value,
            "error": f"journal file missing for catalog-only session"
            f" (expected near {journal_path_value or store.path.journals})",
            "read_note": None,
        }

    # Successor lineage for EVERY entry (either authority): any other entry
    # whose predecessor_session_id names THIS session is its child. Compared
    # against entry.session_id with no predecessor prerequisite, so root
    # parents (including catalog-only ones) keep their children and a
    # non-root parent never lists its siblings.
    for entry in entries.values():
        entry["successor_session_ids"] = sorted(
            other["session_id"]
            for other in entries.values()
            if other is not entry
            and other["predecessor_session_id"] == entry["session_id"]
        )

    sessions = sorted(
        entries.values(),
        key=lambda e: (e.get("created_at") or "", e["session_id"]),
    )
    journal_count = sum(1 for e in sessions if e["authority"] == "journal")
    catalog_only_count = len(sessions) - journal_count
    error_count = sum(1 for e in sessions if e.get("error"))
    return {
        "status": "sessions_present" if sessions else "no_recording_sessions",
        "sessions": sessions,
        "counts": {
            "journal_sessions": journal_count,
            "catalog_only_sessions": catalog_only_count,
            "sessions_with_errors": error_count,
        },
        "note": "durable journals are the recording authority; catalog-only "
        "rows are retained with their missing journal marked as an error; "
        "accepted/backlog/rejected/errors are live in-memory counters and "
        "stay null from durable state, never inferred zero",
    }


def build_report(store: Store) -> dict[str, Any]:
    """Collect the store summary from catalog + manifests (read-only)."""
    catalog = store.catalog
    datasets: dict[str, Any] = {}
    for row in catalog.query_all("SELECT * FROM datasets ORDER BY dataset_id"):
        ds_id = str(row["dataset_id"])
        semantic = json.loads(str(row["semantic_json"]))
        heads = catalog.query_all(
            "SELECT h.partition, h.revision_id, r.rows, r.manifest_path"
            " FROM partition_heads h JOIN revisions r ON r.revision_id=h.revision_id"
            " WHERE h.dataset_id=? ORDER BY h.partition",
            (ds_id,),
        )
        partitions: dict[str, Any] = {}
        total_rows = 0
        start_ns: int | None = None
        end_ns: int | None = None
        for head in heads:
            manifest_path = Path(str(head["manifest_path"]))
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                coverage = manifest.get("coverage", {})
            except (OSError, json.JSONDecodeError):
                coverage = {}
            unresolved = catalog.unresolved_issues(ds_id, str(head["partition"]))
            partitions[str(head["partition"])] = {
                "revision_id": str(head["revision_id"]),
                "rows": int(head["rows"]),
                "observed_start": _ns_to_iso(coverage.get("start_ns")),
                "observed_end": _ns_to_iso(coverage.get("end_ns")),
                "unresolved_conflicts": len(unresolved),
            }
            total_rows += int(head["rows"])
            if coverage.get("start_ns") is not None:
                start_ns = (
                    coverage["start_ns"]
                    if start_ns is None
                    else min(start_ns, coverage["start_ns"])
                )
            if coverage.get("end_ns") is not None:
                end_ns = (
                    coverage["end_ns"] if end_ns is None else max(end_ns, coverage["end_ns"])
                )
        datasets[ds_id] = {
            "semantic": semantic,
            "partition_count": len(partitions),
            "published_rows": total_rows,
            "observed_start": _ns_to_iso(start_ns),
            "observed_end": _ns_to_iso(end_ns),
            "expected_status": "unknown",
            "partitions": partitions,
        }

    batches: dict[str, int] = {}
    for row in catalog.query_all(
        "SELECT state, COUNT(*) AS n FROM batches GROUP BY state"
    ):
        batches[str(row["state"])] = int(row["n"])

    issues: dict[str, Any] = {"unresolved": [], "resolved_count": 0}
    for row in catalog.query_all("SELECT * FROM quality_issues"):
        if row["resolution"] is None:
            issues["unresolved"].append(
                {
                    "issue_id": str(row["issue_id"]),
                    "dataset_id": str(row["scope_dataset_id"]),
                    "partition": str(row["scope_partition"]),
                    "code": str(row["code"]),
                    "created_at": str(row["created_at"]),
                }
            )
        else:
            issues["resolved_count"] += 1

    recording = _collect_recording(store)

    assets = [
        {
            "asset_id": str(a["asset_id"]),
            "origin": str(a["origin"]),
            "format": str(a["format"]),
            "size": int(a["size"]),
            "sha256": a["sha256"],
            "discovery": str(a["discovery"]),
        }
        for a in catalog.query_all("SELECT * FROM assets ORDER BY asset_id")
    ]

    snapshots = [
        {
            "snapshot_id": str(s["snapshot_id"]),
            "created_at": str(s["created_at"]),
        }
        for s in catalog.query_all("SELECT * FROM snapshots ORDER BY created_at")
    ]

    candidates_dir = store.path.reports / "candidates"
    candidate_files = (
        sorted(p.name for p in candidates_dir.glob("*.jsonl.gz"))
        if candidates_dir.is_dir()
        else []
    )

    disk = {
        name: _dir_size(getattr(store.path, name))
        for name in (
            "objects",
            "revision_manifests",
            "snapshot_manifests",
            "captures",
            "staging",
            "journals",
            "reports",
            "exports",
        )
    }
    disk["catalog_sqlite"] = (
        store.path.catalog.stat().st_size if store.path.catalog.is_file() else 0
    )

    return {
        "generated_at": _utcnow(),
        "store": {
            "root": str(store.root),
            "store_id": store.store_id,
        },
        "datasets": datasets,
        "batches_by_state": batches,
        "quality_issues": issues,
        "recording": recording,
        "assets": assets,
        "snapshots": snapshots,
        "candidate_files": candidate_files,
        "disk_bytes": disk,
        "coverage_note": "observed bounds only; expected completeness is "
        "unknown without calendar evidence",
    }


def render_html(report: dict[str, Any]) -> str:
    """Render the report as one self-contained static HTML page."""

    def esc(value: Any) -> str:
        return html.escape("" if value is None else str(value))

    def esc_unknown(value: Any) -> str:
        """Render unknown (None) live counters explicitly as UNKNOWN.

        True values are preserved; ``null`` in the machine report renders as
        the visible text UNKNOWN instead of a blank cell.
        """

        return "UNKNOWN" if value is None else html.escape(str(value))

    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>research_store report</title>",
        "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:2em}"
        "table{border-collapse:collapse;margin-bottom:1.5em;width:100%}"
        "td,th{border:1px solid #bbb;padding:3px 8px;text-align:left;"
        "overflow-wrap:anywhere;word-break:break-word}"
        "th{background:#eee}h1,h2{font-weight:600}</style>",
        "</head><body>",
        "<h1>research_store report</h1>",
        f"<p>generated {esc(report['generated_at'])}; store "
        f"{esc(report['store']['store_id'])} at {esc(report['store']['root'])}</p>",
        f"<p><em>{esc(report['coverage_note'])}</em></p>",
        "<h2>Datasets</h2><table>",
        "<tr><th>dataset</th><th>source</th><th>class</th><th>interval</th>"
        "<th>series</th><th>adjustment</th><th>time label</th><th>rows</th>"
        "<th>partitions</th><th>observed start</th><th>observed end</th>"
        "<th>expected</th></tr>",
    ]
    for ds_id, ds in sorted(report["datasets"].items()):
        sem = ds["semantic"]
        parts.append(
            "<tr>"
            f"<td>{esc(ds_id)}</td><td>{esc(sem.get('source_id'))}</td>"
            f"<td>{esc(sem.get('asset_class'))}</td>"
            f"<td>{esc(sem.get('interval'))}</td>"
            f"<td>{esc(sem.get('series_kind'))}</td>"
            f"<td>{esc(sem.get('adjustment'))}</td>"
            f"<td>{esc(sem.get('source_time_label'))}</td>"
            f"<td>{ds['published_rows']}</td><td>{ds['partition_count']}</td>"
            f"<td>{esc(ds['observed_start'])}</td>"
            f"<td>{esc(ds['observed_end'])}</td>"
            f"<td>{esc(ds['expected_status'])}</td></tr>"
        )
    parts.append("</table><h2>Batches by state</h2><table><tr><th>state</th><th>count</th></tr>")
    for state, count in sorted(report["batches_by_state"].items()):
        parts.append(f"<tr><td>{esc(state)}</td><td>{count}</td></tr>")
    parts.append("</table><h2>Quality issues / conflicts</h2>")
    parts.append(f"<p>resolved: {report['quality_issues']['resolved_count']}; unresolved:</p>")
    parts.append("<table><tr><th>issue</th><th>dataset</th><th>partition</th><th>code</th><th>created</th></tr>")
    for issue in report["quality_issues"]["unresolved"]:
        parts.append(
            f"<tr><td>{esc(issue['issue_id'])}</td>"
            f"<td>{esc(issue['dataset_id'])}</td>"
            f"<td>{esc(issue['partition'])}</td><td>{esc(issue['code'])}</td>"
            f"<td>{esc(issue['created_at'])}</td></tr>"
        )
    parts.append("</table><h2>Recording</h2>")
    parts.append(
        f"<p>status: {esc(report['recording']['status'])} — "
        f"{esc(report['recording']['note'])}</p>"
    )
    counts = report["recording"].get("counts")
    if counts:
        parts.append(
            "<p>journals: "
            f"{counts['journal_sessions']}; catalog-only: "
            f"{counts['catalog_only_sessions']}; with errors: "
            f"{counts['sessions_with_errors']}</p>"
        )
    parts.append(
        "<table><tr><th>session</th><th>authority</th><th>status</th>"
        "<th>catalog status</th><th>committed seq</th><th>durable last seq</th>"
        "<th>accepted</th><th>backlog</th><th>rejected</th><th>errors</th>"
        "<th>source spec</th>"
        "<th>calendar spec</th>"
        "<th>predecessor</th><th>successors</th><th>created</th><th>error</th></tr>"
    )
    for session in report["recording"]["sessions"]:
        parts.append(
            "<tr>"
            f"<td>{esc(session['session_id'])}</td>"
            f"<td>{esc(session['authority'])}</td>"
            f"<td>{esc(session['status'])}</td>"
            f"<td>{esc(session.get('catalog_status'))}</td>"
            f"<td>{esc_unknown(session.get('committed_seq'))}</td>"
            f"<td>{esc_unknown(session.get('durable_last_seq'))}</td>"
            # live in-memory counters: None renders as explicit UNKNOWN
            f"<td>{esc_unknown(session.get('accepted_seq'))}</td>"
            f"<td>{esc_unknown(session.get('backlog'))}</td>"
            f"<td>{esc_unknown(session.get('rejected'))}</td>"
            f"<td>{esc_unknown(session.get('errors'))}</td>"
            f"<td>{esc(session.get('source_spec'))}</td>"
            f"<td>{esc(session.get('calendar_spec'))}</td>"
            f"<td>{esc(session.get('predecessor_session_id'))}</td>"
            f"<td>{esc(', '.join(session.get('successor_session_ids') or []))}</td>"
            f"<td>{esc(session.get('created_at'))}</td>"
            f"<td>{esc(session.get('error'))}</td></tr>"
        )
    parts.append("</table>")
    parts.append("<h2>Assets</h2><table><tr><th>asset</th><th>origin</th><th>format</th><th>size</th><th>sha256</th><th>discovery</th></tr>")
    for asset in report["assets"]:
        parts.append(
            f"<tr><td>{esc(asset['asset_id'])}</td><td>{esc(asset['origin'])}</td>"
            f"<td>{esc(asset['format'])}</td><td>{asset['size']}</td>"
            f"<td>{esc(asset['sha256'])}</td><td>{esc(asset['discovery'])}</td></tr>"
        )
    parts.append("</table><h2>Snapshots</h2><table><tr><th>snapshot</th><th>created</th></tr>")
    for snap in report["snapshots"]:
        parts.append(f"<tr><td>{esc(snap['snapshot_id'])}</td><td>{esc(snap['created_at'])}</td></tr>")
    parts.append("</table><h2>Preserved candidates</h2><ul>")
    for name in report["candidate_files"]:
        parts.append(f"<li>{esc(name)}</li>")
    parts.append("</ul><h2>Disk usage (bytes)</h2><table><tr><th>area</th><th>bytes</th></tr>")
    for area, size in sorted(report["disk_bytes"].items()):
        parts.append(f"<tr><td>{esc(area)}</td><td>{size}</td></tr>")
    parts.append("</table></body></html>")
    return "".join(parts)


def write_report(store: Store, output: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    """Build the report and write the HTML (default: store reports/ dir)."""
    report = build_report(store)
    if output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = store.path.reports / f"report-{stamp}.html"
    else:
        output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(report), encoding="utf-8")
    return report, output_path


__all__ = ["build_report", "render_html", "write_report"]
