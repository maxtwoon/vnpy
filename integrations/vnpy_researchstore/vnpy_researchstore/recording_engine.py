"""Recording main engine with the binding stop-barrier protocol.

``RecordingMainEngine`` subclasses the vnpy ``MainEngine`` but overrides
``close()`` so a recorder shutdown can never silently lose queued events:

1. ``close()`` enqueues a ``RecorderStopBarrier`` event BEFORE any parent
   close or ``EventEngine.stop()`` — so every tick already queued ahead of the
   barrier is dispatched first, on the still-running dispatch thread.
2. The barrier handler (running ON the dispatch thread) unregisters the
   recorder's event callbacks there — after all earlier queued ticks — and
   starts the journal close (fix accepted cutoff, drain).
3. The controlling thread then waits at most ``STOP_WAIT_TIMEOUT_S`` for the
   journal to report ``committed == accepted cutoff`` and state CLOSED.
4. Only on success does it call ``super().close()``. On timeout or write
   error it reports STOP_FAILED, does NOT call the parent close, and leaves
   the event engine and process usable so ``retry_stop()`` can re-attempt the
   same cutoff.

A stop requested from the dispatch thread itself is rejected with
``RecorderStopError`` (marshalled back to the caller) instead of deadlocking.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum

from vnpy.event import Event, EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.event import EVENT_TICK, EVENT_TRADE

from .recorder import RecorderSnapshot, ResearchRecorder

#: Event type of the stop barrier. Internal to the recording engine; never
#: collides with vnpy trading event types.
EVENT_RECORDER_STOP_BARRIER = "eRecorderStopBarrier"

#: Bound for the controlling thread's wait for committed==cutoff + CLOSED.
STOP_WAIT_TIMEOUT_S = 10.0

#: How long the controlling thread may wait for the barrier handler itself to
#: run after the barrier event was enqueued (it runs after earlier queued
#: ticks; this bound is generous but finite).
BARRIER_DISPATCH_TIMEOUT_S = 10.0


class RecorderStopError(Exception):
    """Stop protocol violation (e.g. stop requested on the dispatch thread)."""


class StopResult(str, Enum):
    """Outcome of one stop attempt."""

    CLOSED = "CLOSED"
    STOP_FAILED = "STOP_FAILED"
    NOT_RECORDING = "NOT_RECORDING"


@dataclass(frozen=True)
class StopReport:
    """Typed result of a stop/retry attempt."""

    result: StopResult
    session_id: str | None
    accepted_seq: int
    committed_seq: int
    detail: str


@dataclass(frozen=True)
class RecorderStopBarrier:
    """Payload of the barrier event.

    ``attempt`` distinguishes a first stop from a retry; both run the same
    protocol against the same fixed cutoff (the journal's ``retry_close``
    re-attempts the SAME cutoff, never a new one).
    """

    attempt: int


class RecordingMainEngine(MainEngine):
    """MainEngine whose close honours the recorder stop barrier.

    The engine never adds gateways, connects accounts, or loads strategies by
    itself; ``add_recorder`` only registers event callbacks on the shared
    event engine.
    """

    def __init__(self, event_engine: EventEngine | None = None) -> None:
        super().__init__(event_engine)
        self._recorder: ResearchRecorder | None = None
        self._recorder_registered = False
        self._stop_lock = threading.Lock()
        self._stop_report: StopReport | None = None
        self._barrier_done = threading.Event()
        self._barrier_attempt = 0
        self._parent_closed = False

    # -- recorder wiring -----------------------------------------------------

    def add_recorder(self, recorder: ResearchRecorder) -> None:
        """Register the recorder's callbacks on the shared event engine.

        Idempotent: registering twice does not double-admit events.
        """

        if self._recorder is recorder and self._recorder_registered:
            return
        if self._recorder is not None and self._recorder is not recorder:
            raise RecorderStopError(
                "this engine already serves a different recorder; create a "
                "fresh RecordingMainEngine instead"
            )
        self._recorder = recorder
        if not self._recorder_registered:
            kinds = recorder.config.event_kinds
            if "tick" in kinds:
                self.event_engine.register(EVENT_TICK, self._on_tick)
            if "trade" in kinds:
                self.event_engine.register(EVENT_TRADE, self._on_trade)
            # vnpy core has no standard EVENT_BAR producer; bar admission is
            # available through ``ResearchRecorder.admit_bar`` for explicit
            # callers instead of an engine-level subscription.
            self.event_engine.register(EVENT_RECORDER_STOP_BARRIER, self._on_stop_barrier)
            self._recorder_registered = True

    def _on_tick(self, event: Event) -> None:
        recorder = self._recorder
        if recorder is not None:
            recorder.admit_tick(event.data)

    def _on_trade(self, event: Event) -> None:
        recorder = self._recorder
        if recorder is not None:
            recorder.admit_trade(event.data)

    # -- stop barrier ----------------------------------------------------------

    def _on_stop_barrier(self, event: Event) -> None:
        """Runs ON the dispatch thread, after earlier queued ticks.

        Unregisters the recorder callbacks HERE (not when the UI requested
        the stop) so every tick queued before the barrier has been admitted
        before the accepted cutoff is fixed. Then starts the journal close;
        the controlling thread waits on ``_barrier_done``.
        """

        barrier = event.data
        attempt = barrier.attempt if isinstance(barrier, RecorderStopBarrier) else 0
        self._unregister_recorder_callbacks()
        recorder = self._recorder
        if recorder is None:
            self._stop_report = StopReport(
                result=StopResult.NOT_RECORDING,
                session_id=None,
                accepted_seq=0,
                committed_seq=0,
                detail="no recorder attached; nothing to stop",
            )
            self._barrier_done.set()
            return
        ok = recorder.retry_stop(timeout=STOP_WAIT_TIMEOUT_S) if attempt > 1 else (
            recorder.stop(timeout=STOP_WAIT_TIMEOUT_S)
        )
        snapshot = recorder.snapshot()
        if ok:
            self._stop_report = StopReport(
                result=StopResult.CLOSED,
                session_id=snapshot.session_id,
                accepted_seq=snapshot.accepted_seq,
                committed_seq=snapshot.committed_seq,
                detail="committed through exact accepted cutoff; session CLOSED",
            )
        else:
            self._stop_report = StopReport(
                result=StopResult.STOP_FAILED,
                session_id=snapshot.session_id,
                accepted_seq=snapshot.accepted_seq,
                committed_seq=snapshot.committed_seq,
                detail=(
                    f"journal did not reach committed==accepted CLOSED within "
                    f"{STOP_WAIT_TIMEOUT_S}s; session left open for retry_stop()"
                ),
            )
        self._barrier_done.set()

    def _unregister_recorder_callbacks(self) -> None:
        if not self._recorder_registered:
            return
        self.event_engine.unregister(EVENT_TICK, self._on_tick)
        self.event_engine.unregister(EVENT_TRADE, self._on_trade)
        self._recorder_registered = False

    # -- close protocol --------------------------------------------------------

    def close(self) -> StopReport:  # type: ignore[override]
        """Binding stop-barrier close; see module docstring.

        Returns the typed ``StopReport`` (the parent ``MainEngine.close``
        returns ``None``; the narrowed return type is intentional so callers
        can honour a failed stop). On STOP_FAILED the parent close is NOT
        called: the event engine keeps running and ``retry_stop()`` can
        re-attempt the same cutoff.
        """

        dispatch_thread = getattr(self.event_engine, "_thread", None)
        if dispatch_thread is not None and threading.current_thread() is dispatch_thread:
            raise RecorderStopError(
                "close() requested from the event-dispatch thread would "
                "deadlock; marshal the request to a controlling thread"
            )
        with self._stop_lock:
            if self._parent_closed:
                return StopReport(
                    result=StopResult.NOT_RECORDING,
                    session_id=None,
                    accepted_seq=0,
                    committed_seq=0,
                    detail="engine is already closed",
                )
            recorder = self._recorder
            if recorder is None or recorder.snapshot().state.value in (
                "IDLE",
                "STOPPED",
            ):
                # Nothing recording: plain parent close is safe.
                self._parent_closed = True
                super().close()
                return StopReport(
                    result=StopResult.NOT_RECORDING,
                    session_id=None,
                    accepted_seq=0,
                    committed_seq=0,
                    detail="no active recorder; parent closed normally",
                )

            self._barrier_attempt += 1
            self._barrier_done.clear()
            # (1) Enqueue the barrier BEFORE any parent close / engine stop.
            self.event_engine.put(
                Event(EVENT_RECORDER_STOP_BARRIER, RecorderStopBarrier(attempt=self._barrier_attempt))
            )
            # (3) Wait at most the bound for the barrier outcome.
            finished = self._barrier_done.wait(timeout=BARRIER_DISPATCH_TIMEOUT_S)
            if not finished:
                self._stop_report = StopReport(
                    result=StopResult.STOP_FAILED,
                    session_id=recorder.snapshot().session_id,
                    accepted_seq=recorder.snapshot().accepted_seq,
                    committed_seq=recorder.snapshot().committed_seq,
                    detail=(
                        f"stop barrier did not run within "
                        f"{BARRIER_DISPATCH_TIMEOUT_S}s; parent close withheld"
                    ),
                )
            report = self._stop_report
            assert report is not None
            if report.result is not StopResult.CLOSED:
                # (4) STOP_FAILED: keep process/event engine usable for retry.
                return report
            # Success only: parent close, then release the journal OS lock.
            self._parent_closed = True
            super().close()
            recorder.release()
            return report

    def retry_stop(self) -> StopReport:
        """Re-attempt a failed stop from a controlling thread.

        Enqueues a fresh barrier with a new attempt number; the journal's
        ``retry_close`` re-attempts the SAME fixed cutoff.
        """

        dispatch_thread = getattr(self.event_engine, "_thread", None)
        if dispatch_thread is not None and threading.current_thread() is dispatch_thread:
            raise RecorderStopError(
                "retry_stop() requested from the event-dispatch thread would "
                "deadlock; marshal the request to a controlling thread"
            )
        with self._stop_lock:
            if self._parent_closed:
                return StopReport(
                    result=StopResult.NOT_RECORDING,
                    session_id=None,
                    accepted_seq=0,
                    committed_seq=0,
                    detail="engine is already closed",
                )
            recorder = self._recorder
            if recorder is None:
                return StopReport(
                    result=StopResult.NOT_RECORDING,
                    session_id=None,
                    accepted_seq=0,
                    committed_seq=0,
                    detail="no recorder attached",
                )
            self._barrier_attempt += 1
            self._barrier_done.clear()
            self.event_engine.put(
                Event(
                    EVENT_RECORDER_STOP_BARRIER,
                    RecorderStopBarrier(attempt=self._barrier_attempt),
                )
            )
            finished = self._barrier_done.wait(timeout=BARRIER_DISPATCH_TIMEOUT_S)
            if not finished:
                self._stop_report = StopReport(
                    result=StopResult.STOP_FAILED,
                    session_id=recorder.snapshot().session_id,
                    accepted_seq=recorder.snapshot().accepted_seq,
                    committed_seq=recorder.snapshot().committed_seq,
                    detail=(
                        f"retry barrier did not run within "
                        f"{BARRIER_DISPATCH_TIMEOUT_S}s; parent close withheld"
                    ),
                )
            report = self._stop_report
            assert report is not None
            if report.result is not StopResult.CLOSED:
                return report
            self._parent_closed = True
            super().close()
            recorder.release()
            return report

    # -- status ----------------------------------------------------------------

    def recorder_snapshot(self) -> RecorderSnapshot | None:
        recorder = self._recorder
        return recorder.snapshot() if recorder is not None else None

    @property
    def parent_closed(self) -> bool:
        return self._parent_closed

    @property
    def recorder_registered(self) -> bool:
        return self._recorder_registered


__all__ = [
    "BARRIER_DISPATCH_TIMEOUT_S",
    "EVENT_RECORDER_STOP_BARRIER",
    "RecordingMainEngine",
    "RecorderStopBarrier",
    "RecorderStopError",
    "STOP_WAIT_TIMEOUT_S",
    "StopReport",
    "StopResult",
]
