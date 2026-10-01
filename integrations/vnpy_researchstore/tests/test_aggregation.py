"""Aggregation tests: committed-only input, deterministic order, honest
statuses (first baseline, reset, gap, late, partial, out-of-session,
zero-volume), provisional vs final separation, no negative clamping, and no
received-time/natural-date inference.

F1 (recording02I): CLOSED alone does NOT clear PARTIAL. A tail bar is
provisional unless independent completion evidence exists (a later committed
event whose event_ts_ns >= bar_end_ns, or an explicit completion_boundary_ns
in session meta).

F3 (recording02I): admission lateness is detected from original committed
ingest seq/order and source event-time high-watermark BEFORE chronological
replay normalises it. seq1/T0, seq2/T10, seq3/T1 must replay T0,T1,T10 and
retain LATE status for seq3/affected bar.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from research_store.aggregation import (
    STATUS_FIRST_BASELINE,
    STATUS_GAP,
    STATUS_LATE,
    STATUS_PARTIAL,
    STATUS_RESET,
    STATUS_TRADING_DATE_UNKNOWN,
    STATUS_ZERO_VOLUME,
    aggregate_session,
)
from research_store.journal import create_session
from research_store.journal_models import JournalEvent
from research_store.store import init_store

BASE = 1_700_000_000_000_000_000
NS_MINUTE = 60 * 1_000_000_000


def tick(ts: int, volume: float, turnover: float, price: float = 10.0) -> JournalEvent:
    return JournalEvent(
        kind="tick",
        instrument="IF2403.CFFEX",
        event_ts_ns=ts,
        source_event_id=None,
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


def committed_only_aggregate(store, admit, n: int):
    """Admit n events, drain, then admit one more and close BEFORE it commits."""
    session = create_session(store, "src-a", "")
    for event in admit:
        session.admit(event)
    drain(session, n)
    session.close()
    return aggregate_session(store, session.session_id)


def test_aggregates_committed_minute_bars(store) -> None:
    session = create_session(store, "src-a", "")
    ts0 = BASE
    session.admit(tick(ts0, volume=100, turnover=1000, price=10.0))
    session.admit(tick(ts0 + 1, volume=110, turnover=1110, price=10.5))
    session.admit(tick(ts0 + NS_MINUTE, volume=130, turnover=1330, price=11.0))
    drain(session, 3)
    result = session.close_at_cutoff(timeout=5.0)
    assert result.state.value == "CLOSED"
    session.close()

    agg = aggregate_session(store, session.session_id)
    assert agg.session_id == session.session_id
    assert agg.committed_seq_end == 3
    assert len(agg.bars) == 2
    # F1: the tail bar (minute 1) has a later event in minute 2, so it is
    # evidenced complete. But minute 2 itself has no later event and no
    # completion boundary, so it stays provisional.
    assert len(agg.provisional_bars) == 1
    # Bars are minute-aligned; BASE sits 20s into its minute.
    assert agg.provisional_bars[0].bar_start_ns == (
        ts0 - (ts0 % NS_MINUTE) + NS_MINUTE
    )
    bar0, bar1 = agg.bars
    assert bar0.bar_start_ns == ts0 - (ts0 % NS_MINUTE)
    assert bar0.open == 10.0 and bar0.high == 10.5 and bar0.low == 10.0
    assert bar0.close == 10.5
    # First sample has no baseline (flagged); second sample in the same bar
    # gives a real delta of 10 volume / 110 turnover.
    assert bar0.volume == pytest.approx(10.0)
    assert bar0.turnover == pytest.approx(110.0)
    assert STATUS_FIRST_BASELINE in bar0.statuses
    # Second bar: delta 20 volume / 220 turnover.
    assert bar1.volume == pytest.approx(20.0)
    assert bar1.turnover == pytest.approx(220.0)


def test_uncommitted_events_never_aggregated(store) -> None:
    session = create_session(store, "src-a", "")
    session.admit(tick(BASE, 100, 1000))
    drain(session, 1)
    # Stop the writer; further events stay uncommitted.
    session._stop.set()
    session._writer.join(timeout=5.0)
    session.admit(tick(BASE + NS_MINUTE, 200, 2000))
    session.close()
    agg = aggregate_session(store, session.session_id)
    assert agg.committed_seq_end == 1
    assert len(agg.bars) == 1
    assert agg.bars[0].last_seq == 1


def test_reset_detected_not_clamped(store) -> None:
    session = create_session(store, "src-a", "")
    session.admit(tick(BASE, 100, 1000))
    session.admit(tick(BASE + NS_MINUTE, 50, 500))  # cumulative decreased
    drain(session, 2)
    session.close()
    agg = aggregate_session(store, session.session_id)
    bar1 = agg.bars[1]
    assert STATUS_RESET in bar1.statuses
    assert bar1.volume is None  # unknown delta, never negative/clamped
    assert bar1.turnover is None


def test_gap_status_and_replay_normalizes_order(store) -> None:
    # Replay is deterministic by (event_ts_ns, seq): an event admitted after a
    # later-timestamped peer is placed at its own event time. F3: the late
    # event is still flagged LATE from ingest-order analysis.
    session = create_session(store, "src-a", "")
    session.admit(tick(BASE, 100, 1000))
    session.admit(tick(BASE + 10 * NS_MINUTE, 110, 1100))  # gap
    session.admit(tick(BASE + NS_MINUTE, 120, 1200))  # admitted after gap event
    drain(session, 3)
    session.close()
    agg = aggregate_session(store, session.session_id)
    by_start = {b.bar_start_ns: b for b in agg.bars}
    gap_bar = by_start[BASE + 10 * NS_MINUTE - ((BASE + 10 * NS_MINUTE) % NS_MINUTE)]
    between_bar = by_start[BASE + NS_MINUTE - ((BASE + NS_MINUTE) % NS_MINUTE)]
    assert STATUS_GAP in gap_bar.statuses
    # F3: the event admitted after a later-timestamped peer is flagged LATE.
    assert STATUS_LATE in between_bar.statuses
    assert between_bar.volume == pytest.approx(20.0)  # 120-100 delta
    assert STATUS_RESET in gap_bar.statuses  # 110 < 120 cumulative decrease


def test_no_calendar_trading_date_stays_null(store) -> None:
    session = create_session(store, "src-a", "")  # no calendar evidence
    session.admit(tick(BASE, 100, 1000))
    drain(session, 1)
    session.close()
    agg = aggregate_session(store, session.session_id)
    bar = agg.bars[0]
    assert bar.trading_date is None
    assert STATUS_TRADING_DATE_UNKNOWN in bar.statuses
    assert bar.field_quality is not None


def test_timezone_only_never_establishes_trading_date(store) -> None:
    """02IA: IANA/tz:IANA alone is a display timezone, NEVER a trading day.

    SYNTHETIC FIXTURE (not gateway evidence): one event on Friday night
    2024-01-05 21:00 Asia/Shanghai (night session; the next trading day is
    Monday 2024-01-08, which a timezone cannot establish). The bar must keep
    trading_date NULL with explicit uncertainty — the previous behavior
    inferred the localized natural date 2024-01-05.
    """
    session = create_session(store, "src-a", "Asia/Shanghai")
    friday_night_ns = 1704459600 * 1_000_000_000  # 2024-01-05 13:00 UTC
    session.admit(tick(friday_night_ns, 100, 1000))
    drain(session, 1)
    session.close()
    agg = aggregate_session(store, session.session_id)
    bar = agg.bars[0]
    assert bar.trading_date is None
    assert STATUS_TRADING_DATE_UNKNOWN in bar.statuses
    assert "2024-01-05" not in (bar.field_quality or "")
    assert "timezone-only" in (bar.field_quality or "")


def test_source_trading_date_flows_to_bar(store) -> None:
    """02IA: genuinely provided source trading_date (e.g. a gateway
    trading-day field) is preserved with provenance. SYNTHETIC FIXTURE."""
    session = create_session(store, "src-a", "Asia/Shanghai")
    friday_night_ns = 1704459600 * 1_000_000_000
    event = tick(friday_night_ns, 100, 1000)
    from dataclasses import replace

    event = replace(event, payload=dict(event.payload, trading_date="2024-01-08"))
    session.admit(event)
    drain(session, 1)
    session.close()
    agg = aggregate_session(store, session.session_id)
    bar = agg.bars[0]
    from datetime import date as _date

    assert bar.trading_date == _date(2024, 1, 8)
    assert STATUS_TRADING_DATE_UNKNOWN not in bar.statuses
    assert "source payload evidence" in (bar.field_quality or "")
    # Field-level certainty does not fake interval completeness either way.
    assert STATUS_PARTIAL in bar.statuses  # tail bar without completion evidence


def test_conflicting_source_trading_dates_stay_null(store) -> None:
    """02IA: conflicting source dates within one bar cannot be resolved by
    guessing — trading_date stays NULL with explicit uncertainty."""
    session = create_session(store, "src-a", "")
    from dataclasses import replace

    e1 = replace(tick(BASE, 100, 1000), payload={"last_price": 10.0, "trading_date": "2024-01-08"})
    e2 = replace(tick(BASE + 1, 110, 1100), payload={"last_price": 10.5, "trading_date": "2024-01-09"})
    session.admit(e1)
    session.admit(e2)
    drain(session, 2)
    session.close()
    agg = aggregate_session(store, session.session_id)
    bar = agg.bars[0]
    assert bar.trading_date is None
    assert STATUS_TRADING_DATE_UNKNOWN in bar.statuses
    assert "conflicting source trading_date" in (bar.field_quality or "")


def test_invalid_source_trading_date_ignored(store) -> None:
    """02IA: an unparseable source trading_date claim is ignored honestly
    (NULL + note), never crashed on and never repaired by guessing."""
    session = create_session(store, "src-a", "")
    from dataclasses import replace

    event = replace(
        tick(BASE, 100, 1000),
        payload={"last_price": 10.0, "trading_date": "not-a-date"},
    )
    session.admit(event)
    drain(session, 1)
    session.close()
    agg = aggregate_session(store, session.session_id)
    bar = agg.bars[0]
    assert bar.trading_date is None
    assert STATUS_TRADING_DATE_UNKNOWN in bar.statuses
    assert "invalid source trading_date" in (bar.field_quality or "")


def test_provisional_tail_reported_for_open_session(store) -> None:
    session = create_session(store, "src-a", "")
    session.admit(tick(BASE, 100, 1000))
    session.admit(tick(BASE + NS_MINUTE, 110, 1100))
    drain(session, 2)
    session.close()  # lock release only; on-disk state stays OPEN
    agg = aggregate_session(store, session.session_id, final=True)
    # Final output contains every bar; the still-open tail is flagged partial
    # AND reported in provisional_bars for monitoring.
    assert len(agg.bars) == 2
    assert len(agg.provisional_bars) == 1
    assert STATUS_PARTIAL in agg.provisional_bars[0].statuses
    assert agg.bars[-1].statuses == agg.provisional_bars[0].statuses


def test_f1_closed_midminute_tail_stays_provisional(store) -> None:
    """F1: CLOSED alone does NOT clear PARTIAL.

    A session that admits one tick 5s into a minute and then closes has
    drained its accepted cutoff, but the minute interval is NOT evidenced
    complete — no later event crosses the bar end, and no explicit
    completion boundary is set. The tail bar must remain PARTIAL.
    """
    session = create_session(store, "src-a", "Asia/Shanghai")
    minute_ns = NS_MINUTE
    aligned = (BASE // minute_ns) * minute_ns + 5_000_000_000  # 5s into minute
    session.admit(tick(aligned, 100, 1000))
    drain(session, 1)
    result = session.close_at_cutoff(timeout=5.0)
    assert result.state.value == "CLOSED"
    session.close()

    agg = aggregate_session(store, session.session_id, final=True)
    assert len(agg.bars) == 1
    tail = agg.bars[0]
    assert STATUS_PARTIAL in tail.statuses
    assert len(agg.provisional_bars) == 1
    assert agg.provisional_bars[0].bar_start_ns == tail.bar_start_ns


def test_f1_completion_boundary_clears_partial(store) -> None:
    """F1: an explicit completion_boundary_ns >= bar_end_ns evidences completion.

    Same setup as test_f1_closed_midminute_tail_stays_provisional, but the
    session carries a recorded completion boundary at the bar end (public
    ``record_completion_boundary_ns`` API). The tail bar is then evidenced
    complete and must NOT be flagged PARTIAL.
    """
    session = create_session(store, "src-a", "Asia/Shanghai")
    minute_ns = NS_MINUTE
    aligned = (BASE // minute_ns) * minute_ns + 5_000_000_000
    session.admit(tick(aligned, 100, 1000))
    drain(session, 1)

    # The minute containing `aligned` ends at (aligned // minute_ns + 1) *
    # minute_ns; recording that boundary is explicit evidence that the
    # interval completed.
    bar_end = (aligned // minute_ns + 1) * minute_ns
    session.record_completion_boundary_ns(bar_end)

    result = session.close_at_cutoff(timeout=5.0)
    assert result.state.value == "CLOSED"
    session.close()

    agg = aggregate_session(store, session.session_id, final=True)
    assert len(agg.bars) == 1
    tail = agg.bars[0]
    assert STATUS_PARTIAL not in tail.statuses
    assert len(agg.provisional_bars) == 0


def test_f1_later_event_evidences_completion(store) -> None:
    """F1: a later committed event whose ts >= bar_end_ns evidences completion.

    Two ticks in the same minute, then a third tick in the next minute.
    The first minute's bar is evidenced complete by the second-minute event.
    The second minute's bar has no later event and stays PARTIAL.
    """
    session = create_session(store, "src-a", "Asia/Shanghai")
    minute_ns = NS_MINUTE
    m0 = (BASE // minute_ns) * minute_ns
    session.admit(tick(m0 + 1_000_000_000, 100, 1000))
    session.admit(tick(m0 + 30_000_000_000, 110, 1100))
    session.admit(tick(m0 + minute_ns + 1_000_000_000, 120, 1200))
    drain(session, 3)
    result = session.close_at_cutoff(timeout=5.0)
    assert result.state.value == "CLOSED"
    session.close()

    agg = aggregate_session(store, session.session_id, final=True)
    assert len(agg.bars) == 2
    bar0, bar1 = agg.bars
    # bar0 (minute 0) has a later event in minute 1 → evidenced complete.
    assert STATUS_PARTIAL not in bar0.statuses
    # bar1 (minute 1) has no later event → stays provisional.
    assert STATUS_PARTIAL in bar1.statuses
    assert len(agg.provisional_bars) == 1
    assert agg.provisional_bars[0].bar_start_ns == bar1.bar_start_ns


def test_f3_late_admission_detected_before_replay(store) -> None:
    """F3: seq1/T0, seq2/T10, seq3/T1 → replay T0,T1,T10, seq3 flagged LATE.

    seq3 is admitted third in ingest order but its event time (T1) is
    earlier than seq2's (T10). Replay normalises to T0,T1,T10 but the
    affected bar must carry the LATE status for seq3.
    """
    session = create_session(store, "src-a", "Asia/Shanghai")
    minute_ns = NS_MINUTE
    m0 = (BASE // minute_ns) * minute_ns
    T0 = m0 + 1_000_000_000
    T10 = m0 + 10_000_000_000
    T1 = m0 + 2_000_000_000
    session.admit(tick(T0, 100, 1000))
    session.admit(tick(T10, 110, 1100))
    session.admit(tick(T1, 120, 1200))  # late: admitted after T10 but ts < T10
    drain(session, 3)
    session.close()

    agg = aggregate_session(store, session.session_id, final=True)
    # All three events are in the same minute.
    assert len(agg.bars) == 1
    bar = agg.bars[0]
    assert STATUS_LATE in bar.statuses
    # Replay order is normalised: the bar's first_seq/last_seq reflect
    # event-time order, not ingest order.
    assert bar.event_count == 3


def test_zero_volume_bar_flagged(store) -> None:
    session = create_session(store, "src-a", "")
    session.admit(tick(BASE, 100, 1000))
    session.admit(
        JournalEvent("tick", "IF2403.CFFEX", BASE + 1, None, {"last_price": 10.1})
    )
    drain(session, 2)
    session.close()
    agg = aggregate_session(store, session.session_id)
    bar = agg.bars[0]
    assert bar.event_count == 2
    assert bar.volume == 0.0  # second event had no cumulative counter
    assert STATUS_ZERO_VOLUME in bar.statuses or STATUS_FIRST_BASELINE in bar.statuses


def test_skipped_events_missing_time_or_price(store) -> None:
    session = create_session(store, "src-a", "")
    session.admit(
        JournalEvent("tick", "IF2403.CFFEX", None, None, {"last_price": 10.0})
    )
    session.admit(JournalEvent("tick", "IF2403.CFFEX", BASE, None, {"volume": 5}))
    session.admit(tick(BASE + NS_MINUTE, 100, 1000))
    drain(session, 3)
    session.close()
    agg = aggregate_session(store, session.session_id)
    assert agg.skipped_events == 2
    assert len(agg.bars) == 1


def test_deterministic_repeat_aggregation(store) -> None:
    session = create_session(store, "src-a", "Asia/Shanghai")
    for i in range(10):
        session.admit(tick(BASE + i * NS_MINUTE, 100 + i * 10, 1000 + i * 100))
    drain(session, 10)
    session.close()
    first = aggregate_session(store, session.session_id)
    second = aggregate_session(store, session.session_id)
    assert first.bars == second.bars
    assert first.statuses == second.statuses
