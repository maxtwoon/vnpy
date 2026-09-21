from __future__ import annotations

from research_store.importers.normalize import normalize_rq_etf_row
from research_store.quality import (
    QualityReport,
    check_row,
    check_rows,
    required_fields_status,
)


def _row(**overrides: object) -> dict:
    base = {
        "instrument": "510300.XSHG",
        "source_label": "2026-07-31 09:31:00",
        "trading_date": "2026-07-31",
        "bar_start_ns": 1,
        "bar_end_ns": 2,
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "volume": 100.0,
        "turnover": 500.0,
        "open_interest": None,
        "quality_flags": [],
        "extensions": {},
        "provenance": {},
    }
    base.update(overrides)
    return base


def test_clean_row_has_no_issues() -> None:
    assert check_row(_row()) == []


def test_envelope_violation_detected() -> None:
    assert check_row(_row(high=0.4)) == ["ohlc_envelope"]
    assert check_row(_row(low=2.5)) == ["ohlc_envelope"]
    assert check_row(_row(open=99.0)) == ["ohlc_envelope"]


def test_nonpositive_price_detected() -> None:
    assert "nonpositive_price" in check_row(_row(close=0.0))


def test_negative_fields_flagged_not_altered() -> None:
    row = _row(volume=-5.0)
    issues = check_row(row)
    assert "negative_volume" in issues
    assert row["volume"] == -5.0  # observational only


def test_missing_price_and_unknown_bounds() -> None:
    row = _row(open=None, high=None, low=None, close=None, bar_start_ns=None)
    assert set(check_row(row)) == {"missing_price", "unknown_time_bounds"}


def test_annotations_counted_separately_from_damage() -> None:
    row = _row(quality_flags=["disputed_upstream_refetch", "repaired_deterministic"])
    report = QualityReport(scope="s")
    check_row(row, report)
    assert report.rows_checked == 1
    assert report.issue_counts["annotation:disputed_upstream_refetch"] == 1
    assert report.issue_counts["annotation:repaired_deterministic"] == 1
    assert report.clean_rows == 1  # annotations are not row damage


def test_check_rows_aggregates_samples() -> None:
    rows = [
        _row(volume=-1.0, source_label=f"2026-07-31 09:{i:02d}:00") for i in range(7)
    ]
    report = check_rows(rows, scope="batch")
    assert report.issue_counts["negative_volume"] == 7
    assert len(report.samples["negative_volume"]) == 5  # capped evidence


def test_required_fields_status_distinguishes_unavailable() -> None:
    rows = [
        _row(turnover=None),
        _row(turnover=1.0),
    ]
    status = required_fields_status(rows, required=("close", "turnover"))
    assert status["null_counts"] == {"close": 0, "turnover": 1}
    assert status["fully_populated"] is False


def test_repaired_real_world_row_flows_through_quality() -> None:
    # the 160105 example: repaired row 0/0 is clean data-wise; the dispute is
    # an annotation, not damage
    raw = {
        "order_book_id": "160105.XSHE",
        "datetime": "2017-09-19 13:01:00",
        "open": "1.0",
        "high": "1.0",
        "low": "1.0",
        "close": "1.0",
        "volume": "0",
        "amount": "0",
        "num_trades": "0",
    }
    row = normalize_rq_etf_row(
        raw,
        interval_minutes=1,
        archive="rqdatac_etf_lof_1m_2017.tar.zst",
        member="2017/160105.XSHE.csv",
        batch_id="b",
    )
    row["quality_flags"].append("disputed_upstream_refetch")
    report = check_rows([row], scope="etf-2017")
    assert report.clean_rows == 1
    assert report.issue_counts["annotation:disputed_upstream_refetch"] == 1
