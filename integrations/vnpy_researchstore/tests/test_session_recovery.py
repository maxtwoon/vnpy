"""Recovery-foundation tests: UNCLEAN_END marking, linked successor session,
committed-only replay, idempotent re-recovery, and payload preservation.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from research_store.journal import create_session, open_session
from research_store.journal_models import JournalEvent, SessionState
from research_store.session_recovery import recover_session
from research_store.store import init_store


def make_event(ts: int | None, payload: dict, instrument: str = "IF2403.CFFEX") -> JournalEvent:
    return JournalEvent(
        kind="tick",
        instrument=instrument,
        event_ts_ns=ts,
        source_event_id=None,
        payload=payload,
    )


@pytest.fixture()
def store(tmp_path: Path):
    s = init_store(tmp_path / "store")
    yield s
    s.close()


def drain(session, n: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if session.status().committed_seq >= n:
            return
        time.sleep(0.01)
    raise AssertionError(f"committed_seq did not reach {n}: {session.status()}")


def test_recovery_marks_unclean_end_and_creates_linked_successor(store) -> None:
    session = create_session(store, "src-a", "cal-a", session_id="sess-old")
    session.admit(make_event(1_700_000_000_000_000_000, {"i": 1}))
    session.admit(make_event(1_700_000_000_000_000_001, {"i": 2}))
    drain(session, 2)
    session.close()  # release lock only; session stays OPEN (no close_at_cutoff)

    report = recover_session(store, "sess-old")
    assert report.prior_status == SessionState.OPEN.value
    assert report.replayed_committed_seq == (1, 2)
    assert report.predecessor_session_id is None
    assert "successor" in report.detail

    conn = sqlite3.connect(str(store.path.journals / "sess-old.sqlite"))
    try:
        state = conn.execute(
            "SELECT value FROM session_meta WHERE key='state'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert state == SessionState.UNCLEAN_END.value

    # The successor is a separate session linked via predecessor_session_id.
    successor_id = report.detail.rsplit("successor ", 1)[1]
    successor = open_session(store, successor_id)
    assert successor.predecessor_session_id == "sess-old"
    assert successor.source_spec == "src-a"
    assert successor.calendar_spec == "cal-a"
    # Successor starts empty and accepts its own events.
    assert successor.status().accepted_seq == 0
    successor.admit(make_event(1_700_000_000_000_000_100, {"i": 3}))
    drain(successor, 1)
    result = successor.close_at_cutoff(timeout=5.0)
    assert result.state is SessionState.CLOSED
    successor.close()


def test_recovery_is_idempotent_for_unclean_end(store) -> None:
    session = create_session(store, "src-a", "cal-a", session_id="sess-idem")
    session.admit(make_event(1_700_000_000_000_000_000, {"i": 1}))
    drain(session, 1)
    session.close()

    first = recover_session(store, "sess-idem", create_successor=False)
    assert first.prior_status == SessionState.OPEN.value
    second = recover_session(store, "sess-idem", create_successor=False)
    assert second.prior_status == SessionState.UNCLEAN_END.value
    assert second.replayed_committed_seq == first.replayed_committed_seq == (1,)


def test_recovery_of_closed_session_needs_no_unclean_mark(store) -> None:
    session = create_session(store, "src-a", "cal-a", session_id="sess-closed")
    session.admit(make_event(1_700_000_000_000_000_000, {"i": 1}))
    drain(session, 1)
    result = session.close_at_cutoff(timeout=5.0)
    assert result.state is SessionState.CLOSED
    session.close()

    report = recover_session(store, "sess-closed")
    assert report.prior_status == SessionState.CLOSED.value
    assert report.replayed_committed_seq == (1,)
    conn = sqlite3.connect(str(store.path.journals / "sess-closed.sqlite"))
    try:
        state = conn.execute(
            "SELECT value FROM session_meta WHERE key='state'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert state == SessionState.CLOSED.value  # not rewritten to UNCLEAN_END


def test_recovery_preserves_full_payload_and_identity(store) -> None:
    session = create_session(store, "src-a", "cal-a", session_id="sess-payload")
    payload = {
        "last_price": 3817.2,
        "volume": 3,
        "extensions": {"bid1": 3817.0, "ask1": 3817.4},
    }
    session.admit(
        JournalEvent(
            kind="tick",
            instrument="IF2403.CFFEX",
            event_ts_ns=1_700_000_000_123_456_789,
            source_event_id="ctp:12345",
            payload=payload,
        )
    )
    drain(session, 1)
    session.close()

    report = recover_session(store, "sess-payload", create_successor=False)
    assert report.replayed_committed_seq == (1,)

    # Reopen read-only via replay path on a fresh exclusive open is refused
    # (UNCLEAN_END), so verify durability directly from the journal file.
    conn = sqlite3.connect(str(store.path.journals / "sess-payload.sqlite"))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM events WHERE seq=1").fetchone()
    finally:
        conn.close()
    assert row["kind"] == "tick"
    assert row["instrument"] == "IF2403.CFFEX"
    assert row["event_ts_ns"] == 1_700_000_000_123_456_789  # full precision kept
    assert row["source_event_id"] == "ctp:12345"
    import json as _json

    assert _json.loads(row["payload_json"]) == payload  # full original payload


def test_recovery_never_treats_uncommitted_rows_as_accepted(store, monkeypatch) -> None:
    session = create_session(store, "src-a", "cal-a", session_id="sess-partial")
    # Stop the writer before any flush: events stay admitted-but-uncommitted.
    session._stop.set()
    session._writer.join(timeout=5.0)
    session.admit(make_event(1_700_000_000_000_000_000, {"i": 1}))
    session.admit(make_event(1_700_000_000_000_000_001, {"i": 2}))
    session.close()

    report = recover_session(store, "sess-partial", create_successor=False)
    assert report.replayed_committed_seq == ()
    conn = sqlite3.connect(str(store.path.journals / "sess-partial.sqlite"))
    try:
        total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        committed = conn.execute("SELECT committed_seq FROM watermark").fetchone()[0]
    finally:
        conn.close()
    assert total == 0  # nothing durable was written for the uncommitted events
    assert committed == 0


def test_top_level_recover_session_forwards_typed_options(store) -> None:
    """recording02I regression (03D smoke finding): the CANONICAL top-level
    ``research_store.recover_session`` must forward ``create_successor`` and
    the successor spec overrides to the real implementation — no silent
    keyword rejection, no private access, no prose-ID parsing.
    """

    from research_store import recover_session as top_level_recover_session

    session = create_session(store, "src-top", "cal-top", session_id="sess-top")
    session.admit(make_event(1_700_000_000_000_000_000, {"i": 1}))
    drain(session, 1)
    session.close()  # lock release only; on-disk state stays OPEN

    # create_successor=False must be honored (no successor session created).
    report = top_level_recover_session(
        store, "sess-top", create_successor=False
    )
    assert report.prior_status == SessionState.OPEN.value
    assert report.successor_session_id is None

    # Typed successor spec overrides must reach the created successor.
    report2 = top_level_recover_session(
        store,
        "sess-top",
        create_successor=True,
        successor_source_spec="successor-src",
        successor_calendar_spec="successor-cal",
    )
    successor_id = report2.successor_session_id
    assert successor_id is not None
    assert report2.last_error is None
    successor = open_session(store, successor_id)
    try:
        assert successor.predecessor_session_id == "sess-top"
        assert successor.source_spec == "successor-src"
        assert successor.calendar_spec == "successor-cal"
    finally:
        successor.close()

    # The keyword is also accepted on an already-closed session (report-only
    # path: no successor is created for CLOSED sessions).
    closed = create_session(store, "src-top", "cal-top", session_id="sess-top-closed")
    closed.admit(make_event(1_700_000_000_000_000_100, {"i": 2}))
    drain(closed, 1)
    result = closed.close_at_cutoff(timeout=5.0)
    assert result.state is SessionState.CLOSED
    closed.close()
    report3 = top_level_recover_session(
        store, "sess-top-closed", create_successor=True
    )
    assert report3.prior_status == SessionState.CLOSED.value
    assert report3.successor_session_id is None
