"""Core fix03 F1: the public conflict receipt exposes the real gap bounds.

A caller must be able to import conflicting bars, inspect only public
receipt fields, resolve QUARANTINE, construct the explicit KnownGap
allowance, and freeze/query successfully while retaining the gap — without
permission the intersecting query must fail. No private sidecar parsing and
no assumed 1ns width.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from research_store import (
    BatchState,
    ConflictResolution,
    CoverageGapError,
    ImportRequest,
    Interval,
    KnownGap,
    Selection,
    SnapshotRequest,
    UnresolvedConflictError,
    compute_dataset_id,
    freeze,
    import_asset,
    open_snapshot,
    recover,
    resolve_conflict,
)
from research_store import revisions

from conftest import NS_MINUTE, bar_row, import_rows, make_asset, make_spec, ns


def _minute_conflict(store, tmp_path: Path):
    spec = make_spec(interval=Interval.M1)
    dataset_id = compute_dataset_id(spec)
    start = ns(2024, 1, 2, 9, 32)
    import_rows(
        store, tmp_path,
        [bar_row(dataset_id, "510300", start, close=4.08, trading=date(2024, 1, 2))],
        spec, asset_name="base.csv", asset_content=b"base",
    )
    receipt = import_rows(
        store, tmp_path,
        [bar_row(dataset_id, "510300", start, close=4.09, trading=date(2024, 1, 2))],
        spec, asset_name="overlay.csv", asset_content=b"overlay",
    )
    assert receipt.state is BatchState.CONFLICTED
    return spec, dataset_id, start, receipt


def test_public_receipt_carries_real_bar_width_not_1ns(store, tmp_path: Path) -> None:
    _, dataset_id, start, receipt = _minute_conflict(store, tmp_path)
    conflict = receipt.conflicts[0]
    assert conflict.gap_ns == (start, start + NS_MINUTE)  # real 60s bar bounds
    # The public bounds equal the interval the reader will actually enforce.
    issue = store.catalog.query_one(
        "SELECT * FROM quality_issues WHERE issue_id=?", (conflict.conflict_id,)
    )
    import json

    sidecar_gap = json.loads(str(issue["evidence_json"]))["gap_ns"]
    assert conflict.gap_ns == (sidecar_gap[0], sidecar_gap[1])


def test_quarantine_workflow_from_public_fields_only(store, tmp_path: Path) -> None:
    """The complete documented workflow uses ONLY receipt fields."""
    spec, dataset_id, start, receipt = _minute_conflict(store, tmp_path)
    conflict = receipt.conflicts[0]
    assert conflict.gap_ns is not None

    # Unresolved conflict blocks freeze by default.
    with pytest.raises(UnresolvedConflictError):
        freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))

    resolve_conflict(
        store, dataset_id, conflict.partition, conflict.conflict_id,
        ConflictResolution.QUARANTINE, reason="disputed overlay correction",
    )

    # Without allowance the intersecting query fails loudly.
    ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
    with open_snapshot(store, ref.snapshot_id) as reader:
        with pytest.raises(CoverageGapError):
            list(reader.bars(
                dataset_id,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 1, 4, tzinfo=timezone.utc),
                required_fields=(), allow_missing_auxiliary=True,
            ))

    # A 1ns allowance must NOT cover the real 60s quarantine interval.
    narrow = freeze(store, SnapshotRequest(
        selections=(Selection(dataset_id, "*"),),
        allow_known_gaps=(KnownGap(dataset_id, start, start + 1, "too narrow"),),
    ))
    with open_snapshot(store, narrow.snapshot_id) as reader:
        with pytest.raises(CoverageGapError):
            list(reader.bars(dataset_id, required_fields=(), allow_missing_auxiliary=True))

    # The exact public bounds do cover it; the gap stays visible and unfilled.
    allowed = freeze(store, SnapshotRequest(
        selections=(Selection(dataset_id, "*"),),
        allow_known_gaps=(
            KnownGap(dataset_id, conflict.gap_ns[0], conflict.gap_ns[1],
                     "quarantined disputed overlay correction"),
        ),
    ))
    with open_snapshot(store, allowed.snapshot_id) as reader:
        rows = [r for b in reader.bars(
            dataset_id, required_fields=(), allow_missing_auxiliary=True
        ) for r in b.to_pylist()]
    assert rows == []  # sole row was the disputed bar: gap retained, not filled


def test_conflicted_replay_receipt_populates_gap_ns(store, tmp_path: Path) -> None:
    """Idempotent replay of a conflicted batch keeps the public bounds."""
    spec = make_spec(interval=Interval.M1)
    dataset_id = compute_dataset_id(spec)
    start = ns(2024, 1, 2, 9, 32)
    import_rows(
        store, tmp_path,
        [bar_row(dataset_id, "510300", start, close=4.08, trading=date(2024, 1, 2))],
        spec, asset_name="base.csv", asset_content=b"base",
    )

    def stream(_partition: str):
        from conftest import bars_batch

        row = bar_row(dataset_id, "510300", start, close=4.09, trading=date(2024, 1, 2))
        yield bars_batch([row])

    request = ImportRequest(
        asset=make_asset(tmp_path, "overlay.csv", b"overlay"),
        spec=spec, adapter="synthetic/0.1", config={"member": "overlay.csv"},
        partitions=("2024",), idempotency_key="overlay-key-1",
    )
    receipt = import_asset(store, request, stream)
    assert receipt.conflicts[0].gap_ns == (start, start + NS_MINUTE)

    replay = import_asset(store, request, stream)  # same idempotency key
    assert replay.detail.startswith("idempotent replay")
    assert replay.conflicts[0].gap_ns == (start, start + NS_MINUTE)
    assert replay.conflicts[0].conflict_id == receipt.conflicts[0].conflict_id


def test_recovered_conflict_receipt_populates_gap_ns(
    store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The crash-recovery path rebuilds the receipt with public bounds."""
    spec = make_spec(interval=Interval.M1)
    dataset_id = compute_dataset_id(spec)
    start = ns(2024, 1, 2, 9, 32)
    import_rows(
        store, tmp_path,
        [bar_row(dataset_id, "510300", start, close=4.08, trading=date(2024, 1, 2))],
        spec, asset_name="base.csv", asset_content=b"base",
    )

    def stream(_partition: str):
        from conftest import bars_batch

        row = bar_row(dataset_id, "510300", start, close=4.09, trading=date(2024, 1, 2))
        yield bars_batch([row])

    request = ImportRequest(
        asset=make_asset(tmp_path, "overlay.csv", b"overlay"),
        spec=spec, adapter="synthetic/0.1", config={"member": "overlay.csv"},
        partitions=("2024",), idempotency_key="overlay-key-2",
    )

    def boom(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt("simulated power loss")

    real_set = store.catalog.set_batch_state

    def refuse_fail(batch_id, state, updated_at, error=None, receipt_json=None):
        if state == BatchState.FAILED.value:
            raise KeyboardInterrupt("simulated power loss")
        return real_set(batch_id, state, updated_at, error=error,
                        receipt_json=receipt_json)

    monkeypatch.setattr(revisions, "_commit_partition_cas", boom)
    monkeypatch.setattr(store.catalog, "set_batch_state", refuse_fail)
    with pytest.raises(KeyboardInterrupt):
        import_asset(store, request, stream)
    monkeypatch.undo()

    report = recover(store)
    conflicted = [b for b in report.batches if b.receipt is not None
                  and b.receipt.state is BatchState.CONFLICTED]
    assert len(conflicted) == 1
    assert conflicted[0].receipt.conflicts[0].gap_ns == (start, start + NS_MINUTE)


def test_daily_conflict_gap_ns_uses_real_bar_bounds(store, tmp_path: Path) -> None:
    """Daily conflicts keep meaningful bounds: the prior bar's real interval."""
    spec = make_spec()  # daily
    dataset_id = compute_dataset_id(spec)
    day = date(2024, 1, 2)
    start = ns(2024, 1, 2, 0, 0)
    import_rows(
        store, tmp_path,
        [bar_row(dataset_id, "000001", start, close=10.0, trading=day)],
        spec, asset_name="a.csv", asset_content=b"a",
    )
    receipt = import_rows(
        store, tmp_path,
        [bar_row(dataset_id, "000001", ns(2024, 1, 2, 15, 0), close=99.0,
                 trading=day)],
        spec, asset_name="b.csv", asset_content=b"b",
    )
    conflict = receipt.conflicts[0]
    assert conflict.key == f"000001@{day}"
    assert conflict.gap_ns == (start, start + NS_MINUTE)

    resolve_conflict(store, dataset_id, "2024", conflict.conflict_id,
                     ConflictResolution.QUARANTINE, "disputed daily close")
    ref = freeze(store, SnapshotRequest(
        selections=(Selection(dataset_id, "*"),),
        allow_known_gaps=(
            KnownGap(dataset_id, conflict.gap_ns[0], conflict.gap_ns[1],
                     "quarantined disputed daily close"),
        ),
    ))
    with open_snapshot(store, ref.snapshot_id) as reader:
        assert [
            r for b in reader.bars(dataset_id, required_fields=(),
                                   allow_missing_auxiliary=True)
            for r in b.to_pylist()
        ] == []
