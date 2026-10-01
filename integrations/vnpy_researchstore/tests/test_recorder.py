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


# -- installed-finding regressions: seal-grammar-conformant stored source_spec


def test_stored_source_spec_is_seal_conformant_and_identity_visible(store) -> None:
    """Regression (installed-review F1): the durable source_spec written by
    the recorder MUST satisfy the sealing grammar while keeping the explicit
    simulated/production identity visible. Simulated and production specs
    stay distinct — never merged, never inferred from symbol naming."""

    from research_store.sealing import validate_source_spec
    from research_store.store import open_store

    sim = make_recorder(store)
    prod = make_recorder(
        store, source_id="ctp-live", source_kind=SOURCE_PRODUCTION,
        gateway_type="ctp",
    )
    sim_id = sim.start()
    prod_id = prod.start()
    sim.stop(timeout=10.0)
    prod.stop(timeout=10.0)

    sim_spec = sim.stored_source_spec
    prod_spec = prod.stored_source_spec
    assert sim_spec == "rec-simulated-ctp-sim-test"
    assert prod_spec == "rec-production-ctp-ctp-live"
    assert sim_spec != prod_spec  # identities never merged
    # Grammar-conformant: the sealer's own public validator accepts both.
    sem_sim = validate_source_spec(sim_spec)
    sem_prod = validate_source_spec(prod_spec)
    assert sem_sim.kind == "unknown"  # no asset class inferred from naming
    assert sem_prod.kind == "unknown"

    sim.release()
    prod.release()

    # The value DURABLY stored in the journals equals the bridge value.
    store2 = open_store(store.root)
    try:
        for sid, expected in (
            (sim_id, sim_spec),
            (prod_id, prod_spec),
        ):
            session = open_store_session(store2, sid)
            try:
                assert session.source_spec == expected
            finally:
                session.close()
    finally:
        store2.close()


def open_store_session(store, session_id: str):
    from research_store.journal import open_session

    return open_session(store, session_id, readonly=True)


def test_invalid_identity_fields_refused_at_config(store) -> None:
    """Config fields that would break the seal grammar are refused at
    configuration time instead of producing an unsealable journal."""

    with pytest.raises(RecorderConfigError, match="invalid durable source_spec"):
        make_recorder(store, source_id="sim=test")
    with pytest.raises(RecorderConfigError, match="invalid durable source_spec"):
        make_recorder(store, source_id="sim;injected")
    with pytest.raises(RecorderConfigError, match="invalid durable source_spec"):
        make_recorder(store, source_id="x" * 80)


def test_recorded_session_seals_end_to_end(store) -> None:
    """The exact installed-review F1 flow, now green: ticks recorded through
    the REAL bridge → clean stop → the durably stored source_spec passed
    VERBATIM to the public seal API → receipt. No metadata repair."""

    from research_store.models import AssetClass, SealRequest
    from research_store.sealing import seal
    from research_store.store import open_store

    recorder = make_recorder(store)
    session_id = recorder.start()
    # 30 s spacing across two wall-clock minutes: minute A gains completion
    # evidence from the minute-B tick; minute B stays an unevidenced tail.
    for i, (m, s) in enumerate(((0, 20), (0, 50), (1, 20))):
        recorder.admit_tick(
            make_tick(when=datetime(2026, 9, 30, 9, m, s))
        )
        assert recorder.snapshot().accepted_seq == i + 1
    assert recorder.stop(timeout=10.0) is True
    recorder.release()
    stored_spec = recorder.stored_source_spec

    store2 = open_store(store.root)
    try:
        session = open_store_session(store2, session_id)
        stored_on_disk = session.source_spec
        session.close()
        assert stored_on_disk == stored_spec

        receipt = seal(
            store2,
            SealRequest(
                session_id=session_id,
                committed_seq_start=1,
                committed_seq_end=3,
                transform_version="agg-v1",
                source_spec=stored_on_disk,  # verbatim stored identity
                calendar_spec="tz:Asia/Shanghai",
                asset_class=AssetClass.FUTURES,
                volume_unit="lots",
                turnover_unit="CNY",
            ),
        )
        assert receipt.session_id == session_id
        assert receipt.input_events == 3
        # 3 verbatim ticks + 1 evidenced minute bar (tail stays partial).
        assert receipt.accepted_rows == 4
        assert receipt.dataset_id
        # Repeat seal: idempotent replay, same identity.
        repeat = seal(
            store2,
            SealRequest(
                session_id=session_id,
                committed_seq_start=1,
                committed_seq_end=3,
                transform_version="agg-v1",
                source_spec=stored_on_disk,
                calendar_spec="tz:Asia/Shanghai",
                asset_class=AssetClass.FUTURES,
                volume_unit="lots",
                turnover_unit="CNY",
            ),
        )
        assert repeat.idempotent_replay is True
        assert repeat.seal_id == receipt.seal_id
        assert repeat.dataset_id == receipt.dataset_id
    finally:
        store2.close()
