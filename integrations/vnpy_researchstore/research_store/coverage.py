"""Coverage evaluation for imported bar data.

Coverage is computed from OBSERVED data only. "Expected" completeness is
reported as unknown unless the caller supplies positive calendar evidence
(listing/delisting plus trading calendar plus suspension knowledge); min/max
range is never presented as completeness. Gaps are reported, never filled.

Each instrument accumulates:

* observed rows / accepted rows / quarantined rows;
* distinct trading dates or labels observed;
* interval sets reasoned from the data (which bar boundaries exist);
* explicit gap lists when a calendar is provided.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .models import IntegrityError
from .objects import hash_file

_GAP_MAX_LISTING = 10_000


@dataclass
class InstrumentCoverage:
    instrument: str
    series_kind: str = "instrument"
    rows_observed: int = 0
    rows_accepted: int = 0
    rows_quarantined: int = 0
    first_label: str | None = None
    last_label: str | None = None
    trading_dates: set[str] = field(default_factory=set)
    interval_minutes_seen: set[int] = field(default_factory=set)
    flags: set[str] = field(default_factory=set)

    def observe(
        self,
        label: str,
        trading_date: str | None,
        interval_minutes: int | None,
        quarantined: bool,
    ) -> None:
        if quarantined:
            self.rows_quarantined += 1
        else:
            self.rows_accepted += 1
        self.rows_observed += 1
        if self.first_label is None or label < self.first_label:
            self.first_label = label
        if self.last_label is None or label > self.last_label:
            self.last_label = label
        if trading_date:
            self.trading_dates.add(trading_date)
        if interval_minutes is not None:
            self.interval_minutes_seen.add(interval_minutes)


@dataclass
class CoverageReport:
    scope: str
    instruments: dict[str, InstrumentCoverage] = field(default_factory=dict)
    calendar: list[str] | None = None
    expected_status: str = "unknown"

    def instrument(self, row: dict[str, Any]) -> InstrumentCoverage:
        name = row["instrument"]
        entry = self.instruments.get(name)
        if entry is None:
            entry = InstrumentCoverage(
                instrument=name, series_kind=row.get("series_kind", "instrument")
            )
            self.instruments[name] = entry
        return entry

    def observe_row(self, row: dict[str, Any], quarantined: bool = False) -> None:
        entry = self.instrument(row)
        interval = None
        start, end = row.get("bar_start_ns"), row.get("bar_end_ns")
        if start is not None and end is not None and end > start:
            interval = int((end - start) // 60_000_000_000)
        entry.observe(
            row.get("source_label", ""),
            row.get("trading_date"),
            interval,
            quarantined,
        )

    def to_dict(self) -> dict[str, Any]:
        instruments = {}
        for name, entry in sorted(self.instruments.items()):
            instruments[name] = {
                "series_kind": entry.series_kind,
                "rows_observed": entry.rows_observed,
                "rows_accepted": entry.rows_accepted,
                "rows_quarantined": entry.rows_quarantined,
                "first_label": entry.first_label,
                "last_label": entry.last_label,
                "trading_dates_observed": len(entry.trading_dates),
                "interval_minutes_seen": sorted(entry.interval_minutes_seen),
                "flags": sorted(entry.flags),
            }
        return {
            "scope": self.scope,
            "expected_status": self.expected_status,
            "instruments": instruments,
        }


def _parse_day(day: str) -> date:
    return date(int(day[:4]), int(day[5:7]), int(day[8:10]))


def compute_gaps(
    entry: InstrumentCoverage, calendar: list[str]
) -> dict[str, Any]:
    """List missing trading days for one instrument against a calendar.

    The calendar must be the positive list of trading days between the
    instrument's first and last observed date; days before listing / after
    delisting are out of scope and are not counted as gaps. Suspensions are
    NOT known to this layer - a suspension-aware calendar must already
    exclude them, otherwise the days appear as gaps (explicitly honest).
    """
    if not entry.trading_dates:
        return {"gaps": [], "gap_days": 0, "note": "no trading dates observed"}
    observed = entry.trading_dates
    cal_in_window = [
        day
        for day in calendar
        if entry.first_label is not None
        and entry.last_label is not None
        and _parse_day(entry.first_label[:10]) <= _parse_day(day) <= _parse_day(entry.last_label[:10])
    ]
    missing = [day for day in cal_in_window if day not in observed]
    return {
        "gaps": missing[:_GAP_MAX_LISTING],
        "gap_days": len(missing),
        "calendar_days_in_window": len(cal_in_window),
    }


def coverage_with_calendar(
    report: CoverageReport, calendar: list[str]
) -> dict[str, Any]:
    """Attach gap evaluation to a report using trading-calendar evidence.

    Only call this with real calendar evidence; otherwise
    ``report.expected_status`` stays ``"unknown"`` and no completeness claim
    is made.
    """
    report.calendar = sorted(calendar)
    report.expected_status = "calendar_only_no_suspensions"
    payload = report.to_dict()
    payload["gaps"] = {
        name: compute_gaps(entry, report.calendar)
        for name, entry in sorted(report.instruments.items())
    }
    return payload


def summarize_coverage(
    rows: list[dict[str, Any]],
    scope: str,
    quarantined_keys: set[tuple[str, str]] | None = None,
) -> CoverageReport:
    """Build a coverage report from canonical rows (streaming-friendly)."""
    report = CoverageReport(scope=scope)
    for row in rows:
        key = (row.get("instrument", ""), row.get("source_label", ""))
        is_quarantined = quarantined_keys is not None and key in quarantined_keys
        report.observe_row(row, quarantined=is_quarantined)
    return report


# ---------------------------------------------------------------------------
# Store-bound coverage (observed state of published data; never filled)
# ---------------------------------------------------------------------------


def store_coverage(store: Any, dataset_id: str | None = None) -> dict[str, Any]:
    """Observed coverage of PUBLISHED data, from catalog heads + manifests.

    Reads only catalog metadata and immutable revision manifests (never globs
    object directories). Expected completeness stays ``unknown`` — no calendar
    evidence exists at this layer; min/max ranges are reported as observed
    bounds, never as completeness. Unresolved conflicts are counted per
    partition so default consumers can see the blocked scopes.
    """
    if dataset_id is not None:
        datasets = [
            row
            for row in store.catalog.query_all(
                "SELECT * FROM datasets WHERE dataset_id=?", (dataset_id,)
            )
        ]
    else:
        datasets = list(store.catalog.query_all("SELECT * FROM datasets"))
    report: dict[str, Any] = {
        "store_root": str(store.root),
        "expected_status": "unknown",
        "datasets": {},
    }
    for dataset in datasets:
        ds_id = str(dataset["dataset_id"])
        semantic = json.loads(str(dataset["semantic_json"]))
        heads = store.catalog.query_all(
            "SELECT h.partition, h.revision_id, r.rows, r.manifest_path,"
            " r.manifest_sha256, r.created_at FROM partition_heads h"
            " JOIN revisions r ON r.revision_id = h.revision_id"
            " WHERE h.dataset_id=? ORDER BY h.partition",
            (ds_id,),
        )
        partitions: dict[str, Any] = {}
        total_rows = 0
        for head in heads:
            manifest_path = Path(str(head["manifest_path"]))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            coverage = manifest.get("coverage", {})
            unresolved = store.catalog.unresolved_issues(
                ds_id, str(head["partition"])
            )
            partitions[str(head["partition"])] = {
                "revision_id": str(head["revision_id"]),
                "rows": int(head["rows"]),
                "observed_start_ns": coverage.get("start_ns"),
                "observed_end_ns": coverage.get("end_ns"),
                "files": len(manifest.get("files", [])),
                "unresolved_conflicts": len(unresolved),
            }
            total_rows += int(head["rows"])
        report["datasets"][ds_id] = {
            "semantic": semantic,
            "partitions": partitions,
            "published_rows": total_rows,
            "partition_count": len(partitions),
        }
    return report


def write_coverage_report(
    store: Any, dataset_id: str | None = None
) -> tuple[dict[str, Any], Path]:
    """Compute store coverage and persist it under ``reports/`` (new file per
    run; historical reports are never overwritten)."""
    report = store_coverage(store, dataset_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scope = dataset_id or "all"
    target = store.path.reports / f"coverage-{scope}-{stamp}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return report, target


def fetch_by_source_labels(
    store: Any, dataset_id: str, labels: list[str]
) -> list[dict[str, Any]]:
    """Inspection query over PUBLISHED rows by ORIGINAL source label.

    This deliberately bypasses normalized bar-time semantics: it answers
    "what did the source say at this label" from the pinned head files, which
    is a different question from the reader's ``[start, end)`` bar-time
    queries. File integrity is verified before reading.
    """
    import duckdb  # local import: store queries share the core dependency

    from .objects import verify_object

    heads = store.catalog.query_all(
        "SELECT h.revision_id, r.manifest_path, r.manifest_sha256"
        " FROM partition_heads h JOIN revisions r ON r.revision_id = h.revision_id"
        " WHERE h.dataset_id=?",
        (dataset_id,),
    )
    files: list[str] = []
    for head in heads:
        manifest_path = Path(str(head["manifest_path"]))
        if hash_file(manifest_path) != str(head["manifest_sha256"]):
            raise IntegrityError(f"tampered revision manifest {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest.get("files", []):
            verify_object(store.root, str(entry["path"]), str(entry["sha256"]))
            files.append(str(store.root / str(entry["path"])))
    if not files:
        return []
    file_list = ", ".join(f"'{Path(f).as_posix()}'" for f in files)
    label_list = ", ".join("'" + label.replace("'", "''") + "'" for label in labels)
    con = duckdb.connect(":memory:")
    try:
        cursor = con.execute(
            f"SELECT * FROM read_parquet([{file_list}], union_by_name=true)"
            f" WHERE source_label IN ({label_list})"
            " ORDER BY COALESCE(instrument_id, series_id), bar_start"
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        con.close()


__all__ = [
    "CoverageReport",
    "InstrumentCoverage",
    "compute_gaps",
    "coverage_with_calendar",
    "fetch_by_source_labels",
    "store_coverage",
    "summarize_coverage",
    "write_coverage_report",
]
