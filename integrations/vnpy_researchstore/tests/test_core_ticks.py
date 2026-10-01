"""Core fix03 F3: canonical tick event identity (session + ingest sequence).

- Two distinct events at the same ts both survive, even with identical
  market fields.
- Identical replay of the same event identity is idempotent.
- Reuse of an identity with a changed payload is an explicit conflict, never
  a silently accepted new event.
- ``ts`` keeps its original precision; ordering is (identity, session_id,
  seq), never derived from ts or unstable query order.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from research_store import (
    BatchState,
    ConflictResolution,
    CoverageGapError,
    ImportRequest,
    Interval,
    KnownGap,
    RecordKind,
    Selection,
    SnapshotRequest,
    StoreError,
    UnresolvedConflictError,
    compute_dataset_id,
    freeze,
    import_asset,
    open_snapshot,
    resolve_conflict,
)

from conftest import make_asset, make_spec, ns, tick_row, ticks_batch

SESSION = "rec-20240102-xshq"
T = ns(2024, 1, 2, 9, 30) + 123_456_789  # sub-second precision must survive
DAY = date(2024, 1, 2)


def make_tick_spec():
    return make_spec(record_kind=RecordKind.TICKS, interval=Interval.M1)


def _import_ticks(store, tmp_path: Path, spec, rows, name, key=None, partition="2024"):
    dataset_id = compute_dataset_id(spec)
    for row in rows:
        row["dataset_id"] = dataset_id

    def stream(_partition: str):
        mid = max(1, len(rows) // 2) if len(rows) > 1 else len(rows)
        yield ticks_batch(rows[:mid])
        if len(rows) > 1:
            yield ticks_batch(rows[mid:])

    request = ImportRequest(
        asset=make_asset(tmp_path, name, name.encode()),
        spec=spec, adapter="synthetic/0.1", config={"member": name},
        partitions=(partition,), idempotency_key=key,
    )
    return import_asset(store, request, stream)


def _read_ticks(store, snap: str, dataset_id: str, **kwargs):
    with open_snapshot(store, snap) as reader:
        return [
            r for b in reader.ticks(dataset_id, **kwargs) for r in b.to_pylist()
        ]


def test_two_same_ts_events_both_survive(store, tmp_path: Path) -> None:
    """Same instrument, same ts, identical market fields: two events, both kept."""
    spec = make_tick_spec()
    dataset_id = compute_dataset_id(spec)
    receipt = _import_ticks(store, tmp_path, spec, [
        tick_row(dataset_id, "000001", T, session=SESSION, seq=1),
        tick_row(dataset_id, "000001", T, session=SESSION, seq=2),
    ], "same_ts.parquet")
    assert receipt.state is BatchState.PUBLISHED
    assert receipt.accepted_rows == 2
    assert receipt.duplicate_rows == 0

    ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
    rows = _read_ticks(store, ref.snapshot_id, dataset_id, required_fields=())
    assert [(r["session_id"], r["seq"]) for r in rows] == [(SESSION, 1), (SESSION, 2)]
    assert all(r["ts"] == T for r in rows)  # precision preserved


def test_same_event_identity_replay_is_idempotent(store, tmp_path: Path) -> None:
    spec = make_tick_spec()
    dataset_id = compute_dataset_id(spec)
    rows = [
        tick_row(dataset_id, "000001", T, session=SESSION, seq=1),
        tick_row(dataset_id, "000001", T, session=SESSION, seq=2),
    ]
    first = _import_ticks(store, tmp_path, spec, rows, "feed_a.parquet",
                          key="tick-key-1")
    assert first.accepted_rows == 2

    # Same content again under the SAME key: prior receipt replayed.
    replay = _import_ticks(store, tmp_path, spec, rows, "feed_a.parquet",
                           key="tick-key-1")
    assert replay.detail.startswith("idempotent replay")
    assert replay.accepted_rows == 2  # prior receipt, nothing re-published

    # Same events from a different asset (new key): dedup, not double-store.
    again = _import_ticks(store, tmp_path, spec, rows, "feed_b.parquet")
    assert again.state is BatchState.PUBLISHED
    assert again.duplicate_rows == 2
    assert again.accepted_rows == 0

    head = store.catalog.get_head(dataset_id, "2024")
    assert store.catalog.get_revision(head)["rows"] == 2


def test_reused_identity_changed_payload_is_conflict(store, tmp_path: Path) -> None:
    spec = make_tick_spec()
    dataset_id = compute_dataset_id(spec)
    _import_ticks(store, tmp_path, spec, [
        tick_row(dataset_id, "000001", T, session=SESSION, seq=7,
                 last_price=10.0),
    ], "base.parquet")

    receipt = _import_ticks(store, tmp_path, spec, [
        tick_row(dataset_id, "000001", T, session=SESSION, seq=7,
                 last_price=11.0),
    ], "corrected.parquet")
    assert receipt.state is BatchState.CONFLICTED
    assert receipt.quarantined_rows == 1
    conflict = receipt.conflicts[0]
    assert conflict.key == f"000001@{SESSION}@7"
    assert conflict.gap_ns == (T, T + 1)  # tick gap: point interval at ts

    # The disputed event was not replaced by the changed payload.
    import json

    head = store.catalog.get_head(dataset_id, "2024")
    rev = store.catalog.get_revision(head)
    manifest = json.loads(Path(str(rev["manifest_path"])).read_text(encoding="utf-8"))
    head_rows = [
        r for f in manifest["files"]
        for r in pq.read_table(str(store.root / f["path"])).to_pylist()
    ]
    assert len(head_rows) == 1 and head_rows[0]["last_price"] == 10.0

    # Resolution EXISTING keeps the original; the gap bounds stay public.
    resolve_conflict(store, dataset_id, "2024", conflict.conflict_id,
                     ConflictResolution.EXISTING, "vendor correction rejected")
    ref = freeze(store, SnapshotRequest(
        selections=(Selection(dataset_id, "*"),),
        allow_known_gaps=(
            KnownGap(dataset_id, conflict.gap_ns[0], conflict.gap_ns[1],
                     "disputed tick correction"),
        ),
    ))
    rows = _read_ticks(store, ref.snapshot_id, dataset_id, required_fields=())
    assert len(rows) == 1 and rows[0]["last_price"] == 10.0


def test_tick_quarantine_keeps_sibling_same_ts_event(store, tmp_path: Path) -> None:
    """Quarantining one event identity never drops its same-ts sibling."""
    spec = make_tick_spec()
    dataset_id = compute_dataset_id(spec)
    _import_ticks(store, tmp_path, spec, [
        tick_row(dataset_id, "000001", T, session=SESSION, seq=1),
        tick_row(dataset_id, "000001", T, session=SESSION, seq=2),
    ], "base.parquet")
    receipt = _import_ticks(store, tmp_path, spec, [
        tick_row(dataset_id, "000001", T, session=SESSION, seq=1,
                 last_price=99.0),
    ], "overlay.parquet")
    conflict = receipt.conflicts[0]
    assert conflict.gap_ns is not None

    with pytest.raises(UnresolvedConflictError):
        freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))

    resolve_conflict(store, dataset_id, "2024", conflict.conflict_id,
                     ConflictResolution.QUARANTINE, "disputed tick value")

    blocked = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
    with open_snapshot(store, blocked.snapshot_id) as reader:
        with pytest.raises(CoverageGapError):
            list(reader.ticks(dataset_id, required_fields=()))

    allowed = freeze(store, SnapshotRequest(
        selections=(Selection(dataset_id, "*"),),
        allow_known_gaps=(
            KnownGap(dataset_id, conflict.gap_ns[0], conflict.gap_ns[1],
                     "quarantined disputed tick"),
        ),
    ))
    rows = _read_ticks(store, allowed.snapshot_id, dataset_id, required_fields=())
    assert [(r["session_id"], r["seq"]) for r in rows] == [(SESSION, 2)]


def test_tick_stream_key_validation(store, tmp_path: Path) -> None:
    spec = make_tick_spec()
    dataset_id = compute_dataset_id(spec)

    # Unsorted by (identity, session, seq): rejected.
    with pytest.raises(StoreError, match="sorted"):
        _import_ticks(store, tmp_path, spec, [
            tick_row(dataset_id, "000001", T, session=SESSION, seq=2),
            tick_row(dataset_id, "000001", T, session=SESSION, seq=1),
        ], "unsorted.parquet")

    # Duplicate event identity within one stream: rejected.
    with pytest.raises(StoreError, match="duplicate keys"):
        _import_ticks(store, tmp_path, spec, [
            tick_row(dataset_id, "000001", T, session=SESSION, seq=1),
            tick_row(dataset_id, "000001", T, session=SESSION, seq=1,
                     last_price=12.0),
        ], "dupkey.parquet")

    # Empty session id would be a silently invented session: rejected.
    with pytest.raises(StoreError, match="session_id"):
        _import_ticks(store, tmp_path, spec, [
            tick_row(dataset_id, "000001", T, session="", seq=1),
        ], "nosession.parquet")

    assert store.catalog.get_head(dataset_id, "2024") is None


def test_tick_ordering_is_session_seq_not_ts(store, tmp_path: Path) -> None:
    """Deterministic (identity, session, seq) order even when ts disagrees."""
    spec = make_tick_spec()
    dataset_id = compute_dataset_id(spec)
    later_ts, earlier_ts = T, T - 5_000_000_000
    receipt = _import_ticks(store, tmp_path, spec, [
        # key-sorted stream: session A before session B, ts intentionally not
        tick_row(dataset_id, "000001", later_ts, session="sess-a", seq=1),
        tick_row(dataset_id, "000001", earlier_ts, session="sess-b", seq=1),
    ], "twosess.parquet")
    assert receipt.state is BatchState.PUBLISHED

    ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
    rows = _read_ticks(store, ref.snapshot_id, dataset_id, required_fields=())
    assert [(r["session_id"], r["seq"], r["ts"]) for r in rows] == [
        ("sess-a", 1, later_ts),
        ("sess-b", 1, earlier_ts),
    ]


def test_tick_instrument_filter_and_range(store, tmp_path: Path) -> None:
    from datetime import datetime, timezone

    spec = make_tick_spec()
    dataset_id = compute_dataset_id(spec)
    t2 = T + 60_000_000_000
    _import_ticks(store, tmp_path, spec, [
        tick_row(dataset_id, "000001", T, session=SESSION, seq=1),
        tick_row(dataset_id, "000001", t2, session=SESSION, seq=2),
        tick_row(dataset_id, "000002", T, session=SESSION, seq=1),
    ], "multi.parquet")

    ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
    rows = _read_ticks(
        store, ref.snapshot_id, dataset_id,
        instruments=["000001"],
        start=datetime(2024, 1, 2, 9, 30, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, 9, 31, tzinfo=timezone.utc),
        required_fields=(),
    )
    assert [(r["instrument_id"], r["session_id"], r["seq"]) for r in rows] == [
        ("000001", SESSION, 1)
    ]
