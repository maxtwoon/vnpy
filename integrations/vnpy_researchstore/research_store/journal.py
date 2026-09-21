"""Durable per-session recording journal (WP08 foundation).

One journal SQLite file per recording session plus an exclusive cross-process
OS lock. Admission goes through a bounded in-process queue drained by a single
writer thread; event insertion and the committed watermark advance in ONE
SQLite transaction. Payloads are stored verbatim under an immutable
``(session_id, seq)`` key with a canonical-JSON sha256; a same-key different
payload (including a different instrument under the same session/seq) is
refused, never replaced.

Pure storage core — never imports ``vnpy`` or any provider SDK, and never
touches ``~/.vntrader``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import queue
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .journal_models import (
    AdmissionReceipt,
    CloseResult,
    CommittedEvent,
    JournalEvent,
    JournalStatus,
    SessionState,
)
from .models import StoreError
from .store import Store

DEFAULT_QUEUE_MAX = 100_000
FLUSH_INTERVAL_S = 0.250
FLUSH_BATCH = 1000
DEFAULT_CLOSE_TIMEOUT_S = 10.0

_JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    instrument TEXT NOT NULL,
    event_ts_ns INTEGER,
    received_ts_ns INTEGER NOT NULL,
    source_event_id TEXT,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watermark (
    committed_seq INTEGER NOT NULL
);
INSERT OR IGNORE INTO watermark (committed_seq) VALUES (0);
"""


class JournalError(StoreError):
    """Base class for journal errors."""


class JournalLockError(JournalError):
    """Session is exclusively owned by another live process."""


class JournalConflictError(JournalError):
    """Same (session_id, seq) with a different payload hash — never replaced."""


class JournalClosedError(JournalError):
    """Admission or close attempted on a session that is not OPEN."""


class JournalQueueFullError(JournalError):
    """Bounded admission queue is full; admission has stopped."""


class JournalWriterError(JournalError):
    """Writer thread failed; the session is marked ERROR, never CLOSED."""


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class _SessionLock:
    """Exclusive cross-process OS lock on a journal lock file.

    On Windows this uses ``msvcrt.locking`` on the lock file: the OS releases
    the lock automatically when the owning process dies, so there is no PID
    inspection and no stale-PID stealing. On POSIX it uses ``fcntl.flock``
    with the same death-release semantics.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file: Any = None

    def acquire(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        f = open(self._path, "a+b")
        try:
            if os.name == "nt":  # pragma: no cover - platform branch
                import msvcrt

                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            else:  # pragma: no cover - platform branch
                import fcntl  # type: ignore[import-not-found]

                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
        except OSError as exc:
            f.close()
            raise JournalLockError(
                f"session lock is held by another process: {self._path}"
            ) from exc
        self._file = f

    def release(self) -> None:
        if self._file is None:
            return
        f = self._file
        self._file = None
        try:
            if os.name == "nt":  # pragma: no cover - platform branch
                import msvcrt

                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - platform branch
                import fcntl  # type: ignore[import-not-found]

                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        except OSError:
            pass
        f.close()


def _connect_journal(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(
        str(path), timeout=5.0, isolation_level=None, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(_JOURNAL_SCHEMA)
    return conn


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM session_meta WHERE key=?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO session_meta (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def create_session(
    store: Store,
    source_spec: str,
    calendar_spec: str,
    *,
    session_id: str | None = None,
    predecessor_session_id: str | None = None,
) -> JournalSession:
    """Create a new journal session and open it exclusively.

    Refuses if the session id already exists or its lock is held elsewhere.
    """

    sid = session_id or f"sess-{uuid.uuid4().hex[:16]}"
    journal_path = store.path.journals / f"{sid}.sqlite"
    lock_path = store.path.journals / f"{sid}.lock"
    if journal_path.exists():
        raise JournalError(f"journal session already exists: {sid}")
    lock = _SessionLock(lock_path)
    lock.acquire()
    try:
        conn = _connect_journal(journal_path)
        with conn:
            _meta_set(conn, "session_id", sid)
            _meta_set(conn, "source_spec", source_spec)
            _meta_set(conn, "calendar_spec", calendar_spec)
            _meta_set(
                conn, "predecessor_session_id", predecessor_session_id or ""
            )
            _meta_set(conn, "state", SessionState.OPEN.value)
            _meta_set(conn, "created_at", _utc_now())
            _meta_set(conn, "updated_at", _utc_now())
    except BaseException:
        lock.release()
        raise
    return JournalSession._open(store, sid, lock, conn)


def open_session(
    store: Store, session_id: str, *, readonly: bool = False
) -> JournalSession:
    """Open an existing journal session exclusively.

    Refuses if another live process holds the session lock. With
    ``readonly=True`` any session state is accepted, no writer thread is
    started, and admission/close are refused — for sealing/recovery/audit
    readers that still require exclusive ownership.
    """

    journal_path = store.path.journals / f"{session_id}.sqlite"
    lock_path = store.path.journals / f"{session_id}.lock"
    if not journal_path.is_file():
        raise JournalError(f"unknown journal session: {session_id}")
    lock = _SessionLock(lock_path)
    lock.acquire()
    try:
        conn = _connect_journal(journal_path)
        state = _meta_get(conn, "state")
        if not readonly and state != SessionState.OPEN.value:
            conn.close()
            lock.release()
            raise JournalClosedError(
                f"session {session_id} is {state}; only OPEN sessions accept events"
            )
    except BaseException:
        if lock._file is not None:
            lock.release()
        raise
    return JournalSession._open(store, session_id, lock, conn, readonly=readonly)


class JournalSession:
    """An open, exclusively owned recording journal session."""

    def __init__(self) -> None:
        self._store: Store
        self._conn: sqlite3.Connection
        self._lock: _SessionLock
        self.session_id: str
        self.source_spec: str
        self.calendar_spec: str
        self.predecessor_session_id: str | None
        self._queue: queue.Queue[tuple[JournalEvent, AdmissionReceipt] | None]
        self._writer: threading.Thread
        self._stop = threading.Event()
        self._closed = False
        self._close_lock = threading.Lock()
        self._seq_lock = threading.Lock()
        self._next_seq = 0
        self._state = SessionState.OPEN
        self._rejected = 0
        self._errors = 0
        self._last_error: str | None = None
        self._writer_error: BaseException | None = None
        self._cutoff_seq: int | None = None
        self._closing = threading.Event()
        self._readonly = False

    # -- construction --------------------------------------------------------

    @classmethod
    def _open(
        cls,
        store: Store,
        session_id: str,
        lock: _SessionLock,
        conn: sqlite3.Connection,
        *,
        readonly: bool = False,
    ) -> JournalSession:
        self = cls()
        self._store = store
        self._conn = conn
        self._lock = lock
        self.session_id = session_id
        self.source_spec = _meta_get(conn, "source_spec") or ""
        self.calendar_spec = _meta_get(conn, "calendar_spec") or ""
        pred = _meta_get(conn, "predecessor_session_id") or ""
        self.predecessor_session_id = pred or None
        row = conn.execute("SELECT COALESCE(MAX(seq), 0) AS m FROM events").fetchone()
        self._next_seq = int(row["m"])
        self._readonly = readonly
        disk_state = _meta_get(conn, "state")
        if disk_state:
            self._state = SessionState(disk_state)
        self._queue = queue.Queue(maxsize=DEFAULT_QUEUE_MAX)
        self._stop = threading.Event()
        if readonly:
            self._writer = threading.Thread(target=lambda: None, daemon=True)
        else:
            self._writer = threading.Thread(
                target=self._writer_main,
                name=f"journal-writer-{session_id}",
                daemon=True,
            )
            self._writer.start()
        return self

    # -- introspection -------------------------------------------------------

    @property
    def journal_path(self) -> Path:
        return self._store.path.journals / f"{self.session_id}.sqlite"

    def read_meta(self, key: str) -> str | None:
        """Public read access to one durable ``session_meta`` value.

        Returns ``None`` when the key is absent. Readers (aggregation,
        sealing, audit) use this instead of touching the private connection.
        """

        return _meta_get(self._conn, key)

    def record_completion_boundary_ns(self, boundary_ns: int) -> None:
        """Durably record explicit interval/session completion evidence.

        ``boundary_ns`` asserts: market data through this event-time ns
        boundary has been observed for this session (e.g. the exchange
        session close). Aggregation treats a boundary >= a tail bar's
        ``bar_end_ns`` as proof that the bar's minute interval completed;
        without it (or a later event crossing the bar end) the tail bar
        stays PARTIAL even when the session is CLOSED.

        Refuses on a readonly open or a torn-down session; the value must
        be a positive int. This is evidence, never a guess: callers pass a
        boundary they can vouch for (calendar/session close), not wall
        clock.
        """

        if self._readonly:
            raise JournalClosedError("session opened readonly; cannot record completion boundary")
        if self._closed:
            raise JournalError("session is torn down; cannot record completion boundary")
        if isinstance(boundary_ns, bool) or not isinstance(boundary_ns, int) or boundary_ns <= 0:
            raise JournalError(
                f"completion boundary must be a positive int (ns); got {boundary_ns!r}"
            )
        with self._conn:
            _meta_set(self._conn, "completion_boundary_ns", str(boundary_ns))
            _meta_set(self._conn, "updated_at", _utc_now())

    def _committed_seq(self) -> int:
        row = self._conn.execute("SELECT committed_seq FROM watermark").fetchone()
        return int(row["committed_seq"])

    def status(self) -> JournalStatus:
        accepted = self._accepted_seq()
        committed = self._committed_seq()
        return JournalStatus(
            session_id=self.session_id,
            state=self._state,
            accepted_seq=accepted,
            committed_seq=committed,
            backlog=accepted - committed,
            rejected=self._rejected,
            errors=self._errors,
            last_error=self._last_error,
        )

    def _accepted_seq(self) -> int:
        with self._seq_lock:
            return self._next_seq

    # -- admission -----------------------------------------------------------

    def admit(self, event: JournalEvent, *, timeout: float = 0.0) -> AdmissionReceipt:
        """Offer one event for admission.

        Returns an ``AdmissionReceipt``; on a full queue or a stopped writer
        returns ``accepted=False`` instead of blocking the calling event
        thread indefinitely.
        """

        if self._readonly:
            self._rejected += 1
            self._last_error = "session opened readonly"
            return AdmissionReceipt(False, None, self._last_error)
        if self._state is not SessionState.OPEN or self._closing.is_set():
            self._rejected += 1
            self._last_error = f"session is {self._state.value}"
            return AdmissionReceipt(False, None, self._last_error)
        if self._writer_error is not None:
            self._rejected += 1
            self._last_error = f"writer stopped: {self._writer_error}"
            return AdmissionReceipt(False, None, self._last_error)
        # Deep copy so later callback mutation cannot change the saved payload.
        frozen = JournalEvent(
            kind=event.kind,
            instrument=event.instrument,
            event_ts_ns=event.event_ts_ns,
            source_event_id=event.source_event_id,
            payload=copy.deepcopy(dict(event.payload)),
        )
        # Assign the ingest sequence and enqueue atomically with respect to
        # the close transition: close_at_cutoff() takes the same lock before
        # latching _closing/_stop, so no sequence can be assigned without a
        # guaranteed matching enqueue ahead of writer shutdown. queue.put with
        # the caller's timeout is bounded, so admission stays nonblocking.
        with self._seq_lock:
            if self._closing.is_set():
                self._rejected += 1
                self._last_error = "session is closing"
                return AdmissionReceipt(False, None, self._last_error)
            self._next_seq += 1
            assigned = self._next_seq
            receipt = AdmissionReceipt(True, assigned, None)
            try:
                self._queue.put((frozen, receipt), timeout=timeout)
            except queue.Full:
                self._next_seq -= 1  # no phantom accepted sequence
                self._rejected += 1
                self._last_error = "admission queue full"
                return AdmissionReceipt(False, None, self._last_error)
        return receipt

    # -- writer thread ---------------------------------------------------------

    def _writer_main(self) -> None:
        batch: list[tuple[JournalEvent, AdmissionReceipt]] = []
        try:
            while True:
                try:
                    item = self._queue.get(timeout=FLUSH_INTERVAL_S)
                except queue.Empty:
                    item = None
                if item is None:
                    if self._stop.is_set() and self._queue.empty():
                        break
                    if batch:
                        self._flush(batch)
                        batch = []
                    if self._stop.is_set() and self._queue.empty():
                        break
                    continue
                batch.append(item)
                if len(batch) >= FLUSH_BATCH:
                    self._flush(batch)
                    batch = []
            if batch:
                self._flush(batch)
        except BaseException as exc:  # noqa: BLE001 - surfaced via status/errors
            self._writer_error = exc
            self._errors += 1
            self._last_error = f"writer error: {type(exc).__name__}: {exc}"
            try:
                self._set_state(SessionState.ERROR)
            except sqlite3.ProgrammingError:
                pass  # session torn down concurrently; error already recorded

    def _flush(self, batch: list[tuple[JournalEvent, AdmissionReceipt]]) -> None:
        """Insert events and advance the committed watermark in ONE transaction."""

        with self._conn:
            for event, receipt in batch:
                payload_json = _canonical_json(event.payload)
                digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
                row = self._conn.execute(
                    "SELECT payload_sha256, instrument, kind, event_ts_ns,"
                    " source_event_id FROM events WHERE seq=?",
                    (receipt.assigned_seq,),
                ).fetchone()
                if row is not None:
                    if (
                        row["payload_sha256"] != digest
                        or row["instrument"] != event.instrument
                        or row["kind"] != event.kind
                        or (
                            None if row["event_ts_ns"] is None
                            else int(row["event_ts_ns"])
                        )
                        != event.event_ts_ns
                        or row["source_event_id"] != event.source_event_id
                    ):
                        raise JournalConflictError(
                            f"session {self.session_id} seq {receipt.assigned_seq} "
                            "already holds a different payload"
                        )
                    continue  # idempotent replay of an identical event
                self._conn.execute(
                    """
                    INSERT INTO events (seq, kind, instrument, event_ts_ns,
                        received_ts_ns, source_event_id, payload_json, payload_sha256)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receipt.assigned_seq,
                        event.kind,
                        event.instrument,
                        event.event_ts_ns,
                        time.time_ns(),
                        event.source_event_id,
                        payload_json,
                        digest,
                    ),
                )
            last = batch[-1][1].assigned_seq
            self._conn.execute(
                "UPDATE watermark SET committed_seq=? WHERE committed_seq<?",
                (last, last),
            )

    def _set_state(self, state: SessionState) -> None:
        with self._conn:
            _meta_set(self._conn, "state", state.value)
            _meta_set(self._conn, "updated_at", _utc_now())
        self._state = state

    def mark_unclean_end(self) -> None:
        """Durably transition this session to UNCLEAN_END while still
        exclusively owning it (before any close()/lock release), so no
        concurrent opener can admit under the retiring identity."""

        self._set_state(SessionState.UNCLEAN_END)

    # -- close -----------------------------------------------------------------

    def close_at_cutoff(self, *, timeout: float = DEFAULT_CLOSE_TIMEOUT_S) -> CloseResult:
        """Fix the exact accepted cutoff and commit everything up to it.

        CLOSED is written only when the committed watermark equals the
        accepted cutoff; a bounded failure never writes a false CLOSED.
        """

        with self._close_lock:
            if self._readonly:
                return CloseResult(
                    session_id=self.session_id,
                    state=self._state,
                    accepted_seq=self._accepted_seq(),
                    committed_seq=self._committed_seq(),
                    committed_through_cutoff=False,
                    detail="session opened readonly",
                )
            if self._state is not SessionState.OPEN:
                return CloseResult(
                    session_id=self.session_id,
                    state=self._state,
                    accepted_seq=self._accepted_seq(),
                    committed_seq=self._committed_seq(),
                    committed_through_cutoff=False,
                    detail=f"session is {self._state.value}",
                )
            # Fix the exact accepted cutoff: take the admission lock (bounded
            # by the close budget) so no sequence assignment/enqueue can
            # straddle the closing latch, then stop admissions, drain the
            # queue into the writer, and wait for it to finish within the
            # remaining budget.
            deadline = time.monotonic() + timeout
            if not self._seq_lock.acquire(timeout=timeout):
                return CloseResult(
                    session_id=self.session_id,
                    state=self._state,
                    accepted_seq=self._accepted_seq(),
                    committed_seq=self._committed_seq(),
                    committed_through_cutoff=False,
                    detail=f"could not latch cutoff within {timeout}s; retry_close()",
                )
            try:
                self._closing.set()
                self._cutoff_seq = self._next_seq
            finally:
                self._seq_lock.release()
            remaining = max(0.0, deadline - time.monotonic())
            self._stop.set()
            self._writer.join(timeout=remaining)
            if self._writer.is_alive():
                return CloseResult(
                    session_id=self.session_id,
                    state=self._state,
                    accepted_seq=self._accepted_seq(),
                    committed_seq=self._committed_seq(),
                    committed_through_cutoff=False,
                    detail=f"writer did not finish within {timeout}s; retry_close()",
                )
            if self._writer_error is not None:
                return CloseResult(
                    session_id=self.session_id,
                    state=self._state,
                    accepted_seq=self._accepted_seq(),
                    committed_seq=self._committed_seq(),
                    committed_through_cutoff=False,
                    detail=f"writer error: {self._writer_error}",
                )
            accepted = self._accepted_seq()
            committed = self._committed_seq()
            if committed == accepted:
                self._set_state(SessionState.CLOSED)
                return CloseResult(
                    session_id=self.session_id,
                    state=SessionState.CLOSED,
                    accepted_seq=accepted,
                    committed_seq=committed,
                    committed_through_cutoff=True,
                    detail="committed through exact accepted cutoff",
                )
            return CloseResult(
                session_id=self.session_id,
                state=self._state,
                accepted_seq=accepted,
                committed_seq=committed,
                committed_through_cutoff=False,
                detail="committed watermark did not reach accepted cutoff",
            )

    def retry_close(self, *, timeout: float = DEFAULT_CLOSE_TIMEOUT_S) -> CloseResult:
        """Re-attempt a close that previously failed within its bound.

        Latches the cutoff (if not already latched) under the admission lock,
        stops the writer, and finalizes only when committed == accepted.
        """

        with self._close_lock:
            if self._state is not SessionState.OPEN:
                return CloseResult(
                    session_id=self.session_id,
                    state=self._state,
                    accepted_seq=self._accepted_seq(),
                    committed_seq=self._committed_seq(),
                    committed_through_cutoff=False,
                    detail=f"session is {self._state.value}",
                )
            deadline = time.monotonic() + timeout
            if not self._closing.is_set():
                if not self._seq_lock.acquire(timeout=timeout):
                    return CloseResult(
                        session_id=self.session_id,
                        state=self._state,
                        accepted_seq=self._accepted_seq(),
                        committed_seq=self._committed_seq(),
                        committed_through_cutoff=False,
                        detail=f"could not latch cutoff within {timeout}s",
                    )
                try:
                    self._closing.set()
                    self._cutoff_seq = self._next_seq
                finally:
                    self._seq_lock.release()
            remaining = max(0.0, deadline - time.monotonic())
            self._stop.set()
            self._writer.join(timeout=remaining)
        if self._writer_error is not None or self._state is SessionState.ERROR:
            return CloseResult(
                session_id=self.session_id,
                state=self._state,
                accepted_seq=self._accepted_seq(),
                committed_seq=self._committed_seq(),
                committed_through_cutoff=False,
                detail=f"session is {self._state.value}",
            )
        accepted = self._accepted_seq()
        committed = self._committed_seq()
        if committed == accepted:
            self._set_state(SessionState.CLOSED)
            return CloseResult(
                session_id=self.session_id,
                state=SessionState.CLOSED,
                accepted_seq=accepted,
                committed_seq=committed,
                committed_through_cutoff=True,
                detail="committed through exact accepted cutoff",
            )
        return CloseResult(
            session_id=self.session_id,
            state=self._state,
            accepted_seq=accepted,
            committed_seq=committed,
            committed_through_cutoff=False,
            detail="committed watermark did not reach accepted cutoff",
        )

    # -- replay ----------------------------------------------------------------

    def replay_committed(self) -> Iterator[CommittedEvent]:
        """Replay committed events only, ordered by (event_ts_ns, seq).

        ``event_ts_ns=None`` sorts first; ``seq`` breaks ties stably. Payloads
        are deep-copied on hand-out so replay consumers cannot mutate the
        durable record.
        """

        committed = self._committed_seq()
        rows = self._conn.execute(
            """
            SELECT seq, kind, instrument, event_ts_ns, received_ts_ns,
                   source_event_id, payload_json, payload_sha256
            FROM events WHERE seq <= ?
            ORDER BY (event_ts_ns IS NOT NULL), event_ts_ns, seq
            """,
            (committed,),
        ).fetchall()
        for row in rows:
            yield CommittedEvent(
                seq=int(row["seq"]),
                kind=str(row["kind"]),
                instrument=str(row["instrument"]),
                event_ts_ns=(
                    None if row["event_ts_ns"] is None else int(row["event_ts_ns"])
                ),
                received_ts_ns=int(row["received_ts_ns"]),
                source_event_id=row["source_event_id"],
                payload=json.loads(row["payload_json"]),
                payload_sha256=str(row["payload_sha256"]),
            )

    # -- teardown ----------------------------------------------------------------

    def close(self) -> None:
        """Release the OS lock and close the journal connection.

        Does not change session state; use ``close_at_cutoff`` for the
        durable close protocol.
        """

        if self._closed:
            return
        self._closed = True
        if self._writer.is_alive():
            self._stop.set()
            self._writer.join(timeout=2.0)
        self._conn.close()
        self._lock.release()

    def __enter__(self) -> JournalSession:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
