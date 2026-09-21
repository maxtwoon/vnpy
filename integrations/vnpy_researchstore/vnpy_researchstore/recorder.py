"""Research recorder bridge: vnpy event callbacks -> durable journal sessions.

This module is the ONLY place where vnpy event objects are translated into
``research_store.journal.JournalEvent`` admissions. It deliberately:

* admits ONLY explicitly configured real instruments on an explicitly
  configured exchange — ``Exchange.LOCAL`` synthetic contracts are refused;
* preserves the source identity (simulated vs production are separate,
  never merged), the event kind, and an immutable deep-copied payload;
* labels CTP ``TickData`` observations as quote/snapshot observations, never
  as exchange trade-by-trade data;
* never connects a gateway, account, or strategy by itself — the bridge only
  consumes events that some explicitly configured upstream pushes into the
  shared ``EventEngine``;
* writes only through the public journal API
  (``create_session`` / ``JournalSession.admit`` / ``status`` /
  ``close_at_cutoff`` / ``retry_close``); it never reads private journal
  attributes and never parses prose to recover typed state.

Pure bridge — the heavy lifecycle (stop barrier, parent-close withholding)
lives in ``recording_engine.py``; this module owns admission policy only.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from research_store.journal import JournalSession, create_session
from research_store.journal_models import (
    AdmissionReceipt,
    JournalEvent,
    JournalStatus,
    SessionState,
)
from research_store.store import Store

# Event kinds the bridge understands. "tick" is a quote/snapshot observation
# unless the provider contract establishes another kind; the bridge records
# the kind it was configured for and never upgrades a quote to trade-by-trade.
SUPPORTED_KINDS = ("tick", "trade", "bar")

# Source identities stay strictly separate: a simulated (SimNow/test) feed
# and a production feed must never share a session or an instrument filter.
SOURCE_SIMULATED = "simulated"
SOURCE_PRODUCTION = "production"

#: Marker the UI/status uses when a typed journal field is requested but the
#: public interface does not expose it yet (see
#: .coordination/recorder03-core-requests.md). Never a fabricated value.
#: WP09 filled both recorder requests (``JournalStatus.last_error`` and
#: ``SessionRecoveryReport.successor_session_id``); the marker now only
#: appears when no journal session is attached at all (there is no status
#: object to read a typed error from).
UNAVAILABLE = "UNAVAILABLE (no journal session attached)"


def _validate_calendar(calendar_spec: str) -> None:
    """Grammar-check a recorder calendar_spec against the revised 02I seal
    contract: ``""``, an IANA zone name, or ``tz:<IANA zone>``.

    A timezone is DISPLAY/normalization evidence only — it never qualifies a
    trading calendar (RECORDING_02I_CALENDAR_CLARIFICATION): trading_date
    stays honestly unknown unless explicit source evidence exists. Legacy
    strings like ``CN.FUTURES.DAY`` are refused here instead of failing only
    later at seal time.
    """

    from research_store.sealing import SealError, validate_calendar_spec

    try:
        validate_calendar_spec(calendar_spec)
    except SealError as exc:
        raise RecorderConfigError(
            f"calendar_spec {calendar_spec!r} violates the seal grammar "
            f"(v1): {exc}"
        ) from None


class RecorderState(str, Enum):
    """Bridge lifecycle state."""

    IDLE = "IDLE"
    RECORDING = "RECORDING"
    STOPPED = "STOPPED"
    STOP_FAILED = "STOP_FAILED"


class RecorderConfigError(Exception):
    """Recorder configuration is missing, ambiguous or unsafe."""


@dataclass(frozen=True)
class RecorderInstrument:
    """One explicitly configured real instrument to admit."""

    symbol: str
    exchange: str          # native Exchange value name, e.g. "SHFE", "CFFEX"

    @property
    def vt_symbol(self) -> str:
        return f"{self.symbol}.{self.exchange}"


@dataclass(frozen=True)
class RecorderConfig:
    """Explicit recorder configuration.

    ``source_kind`` is ``"simulated"`` or ``"production"``; the two are never
    mixed inside one recorder. ``gateway_type`` is declarative metadata only
    (e.g. "ctp"); the bridge never instantiates or connects a gateway.
    """

    source_id: str
    source_kind: str
    calendar_spec: str
    instruments: tuple[RecorderInstrument, ...]
    event_kinds: tuple[str, ...] = ("tick",)
    gateway_type: str = ""
    session_id: str | None = None
    predecessor_session_id: str | None = None

    def validate(self) -> None:
        if not self.source_id:
            raise RecorderConfigError("recorder source_id is required")
        if self.source_kind not in (SOURCE_SIMULATED, SOURCE_PRODUCTION):
            raise RecorderConfigError(
                f"source_kind must be {SOURCE_SIMULATED!r} or {SOURCE_PRODUCTION!r}; "
                f"got {self.source_kind!r}"
            )
        if not self.calendar_spec:
            raise RecorderConfigError("recorder calendar_spec is required")
        _validate_calendar(self.calendar_spec)
        if not self.instruments:
            raise RecorderConfigError("at least one instrument must be configured")
        for instrument in self.instruments:
            if not instrument.symbol or not instrument.exchange:
                raise RecorderConfigError(
                    f"instrument {instrument!r} needs explicit symbol and exchange"
                )
            if instrument.exchange.upper() == "LOCAL":
                raise RecorderConfigError(
                    "LOCAL synthetic contracts are refused; configure a real "
                    f"exchange, got {instrument.vt_symbol!r}"
                )
        for kind in self.event_kinds:
            if kind not in SUPPORTED_KINDS:
                raise RecorderConfigError(
                    f"unsupported event kind {kind!r}; supported {SUPPORTED_KINDS}"
                )


@dataclass(frozen=True)
class RecorderAdmission:
    """What the bridge admitted for one event (visible bookkeeping)."""

    accepted: bool
    assigned_seq: int | None
    reason: str | None
    vt_symbol: str
    kind: str


@dataclass(frozen=True)
class RecorderSnapshot:
    """A point-in-time, non-blocking view of recorder + journal state.

    ``last_error_detail`` is the typed ``JournalStatus.last_error`` (WP09):
    the journal's own detail of the most recent writer/admission error, or
    ``None`` when there is none. ``errors`` is the real count from
    ``JournalStatus`` and is never faked to zero. ``rejected`` combines
    journal-level rejections (queue full / session closed) with bridge-level
    refusals (unconfigured instrument or kind, not recording).
    """

    state: RecorderState
    source_id: str
    source_kind: str
    instruments: tuple[str, ...]
    event_kinds: tuple[str, ...]
    gateway_type: str
    session_id: str | None
    journal_path: str | None
    journal_state: SessionState | None
    accepted_seq: int
    committed_seq: int
    backlog: int
    rejected: int
    errors: int
    # Typed ``JournalStatus.last_error`` (WP09): the journal's own detail of
    # the most recent writer/admission error. ``None`` means the journal
    # reports no error — never a fabricated string. ``UNAVAILABLE`` only
    # appears when no session is attached at all.
    last_error_detail: str | None
    last_admission: RecorderAdmission | None = field(default=None)


class ResearchRecorder:
    """Admits configured-instrument events into one journal session.

    Threading: ``admit_tick``/``admit_trade``/``admit_bar`` are called from the
    event-dispatch thread; they only touch the bounded journal admission queue
    and never block on the writer. ``snapshot()`` may be called from any
    thread (including a UI timer) and never blocks the dispatch thread.
    """

    def __init__(self, store: Store, config: RecorderConfig) -> None:
        config.validate()
        self._store = store
        self.config = config
        self._session: JournalSession | None = None
        self._state = RecorderState.IDLE
        self._state_lock = threading.Lock()
        self._last_admission: RecorderAdmission | None = None
        self._admission_lock = threading.Lock()
        self._bridge_rejected = 0
        self._allowed = {i.vt_symbol for i in config.instruments}

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> str:
        """Open the journal session and begin admitting events."""

        with self._state_lock:
            if self._state is RecorderState.RECORDING:
                raise RecorderConfigError("recorder is already recording")
            if self._session is not None:
                self._session.close()
                self._session = None
            session = create_session(
                self._store,
                source_spec=self._build_source_spec(),
                calendar_spec=self.config.calendar_spec,
                session_id=self.config.session_id,
                predecessor_session_id=self.config.predecessor_session_id,
            )
            self._session = session
            self._state = RecorderState.RECORDING
            return session.session_id

    def _build_source_spec(self) -> str:
        # Simulated and production identities stay separate in the durable
        # source spec as well, not just in process memory.
        return (
            f"source_id={self.config.source_id};"
            f"source_kind={self.config.source_kind};"
            f"gateway_type={self.config.gateway_type or 'none'}"
        )

    def stop(self, *, timeout: float = 10.0) -> bool:
        """Fix the accepted cutoff and drain; True only on exact CLOSED.

        Delegates to the journal's public ``close_at_cutoff``; a bounded
        failure leaves the session open and the recorder in STOP_FAILED so a
        later ``retry_stop`` can re-attempt the SAME cutoff.
        """

        with self._state_lock:
            session = self._session
            if session is None:
                self._state = RecorderState.STOPPED
                return True
            if self._state is not RecorderState.RECORDING:
                return self._state is RecorderState.STOPPED
            result = session.close_at_cutoff(timeout=timeout)
            if result.committed_through_cutoff and result.state is SessionState.CLOSED:
                self._state = RecorderState.STOPPED
                return True
            self._state = RecorderState.STOP_FAILED
            return False

    def retry_stop(self, *, timeout: float = 10.0) -> bool:
        """Re-attempt a failed stop against the same fixed cutoff."""

        with self._state_lock:
            session = self._session
            if session is None:
                self._state = RecorderState.STOPPED
                return True
            if self._state is RecorderState.STOPPED:
                return True
            result = session.retry_close(timeout=timeout)
            if result.committed_through_cutoff and result.state is SessionState.CLOSED:
                self._state = RecorderState.STOPPED
                return True
            self._state = RecorderState.STOP_FAILED
            return False

    def release(self) -> None:
        """Release the OS lock/connection without changing session state."""

        with self._state_lock:
            if self._session is not None:
                self._session.close()
                self._session = None
            if self._state is RecorderState.RECORDING:
                self._state = RecorderState.STOP_FAILED

    # -- admission -----------------------------------------------------------

    def admit_tick(self, tick: Any) -> RecorderAdmission:
        """Admit one ``TickData`` observation (quote/snapshot, not trades)."""

        return self._admit(
            kind="tick",
            vt_symbol=str(getattr(tick, "vt_symbol", "")),
            event_ts_ns=self._event_ts_ns(getattr(tick, "datetime", None)),
            source_event_id=None,
            payload=self._tick_payload(tick),
        )

    def admit_trade(self, trade: Any) -> RecorderAdmission:
        """Admit one ``TradeData`` (real trade-by-trade, if a feed provides it)."""

        return self._admit(
            kind="trade",
            vt_symbol=str(getattr(trade, "vt_symbol", "")),
            event_ts_ns=self._event_ts_ns(getattr(trade, "datetime", None)),
            source_event_id=str(getattr(trade, "tradeid", "") or "") or None,
            payload=self._trade_payload(trade),
        )

    def admit_bar(self, bar: Any) -> RecorderAdmission:
        """Admit one ``BarData`` observation."""

        return self._admit(
            kind="bar",
            vt_symbol=str(getattr(bar, "vt_symbol", "")),
            event_ts_ns=self._event_ts_ns(getattr(bar, "datetime", None)),
            source_event_id=None,
            payload=self._bar_payload(bar),
        )

    def _admit(
        self,
        *,
        kind: str,
        vt_symbol: str,
        event_ts_ns: int | None,
        source_event_id: str | None,
        payload: Mapping[str, Any],
    ) -> RecorderAdmission:
        session = self._session
        if session is None or self._state is not RecorderState.RECORDING:
            admission = RecorderAdmission(
                accepted=False,
                assigned_seq=None,
                reason=f"recorder is {self._state.value}",
                vt_symbol=vt_symbol,
                kind=kind,
            )
            self._remember(admission, bridge_refusal=True)
            return admission
        if kind not in self.config.event_kinds:
            admission = RecorderAdmission(
                accepted=False,
                assigned_seq=None,
                reason=f"event kind {kind!r} not configured",
                vt_symbol=vt_symbol,
                kind=kind,
            )
            self._remember(admission, bridge_refusal=True)
            return admission
        if vt_symbol not in self._allowed:
            admission = RecorderAdmission(
                accepted=False,
                assigned_seq=None,
                reason=f"instrument {vt_symbol!r} not configured",
                vt_symbol=vt_symbol,
                kind=kind,
            )
            self._remember(admission, bridge_refusal=True)
            return admission
        # The journal deep-copies again at admission; this copy guarantees the
        # bridge itself cannot mutate the payload through the reference it
        # handed over if the caller mutates the original event object after
        # the callback returns.
        event = JournalEvent(
            kind=kind,
            instrument=vt_symbol,
            event_ts_ns=event_ts_ns,
            source_event_id=source_event_id,
            payload=copy.deepcopy(dict(payload)),
        )
        receipt: AdmissionReceipt = session.admit(event, timeout=0.0)
        admission = RecorderAdmission(
            accepted=receipt.accepted,
            assigned_seq=receipt.assigned_seq,
            reason=receipt.reason,
            vt_symbol=vt_symbol,
            kind=kind,
        )
        self._remember(admission)
        return admission

    def _remember(self, admission: RecorderAdmission, *, bridge_refusal: bool = False) -> None:
        with self._admission_lock:
            self._last_admission = admission
            if bridge_refusal:
                # Journal-level rejections are counted by JournalStatus; only
                # admissions refused by the bridge itself count here.
                self._bridge_rejected += 1

    # -- status --------------------------------------------------------------

    def snapshot(self) -> RecorderSnapshot:
        """Non-blocking state view; safe from any thread."""

        session = self._session
        if session is None:
            return RecorderSnapshot(
                state=self._state,
                source_id=self.config.source_id,
                source_kind=self.config.source_kind,
                instruments=tuple(sorted(self._allowed)),
                event_kinds=self.config.event_kinds,
                gateway_type=self.config.gateway_type,
                session_id=None,
                journal_path=None,
                journal_state=None,
                accepted_seq=0,
                committed_seq=0,
                backlog=0,
                rejected=self._bridge_rejected,
                errors=0,
                last_error_detail=UNAVAILABLE,
                last_admission=self._last_admission,
            )
        status: JournalStatus = session.status()
        # Typed last-error detail (WP09): the journal's own field, never
        # parsed from CloseResult.detail or exception prose.
        last_error = getattr(status, "last_error", None)
        return RecorderSnapshot(
            state=self._state,
            source_id=self.config.source_id,
            source_kind=self.config.source_kind,
            instruments=tuple(sorted(self._allowed)),
            event_kinds=self.config.event_kinds,
            gateway_type=self.config.gateway_type,
            session_id=session.session_id,
            journal_path=str(session.journal_path),
            journal_state=status.state,
            accepted_seq=status.accepted_seq,
            committed_seq=status.committed_seq,
            backlog=status.backlog,
            rejected=status.rejected + self._bridge_rejected,
            errors=status.errors,
            last_error_detail=last_error,
            last_admission=self._last_admission,
        )

    # -- payload builders (explicit fields, full copy) ------------------------

    @staticmethod
    def _event_ts_ns(value: Any) -> int | None:
        if isinstance(value, datetime):
            return int(value.timestamp() * 1e9)
        return None

    @staticmethod
    def _tick_payload(tick: Any) -> dict[str, Any]:
        # A CTP TickData (or any provider quote) is a quote/snapshot
        # observation. The payload keeps every public field so the journal
        # record is self-describing; the bridge never relabels it as
        # trade-by-trade.
        payload: dict[str, Any] = {
            "observation": "quote_snapshot",
            "gateway_name": str(getattr(tick, "gateway_name", "")),
            "symbol": str(getattr(tick, "symbol", "")),
            "exchange": str(getattr(tick, "exchange", "")),
            "datetime": str(getattr(tick, "datetime", "")),
            "name": str(getattr(tick, "name", "")),
            "volume": getattr(tick, "volume", None),
            "turnover": getattr(tick, "turnover", None),
            "open_interest": getattr(tick, "open_interest", None),
            "last_price": getattr(tick, "last_price", None),
            "last_volume": getattr(tick, "last_volume", None),
            "limit_up": getattr(tick, "limit_up", None),
            "limit_down": getattr(tick, "limit_down", None),
            "open_price": getattr(tick, "open_price", None),
            "high_price": getattr(tick, "high_price", None),
            "low_price": getattr(tick, "low_price", None),
            "pre_close": getattr(tick, "pre_close", None),
            "bid_price_1": getattr(tick, "bid_price_1", None),
            "ask_price_1": getattr(tick, "ask_price_1", None),
            "bid_volume_1": getattr(tick, "bid_volume_1", None),
            "ask_volume_1": getattr(tick, "ask_volume_1", None),
            "localtime": str(getattr(tick, "localtime", "")),
        }
        extra = getattr(tick, "extra", None)
        if isinstance(extra, Mapping):
            payload["extra"] = copy.deepcopy(dict(extra))
        return payload

    @staticmethod
    def _trade_payload(trade: Any) -> dict[str, Any]:
        return {
            "gateway_name": str(getattr(trade, "gateway_name", "")),
            "symbol": str(getattr(trade, "symbol", "")),
            "exchange": str(getattr(trade, "exchange", "")),
            "datetime": str(getattr(trade, "datetime", "")),
            "tradeid": str(getattr(trade, "tradeid", "")),
            "orderid": str(getattr(trade, "orderid", "")),
            "direction": str(getattr(trade, "direction", "")),
            "offset": str(getattr(trade, "offset", "")),
            "price": getattr(trade, "price", None),
            "volume": getattr(trade, "volume", None),
        }

    @staticmethod
    def _bar_payload(bar: Any) -> dict[str, Any]:
        return {
            "gateway_name": str(getattr(bar, "gateway_name", "")),
            "symbol": str(getattr(bar, "symbol", "")),
            "exchange": str(getattr(bar, "exchange", "")),
            "datetime": str(getattr(bar, "datetime", "")),
            "interval": str(getattr(bar, "interval", "")),
            "volume": getattr(bar, "volume", None),
            "turnover": getattr(bar, "turnover", None),
            "open_interest": getattr(bar, "open_interest", None),
            "open_price": getattr(bar, "open_price", None),
            "high_price": getattr(bar, "high_price", None),
            "low_price": getattr(bar, "low_price", None),
            "close_price": getattr(bar, "close_price", None),
        }
