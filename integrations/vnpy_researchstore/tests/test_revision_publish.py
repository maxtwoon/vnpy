"""Publish tests: happy path, idempotency, dedup, same-key conflicts."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from research_store import (
    BatchState,
    ImportRequest,
    compute_dataset_id,
    import_asset,
)

from conftest import bar_row, bars_batch, import_rows, make_asset, make_spec, ns


def test_publish_streams_to_immutable_objects(store, tmp_path: Path) -> None:
    spec = make_spec()
    rows = [
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 30), trading=date(2024, 1, 2)),
        bar_row("ds", "000001", ns(2024, 1, 3, 9, 30), trading=date(2024, 1, 3)),
        bar_row("ds", "000002", ns(2024, 1, 2, 9, 30), trading=date(2024, 1, 2)),
    ]
    receipt = import_rows(store, tmp_path, rows, spec)
    assert receipt.state is BatchState.PUBLISHED
    assert receipt.accepted_rows == 3
    assert receipt.duplicate_rows == 0

    dataset_id = compute_dataset_id(spec)
    head = store.catalog.get_head(dataset_id, "2024")
    assert head == receipt.partitions[0].revision_id

    files = list(store.path.objects.rglob("*.parquet"))
    assert len(files) == 1
    table = pq.read_table(str(files[0]))
    assert table.num_rows == 3
    # content-hash filename matches the actual content
    from research_store.objects import hash_file

    assert files[0].stem == hash_file(files[0])


def test_repeat_import_is_idempotent(store, tmp_path: Path) -> None:
    spec = make_spec()
    rows = [bar_row("ds", "000001", ns(2024, 1, 2, 9, 30))]
    first = import_rows(store, tmp_path, rows, spec)
    head_after_first = store.catalog.get_head(first.dataset_id, "2024")

    def stream(_p: str):
        yield bars_batch(rows)

    request = ImportRequest(
        asset=make_asset(tmp_path, "feed.csv", b"fixture"),
        spec=spec, adapter="synthetic/0.1", config={"member": "feed.csv"},
        partitions=("2024",),
    )
    second = import_asset(store, request, stream)
    assert second.batch_id == first.batch_id
    assert "idempotent replay" in second.detail
    assert store.catalog.get_head(first.dataset_id, "2024") == head_after_first
    batches = store.catalog.query_all(
        "SELECT * FROM batches WHERE dataset_id=?", (first.dataset_id,)
    )
    assert len(batches) == 1


def test_same_key_same_values_dedup(store, tmp_path: Path) -> None:
    spec = make_spec()
    start = ns(2024, 1, 2, 9, 30)
    import_rows(store, tmp_path, [bar_row("ds", "000001", start)], spec,
                asset_name="v1.csv", asset_content=b"v1")
    # Second import: same key, identical values, different provenance/audit.
    replayed = bar_row("ds", "000001", start, batch_id="batch-other", asset_id="asset-other")
    new_row = bar_row("ds", "000001", ns(2024, 1, 3, 9, 30), trading=date(2024, 1, 3))
    receipt = import_rows(store, tmp_path, [replayed, new_row], spec,
                          asset_name="v2.csv", asset_content=b"v2")
    assert receipt.state is BatchState.PUBLISHED
    assert receipt.duplicate_rows == 1  # source counts preserved
    assert receipt.accepted_rows == 1  # only the genuinely new row
    assert not receipt.conflicts
    head = store.catalog.get_head(receipt.dataset_id, "2024")
    rev = store.catalog.get_revision(head)
    assert rev["rows"] == 2


def test_same_key_different_values_conflict_no_last_wins(store, tmp_path: Path) -> None:
    spec = make_spec()
    start = ns(2024, 1, 2, 9, 30)
    import_rows(store, tmp_path, [bar_row("ds", "000001", start, close=10.0)], spec,
                asset_name="base.csv", asset_content=b"base")
    conflicting = bar_row("ds", "000001", start, close=99.0)  # disputed value
    fresh = bar_row("ds", "000002", start, close=20.0)
    receipt = import_rows(store, tmp_path, [conflicting, fresh], spec,
                          asset_name="cand.csv", asset_content=b"cand")

    assert receipt.state is BatchState.CONFLICTED
    assert len(receipt.conflicts) == 1
    conflict = receipt.conflicts[0]
    assert conflict.resolution is None
    assert "99.0" in conflict.candidate_evidence
    assert "10.0" in conflict.existing_evidence

    # Unaffected new rows may publish; the conflicted key keeps the EXISTING
    # value — never last-wins. Inspect through the published manifest/files.
    import json

    head = store.catalog.get_head(receipt.dataset_id, "2024")
    rev = store.catalog.get_revision(head)
    manifest = json.loads(Path(rev["manifest_path"]).read_text(encoding="utf-8"))
    data = {
        r["instrument_id"]: r
        for f in manifest["files"]
        for r in pq.read_table(str(store.root / f["path"])).to_pylist()
    }
    assert data["000001"]["close"] == 10.0
    assert data["000002"]["close"] == 20.0

    issues = store.catalog.unresolved_issues(receipt.dataset_id, "2024")
    assert len(issues) == 1
    assert issues[0]["code"] == "same_key_different_values"
