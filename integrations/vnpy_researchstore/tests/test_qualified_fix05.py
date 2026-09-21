"""Qualified-fix05 regression tests (actual Kimi, synthetic fixtures).

Closes the three accepted QUALIFIED_RECHECK_04 findings:

* F1 (HIGH): native dataset discovery (resolve_bar_dataset) scanned the whole
  symbol with the default qualified reader, so a default-qualified exclusion
  anywhere in the symbol's history refused CLEAN query windows. Discovery is
  now observational; consumer reads still enforce qualification for their
  effective requested range (including Alpha extended_days).
* F2 (MEDIUM): freeze() held the catalog transaction across full Parquet
  scans. The scan now runs outside the transaction over immutable file
  references captured inside it.
* F3 (MEDIUM): legacy manifests (no policy capture) were indistinguishable
  from captured-clean. They are now recognizably LEGACY UNQUALIFIED: default
  qualified reads refuse them, observational access is preserved, old bytes
  are never rewritten.

All fixture data is synthetic and clearly labelled.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from research_store import (
    CoverageGapError,
    KnownGap,
    Selection,
    SnapshotRequest,
    StoreError,
    freeze,
    open_snapshot,
)
from research_store.snapshots import load_snapshot_manifest

from conftest import bar_row, import_rows, make_spec, ns

from test_native_support import (
    DAILY_DATES,
    ensure_isolated_vnpy,
    freeze_all,
    import_dataset,
    make_database,
    make_lab,
)

INSTRUMENT = "000009"


def _daily_rows_with_excluded_day(exchange: str = "XSHE") -> list[dict[str, Any]]:
    """Five daily rows; ONLY day 1 carries a deterministic-repair flag."""
    rows = []
    for i, day in enumerate(DAILY_DATES):
        fq = None
        if i == 0:
            fq = json.dumps({"flags": ["repaired_deterministic"], "repair": {"old": 1.0}})
        row = bar_row(
            "DATASET",
            INSTRUMENT,
            ns(day.year, day.month, day.day, 1, 30),
            close=10.0 + i,
            volume=100.0,
            turnover=1000.0 + i,
            trading=day,
        )
        row["exchange"] = exchange
        row["field_quality"] = fq
        rows.append(row)
    return rows


def _native_dt(day: date) -> datetime:
    return datetime(day.year, day.month, day.day)


# ---------------------------------------------------------------------------
# F1 — clean separated range stays usable on all three native entry points
# ---------------------------------------------------------------------------


def test_f1_core_and_native_clean_range_with_exclusion_elsewhere(
    store, tmp_path: Path
) -> None:
    dataset_id = import_dataset(
        store, tmp_path, _daily_rows_with_excluded_day(), asset_name="daily.csv"
    )
    snapshot_id = freeze_all(store, [dataset_id])
    clean_start, clean_end = DAILY_DATES[2], DAILY_DATES[3]

    # Core reader over the clean range succeeds.
    with open_snapshot(store, snapshot_id) as reader:
        rows = [
            r
            for b in reader.bars(
                dataset_id,
                start=datetime(clean_start.year, clean_start.month, clean_start.day, tzinfo=timezone.utc),
                end=datetime(clean_end.year, clean_end.month, clean_end.day, 23, 59, tzinfo=timezone.utc),
                required_fields=(),
                allow_missing_auxiliary=True,
            )
            for r in b.to_pylist()
        ]
    assert len(rows) == 2

    ensure_isolated_vnpy()
    from vnpy.trader.constant import Exchange, Interval

    db = make_database(store.root, snapshot_id)
    try:
        bars = db.load_bar_data(
            INSTRUMENT, Exchange.SZSE, Interval.DAILY,
            _native_dt(clean_start), _native_dt(clean_end),
        )
        assert len(bars) == 2
    finally:
        db.close()

    lab = make_lab(tmp_path / "lab", store, snapshot_id)
    vt = f"{INSTRUMENT}.{Exchange.SZSE.value}"
    try:
        bars = lab.load_bar_data(
            vt, Interval.DAILY, _native_dt(clean_start), _native_dt(clean_end)
        )
        assert len(bars) == 2
        df = lab.load_bar_df(
            [vt], Interval.DAILY, _native_dt(clean_start), _native_dt(clean_end),
            extended_days=0,
        )
        assert df is not None and df.height == 2
    finally:
        lab.close()


def test_f1_selected_excluded_range_refuses_on_all_native_paths(
    store, tmp_path: Path
) -> None:
    dataset_id = import_dataset(
        store, tmp_path, _daily_rows_with_excluded_day(), asset_name="daily.csv"
    )
    snapshot_id = freeze_all(store, [dataset_id])
    excluded_day = DAILY_DATES[0]

    ensure_isolated_vnpy()
    from vnpy.trader.constant import Exchange, Interval

    db = make_database(store.root, snapshot_id)
    try:
        with pytest.raises(CoverageGapError, match="default-qualified exclusion"):
            db.load_bar_data(
                INSTRUMENT, Exchange.SZSE, Interval.DAILY,
                _native_dt(excluded_day), _native_dt(excluded_day),
            )
    finally:
        db.close()

    lab = make_lab(tmp_path / "lab", store, snapshot_id)
    vt = f"{INSTRUMENT}.{Exchange.SZSE.value}"
    try:
        with pytest.raises(CoverageGapError, match="default-qualified exclusion"):
            lab.load_bar_data(
                vt, Interval.DAILY, _native_dt(excluded_day), _native_dt(excluded_day)
            )
        with pytest.raises(CoverageGapError, match="default-qualified exclusion"):
            lab.load_bar_df(
                [vt], Interval.DAILY, _native_dt(excluded_day), _native_dt(excluded_day),
                extended_days=0,
            )
    finally:
        lab.close()


def test_f1_explicit_known_gap_leaves_excluded_rows_absent(
    store, tmp_path: Path
) -> None:
    dataset_id = import_dataset(
        store, tmp_path, _daily_rows_with_excluded_day(), asset_name="daily.csv"
    )
    day1 = DAILY_DATES[0]
    gap = KnownGap(
        dataset_id=dataset_id,
        start_ns=ns(day1.year, day1.month, day1.day, 1, 30),
        end_ns=ns(day1.year, day1.month, day1.day, 1, 30) + 60 * 1_000_000_000,
        reason="synthetic fixture: accepted known gap for deterministic repaired key",
    )
    ref = freeze(
        store,
        SnapshotRequest(selections=(Selection(dataset_id, "*"),), allow_known_gaps=(gap,)),
    )
    ensure_isolated_vnpy()
    from vnpy.trader.constant import Exchange, Interval

    db = make_database(store.root, ref.snapshot_id)
    try:
        bars = db.load_bar_data(
            INSTRUMENT, Exchange.SZSE, Interval.DAILY,
            _native_dt(DAILY_DATES[0]), _native_dt(DAILY_DATES[1]),
        )
        # The allowance permits the missing interval: day 1 stays absent,
        # day 2 is present — the rejected row is never returned.
        assert [b.datetime.date() for b in bars] == [DAILY_DATES[1]]
    finally:
        db.close()


def test_f1_nonaligned_endpoints_still_enforce_qualification(
    store, tmp_path: Path
) -> None:
    """A range that merely TOUCHES the excluded day (non-aligned endpoints)
    refuses; a range strictly before it succeeds."""
    dataset_id = import_dataset(
        store, tmp_path, _daily_rows_with_excluded_day(), asset_name="daily.csv"
    )
    snapshot_id = freeze_all(store, [dataset_id])
    day1 = DAILY_DATES[0]

    with open_snapshot(store, snapshot_id) as reader:
        # Strictly-before range: clean.
        rows = [
            r
            for b in reader.bars(
                dataset_id,
                start=datetime(day1.year, day1.month, day1.day, tzinfo=timezone.utc),
                end=datetime(day1.year, day1.month, day1.day, 1, 30, tzinfo=timezone.utc),
                required_fields=(),
                allow_missing_auxiliary=True,
            )
            for r in b.to_pylist()
        ]
        assert rows == []
        # Range ending one ns past the excluded bar start refuses.
        with pytest.raises(CoverageGapError):
            list(
                reader.bars(
                    dataset_id,
                    start=datetime(day1.year, day1.month, day1.day, tzinfo=timezone.utc),
                    end=datetime(
                        day1.year, day1.month, day1.day, 1, 30, 0, 1,
                        tzinfo=timezone.utc,
                    ),
                    required_fields=(),
                    allow_missing_auxiliary=True,
                )
            )


# ---------------------------------------------------------------------------
# F2 — freeze scans outside the catalog transaction, from captured refs only
# ---------------------------------------------------------------------------


def test_f2_freeze_scans_outside_transaction_and_ignores_later_head_moves(
    store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = make_spec()
    dataset_id = import_dataset(
        store, tmp_path, _daily_rows_with_excluded_day(), asset_name="w1.csv"
    )

    from research_store import catalog as catalog_module
    from research_store import quality as quality_module

    tx_active = False
    scan_saw_tx_active = False
    original_transaction = catalog_module.Catalog.transaction
    original_scan = quality_module.scan_exclusion_entries_in_files

    def spying_transaction(self, immediate: bool = False):
        nonlocal tx_active
        ctx = original_transaction(self, immediate=immediate)

        class _Spy:
            def __enter__(self):
                nonlocal tx_active
                tx_active = True
                return ctx.__enter__()

            def __exit__(self, *exc: object) -> Any:
                nonlocal tx_active
                tx_active = False
                return ctx.__exit__(*exc)

        return _Spy()

    def spying_scan(root: Path, ds_id: str, files: list[tuple[str, str, str]]):
        nonlocal scan_saw_tx_active
        scan_saw_tx_active = scan_saw_tx_active or tx_active
        # Simulate a concurrent writer advancing the head AFTER the capture:
        # publish a new flagged row for a later day before the scan runs.
        day = DAILY_DATES[3]
        row = bar_row(
            dataset_id,
            INSTRUMENT,
            ns(day.year, day.month, day.day, 1, 30),
            close=99.0,
            trading=day,
        )
        row["exchange"] = "XSHE"
        row["field_quality"] = json.dumps(
            {"flags": ["repaired_deterministic"], "repair": {"old": 2.0}}
        )
        import_rows(store, tmp_path, [row], spec, asset_name="w2.csv", asset_content=b"w2")
        return original_scan(root, ds_id, files)

    monkeypatch.setattr(catalog_module.Catalog, "transaction", spying_transaction)
    monkeypatch.setattr(quality_module, "scan_exclusion_entries_in_files", spying_scan)

    ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
    manifest = load_snapshot_manifest(store, ref.snapshot_id)

    assert scan_saw_tx_active is False, "exclusion scan ran inside the catalog transaction"
    # The capture reflects ONLY the revision captured in-transaction: the
    # later head (with the second flagged row) must not mix in.
    captured = manifest["default_qualified_exclusions"]
    assert len(captured) == 1
    assert captured[0]["source_label"] is None  # synthetic rows carry no label
    day1 = DAILY_DATES[0]
    assert captured[0]["start_ns"] == ns(day1.year, day1.month, day1.day, 1, 30)
    day4 = DAILY_DATES[3]
    assert captured[0]["start_ns"] != ns(day4.year, day4.month, day4.day, 1, 30)


# ---------------------------------------------------------------------------
# F3 — legacy manifests are recognizably unqualified; bytes preserved
# ---------------------------------------------------------------------------


def test_f3_legacy_manifest_default_and_native_refusal_observational_preserved(
    store, tmp_path: Path
) -> None:
    dataset_id = import_dataset(
        store, tmp_path, _daily_rows_with_excluded_day(), asset_name="daily.csv"
    )
    ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
    manifest = load_snapshot_manifest(store, ref.snapshot_id)
    assert manifest["snapshot_format"] == 2

    legacy = dict(manifest)
    legacy.pop("default_qualified_exclusions")
    legacy["snapshot_format"] = 1
    legacy["snapshot_id"] = "snap-legacyqfix05000"
    legacy_path = store.root / "manifests" / "snapshots" / "snap-legacyqfix05000.json"
    legacy_bytes = json.dumps(legacy).encode("utf-8")
    legacy_path.write_bytes(legacy_bytes)
    try:
        with open_snapshot(store, "snap-legacyqfix05000") as reader:
            assert reader.default_qualified_status(dataset_id) == "legacy_unqualified"
            with pytest.raises(CoverageGapError, match="predates the default-qualified"):
                list(
                    reader.bars(
                        dataset_id, required_fields=(), allow_missing_auxiliary=True
                    )
                )
            # Observational access preserved.
            rows = [
                r
                for b in reader.bars(
                    dataset_id,
                    required_fields=(),
                    allow_missing_auxiliary=True,
                    include_default_excluded=True,
                )
                for r in b.to_pylist()
            ]
            assert len(rows) == 5

        ensure_isolated_vnpy()
        from vnpy.trader.constant import Exchange, Interval

        db = make_database(store.root, "snap-legacyqfix05000")
        try:
            with pytest.raises(CoverageGapError, match="predates the default-qualified"):
                db.load_bar_data(
                    INSTRUMENT, Exchange.SZSE, Interval.DAILY,
                    _native_dt(DAILY_DATES[2]), _native_dt(DAILY_DATES[3]),
                )
            with pytest.raises(StoreError, match="predates the default-qualified"):
                db.get_bar_overview()
        finally:
            db.close()
        # Old bytes unchanged.
        assert legacy_path.read_bytes() == legacy_bytes
    finally:
        legacy_path.unlink()


def test_f3_new_clean_snapshot_is_qualified_and_usable(store, tmp_path: Path) -> None:
    dataset_id = import_dataset(
        store, tmp_path, _daily_rows_with_excluded_day(), asset_name="daily.csv"
    )
    ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
    with open_snapshot(store, ref.snapshot_id) as reader:
        assert reader.default_qualified_status(dataset_id) == "qualified"
        assert len(reader.default_qualified_exclusions(dataset_id)) == 1
