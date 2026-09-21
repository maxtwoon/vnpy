# research_store journal interfaces — foundation stage (Kimi WP08 journal, task 02E)

Status: IMPLEMENTED and tested for the foundation scope described below.
Aggregation, sealing, retention and public CLI/UI wiring are MANDATORY
follow-up stages (WP08 recorder bridge / WP09) and are explicitly NOT claimed
here. The existing public stubs `research_store.revisions.recover_session` and
`research_store.revisions.seal` remain PENDING stubs owned by the later
integration phase; this module provides the working foundation they will call.

Package: `research_store` (pure core — never imports `vnpy`, provider SDKs, or
touches `~/.vntrader`). Python >= 3.10. Standard library only.

## 1. Typed models (`research_store.journal_models`)

```python
class SessionState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNCLEAN_END = "UNCLEAN_END"
    ERROR = "ERROR"

@dataclass(frozen=True)
class JournalEvent:
    """One recorded event. ``payload`` is an immutable deep copy of what was
    admitted; the journal hashes the canonical JSON of the full payload."""
    kind: str                     # event kind, e.g. "tick" | "trade" | "bar"
    instrument: str               # real instrument identity
    event_ts_ns: int | None       # original event time, full ns precision
    source_event_id: str | None   # gateway/source event id, unmapped
    payload: Mapping[str, Any]    # full original payload, deep-copied on admission

@dataclass(frozen=True)
class AdmissionReceipt:
    accepted: bool
    assigned_seq: int | None      # session-assigned ingest sequence (1-based)
    reason: str | None

@dataclass(frozen=True)
class JournalStatus:
    session_id: str
    state: SessionState
    accepted_seq: int             # last assigned ingest sequence
    committed_seq: int            # durable committed watermark
    backlog: int                  # accepted-but-not-yet-committed
    rejected: int
    errors: int

@dataclass(frozen=True)
class CloseResult:
    session_id: str
    state: SessionState           # CLOSED on success, never a false CLOSED
    accepted_seq: int
    committed_seq: int
    committed_through_cutoff: bool
    detail: str
```

## 2. Journal session (`research_store.journal`)

```python
def create_session(
    store: Store,
    source_spec: str,
    calendar_spec: str,
    *,
    session_id: str | None = None,
    predecessor_session_id: str | None = None,
) -> JournalSession

def open_session(store: Store, session_id: str) -> JournalSession

class JournalSession:
    session_id: str
    source_spec: str
    calendar_spec: str
    predecessor_session_id: str | None

    def admit(self, event: JournalEvent, *, timeout: float = 0.0) -> AdmissionReceipt
    def status(self) -> JournalStatus
    def close_at_cutoff(self, *, timeout: float = 10.0) -> CloseResult
    def retry_close(self, *, timeout: float = 10.0) -> CloseResult
    def replay_committed(self) -> Iterator[CommittedEvent]   # event-time, then seq
    def mark_unclean_end(self) -> None                        # durable, pre-lock-release
    def close(self) -> None                                   # release OS lock

@dataclass(frozen=True)
class CommittedEvent:
    seq: int
    kind: str
    instrument: str
    event_ts_ns: int | None
    received_ts_ns: int
    source_event_id: str | None
    payload: Mapping[str, Any]
    payload_sha256: str
```

Guarantees (all covered by tests in `tests/test_journal*.py`):

- One journal SQLite file per session under `<store>/journals/<session_id>.sqlite`,
  `journal_mode=WAL`, `synchronous=FULL`, `busy_timeout=5000`.
- Exclusive cross-process OS lock on `<session_id>.lock` held for the session
  lifetime. On Windows this is `msvcrt.locking` on the lock file — the OS
  releases it automatically when the owning process dies; there is no PID
  inspection and therefore no stale-PID stealing. A second process attempting
  `create_session`/`open_session` for the same session id is refused.
- Events are keyed `(session_id, seq)` with `seq` assigned by the session at
  admission (1-based, gapless). The full payload (including `instrument`) is
  canonical-JSON hashed (`payload_sha256`) and stored verbatim.
  - Identical `(session_id, seq)` replay — same payload hash, instrument,
    kind, `event_ts_ns`, and `source_event_id` — dedups idempotently.
  - Same `(session_id, seq)` with any different identity field — payload hash,
    instrument, kind, event time, or source identity — is refused with
    `JournalConflictError`; the stored row is never replaced.
- Sequence assignment and enqueue are atomic with respect to the close
  transition: `admit` holds the admission lock across both, and
  `close_at_cutoff`/`retry_close` acquire the same lock (bounded by the close
  budget) before latching the cutoff and stopping the writer. An accepted
  receipt therefore never names an event stranded after writer shutdown, and
  a queue-full rejection never burns a sequence number.
- Event insertion and the committed-watermark update happen in ONE SQLite
  transaction; a crash between insert and watermark leaves no half-committed
  state visible to replay.
- Admission goes through a bounded in-process queue (default max 100_000).
  A single writer thread batches to SQLite every 250 ms or 1000 events,
  whichever comes first. `status()` exposes accepted / committed / backlog /
  rejected / errors. A full queue or a writer error stops admission
  (`AdmissionReceipt(accepted=False, ...)`) instead of blocking the calling
  event thread indefinitely or silently dropping.
- `close_at_cutoff(timeout=10.0)` fixes the exact accepted cutoff, drains and
  commits everything admitted up to that cutoff, and marks the session CLOSED
  only when `committed_seq == accepted cutoff`. The close budget covers both
  the admission-lock acquisition and the writer drain; a close that cannot
  finish within the bound returns without ever writing a false CLOSED state;
  `retry_close()` re-attempts the same cutoff (latching it if the first
  attempt never got the lock). The writer error path marks the session ERROR
  (never CLOSED).
- No callback can mutate the saved payload: `JournalEvent` is frozen and the
  journal deep-copies the payload at admission and at replay hand-out.
- Deterministic replay: committed events only, ordered by
  `(event_ts_ns, seq)`; `event_ts_ns=None` sorts first, `seq` breaks ties
  stably within and across sessions. Canonical snapshot ordering
  (instrument/session/seq) remains the separate reviewed reader contract.

## 3. Session recovery (`research_store.session_recovery`)

```python
def recover_session(
    store: Store,
    session_id: str,
    *,
    create_successor: bool = True,
    successor_source_spec: str | None = None,
    successor_calendar_spec: str | None = None,
) -> SessionRecoveryReport
```

- Reads COMMITTED events only; uncommitted journal rows are never treated as
  accepted durable events.
- An unclosed (`OPEN`) session is marked `UNCLEAN_END` DURABLY while recovery
  still holds the session's exclusive OS lock (via
  `JournalSession.mark_unclean_end()`), before the lock is released — so no
  concurrent opener can admit or commit under the retiring identity in a
  recovery gap. Marking is idempotent for already-terminal sessions.
- With `create_successor=True`, creates a separate new journal session linked
  via `predecessor_session_id`; the successor starts with an empty journal and
  its own OS lock.
- Returns the existing shared-core `SessionRecoveryReport`
  (`models.py`): `session_id`, `prior_status`, `replayed_committed_seq`
  (the committed sequences replayed, in deterministic order),
  `predecessor_session_id`, `detail`.

## 4. Non-goals of this stage

- No aggregation, no sealing, no retention policy, no recorder bridge, no CLI
  verbs, no edits to `models.py`/`schemas.py`/`catalog.py`/`revisions.py`/
  `snapshots.py`/`reader.py`/`store.py`/`__init__.py`/`INTERFACES.md` or any
  importer/quality/CLI/export/datasource/native path.
- `research_store.revisions.recover_session` / `seal` public stubs stay
  PENDING; the later integration phase wires them to this foundation.
