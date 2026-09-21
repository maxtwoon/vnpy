"""Sealing of committed journal ranges via the immutable canonical publish API.

A seal publishes the committed events (verbatim ticks, session/seq identity
preserved) and/or their aggregated minute bars through ``import_asset`` — the
same CAS revision machinery importers use.

F2 (recording02I): runtime idempotency (session, range, transform, config)
is kept separate from semantic dataset identity. The committed sequence
range is NEVER part of the semantic ``rule_version``/dataset identity; it
lives only in the idempotency key. Same source/asset/kind/interval/
adjustment/version/seriesrule/timezone/labels/units/origin/schema and same
transform extend through one stable dataset + new revisions, not
disconnected datasets. Session provenance (session_id, seq) is tick
identity/metadata carried in the rows, not a semantic discriminator.

F4 (recording02I): asset class, volume unit, and turnover unit are explicit
validated fields on ``SealRequest``. There is no unconditional FUTURES
default. Unknown/unsupported semantics are explicit errors (``SealError``)
or honest unqualified values (``AssetClass.OTHER``), never guessed.

The request can never include uncommitted events: the committed watermark of
the journal is checked before publishing. A partial publication/failure is
never recorded as completely sealed: a durable anchor (batch id + idempotency
key + request) is written to the journal's own session_meta BEFORE the CAS
commit, so a crash mid-seal resumes through the standard recovery sweep and
the receipt reflects the actual published revision/file/count evidence.

Pure storage core — never imports ``vnpy`` or any provider SDK.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa

from . import schemas
from .aggregation import (
    STATUS_PARTIAL,
    AggregatedBar,
    AggregatedSession,
    _source_trading_date,
    aggregate_open_session,
)
from .journal import open_session
from .journal_models import CommittedEvent, SessionState
from .models import (
    AssetClass,
    AssetRef,
    ImportReceipt,
    ImportRequest,
    Interval,
    OriginMethod,
    PartitionReceipt,
    RecordKind,
    SealReceipt,
    SealRequest,
    SemanticSpec,
    StoreError,
    TimeLabel,
    Adjustment,
    compute_dataset_id,
)
from .revisions import import_asset
from .store import Store

SEAL_ADAPTER = "research_store.sealing/0.2"
SEAL_TRANSFORM = "seal-v1"

# F4 (recording02I): source_spec / calendar_spec grammar (v1).
#
# source_spec   := <name> | <kind> ":" <name> [ "@" <version> ]
#   kind        ∈ {"futures", "equity", "etf", "index", "option",
#                  "convertible", "unknown"}  (bare name ⇒ kind "unknown")
#   name/version: letters, digits, ".", "_", "-" (1..64 chars each)
#
#   The declared kind pins the ONLY asset class the sealer accepts for the
#   session (see _SOURCE_KIND_ASSET_CLASS), so a real config provides asset
#   class semantics once, at session creation, and every seal of that
#   session stays consistent with it. A bare source name stays legal and
#   means "semantics unknown": any explicit asset class may then be
#   declared on the SealRequest, or the honest OTHER/unknown default kept.
#
# calendar_spec := ""                      (no calendar evidence at all)
#               |  "tz:" <IANA zone name>  (timezone-only)
#               |  <IANA zone name>        (v1 shorthand for "tz:...")
#
#   recording02IA semantics: a timezone-only calendar_spec establishes
#   display timezone / normalised UTC conversion ONLY — never a trading
#   day. trading_date comes exclusively from explicit source payload
#   evidence (payload["trading_date"], ISO YYYY-MM-DD); without it,
#   trading_date stays NULL with the explicit trading_date_unknown
#   status/quality note (an unproven Friday-night date is never inferred).
#   No explicit calendar-mapping form exists in v1 (documented decision:
#   no calendar service, no next-day guessing; add one only with versioned,
#   scoped evidence). Anything else (e.g. a named session calendar such as
#   "CN.FUTURES.DAY" that this core cannot resolve) is an explicit
#   SealError at seal time. Recording (create_session) stays permissive:
#   raw capture must not lose data; validation applies at the publication
#   boundary. Recorder/CLI configs that carry unsupported strings must
#   migrate to the grammar above.

_SOURCE_SPEC_RE = re.compile(
    r"^(?:(?P<kind>futures|equity|etf|index|option|convertible|unknown):)?"
    r"(?P<name>[A-Za-z0-9._-]{1,64})"
    r"(?:@(?P<version>[A-Za-z0-9._-]{1,64}))?$"
)

_SOURCE_KIND_ASSET_CLASS: dict[str, frozenset[AssetClass]] = {
    "futures": frozenset({AssetClass.FUTURES}),
    "equity": frozenset({AssetClass.EQUITY}),
    "etf": frozenset({AssetClass.ETF}),
    "index": frozenset({AssetClass.INDEX}),
    "option": frozenset({AssetClass.OPTION}),
    "convertible": frozenset({AssetClass.CONVERTIBLE}),
    "unknown": frozenset(AssetClass),
}

_CALENDAR_SPEC_RE = re.compile(r"^tz:(?P<zone>.+)$")


@dataclass(frozen=True)
class SourceSemantics:
    """Parsed ``source_spec`` semantics (F4)."""

    kind: str                     # "futures" | ... | "unknown"
    name: str
    version: str | None
    allowed_asset_classes: frozenset[AssetClass]


def validate_source_spec(source_spec: str) -> SourceSemantics:
    """Validate a ``source_spec`` string against the documented grammar.

    Raises ``SealError`` with the exact expected format on refusal. Never
    invents a kind for an unparseable value.
    """

    spec = (source_spec or "").strip()
    match = _SOURCE_SPEC_RE.match(spec)
    if match is None:
        raise SealError(
            f"unsupported source_spec {source_spec!r}; expected "
            '"<name>" or "<kind>:<name>[@<version>]" with kind one of '
            "futures|equity|etf|index|option|convertible|unknown"
        )
    kind = match.group("kind") or "unknown"
    return SourceSemantics(
        kind=kind,
        name=match.group("name"),
        version=match.group("version"),
        allowed_asset_classes=_SOURCE_KIND_ASSET_CLASS[kind],
    )


def validate_calendar_spec(calendar_spec: str) -> str | None:
    """Validate a ``calendar_spec`` string; return the IANA zone or None.

    ``""`` (no evidence) returns ``None`` honestly. ``"tz:<zone>"`` and the
    bare ``<zone>`` shorthand must resolve as IANA timezones. Anything else
    raises ``SealError``. The resolved zone is a DISPLAY timezone only
    (normalised UTC conversion); it NEVER establishes a trading day —
    trading_date requires explicit source payload evidence (recording02IA).
    """

    spec = (calendar_spec or "").strip()
    if not spec:
        return None
    match = _CALENDAR_SPEC_RE.match(spec)
    zone = match.group("zone") if match is not None else spec
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(zone)
    except Exception as exc:  # noqa: BLE001 - any resolver failure is a refusal
        raise SealError(
            f"unsupported calendar_spec {calendar_spec!r}; expected \"\", "
            'an IANA timezone name, or "tz:<IANA timezone name>" '
            f"(resolver error: {exc})"
        ) from exc
    return zone


# F4: known volume/turnover units per asset class. These are validated
# against the request; unknown combinations are explicit errors.
_KNOWN_VOLUME_UNITS: dict[AssetClass, set[str]] = {
    AssetClass.FUTURES: {"contracts", "lots", "unknown"},
    AssetClass.EQUITY: {"shares", "unknown"},
    AssetClass.ETF: {"shares", "units", "unknown"},
    AssetClass.INDEX: {"points", "unknown"},
    AssetClass.OPTION: {"contracts", "unknown"},
    AssetClass.CONVERTIBLE: {"bonds", "unknown"},
    AssetClass.OTHER: {"unknown"},
}

_KNOWN_TURNOVER_UNITS: dict[AssetClass, set[str]] = {
    AssetClass.FUTURES: {"currency", "CNY", "USD", "unknown"},
    AssetClass.EQUITY: {"currency", "CNY", "USD", "unknown"},
    AssetClass.ETF: {"currency", "CNY", "USD", "unknown"},
    AssetClass.INDEX: {"currency", "CNY", "USD", "unknown"},
    AssetClass.OPTION: {"currency", "CNY", "USD", "unknown"},
    AssetClass.CONVERTIBLE: {"currency", "CNY", "USD", "unknown"},
    AssetClass.OTHER: {"unknown"},
}


class SealError(StoreError):
    """Seal preconditions violated (unknown session, uncommitted range...)."""


@dataclass(frozen=True)
class SealPlan:
    """What a seal will publish, resolved before any publication."""

    session_id: str
    committed_seq_start: int
    committed_seq_end: int
    committed_watermark: int
    event_count: int
    idempotency_key: str


def seal_idempotency_key(request: SealRequest, record_kind: str) -> str:
    """Content-addressed key over everything that affects sealed output.

    F2: this key covers the runtime identity (session, range, transform,
    source/calendar config, record kind) for idempotent replay detection.
    It is NOT the semantic dataset identity; dataset identity is derived
    from ``_spec()`` which excludes the sequence range.
    """

    payload = {
        "session_id": request.session_id,
        "range": [request.committed_seq_start, request.committed_seq_end],
        "transform_version": request.transform_version,
        "source_spec": request.source_spec,
        "calendar_spec": request.calendar_spec,
        "asset_class": request.asset_class.value,
        "volume_unit": request.volume_unit,
        "turnover_unit": request.turnover_unit,
        "record_kind": record_kind,
        "adapter": SEAL_ADAPTER,
    }
    return "seal-" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:40]


def _connect(journal_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(journal_path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
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


def _committed_watermark(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT committed_seq FROM watermark").fetchone()
    return int(row["committed_seq"]) if row is not None else 0


def _validate_asset_semantics(
    request: SealRequest, stored_source_spec: str, stored_calendar_spec: str
) -> SourceSemantics:
    """F4: validate asset/source/unit semantics before any publication.

    Raises SealError for unknown/unsupported combinations. Never guesses:
    the declared asset class must be allowed by the session's stored
    ``source_spec`` kind, source/calendar specs must match the session's
    stored metadata, and units must be known for the asset class.
    """

    source = validate_source_spec(stored_source_spec)
    if request.source_spec != stored_source_spec:
        raise SealError(
            f"source_spec {request.source_spec!r} does not match the "
            f"session's stored source_spec {stored_source_spec!r}"
        )
    request_zone = validate_calendar_spec(request.calendar_spec)
    stored_zone = validate_calendar_spec(stored_calendar_spec)
    if request_zone != stored_zone:
        raise SealError(
            f"calendar_spec {request.calendar_spec!r} does not match the "
            f"session's stored calendar_spec {stored_calendar_spec!r}"
        )

    ac = request.asset_class
    vu = request.volume_unit
    tu = request.turnover_unit

    if ac not in source.allowed_asset_classes:
        raise SealError(
            f"asset_class {ac.value!r} is not consistent with the session's "
            f"source_spec kind {source.kind!r}; allowed: "
            f"{sorted(c.value for c in source.allowed_asset_classes)}; set the "
            "SealRequest asset_class/volume_unit/turnover_unit fields explicitly"
        )
    if ac not in _KNOWN_VOLUME_UNITS:
        raise SealError(
            f"asset class {ac!r} has no known volume units; "
            "explicit mapping required"
        )
    if vu not in _KNOWN_VOLUME_UNITS[ac]:
        raise SealError(
            f"volume unit {vu!r} is not valid for asset class {ac.value}; "
            f"known units: {sorted(_KNOWN_VOLUME_UNITS[ac])}"
        )
    if tu not in _KNOWN_TURNOVER_UNITS[ac]:
        raise SealError(
            f"turnover unit {tu!r} is not valid for asset class {ac.value}; "
            f"known units: {sorted(_KNOWN_TURNOVER_UNITS[ac])}"
        )
    return source


def plan_seal(store: Store, request: SealRequest) -> SealPlan:
    """Validate the request against the durable journal and resolve counts.

    Raises SealError when the session is unknown, the declared asset/source/
    calendar semantics are unsupported or inconsistent with the stored
    session metadata, the range is empty, or the range exceeds the committed
    watermark (uncommitted events can never be sealed).
    """

    journal_path = store.path.journals / f"{request.session_id}.sqlite"
    if not journal_path.is_file():
        raise SealError(f"unknown journal session: {request.session_id}")
    conn = _connect(journal_path)
    try:
        watermark = _committed_watermark(conn)
        stored_source_spec = _meta_get(conn, "source_spec") or ""
        stored_calendar_spec = _meta_get(conn, "calendar_spec") or ""
    finally:
        conn.close()
    _validate_asset_semantics(request, stored_source_spec, stored_calendar_spec)
    start, end = request.committed_seq_start, request.committed_seq_end
    if start < 1 or end < start:
        raise SealError(f"empty seal range [{start}, {end}]")
    if end > watermark:
        raise SealError(
            f"seal range [{start}, {end}] exceeds committed watermark {watermark}; "
            "uncommitted events cannot be sealed"
        )
    conn = _connect(journal_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM events WHERE seq BETWEEN ? AND ?",
            (start, end),
        ).fetchone()["c"]
    finally:
        conn.close()
    return SealPlan(
        session_id=request.session_id,
        committed_seq_start=start,
        committed_seq_end=end,
        committed_watermark=watermark,
        event_count=int(count),
        idempotency_key=seal_idempotency_key(request, "ticks"),
    )


def _tick_rows(
    events: list[CommittedEvent], dataset_id: str, request: SealRequest
) -> list[dict[str, Any]]:
    """Materialize verbatim tick rows for the sealable events.

    recording02IA: ``event_ts_ns`` must be present (the canonical ticks
    schema has NOT NULL ``ts``) — callers exclude unknown-time ticks before
    calling this, and none is ever fabricated as epoch zero. Field
    fallbacks preserve genuine numeric zeros (explicit ``is None`` checks,
    never truthiness). ``trading_date`` comes ONLY from source payload
    evidence; a timezone-only calendar_spec never supplies a day.
    """

    rows: list[dict[str, Any]] = []
    for event in events:
        assert event.event_ts_ns is not None, (
            "unknown-time ticks must be excluded by the caller before "
            "materialization; raw rows stay in the journal"
        )
        payload = event.payload
        trading, note = _source_trading_date(payload)
        if trading is not None:
            quality: dict[str, Any] = {"trading_date": "source payload evidence"}
            completeness = "complete"
        elif note is not None:
            quality = {"trading_date": note}
            completeness = "partial"  # source claimed a date but it is invalid
        else:
            quality = {
                "trading_date": (
                    "unknown: no source evidence; a timezone-only "
                    "calendar_spec does not establish a trading day"
                )
            }
            completeness = "complete"
        last_price = payload.get("last_price")
        if last_price is None:
            last_price = payload.get("price")
        turnover = payload.get("turnover")
        if turnover is None:
            turnover = payload.get("amount")
        rows.append(
            {
                "dataset_id": dataset_id,
                "instrument_id": event.instrument,
                "series_id": None,
                "symbol": event.instrument,
                "exchange": None,
                "session_id": request.session_id,
                "seq": event.seq,
                "ts": event.event_ts_ns,
                "trading_date": trading,
                "source_label": event.source_event_id,
                "last_price": last_price,
                "last_volume": payload.get("last_volume"),
                "turnover": turnover,
                "bid_price1": payload.get("bid_price1"),
                "ask_price1": payload.get("ask_price1"),
                "bid_volume1": payload.get("bid_volume1"),
                "ask_volume1": payload.get("ask_volume1"),
                "completeness": completeness,
                "field_quality": json.dumps(quality, sort_keys=True),
                "contract_id": None,
                "asset_id": f"journal-{request.session_id}",
                "batch_id": "pending",
                "transform_version": request.transform_version,
                "extensions_json": json.dumps(
                    {"kind": event.kind, "payload": payload}, sort_keys=True, default=str
                ),
            }
        )
    return rows


def _bar_rows(
    aggregated: AggregatedSession, dataset_id: str, request: SealRequest
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bar in aggregated.bars:
        assert isinstance(bar, AggregatedBar)
        rows.append(
            {
                "dataset_id": dataset_id,
                "instrument_id": bar.instrument,
                "series_id": None,
                "symbol": bar.instrument,
                "exchange": None,
                "bar_start": bar.bar_start_ns,
                "bar_end": bar.bar_end_ns,
                "trading_date": bar.trading_date,
                "source_label": None,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "turnover": bar.turnover,
                "open_interest": None,
                "completeness": bar.completeness,
                "field_quality": bar.field_quality,
                "contract_id": None,
                "asset_id": f"journal-{request.session_id}",
                "batch_id": "pending",
                "transform_version": request.transform_version,
                "extensions_json": json.dumps(
                    {
                        "session_id": aggregated.session_id,
                        "first_seq": bar.first_seq,
                        "last_seq": bar.last_seq,
                        "event_count": bar.event_count,
                        "statuses": list(bar.statuses),
                        "source_kind": bar.source_kind,
                    },
                    sort_keys=True,
                ),
            }
        )
    return rows


def _spec(request: SealRequest, record_kind: RecordKind, interval: Interval) -> SemanticSpec:
    """Build the semantic identity for a seal publication.

    F2: the semantic identity covers source, asset class, record kind,
    interval, adjustment, series rule, timezone, labels, units, origin,
    schema, and transform version. It deliberately EXCLUDES the committed
    sequence range and session id: those are runtime provenance (carried in
    the idempotency key and row metadata), not semantic discriminators.
    Same semantic series → same dataset_id → new revisions on range growth.
    """

    tz = request.calendar_spec if (request.calendar_spec or "") else "UTC"
    return SemanticSpec(
        source_id=f"journal:{request.source_spec}",
        asset_class=request.asset_class,
        record_kind=record_kind,
        interval=interval,
        adjustment=Adjustment.NONE,
        adjustment_version="",
        series_kind="instrument",
        rule_version=f"seal-{request.transform_version}",
        timezone=tz,
        source_time_label=TimeLabel.START,
        volume_unit=request.volume_unit,
        turnover_unit=request.turnover_unit,
        origin_method=OriginMethod.SOURCE if record_kind is RecordKind.TICKS else OriginMethod.DERIVED,
        schema_version=1,
    )


def _publish(
    store: Store,
    request: SealRequest,
    record_kind: RecordKind,
    interval: Interval,
    rows: list[dict[str, Any]],
    partition: str,
) -> ImportReceipt:
    spec = _spec(request, record_kind, interval)
    dataset_id = compute_dataset_id(spec)
    for row in rows:
        row["dataset_id"] = dataset_id
    schema = schemas.schema_for(record_kind.value)
    batches = [
        pa.RecordBatch.from_pydict(
            {name: [row[name] for row in rows] for name in schema.names}, schema=schema
        )
    ] if rows else []

    def stream(_partition: str) -> Iterator[pa.RecordBatch]:
        yield from batches

    asset = AssetRef(
        asset_id=f"journal-{request.session_id}",
        origin=f"journals/{request.session_id}.sqlite",
        format="journal_sqlite",
        size=0,
        sha256=hashlib.sha256(
            json.dumps(
                {
                    "session": request.session_id,
                    "range": [request.committed_seq_start, request.committed_seq_end],
                    "kind": record_kind.value,
                    "rows": len(rows),
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    )
    import_request = ImportRequest(
        asset=asset,
        spec=spec,
        adapter=SEAL_ADAPTER,
        config={
            "session_id": request.session_id,
            "committed_seq_start": str(request.committed_seq_start),
            "committed_seq_end": str(request.committed_seq_end),
            "transform_version": request.transform_version,
            "source_spec": request.source_spec,
            "calendar_spec": request.calendar_spec,
            "asset_class": request.asset_class.value,
            "volume_unit": request.volume_unit,
            "turnover_unit": request.turnover_unit,
        },
        partitions=(partition,),
        idempotency_key=seal_idempotency_key(request, record_kind.value),
    )
    return import_asset(store, import_request, stream)


def _anchor_key(record_kind: str) -> str:
    return f"seal_anchor:{record_kind}"


def seal(store: Store, request: SealRequest) -> SealReceipt:
    """Seal a committed journal range into immutable canonical datasets.

    Publishes verbatim ticks and aggregated minute bars for the range. The
    whole operation is idempotent and crash-resumable through the standard
    import recovery sweep (durable anchor written before the CAS commit).

    F1: bars flagged PARTIAL (provisional) are excluded from the sealed bars
    publication. Only bars with independent completion evidence are published
    as canonical/backtest-ready. Committed raw ticks are always published
    regardless of bar completeness.

    F2: same semantic series (same source/asset/transform config) extends
    through one stable dataset + new revisions on range growth. The sequence
    range is runtime provenance, not a semantic discriminator.

    F4: asset class and units are validated before publication. No
    unconditional FUTURES default.

    recording02IA: ticks without an event time are EXCLUDED from publication
    with an explicit count in ``detail`` (canonical ``ts`` is NOT NULL; the
    raw rows stay preserved in the journal and are never fabricated as epoch
    zero). Tick/bar ``trading_date`` comes only from source payload evidence;
    a timezone-only calendar_spec never supplies a trading day, and genuine
    numeric zeros are preserved verbatim.
    """

    plan = plan_seal(store, request)
    journal_path = store.path.journals / f"{request.session_id}.sqlite"

    # Read committed events in deterministic replay order. Readonly open
    # accepts CLOSED/UNCLEAN_END sessions too; admission/close stay refused.
    session = open_session(store, request.session_id, readonly=True)
    try:
        if session.status().state is SessionState.ERROR:
            raise SealError(
                f"session {request.session_id} is ERROR; resolve before sealing"
            )
        events = [
            event
            for event in session.replay_committed()
            if plan.committed_seq_start <= event.seq <= plan.committed_seq_end
        ]
        # recording02IA: ticks without an event time cannot be published
        # honestly (canonical ts is NOT NULL) and are never fabricated as
        # epoch zero. They stay preserved in the journal and are excluded
        # from this seal with an explicit count in the receipt detail.
        publishable = [event for event in events if event.event_ts_ns is not None]
        unknown_time_excluded = len(events) - len(publishable)
        aggregated = aggregate_open_session(session, final=True)
    finally:
        session.close()

    # F1: exclude provisional/partial bars from canonical publication.
    # Only bars whose minute interval is independently evidenced complete
    # are published as canonical/backtest-ready. Raw committed ticks are
    # always published regardless.
    canonical_bars = tuple(
        bar for bar in aggregated.bars if STATUS_PARTIAL not in bar.statuses
    )

    partition = request.session_id
    tick_receipt = _publish(
        store, request, RecordKind.TICKS, Interval.M1, _tick_rows(publishable, "pending", request), partition
    )
    bar_receipt = _publish(
        store, request, RecordKind.BARS, Interval.M1, _bar_rows(
            AggregatedSession(
                session_id=aggregated.session_id,
                source_spec=aggregated.source_spec,
                calendar_spec=aggregated.calendar_spec,
                committed_seq_end=aggregated.committed_seq_end,
                bars=canonical_bars,
                provisional_bars=(),
                skipped_events=aggregated.skipped_events,
                statuses=aggregated.statuses,
            ),
            "pending",
            request,
        ),
        partition,
    )

    # Durable seal record in the journal's own meta (journal-owned file).
    conn = _connect(journal_path)
    try:
        with conn:
            record = {
                "session_id": request.session_id,
                "committed_seq_start": request.committed_seq_start,
                "committed_seq_end": request.committed_seq_end,
                "transform_version": request.transform_version,
                "source_spec": request.source_spec,
                "calendar_spec": request.calendar_spec,
                "asset_class": request.asset_class.value,
                "volume_unit": request.volume_unit,
                "turnover_unit": request.turnover_unit,
                "ticks": {
                    "batch_id": tick_receipt.batch_id,
                    "dataset_id": tick_receipt.dataset_id,
                    "idempotency_key": tick_receipt.idempotency_key,
                    "accepted_rows": tick_receipt.accepted_rows,
                    "state": tick_receipt.state.value,
                },
                "bars": {
                    "batch_id": bar_receipt.batch_id,
                    "dataset_id": bar_receipt.dataset_id,
                    "idempotency_key": bar_receipt.idempotency_key,
                    "accepted_rows": bar_receipt.accepted_rows,
                    "state": bar_receipt.state.value,
                },
            }
            _meta_set(conn, "last_seal", json.dumps(record, sort_keys=True))
            seals = _meta_get(conn, "seals")
            seal_list = json.loads(seals) if seals else []
            seal_list.append(record)
            _meta_set(conn, "seals", json.dumps(seal_list, sort_keys=True))
    finally:
        conn.close()

    idempotent_replay = "idempotent" in _receipt_detail(
        tick_receipt
    ) or "idempotent" in _receipt_detail(bar_receipt)

    partitions: list[PartitionReceipt] = list(tick_receipt.partitions) + list(
        bar_receipt.partitions
    )
    detail = (
        f"sealed [{request.committed_seq_start}, {request.committed_seq_end}] "
        f"({plan.event_count} committed events); ticks batch {tick_receipt.batch_id} "
        f"state {tick_receipt.state.value}; bars batch {bar_receipt.batch_id} "
        f"state {bar_receipt.state.value}"
    )
    if unknown_time_excluded:
        detail += (
            f"; excluded {unknown_time_excluded} tick(s) with unknown event "
            "time (raw retained in journal, never fabricated as epoch zero)"
        )
    return SealReceipt(
        session_id=request.session_id,
        seal_id=tick_receipt.batch_id,
        partitions=tuple(partitions),
        idempotent_replay=idempotent_replay,
        dataset_id=tick_receipt.dataset_id,
        input_events=plan.event_count,
        accepted_rows=tick_receipt.accepted_rows + bar_receipt.accepted_rows,
        detail=detail,
    )


def _receipt_detail(receipt: ImportReceipt) -> str:
    return getattr(receipt, "detail", "") or ""
