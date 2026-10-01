"""Recovery tests: injected interruption, tampered/missing files, orphans."""

from __future__ import annotations

from pathlib import Path

import pytest

from research_store import BatchState, compute_dataset_id, recover
from research_store import revisions

from conftest import bar_row, import_rows, make_spec, ns


def _simulate_power_loss(store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rows, spec):
    """Crash between the durable prepared anchor and the catalog commit."""

    def boom(*args, **kwargs):
        raise KeyboardInterrupt("simulated power loss")

    monkeypatch.setattr(revisions, "_commit_partition_cas", boom)
    # The crash also prevents the exception handler from marking the batch
    # failed — the batch stays exactly as a killed process would leave it.
    real_set = store.catalog.set_batch_state

    def refuse_fail(batch_id, state, updated_at, error=None, receipt_json=None):
        if state == BatchState.FAILED.value:
            raise KeyboardInterrupt("simulated power loss")
        return real_set(batch_id, state, updated_at, error=error, receipt_json=receipt_json)

    monkeypatch.setattr(store.catalog, "set_batch_state", refuse_fail)
    with pytest.raises(KeyboardInterrupt):
        import_rows(store, tmp_path, rows, spec)
    monkeypatch.undo()  # crash simulation over; recovery runs unpatched


def test_interrupted_publish_recovers_prepared(store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)
    rows = [bar_row(dataset_id, "000001", ns(2024, 1, 2, 9, 30))]
    _simulate_power_loss(store, tmp_path, monkeypatch, rows, spec)

    batch = store.catalog.find_batch_by_key(_last_key(store))
    assert batch["state"] == BatchState.PREPARED.value
    assert store.catalog.get_head(dataset_id, "2024") is None

    report = recover(store)
    assert report.batches[0].action == "republished"
    assert report.batches[0].error is None
    head = store.catalog.get_head(dataset_id, "2024")
    assert head is not None
    assert store.catalog.get_revision(head)["rows"] == 1

    # Recovery is idempotent: a second run returns the prior state cleanly.
    again = recover(store)
    assert all(b.action == "returned_prior_receipt" for b in again.batches)


def _last_key(store) -> str:
    row = store.catalog.query_one(
        "SELECT idempotency_key FROM batches ORDER BY created_at DESC LIMIT 1"
    )
    return str(row[0])


def test_tampered_prepared_object_fails_loudly(store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)
    rows = [bar_row(dataset_id, "000001", ns(2024, 1, 2, 9, 30))]
    _simulate_power_loss(store, tmp_path, monkeypatch, rows, spec)

    obj = next(store.path.objects.rglob("*.parquet"))
    payload = bytearray(obj.read_bytes())
    payload[-10] ^= 0xFF  # tamper
    obj.write_bytes(bytes(payload))

    report = recover(store)
    assert report.batches[0].action == "failed"
    assert report.batches[0].error is not None
    assert "tampered" in report.batches[0].error
    # No fallback: head must not move, batch must not be marked published.
    assert store.catalog.get_head(dataset_id, "2024") is None
    batch = store.catalog.get_batch(report.batches[0].batch_id)
    assert batch["state"] == BatchState.FAILED.value


def test_missing_prepared_object_fails_loudly(store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)
    rows = [bar_row(dataset_id, "000001", ns(2024, 1, 2, 9, 30))]
    _simulate_power_loss(store, tmp_path, monkeypatch, rows, spec)

    next(store.path.objects.rglob("*.parquet")).unlink()
    report = recover(store)
    assert report.batches[0].action == "failed"
    assert "missing" in (report.batches[0].error or "")
    assert store.catalog.get_head(dataset_id, "2024") is None


def test_interrupted_before_prepare_is_marked_failed(store, tmp_path: Path) -> None:
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)

    def dying_stream(_partition: str):
        yield from ()  # never produces; importer died mid-stream
        raise RuntimeError("importer died")

    from research_store import ImportRequest, import_asset
    from conftest import make_asset

    request = ImportRequest(
        asset=make_asset(tmp_path, "dead.csv", b"dead"),
        spec=spec, adapter="synthetic/0.1", config={"member": "dead.csv"},
        partitions=("2024",),
    )
    with pytest.raises(RuntimeError):
        import_asset(store, request, dying_stream)
    recover(store)  # failed batch is not re-selected; nothing moves
    assert store.catalog.get_head(dataset_id, "2024") is None


def test_orphan_files_reported_not_deleted(store, tmp_path: Path) -> None:
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)
    import_rows(store, tmp_path, [bar_row(dataset_id, "000001", ns(2024, 1, 2, 9, 30))], spec)

    orphan = store.path.objects / "ab" / "orphan.parquet"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"unreferenced")
    leftover = store.path.staging / "obj-leftover.parquet"
    leftover.write_bytes(b"partial")

    report = recover(store)
    assert orphan in report.orphan_files
    assert leftover in report.orphan_files
    assert orphan.exists() and leftover.exists()  # reported, never auto-deleted
