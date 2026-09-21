from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from _rs_import_bootstrap import ZSTANDARD_AVAILABLE

from research_store.importers.adapters import import_rq_etf
from research_store.importers.core_bridge import (
    CoreBridgeError,
    build_jq_daily_spec,
    build_rq_etf_spec,
    build_ssquant_spec,
    to_core_row,
    to_record_batches,
)
from research_store.importers.normalize import normalize_ssquant_row
from research_store.importers.sink import CountingSink
from research_store.models import AssetRef, compute_dataset_id
from research_store.revisions import import_asset
from research_store.store import init_store


def _write_tar_zst(path: Path, entries: list[tuple[str, bytes]]) -> None:
    import zstandard

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tf:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    path.write_bytes(zstandard.ZstdCompressor().compress(buffer.getvalue()))


@pytest.fixture()
def etf_package(tmp_path: Path) -> Path:
    package = tmp_path / "etf"
    package.mkdir()
    csv_text = (
        "order_book_id,datetime,open,high,low,close,volume,amount,num_trades\n"
        "510300.XSHG,2016-02-29 09:31:00,4.0,4.1,3.9,4.05,100,405,3\n"
        "510300.XSHG,2016-02-29 09:32:00,4.05,4.1,4.0,4.08,90,365,2\n"
        "159915.XSHE,2016-02-29 09:31:00,1.0,1.1,0.9,1.0,50,50,1\n"
    )
    _write_tar_zst(
        package / "rqdatac_etf_lof_1m_2016.tar.zst",
        [("2016/510300.XSHG.csv", csv_text.encode())],
    )
    return package


@pytest.mark.skipif(not ZSTANDARD_AVAILABLE, reason="zstandard not installed")
def test_publish_through_core_boundary(tmp_path: Path, etf_package: Path) -> None:
    sink = CountingSink()
    import_rq_etf(etf_package, sink, batch_id="b-core", frequency="1m")
    spec = build_rq_etf_spec("1m")
    dataset_id = compute_dataset_id(spec)
    store = init_store(tmp_path / "store")
    try:
        asset = AssetRef(
            asset_id="asset-etf-2016",
            origin=str(etf_package / "rqdatac_etf_lof_1m_2016.tar.zst"),
            format="tar_zst_csv",
            size=(etf_package / "rqdatac_etf_lof_1m_2016.tar.zst").stat().st_size,
            sha256="0" * 64,
        )
        batches = list(
            to_record_batches(sink.rows, dataset_id, asset.asset_id, "b-core")
        )
        assert sum(batch.num_rows for batch in batches) == 3
        request_config = {"frequency": "1m", "archive": "rqdatac_etf_lof_1m_2016.tar.zst"}

        from research_store.models import ImportRequest

        request = ImportRequest(
            asset=asset,
            spec=spec,
            adapter="rq_etf/0.1",
            config=request_config,
            partitions=("2016",),
        )

        def rows(partition: str) -> object:
            assert partition == "2016"
            return iter(batches)

        receipt = import_asset(store, request, rows)
        assert receipt.state.value == "published"
        assert receipt.accepted_rows == 3
        assert receipt.conflicts == ()

        # idempotent replay returns prior receipt, no re-publish
        replay = import_asset(store, request, rows)
        assert replay.batch_id == receipt.batch_id
        assert replay.accepted_rows == 3

        # verify NULL-preservation + END-label bounds landed in the object
        rev = receipt.partitions[0]
        manifest_path = store.path.revision_manifests / f"{rev.revision_id}.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["rows"] == 3
        object_files = [
            store.root / file_ref["path"] for file_ref in manifest["files"]
        ]
        import pyarrow.parquet as pq

        table = pq.read_table(object_files[0])
        data = table.to_pylist()
        by_key = {(row["symbol"], row["bar_start"]): row for row in data}
        first = by_key[("510300.XSHG", data[0]["bar_start"])]
        assert first["bar_end"] - first["bar_start"] == 60 * 1_000_000_000
        assert first["trading_date"].isoformat() == "2016-02-29"
        assert json.loads(first["field_quality"])["flags"] == []
        # sorted by identity then time across instruments
        identities = [
            (row["instrument_id"] or row["series_id"], row["bar_start"])
            for row in data
        ]
        assert identities == sorted(identities)
    finally:
        store.close()


def test_core_bridge_rejects_unknown_bounds_honestly() -> None:
    row = normalize_ssquant_row(
        {
            "datetime": "2026-02-24 13:30:00",
            "symbol": "rb2605",
            "real_symbol": "rb2605",
            "open": 3036.0,
            "high": 3036.0,
            "low": 3027.0,
            "close": 3029.0,
            "volume": 8387.0,
            "amount": 254157290.0,
        },
        table="rb2605_1M_raw",
        batch_id="b",
        series_kind="real_contract",
    )
    with pytest.raises(CoreBridgeError, match="bar bounds"):
        to_core_row(row, "ds-x", "asset", "batch")


def test_specs_carry_verified_semantics() -> None:
    etf = build_rq_etf_spec("1m")
    assert etf.source_time_label.value == "end"
    assert etf.adjustment.value == "none"
    assert etf.volume_unit == "share"
    jq = build_jq_daily_spec()
    assert jq.adjustment.value == "unknown"
    ssquant = build_ssquant_spec("1m", "continuous_888")
    assert ssquant.source_time_label.value == "unknown"
    assert ssquant.turnover_unit == "unknown"
    # discriminating semantics produce distinct dataset ids
    assert compute_dataset_id(etf) != compute_dataset_id(jq)
    assert compute_dataset_id(etf) != compute_dataset_id(ssquant)
