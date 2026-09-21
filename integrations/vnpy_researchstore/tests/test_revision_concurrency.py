"""Concurrent same-partition publication: the CAS must have exactly one winner."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from research_store import HeadConflictError, compute_dataset_id

from research_store import revisions

from conftest import bar_row, import_rows, make_spec, ns


def test_simultaneous_partition_publish_cas(store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)

    barrier = threading.Barrier(2)
    real_commit = revisions._commit_partition_cas

    def synchronized_commit(*args, **kwargs):
        # Both publishers finish staging and arrive at the commit with their
        # recorded (now stale for one of them) base heads.
        barrier.wait(timeout=30)
        return real_commit(*args, **kwargs)

    monkeypatch.setattr(revisions, "_commit_partition_cas", synchronized_commit)

    rows_a = [bar_row(dataset_id, "AAA", ns(2024, 1, 2, 9, 30))]
    rows_b = [bar_row(dataset_id, "BBB", ns(2024, 1, 2, 9, 30))]

    results: dict[str, object] = {}

    def publish(tag: str, rows: list[dict], content: bytes) -> None:
        try:
            results[tag] = import_rows(
                store, tmp_path, rows, spec,
                asset_name=f"{tag}.csv", asset_content=content,
            )
        except HeadConflictError as exc:
            results[tag] = exc

    threads = [
        threading.Thread(target=publish, args=("a", rows_a, b"a")),
        threading.Thread(target=publish, args=("b", rows_b, b"b")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
        assert not t.is_alive()

    outcomes = dict(results)
    winners = [t for t, r in outcomes.items() if not isinstance(r, HeadConflictError)]
    losers = [t for t, r in outcomes.items() if isinstance(r, HeadConflictError)]
    assert len(winners) == 1, f"exactly one CAS winner expected, got {results}"
    assert len(losers) == 1

    # The loser rebuilds from the new head and retries: no overwrite, both
    # instruments end up published exactly once.
    monkeypatch.setattr(revisions, "_commit_partition_cas", real_commit)
    loser = losers[0]
    loser_rows = rows_a if loser == "a" else rows_b
    retry = import_rows(store, tmp_path, loser_rows, spec,
                        asset_name=f"{loser}.csv", asset_content=loser.encode())
    assert retry.accepted_rows == 1
    head = store.catalog.get_head(dataset_id, "2024")
    rev = store.catalog.get_revision(head)
    assert rev["rows"] == 2
