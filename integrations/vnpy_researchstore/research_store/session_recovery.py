"""Recording-session recovery on top of the durable journal foundation.

Reads COMMITTED events only, marks an unclosed session UNCLEAN_END
(idempotently), and optionally creates a separate successor session linked via
``predecessor_session_id``. Uncommitted journal rows are never treated as
accepted durable events.

Pure storage core — never imports ``vnpy`` or any provider SDK, and never
touches ``~/.vntrader``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .journal import create_session, open_session
from .journal_models import SessionState
from .models import SessionRecoveryReport, StoreError
from .store import Store


class SessionRecoveryError(StoreError):
    """Recovery preconditions violated (unknown session, ...)."""


def _read_meta(journal_path: Path) -> tuple[str, str, str, str | None]:
    if not journal_path.is_file():
        raise SessionRecoveryError(f"unknown journal session: {journal_path.stem}")
    conn = sqlite3.connect(str(journal_path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        def meta(key: str) -> str | None:
            row = conn.execute(
                "SELECT value FROM session_meta WHERE key=?", (key,)
            ).fetchone()
            return None if row is None else str(row["value"])

        state = meta("state") or SessionState.OPEN.value
        source_spec = meta("source_spec") or ""
        calendar_spec = meta("calendar_spec") or ""
        pred = meta("predecessor_session_id") or ""
        return state, source_spec, calendar_spec, pred or None
    finally:
        conn.close()


def _mark_unclean_end(journal_path: Path) -> None:
    """Direct on-disk UNCLEAN_END write.

    Retained as a module-level seam for review repros; production recovery
    marks UNCLEAN_END through ``JournalSession.mark_unclean_end()`` while
    still holding the exclusive OS lock (see ``recover_session``).
    """

    conn = sqlite3.connect(str(journal_path), timeout=5.0, isolation_level=None)
    try:
        with conn:
            conn.execute(
                "INSERT INTO session_meta (key, value) VALUES ('state', ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (SessionState.UNCLEAN_END.value,),
            )
            conn.execute(
                "INSERT INTO session_meta (key, value) VALUES ('updated_at', datetime('now'))"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            )
    finally:
        conn.close()


def recover_session(
    store: Store,
    session_id: str,
    *,
    create_successor: bool = True,
    successor_source_spec: str | None = None,
    successor_calendar_spec: str | None = None,
) -> SessionRecoveryReport:
    """Recover an unclosed recording session.

    - Replays COMMITTED events only (by event-time then sequence) to report
      the committed sequences; uncommitted rows are never reported as durable.
    - Marks the unclosed old session UNCLEAN_END; already-closed sessions are
      left untouched and simply reported.
    - With ``create_successor=True`` opens a separate new journal session
      linked via ``predecessor_session_id`` and returns its id.
    """

    journal_path = store.path.journals / f"{session_id}.sqlite"
    prior_status, source_spec, calendar_spec, predecessor = _read_meta(journal_path)

    replayed: tuple[int, ...] = ()
    if prior_status == SessionState.OPEN.value:
        # Replay committed events only through the journal's own reader, then
        # durably mark UNCLEAN_END WHILE STILL HOLDING the exclusive OS lock,
        # and only then release it via close(). No concurrent opener can
        # admit/commit under the retiring identity in a recovery gap.
        session = open_session(store, session_id)
        try:
            replayed = tuple(ev.seq for ev in session.replay_committed())
            session.mark_unclean_end()
        finally:
            session.close()
        detail = "unclosed session marked UNCLEAN_END; committed events replayed"
    elif prior_status == SessionState.CLOSED.value:
        # Closed sessions need no recovery; report committed sequences only.
        conn = sqlite3.connect(str(journal_path), timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT committed_seq FROM watermark"
            ).fetchone()
            committed = int(row["committed_seq"]) if row is not None else 0
            replayed = tuple(
                r["seq"]
                for r in conn.execute(
                    "SELECT seq FROM events WHERE seq <= ? ORDER BY seq",
                    (committed,),
                ).fetchall()
            )
        finally:
            conn.close()
        detail = "session already CLOSED; committed sequences reported"
    else:  # UNCLEAN_END or ERROR — idempotent re-report
        conn = sqlite3.connect(str(journal_path), timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT committed_seq FROM watermark").fetchone()
            committed = int(row["committed_seq"]) if row is not None else 0
            replayed = tuple(
                r["seq"]
                for r in conn.execute(
                    "SELECT seq FROM events WHERE seq <= ? ORDER BY seq",
                    (committed,),
                ).fetchall()
            )
        finally:
            conn.close()
        detail = f"session already {prior_status}; committed sequences re-reported"

    successor_id: str | None = None
    last_error: str | None = None
    if create_successor and prior_status != SessionState.CLOSED.value:
        try:
            successor = create_session(
                store,
                successor_source_spec or source_spec,
                successor_calendar_spec or calendar_spec,
                predecessor_session_id=session_id,
            )
            successor_id = successor.session_id
            successor.close()
        except StoreError as exc:
            last_error = f"successor creation failed: {type(exc).__name__}: {exc}"

    return SessionRecoveryReport(
        session_id=session_id,
        prior_status=prior_status,
        replayed_committed_seq=replayed,
        predecessor_session_id=predecessor,
        detail=detail if successor_id is None else f"{detail}; successor {successor_id}",
        successor_session_id=successor_id,
        last_error=last_error,
    )
