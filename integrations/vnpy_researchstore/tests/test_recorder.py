"""Bridge-level recorder tests: admission policy, payload copying, isolation.

All tests are offline and labelled simulated/test. They use only task-owned
temporary stores and the plugin venv interpreter; no gateway, account,
network, or provider is touched.
"""

from __future__ import annotations

import sys
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
from research_store.journal_models import SessionState  # noqa: E402
from vnpy.trader.constant import Exchange  # noqa: E402
from vnpy.trader.object import TickData  # noqa: E402
from vnpy_researchstore.recorder import (  # noqa: E402
    SOURCE_PRODUCTION,
    SOURCE_SIMULATED,
    UNAVAILABLE,
    RecorderConfig,
    RecorderConfigError,
    RecorderInstrument,
    RecorderState,
    ResearchRecorder,
)


def make_tick(
    symbol: str = "rb2501",
    exchange: Exchange = Exchange.SHFE,
    price: float = 3500.0,
    when: datetime | None = None,
) -> TickData:
    return TickData(
        gateway_name="test",
        symbol=symbol,
        exchange=exchange,
        datetime=when or datetime(2026, 9, 17, 9, 0, 0),
        volume=10.0,
        turnover=35000.0,
        last_price=price,
        bid_price_1=price - 1,
        ask_price_1=price + 1,
        bid_volume_1=2.0,
        ask_volume_1=3.0,
    )


@pytest.fixture()
def store(tmp_path: Path):
    s = init_store(tmp_path / "store")
    yield s
    s.close()


def make_recorder(store, **overrides) -> ResearchRecorder:
    config = RecorderConfig(
        source_id=overrides.pop("source_id", "sim-test"),
        source_kind=overrides.pop("source_kind", SOURCE_SIMULATED),
        calendar_spec=overrides.pop("calendar_spec", "tz:Asia/Shanghai"),
        instruments=overrides.pop(
            "instruments", (RecorderInstrument("rb2501", "SHFE"),)
        ),
        event_kinds=overrides.pop("event_kinds", ("tick",)),
        gateway_type=overrides.pop("gateway_type", "ctp"),
        **overrides,
    )
    return ResearchRecorder(store, config)


def test_admission_and_exact_cutoff(store) -> None:
    recorder = make_recorder(store)
    session_id = recorder.start()
    for i in range(5):
        admission = recorder.admit_tick(make_tick(price=3500.0 + i))
        assert admission.accepted
        assert admission.assigned_seq == i + 1
    assert recorder.stop(timeout=10.0) is True
    snapshot = recorder.snapshot()
    assert snapshot.state is RecorderState.STOPPED
    assert snapshot.journal_state is SessionState.CLOSED
    assert snapshot.accepted_seq == 5
    assert snapshot.committed_seq == 5
    assert snapshot.backlog == 0
    assert snapshot.session_id == session_id
    recorder.release()


def test_unconfigured_instrument_refused(store) -> None:
    recorder = make_recorder(store)
    recorder.start()
    admission = recorder.admit_tick(make_tick(symbol="ag2506"))
    assert not admission.accepted
    assert "not configured" in (admission.reason or "")
    assert recorder.snapshot().rejected == 1
    assert recorder.stop(timeout=10.0) is True
    recorder.release()


def test_local_synthetic_contract_refused_by_config(store) -> None:
    with pytest.raises(RecorderConfigError, match="LOCAL"):
        make_recorder(
            store, instruments=(RecorderInstrument("SYNTH", "LOCAL"),)
        )


def test_empty_config_refused(store) -> None:
    with pytest.raises(RecorderConfigError):
        make_recorder(store, instruments=())


def test_source_kind_isolation(store) -> None:
    """Simulated and production recorders never share a session identity."""

    sim = make_recorder(store, source_id="simnow", source_kind=SOURCE_SIMULATED)
    prod = make_recorder(
        store, source_id="ctp-live", source_kind=SOURCE_PRODUCTION
    )
    sim_session = sim.start()
    prod_session = prod.start()
    assert sim_session != prod_session
    sim_spec = sim.snapshot()
    prod_spec = prod.snapshot()
    assert sim_spec.source_kind == SOURCE_SIMULATED
    assert prod_spec.source_kind == SOURCE_PRODUCTION
    assert sim_spec.source_id != prod_spec.source_id
    sim.stop(timeout=10.0)
    prod.stop(timeout=10.0)
    sim.release()
    prod.release()


def test_invalid_source_kind_refused(store) -> None:
    with pytest.raises(RecorderConfigError, match="source_kind"):
        make_recorder(store, source_kind="live-ish")


def _read_committed_payloads(store, session_id: str) -> list[dict]:
    """Read committed events straight from the journal SQLite (read-only).

    ``open_session`` only accepts OPEN sessions, so after a successful close
    the durable rows are verified with a plain read-only connection instead.
    """

    import json
    import sqlite3

    path = store.path.journals / f"{session_id}.sqlite"
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        committed = conn.execute("SELECT committed_seq FROM watermark").fetchone()[0]
        rows = conn.execute(
            "SELECT kind, instrument, payload_json FROM events WHERE seq <= ? ORDER BY seq",
            (committed,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {"kind": kind, "instrument": instrument, "payload": json.loads(payload)}
        for kind, instrument, payload in rows
    ]


def test_payload_copy_immune_to_later_mutation(store) -> None:
    """Mutating the original TickData after admission must not change the
    durable payload (the bridge deep-copies before admission)."""

    recorder = make_recorder(store)
    session_id = recorder.start()
    tick = make_tick(price=3500.0)
    admission = recorder.admit_tick(tick)
    assert admission.accepted
    # Mutate the original event object after the callback returned.
    tick.last_price = 9999.0
    tick.volume = 123456.0
    assert recorder.stop(timeout=10.0) is True
    recorder.release()
    (event,) = _read_committed_payloads(store, session_id)
    assert event["payload"]["last_price"] == 3500.0
    assert event["payload"]["volume"] == 10.0
    assert event["payload"]["observation"] == "quote_snapshot"
    assert event["kind"] == "tick"
    assert event["instrument"] == "rb2501.SHFE"


def test_tick_observation_is_quote_not_trade_by_trade(store) -> None:
    recorder = make_recorder(store)
    session_id = recorder.start()
    recorder.admit_tick(make_tick())
    assert recorder.stop(timeout=10.0) is True
    recorder.release()
    (event,) = _read_committed_payloads(store, session_id)
    assert event["kind"] == "tick"
    assert event["payload"]["observation"] == "quote_snapshot"


def test_last_error_detail_typed_or_honestly_unavailable(store) -> None:
    """WP09 typed ``JournalStatus.last_error``: with a session attached the
    bridge surfaces the journal's own typed detail (None when the journal
    reports no error); with no session at all the honest UNAVAILABLE marker
    is used instead of a fabricated value."""

    recorder = make_recorder(store)
    snapshot = recorder.snapshot()
    assert snapshot.session_id is None
    assert snapshot.last_error_detail == UNAVAILABLE
    recorder.start()
    snapshot = recorder.snapshot()
    assert snapshot.session_id is not None
    assert snapshot.last_error_detail is None
    assert snapshot.errors == 0
    assert recorder.stop(timeout=10.0) is True
    recorder.release()


def test_repeated_stop_is_stable(store) -> None:
    recorder = make_recorder(store)
    recorder.start()
    recorder.admit_tick(make_tick())
    assert recorder.stop(timeout=10.0) is True
    # Second stop on an already-closed session must not fail or rewrite state.
    assert recorder.stop(timeout=10.0) is True
    assert recorder.snapshot().journal_state is SessionState.CLOSED
    recorder.release()


def test_admission_after_stop_refused(store) -> None:
    recorder = make_recorder(store)
    recorder.start()
    recorder.admit_tick(make_tick())
    assert recorder.stop(timeout=10.0) is True
    admission = recorder.admit_tick(make_tick())
    assert not admission.accepted
    recorder.release()


def test_no_gateway_connect_side_effect(store, monkeypatch) -> None:
    """Adding a recorder must never instantiate or connect a gateway."""

    import vnpy.trader.engine as engine_module

    def _forbidden_connect(*args, **kwargs):  # noqa: ANN002, ANN003
        pytest.fail("connect() must not be called by the recorder")

    monkeypatch.setattr(engine_module.MainEngine, "connect", _forbidden_connect)
    recorder = make_recorder(store)
    recorder.start()
    recorder.admit_tick(make_tick())
    assert recorder.stop(timeout=10.0) is True
    recorder.release()
