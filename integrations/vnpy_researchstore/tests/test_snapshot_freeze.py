"""Snapshot tests: immutability, exact revision selection, quality binding."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_store import (
    ConflictResolution,
    KnownGap,
    Selection,
    SnapshotRequest,
    StoreError,
    UnknownDatasetError,
    UnresolvedConflictError,
    compute_dataset_id,
    freeze,
    open_snapshot,
    resolve_conflict,
)

from conftest import NS_MINUTE, bar_row, import_rows, make_spec, ns

from datetime import date


def _import_two_waves(store, tmp_path: Path):
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)
    import_rows(store, tmp_path,
                [bar_row(dataset_id, "000001", ns(2024, 1, 2, 9, 30), close=10.0)],
                spec, asset_name="w1.csv", asset_content=b"w1")
    return spec, dataset_id


def _all_rows(store, snapshot_id: str, dataset_id: str) -> list[dict]:
    with open_snapshot(store, snapshot_id) as reader:
        return [
            row
            for batch in reader.bars(dataset_id)
            for row in batch.to_pylist()
        ]


def test_snapshot_selects_exact_revisions_immutably(store, tmp_path: Path) -> None:
    spec, dataset_id = _import_two_waves(store, tmp_path)
    snap1 = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "2024"),)))

    # Later import advances the head; snap1 must be unaffected.
    import_rows(store, tmp_path,
                [bar_row(dataset_id, "000001", ns(2024, 1, 3, 9, 30), close=11.0,
                         trading=date(2024, 1, 3))],
                spec, asset_name="w2.csv", asset_content=b"w2")
    snap2 = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "2024"),)))

    assert snap1.snapshot_id != snap2.snapshot_id
    rows1 = _all_rows(store, snap1.snapshot_id, dataset_id)
    rows2 = _all_rows(store, snap2.snapshot_id, dataset_id)
    assert len(rows1) == 1
    assert len(rows2) == 2

    # snap1 manifest is immutable on disk and still pins the first revision.
    manifest = json.loads(Path(snap1.manifest_path).read_text(encoding="utf-8"))
    assert manifest["selections"][0]["rows"] == 1


def test_freeze_is_deterministic_for_unchanged_state(store, tmp_path: Path) -> None:
    spec, dataset_id = _import_two_waves(store, tmp_path)
    req = SnapshotRequest(selections=(Selection(dataset_id, "*"),))
    assert freeze(store, req).snapshot_id == freeze(store, req).snapshot_id


def test_freeze_captures_consistent_heads(store, tmp_path: Path) -> None:
    spec, dataset_id = _import_two_waves(store, tmp_path)
    ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
    manifest = json.loads(Path(ref.manifest_path).read_text(encoding="utf-8"))
    head = store.catalog.get_head(dataset_id, "2024")
    assert manifest["selections"][0]["revision_id"] == head
    assert manifest["selections"][0]["files"], "files pinned with hashes"
    assert all("sha256" in f for f in manifest["selections"][0]["files"])


def test_freeze_unknown_dataset_and_empty_selection_fail(store, tmp_path: Path) -> None:
    spec, dataset_id = _import_two_waves(store, tmp_path)
    with pytest.raises(UnknownDatasetError):
        freeze(store, SnapshotRequest(selections=(Selection("ds-nope", "*"),)))
    with pytest.raises(StoreError, match="no published partitions"):
        freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "2099"),)))
    with pytest.raises(StoreError, match="at least one selection"):
        freeze(store, SnapshotRequest(selections=()))


def test_freeze_fails_on_unresolved_conflict(store, tmp_path: Path) -> None:
    spec, dataset_id = _import_two_waves(store, tmp_path)
    import_rows(store, tmp_path,
                [bar_row(dataset_id, "000001", ns(2024, 1, 2, 9, 30), close=99.0)],
                spec, asset_name="c.csv", asset_content=b"c")
    with pytest.raises(UnresolvedConflictError):
        freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "2024"),)))


def test_snapshot_quality_binding_quarantine_gap(store, tmp_path: Path) -> None:
    spec, dataset_id = _import_two_waves(store, tmp_path)
    conflict_ts = ns(2024, 1, 2, 9, 30)
    receipt = import_rows(
        store, tmp_path,
        [bar_row(dataset_id, "000001", conflict_ts, close=99.0)],
        spec, asset_name="c.csv", asset_content=b"c",
    )
    resolve_conflict(store, dataset_id, "2024", receipt.conflicts[0].conflict_id,
                     ConflictResolution.QUARANTINE, "disputed; visible gap required")

    ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "2024"),)))
    manifest = json.loads(Path(ref.manifest_path).read_text(encoding="utf-8"))
    assert manifest["quality_decisions"], "quality decisions bound to snapshot"

    # Reader rejects queries over the quarantined key...
    from datetime import datetime, timezone

    from research_store import CoverageGapError

    with open_snapshot(store, ref.snapshot_id) as reader:
        with pytest.raises(CoverageGapError):
            list(reader.bars(
                dataset_id,
                start=datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc),
                end=datetime(2024, 1, 3, 0, 0, tzinfo=timezone.utc),
            ))
        # ...unless the snapshot explicitly allows the gap with a reason.
    ref2 = freeze(store, SnapshotRequest(
        selections=(Selection(dataset_id, "2024"),),
        # The allowed gap must cover the disputed bar's full real bounds
        # [bar_start, bar_end), recorded as gap_ns at conflict detection.
        allow_known_gaps=(KnownGap(dataset_id, conflict_ts, conflict_ts + NS_MINUTE,
                                   "quarantined disputed close"),),
    ))
    with open_snapshot(store, ref2.snapshot_id) as reader:
        rows = [
            row for batch in reader.bars(
                dataset_id,
                start=datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc),
                end=datetime(2024, 1, 3, 0, 0, tzinfo=timezone.utc),
            )
            for row in batch.to_pylist()
        ]
    assert rows == []  # gap stays empty: no zero/forward fill


def test_allow_known_gaps_requires_reason(store, tmp_path: Path) -> None:
    spec, dataset_id = _import_two_waves(store, tmp_path)
    with pytest.raises(StoreError, match="reason"):
        freeze(store, SnapshotRequest(
            selections=(Selection(dataset_id, "2024"),),
            allow_known_gaps=(KnownGap(dataset_id, 0, 1, ""),),
        ))
