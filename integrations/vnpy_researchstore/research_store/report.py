"""Standalone store report: machine-readable summary + simple HTML.

Reports assets, datasets, coverage timeline (observed bounds only), sources,
quality issues/conflicts, recording status and disk usage. Missing, unknown
and partial states are reported faithfully — nothing is smoothed into a PASS.
No bulk market data is embedded; only catalog metadata and manifest coverage
ranges are read.
"""

from __future__ import annotations

import html
import json
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

    sessions = catalog.query_all(
        "SELECT session_id, status FROM recording_sessions ORDER BY created_at"
    )
    recording = {
        "status": "no_recording_sessions" if not sessions else "sessions_present",
        "sessions": [
            {"session_id": str(s["session_id"]), "status": str(s["status"])}
            for s in sessions
        ],
        "note": "recording/journal/aggregation land in WP08/WP09; an empty "
        "session table is reported, never a fabricated status",
    }

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

    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>research_store report</title>",
        "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:2em}"
        "table{border-collapse:collapse;margin-bottom:1.5em}"
        "td,th{border:1px solid #bbb;padding:3px 8px;text-align:left}"
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
