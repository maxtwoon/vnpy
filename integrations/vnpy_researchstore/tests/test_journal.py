"""Foundation tests for the durable recording journal.

Covers: admission + assigned sequence, immutable payload with collision
refusal (including a different instrument under the same session/seq),
same-time distinct events, event+watermark single transaction, bounded queue
overflow, writer error stopping admission, exact cutoff close with bounded
timeout and retry, committed-only deterministic replay (event-time then seq),
replay twice, and input mutation not affecting the saved payload.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from research_store.journal import (
    JournalClosedError,
    JournalConflictError,
    JournalSession,
    create_session,
    open_session,
)
from research_store.journal_models import JournalEvent, SessionState
from research_store.store import init_store


def make_event(
    kind: str = "tick",
    instrument: str = "IF2403.CFFEX",
    ts: int | None = 1_700_000_000_000_000_000,
    payload: dict | None = None,
    source_event_id: str | None = None,
) -> JournalEvent:
    return JournalEvent(
        kind=kind,
        instrument=instrument,
        event_ts_ns=ts,
        source_event_id=source_event_id,
        payload=payload if payload is not None else {"last_price": 10.5, "volume": 1},
    )


@pytest.fixture()
def store(tmp_path: Path):
    s = init_store(tmp_path / "store")
    yield s
    s.close()


def drain(session: JournalSession, n: int = 50, timeout: float = 5.0) -> None:
    """Wait until the writer commits at least n events."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if session.status().committed_seq >= n:
            return
        time.sleep(0.01)
    raise AssertionError(
        f"committed_seq did not reach {n}: {session.status()}"
    )


def test_admit_assigns_gapless_sequences_and_commits(store) -> None:
    session = create_session(store, "src-a", "cal-a")
    receipts = [session.admit(make_event(payload={"i": i})) for i in range(5)]
    assert all(r.accepted for r in receipts)
    assert [r.assigned_seq for r in receipts] == [1, 2, 3, 4, 5]
    drain(session, 5)
    status = session.status()
    assert status.committed_seq == 5
    assert status.backlog == 0
    assert status.state is SessionState.OPEN
    result = session.close_at_cutoff(timeout=5.0)
    assert result.state is SessionState.CLOSED
    assert result.committed_through_cutoff
    session.close()


def test_same_seq_different_payload_refused_never_replaced(store, monkeypatch) -> None:
    session = create_session(store, "src-a", "cal-a")
    original = make_event(instrument="IF2403.CFFEX", payload={"last_price": 10.5})
    r1 = session.admit(original)
    drain(session, 1)

    # Direct same-key/different-payload insert must raise and not replace.
    with pytest.raises(JournalConflictError):
        session._flush(
            [
                (
                    make_event(instrument="IF2403.CFFEX", payload={"last_price": 99.0}),
                    type("R", (), {"assigned_seq": r1.assigned_seq})(),
                )
            ]
        )
    # A different instrument under the same session/seq is also a conflict.
    with pytest.raises(JournalConflictError):
        session._flush(
            [
                (
                    make_event(instrument="IC2403.CFFEX", payload={"last_price": 10.5}),
                    type("R", (), {"assigned_seq": r1.assigned_seq})(),
                )
            ]
        )
    events = list(session.replay_committed())
    assert len(events) == 1
    assert events[0].payload == {"last_price": 10.5}
    assert events[0].instrument == "IF2403.CFFEX"
    session.close()


def test_identical_replay_dedups_idempotently(store) -> None:
    session = create_session(store, "src-a", "cal-a")
    r1 = session.admit(make_event(payload={"last_price": 10.5}))
    drain(session, 1)
    # Re-flush the identical (seq, payload) — must dedup, not duplicate.
    session._flush(
        [
            (
                make_event(payload={"last_price": 10.5}),
                type("R", (), {"assigned_seq": r1.assigned_seq})(),
            )
        ]
    )
    assert len(list(session.replay_committed())) == 1
    session.close()


def test_same_timestamp_distinct_events_both_survive(store) -> None:
    session = create_session(store, "src-a", "cal-a")
    ts = 1_700_000_000_000_000_000
    session.admit(make_event(instrument="IF2403.CFFEX", ts=ts, payload={"p": 1}))
    session.admit(make_event(instrument="IF2403.CFFEX", ts=ts, payload={"p": 2}))
    drain(session, 2)
    events = list(session.replay_committed())
    assert len(events) == 2
    assert events[0].event_ts_ns == ts and events[1].event_ts_ns == ts
    assert events[0].seq < events[1].seq  # stable tie handling
    assert [e.payload for e in events] == [{"p": 1}, {"p": 2}]
    session.close()


def test_replay_orders_by_event_time_then_seq(store) -> None:
    session = create_session(store, "src-a", "cal-a")
    base = 1_700_000_000_000_000_000
    session.admit(make_event(ts=base + 200, payload={"p": "late-admitted"}))
    session.admit(make_event(ts=base + 100, payload={"p": "early"}))
    session.admit(make_event(ts=None, payload={"p": "no-ts-first"}))
    drain(session, 3)
    order = [(e.event_ts_ns, e.seq) for e in session.replay_committed()]
    assert order[0][0] is None
    assert order[1][0] == base + 100
    assert order[2][0] == base + 200
    session.close()


def test_input_mutation_does_not_change_saved_payload(store) -> None:
    session = create_session(store, "src-a", "cal-a")
    payload = {"last_price": 10.5, "nested": {"bid": 1}}
    session.admit(make_event(payload=payload))
    payload["last_price"] = 999.0  # mutate after admission
    payload["nested"]["bid"] = 999
    drain(session, 1)
    events = list(session.replay_committed())
    assert events[0].payload == {"last_price": 10.5, "nested": {"bid": 1}}
    # Mutating the replayed payload must not affect a second replay.
    events[0].payload["nested"]["bid"] = 12345  # type: ignore[index]
    again = list(session.replay_committed())
    assert again[0].payload == {"last_price": 10.5, "nested": {"bid": 1}}
    session.close()


def test_queue_overflow_stops_admission_without_blocking(store, monkeypatch) -> None:
    import research_store.journal as journal_mod

    session = create_session(store, "src-a", "cal-a")
    # Stop the writer so the bounded queue actually fills.
    session._stop.set()
    session._writer.join(timeout=5.0)
    monkeypatch.setattr(journal_mod, "DEFAULT_QUEUE_MAX", 8)
    session._queue = journal_mod.queue.Queue(maxsize=8)
    accepted = 0
    rejected = 0
    for i in range(32):
        r = session.admit(make_event(payload={"i": i}))
        if r.accepted:
            accepted += 1
        else:
            rejected += 1
    assert accepted == 8
    assert rejected == 24
    status = session.status()
    assert status.rejected >= 24
    session.close()


def test_writer_error_stops_admission_and_marks_error(store, monkeypatch) -> None:
    session = create_session(store, "src-a", "cal-a")

    def failing_flush(batch):
        raise RuntimeError("disk full")

    session._flush = failing_flush  # type: ignore[method-assign]
    session.admit(make_event(payload={"i": 1}))
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if session.status().state is SessionState.ERROR:
            break
        time.sleep(0.01)
    assert session.status().state is SessionState.ERROR
    assert session.status().errors >= 1
    # Admission stops with a visible rejection, no indefinite blocking.
    r = session.admit(make_event(payload={"i": 2}))
    assert not r.accepted
    # Close must never claim CLOSED after a writer error.
    result = session.close_at_cutoff(timeout=5.0)
    assert result.state is SessionState.ERROR
    assert not result.committed_through_cutoff
    session.close()


def test_close_at_cutoff_exact_cutoff_and_retry(store) -> None:
    session = create_session(store, "src-a", "cal-a")
    for i in range(10):
        session.admit(make_event(payload={"i": i}))
    result = session.close_at_cutoff(timeout=5.0)
    assert result.state is SessionState.CLOSED
    assert result.accepted_seq == 10
    assert result.committed_seq == 10
    assert result.committed_through_cutoff
    # No false CLOSED: a second close reports the durable CLOSED state.
    again = session.close_at_cutoff(timeout=5.0)
    assert again.state is SessionState.CLOSED
    session.close()
    # A CLOSED session refuses re-open for admission.
    with pytest.raises(JournalClosedError):
        open_session(store, session.session_id)


def test_close_timeout_returns_without_false_closed(store, monkeypatch) -> None:
    session = create_session(store, "src-a", "cal-a")
    session.admit(make_event(payload={"i": 1}))
    # Simulate a writer that never finishes.
    monkeypatch.setattr(session._writer, "join", lambda timeout=None: None)
    monkeypatch.setattr(session._writer, "is_alive", lambda: True)
    result = session.close_at_cutoff(timeout=0.01)
    assert result.state is not SessionState.CLOSED
    assert not result.committed_through_cutoff
    session.close()


def test_replay_twice_same_content_and_count(store) -> None:
    session = create_session(store, "src-a", "cal-a")
    for i in range(20):
        session.admit(make_event(ts=1_700_000_000_000_000_000 + i, payload={"i": i}))
    drain(session, 20)
    first = [(e.seq, e.event_ts_ns, dict(e.payload)) for e in session.replay_committed()]
    second = [(e.seq, e.event_ts_ns, dict(e.payload)) for e in session.replay_committed()]
    assert first == second
    assert len(first) == 20
    session.close()


def test_concurrent_admission_single_writer_commits_all(store) -> None:
    session = create_session(store, "src-a", "cal-a")
    per_thread = 200
    threads = [
        threading.Thread(
            target=lambda base: [
                session.admit(make_event(payload={"i": base + j})) for j in range(per_thread)
            ],
            args=(i * per_thread,),
        )
        for i in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    drain(session, 4 * per_thread)
    result = session.close_at_cutoff(timeout=10.0)
    assert result.state is SessionState.CLOSED
    assert result.committed_seq == 4 * per_thread
    seqs = [e.seq for e in session.replay_committed()]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 4 * per_thread
    session.close()
