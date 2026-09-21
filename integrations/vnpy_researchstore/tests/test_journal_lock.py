"""Cross-process lock and crash-recovery tests for the journal foundation.

Child processes are spawned only for task-owned temporary stores; no
unrelated Python or trading process is touched.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from research_store.journal import (
    JournalClosedError,
    JournalLockError,
    create_session,
    open_session,
)
from research_store.journal_models import JournalEvent, SessionState
from research_store.store import init_store


def make_event(ts: int, payload: dict) -> JournalEvent:
    return JournalEvent(
        kind="tick",
        instrument="IF2403.CFFEX",
        event_ts_ns=ts,
        source_event_id=None,
        payload=payload,
    )


@pytest.fixture()
def store(tmp_path: Path):
    s = init_store(tmp_path / "store")
    yield s
    s.close()


CHILD_OPEN_SCRIPT = textwrap.dedent(
    """
    import sys
    from research_store.journal import open_session
    from research_store.store import init_store, open_store

    root, session_id = sys.argv[1], sys.argv[2]
    store = open_store(root)
    try:
        session = open_session(store, session_id)
    except Exception as exc:  # noqa: BLE001
        print(f"REFUSED {type(exc).__name__}: {exc}")
        sys.exit(0)
    print(f"OPENED {session.session_id}")
    session.close()
    """
)


def test_competing_child_process_lock_refused(store, tmp_path: Path) -> None:
    session = create_session(store, "src-a", "cal-a")
    session.admit(make_event(1_700_000_000_000_000_000, {"i": 1}))
    script = tmp_path / "child_open.py"
    script.write_text(CHILD_OPEN_SCRIPT, encoding="utf-8")
    env = {"PYTHONPATH": str(Path(__file__).resolve().parent.parent)}
    proc = subprocess.run(
        [sys.executable, str(script), str(store.root), session.session_id],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert "REFUSED JournalLockError" in proc.stdout, proc.stdout + proc.stderr
    # Same-process second open is refused too.
    with pytest.raises(JournalLockError):
        open_session(store, session.session_id)
    session.close()
    # After the owner releases the lock, a child can open the still-OPEN
    # session (close() releases the OS lock; close_at_cutoff is the durable
    # close protocol).
    proc2 = subprocess.run(
        [sys.executable, str(script), str(store.root), session.session_id],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert "OPENED" in proc2.stdout, proc2.stdout + proc2.stderr


CHILD_HOLD_SCRIPT = textwrap.dedent(
    """
    import sys
    from research_store.journal import create_session
    from research_store.store import open_store

    root, session_id = sys.argv[1], sys.argv[2]
    store = open_store(root)
    session = create_session(store, "src-child", "cal-child", session_id=session_id)
    print("HOLDING", flush=True)
    try:
        import time
        time.sleep(30)
    finally:
        session.close()
    """
)


def test_lock_released_on_child_death_no_stale_pid_stealing(
    store, tmp_path: Path
) -> None:
    script = tmp_path / "child_hold.py"
    script.write_text(CHILD_HOLD_SCRIPT, encoding="utf-8")
    env = {"PYTHONPATH": str(Path(__file__).resolve().parent.parent)}
    proc = subprocess.Popen(
        [sys.executable, str(script), str(store.root), "sess-held"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "HOLDING"
    # While the child lives, the parent is refused the held lock.
    with pytest.raises(JournalLockError):
        open_session(store, "sess-held")
    # Kill the child (task-owned process only); the OS releases the lock.
    proc.kill()
    proc.wait(timeout=30)
    # No stale-PID stealing: the lock is now acquirable by the parent. The
    # dead child's session survives as an OPEN session that recovery can
    # adopt (create_session still refuses the existing session id).
    adopted = open_session(store, "sess-held")
    assert adopted.session_id == "sess-held"
    assert adopted.status().state is SessionState.OPEN
    adopted.admit(make_event(1_700_000_000_000_000_000, {"i": 1}))
    adopted.close()


CRASH_SCRIPT = textwrap.dedent(
    """
    import sys
    from research_store.journal import create_session
    from research_store.journal_models import JournalEvent
    from research_store.store import open_store

    root = sys.argv[1]
    store = open_store(root)
    session = create_session(store, "src-crash", "cal-crash", session_id="sess-crash")
    base = 1_700_000_000_000_000_000
    for i in range(5000):
        session.admit(
            JournalEvent("tick", "IF2403.CFFEX", base + i, None, {"i": i})
        )
    # Die immediately: the bounded queue guarantees some events are still
    # uncommitted, so committed-only recovery has something to exclude.
    print("DYING", flush=True)
    import os
    os._exit(1)  # hard kill: no atexit, no close
    """
)


def test_child_process_kill_committed_only_recovery(store, tmp_path: Path) -> None:
    script = tmp_path / "child_crash.py"
    script.write_text(CRASH_SCRIPT, encoding="utf-8")
    env = {"PYTHONPATH": str(Path(__file__).resolve().parent.parent)}
    proc = subprocess.Popen(
        [sys.executable, str(script), str(store.root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "DYING"
    proc.wait(timeout=60)
    assert proc.returncode == 1

    from research_store.session_recovery import recover_session

    report = recover_session(store, "sess-crash", create_successor=False)
    assert report.prior_status == SessionState.OPEN.value
    assert report.session_id == "sess-crash"
    # Committed-only: the replayed sequences never exceed the durable
    # committed watermark, and any uncommitted rows are excluded.
    import sqlite3

    conn = sqlite3.connect(str(store.path.journals / "sess-crash.sqlite"))
    try:
        committed = conn.execute("SELECT committed_seq FROM watermark").fetchone()[0]
        total_rows = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        conn.close()
    assert len(report.replayed_committed_seq) == committed
    assert report.replayed_committed_seq == tuple(range(1, committed + 1))
    assert total_rows >= committed  # uncommitted rows may exist, never replayed
    # The old session is marked UNCLEAN_END and refuses admission re-open.
    with pytest.raises(JournalClosedError):
        open_session(store, "sess-crash")
