"""Stop-barrier protocol tests for RecordingMainEngine.

Covers the binding protocol: barrier enqueued before parent close, earlier
queued ticks processed first, callbacks unregistered inside the barrier,
exact committed cutoff, parent close withheld on timeout/write error, retry
after drain becomes possible, dispatch-thread stop rejection, and repeated
stop. All offline, simulated/test labelled, task-owned temp stores only.
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_store import init_store  # noqa: E402
from vnpy.event import Event, EventEngine  # noqa: E402
from vnpy.trader.constant import Exchange  # noqa: E402
from vnpy.trader.event import EVENT_TICK  # noqa: E402
from vnpy.trader.object import TickData  # noqa: E402
from vnpy_researchstore.recorder import (  # noqa: E402
    RecorderConfig,
    RecorderInstrument,
    ResearchRecorder,
)
from vnpy_researchstore.recording_engine import (  # noqa: E402
    EVENT_RECORDER_STOP_BARRIER,
    RecordingMainEngine,
    RecorderStopError,
    StopResult,
)


def make_tick(symbol: str = "rb2501", price: float = 3500.0) -> TickData:
    return TickData(
        gateway_name="test",
        symbol=symbol,
        exchange=Exchange.SHFE,
        datetime=datetime(2026, 9, 17, 9, 0, 0),
        volume=1.0,
        turnover=price,
        last_price=price,
    )


@pytest.fixture()
def store(tmp_path: Path):
    s = init_store(tmp_path / "store")
    yield s
    s.close()


def make_engine(store) -> tuple[RecordingMainEngine, ResearchRecorder]:
    engine = RecordingMainEngine()
    recorder = ResearchRecorder(
        store,
        RecorderConfig(
            source_id="sim-test",
            source_kind="simulated",
            calendar_spec="tz:Asia/Shanghai",
            instruments=(RecorderInstrument("rb2501", "SHFE"),),
            event_kinds=("tick",),
            gateway_type="ctp",
        ),
    )
    engine.add_recorder(recorder)
    return engine, recorder


def test_queued_ticks_then_barrier_order(store) -> None:
    """Ticks queued BEFORE the barrier are admitted before the cutoff."""

    engine, recorder = make_engine(store)
    recorder.start()
    for i in range(20):
        engine.event_engine.put(Event(EVENT_TICK, make_tick(price=3500.0 + i)))
    # Let the dispatch thread drain the ticks before the stop request.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if recorder.snapshot().accepted_seq >= 20:
            break
        time.sleep(0.01)
    report = engine.close()
    assert report.result is StopResult.CLOSED
    assert report.accepted_seq == 20
    assert report.committed_seq == 20
    assert engine.parent_closed is True


def test_barrier_enqueued_before_parent_close(store, monkeypatch) -> None:
    """The barrier event must be put on the queue before EventEngine.stop."""

    engine, recorder = make_engine(store)
    recorder.start()
    engine.event_engine.put(Event(EVENT_TICK, make_tick()))
    time.sleep(0.2)

    order: list[str] = []
    original_put = EventEngine.put
    original_stop = EventEngine.stop

    def traced_put(self, event):  # noqa: ANN001
        if event.type == EVENT_RECORDER_STOP_BARRIER:
            order.append("barrier")
        return original_put(self, event)

    def traced_stop(self):  # noqa: ANN001
        order.append("engine_stop")
        return original_stop(self)

    monkeypatch.setattr(EventEngine, "put", traced_put)
    monkeypatch.setattr(EventEngine, "stop", traced_stop)
    report = engine.close()
    assert report.result is StopResult.CLOSED
    assert order == ["barrier", "engine_stop"]


def test_callbacks_unregistered_inside_barrier(store) -> None:
    engine, recorder = make_engine(store)
    recorder.start()
    engine.event_engine.put(Event(EVENT_TICK, make_tick()))
    time.sleep(0.2)
    assert engine.recorder_registered is True
    report = engine.close()
    assert report.result is StopResult.CLOSED
    assert engine.recorder_registered is False
    # After close, tick events no longer reach the recorder.
    snapshot_before = recorder.snapshot()
    engine.event_engine.put(Event(EVENT_TICK, make_tick()))
    time.sleep(0.2)
    assert recorder.snapshot().accepted_seq == snapshot_before.accepted_seq


def test_parent_close_withheld_on_close_timeout(store, monkeypatch) -> None:
    """A journal close that cannot finish within its bound => STOP_FAILED,
    parent close NOT called, engine stays usable for retry.

    The patched first ``close_at_cutoff`` runs the REAL journal close with a
    bound too small for the writer to finish — exactly what a genuine timeout
    looks like from the engine's side (no CLOSED, ``committed_through_cutoff``
    False) — then the patch is removed and the retry succeeds.
    """

    from research_store.journal import JournalSession

    engine, recorder = make_engine(store)
    recorder.start()
    engine.event_engine.put(Event(EVENT_TICK, make_tick()))
    time.sleep(0.2)

    original = JournalSession.close_at_cutoff

    def timing_out_close(self, *, timeout=10.0):  # noqa: ANN001, ANN202
        return original(self, timeout=0.001)

    monkeypatch.setattr(JournalSession, "close_at_cutoff", timing_out_close)
    report = engine.close()
    assert report.result is StopResult.STOP_FAILED
    assert engine.parent_closed is False
    # Process/event engine still usable: retry is possible once the journal
    # can drain (here: the patch is removed, the real close succeeds).
    monkeypatch.undo()
    retry_report = engine.retry_stop()
    assert retry_report.result is StopResult.CLOSED
    assert engine.parent_closed is True


def test_retry_after_drain_becomes_possible(store, monkeypatch) -> None:
    """First stop fails inside the journal bound; once the writer drains,
    retry_stop reaches the exact cutoff and CLOSED."""

    from research_store.journal import JournalSession

    engine, recorder = make_engine(store)
    recorder.start()
    engine.event_engine.put(Event(EVENT_TICK, make_tick()))
    time.sleep(0.2)

    calls = {"n": 0}
    original = JournalSession.close_at_cutoff

    def flaky_close(self, *, timeout=10.0):  # noqa: ANN001, ANN202
        calls["n"] += 1
        if calls["n"] == 1:
            return original(self, timeout=0.001)  # bound too small: fails
        return original(self, timeout=timeout)

    monkeypatch.setattr(JournalSession, "close_at_cutoff", flaky_close)
    report = engine.close()
    assert report.result is StopResult.STOP_FAILED
    assert engine.parent_closed is False
    retry_report = engine.retry_stop()
    assert retry_report.result is StopResult.CLOSED
    assert retry_report.accepted_seq == retry_report.committed_seq
    assert engine.parent_closed is True


def test_dispatch_thread_stop_rejected(store) -> None:
    """close() from the dispatch thread must raise, not deadlock."""

    engine, recorder = make_engine(store)
    recorder.start()
    outcome: list[str] = []
    done = threading.Event()

    def tick_then_close(event):  # noqa: ANN001, ANN202
        try:
            engine.close()
        except RecorderStopError:
            outcome.append("rejected")
        finally:
            done.set()

    engine.event_engine.register(EVENT_TICK, tick_then_close)
    engine.event_engine.put(Event(EVENT_TICK, make_tick()))
    assert done.wait(timeout=10.0), "dispatch-thread close deadlocked"
    assert outcome == ["rejected"]
    engine.event_engine.unregister(EVENT_TICK, tick_then_close)
    report = engine.close()
    assert report.result is StopResult.CLOSED


def test_repeated_stop(store) -> None:
    engine, recorder = make_engine(store)
    recorder.start()
    engine.event_engine.put(Event(EVENT_TICK, make_tick()))
    time.sleep(0.2)
    first = engine.close()
    assert first.result is StopResult.CLOSED
    second = engine.close()
    assert second.result is StopResult.NOT_RECORDING
    assert engine.parent_closed is True


def test_close_without_recorder_parent_closes(store) -> None:
    engine = RecordingMainEngine()
    report = engine.close()
    assert report.result is StopResult.NOT_RECORDING
    assert engine.parent_closed is True


def test_no_unsolicited_gateway_connect(store, monkeypatch) -> None:
    import vnpy.trader.engine as engine_module

    def _forbidden(*args, **kwargs):  # noqa: ANN002, ANN003
        pytest.fail("MainEngine.connect must not be called")

    monkeypatch.setattr(engine_module.MainEngine, "connect", _forbidden)
    engine, recorder = make_engine(store)
    recorder.start()
    engine.event_engine.put(Event(EVENT_TICK, make_tick()))
    time.sleep(0.2)
    report = engine.close()
    assert report.result is StopResult.CLOSED
