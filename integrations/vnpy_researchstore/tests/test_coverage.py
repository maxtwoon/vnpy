from __future__ import annotations

from research_store.coverage import (
    compute_gaps,
    coverage_with_calendar,
    summarize_coverage,
)
from research_store.importers.normalize import normalize_rq_etf_row


def _etf_row(label: str, instrument: str = "510300.XSHG") -> dict:
    return normalize_rq_etf_row(
        {
            "order_book_id": instrument,
            "datetime": label,
            "open": "1",
            "high": "1",
            "low": "1",
            "close": "1",
            "volume": "1",
            "amount": "1",
        },
        interval_minutes=1,
        archive="a",
        member="m",
        batch_id="b",
    )


def test_expected_unknown_without_calendar_evidence() -> None:
    rows = [_etf_row("2026-07-30 09:31:00"), _etf_row("2026-07-31 09:31:00")]
    report = summarize_coverage(rows, scope="etf")
    payload = report.to_dict()
    assert payload["expected_status"] == "unknown"
    entry = payload["instruments"]["510300.XSHG"]
    assert entry["rows_observed"] == 2
    assert entry["first_label"] == "2026-07-30 09:31:00"
    assert entry["trading_dates_observed"] == 2
    assert entry["interval_minutes_seen"] == [1]


def test_quarantined_rows_visible_not_hidden() -> None:
    rows = [_etf_row("2026-07-30 09:31:00"), _etf_row("2026-07-30 09:32:00")]
    quarantine = {("510300.XSHG", "2026-07-30 09:32:00")}
    report = summarize_coverage(rows, scope="etf", quarantined_keys=quarantine)
    entry = report.instruments["510300.XSHG"]
    assert entry.rows_quarantined == 1
    assert entry.rows_accepted == 1
    assert entry.rows_observed == 2


def test_gaps_only_with_calendar_and_never_filled() -> None:
    rows = [
        _etf_row("2026-07-29 09:31:00"),
        _etf_row("2026-07-31 09:31:00"),  # 2026-07-30 missing
    ]
    report = summarize_coverage(rows, scope="etf")
    calendar = ["2026-07-29", "2026-07-30", "2026-07-31"]
    payload = coverage_with_calendar(report, calendar)
    gaps = payload["gaps"]["510300.XSHG"]
    assert gaps["gap_days"] == 1
    assert gaps["gaps"] == ["2026-07-30"]
    # no fabricated rows appeared anywhere
    assert payload["instruments"]["510300.XSHG"]["rows_observed"] == 2


def test_days_outside_observed_window_not_counted_as_gaps() -> None:
    rows = [_etf_row("2026-07-30 09:31:00"), _etf_row("2026-07-31 09:31:00")]
    report = summarize_coverage(rows, scope="etf")
    entry = report.instruments["510300.XSHG"]
    calendar = ["2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03"]
    gaps = compute_gaps(entry, calendar)
    assert gaps["gaps"] == []
    assert gaps["calendar_days_in_window"] == 2


def test_min_max_is_not_completeness() -> None:
    rows = [_etf_row("2016-01-04 09:31:00"), _etf_row("2026-07-31 09:31:00")]
    payload = summarize_coverage(rows, scope="etf").to_dict()
    # wide min/max with 2 rows: expected stays unknown, no completeness claim
    assert payload["expected_status"] == "unknown"
    assert payload["instruments"]["510300.XSHG"]["rows_observed"] == 2


def test_multiple_instruments_and_kinds() -> None:
    rows = [
        _etf_row("2026-07-31 09:31:00", instrument="510300.XSHG"),
        _etf_row("2026-07-31 09:31:00", instrument="159915.XSHE"),
    ]
    payload = summarize_coverage(rows, scope="etf").to_dict()
    assert set(payload["instruments"]) == {"510300.XSHG", "159915.XSHE"}
