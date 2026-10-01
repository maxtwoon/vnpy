"""Reader tests: half-open ranges, NULL round-trip, field requirements,
integrity failures, and error taxonomy."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from research_store import (
    IntegrityError,
    MissingFieldDataError,
    Selection,
    SnapshotRequest,
    StoreError,
    UnavailableFieldError,
    UnknownDatasetError,
    compute_dataset_id,
    freeze,
    open_snapshot,
)

from conftest import bar_row, import_rows, make_spec, ns

from research_store import Interval

START = datetime(2024, 1, 2, 9, 30, tzinfo=timezone.utc)
MID = datetime(2024, 1, 2, 9, 31, tzinfo=timezone.utc)
END = datetime(2024, 1, 2, 9, 32, tzinfo=timezone.utc)


def _dataset_with_rows(store, tmp_path: Path, rows: list[dict]):
    # Minute datasets key on bar_start, which is what reader range tests
    # exercise; daily datasets key on (identity, trading_date).
    spec = make_spec(interval=Interval.M1)
    dataset_id = compute_dataset_id(spec)
    import_rows(store, tmp_path, rows, spec)
    ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
    return dataset_id, ref.snapshot_id


def test_half_open_range_boundaries(store, tmp_path: Path) -> None:
    dataset_id, snap = _dataset_with_rows(store, tmp_path, [
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 30)),
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 31)),
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 32)),
    ])
    with open_snapshot(store, snap) as reader:
        batches = list(reader.bars(dataset_id, start=START, end=END))
    starts = sorted(
        row["bar_start"] for batch in batches for row in batch.to_pylist()
    )
    # [start, end): the bar exactly AT end is excluded, the one at start kept.
    assert starts == [ns(2024, 1, 2, 9, 30), ns(2024, 1, 2, 9, 31)]


def test_null_measures_round_trip(store, tmp_path: Path) -> None:
    dataset_id, snap = _dataset_with_rows(store, tmp_path, [
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 30), turnover=None, open_interest=None),
    ])
    with open_snapshot(store, snap) as reader:
        rows = [r for b in reader.bars(dataset_id) for r in b.to_pylist()]
    assert rows[0]["turnover"] is None  # real NULL, never zero-filled
    assert rows[0]["open_interest"] is None


def test_required_ohlcv_nulls_always_error(store, tmp_path: Path) -> None:
    dataset_id, snap = _dataset_with_rows(store, tmp_path, [
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 30), close=None),
    ])
    with open_snapshot(store, snap) as reader:
        with pytest.raises(MissingFieldDataError):
            list(reader.bars(dataset_id))
        # OHLCV never passes through as NaN even with the auxiliary escape.
        with pytest.raises(MissingFieldDataError):
            list(reader.bars(dataset_id, allow_missing_auxiliary=True))


def test_auxiliary_nulls_error_by_default_pass_when_explicit(store, tmp_path: Path) -> None:
    dataset_id, snap = _dataset_with_rows(store, tmp_path, [
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 30), turnover=None),
    ])
    with open_snapshot(store, snap) as reader:
        with pytest.raises(MissingFieldDataError, match="turnover"):
            list(reader.bars(dataset_id, required_fields=("open", "close", "turnover")))
        rows = [
            r for b in reader.bars(
                dataset_id,
                required_fields=("open", "close", "turnover"),
                allow_missing_auxiliary=True,
            )
            for r in b.to_pylist()
        ]
    assert rows[0]["turnover"] is None  # explicit NaN passthrough, not fake 0


def test_unavailable_field_and_unknown_dataset(store, tmp_path: Path) -> None:
    dataset_id, snap = _dataset_with_rows(store, tmp_path, [
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 30)),
    ])
    with open_snapshot(store, snap) as reader:
        with pytest.raises(UnavailableFieldError):
            list(reader.bars(dataset_id, required_fields=("vwap",)))
        with pytest.raises(UnknownDatasetError):
            list(reader.bars("ds-not-in-snapshot"))


def test_no_data_is_empty_stream_not_error(store, tmp_path: Path) -> None:
    dataset_id, snap = _dataset_with_rows(store, tmp_path, [
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 30)),
    ])
    with open_snapshot(store, snap) as reader:
        out = list(reader.bars(
            dataset_id,
            start=datetime(2030, 1, 1, tzinfo=timezone.utc),
            end=datetime(2030, 1, 2, tzinfo=timezone.utc),
        ))
        rows = [r for b in out for r in b.to_pylist()]
    assert rows == []


def test_instrument_filter_and_ordering(store, tmp_path: Path) -> None:
    dataset_id, snap = _dataset_with_rows(store, tmp_path, [
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 30)),
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 31)),
        bar_row("ds", "000002", ns(2024, 1, 2, 9, 30)),
    ])
    with open_snapshot(store, snap) as reader:
        rows = [
            r for b in reader.bars(dataset_id, instruments=["000001"])
            for r in b.to_pylist()
        ]
    assert [r["bar_start"] for r in rows] == [ns(2024, 1, 2, 9, 30), ns(2024, 1, 2, 9, 31)]


def test_naive_datetime_rejected(store, tmp_path: Path) -> None:
    dataset_id, snap = _dataset_with_rows(store, tmp_path, [
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 30)),
    ])
    with open_snapshot(store, snap) as reader:
        with pytest.raises(StoreError, match="naive"):
            list(reader.bars(dataset_id, start=datetime(2024, 1, 2)))


def test_missing_and_tampered_pinned_files_fail(store, tmp_path: Path) -> None:
    dataset_id, snap = _dataset_with_rows(store, tmp_path, [
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 30)),
    ])
    obj = next(store.path.objects.rglob("*.parquet"))

    obj.rename(obj.with_suffix(".hidden"))
    with open_snapshot(store, snap) as reader:
        with pytest.raises(IntegrityError, match="missing"):
            list(reader.bars(dataset_id))

    obj.with_suffix(".hidden").rename(obj)
    payload = bytearray(obj.read_bytes())
    payload[-10] ^= 0xFF
    obj.write_bytes(bytes(payload))
    with open_snapshot(store, snap) as reader:
        with pytest.raises(IntegrityError, match="tampered"):
            list(reader.bars(dataset_id))
