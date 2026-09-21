"""StoreSink tests: real core-boundary publish, partitions, candidates."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from _rs_import_bootstrap import PYARROW_AVAILABLE, ZSTANDARD_AVAILABLE

from research_store.importers.adapters import import_rq_etf
from research_store.importers.core_bridge import build_rq_etf_spec
from research_store.importers.partitions import bucket16, partition_for_row, product_of
from research_store.importers.store_sink import StoreSink
from research_store.models import AssetRef, Selection, SnapshotRequest, compute_dataset_id
from research_store.snapshots import freeze, open_snapshot
from research_store.store import init_store

pytestmark = pytest.mark.skipif(
    not (ZSTANDARD_AVAILABLE and PYARROW_AVAILABLE),
    reason="zstandard and pyarrow required",
)


def _write_tar_zst(path: Path, entries: list[tuple[str, bytes]]) -> None:
    import zstandard

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tf:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    path.write_bytes(zstandard.ZstdCompressor().compress(buffer.getvalue()))


def _etf_csv(rows: list[str]) -> bytes:
    header = "order_book_id,datetime,open,high,low,close,volume,amount,num_trades\n"
    return (header + "\n".join(rows) + "\n").encode()


def _asset(path: Path) -> AssetRef:
    from research_store.importers.safeio import file_sha256

    return AssetRef(
        asset_id=f"asset-{path.stem}",
        origin=str(path),
        format="tar_zst_csv",
        size=path.stat().st_size,
        sha256=file_sha256(path),
    )


def test_partition_scheme() -> None:
    daily = {"instrument": "600519.XSHG", "trading_date": "2024-03-05"}
    assert partition_for_row(daily, "1d", "equity") == "2024"
    minute = {
        "instrument": "510300.XSHG",
        "exchange": "XSHG",
        # 2016-02-29 09:31 +0800 END label => 2016-02 01:31 UTC
        "bar_end_ns": 1_456_708_860 * 1_000_000_000,
    }
    part = partition_for_row(minute, "1m", "etf")
    assert part == f"XSHG/2016-02/{bucket16('510300.XSHG')}"
    fut = {"instrument": "A2505", "bar_end_ns": 1_456_708_860 * 1_000_000_000}
    assert partition_for_row(fut, "1m", "futures") == "A/2016-02"
    dominant = {
        "instrument": "A2505",
        "bar_end_ns": 1_456_708_860 * 1_000_000_000,
        "extensions": {"underlying_symbol": "a"},
    }
    assert partition_for_row(dominant, "1m", "futures") == "A/2016-02"
    assert product_of("rb2605") == "RB"
    with pytest.raises(ValueError, match="unknown"):
        partition_for_row({"instrument": "x", "bar_end_ns": None}, "1m", "futures")


def test_store_sink_publishes_and_reads_back(tmp_path: Path) -> None:
    package = tmp_path / "etf"
    package.mkdir()
    archive = package / "rqdatac_etf_lof_1m_2016.tar.zst"
    _write_tar_zst(
        archive,
        [
            (
                "2016/510300.XSHG.csv",
                _etf_csv(
                    [
                        "510300.XSHG,2016-02-29 09:31:00,1,1.2,0.9,1.1,100,500,3",
                        # empty amount -> real NULL turnover, never zero-filled
                        "510300.XSHG,2016-02-29 09:32:00,1.1,1.3,1.0,1.2,90,,2",
                    ]
                ),
            ),
            (
                "2016/159915.XSHE.csv",
                _etf_csv(["159915.XSHE,2016-02-29 09:31:00,2,2.2,1.9,2.1,50,100,1"]),
            ),
        ],
    )
    store = init_store(tmp_path / "store")
    try:
        spec = build_rq_etf_spec("1m")
        sink = StoreSink(
            store, _asset(archive), spec, adapter="rq_etf/0.1",
            config={"archive": archive.name}, batch_id="b-etf",
        )
        adapter_receipt = import_rq_etf(
            package, sink, batch_id="b-etf", frequency="1m", years=[2016]
        )
        assert adapter_receipt.rows_accepted == 3
        receipt = sink.publish()
        assert receipt is not None
        assert receipt.state.value == "published"
        assert receipt.accepted_rows == 3
        sink.cleanup_spool()

        dataset_id = compute_dataset_id(spec)
        # canonical partitions: exchange/year-month/bucket
        partitions = {p.partition for p in receipt.partitions}
        assert partitions == {
            f"XSHG/2016-02/{bucket16('510300.XSHG')}",
            f"XSHE/2016-02/{bucket16('159915.XSHE')}",
        }

        # final readback through the real snapshot reader (not a mock)
        ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
        reader = open_snapshot(store, ref.snapshot_id)
        try:
            batches = list(
                reader.bars(
                    dataset_id, required_fields=(), allow_missing_auxiliary=True
                )
            )
            rows = [r for b in batches for r in b.to_pylist()]
        finally:
            reader.close()
        assert len(rows) == 3
        by_label = {r["source_label"]: r for r in rows}
        assert by_label["2016-02-29 09:32:00"]["turnover"] is None
        assert by_label["2016-02-29 09:32:00"]["volume"] == 90.0

        # idempotent replay through the same sink path returns the same batch
        sink2 = StoreSink(
            store, _asset(archive), spec, adapter="rq_etf/0.1",
            config={"archive": archive.name}, batch_id="b-etf",
        )
        import_rq_etf(package, sink2, batch_id="b-etf", frequency="1m", years=[2016])
        replay = sink2.publish()
        assert replay is not None
        assert replay.batch_id == receipt.batch_id
        assert replay.state.value == "published"
    finally:
        store.close()


def test_store_sink_preserves_failed_members(tmp_path: Path) -> None:
    package = tmp_path / "etf"
    package.mkdir()
    archive = package / "rqdatac_etf_lof_1d_2016.tar.zst"
    _write_tar_zst(
        archive,
        [("2016/510300.XSHG.csv", b"not,a,valid\n\x00\x01broken")],
    )
    store = init_store(tmp_path / "store")
    try:
        spec = build_rq_etf_spec("1d")
        sink = StoreSink(
            store, _asset(archive), spec, adapter="rq_etf/0.1",
            config={"archive": archive.name}, batch_id="b-bad",
        )
        receipt_adapter = import_rq_etf(
            package, sink, batch_id="b-bad", frequency="1d", years=[2016]
        )
        receipt = sink.publish()
        summary = sink.summary(receipt)
        # the bad member surfaces; nothing silently published
        assert summary["counts"]["members_failed"] == 1
        assert receipt_adapter.members_failed == 1
    finally:
        store.close()
