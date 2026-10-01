"""Correction02G regressions for the three accepted JOURNAL_AUDIT_02E findings.

F1: recovery must durably mark UNCLEAN_END while still holding the exclusive
    OS lock, before releasing it — no interloper can admit under the retiring
    identity in a recovery gap.
F2: admission's sequence assignment and enqueue are atomic with respect to
    the close latch — an accepted receipt can never name an event stranded
    after the writer exits; close/retry budgets stay bounded.
F3: same-(session,seq) replay equality includes event_ts_ns and
    source_event_id — changed time/source identity is JournalConflictError,
    never silent coalescing; identical replay stays idempotent.

Deterministic synchronization (threading.Events / lock handoff) is used
instead of sleep-only timing wherever the race window must be forced.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from research_store.journal import (
    JournalConflictError,
    JournalSession,
    create_session,
    open_session,
)
from research_store.journal_models import JournalEvent, SessionState
from research_store.session_recovery import recover_session
from research_store.store import init_store


def make_event(
    ts: int | None = 1_700_000_000_000_000_000,
    payload: dict | None = None,
    instrument: str = "IF2403.CFFEX",
    source_event_id: str | None = None,
) -> JournalEvent:
    return JournalEvent(
        kind="tick",
        instrument=instrument,
        event_ts_ns=ts,
        source_event_id=source_event_id,
        payload=payload if payload is not None else {"last_price": 10.5},
    )


@pytest.fixture()
def store(tmp_path: Path):
    s = init_store(tmp_path / "store")
    yield s
    s.close()


def drain(session: JournalSession, n: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if session.status().committed_seq >= n:
            return
        time.sleep(0.01)
    raise AssertionError(f"committed_seq did not reach {n}: {session.status()}")


# ---------------------------------------------------------------------------
# F3: same-seq equality includes event_ts_ns and source_event_id
# ---------------------------------------------------------------------------


def test_same_seq_changed_event_ts_ns_is_conflict(store) -> None:
    session = create_session(store, "src-a", "cal-a")
    r1 = session.admit(make_event(ts=1_700_000_000_000_000_000, payload={"p": 1}))
    drain(session, 1)
    with pytest.raises(JournalConflictError):
        session._flush(
            [
                (
                    make_event(ts=1_800_000_000_000_000_000, payload={"p": 1}),
                    type("R", (), {"assigned_seq": r1.assigned_seq})(),
                )
            ]
        )
    events = list(session.replay_committed())
    assert len(events) == 1
    assert events[0].event_ts_ns == 1_700_000_000_000_000_000
    session.close()


def test_same_seq_changed_source_event_id_is_conflict(store) -> None:
    session = create_session(store, "src-a", "cal-a")
    r1 = session.admit(
        make_event(source_event_id="ctp:AAA", payload={"p": 1})
    )
    drain(session, 1)
    with pytest.raises(JournalConflictError):
        session._flush(
            [
                (
                    make_event(source_event_id="ctp:BBB", payload={"p": 1}),
                    type("R", (), {"assigned_seq": r1.assigned_seq})(),
                )
            ]
        )
    events = list(session.replay_committed())
    assert len(events) == 1
    assert events[0].source_event_id == "ctp:AAA"
    session.close()


def test_same_seq_identical_replay_still_idempotent(store) -> None:
    session = create_session(store, "src-a", "cal-a")
    r1 = session.admit(
        make_event(ts=1_700_000_000_000_000_000, source_event_id="ctp:AAA", payload={"p": 1})
    )
    drain(session, 1)
    # Identical replay (same time, source id, payload) dedups, no conflict.
    session._flush(
        [
            (
                make_event(ts=1_700_000_000_000_000_000, source_event_id="ctp:AAA", payload={"p": 1}),
                type("R", (), {"assigned_seq": r1.assigned_seq})(),
            )
        ]
    )
    assert len(list(session.replay_committed())) == 1
    session.close()


# ---------------------------------------------------------------------------
# F2: admission seq-assign/enqueue atomic vs close latch
# ---------------------------------------------------------------------------


def test_concurrent_admit_close_no_stranded_event(store, monkeypatch) -> None:
    """Force the original race: a delayed put holds the admission lock while
    close_at_cutoff runs. The close must wait for the enqueue, then commit the
    accepted event — never strand it with a dead writer."""
    session = create_session(store, "src-a", "cal-a")
    put_started = threading.Event()
    release_put = threading.Event()
    orig_put = session._queue.put

    def gated_put(item, timeout=None):
        put_started.set()
        release_put.wait(timeout=5.0)
        return orig_put(item, timeout=timeout)

    monkeypatch.setattr(session._queue, "put", gated_put)

    receipt_holder = {}

    def admitter():
        receipt_holder["r"] = session.admit(make_event(payload={"i": 1}))

    t = threading.Thread(target=admitter)
    t.start()
    assert put_started.wait(timeout=5.0)  # admitter holds _seq_lock in put

    # Release the gated put shortly after the close begins waiting on the
    # admission lock, so the close budget covers the lock wait + writer drain.
    def release_later():
        time.sleep(0.2)
        release_put.set()

    threading.Thread(target=release_later, daemon=True).start()
    result = session.close_at_cutoff(timeout=5.0)
    # The close must have waited for the in-flight enqueue, then committed it.
    assert result.state is SessionState.CLOSED, result
    assert result.accepted_seq == 1
    assert result.committed_seq == 1
    t.join(timeout=5.0)
    assert receipt_holder["r"].accepted is True
    assert receipt_holder["r"].assigned_seq == 1
    status = session.status()
    assert status.backlog == 0
    assert status.committed_seq == 1
    session.close()


def test_close_budget_includes_lock_acquisition(store, monkeypatch) -> None:
    """If the admission lock is held longer than the close budget, the close
    fails bounded (no false CLOSED, no indefinite wait) and retry_close can
    still finalize after the lock is released."""
    session = create_session(store, "src-a", "cal-a")
    session.admit(make_event(payload={"i": 0}))
    drain(session, 1)
    gate = threading.Event()
    orig_put = session._queue.put

    def slow_put(item, timeout=None):
        gate.wait(timeout=10.0)  # hold the admission lock until released
        return orig_put(item, timeout=timeout)

    monkeypatch.setattr(session._queue, "put", slow_put)

    def admitter():
        session.admit(make_event(payload={"i": 1}))

    t = threading.Thread(target=admitter)
    t.start()
    time.sleep(0.1)  # ensure admitter is inside slow_put holding _seq_lock
    result = session.close_at_cutoff(timeout=0.2)
    assert result.state is not SessionState.CLOSED
    assert not result.committed_through_cutoff
    assert "could not latch cutoff" in result.detail
    # Admit during the blocked close is still gated by _closing once latched;
    # here the latch never happened, so the writer is still running.
    gate.set()
    t.join(timeout=5.0)
    retry = session.retry_close(timeout=5.0)
    assert retry.state is SessionState.CLOSED, retry
    assert retry.committed_seq == 2
    session.close()


def test_queue_full_no_phantom_accepted_sequence(store, monkeypatch) -> None:
    import research_store.journal as journal_mod

    session = create_session(store, "src-a", "cal-a")
    session._stop.set()
    session._writer.join(timeout=5.0)
    monkeypatch.setattr(journal_mod, "DEFAULT_QUEUE_MAX", 4)
    session._queue = journal_mod.queue.Queue(maxsize=4)
    for i in range(4):
        assert session.admit(make_event(payload={"i": i})).accepted
    # The 5th admission is rejected and must not burn a sequence number.
    r = session.admit(make_event(payload={"i": 4}))
    assert not r.accepted
    assert session.status().accepted_seq == 4
    assert session.status().rejected >= 1
    session.close()


# ---------------------------------------------------------------------------
# F1: recovery marks UNCLEAN_END durably while still holding the lock
# ---------------------------------------------------------------------------


def test_recovery_marks_unclean_end_before_lock_release(store, monkeypatch) -> None:
    """Force the original race: delay the in-session UNCLEAN_END transition
    while an interloper attempts to open the same session. The interloper must
    be refused (lock held or state terminal) and must never commit an
    unreported event."""
    session = create_session(store, "src-a", "cal-a", session_id="sess-race")
    session.admit(make_event(payload={"i": 1}))
    drain(session, 1)
    session.close()  # release lock; on-disk state stays OPEN

    orig_mark = JournalSession.mark_unclean_end
    mark_entered = threading.Event()
    release_mark = threading.Event()

    def delayed_mark(self):
        mark_entered.set()
        release_mark.wait(timeout=5.0)
        orig_mark(self)

    monkeypatch.setattr(JournalSession, "mark_unclean_end", delayed_mark)

    report_holder = {}

    def do_recover():
        report_holder["report"] = recover_session(store, "sess-race", create_successor=False)

    t = threading.Thread(target=do_recover)
    t.start()
    assert mark_entered.wait(timeout=5.0)  # recovery holds the lock, delayed in mark

    interloper_error = None
    try:
        interloper = open_session(store, "sess-race")
        interloper.admit(make_event(payload={"i": 2}))
        interloper.close()
    except Exception as exc:  # noqa: BLE001
        interloper_error = f"{type(exc).__name__}: {exc}"
    assert interloper_error is not None, "interloper must be refused during recovery"

    release_mark.set()
    t.join(timeout=5.0)
    report = report_holder["report"]
    assert report.prior_status == SessionState.OPEN.value
    assert report.replayed_committed_seq == (1,)

    import sqlite3

    conn = sqlite3.connect(str(store.path.journals / "sess-race.sqlite"))
    try:
        state = conn.execute(
            "SELECT value FROM session_meta WHERE key='state'"
        ).fetchone()[0]
        rows = [r[0] for r in conn.execute("SELECT seq FROM events ORDER BY seq")]
    finally:
        conn.close()
    assert state == SessionState.UNCLEAN_END.value
    assert rows == [1]  # no unreported interloper event


def test_recovery_successor_and_idempotence_preserved(store) -> None:
    session = create_session(store, "src-a", "cal-a", session_id="sess-old")
    session.admit(make_event(payload={"i": 1}))
    drain(session, 1)
    session.close()

    report = recover_session(store, "sess-old")
    assert report.prior_status == SessionState.OPEN.value
    assert report.replayed_committed_seq == (1,)
    assert "successor" in report.detail
    successor_id = report.detail.rsplit("successor ", 1)[1]
    successor = open_session(store, successor_id)
    assert successor.predecessor_session_id == "sess-old"
    successor.close()

    # Idempotent re-recovery reports the terminal state and same sequences.
    again = recover_session(store, "sess-old", create_successor=False)
    assert again.prior_status == SessionState.UNCLEAN_END.value
    assert again.replayed_committed_seq == (1,)
