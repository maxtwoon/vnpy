"""Sealing tests: committed-range validation, idempotent replay, deterministic
repeat seal, changed-input new identity, uncommitted refusal, crash recovery
through the standard sweep, and a synthetic offline seal→freeze→query example.

recording02I corrections:

F1 — bars flagged PARTIAL (mid-minute stop, no completion evidence) are
EXCLUDED from the sealed canonical bars; committed ticks are always kept.

F2 — the committed sequence range is runtime idempotency provenance, NOT
semantic identity: range extension of one session extends the SAME dataset
through new revisions with parent linkage and dedup of already-sealed ticks
(complete effective partition manifests), never a forked dataset.

F4 — asset class / volume unit / turnover unit are explicit validated
semantics. A typed ``source_spec`` (``"<kind>:<name>[@<version>]"``) pins the
allowed asset class; an untyped name seals honestly as OTHER/unknown; unit
and calendar-spec refusals are explicit ``SealError``.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from research_store.aggregation import STATUS_PARTIAL
from research_store.journal import create_session
from research_store.journal_models import JournalEvent
from research_store.models import (
    AssetClass,
    Interval,
    RecordKind,
    SealRequest,
    Selection,
    SnapshotRequest,
    compute_dataset_id,
)
from research_store.sealing import (
    SealError,
    _spec,
    plan_seal,
    seal,
    seal_idempotency_key,
    validate_calendar_spec,
    validate_source_spec,
)
from research_store.snapshots import freeze, open_snapshot
from research_store.store import init_store

BASE = 1_700_000_000_000_000_000
NS_MINUTE = 60 * 1_000_000_000
SOURCE_SPEC = "futures:synthetic-recording"


def tick(
    ts: int,
    volume: float,
    turnover: float,
    price: float = 10.0,
    instrument: str = "IF2403.CFFEX",
) -> JournalEvent:
    return JournalEvent(
        kind="tick",
        instrument=instrument,
        event_ts_ns=ts,
        source_event_id=f"ctp:{ts}",
        payload={"last_price": price, "volume": volume, "turnover": turnover},
    )


@pytest.fixture()
def store(tmp_path: Path):
    s = init_store(tmp_path / "store")
    yield s
    s.close()


def drain(session, n: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if session.status().committed_seq >= n:
            return
        time.sleep(0.01)
    raise AssertionError(f"committed_seq did not reach {n}: {session.status()}")


def make_request(
    session_id: str,
    end: int,
    transform: str = "t0",
    source_spec: str = SOURCE_SPEC,
    calendar: str = "Asia/Shanghai",
    asset_class: AssetClass = AssetClass.FUTURES,
    volume_unit: str = "contracts",
    turnover_unit: str = "currency",
) -> SealRequest:
    return SealRequest(
        session_id=session_id,
        committed_seq_start=1,
        committed_seq_end=end,
        transform_version=transform,
        source_spec=source_spec,
        calendar_spec=calendar,
        asset_class=asset_class,
        volume_unit=volume_unit,
        turnover_unit=turnover_unit,
    )


def committed_session(
    store,
    n: int = 6,
    source_spec: str = SOURCE_SPEC,
    calendar: str = "Asia/Shanghai",
    instrument: str = "IF2403.CFFEX",
) -> str:
    session = create_session(store, source_spec, calendar)
    for i in range(n):
        session.admit(tick(BASE + i * 30_000_000_000, 100 + i * 10, 1000 + i * 100, instrument=instrument))
    drain(session, n)
    result = session.close_at_cutoff(timeout=5.0)
    assert result.state.value == "CLOSED"
    session.close()
    return session.session_id


# -- range safety ------------------------------------------------------------


def test_plan_seal_rejects_uncommitted_range(store) -> None:
    session = create_session(store, SOURCE_SPEC, "Asia/Shanghai")
    session.admit(tick(BASE, 100, 1000))
    drain(session, 1)
    session.close()  # OPEN, one committed
    with pytest.raises(SealError, match="exceeds committed watermark"):
        plan_seal(store, make_request(session.session_id, end=5))
    with pytest.raises(SealError, match="empty seal range"):
        plan_seal(store, make_request(session.session_id, end=0))


def test_plan_seal_rejects_unknown_session_typed(store) -> None:
    with pytest.raises(SealError, match="unknown journal session"):
        plan_seal(store, make_request("sess-missing", end=2))


# -- F1: partial tail bars are excluded from canonical publication -----------


def test_seal_publishes_ticks_and_evidenced_bars_only(store) -> None:
    session_id = committed_session(store, n=6)
    receipt = seal(store, make_request(session_id, end=6))
    assert receipt.session_id == session_id
    assert receipt.input_events == 6
    # 6 ticks + 2 minute bars: minutes 0 and 1 have later-event completion
    # evidence; the tail minute 2 is PARTIAL (closed mid-minute) and is
    # excluded from canonical publication.
    assert receipt.accepted_rows == 6 + 2
    assert receipt.dataset_id is not None
    assert len(receipt.partitions) == 2  # ticks partition + bars partition
    assert not receipt.idempotent_replay
    assert "sealed [1, 6]" in receipt.detail


def test_f1_seal_excludes_partial_tail_but_keeps_all_ticks(store) -> None:
    """SYNTHETIC/OFFLINE: freeze + query back proves the published shape."""
    session_id = committed_session(store, n=6)
    request = make_request(session_id, end=6)
    receipt = seal(store, request)

    ticks_ds = compute_dataset_id(_spec(request, RecordKind.TICKS, Interval.M1))
    bars_ds = compute_dataset_id(_spec(request, RecordKind.BARS, Interval.M1))
    assert receipt.dataset_id == ticks_ds

    snap = freeze(
        store,
        SnapshotRequest(
            selections=(
                Selection(ticks_ds, "*"),
                Selection(bars_ds, "*"),
            ),
            required_fields=("open", "high", "low", "close", "volume"),
        ),
    )
    reader = open_snapshot(store, snap.snapshot_id)
    try:
        bar_rows = [
            r
            for b in reader.bars(bars_ds)
            for r in b.to_pylist()
        ]
        tick_rows = [r for b in reader.ticks(ticks_ds) for r in b.to_pylist()]
    finally:
        reader.close()

    assert len(tick_rows) == 6  # committed ticks always preserved
    assert len(bar_rows) == 2  # evidenced minutes only; partial tail excluded
    m0 = BASE - (BASE % NS_MINUTE)
    starts = {r["bar_start"] for r in bar_rows}
    assert starts == {m0, m0 + NS_MINUTE}
    assert m0 + 2 * NS_MINUTE not in starts  # the mid-minute-stopped tail
    for row in bar_rows:
        assert STATUS_PARTIAL not in (row["extensions_json"] or "")


def test_seal_repeat_is_idempotent_same_identity(store) -> None:
    session_id = committed_session(store, n=4)
    first = seal(store, make_request(session_id, end=4))
    second = seal(store, make_request(session_id, end=4))
    assert second.idempotent_replay
    assert first.seal_id == second.seal_id
    assert first.dataset_id == second.dataset_id
    assert first.accepted_rows == second.accepted_rows
    assert first.partitions == second.partitions


def test_seal_changed_transform_new_identity(store) -> None:
    session_id = committed_session(store, n=4)
    first = seal(store, make_request(session_id, end=4, transform="t0"))
    changed = seal(store, make_request(session_id, end=4, transform="t1"))
    assert first.dataset_id != changed.dataset_id
    assert not changed.idempotent_replay


# -- F2: range extension extends one dataset through revisions ---------------


def test_f2_range_extension_same_dataset_new_revision_with_lineage(store) -> None:
    """The original 02H repro_seal_identity scenario, corrected.

    Sealing [1,3] then the extended range [1,6] of the SAME session must
    prove REAL lineage, not merely different hashes: same dataset ids, the
    extension publishes as a NEW revision whose parent is the previous
    head, already-sealed ticks dedup, and the effective partition manifest
    is complete (all 6 ticks queryable after the extension).
    """

    session_id = committed_session(store, n=6)
    request_small = make_request(session_id, end=3)
    request_full = make_request(session_id, end=6)

    receipt1 = seal(store, request_small)
    receipt2 = seal(store, request_full)

    # Stable semantic dataset identity across the range extension.
    assert receipt2.dataset_id == receipt1.dataset_id
    assert not receipt2.idempotent_replay  # different runtime idempotency key
    assert seal_idempotency_key(request_small, "ticks") != seal_idempotency_key(
        request_full, "ticks"
    )

    ticks1, bars1 = receipt1.partitions
    ticks2, bars2 = receipt2.partitions

    # New revisions chain onto the previous partition heads (parent linkage).
    assert ticks2.base_revision == ticks1.revision_id
    assert bars2.base_revision == bars1.revision_id

    # Old ticks deduped (3 duplicates), 3 new ticks accepted.
    batch2 = store.catalog.find_batch_by_key(seal_idempotency_key(request_full, "ticks"))
    assert batch2 is not None
    assert int(batch2["duplicate_rows"]) == 3
    assert int(batch2["accepted_rows"]) == 3

    # Complete effective partition manifests: the ticks revision now holds
    # the full committed range; bars hold the evidenced minutes.
    rev_ticks2 = store.catalog.get_revision(ticks2.revision_id)
    rev_bars2 = store.catalog.get_revision(bars2.revision_id)
    assert rev_ticks2 is not None and int(rev_ticks2["rows"]) == 6
    assert rev_ticks2["parent_revision"] == ticks1.revision_id
    assert rev_bars2 is not None and int(rev_bars2["rows"]) == 2

    # Query back through the public reader: the effective partition state.
    ticks_ds = compute_dataset_id(
        _spec(request_full, RecordKind.TICKS, Interval.M1)
    )
    bars_ds = compute_dataset_id(_spec(request_full, RecordKind.BARS, Interval.M1))
    snap = freeze(
        store,
        SnapshotRequest(
            selections=(Selection(ticks_ds, "*"), Selection(bars_ds, "*")),
            required_fields=(),
        ),
    )
    reader = open_snapshot(store, snap.snapshot_id)
    try:
        tick_rows = [r for b in reader.ticks(ticks_ds) for r in b.to_pylist()]
        bar_rows = [r for b in reader.bars(bars_ds) for r in b.to_pylist()]
    finally:
        reader.close()
    assert sorted(r["seq"] for r in tick_rows) == [1, 2, 3, 4, 5, 6]
    assert len(bar_rows) == 2


def test_seal_subset_after_full_dedups(store) -> None:
    """Sealing a subset range AFTER the full range never forks or rewinds:
    same dataset, all rows dedup, a no-content revision is chained."""
    session_id = committed_session(store, n=6)
    full = seal(store, make_request(session_id, end=6))
    subset = seal(store, make_request(session_id, end=3))
    assert subset.dataset_id == full.dataset_id
    ticks1, _ = full.partitions
    ticks2, _ = subset.partitions
    assert ticks2.base_revision == ticks1.revision_id
    batch = store.catalog.find_batch_by_key(
        seal_idempotency_key(make_request(session_id, end=3), "ticks")
    )
    assert int(batch["duplicate_rows"]) == 3
    assert int(batch["accepted_rows"]) == 0


def test_seal_crash_recovery_resumes(store, monkeypatch) -> None:
    """Interrupt the bars publish after the ticks publish landed; the standard
    recovery sweep must let a repeat seal converge without duplicating ticks."""
    session_id = committed_session(store, n=4)
    import research_store.sealing as sealing_mod

    calls = {"n": 0}
    real_publish = sealing_mod._publish

    def flaky_publish(store_, request, record_kind, interval, rows, partition):
        calls["n"] += 1
        if record_kind is sealing_mod.RecordKind.BARS and calls["n"] <= 2:
            raise RuntimeError("simulated crash during bars publish")
        return real_publish(store_, request, record_kind, interval, rows, partition)

    monkeypatch.setattr(sealing_mod, "_publish", flaky_publish)
    with pytest.raises(RuntimeError, match="simulated crash"):
        seal(store, make_request(session_id, end=4))
    monkeypatch.setattr(sealing_mod, "_publish", real_publish)

    # Repeat seal: ticks replay idempotently, bars publish fresh. n=4 has
    # 1 evidenced bar (minute 0); its tail minute 1 stays PARTIAL/excluded.
    receipt = seal(store, make_request(session_id, end=4))
    assert receipt.input_events == 4
    assert receipt.accepted_rows == 4 + 1


def test_sealed_ticks_preserve_session_seq_identity(store) -> None:
    session_id = committed_session(store, n=3)
    request = make_request(session_id, end=3)
    seal(store, request)
    ticks_dataset = compute_dataset_id(
        _spec(request, RecordKind.TICKS, Interval.M1)
    )
    snap = freeze(
        store,
        SnapshotRequest(
            selections=(Selection(ticks_dataset, "*"),),
            required_fields=(),
        ),
    )
    reader = open_snapshot(store, snap.snapshot_id)
    try:
        ticks = list(reader.ticks(ticks_dataset))
    finally:
        reader.close()
    import pyarrow as pa

    table = pa.Table.from_batches(ticks)
    sessions = table.column("session_id").to_pylist()
    seqs = table.column("seq").to_pylist()
    assert set(sessions) == {session_id}
    assert sorted(seqs) == [1, 2, 3]


# -- recording02IA: calendar truthfulness + honest tick materialization ------


def test_02ia_tick_zero_preserved_and_source_trading_date_roundtrips(store) -> None:
    """SYNTHETIC FIXTURE (not gateway evidence). Verifies, on sealed tick
    rows read back through the public reader:

    - a genuine numeric zero ``last_price`` is preserved (never replaced by
      a sibling ``price`` field or nulled by truthiness);
    - an explicitly source-evidenced ``trading_date`` is published with
      provenance in ``field_quality``;
    - a tick without source date evidence keeps trading_date NULL with the
      explicit unknown note (a timezone-only calendar_spec proves nothing).
    """

    session = create_session(store, "futures:night-sim", "Asia/Shanghai")
    friday_night_ns = 1704459600 * 1_000_000_000  # 2024-01-05 21:00 CST
    session.admit(
        JournalEvent(
            kind="tick",
            instrument="A2405.DCE",
            event_ts_ns=friday_night_ns,
            source_event_id="syn-1",
            payload={
                "last_price": 0.0,  # genuine zero — must survive verbatim
                "price": 99.0,      # must NOT replace the real zero
                "volume": 10,
                "turnover": 100.0,
                "trading_date": "2024-01-08",  # source vouches: Monday
            },
        )
    )
    session.admit(
        JournalEvent(
            kind="tick",
            instrument="A2405.DCE",
            event_ts_ns=friday_night_ns + 1_000_000_000,
            source_event_id="syn-2",
            payload={"last_price": 1.0, "volume": 11, "turnover": 110.0},
        )
    )
    drain(session, 2)
    assert session.close_at_cutoff(timeout=5.0).state.value == "CLOSED"
    session.close()

    request = make_request(
        session.session_id,
        end=2,
        source_spec="futures:night-sim",
    )
    seal(store, request)
    ticks_ds = compute_dataset_id(_spec(request, RecordKind.TICKS, Interval.M1))
    snap = freeze(
        store,
        SnapshotRequest(
            selections=(Selection(ticks_ds, "*"),),
            required_fields=(),
        ),
    )
    reader = open_snapshot(store, snap.snapshot_id)
    try:
        rows = [r for b in reader.ticks(ticks_ds) for r in b.to_pylist()]
    finally:
        reader.close()
    by_seq = {r["seq"]: r for r in rows}
    assert set(by_seq) == {1, 2}

    zero_row = by_seq[1]
    assert zero_row["last_price"] == 0.0  # genuine zero preserved verbatim
    from datetime import date as _date

    assert zero_row["trading_date"] == _date(2024, 1, 8)
    assert "source payload evidence" in (zero_row["field_quality"] or "")
    assert zero_row["completeness"] == "complete"

    unknown_row = by_seq[2]
    assert unknown_row["trading_date"] is None
    assert "does not establish a trading day" in (unknown_row["field_quality"] or "")
    assert unknown_row["completeness"] == "complete"


def test_02ia_invalid_source_trading_date_makes_tick_partial(store) -> None:
    """A source that CLAIMS a trading_date but sends garbage keeps the NULL
    date with the claim preserved in field_quality and marks the row partial
    (an invalid claim is a row-level quality issue, unlike plain absence)."""
    session = create_session(store, "futures:bad-date", "Asia/Shanghai")
    session.admit(
        JournalEvent(
            kind="tick",
            instrument="A2405.DCE",
            event_ts_ns=BASE,
            source_event_id="syn-3",
            payload={"last_price": 1.0, "trading_date": "08/01/2024"},
        )
    )
    drain(session, 1)
    assert session.close_at_cutoff(timeout=5.0).state.value == "CLOSED"
    session.close()

    request = make_request(session.session_id, end=1, source_spec="futures:bad-date")
    seal(store, request)
    ticks_ds = compute_dataset_id(_spec(request, RecordKind.TICKS, Interval.M1))
    snap = freeze(
        store,
        SnapshotRequest(selections=(Selection(ticks_ds, "*"),), required_fields=()),
    )
    reader = open_snapshot(store, snap.snapshot_id)
    try:
        rows = [r for b in reader.ticks(ticks_ds) for r in b.to_pylist()]
    finally:
        reader.close()
    assert len(rows) == 1
    row = rows[0]
    assert row["trading_date"] is None
    assert "invalid source trading_date" in (row["field_quality"] or "")
    assert row["completeness"] == "partial"


def test_02ia_unknown_event_time_tick_excluded_never_epoch_zero(store) -> None:
    """A committed tick without ``event_ts_ns`` cannot be published honestly
    (canonical ts is NOT NULL). It must be EXCLUDED from the seal with an
    explicit count in the receipt detail — never fabricated as ts=0. The raw
    row stays preserved in the journal."""
    session = create_session(store, "futures:no-ts", "Asia/Shanghai")
    session.admit(tick(BASE, 100, 1000))
    session.admit(
        JournalEvent(
            kind="tick",
            instrument="IF2403.CFFEX",
            event_ts_ns=None,  # source never supplied an event time
            source_event_id="syn-no-ts",
            payload={"last_price": 1.0},
        )
    )
    drain(session, 2)
    assert session.close_at_cutoff(timeout=5.0).state.value == "CLOSED"
    session.close()

    request = make_request(session.session_id, end=2, source_spec="futures:no-ts")
    receipt = seal(store, request)
    assert "excluded 1 tick(s) with unknown event time" in receipt.detail

    ticks_ds = compute_dataset_id(_spec(request, RecordKind.TICKS, Interval.M1))
    snap = freeze(
        store,
        SnapshotRequest(selections=(Selection(ticks_ds, "*"),), required_fields=()),
    )
    reader = open_snapshot(store, snap.snapshot_id)
    try:
        rows = [r for b in reader.ticks(ticks_ds) for r in b.to_pylist()]
    finally:
        reader.close()
    assert sorted(r["seq"] for r in rows) == [1]
    assert rows[0]["ts"] == BASE  # no epoch-zero row exists
    assert rows[0]["ts"] != 0

    # Raw journal retention: the unknown-time event is still committed.
    import sqlite3

    conn = sqlite3.connect(str(store.path.journals / f"{session.session_id}.sqlite"))
    try:
        raw = conn.execute(
            "SELECT event_ts_ns, seq FROM events WHERE seq=2"
        ).fetchone()
    finally:
        conn.close()
    assert raw == (None, 2)


# -- F4: explicit validated asset/source/unit semantics ----------------------


def test_f4_futures_and_etf_sources_have_distinct_identity(store) -> None:
    """Same events, different declared source semantics → different datasets.

    FUTURES volume is contracts; ETF volume is shares/units — the units and
    asset class participate in the semantic identity so contract volume can
    never silently merge with share volume.
    """

    sid_fut = committed_session(store, n=3, source_spec="futures:sim@v1")
    receipt_fut = seal(
        store,
        make_request(
            sid_fut,
            end=3,
            source_spec="futures:sim@v1",
            asset_class=AssetClass.FUTURES,
            volume_unit="contracts",
            turnover_unit="CNY",
        ),
    )
    sid_etf = committed_session(
        store, n=3, source_spec="etf:sim@v1", instrument="510300.SSE"
    )
    receipt_etf = seal(
        store,
        make_request(
            sid_etf,
            end=3,
            source_spec="etf:sim@v1",
            asset_class=AssetClass.ETF,
            volume_unit="shares",
            turnover_unit="CNY",
        ),
    )
    assert receipt_fut.dataset_id != receipt_etf.dataset_id

    # The declared kind also pins identity even at equal units: a futures
    # source and an equity source with identical names never share a dataset.
    # The declared kind also pins identity even at equal units: a futures
    # source and an equity source with identical names never share a dataset.
    sid_eq = committed_session(store, n=3, source_spec="equity:sim@v1")
    receipt_eq = seal(
        store,
        make_request(
            sid_eq,
            end=3,
            source_spec="equity:sim@v1",
            asset_class=AssetClass.EQUITY,
            volume_unit="shares",
            turnover_unit="CNY",
        ),
    )
    assert receipt_eq.dataset_id != receipt_etf.dataset_id


def test_f4_inconsistent_asset_class_refused(store) -> None:
    """A futures-declared source must not be relabelled EQUITY (and vice
    versa: stock volume must never be tagged as contracts)."""
    sid = committed_session(store, n=2)
    with pytest.raises(SealError, match="not consistent"):
        plan_seal(
            store,
            make_request(
                sid, end=2, asset_class=AssetClass.EQUITY, volume_unit="shares"
            ),
        )


def test_f4_units_not_valid_for_asset_class_refused(store) -> None:
    sid = committed_session(store, n=2)
    with pytest.raises(SealError, match="volume unit 'shares' is not valid"):
        plan_seal(store, make_request(sid, end=2, volume_unit="shares"))
    with pytest.raises(SealError, match="turnover unit 'lots' is not valid"):
        plan_seal(store, make_request(sid, end=2, turnover_unit="lots"))


def test_f4_source_spec_mismatch_with_session_refused(store) -> None:
    sid = committed_session(store, n=2)
    with pytest.raises(SealError, match="does not match"):
        plan_seal(store, make_request(sid, end=2, source_spec="futures:other"))


def test_f4_untyped_source_seals_honest_unknown(store) -> None:
    """A bare source name has unknown semantics: the honest OTHER/unknown
    combination is accepted and published visibly — never guessed FUTURES."""
    sid = committed_session(store, n=2, source_spec="sim-src")
    # Dataclass defaults: omitting the semantics fields means honest OTHER +
    # unknown units, visible in the published dataset identity.
    request = SealRequest(
        session_id=sid,
        committed_seq_start=1,
        committed_seq_end=2,
        transform_version="t0",
        source_spec="sim-src",
        calendar_spec="Asia/Shanghai",
    )
    assert request.asset_class is AssetClass.OTHER
    assert request.volume_unit == "unknown"
    assert request.turnover_unit == "unknown"
    receipt = seal(store, request)
    spec = _spec(request, RecordKind.TICKS, Interval.M1)
    assert spec.asset_class is AssetClass.OTHER
    assert spec.volume_unit == "unknown"
    assert spec.turnover_unit == "unknown"
    assert receipt.dataset_id == compute_dataset_id(spec)


def test_f4_source_and_calendar_spec_validation_helpers() -> None:
    # source_spec grammar: bare name, kind:name, kind:name@version.
    parsed = validate_source_spec("futures:ctp-feed@v2")
    assert parsed.kind == "futures"
    assert parsed.name == "ctp-feed"
    assert parsed.version == "v2"
    assert AssetClass.FUTURES in parsed.allowed_asset_classes
    assert AssetClass.EQUITY not in parsed.allowed_asset_classes
    bare = validate_source_spec("sim-src")
    assert bare.kind == "unknown"
    assert len(bare.allowed_asset_classes) == len(AssetClass)
    with pytest.raises(SealError, match="unsupported source_spec"):
        validate_source_spec("bogus-kind:name")
    with pytest.raises(SealError, match="unsupported source_spec"):
        validate_source_spec("futures:")
    with pytest.raises(SealError, match="unsupported source_spec"):
        validate_source_spec("")

    # calendar_spec grammar: empty = no evidence; bare IANA = v1 shorthand;
    # "tz:<IANA>" = explicit; anything unresolvable is refused.
    assert validate_calendar_spec("") is None
    assert validate_calendar_spec("Asia/Shanghai") == "Asia/Shanghai"
    assert validate_calendar_spec("tz:Asia/Shanghai") == "Asia/Shanghai"
    with pytest.raises(SealError, match="unsupported calendar_spec"):
        validate_calendar_spec("CN.FUTURES.DAY")
    with pytest.raises(SealError, match="unsupported calendar_spec"):
        validate_calendar_spec("Mars/Base-1")


def test_f4_calendar_specs_at_seal(store) -> None:
    sid = committed_session(store, n=2)
    # Explicit "tz:" form is accepted.
    plan = plan_seal(store, make_request(sid, end=2, calendar="tz:Asia/Shanghai"))
    assert plan.event_count == 2
    # Empty calendar = no evidence, seals honestly (trading_date stays NULL).
    sid_nocal = committed_session(
        store, n=2, source_spec="futures:no-cal", calendar=""
    )
    request = make_request(sid_nocal, end=2, source_spec="futures:no-cal", calendar="")
    receipt = seal(store, request)
    assert receipt.accepted_rows == 2  # ticks only; both bars stay partial
    # A request calendar that disagrees with the stored one is refused.
    with pytest.raises(SealError, match="does not match"):
        plan_seal(store, make_request(sid_nocal, end=2, source_spec="futures:no-cal"))
    # A named session calendar this core cannot resolve is an explicit error.
    with pytest.raises(SealError, match="unsupported calendar_spec"):
        plan_seal(store, make_request(sid, end=2, calendar="CN.FUTURES.DAY"))
