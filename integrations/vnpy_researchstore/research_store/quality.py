"""Bar-level and dataset-level quality evaluation.

Quality here is OBSERVATIONAL: rows are checked and flagged, never fixed.
Deterministic repairs are the repair index's business and arrive as
provenance, not as quality verdicts. The distinction the contract demands:

* a row repaired by the validated 133-key repair carries
  ``repaired_deterministic`` provenance and remains a preserved observation
  with its old/new/upstream candidates;
* DEFAULT QUALIFIED BACKTEST DATA excludes ALL repaired keys — the full
  133-key deterministic set, not merely the disputed subsets (118
  volume/amount or 119 any-market-field disputes) — each exclusion visible
  as a counted gap with real bounds until an explicit resolution admits a
  candidate (coordinator reconciliation 2026-09-16). Enforcement is
  captured per snapshot at ``freeze()`` time (manifest key
  ``default_qualified_exclusions``) and applied by ``SnapshotReader``
  default reads: queries intersecting an excluded interval raise
  ``CoverageGapError`` unless the snapshot explicitly allowed the gap, and
  allowed exclusions are filtered out of the returned rows — the allowance
  permits the missing interval, never the rejected row;
* a repaired key whose values differ from the independent upstream refetch
  is DISPUTED (``disputed_upstream_refetch``) and additionally stays a
  preserved conflict candidate, never silently resolved;
* negative volumes/amounts/OI in raw sources are flagged and preserved.

Aggregation produces a machine-readable :class:`QualityReport` with issue
codes, counts and evidence samples - never a fabricated PASS.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import IntegrityError, StoreError
from .objects import hash_file, verify_object

PRICE_FIELDS = ("open", "high", "low", "close")

# Repair provenance flags that exclude a row from DEFAULT qualified backtest
# data. The policy covers the FULL deterministic repaired-key set (all 133),
# regardless of whether a particular repair matches the upstream refetch:
# 118 (volume/amount disputes) and 119 (any-market-field disputes) are
# observed subsets of the same rule, never replacements for it.
DEFAULT_EXCLUSION_FLAGS: tuple[str, ...] = (
    "repaired_deterministic",
    "disputed_upstream_refetch",
    "disputed_upstream_refetch_auxiliary_only",
)

_ISSUE_SAMPLE_LIMIT = 5
_GAP_LISTING_LIMIT = 10_000


@dataclass
class QualityReport:
    """Aggregated quality results for one scope (batch/dataset/partition)."""

    scope: str
    rows_checked: int = 0
    issue_counts: Counter[str] = field(default_factory=Counter)
    samples: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def clean_rows(self) -> int:
        return self.rows_checked - sum(
            count
            for code, count in self.issue_counts.items()
            if not code.startswith("annotation:")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "rows_checked": self.rows_checked,
            "issue_counts": dict(self.issue_counts),
            "clean_rows": self.clean_rows,
            "samples": self.samples,
        }


def _add_issue(
    report: QualityReport, code: str, row: dict[str, Any]
) -> None:
    report.issue_counts[code] += 1
    if len(report.samples.get(code, [])) < _ISSUE_SAMPLE_LIMIT:
        evidence = {
            "instrument": row.get("instrument"),
            "source_label": row.get("source_label"),
            "trading_date": row.get("trading_date"),
            "provenance": row.get("provenance"),
        }
        report.samples.setdefault(code, []).append(evidence)


def check_row(row: dict[str, Any], report: QualityReport | None = None) -> list[str]:
    """Evaluate one canonical row; returns the issue codes found.

    Checks (all observational):

    * ``ohlc_envelope`` - high < low, or open/close outside [low, high];
    * ``nonpositive_price`` - any non-null OHLC <= 0;
    * ``negative_volume`` / ``negative_turnover`` / ``negative_open_interest``;
    * ``missing_price`` - all four OHLC null;
    * ``unknown_time_bounds`` - bar bounds unknown (e.g. SSQuant labels);
    * annotation codes from the normaliser flags (``negative:*``,
      ``disputed_upstream_refetch`` etc.) are folded into issue counts with
      the ``annotation:`` prefix so they never count as row damage.
    """
    issues: list[str] = []
    open_, high = row.get("open"), row.get("high")
    low, close = row.get("low"), row.get("close")
    prices = {"open": open_, "high": high, "low": low, "close": close}
    present = {name: value for name, value in prices.items() if value is not None}
    if not present:
        issues.append("missing_price")
    else:
        if any(value <= 0 for value in present.values()):
            issues.append("nonpositive_price")
        if "high" in present and "low" in present and present["high"] < present["low"]:
            issues.append("ohlc_envelope")
        elif "high" in present and "low" in present:
            for name in ("open", "close"):
                if name in present and not (
                    present["low"] <= present[name] <= present["high"]
                ):
                    issues.append("ohlc_envelope")
                    break
    for field_name, code in (
        ("volume", "negative_volume"),
        ("turnover", "negative_turnover"),
        ("open_interest", "negative_open_interest"),
    ):
        value = row.get(field_name)
        if value is not None and value < 0:
            issues.append(code)
    if row.get("bar_start_ns") is None or row.get("bar_end_ns") is None:
        issues.append("unknown_time_bounds")

    if report is not None:
        report.rows_checked += 1
        for code in issues:
            _add_issue(report, code, row)
        for flag in row.get("quality_flags", []):
            _add_issue(report, f"annotation:{flag}", row)
    return issues


def check_rows(rows: list[dict[str, Any]], scope: str) -> QualityReport:
    """Evaluate a batch of canonical rows and aggregate a report."""
    report = QualityReport(scope=scope)
    for row in rows:
        check_row(row, report)
    return report


def required_fields_status(
    rows: list[dict[str, Any]], required: tuple[str, ...]
) -> dict[str, Any]:
    """Completeness of user-required fields across rows.

    Reports per-field null counts; a field missing from the source shows up
    as all-null, an "unavailable field" distinct from "no data".
    """
    total = len(rows)
    nulls = {name: 0 for name in required}
    for row in rows:
        for name in required:
            if row.get(name) is None:
                nulls[name] += 1
    return {
        "rows": total,
        "required": list(required),
        "null_counts": nulls,
        "fully_populated": all(count == 0 for count in nulls.values()),
    }


# ---------------------------------------------------------------------------
# Store-bound quality (observational checks over PUBLISHED data)
# ---------------------------------------------------------------------------


def _core_row_to_canonical(row: dict[str, Any]) -> dict[str, Any]:
    """Map a published BARS_SCHEMA_V1 row to the canonical check shape."""
    trading_date = row.get("trading_date")
    return {
        "instrument": row.get("instrument_id") or row.get("series_id"),
        "source_label": row.get("source_label"),
        "trading_date": (
            None if trading_date is None else str(trading_date)[:10]
        ),
        "bar_start_ns": row.get("bar_start"),
        "bar_end_ns": row.get("bar_end"),
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "volume": row.get("volume"),
        "turnover": row.get("turnover"),
        "open_interest": row.get("open_interest"),
        "quality_flags": list(_field_quality_of(row).get("flags", [])),
        "provenance": {
            "asset_id": row.get("asset_id"),
            "batch_id": row.get("batch_id"),
            "transform_version": row.get("transform_version"),
        },
    }


def _field_quality_of(row: dict[str, Any]) -> dict[str, Any]:
    """Parsed ``field_quality`` JSON of a published row ({} when absent)."""
    raw_quality = row.get("field_quality")
    if not raw_quality:
        return {}
    try:
        parsed = json.loads(str(raw_quality))
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"unparseable_field_quality": str(raw_quality)}


def _scan_published(
    store: Any, dataset_id: str, partitions: list[str] | None
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """Stream integrity-verified published rows of one dataset.

    Yields ``(canonical_row, parsed_field_quality)`` pairs from the pinned
    partition head files listed in the immutable revision manifests — never
    by globbing object directories. Manifest and object hashes are verified
    before reading.
    """
    import pyarrow.parquet as pq

    heads = store.catalog.query_all(
        "SELECT h.partition, r.manifest_path, r.manifest_sha256"
        " FROM partition_heads h JOIN revisions r ON r.revision_id = h.revision_id"
        " WHERE h.dataset_id=? ORDER BY h.partition",
        (dataset_id,),
    )
    for head in heads:
        partition = str(head["partition"])
        if partitions is not None and partition not in partitions:
            continue
        manifest_path = Path(str(head["manifest_path"]))
        if hash_file(manifest_path) != str(head["manifest_sha256"]):
            raise IntegrityError(f"tampered revision manifest {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest.get("files", []):
            verify_object(store.root, str(entry["path"]), str(entry["sha256"]))
            table = pq.read_table(str(store.root / str(entry["path"])))
            for raw in table.to_pylist():
                yield _core_row_to_canonical(raw), _field_quality_of(raw)


def matched_exclusion_flags(quality_flags: list[str]) -> list[str]:
    """Flags of ``DEFAULT_EXCLUSION_FLAGS`` present on one row (policy order)."""
    return [flag for flag in DEFAULT_EXCLUSION_FLAGS if flag in quality_flags]


def _exclusion_entry(
    dataset_id: str, partition: str, raw: dict[str, Any], matched: list[str]
) -> dict[str, Any] | None:
    """Map one published row to a bounded exclusion entry (None when the row
    cannot be addressed as a bounded gap)."""
    instrument = raw.get("instrument_id") or raw.get("series_id")
    start_ns = raw.get("bar_start")
    end_ns = raw.get("bar_end")
    if instrument is None or start_ns is None or end_ns is None:
        # Cannot address the row as a bounded gap (e.g. unknown time
        # bounds); the quality report still counts it, but the reader
        # filter/gap check needs real bounds.
        return None
    return {
        "dataset_id": dataset_id,
        "partition": partition,
        "instrument": instrument,
        "start_ns": start_ns,
        "end_ns": end_ns,
        "source_label": raw.get("source_label"),
        "flags": matched,
    }


def scan_exclusion_entries_in_files(
    root: Path,
    dataset_id: str,
    files: list[tuple[str, str, str]],
) -> Iterator[dict[str, Any]]:
    """Stream exclusion entries from an EXPLICIT immutable file reference list.

    ``files`` carries ``(partition, relative_path, sha256)`` triples captured
    earlier (e.g. by ``freeze`` inside its consistent read transaction). Hash
    verification and Parquet scanning happen HERE, outside any catalog
    transaction, over exactly the captured references — never by re-querying
    current mutable heads. This is the freeze-time capture path; the quality
    report uses ``scan_default_qualified_exclusions`` below.
    """
    import pyarrow.parquet as pq

    for partition, rel_path, sha256 in files:
        verify_object(root, rel_path, sha256)
        table = pq.read_table(str(root / rel_path))
        for raw in table.to_pylist():
            field_quality = _field_quality_of(raw)
            flags = list(field_quality.get("flags", []))
            matched = matched_exclusion_flags(flags)
            if not matched:
                continue
            entry = _exclusion_entry(dataset_id, partition, raw, matched)
            if entry is not None:
                yield entry


def scan_default_qualified_exclusions(
    store: Any, dataset_id: str, partitions: list[str] | None = None
) -> Iterator[dict[str, Any]]:
    """Stream the default-qualified EXCLUSION set over PUBLISHED data.

    Yields one entry per published row carrying any ``DEFAULT_EXCLUSION_FLAGS``
    provenance flag, with the row's real normalized bounds, its partition and
    matched flags. This is the single policy evaluation shared by the quality
    report (``store_default_qualified``) and the freeze-time snapshot capture:
    both must agree on exactly which rows are excluded from default qualified
    backtest data. Rows are streamed from integrity-verified pinned head
    files; nothing is modified.
    """
    heads = store.catalog.query_all(
        "SELECT h.partition, r.manifest_path, r.manifest_sha256"
        " FROM partition_heads h JOIN revisions r ON r.revision_id = h.revision_id"
        " WHERE h.dataset_id=? ORDER BY h.partition",
        (dataset_id,),
    )
    file_refs: list[tuple[str, str, str]] = []
    for head in heads:
        partition = str(head["partition"])
        if partitions is not None and partition not in partitions:
            continue
        manifest_path = Path(str(head["manifest_path"]))
        if hash_file(manifest_path) != str(head["manifest_sha256"]):
            raise IntegrityError(f"tampered revision manifest {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for file_entry in manifest.get("files", []):
            file_refs.append(
                (partition, str(file_entry["path"]), str(file_entry["sha256"]))
            )
    yield from scan_exclusion_entries_in_files(store.root, dataset_id, file_refs)


def _default_qualified_accumulator() -> dict[str, Any]:
    return {
        "rows_total": 0,
        "rows_excluded": 0,
        "excluded_by_flag": Counter[str](),
        "gaps": [],
        "candidates": {"old_new": 0, "upstream_refetch": 0, "missing": 0},
    }


def _observe_default_qualified(
    acc: dict[str, Any], row: dict[str, Any], field_quality: dict[str, Any]
) -> None:
    """Fold one published row into the default-qualified policy evaluation."""
    acc["rows_total"] += 1
    matched = matched_exclusion_flags(row["quality_flags"])
    if not matched:
        return
    acc["rows_excluded"] += 1
    for flag in matched:
        acc["excluded_by_flag"][flag] += 1
    if len(acc["gaps"]) < _GAP_LISTING_LIMIT:
        acc["gaps"].append(
            {
                "instrument": row["instrument"],
                "start_ns": row["bar_start_ns"],
                "end_ns": row["bar_end_ns"],
                "trading_date": row["trading_date"],
                "source_label": row["source_label"],
                "flags": matched,
            }
        )
    repair = field_quality.get("repair")
    if isinstance(repair, dict) and repair.get("old"):
        acc["candidates"]["old_new"] += 1
        if repair.get("upstream_refetch"):
            acc["candidates"]["upstream_refetch"] += 1
    else:
        acc["candidates"]["missing"] += 1


def _default_qualified_payload(
    dataset_id: str, partitions_checked: list[str], acc: dict[str, Any]
) -> dict[str, Any]:
    return {
        "policy": (
            "all deterministic repaired keys excluded from default "
            "qualified data (full repaired-key set; 118/119 disputed "
            "subsets never replace it) — exclusions are counted gaps "
            "with real bounds, candidates preserved for explicit "
            "resolution"
        ),
        "dataset_id": dataset_id,
        "partitions_checked": partitions_checked,
        "rows_total": acc["rows_total"],
        "rows_qualified": acc["rows_total"] - acc["rows_excluded"],
        "rows_excluded": acc["rows_excluded"],
        "excluded_by_flag": dict(acc["excluded_by_flag"]),
        "excluded_gap_count": acc["rows_excluded"],
        "excluded_gaps": acc["gaps"],
        "excluded_gaps_list_truncated": acc["rows_excluded"] > len(acc["gaps"]),
        "candidates_preserved": dict(acc["candidates"]),
    }


def store_default_qualified(
    store: Any,
    dataset_id: str,
    partitions: list[str] | None = None,
) -> dict[str, Any]:
    """Evaluate the default-qualified exclusion policy over PUBLISHED data.

    Streams the pinned head files (integrity-verified) and reports explicit
    row/gap counts for the repaired-key exclusions, including each excluded
    key's real normalized bounds (usable directly as ``KnownGap`` intervals)
    and an audit of preserved old/new/upstream candidates. A flag alone is
    not treated as proof of exclusion: the gap list and counts ARE the
    exclusion evidence. The same policy is enforced for snapshot reads via
    ``scan_default_qualified_exclusions`` captured at ``freeze()`` time.
    """
    dataset = store.catalog.get_dataset(dataset_id)
    if dataset is None:
        raise StoreError(f"unknown dataset {dataset_id}")
    acc = _default_qualified_accumulator()
    partitions_checked: list[str] = []
    heads = store.catalog.query_all(
        "SELECT partition FROM partition_heads WHERE dataset_id=?"
        " ORDER BY partition",
        (dataset_id,),
    )
    for head in heads:
        partition = str(head["partition"])
        if partitions is not None and partition not in partitions:
            continue
        partitions_checked.append(partition)
    for row, field_quality in _scan_published(store, dataset_id, partitions):
        _observe_default_qualified(acc, row, field_quality)
    return _default_qualified_payload(dataset_id, partitions_checked, acc)


def store_quality(
    store: Any,
    dataset_id: str,
    partitions: list[str] | None = None,
    required: tuple[str, ...] = ("open", "high", "low", "close", "volume"),
) -> dict[str, Any]:
    """Observational quality over published data of one dataset.

    Streams the pinned head files (integrity-verified before reading) and
    re-runs the row checks; per-field NULL counts for ``required`` are
    reported separately so "unavailable field" stays distinct from "no data".
    Nothing is repaired or filled; issue counts aggregate the flags the
    importer attached (repair provenance, untrusted amounts, unknown time
    bounds) as ``annotation:*`` entries. The payload carries the
    ``default_qualified`` policy evaluation (full repaired-key exclusion
    with explicit row/gap counts) computed in the same pass.
    """
    dataset = store.catalog.get_dataset(dataset_id)
    if dataset is None:
        raise StoreError(f"unknown dataset {dataset_id}")
    semantic = json.loads(str(dataset["semantic_json"]))
    report = QualityReport(scope=f"store:{dataset_id}")
    required_nulls: Counter[str] = Counter()
    rows_seen = 0
    partitions_checked: list[str] = []
    dq = _default_qualified_accumulator()
    for head in store.catalog.query_all(
        "SELECT h.partition FROM partition_heads h WHERE h.dataset_id=?"
        " ORDER BY h.partition",
        (dataset_id,),
    ):
        partition = str(head["partition"])
        if partitions is not None and partition not in partitions:
            continue
        partitions_checked.append(partition)
    for row, field_quality in _scan_published(store, dataset_id, partitions):
        check_row(row, report)
        rows_seen += 1
        for name in required:
            if row.get(name) is None:
                required_nulls[name] += 1
        _observe_default_qualified(dq, row, field_quality)
    payload = report.to_dict()
    payload.update(
        {
            "dataset_id": dataset_id,
            "semantic": semantic,
            "partitions_checked": partitions_checked,
            "required_fields": {
                "required": list(required),
                "null_counts": dict(required_nulls),
                "fully_populated": rows_seen > 0 and not required_nulls,
            },
            "default_qualified": _default_qualified_payload(
                dataset_id, partitions_checked, dq
            ),
        }
    )
    return payload


def write_quality_report(
    store: Any,
    dataset_id: str,
    partitions: list[str] | None = None,
    required: tuple[str, ...] = ("open", "high", "low", "close", "volume"),
) -> tuple[dict[str, Any], Path]:
    """Compute store quality and persist it under ``reports/`` (new file per
    run; historical reports are never overwritten)."""
    payload = store_quality(store, dataset_id, partitions, required)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = store.path.reports / f"quality-{dataset_id}-{stamp}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return payload, target


__all__ = [
    "DEFAULT_EXCLUSION_FLAGS",
    "QualityReport",
    "check_row",
    "check_rows",
    "matched_exclusion_flags",
    "required_fields_status",
    "scan_default_qualified_exclusions",
    "scan_exclusion_entries_in_files",
    "store_default_qualified",
    "store_quality",
    "write_quality_report",
]
