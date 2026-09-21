"""Regressions for the two verified native02 audit findings (native fix03).

F1 — exchange validation over the WHOLE streamed row range of the requested
symbol: resolution inspects every emitted batch (never just the first), so a
later unmapped/NULL/mismatched label refuses instead of being silently
stamped with the requested exchange; an empty leading batch is not evidence
of absence; ambiguity/unmapped-label policies are unchanged; Database and
ResearchAlphaLab share the helper and both refuse.

F2 — DAILY overview identity/bounds come from ``trading_date`` (the same
native convention ``load_bar_data`` uses), never the tz-converted
``bar_start``; MINUTE/HOUR overview keeps ``bar_start`` semantics; the
shipped ``native_overview`` CLI prints the same boundaries.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from research_store import AssetClass, ImportRequest, Store, StoreError
from research_store import Interval as RSInterval
from research_store import compute_dataset_id, import_asset

from conftest import bar_row, bars_batch, make_asset, make_spec, ns
from test_native_bootstrap import run_tool, write_config
from test_native_support import (
    daily_rows,
    freeze_all,
    import_dataset,
    make_database,
    make_lab,
    minute_rows,
    native_minute_dt,
    vt_constants,
)

# Bound at test-run time, never at collection time (see test_native_database).
Exchange: Any = None
VtInterval: Any = None


@pytest.fixture(scope="module", autouse=True)
def _bind_vnpy() -> None:
    global Exchange, VtInterval
    Exchange, VtInterval = vt_constants()


# ---------------------------------------------------------------------------
# F1, helper level: resolve_bar_dataset against a controlled batch stream
# ---------------------------------------------------------------------------


class _StubReader:
    """SnapshotReader stand-in whose bars() replays prebuilt batches."""

    def __init__(self, batches: dict[str, list[pa.RecordBatch]]) -> None:
        self._batches = batches
        self.snapshot_id = "snap-stub"

    def bars(self, dataset_id: str, **_kwargs: Any) -> Iterator[pa.RecordBatch]:
        return iter(self._batches.get(dataset_id, []))


def _exchange_batch(*labels: str | None) -> pa.RecordBatch:
    schema = pa.schema(
        [
            pa.field("exchange", pa.string(), nullable=True),
            pa.field("instrument_id", pa.string(), nullable=True),
            pa.field("series_id", pa.string(), nullable=True),
        ]
    )
    return pa.RecordBatch.from_pydict(
        {
            "exchange": list(labels),
            "instrument_id": ["000777"] * len(labels),
            "series_id": [None] * len(labels),
        },
        schema=schema,
    )


def _resolve(batches: dict[str, list[pa.RecordBatch]]) -> Any:
    from vnpy_researchstore.native_common import (
        DatasetEntry,
        load_exchange_map,
        resolve_bar_dataset,
    )

    index = {
        dataset_id: DatasetEntry(
            dataset_id=dataset_id,
            semantic={"record_kind": "bars", "interval": "1d"},
            partitions=("2024",),
            rows=1,
            coverage_start_ns=None,
            coverage_end_ns=None,
        )
        for dataset_id in batches
    }
    return resolve_bar_dataset(
        _StubReader(batches),
        index,
        "000777",
        Exchange.SZSE,
        "1d",
        load_exchange_map(None),
    )


class TestResolveWholeStream:
    def test_later_batch_unmapped_label_refuses(self) -> None:
        with pytest.raises(StoreError, match="inconsistent exchange labels") as exc:
            _resolve({"ds-a": [_exchange_batch("XSHE"), _exchange_batch("XZZZ")]})
        assert "XZZZ" in str(exc.value)

    def test_later_batch_different_valid_exchange_refuses(self) -> None:
        with pytest.raises(StoreError, match="inconsistent exchange labels") as exc:
            _resolve({"ds-a": [_exchange_batch("XSHE"), _exchange_batch("XSGE")]})
        assert "SHFE" in str(exc.value)

    def test_null_label_alongside_match_refuses(self) -> None:
        with pytest.raises(StoreError, match="inconsistent exchange labels"):
            _resolve({"ds-a": [_exchange_batch("XSHE", None)]})

    def test_uniform_labels_across_batches_resolve(self) -> None:
        entry, stored_identity = _resolve(
            {"ds-a": [_exchange_batch("XSHE"), _exchange_batch("XSHE")]}
        )
        assert entry is not None
        assert entry.dataset_id == "ds-a"
        assert stored_identity == "000777"

    def test_identity_passthrough_label_resolves(self) -> None:
        entry, stored_identity = _resolve({"ds-a": [_exchange_batch("SZSE")]})
        assert entry is not None
        assert stored_identity == "000777"

    def test_empty_leading_batch_is_not_absence(self) -> None:
        entry, _ = _resolve({"ds-a": [_exchange_batch(), _exchange_batch("XSHE")]})
        assert entry is not None
        assert entry.dataset_id == "ds-a"

    def test_all_empty_batches_is_plain_no_match(self) -> None:
        assert _resolve({"ds-a": [_exchange_batch()]}) == (None, None)

    def test_nonmatching_dataset_unmapped_label_still_refuses(self) -> None:
        with pytest.raises(StoreError, match="unmapped exchange label"):
            _resolve({"ds-a": [_exchange_batch("XZZZ")]})

    def test_different_exchange_dataset_is_plain_no_match(self) -> None:
        assert _resolve({"ds-a": [_exchange_batch("XSGE")]}) == (None, None)

    def test_ambiguity_across_datasets_preserved(self) -> None:
        with pytest.raises(StoreError, match="ambiguous"):
            _resolve(
                {
                    "ds-a": [_exchange_batch("XSHE")],
                    "ds-b": [_exchange_batch("XSHE")],
                }
            )


# ---------------------------------------------------------------------------
# F1, end to end: real store + real streamed reader, both consumers
# ---------------------------------------------------------------------------


def _mixed_rows(instrument: str, second_label: str) -> list[dict[str, Any]]:
    rows = daily_rows(instrument)
    for row in rows[len(rows) // 2 :]:
        row["exchange"] = second_label
    return rows


class TestMixedLabelsEndToEnd:
    def test_database_later_unmapped_label_refuses(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            _mixed_rows("000777", "XZZZ"),
            asset_name="mixed-unmapped.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        with pytest.raises(StoreError, match="inconsistent exchange labels") as exc:
            db.load_bar_data(
                "000777",
                Exchange.SZSE,
                VtInterval.DAILY,
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
            )
        assert "XZZZ" in str(exc.value)
        db.close()

    def test_database_later_different_valid_exchange_refuses(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            _mixed_rows("000778", "XSGE"),
            asset_name="mixed-exchange.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        with pytest.raises(StoreError, match="inconsistent exchange labels") as exc:
            db.load_bar_data(
                "000778",
                Exchange.SZSE,
                VtInterval.DAILY,
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
            )
        assert "SHFE" in str(exc.value)
        db.close()

    def test_alpha_shared_helper_refuses(
        self, store: Store, tmp_path: Path
    ) -> None:
        dataset_id = import_dataset(
            store,
            tmp_path,
            _mixed_rows("000779", "XZZZ"),
            asset_name="mixed-alpha.csv",
        )
        snapshot_id = freeze_all(store, [dataset_id])
        lab = make_lab(tmp_path / "lab", store, snapshot_id)
        with pytest.raises(StoreError, match="inconsistent exchange labels"):
            lab.load_bar_data(
                "000779.SZSE", VtInterval.DAILY, "2024-01-01", "2024-01-31"
            )
        with pytest.raises(StoreError, match="inconsistent exchange labels"):
            lab.load_bar_df(
                ["000779.SZSE"], VtInterval.DAILY, "2024-01-02", "2024-01-08", 0
            )
        lab.close()


def _import_partitions(
    store: Store,
    tmp_path: Path,
    instrument: str,
    rows_by_partition: dict[str, list[dict[str, Any]]],
) -> str:
    """Import one dataset physically spread over the given partitions."""

    spec = make_spec()
    dataset_id = compute_dataset_id(spec)
    for rows in rows_by_partition.values():
        for row in rows:
            row["dataset_id"] = dataset_id
    asset = make_asset(
        tmp_path, "partitions.csv", b"fixture-partitions"
    )
    request = ImportRequest(
        asset=asset,
        spec=spec,
        adapter="synthetic/0.1",
        config={"member": "partitions.csv"},
        partitions=tuple(rows_by_partition),
    )
    receipt = import_asset(
        store,
        request,
        lambda partition: iter([bars_batch(rows_by_partition[partition])]),
    )
    assert receipt.state.value == "published"
    return dataset_id


def _daily_partition_row(
    dataset_id: str, instrument: str, trading: date, label: str
) -> dict[str, Any]:
    row = bar_row(
        dataset_id,
        instrument,
        ns(trading.year, trading.month, trading.day, 1, 30),
        close=10.0,
        turnover=1000.0,
        trading=trading,
    )
    row["exchange"] = label
    return row


class TestMultiPartitionMixedLabels:
    def test_label_flip_across_partitions_refuses(
        self, store: Store, tmp_path: Path
    ) -> None:
        instrument = "000780"
        dataset_id = _import_partitions(
            store,
            tmp_path,
            instrument,
            {
                "2023": [
                    _daily_partition_row(
                        "PLACEHOLDER", instrument, date(2023, 12, 29), "XSHE"
                    ),
                    _daily_partition_row(
                        "PLACEHOLDER", instrument, date(2024, 1, 2), "XSHE"
                    ),
                ],
                "2024": [
                    _daily_partition_row(
                        "PLACEHOLDER", instrument, date(2024, 1, 3), "XSGE"
                    ),
                    _daily_partition_row(
                        "PLACEHOLDER", instrument, date(2024, 1, 4), "XSGE"
                    ),
                ],
            },
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        with pytest.raises(StoreError, match="inconsistent exchange labels") as exc:
            db.load_bar_data(
                instrument,
                Exchange.SZSE,
                VtInterval.DAILY,
                datetime(2023, 1, 1),
                datetime(2024, 1, 31),
            )
        assert "SHFE" in str(exc.value)
        db.close()


class TestRealBatchBoundary:
    def test_second_reader_batch_unmapped_label_refuses(
        self, store: Store, tmp_path: Path
    ) -> None:
        # The reader fetches 65536 rows per batch: 65537 rows stream as two
        # real batches, the unmapped label landing only in the second.
        total = 65_536 + 1
        base = ns(2024, 1, 2, 1, 0)
        step = 60 * 1_000_000_000
        rows = []
        for i in range(total):
            row = bar_row(
                "DATASET",
                "000781",
                base + i * step,
                close=10.0,
                turnover=100.0,
                trading=date(2024, 1, 2),
            )
            row["exchange"] = "XSHE" if i < total - 1 else "XZZZ"
            rows.append(row)
        dataset_id = import_dataset(
            store, tmp_path, rows, asset_name="batch-boundary.csv", interval=RSInterval.M1
        )
        snapshot_id = freeze_all(store, [dataset_id])
        db = make_database(store.root, snapshot_id)
        with pytest.raises(StoreError, match="inconsistent exchange labels") as exc:
            db.load_bar_data(
                "000781",
                Exchange.SZSE,
                VtInterval.MINUTE,
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
            )
        assert "XZZZ" in str(exc.value)
        db.close()


# ---------------------------------------------------------------------------
# F2: DAILY overview trading_date semantics (Database + shipped CLI)
# ---------------------------------------------------------------------------

_NIGHT_SESSIONS = (
    (date(2024, 1, 3), ns(2024, 1, 2, 13, 0)),  # 21:00 Beijing on the prior day
    (date(2024, 1, 4), ns(2024, 1, 3, 13, 0)),
)


def _night_snapshot(store: Store, tmp_path: Path) -> str:
    rows = []
    for trading, start in _NIGHT_SESSIONS:
        row = bar_row(
            "DATASET",
            "rb2405",
            start,
            close=10.0,
            turnover=1000.0,
            open_interest=500.0,
            trading=trading,
        )
        row["exchange"] = "XSGE"
        rows.append(row)
    dataset_id = import_dataset(
        store,
        tmp_path,
        rows,
        asset_name="night-session.csv",
        asset_class=AssetClass.FUTURES,
        volume_unit="lot",
    )
    return freeze_all(store, [dataset_id])


class TestDailyOverviewTradingDate:
    def test_overview_boundaries_match_native_daily_reads(
        self, store: Store, tmp_path: Path
    ) -> None:
        from vnpy_researchstore.native_common import _ns_to_native_datetime

        snapshot_id = _night_snapshot(store, tmp_path)
        db = make_database(store.root, snapshot_id)

        # Precondition: the bar_start native date really differs from the
        # trading date (night session crossing midnight).
        assert _ns_to_native_datetime(ns(2024, 1, 2, 13, 0)).date() == date(2024, 1, 2)

        bars = db.load_bar_data(
            "rb2405",
            Exchange.SHFE,
            VtInterval.DAILY,
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
        )
        assert [b.datetime for b in bars] == [
            datetime(2024, 1, 3),
            datetime(2024, 1, 4),
        ]
        overview = [o for o in db.get_bar_overview() if o.interval == VtInterval.DAILY]
        assert len(overview) == 1
        entry = overview[0]
        assert entry.symbol == "rb2405"
        assert entry.exchange == Exchange.SHFE
        assert entry.count == len(bars)
        assert entry.start == min(b.datetime for b in bars)
        assert entry.end == max(b.datetime for b in bars)
        db.close()

    def test_native_overview_cli_daily_trading_date(
        self, store: Store, tmp_path: Path
    ) -> None:
        snapshot_id = _night_snapshot(store, tmp_path)
        config = write_config(tmp_path, store, snapshot_id)
        proc = run_tool("native_overview.py", config, tmp_path)
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert [row for row in payload["overview"] if row["interval"] == "d"] == [
            {
                "symbol": "rb2405",
                "exchange": "SHFE",
                "interval": "d",
                "count": 2,
                "start": "2024-01-03T00:00:00",
                "end": "2024-01-04T00:00:00",
            }
        ]


class TestMinuteHourOverviewUnchanged:
    def test_minute_overview_uses_bar_start(self, store: Store, tmp_path: Path) -> None:
        minute_id = import_dataset(
            store,
            tmp_path,
            minute_rows("000001"),
            asset_name="minute.csv",
            interval=RSInterval.M1,
        )
        snapshot_id = freeze_all(store, [minute_id])
        db = make_database(store.root, snapshot_id)
        entry = next(
            o for o in db.get_bar_overview() if o.interval == VtInterval.MINUTE
        )
        assert entry.count == 6
        assert entry.start == native_minute_dt(0)
        assert entry.end == native_minute_dt(5)
        db.close()

    def test_hour_overview_uses_bar_start(self, store: Store, tmp_path: Path) -> None:
        hour_id = import_dataset(
            store,
            tmp_path,
            minute_rows("000002"),
            asset_name="hour.csv",
            interval=RSInterval.H1,
        )
        snapshot_id = freeze_all(store, [hour_id])
        db = make_database(store.root, snapshot_id)
        entry = next(o for o in db.get_bar_overview() if o.interval == VtInterval.HOUR)
        assert entry.count == 6
        assert entry.start == native_minute_dt(0)
        assert entry.end == native_minute_dt(5)
        db.close()
