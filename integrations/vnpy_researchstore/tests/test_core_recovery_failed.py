"""Core fix03 F2: partially published FAILED batches are recover-visible.

Evidence base: .coordination/review-core02/repro_multipartition.py (actual
reviewer reproduction). A multi-partition batch interrupted after the first
partition's CAS commit must not be invisible to the general recover() sweep;
it resumes idempotently when the durable anchor allows, fails loudly with
retry guidance when it does not, and never duplicates rows or clobbers a
newer head.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from research_store import BatchState, ImportRequest, compute_dataset_id, import_asset
from research_store import revisions
from research_store.revisions import recover

from conftest import bar_row, make_asset, make_spec, ns

DAY_2024 = date(2024, 1, 2)
DAY_2025 = date(2025, 1, 2)


def _two_partition_request(tmp_path: Path, spec, dataset_id: str, key: str | None = None):
    def rows_for(partition: str):
        row = (
            bar_row(dataset_id, "000001", ns(2024, 1, 2, 0, 0), trading=DAY_2024)
            if partition == "2024"
            else bar_row(dataset_id, "000001", ns(2025, 1, 2, 0, 0), trading=DAY_2025)
        )
        from conftest import bars_batch

        yield bars_batch([row])

    request = ImportRequest(
        asset=make_asset(tmp_path, "multi.csv", b"multi"),
        spec=spec, adapter="synthetic/0.1", config={"member": "multi.csv"},
        partitions=("2024", "2025"), idempotency_key=key,
    )
    return request, rows_for


def _interrupt_after_first_commit(store, monkeypatch: pytest.MonkeyPatch):
    """Fail the SECOND partition CAS commit (first one already committed)."""
    orig = revisions._commit_partition_cas
    calls = {"n": 0}

    def flaky(receiving_store, rev, now):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("SIMULATED crash after partition 1 committed")
        return orig(receiving_store, rev, now)

    monkeypatch.setattr(revisions, "_commit_partition_cas", flaky)


def test_failed_partial_batch_is_swept_and_resumed(
    store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)
    request, rows_for = _two_partition_request(
        tmp_path, spec, dataset_id, key="multi-key-1"
    )

    _interrupt_after_first_commit(store, monkeypatch)
    with pytest.raises(RuntimeError):
        import_asset(store, request, rows_for)
    monkeypatch.undo()

    batch = store.catalog.find_batch_by_key("multi-key-1")
    assert batch["state"] == BatchState.FAILED.value
    committed_head = store.catalog.get_head(dataset_id, "2024")
    assert committed_head is not None  # partition 1 durably published
    assert store.catalog.get_head(dataset_id, "2025") is None

    # The general sweep now sees the FAILED batch and resumes it.
    report = recover(store)
    entry = next(b for b in report.batches if b.batch_id == batch["batch_id"])
    assert entry.action == "republished"
    assert entry.error is None
    assert entry.receipt is not None and entry.receipt.state is BatchState.PUBLISHED
    assert [(p.partition, p.rows) for p in entry.receipt.partitions] == [
        ("2024", 1), ("2025", 1)
    ]

    # Partition 1 was NOT re-published or duplicated.
    assert store.catalog.get_head(dataset_id, "2024") == committed_head
    head_2025 = store.catalog.get_head(dataset_id, "2025")
    assert head_2025 is not None
    for head in (committed_head, head_2025):
        assert store.catalog.get_revision(head)["rows"] == 1

    # Repeating recovery converges on the prior receipt.
    again = recover(store)
    entry2 = next(b for b in again.batches if b.batch_id == batch["batch_id"])
    assert entry2.action == "returned_prior_receipt"

    # The same idempotency-key retry converges without duplicated rows.
    replay = import_asset(store, request, rows_for)
    assert replay.detail.startswith("idempotent replay")
    assert store.catalog.get_head(dataset_id, "2024") == committed_head
    assert store.catalog.get_head(dataset_id, "2025") == head_2025


def test_failed_without_anchor_reports_retry_guidance(store, tmp_path: Path) -> None:
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)

    def dying_stream(_partition: str):
        yield from ()
        raise RuntimeError("importer died mid-stream")

    request = ImportRequest(
        asset=make_asset(tmp_path, "dead.csv", b"dead"),
        spec=spec, adapter="synthetic/0.1", config={"member": "dead.csv"},
        partitions=("2024",), idempotency_key="dead-key-1",
    )
    with pytest.raises(RuntimeError):
        import_asset(store, request, dying_stream)

    batch = store.catalog.find_batch_by_key("dead-key-1")
    assert batch["state"] == BatchState.FAILED.value
    report = recover(store)
    entry = next(b for b in report.batches if b.batch_id == batch["batch_id"])
    assert entry.action == "failed"
    assert entry.prior_state is BatchState.FAILED
    assert entry.receipt is None
    assert "idempotency_key" in (entry.error or "")
    assert "dead-key-1" in (entry.error or "")
    assert store.catalog.get_head(dataset_id, "2024") is None


def test_failed_resume_never_clobbers_newer_head(
    store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)
    request, rows_for = _two_partition_request(
        tmp_path, spec, dataset_id, key="multi-key-2"
    )

    _interrupt_after_first_commit(store, monkeypatch)
    with pytest.raises(RuntimeError):
        import_asset(store, request, rows_for)
    monkeypatch.undo()
    committed_head = store.catalog.get_head(dataset_id, "2024")
    assert committed_head is not None

    # An independent batch publishes partition 2025 before recovery runs.
    def only_2025(_partition: str):
        from conftest import bars_batch

        yield bars_batch(
            [bar_row(dataset_id, "000001", ns(2025, 1, 2, 0, 0), trading=DAY_2025)]
        )

    newer = ImportRequest(
        asset=make_asset(tmp_path, "newer.csv", b"newer"),
        spec=spec, adapter="synthetic/0.1", config={"member": "newer.csv"},
        partitions=("2025",),
    )
    import_asset(store, newer, only_2025)
    newer_head = store.catalog.get_head(dataset_id, "2025")
    assert newer_head is not None

    batch = store.catalog.find_batch_by_key("multi-key-2")
    report = recover(store)
    entry = next(b for b in report.batches if b.batch_id == batch["batch_id"])
    assert entry.action == "failed"
    assert entry.error is not None
    # Neither partition was clobbered nor duplicated.
    assert store.catalog.get_head(dataset_id, "2024") == committed_head
    assert store.catalog.get_head(dataset_id, "2025") == newer_head
    assert store.catalog.get_batch(batch["batch_id"])["state"] == (
        BatchState.FAILED.value
    )
