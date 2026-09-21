"""Time-contract tests (disposition 2026-09-16):

- daily identity/dedup/conflict is (instrument-or-series, trading_date), even
  when source timestamp labels differ;
- daily NULL trading_date is rejected at publication, not at read;
- minute NULL trading_date round-trips with its quality flag, never derived
  from bar_start / natural date;
- distinct minutes remain distinct keys;
- snapshots retain the uncertainty (quality flags + decisions) instead of
  silently labeling data qualified.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from research_store import (
    BatchState,
    ConflictResolution,
    CoverageGapError,
    Interval,
    KnownGap,
    Selection,
    SnapshotRequest,
    StoreError,
    UnresolvedConflictError,
    compute_dataset_id,
    freeze,
    open_snapshot,
    resolve_conflict,
)

from conftest import NS_MINUTE, bar_row, import_rows, make_spec, ns

DAY1 = date(2024, 1, 2)
DAY2 = date(2024, 1, 3)


def _read_all(store, snap: str, dataset_id: str, **kwargs) -> list[dict]:
    with open_snapshot(store, snap) as reader:
        return [r for b in reader.bars(dataset_id, **kwargs) for r in b.to_pylist()]


def _freeze_all(store, dataset_id: str, **kwargs):
    return freeze(store, SnapshotRequest(
        selections=(Selection(dataset_id, "*"),), **kwargs
    ))


# -- daily identity ---------------------------------------------------------


def test_daily_duplicate_with_different_label_timestamps_dedups(store, tmp_path: Path) -> None:
    """Same (identity, trading_date) with different bar_start labels and
    identical values is ONE key: deduplicated, not double-published."""

    spec = make_spec()  # daily
    dataset_id = compute_dataset_id(spec)
    # Source A labels the daily bar at 00:00, source B at 15:00 close.
    import_rows(store, tmp_path,
                [bar_row(dataset_id, "000001", ns(2024, 1, 2, 0, 0), trading=DAY1)],
                spec, asset_name="a.csv", asset_content=b"a")
    receipt = import_rows(
        store, tmp_path,
        [bar_row(dataset_id, "000001", ns(2024, 1, 2, 15, 0), trading=DAY1)],
        spec, asset_name="b.csv", asset_content=b"b",
    )
    assert receipt.state is BatchState.PUBLISHED
    assert receipt.duplicate_rows == 1
    assert receipt.accepted_rows == 0
    head = store.catalog.get_head(dataset_id, "2024")
    assert store.catalog.get_revision(head)["rows"] == 1


def test_daily_conflict_by_trading_date_despite_different_labels(store, tmp_path: Path) -> None:
    """Same (identity, trading_date), different close, different label =>
    conflict keyed on the trading date; resolution replaces exactly that day."""

    spec = make_spec()
    dataset_id = compute_dataset_id(spec)
    base = import_rows(
        store, tmp_path,
        [bar_row(dataset_id, "000001", ns(2024, 1, 2, 0, 0), close=10.0, trading=DAY1)],
        spec, asset_name="a.csv", asset_content=b"a",
    )
    snap_before = _freeze_all(store, dataset_id)
    receipt = import_rows(
        store, tmp_path,
        [bar_row(dataset_id, "000001", ns(2024, 1, 2, 15, 0), close=99.0, trading=DAY1)],
        spec, asset_name="b.csv", asset_content=b"b",
    )
    assert receipt.state is BatchState.CONFLICTED
    conflict = receipt.conflicts[0]
    assert conflict.key == f"000001@{DAY1}"  # keyed by trading date, not label

    with pytest.raises(UnresolvedConflictError):
        _freeze_all(store, dataset_id)

    resolve_conflict(store, dataset_id, "2024", conflict.conflict_id,
                     ConflictResolution.CANDIDATE, "vendor correction verified")
    rows = _read_all(store, _freeze_all(store, dataset_id).snapshot_id, dataset_id)
    assert len(rows) == 1
    assert rows[0]["close"] == 99.0
    assert rows[0]["trading_date"] == DAY1

    # The pre-resolution snapshot is unchanged and still shows the old value.
    old_rows = _read_all(store, snap_before.snapshot_id, dataset_id)
    assert old_rows[0]["close"] == 10.0
    assert base.partitions[0].revision_id != store.catalog.get_head(dataset_id, "2024")


def test_daily_series_identity_accepted_without_instrument(store, tmp_path: Path) -> None:
    """Daily continuous candidate series must not be excluded merely because
    instrument_id is null when series_id is valid."""

    spec = make_spec(series_kind="continuous_888", rule_version="unverified")
    dataset_id = compute_dataset_id(spec)
    receipt = import_rows(
        store, tmp_path,
        [bar_row(dataset_id, "ignored", ns(2024, 1, 2, 0, 0), trading=DAY1,
                 series="RB888", contract_id="RB2405")],
        spec,
    )
    assert receipt.state is BatchState.PUBLISHED
    assert receipt.accepted_rows == 1


def test_daily_null_trading_date_rejected_at_publication(store, tmp_path: Path) -> None:
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)
    row = bar_row(dataset_id, "000001", ns(2024, 1, 2, 0, 0))
    row["trading_date"] = None
    with pytest.raises(StoreError, match="trading_date"):
        import_rows(store, tmp_path, [row], spec)
    assert store.catalog.get_head(dataset_id, "2024") is None


def test_daily_quarantine_gap_uses_real_bar_bounds(store, tmp_path: Path) -> None:
    spec = make_spec()
    dataset_id = compute_dataset_id(spec)
    start = ns(2024, 1, 2, 0, 0)
    import_rows(store, tmp_path,
                [bar_row(dataset_id, "000001", start, close=10.0, trading=DAY1)],
                spec, asset_name="a.csv", asset_content=b"a")
    receipt = import_rows(
        store, tmp_path,
        [bar_row(dataset_id, "000001", ns(2024, 1, 2, 15, 0), close=99.0, trading=DAY1)],
        spec, asset_name="b.csv", asset_content=b"b",
    )
    resolve_conflict(store, dataset_id, "2024", receipt.conflicts[0].conflict_id,
                     ConflictResolution.QUARANTINE, "disputed daily close")

    ref = _freeze_all(store, dataset_id)
    with open_snapshot(store, ref.snapshot_id) as reader:
        with pytest.raises(CoverageGapError):
            list(reader.bars(
                dataset_id,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 1, 4, tzinfo=timezone.utc),
            ))
    allowed = _freeze_all(store, dataset_id, allow_known_gaps=(
        KnownGap(dataset_id, start, start + NS_MINUTE, "quarantined disputed day"),
    ))
    assert _read_all(store, allowed.snapshot_id, dataset_id) == []


# -- minute unknown trading day ---------------------------------------------


def test_minute_null_trading_date_roundtrip_with_flag(store, tmp_path: Path) -> None:
    spec = make_spec(interval=Interval.M1)
    dataset_id = compute_dataset_id(spec)
    row = bar_row(dataset_id, "RB2405", ns(2024, 1, 2, 21, 0))
    row["trading_date"] = None  # no calendar evidence
    row["field_quality"] = json.dumps({"trading_date": "unknown_no_calendar"})
    receipt = import_rows(store, tmp_path, [row], spec)
    assert receipt.state is BatchState.PUBLISHED

    ref = _freeze_all(store, dataset_id)
    rows = _read_all(store, ref.snapshot_id, dataset_id)
    assert len(rows) == 1
    assert rows[0]["trading_date"] is None  # preserved, never derived
    assert "unknown_no_calendar" in rows[0]["field_quality"]
    assert rows[0]["bar_start"] == ns(2024, 1, 2, 21, 0)


def test_minute_null_trading_date_without_quality_note_rejected(store, tmp_path: Path) -> None:
    spec = make_spec(interval=Interval.M1)
    dataset_id = compute_dataset_id(spec)
    row = bar_row(dataset_id, "RB2405", ns(2024, 1, 2, 21, 0))
    row["trading_date"] = None
    row["field_quality"] = None  # silent unknown day is not acceptable
    with pytest.raises(StoreError, match="field_quality"):
        import_rows(store, tmp_path, [row], spec)
    assert store.catalog.get_head(dataset_id, "2024") is None


def test_distinct_minutes_are_distinct_keys(store, tmp_path: Path) -> None:
    spec = make_spec(interval=Interval.M1)
    dataset_id = compute_dataset_id(spec)
    receipt = import_rows(
        store, tmp_path,
        [
            bar_row(dataset_id, "RB2405", ns(2024, 1, 2, 21, 0), trading=DAY1),
            bar_row(dataset_id, "RB2405", ns(2024, 1, 2, 21, 1), trading=DAY1),
        ],
        spec,
    )
    assert receipt.accepted_rows == 2
    head = store.catalog.get_head(dataset_id, "2024")
    assert store.catalog.get_revision(head)["rows"] == 2


def test_no_field_derives_trading_day_from_bar_start(store, tmp_path: Path) -> None:
    """Reading a NULL-day minute row must not surface any derived date."""

    spec = make_spec(interval=Interval.M1)
    dataset_id = compute_dataset_id(spec)
    row = bar_row(dataset_id, "RB2405", ns(2024, 1, 2, 23, 30))  # night session
    row["trading_date"] = None
    row["field_quality"] = json.dumps({"trading_date": "unknown_no_calendar"})
    import_rows(store, tmp_path, [row], spec)
    rows = _read_all(store, _freeze_all(store, dataset_id).snapshot_id, dataset_id)
    assert rows[0]["trading_date"] is None
