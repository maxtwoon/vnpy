"""Native Database bridge tests: read-only contract, inclusive end, dataset
resolution, semantic refusals, auxiliary degradation and snapshot-only
overview."""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from research_store import (
    MissingFieldDataError,
    ReadOnlyError,
    Store,
    StoreError,
    UnsupportedCapabilityError,
)
from research_store import Interval as RSInterval

from test_native_support import (
    AssetClass,
    DAILY_DATES,
    daily_rows,
    freeze_all,
    import_dataset,
    make_database,
    minute_rows,
    native_minute_dt,
    untrusted_quality,
    vt_constants,
)

# Bound by the autouse fixture at test-run time (never at collection time, so
# the core "no vnpy side effects" purity test still sees a vnpy-free process).
Exchange: Any = None
VtInterval: Any = None


@pytest.fixture(scope="module", autouse=True)
def _bind_vnpy() -> None:
    global Exchange, VtInterval
    Exchange, VtInterval = vt_constants()


@pytest.fixture()
def daily_snapshot(store: Store, tmp_path: Path):
    """Store with one daily equity dataset (000001.XSHE) frozen."""
    dataset_id = import_dataset(
        store, tmp_path, daily_rows("000001"), asset_name="daily.csv"
    )
    snapshot_id = freeze_all(store, [dataset_id])
    return store, snapshot_id, dataset_id


class TestReadOnlyContract:
    def test_save_and_delete_raise(self, daily_snapshot) -> None:
        store, snapshot_id, _ = daily_snapshot
        db = make_database(store.root, snapshot_id)
        with pytest.raises(ReadOnlyError):
            db.save_bar_data([])
        with pytest.raises(ReadOnlyError):
            db.save_tick_data([])
        with pytest.raises(ReadOnlyError):
            db.delete_bar_data("000001", Exchange.SZSE, VtInterval.DAILY)
        with pytest.raises(ReadOnlyError):
            db.delete_tick_data("000001", Exchange.SZSE)
        db.close()

    def test_tick_load_unsupported(self, daily_snapshot) -> None:
        store, snapshot_id, _ = daily_snapshot
        db = make_database(store.root, snapshot_id)
        with pytest.raises(UnsupportedCapabilityError):
            db.load_tick_data(
                "000001", Exchange.SZSE, datetime(2024, 1, 2), datetime(2024, 1, 3)
            )
        assert db.get_tick_overview() == []
        db.close()


class TestInclusiveEnd:
    def test_daily_final_bar_equals_end(self, daily_snapshot) -> None:
        store, snapshot_id, _ = daily_snapshot
        db = make_database(store.root, snapshot_id)
        bars = db.load_bar_data(
            "000001",
            Exchange.SZSE,
            VtInterval.DAILY,
            datetime(2024, 1, 3),
            datetime(2024, 1, 5),
        )
        assert [b.datetime for b in bars] == [
            datetime(2024, 1, 3),
            datetime(2024, 1, 4),
            datetime(2024, 1, 5),
        ]
        assert bars[-1].datetime == datetime(2024, 1, 5)  # inclusive end survives
        db.close()

    def test_minute_exact_and_nonaligned_end(self, store: Store, tmp_path: Path) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            minute_rows("000001"),
            asset_name="minute.csv",
            interval=RSInterval.M1,
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)

        start = native_minute_dt(0)
        exact_end = native_minute_dt(3)
        bars = db.load_bar_data(
            "000001", Exchange.SZSE, VtInterval.MINUTE, start, exact_end
        )
        assert len(bars) == 4
        assert bars[-1].datetime == exact_end  # bar at exactly `end` included

        nonaligned = exact_end.replace(second=30)
        bars = db.load_bar_data(
            "000001", Exchange.SZSE, VtInterval.MINUTE, start, nonaligned
        )
        assert len(bars) == 4  # no padding of an extra bar
        assert bars[-1].datetime == exact_end
        db.close()


class TestDatasetResolution:
    def test_unknown_symbol_returns_empty(self, daily_snapshot) -> None:
        store, snapshot_id, _ = daily_snapshot
        db = make_database(store.root, snapshot_id)
        bars = db.load_bar_data(
            "999999",
            Exchange.SZSE,
            VtInterval.DAILY,
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
        )
        assert bars == []
        db.close()

    def test_wrong_exchange_returns_empty(self, daily_snapshot) -> None:
        store, snapshot_id, _ = daily_snapshot
        db = make_database(store.root, snapshot_id)
        bars = db.load_bar_data(
            "000001",
            Exchange.SSE,  # stored label XSHE maps to SZSE, not SSE
            VtInterval.DAILY,
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
        )
        assert bars == []
        db.close()

    def test_unmapped_exchange_label_refuses(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            daily_rows("000003", exchange="XZZZ"),
            asset_name="unknown-exchange.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        with pytest.raises(StoreError, match="unmapped exchange label"):
            db.load_bar_data(
                "000003",
                Exchange.SZSE,
                VtInterval.DAILY,
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
            )
        db.close()

    def test_ambiguous_datasets_refused(self, store: Store, tmp_path: Path) -> None:
        first = import_dataset(
            store, tmp_path, daily_rows("000004"), asset_name="a.csv"
        )
        second = import_dataset(
            store,
            tmp_path,
            daily_rows("000004"),
            asset_name="b.csv",
            source_id="synthetic-b",
        )
        assert first != second
        snapshot_id = freeze_all(store, [first, second])
        db = make_database(store.root, snapshot_id)
        with pytest.raises(StoreError, match="ambiguous"):
            db.load_bar_data(
                "000004",
                Exchange.SZSE,
                VtInterval.DAILY,
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
            )
        db.close()


class TestAuxiliarySemantics:
    def test_missing_turnover_default_refusal(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            daily_rows("000005", turnover=None),
            asset_name="no-turnover.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        with pytest.raises(MissingFieldDataError):
            db.load_bar_data(
                "000005",
                Exchange.SZSE,
                VtInterval.DAILY,
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
            )
        db.close()

    def test_explicit_ohlcv_mode_returns_nan_with_receipt(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            daily_rows("000005", turnover=None),
            asset_name="no-turnover.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id, allow_missing_auxiliary=True)
        bars = db.load_bar_data(
            "000005",
            Exchange.SZSE,
            VtInterval.DAILY,
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
        )
        assert len(bars) == len(DAILY_DATES)
        assert all(math.isnan(b.turnover) for b in bars)
        assert all(
            b.extra["auxiliary"]["turnover"] == "missing_auxiliary_nan" for b in bars
        )
        receipt = db.last_receipt
        assert receipt.dataset_id == dataset_id
        assert receipt.snapshot_id == snapshot_id
        assert receipt.missing_turnover_rows == len(DAILY_DATES)
        assert receipt.allow_missing_auxiliary is True
        db.close()

    def test_equity_open_interest_explicit_zero(self, daily_snapshot) -> None:
        store, snapshot_id, _ = daily_snapshot
        db = make_database(store.root, snapshot_id)
        bars = db.load_bar_data(
            "000001",
            Exchange.SZSE,
            VtInterval.DAILY,
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
        )
        assert bars
        assert all(b.open_interest == 0.0 for b in bars)
        assert all(
            b.extra["auxiliary"]["open_interest"] == "not_applicable_explicit_zero"
            for b in bars
        )
        db.close()

    def test_futures_missing_open_interest_refusal(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            daily_rows("rb2505", exchange="XSGE", open_interest=None),
            asset_name="futures-no-oi.csv",
            asset_class=AssetClass.FUTURES,
            volume_unit="lot",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        with pytest.raises(MissingFieldDataError):
            db.load_bar_data(
                "rb2505",
                Exchange.SHFE,
                VtInterval.DAILY,
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
            )
        db.close()

    def test_untrusted_turnover_default_refusal(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            daily_rows("000006", field_quality=untrusted_quality()),
            asset_name="untrusted.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        with pytest.raises(MissingFieldDataError, match="untrusted"):
            db.load_bar_data(
                "000006",
                Exchange.SZSE,
                VtInterval.DAILY,
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
            )
        db.close()

    def test_untrusted_turnover_explicit_mode_nan(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            daily_rows("000006", field_quality=untrusted_quality()),
            asset_name="untrusted.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id, allow_missing_auxiliary=True)
        bars = db.load_bar_data(
            "000006",
            Exchange.SZSE,
            VtInterval.DAILY,
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
        )
        assert all(math.isnan(b.turnover) for b in bars)
        assert all(
            b.extra["auxiliary"]["turnover"] == "untrusted_turnover_nan" for b in bars
        )
        assert db.last_receipt.untrusted_turnover_rows == len(DAILY_DATES)
        db.close()

    def test_unknown_volume_unit_refusal(self, store: Store, tmp_path: Path) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            daily_rows("000007"),
            asset_name="unknown-units.csv",
            volume_unit="unknown",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        with pytest.raises(StoreError, match="volume unit unknown"):
            db.load_bar_data(
                "000007",
                Exchange.SZSE,
                VtInterval.DAILY,
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
            )
        db.close()


class TestOverviewAndProvenance:
    def test_overview_snapshot_only_omits_unsupported_intervals(
        self, store: Store, tmp_path: Path
    ) -> None:
        daily_id = import_dataset(
            store, tmp_path, daily_rows("000001"), asset_name="daily.csv"
        )
        minute_id = import_dataset(
            store,
            tmp_path,
            minute_rows("000001"),
            asset_name="minute.csv",
            interval=RSInterval.M1,
        )
        five_min_id = import_dataset(
            store,
            tmp_path,
            minute_rows("000002"),
            asset_name="five.csv",
            interval=RSInterval.M5,
        )
        snapshot_id = freeze_all(store, [daily_id, minute_id, five_min_id])
        db = make_database(store.root, snapshot_id)

        overview = db.get_bar_overview()
        by_key = {(o.symbol, o.interval): o for o in overview}
        daily = by_key[("000001", VtInterval.DAILY)]
        assert daily.count == len(DAILY_DATES)
        assert daily.exchange == Exchange.SZSE
        assert daily.start is not None and daily.end is not None
        assert daily.start < daily.end
        minute = by_key[("000001", VtInterval.MINUTE)]
        assert minute.count == 6
        # The 5m dataset is omitted, never relabelled as 1m...
        assert all(o.symbol != "000002" for o in overview)
        # ...and the omission is reported in diagnostics
        assert any(five_min_id in note for note in db.diagnostics)
        db.close()

    def test_bar_extra_provenance(self, daily_snapshot) -> None:
        store, snapshot_id, dataset_id = daily_snapshot
        db = make_database(store.root, snapshot_id)
        bars = db.load_bar_data(
            "000001",
            Exchange.SZSE,
            VtInterval.DAILY,
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
        )
        extra = bars[0].extra
        assert extra["snapshot_id"] == snapshot_id
        assert extra["dataset_id"] == dataset_id
        assert extra["source_id"] == "synthetic"
        assert extra["source_symbol"] == "000001"
        assert extra["source_exchange_label"] == "XSHE"
        assert extra["trading_date"] == "2024-01-02"
        assert extra["provenance"]["batch_id"]
        db.close()
