"""Validation contract tests: time and field requirements are hard errors.

These tests pin invariants (non-finite rejection, sortedness, identity,
half-open bar times); they do not mirror implementation details.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from research_store import Interval, StoreError, compute_dataset_id

from conftest import bar_row, bars_batch, import_rows, make_asset, make_spec, ns


def _expect_reject(store, tmp_path: Path, rows: list[dict], needle: str, spec=None) -> None:
    spec = spec or make_spec()
    with pytest.raises(StoreError, match=needle):
        import_rows(store, tmp_path, rows, spec)
    # a rejected import must not move the partition head
    assert store.catalog.get_head(compute_dataset_id(spec), "2024") is None


def test_bar_end_must_exceed_bar_start(store, tmp_path: Path) -> None:
    row = bar_row("ds", "000001", ns(2024, 1, 2, 9, 30))
    row["bar_end"] = row["bar_start"]
    _expect_reject(store, tmp_path, [row], "bar_end")


def test_unsorted_stream_rejected(store, tmp_path: Path) -> None:
    # minute spec: identity key is bar_start, so order violations are visible
    spec = make_spec(interval=Interval.M1)
    rows = [
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 31)),
        bar_row("ds", "000001", ns(2024, 1, 2, 9, 30)),
    ]
    _expect_reject(store, tmp_path, rows, "sorted", spec)


def test_duplicate_keys_within_stream_rejected(store, tmp_path: Path) -> None:
    spec = make_spec(interval=Interval.M1)
    rows = [bar_row("ds", "000001", ns(2024, 1, 2, 9, 30))] * 2
    _expect_reject(store, tmp_path, rows, "duplicate", spec)


def test_nonfinite_values_rejected_not_silently_stored(store, tmp_path: Path) -> None:
    rows = [bar_row("ds", "000001", ns(2024, 1, 2, 9, 30), close=math.inf)]
    _expect_reject(store, tmp_path, rows, "non-finite")
    rows = [bar_row("ds", "000001", ns(2024, 1, 2, 9, 30), volume=math.nan)]
    _expect_reject(store, tmp_path, rows, "non-finite")


def test_exactly_one_of_instrument_or_series(store, tmp_path: Path) -> None:
    both = bar_row("ds", "000001", ns(2024, 1, 2, 9, 30))
    both["series_id"] = "000001.888"  # instrument_id already set: both present
    _expect_reject(store, tmp_path, [both], "exactly one")

    neither = bar_row("ds", "000001", ns(2024, 1, 2, 9, 30))
    neither["instrument_id"] = None
    _expect_reject(store, tmp_path, [neither], "exactly one")


def test_invalid_completeness_rejected(store, tmp_path: Path) -> None:
    row = bar_row("ds", "000001", ns(2024, 1, 2, 9, 30))
    row["completeness"] = "maybe"
    _expect_reject(store, tmp_path, [row], "completeness")


def test_mismatched_dataset_id_rejected(store, tmp_path: Path) -> None:
    from research_store import ImportRequest, import_asset

    spec = make_spec()
    row = bar_row("ds-WRONG", "000001", ns(2024, 1, 2, 9, 30))  # not this spec's id
    request = ImportRequest(
        asset=make_asset(tmp_path, "mismatch.csv", b"x"),
        spec=spec, adapter="synthetic/0.1", config={"member": "mismatch.csv"},
        partitions=("2024",),
    )
    with pytest.raises(StoreError, match="dataset_id"):
        import_asset(store, request, lambda _p: iter([bars_batch([row])]))
    assert store.catalog.get_head(compute_dataset_id(spec), "2024") is None
