"""Aggregation of committed journal events into session/day outputs (WP09).

Aggregates ONLY committed events, replayed in deterministic order
(event-time, then ingest sequence). Cumulative volume/amount fields are
handled with explicit first-baseline, reset and gap/reconnect detection —
never negative-delta clamping. Missing event time or calendar evidence never
becomes received-time or natural-date inference: trading_date stays NULL with
an explicit field_quality note, and the bar carries an honest status.

Quote/CTP observations and sampled polling aggregates are NOT certified
trade-by-trade market data: derived bars keep observed-source semantics
(``completeness`` partial/unknown plus a field_quality source note).

Provisional running output (the still-open final bar) is separate from final
session/day output; provisional bars are excluded from backtest-ready output.

F1 (recording02I): journal CLOSED only proves the local accepted cutoff
drained — it does NOT prove the last minute interval completed. A tail bar
is provisional (PARTIAL) unless independent completion evidence exists: a
later committed event whose event_ts_ns >= bar_end_ns, or an explicit
session/calendar close boundary crossing the bar end. CLOSED alone never
clears PARTIAL.

F3 (recording02I): admission lateness is detected from the original
committed ingest sequence and the running max source event-time BEFORE
chronological replay normalises it. An event whose event_ts_ns is earlier
than the running max at its ingest position is flagged LATE. Replay output
order remains (event_ts_ns, seq); the LATE status is metadata, not a
reordering.

Calendar truthfulness (recording02IA): a timezone-only ``calendar_spec``
(IANA name or ``tz:IANA``) establishes display timezone / normalised UTC
conversion ONLY — never a trading day. ``trading_date`` is set exclusively
from explicit source payload evidence (``payload["trading_date"]``, ISO
``YYYY-MM-DD``). Without it the bar's trading_date stays NULL with the
explicit ``trading_date_unknown`` status; an unproven Friday-night date is
never inferred. ``out_of_session`` is reserved for positive evidence and
is not asserted from missing calendar data (unknown ≠ false). There is no
calendar service and no next-day guessing.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .journal import JournalSession, open_session
from .journal_models import CommittedEvent, SessionState
from .models import Completeness, StoreError
from .store import Store

NS_MINUTE = 60 * 1_000_000_000

# Bar status flags (explicit, never silently green).
STATUS_FIRST_BASELINE = "first_baseline"        # first cumulative sample: delta unknown
STATUS_RESET = "reset"                          # cumulative counter decreased
STATUS_GAP = "gap"                              # time gap before this bar
STATUS_RECONNECT = "reconnect"                  # source reconnect before this bar
STATUS_LATE = "late"                            # admitted after a later-ts event was already admitted
STATUS_PARTIAL = "partial"                      # bar interval not independently evidenced complete
STATUS_TRADING_DATE_UNKNOWN = "trading_date_unknown"  # no source trading-day evidence
STATUS_OUT_OF_SESSION = "out_of_session"        # RESERVED: requires positive session
#                                                # evidence; never asserted from a
#                                                # missing calendar (unknown ≠ false)
STATUS_ZERO_VOLUME = "zero_volume"              # bar aggregated zero real volume
STATUS_NEGATIVE_DELTA = "negative_delta"        # cumulative decreased within a bar


class AggregationError(StoreError):
    """Aggregation preconditions violated."""


@dataclass(frozen=True)
class AggregatedBar:
    """One aggregated minute bar with honest provenance and status."""

    instrument: str
    bar_start_ns: int
    bar_end_ns: int
    trading_date: date | None
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None            # real aggregated delta volume, None if unknown
    turnover: float | None
    first_seq: int                  # session lineage of first contributing event
    last_seq: int
    event_count: int
    statuses: tuple[str, ...]
    source_kind: str                # observed event kind(s), e.g. "tick"
    completeness: str
    field_quality: str | None       # JSON notes


@dataclass(frozen=True)
class AggregatedSession:
    """Aggregation result for one journal session."""

    session_id: str
    source_spec: str
    calendar_spec: str
    committed_seq_end: int
    bars: tuple[AggregatedBar, ...]         # final bars (excludes provisional tail)
    provisional_bars: tuple[AggregatedBar, ...]  # still-open / unproven tail bar(s)
    skipped_events: int                     # committed events with no usable payload
    statuses: tuple[str, ...]               # union of bar statuses


def _event_time_ns(event: CommittedEvent) -> int | None:
    """Original event time only; never received-time inference."""

    return event.event_ts_ns


def _float(payload: Mapping[str, Any], *names: str) -> float | None:
    for name in names:
        value = payload.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _minute_start(ts_ns: int) -> int:
    return ts_ns - (ts_ns % NS_MINUTE)


def _source_trading_date(payload: Mapping[str, Any]) -> tuple[date | None, str | None]:
    """Trading day ONLY from explicit source payload evidence.

    Accepts ``payload["trading_date"]`` as a ``datetime.date`` or an ISO
    ``YYYY-MM-DD`` string (e.g. a gateway trading-day field). Returns
    ``(date, None)`` for valid evidence, ``(None, None)`` when the key is
    absent, and ``(None, reason)`` for an invalid claim. A timezone-only
    ``calendar_spec`` never supplies a trading day, and there is no
    next-day/holiday guessing.
    """

    value = payload.get("trading_date")
    if value is None:
        return None, None
    if isinstance(value, date):
        return value, None
    if isinstance(value, str):
        try:
            return date.fromisoformat(value), None
        except ValueError:
            return None, f"invalid source trading_date {value!r} ignored"
    return None, f"invalid source trading_date {value!r} ignored"


def _delta(
    previous: float | None, current: float | None
) -> tuple[float | None, str | None]:
    """Cumulative delta with reset detection; never clamps negative to zero.

    A missing current counter after a baseline means the event carried no
    volume update (e.g. a quote tick): the delta is honestly zero. A missing
    first sample leaves the delta unknown (first-baseline status).
    """

    if current is None:
        if previous is None:
            return None, None
        return 0.0, None
    if previous is None:
        return None, STATUS_FIRST_BASELINE
    delta = current - previous
    if delta < 0:
        return None, STATUS_RESET
    return delta, None


@dataclass
class _InstrumentState:
    instrument: str
    last_cum_volume: float | None = None
    last_cum_turnover: float | None = None
    last_event_ts_ns: int | None = None
    last_seq: int = 0
    # F3: running max source event-time over events admitted SO FAR in
    # ingest (seq) order. Used to flag late arrivals before replay sorts.
    max_event_ts_ns: int | None = None


@dataclass
class _OpenBar:
    instrument: str
    bar_start_ns: int
    bar_end_ns: int
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float = 0.0
    volume_known: bool = False
    turnover: float = 0.0
    turnover_known: bool = False
    first_seq: int = 0
    last_seq: int = 0
    event_count: int = 0
    trading_date: date | None = None
    trading_date_conflict: bool = False
    statuses: set[str] = field(default_factory=set)
    source_kinds: set[str] = field(default_factory=set)
    quality_notes: list[str] = field(default_factory=list)


def _close_bar(open_bar: _OpenBar, partial: bool) -> AggregatedBar:
    trading = open_bar.trading_date
    if trading is not None and open_bar.trading_date_conflict:
        open_bar.quality_notes.append(
            "conflicting source trading_date values within the bar; "
            "trading_date unknown"
        )
        trading = None
    if trading is not None:
        open_bar.quality_notes.append(
            "trading_date from source payload evidence"
        )
    else:
        open_bar.statuses.add(STATUS_TRADING_DATE_UNKNOWN)
        if not open_bar.trading_date_conflict:
            open_bar.quality_notes.append(
                "trading_date unknown: no source evidence; a timezone-only "
                "calendar_spec does not establish a trading day"
            )
    if partial:
        open_bar.statuses.add(STATUS_PARTIAL)
    if open_bar.event_count == 0 or not open_bar.volume_known:
        open_bar.statuses.add(STATUS_ZERO_VOLUME)
    if not open_bar.volume_known:
        open_bar.quality_notes.append("volume delta unknown (first baseline/reset)")
    if not open_bar.turnover_known:
        open_bar.quality_notes.append("turnover delta unknown (first baseline/reset)")
    field_quality: str | None = None
    if open_bar.quality_notes:
        field_quality = json.dumps(
            {"aggregation": sorted(set(open_bar.quality_notes))}, sort_keys=True
        )
    # Field-level trading_date uncertainty does NOT degrade row completeness:
    # only interval incompleteness (PARTIAL) or unknown volume do. Otherwise a
    # recording without a full calendar would be blanket-rejected.
    completeness = (
        Completeness.COMPLETE.value
        if STATUS_PARTIAL not in open_bar.statuses and open_bar.volume_known
        else Completeness.PARTIAL.value
    )
    return AggregatedBar(
        instrument=open_bar.instrument,
        bar_start_ns=open_bar.bar_start_ns,
        bar_end_ns=open_bar.bar_end_ns,
        trading_date=trading,
        open=open_bar.open,
        high=open_bar.high,
        low=open_bar.low,
        close=open_bar.close,
        volume=open_bar.volume if open_bar.volume_known else None,
        turnover=open_bar.turnover if open_bar.turnover_known else None,
        first_seq=open_bar.first_seq,
        last_seq=open_bar.last_seq,
        event_count=open_bar.event_count,
        statuses=tuple(sorted(open_bar.statuses)),
        source_kind="+".join(sorted(open_bar.source_kinds)) or "unknown",
        completeness=completeness,
        field_quality=field_quality,
    )


def _detect_late_events(
    events: list[CommittedEvent],
) -> dict[int, str]:
    """F3: detect admission lateness from original committed seq/order.

    Walks events in ingest (seq) order, tracking the running max source
    event-time. An event whose ``event_ts_ns`` is earlier than the running
    max at its ingest position was admitted late. Returns a mapping of
    ``seq -> explanation`` for each late event. Never compares
    ``received_ts_ns`` (receipt clock) against ``event_ts_ns`` (source
    clock); the signal is purely source-event-time high-watermark vs.
    current source event-time at admission order.
    """

    late: dict[int, str] = {}
    max_ts: int | None = None
    for event in sorted(events, key=lambda e: e.seq):
        ts = event.event_ts_ns
        if ts is not None:
            if max_ts is not None and ts < max_ts:
                late[event.seq] = (
                    f"event_ts_ns {ts} < running max {max_ts} "
                    f"at ingest seq {event.seq}"
                )
            if max_ts is None or ts > max_ts:
                max_ts = ts
    return late


def aggregate_session(
    store: Store,
    session_id: str,
    *,
    final: bool = True,
) -> AggregatedSession:
    """Aggregate the committed events of one journal session into minute bars.

    ``bars`` always contains every aggregated bar. When the session is still
    OPEN on disk, its tail bar is flagged ``partial`` and also reported in
    ``provisional_bars`` (live monitoring); ``final=False`` suppresses that
    monitoring report. Only COMMITTED events are read, in (event_ts_ns, seq)
    order; uncommitted rows are never aggregated.

    F1: a tail bar whose minute interval is not independently evidenced
    complete is also flagged ``partial`` and reported in
    ``provisional_bars``, even when the session state is CLOSED. Independent
    completion evidence means a later committed event whose event_ts_ns >=
    bar_end_ns, or an explicit ``completion_boundary_ns`` in the session meta
    that is >= bar_end_ns. CLOSED alone never clears PARTIAL.
    """

    session = open_session(store, session_id, readonly=True)
    try:
        return aggregate_open_session(session, final=final)
    finally:
        session.close()


def aggregate_open_session(
    session: JournalSession, *, final: bool = True
) -> AggregatedSession:
    """Aggregate an already-open journal session (convenience for the sealer)."""

    calendar_spec = session.calendar_spec
    states: dict[str, _InstrumentState] = {}
    open_bars: dict[str, _OpenBar] = {}
    final_bars: list[AggregatedBar] = []
    provisional: list[AggregatedBar] = []
    skipped = 0
    committed_end = session.status().committed_seq

    # F1: read optional completion boundary from session meta. When present
    # and >= a tail bar's bar_end_ns, that bar's interval is evidenced
    # complete regardless of session state.
    completion_boundary_ns: int | None = _read_completion_boundary(session)

    # Collect all committed events for late detection (F3) before replay.
    all_events: list[CommittedEvent] = list(session.replay_committed())
    late_map = _detect_late_events(all_events)

    for event in all_events:
        ts_ns = _event_time_ns(event)
        price = _float(event.payload, "last_price", "price", "close")
        cum_volume = _float(event.payload, "volume", "cum_volume", "total_volume")
        cum_turnover = _float(event.payload, "turnover", "amount", "cum_turnover")
        if ts_ns is None or price is None:
            skipped += 1
            continue
        state = states.setdefault(event.instrument, _InstrumentState(event.instrument))
        bar_start = _minute_start(ts_ns)

        bar = open_bars.get(event.instrument)
        if bar is None or bar.bar_start_ns != bar_start:
            if bar is not None:
                final_bars.append(_close_bar(bar, partial=False))
                open_bars.pop(event.instrument)
            bar = _OpenBar(
                instrument=event.instrument,
                bar_start_ns=bar_start,
                bar_end_ns=bar_start + NS_MINUTE,
                open=price,
                high=price,
                low=price,
                close=price,
                first_seq=event.seq,
            )
            open_bars[event.instrument] = bar
            if state.last_event_ts_ns is not None and ts_ns - state.last_event_ts_ns > NS_MINUTE:
                bar.statuses.add(STATUS_GAP)
        # F3: flag late arrivals detected from ingest-order analysis on the
        # bar that CONTAINS the late event — whether the event creates the
        # bar or joins an already-open bar (e.g. seq1/T0, seq2/T10, seq3/T1
        # in one minute: seq3 joins seq1's bar and must still carry LATE).
        if event.seq in late_map:
            bar.statuses.add(STATUS_LATE)
            bar.quality_notes.append(late_map[event.seq])

        # Calendar truthfulness (02IA): trading_date ONLY from source
        # payload evidence; never from the timezone or a natural date.
        src_date, src_note = _source_trading_date(event.payload)
        if src_note is not None:
            bar.quality_notes.append(src_note)
        if src_date is not None:
            if bar.trading_date is None:
                bar.trading_date = src_date
            elif bar.trading_date != src_date:
                bar.trading_date_conflict = True

        # Price roll-up.
        bar.high = price if bar.high is None else max(bar.high, price)
        bar.low = price if bar.low is None else min(bar.low, price)
        bar.close = price
        bar.last_seq = event.seq
        bar.event_count += 1
        bar.source_kinds.add(event.kind)
        if event.source_event_id:
            bar.quality_notes.append(f"observed source event {event.source_event_id}")

        # Cumulative deltas with reset/first-baseline honesty.
        d_volume, st_volume = _delta(state.last_cum_volume, cum_volume)
        d_turnover, st_turnover = _delta(state.last_cum_turnover, cum_turnover)
        if st_volume == STATUS_RESET or st_turnover == STATUS_RESET:
            bar.statuses.add(STATUS_RESET)
        if st_volume == STATUS_FIRST_BASELINE:
            bar.statuses.add(STATUS_FIRST_BASELINE)
        if d_volume is not None:
            bar.volume += d_volume
            bar.volume_known = True
            if d_volume < 0:
                bar.statuses.add(STATUS_NEGATIVE_DELTA)
        if d_turnover is not None:
            bar.turnover += d_turnover
            bar.turnover_known = True
        if cum_volume is not None:
            state.last_cum_volume = cum_volume
        if cum_turnover is not None:
            state.last_cum_turnover = cum_turnover
        state.last_event_ts_ns = ts_ns
        state.last_seq = event.seq

    # F1: determine which tail bars are provisional.
    #
    # A tail bar is provisional (PARTIAL) when its minute interval is NOT
    # independently evidenced complete. Evidence of completion:
    #   (a) A later committed event whose event_ts_ns >= bar_end_ns (the next
    #       bar or a later tick proves the minute elapsed).
    #   (b) An explicit completion_boundary_ns in session meta >= bar_end_ns.
    #
    # Session state (OPEN vs CLOSED) is NOT evidence of interval completion.
    # CLOSED only proves the local accepted cutoff drained; it says nothing
    # about whether market data for the remaining seconds of the tail bar's
    # minute ever arrived.
    session_is_open = session.status().state is SessionState.OPEN
    for bar in open_bars.values():
        has_completion_evidence = _has_completion_evidence(
            bar, all_events, completion_boundary_ns
        )
        is_provisional = session_is_open or not has_completion_evidence
        closed_bar = _close_bar(bar, partial=is_provisional)
        final_bars.append(closed_bar)
        if is_provisional:
            provisional.append(closed_bar)

    all_final = final_bars
    kept_provisional: tuple[AggregatedBar, ...] = tuple(provisional) if final else ()
    union: set[str] = set()
    for final_bar in all_final:
        union.update(final_bar.statuses)
    for prov_bar in kept_provisional:
        union.update(prov_bar.statuses)
    return AggregatedSession(
        session_id=session.session_id,
        source_spec=session.source_spec,
        calendar_spec=calendar_spec,
        committed_seq_end=committed_end,
        bars=tuple(all_final),
        provisional_bars=tuple(kept_provisional),
        skipped_events=skipped,
        statuses=tuple(sorted(union)),
    )


def _read_completion_boundary(session: JournalSession) -> int | None:
    """Read optional completion_boundary_ns from session meta.

    This is an explicit, trustworthy interval/session completion evidence
    point: the caller (recorder, calendar module, or operator) asserts that
    market data up to and including this ns boundary has been observed.
    Written only through ``JournalSession.record_completion_boundary_ns``.
    A missing or unparseable value is treated as NO evidence (the tail bar
    then stays PARTIAL — fail-safe, never fail-open).
    """

    raw = session.read_meta("completion_boundary_ns")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _has_completion_evidence(
    bar: _OpenBar,
    all_events: list[CommittedEvent],
    completion_boundary_ns: int | None,
) -> bool:
    """Check whether a tail bar's minute interval is independently evidenced complete.

    Evidence:
    (a) A later committed event (in the same session) whose event_ts_ns >=
        bar.bar_end_ns proves the minute elapsed.
    (b) An explicit completion_boundary_ns >= bar.bar_end_ns.
    """

    if completion_boundary_ns is not None and completion_boundary_ns >= bar.bar_end_ns:
        return True
    for event in all_events:
        if (
            event.instrument == bar.instrument
            and event.event_ts_ns is not None
            and event.event_ts_ns >= bar.bar_end_ns
        ):
            return True
    return False
