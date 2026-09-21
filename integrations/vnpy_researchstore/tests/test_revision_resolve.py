"""Conflict resolution tests: new revision only, old snapshots immutable."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from research_store import (
    ConflictResolution,
    StoreError,
    compute_dataset_id,
    resolve_conflict,
)

from conftest import bar_row, import_rows, make_spec, ns


def _head_rows(store, dataset_id: str, partition: str = "2024") -> dict[str, dict]:
    head = store.catalog.get_head(dataset_id, partition)
    rev = store.catalog.get_revision(head)
    manifest = json.loads(Path(rev["manifest_path"]).read_text(encoding="utf-8"))
    return {
        r["instrument_id"]: r
        for f in manifest["files"]
        for r in pq.read_table(str(store.root / f["path"])).to_pylist()
    }


def _conflicted(store, tmp_path: Path):
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)
    start = ns(2024, 1, 2, 9, 30)
    base = import_rows(store, tmp_path, [bar_row(dataset_id, "000001", start, close=10.0)],
                       spec, asset_name="base.csv", asset_content=b"base")
    receipt = import_rows(
        store, tmp_path, [bar_row(dataset_id, "000001", start, close=99.0)],
        spec, asset_name="cand.csv", asset_content=b"cand",
    )
    conflict = receipt.conflicts[0]
    return spec, dataset_id, start, base, conflict


def test_resolve_candidate_creates_new_revision(store, tmp_path: Path) -> None:
    spec, dataset_id, start, base, conflict = _conflicted(store, tmp_path)
    old_head = store.catalog.get_head(dataset_id, "2024")

    receipt = resolve_conflict(
        store, dataset_id, "2024", conflict.conflict_id,
        ConflictResolution.CANDIDATE, "upstream refetch confirmed 99.0",
    )
    assert receipt.revision_id != old_head
    assert receipt.parent_revision == old_head
    assert _head_rows(store, dataset_id)["000001"]["close"] == 99.0

    # Old revision is never altered.
    old_rev = store.catalog.get_revision(old_head)
    old_manifest = json.loads(Path(old_rev["manifest_path"]).read_text(encoding="utf-8"))
    old_rows = [
        r for f in old_manifest["files"]
        for r in pq.read_table(str(store.root / f["path"])).to_pylist()
    ]
    assert old_rows[0]["close"] == 10.0

    issue = store.catalog.query_one(
        "SELECT * FROM quality_issues WHERE issue_id=?", (conflict.conflict_id,)
    )
    assert issue["resolution"] == "candidate"
    assert issue["resolved_by_revision"] == receipt.revision_id


def test_resolve_existing_keeps_current_rows(store, tmp_path: Path) -> None:
    spec, dataset_id, start, base, conflict = _conflicted(store, tmp_path)
    resolve_conflict(store, dataset_id, "2024", conflict.conflict_id,
                     ConflictResolution.EXISTING, "vendor correction rejected")
    assert _head_rows(store, dataset_id)["000001"]["close"] == 10.0


def test_resolve_quarantine_leaves_visible_gap(store, tmp_path: Path) -> None:
    spec, dataset_id, start, base, conflict = _conflicted(store, tmp_path)
    resolve_conflict(store, dataset_id, "2024", conflict.conflict_id,
                     ConflictResolution.QUARANTINE, "both values untrusted")
    assert _head_rows(store, dataset_id) == {}  # gap, not zero/filled


def test_double_resolution_rejected(store, tmp_path: Path) -> None:
    spec, dataset_id, start, base, conflict = _conflicted(store, tmp_path)
    resolve_conflict(store, dataset_id, "2024", conflict.conflict_id,
                     ConflictResolution.EXISTING, "first decision")
    with pytest.raises(StoreError, match="already resolved"):
        resolve_conflict(store, dataset_id, "2024", conflict.conflict_id,
                         ConflictResolution.CANDIDATE, "second decision")


def test_resolution_requires_reason(store, tmp_path: Path) -> None:
    spec, dataset_id, start, base, conflict = _conflicted(store, tmp_path)
    with pytest.raises(StoreError, match="reason"):
        resolve_conflict(store, dataset_id, "2024", conflict.conflict_id,
                         ConflictResolution.EXISTING, "")
