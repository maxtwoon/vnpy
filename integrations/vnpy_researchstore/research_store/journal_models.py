"""Typed models for the durable recording journal (WP08 foundation).

Pure storage core — never imports ``vnpy`` or any provider SDK, and never
touches ``~/.vntrader``. These models are Kimi-owned journal-scope types; the
shared-core ``SessionRecoveryReport`` in ``models.py`` is reused as-is for
recovery reports.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class SessionState(str, Enum):
    """Lifecycle state of a recording journal session."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNCLEAN_END = "UNCLEAN_END"
    ERROR = "ERROR"


@dataclass(frozen=True)
class JournalEvent:
    """One event offered for admission.

    ``payload`` is the full original payload. The journal deep-copies it at
    admission and at replay hand-out, so no callback can mutate the saved
    payload through the reference it passed in.
    """

    kind: str                       # event kind, e.g. "tick" | "trade" | "bar"
    instrument: str                 # real instrument identity
    event_ts_ns: int | None         # original event time, full ns precision
    source_event_id: str | None     # gateway/source event id, unmapped
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class AdmissionReceipt:
    """Result of one ``JournalSession.admit`` call."""

    accepted: bool
    assigned_seq: int | None        # session-assigned ingest sequence, 1-based
    reason: str | None


@dataclass(frozen=True)
class JournalStatus:
    """Visible writer state: accepted/committed/backlog/rejected/errors."""

    session_id: str
    state: SessionState
    accepted_seq: int               # last assigned ingest sequence
    committed_seq: int              # durable committed watermark
    backlog: int                    # accepted but not yet committed
    rejected: int
    errors: int
    last_error: str | None = None   # detail of the most recent writer/admission error


@dataclass(frozen=True)
class CloseResult:
    """Result of ``close_at_cutoff`` / ``retry_close``.

    ``state`` is CLOSED only when the committed watermark reached the exact
    accepted cutoff; a bounded failure never reports a false CLOSED.
    """

    session_id: str
    state: SessionState
    accepted_seq: int
    committed_seq: int
    committed_through_cutoff: bool
    detail: str


@dataclass(frozen=True)
class CommittedEvent:
    """One committed journal event as replayed.

    Ordered by ``(event_ts_ns, seq)``; ``event_ts_ns=None`` sorts first and
    ``seq`` breaks ties stably. ``payload`` is a deep copy handed out to the
    caller — mutating it does not affect the journal.
    """

    seq: int
    kind: str
    instrument: str
    event_ts_ns: int | None
    received_ts_ns: int
    source_event_id: str | None
    payload: Mapping[str, Any]
    payload_sha256: str
