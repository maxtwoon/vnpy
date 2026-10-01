"""ResearchAlphaLab tests: snapshot-bound lab dir, read-only data, interval
scope, VWAP/multiplier/zero-volume semantics, inclusive end after
extended_days, and unknown-semantics refusals."""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from research_store import (
    Adjustment,
    AssetClass,
    ReadOnlyError,
    Store,
    StoreError,
    UnsupportedCapabilityError,
)
from research_store import Interval as RSInterval

from test_native_support import (
    DAILY_DATES,
    daily_rows,
    freeze_all,
    import_dataset,
    make_lab,
    minute_rows,
    untrusted_quality,
    vt_constants,
)

# Bound at test-run time, never at collection time (see test_native_database).
VtInterval: Any = None


@pytest.fixture(scope="module", autouse=True)
def _bind_vnpy() -> None:
    global VtInterval
    _, VtInterval = vt_constants()


@pytest.fixture()
def daily_env(store: Store, tmp_path: Path):
    dataset_id = import_dataset(
        store, tmp_path, daily_rows("000001"), asset_name="daily.csv"
    )
    snapshot_id = freeze_all(store, [dataset_id])
    return store, snapshot_id, dataset_id


class TestLabBinding:
    def test_snapshot_bound_resultdir(self, daily_env, tmp_path: Path) -> None:
        store, snapshot_id, _ = daily_env
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        assert lab.lab_path == (tmp_path / "lab" / snapshot_id)
        assert (tmp_path / "lab" / ".researchstore_snapshot").exists()
        lab.close()

    def test_incompatible_reuse_rejected(self, daily_env, tmp_path: Path) -> None:
        store, snapshot_id, _ = daily_env
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        lab.close()
        # rebind with the same snapshot is fine
        make_lab(tmp_path / "lab", store, snapshot_id).close()
        # a different snapshot id over the same lab root is rejected
        other = import_dataset(
            store,
            tmp_path,
            daily_rows("000002"),
            asset_name="other.csv",
            source_id="synthetic-other",
        )
        other_snapshot = freeze_all(store, [other])
        assert other_snapshot != snapshot_id
        with pytest.raises(StoreError, match="refusing reuse"):
            make_lab(tmp_path / "lab", store, other_snapshot)

    def test_market_data_save_prohibited(self, daily_env, tmp_path: Path) -> None:
        store, snapshot_id, _ = daily_env
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        with pytest.raises(ReadOnlyError):
            lab.save_bar_data([])
        lab.close()


class TestLoadBarData:
    def test_daily_inclusive_end(self, daily_env, tmp_path: Path) -> None:
        store, snapshot_id, _ = daily_env
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        bars = lab.load_bar_data(
            "000001.SZSE", VtInterval.DAILY, "2024-01-03", "2024-01-05"
        )
        assert [b.datetime for b in bars] == [
            datetime(2024, 1, 3),
            datetime(2024, 1, 4),
            datetime(2024, 1, 5),
        ]
        lab.close()

    def test_minute_supported_hour_rejected(
        self, store: Store, tmp_path: Path
    ) -> None:
        minute_id = import_dataset(
            store,
            tmp_path,
            minute_rows("000001"),
            asset_name="minute.csv",
            interval=RSInterval.M1,
        )
        hourly_id = import_dataset(
            store,
            tmp_path,
            minute_rows("000001"),
            asset_name="hourly.csv",
            interval=RSInterval.H1,
        )
        snapshot_id = freeze_all(store, [minute_id, hourly_id])
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        bars = lab.load_bar_data(
            "000001.SZSE", "1m", datetime(2024, 1, 1), datetime(2024, 1, 3)
        )
        assert len(bars) == 6
        with pytest.raises(UnsupportedCapabilityError):
            lab.load_bar_data(
                "000001.SZSE", VtInterval.HOUR, datetime(2024, 1, 1), datetime(2024, 1, 3)
            )
        lab.close()

    def test_minute_null_trading_date_refused(
        self, store: Store, tmp_path: Path
    ) -> None:
        import json

        rows = minute_rows("000001", trading=None)
        for row in rows:
            # publish requires the unknown day to stay visible quality metadata
            row["field_quality"] = json.dumps(
                {"flags": ["trading_date_unknown_no_calendar"]}
            )
        dataset_id = import_dataset(
            store,
            tmp_path,
            rows,
            asset_name="minute-null-date.csv",
            interval=RSInterval.M1,
        )
        snapshot_id = freeze_all(store, [dataset_id])
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        with pytest.raises(StoreError, match="trading_date"):
            lab.load_bar_data(
                "000001.SZSE", VtInterval.MINUTE, datetime(2024, 1, 1), datetime(2024, 1, 3)
            )
        lab.close()

    def test_unknown_adjustment_refused(self, store: Store, tmp_path: Path) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            daily_rows("000001"),
            asset_name="jq-like.csv",
            adjustment=Adjustment.UNKNOWN,
        )
        snapshot_id = freeze_all(store, [dataset_id])
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        with pytest.raises(StoreError, match="adjustment unknown"):
            lab.load_bar_data(
                "000001.SZSE", VtInterval.DAILY, "2024-01-01", "2024-01-31"
            )
        lab.close()


class TestLoadBarDf:
    def test_columns_normalization_and_vwap(self, daily_env, tmp_path: Path) -> None:
        store, snapshot_id, _ = daily_env
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        df = lab.load_bar_df(["000001.SZSE"], VtInterval.DAILY, "2024-01-02", "2024-01-08", 0)
        assert df is not None
        assert df.columns == [
            "datetime",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "open_interest",
            "vwap",
            "vt_symbol",
        ]
        assert df.height == len(DAILY_DATES)
        # OHLC first-close normalization: close_0 = 10 -> close 10,11,... -> 1.0,1.1,...
        closes = df["close"].to_list()
        assert closes[0] == pytest.approx(1.0)
        assert closes[1] == pytest.approx(1.1)
        # equity VWAP: turnover/volume (turnover 1000+i, volume 100)
        assert df["vwap"].to_list()[0] == pytest.approx(10.0)
        assert set(df["vt_symbol"].to_list()) == {"000001.SZSE"}
        lab.close()

    def test_inclusive_end_survives_extended_days(
        self, daily_env, tmp_path: Path
    ) -> None:
        store, snapshot_id, _ = daily_env
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        df = lab.load_bar_df(["000001.SZSE"], VtInterval.DAILY, "2024-01-04", "2024-01-05", 2)
        assert df is not None
        dates = [dt.date() if hasattr(dt, "date") else dt for dt in df["datetime"].to_list()]
        assert datetime(2024, 1, 5).date() in dates  # exact end bar survives
        assert max(dates) == datetime(2024, 1, 5).date()  # no padded extra day
        lab.close()

    def test_empty_request_and_empty_window_stable(
        self, daily_env, tmp_path: Path
    ) -> None:
        store, snapshot_id, _ = daily_env
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        assert lab.load_bar_df([], VtInterval.DAILY, "2024-01-01", "2024-01-31", 0) is None
        assert (
            lab.load_bar_df(["000001.SZSE"], VtInterval.DAILY, "2025-01-01", "2025-01-31", 0)
            is None
        )
        lab.close()

    def test_zero_volume_vwap_nan(self, store: Store, tmp_path: Path) -> None:
        rows = daily_rows("000008", volume=0.0, turnover=0.0)
        dataset_id = import_dataset(store, tmp_path, rows, asset_name="zero-vol.csv")
        snapshot_id = freeze_all(store, [dataset_id])
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        df = lab.load_bar_df(["000008.SZSE"], VtInterval.DAILY, "2024-01-02", "2024-01-08", 0)
        assert df is not None
        assert all(math.isnan(v) for v in df["vwap"].to_list())
        lab.close()

    def test_missing_turnover_refused_by_default(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            daily_rows("000009", turnover=None),
            asset_name="no-turnover.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        with pytest.raises(StoreError):
            lab.load_bar_df(["000009.SZSE"], VtInterval.DAILY, "2024-01-02", "2024-01-08", 0)
        lab.close()

    def test_untrusted_turnover_refused(self, store: Store, tmp_path: Path) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            daily_rows("000010", field_quality=untrusted_quality()),
            asset_name="untrusted.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        with pytest.raises(StoreError, match="untrusted"):
            lab.load_bar_df(["000010.SZSE"], VtInterval.DAILY, "2024-01-02", "2024-01-08", 0)
        lab.close()

    def test_futures_requires_verified_multiplier(
        self, store: Store, tmp_path: Path
    ) -> None:
        rows = daily_rows(
            "rb2505", exchange="XSGE", open_interest=500.0, turnover=100000.0
        )
        dataset_id = import_dataset(
            store,
            tmp_path,
            rows,
            asset_name="futures.csv",
            asset_class=AssetClass.FUTURES,
            volume_unit="lot",
        )
        snapshot_id = freeze_all(store, [dataset_id])

        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        with pytest.raises(StoreError, match="multiplier"):
            lab.load_bar_df(["rb2505.SHFE"], VtInterval.DAILY, "2024-01-02", "2024-01-08", 0)
        lab.close()

        lab = make_lab(
            tmp_path / "lab2",
            store,
            snapshot_id,
            multipliers={"rb2505.SHFE": 10.0},
        )
        df = lab.load_bar_df(["rb2505.SHFE"], VtInterval.DAILY, "2024-01-02", "2024-01-08", 0)
        assert df is not None
        # futures VWAP: turnover / (volume * multiplier) = 100000 / (100 * 10)
        assert df["vwap"].to_list()[0] == pytest.approx(100.0)
        lab.close()

    def test_futures_unverified_volume_unit_refused(
        self, store: Store, tmp_path: Path
    ) -> None:
        rows = daily_rows("rb2505", exchange="XSGE", open_interest=500.0)
        dataset_id = import_dataset(
            store,
            tmp_path,
            rows,
            asset_name="futures-unknown-unit.csv",
            asset_class=AssetClass.FUTURES,
            volume_unit="unknown",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        lab = make_lab(
            tmp_path / "lab",
            store,
            snapshot_id,
            multipliers={"rb2505.SHFE": 10.0},
        )
        with pytest.raises(StoreError, match="volume unit"):
            lab.load_bar_df(["rb2505.SHFE"], VtInterval.DAILY, "2024-01-02", "2024-01-08", 0)
        lab.close()

    def test_suspended_row_mask_preserved(self, store: Store, tmp_path: Path) -> None:
        # All-zero numeric row (suspended): vwap NaN via volume==0 keeps the
        # native mask semantics (sum over numerics is NaN -> row preserved).
        rows = daily_rows("000011", close0=0.0, volume=0.0, turnover=0.0)
        for row in rows:
            row["open"] = row["high"] = row["low"] = row["close"] = 0.0
        dataset_id = import_dataset(store, tmp_path, rows, asset_name="susp.csv")
        snapshot_id = freeze_all(store, [dataset_id])
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        df = lab.load_bar_df(["000011.SZSE"], VtInterval.DAILY, "2024-01-02", "2024-01-08", 0)
        assert df is not None
        assert df.height == len(DAILY_DATES)
        assert all(math.isnan(v) for v in df["vwap"].to_list())
        lab.close()
