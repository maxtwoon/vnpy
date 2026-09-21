from __future__ import annotations

import io
import sqlite3
import tarfile
from pathlib import Path

import pytest

from _rs_import_bootstrap import PYARROW_AVAILABLE, ZSTANDARD_AVAILABLE

from research_store.importers.adapters import (
    import_jq_daily,
    import_rq_etf,
    import_rq_futures,
    import_ssquant_table,
    load_futures_universe,
    resolve_three_digit_symbol,
    resolve_unique_symbol,
)
from research_store.importers.errors import AmbiguousSymbolError
from research_store.importers.sink import CountingSink, JSONLImportSink

needs_archive_deps = pytest.mark.skipif(
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


@needs_archive_deps
def test_import_rq_etf_streaming_end_to_end(tmp_path: Path) -> None:
    package = tmp_path / "etf"
    package.mkdir()
    _write_tar_zst(
        package / "rqdatac_etf_lof_1m_2016.tar.zst",
        [
            (
                "2016/510300.XSHG.csv",
                _etf_csv(
                    [
                        "510300.XSHG,2016-02-29 09:31:00,1,1,1,1,100,500,3",
                        "510300.XSHG,2016-02-29 09:32:00,1,1,1,1,100,500,3",
                        "510300.XSHG,2016-02-29 13:01:00,1,1,1,1,100,500,3",
                    ]
                ),
            ),
            (
                "2016/161225.XSHE.csv",
                _etf_csv(["161225.XSHE,2016-02-29 11:30:00,0.849,0.849,0.849,0.849,0.0,0.0,0.0"]),
            ),
        ],
    )
    sink = CountingSink()
    receipt = import_rq_etf(
        package, sink, batch_id="batch-1", frequency="1m", years=[2016]
    )
    assert receipt.rows_accepted == 4
    assert receipt.members_ok == 2
    first = sink.rows[0]
    assert first["instrument"] == "510300.XSHG"
    assert first["trading_date"] == "2016-02-29"
    assert first["provenance"]["archive"] == "rqdatac_etf_lof_1m_2016.tar.zst"
    labels = [row["source_label"] for row in sink.rows]
    # no midday filler: 11:30/13:01 gap stays a gap
    assert labels == [
        "2016-02-29 09:31:00",
        "2016-02-29 09:32:00",
        "2016-02-29 13:01:00",
        "2016-02-29 11:30:00",
    ]


@needs_archive_deps
def test_import_rq_etf_jsonl_sink_and_repair(tmp_path: Path) -> None:
    package = tmp_path / "etf"
    package.mkdir()
    _write_tar_zst(
        package / "rqdatac_etf_lof_1m_2017.tar.zst",
        [
            (
                "2017/160105.XSHE.csv",
                _etf_csv(
                    [
                        "160105.XSHE,2017-09-19 13:01:00,1,1,1,1,0,0,0",
                        "160105.XSHE,2017-09-19 13:02:00,1,1,1,1,10,20,1",
                    ]
                ),
            )
        ],
    )
    import json

    (package / "QUALITY_REPAIR_20260905.json").write_text(
        json.dumps({"repair_date": "2026-09-05", "archives": []}), encoding="utf-8"
    )
    import csv as csv_mod

    out = io.StringIO()
    writer = csv_mod.DictWriter(
        out, fieldnames=["dataset", "file", "order_book_id", "datetime", "reasons", "before", "after"]
    )
    writer.writeheader()
    writer.writerow(
        {
            "dataset": "etf_lof",
            "file": "2017/160105.XSHE.csv",
            "order_book_id": "160105.XSHE",
            "datetime": "2017-09-19 13:01:00",
            "reasons": "negative_turnover_or_volume_to_zero",
            "before": json.dumps({"volume": "15000", "amount": "-100"}),
            "after": json.dumps({"volume": "0", "amount": "0"}),
        }
    )
    (package / "quality_repair_changes_20260905.csv").write_text(
        out.getvalue(), encoding="utf-8"
    )
    from research_store.importers.repair_index import load_repair_index

    index = load_repair_index(package)
    out_path = tmp_path / "out" / "batch.jsonl.gz"
    with JSONLImportSink(out_path) as sink:
        receipt = import_rq_etf(
            package, sink, batch_id="b2", frequency="1m", repair_index=index
        )
    assert receipt.rows_accepted == 2
    import gzip as gzip_mod

    with gzip_mod.open(out_path, "rt", encoding="utf-8") as fh:
        lines = [json.loads(line) for line in fh]
    rows = [line for line in lines if "_member" not in line]
    assert rows[0]["quality_flags"] == ["repaired_deterministic"]
    assert rows[1]["quality_flags"] == []


def test_import_jq_daily(tmp_path: Path) -> None:
    import gzip

    daily = tmp_path / "daily"
    daily.mkdir()
    with gzip.open(daily / "all_a_daily_2016.csv.gz", "wt", encoding="utf-8") as fh:
        fh.write(
            "date,code,open,close,high,low,volume,money,pre_close,paused,factor\n"
            "2016-01-04,000001.XSHE,10,10,10,10,100,1000,10,0.0,1.0\n"
            "2016-01-04,600000.XSHG,,, ,0,0,,,1.0,1.0\n"
        )
    sink = CountingSink()
    receipt = import_jq_daily(daily, sink, batch_id="b", years=[2016])
    assert receipt.rows_accepted == 2
    first, second = sink.rows
    assert first["trading_date"] == "2016-01-04"
    assert second["open"] is None and second["high"] is None
    assert second["extensions"]["paused"] == "1.0"
    assert second["extensions"]["adjustment_status"] == "unknown_factor_all_one"


def _ssquant_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE rb888_1M_raw (datetime TEXT PRIMARY KEY, symbol TEXT, "
        "real_symbol TEXT, open REAL, high REAL, low REAL, close REAL, "
        "volume REAL, amount REAL, openint REAL, cumulative_openint REAL)"
    )
    con.execute(
        "CREATE TABLE rb888_1M_raw_staging (datetime TEXT NOT NULL, symbol TEXT NOT NULL, "
        "open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, "
        "volume REAL NOT NULL, amount REAL NOT NULL, PRIMARY KEY (datetime, symbol))"
    )
    con.execute(
        "INSERT INTO rb888_1M_raw VALUES ('2026-07-01 11:30:00','rb888','rb2610',1,1,1,1,9,9,1,1)"
    )
    con.execute(
        "INSERT INTO rb888_1M_raw VALUES ('2026-07-01 15:16:00','RB888',NULL,1,1,1,1,0,0,0,0)"
    )
    con.execute(
        "INSERT INTO rb888_1M_raw_staging VALUES ('2026-07-01 11:30:00','RB888',1,1,1,1,2,2)"
    )
    con.commit()
    con.close()


def test_import_ssquant_quarantine_and_staging(tmp_path: Path) -> None:
    db = tmp_path / "capture.db"
    _ssquant_db(db)
    sink = CountingSink()
    quarantine = {("rb888_1M_raw", "RB888", "2026-07-01 15:16:00")}
    receipt = import_ssquant_table(
        db, "rb888_1M_raw", sink, batch_id="b", quarantine_keys=quarantine
    )
    assert receipt.rows_accepted == 1
    assert receipt.rows_quarantined == 1
    assert receipt.extras["series_kind"] == "continuous_888"
    assert sink.rows[0]["extensions"]["real_symbol"] == "rb2610"

    staging_sink = CountingSink()
    staging_receipt = import_ssquant_table(
        db, "rb888_1M_raw_staging", staging_sink, batch_id="b"
    )
    assert staging_receipt.rows_accepted == 1
    assert staging_receipt.extras["series_kind"] == "staging"
    assert staging_sink.rows[0]["series_kind"] == "staging"


@needs_archive_deps
def test_import_rq_futures_dominant_and_contract(tmp_path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    futures = tmp_path / "futures"
    dominant_dir = futures / "dominant_1m_none"
    contract_dir = futures / "contract_1m_none"
    dominant_dir.mkdir(parents=True)
    contract_dir.mkdir(parents=True)

    dominant_table = pa.table(
        {
            "underlying_symbol": pa.array(["RB", "RB"]),
            "datetime": pa.array(
                ["2026-07-31 21:00:00", "2026-07-31 21:01:00"]
            ),
            "trading_date": pa.array(
                ["2026-08-03 00:00:00", "2026-08-03 00:00:00"]
            ),
            "dominant_id": pa.array(["RB2610", "RB2610"]),
            "open": pa.array([3200.0, 3200.0]),
            "close": pa.array([3201.0, 3202.0]),
            "high": pa.array([3202.0, 3203.0]),
            "low": pa.array([3199.0, 3200.0]),
            "total_turnover": pa.array([100.0, 100.0]),
            "volume": pa.array([1.0, 1.0]),
            "open_interest": pa.array([1.0, 1.0]),
        }
    )
    sink_io = io.BytesIO()
    pq.write_table(dominant_table, sink_io)
    _write_tar_zst(
        dominant_dir / "rqdatac_dominant_1m_none_2026.tar.zst",
        [("2026/unit_0000.parquet", sink_io.getvalue())],
    )

    contract_table = pa.table(
        {
            "order_book_id": pa.array(["RB2605"]),
            "datetime": pa.array(["2026-02-24 13:30:00"]),
            "open": pa.array([3036.0]),
            "high": pa.array([3036.0]),
            "low": pa.array([3027.0]),
            "close": pa.array([3029.0]),
            "volume": pa.array([8387.0]),
            "amount": pa.array([254157290.0]),
            "open_interest": pa.array([-1305.0]),
        }
    )
    sink_io = io.BytesIO()
    pq.write_table(contract_table, sink_io)
    _write_tar_zst(
        contract_dir / "rqdatac_contract_1m_none_2026.tar.zst",
        [("2026/unit_0000.parquet", sink_io.getvalue())],
    )

    sink = CountingSink()
    receipt = import_rq_futures(
        dominant_dir,
        "dominant_1m_none",
        sink,
        batch_id="b",
        staging_dir=tmp_path / "spool",
    )
    assert receipt.rows_accepted == 2
    assert sink.rows[0]["trading_date"] == "2026-08-03"
    assert sink.rows[0]["extensions"]["dominant_id"] == "RB2610"

    contract_sink = CountingSink()
    contract_receipt = import_rq_futures(
        contract_dir,
        "contract_1m_none",
        contract_sink,
        batch_id="b",
        staging_dir=tmp_path / "spool2",
    )
    assert contract_receipt.rows_accepted == 1
    row = contract_sink.rows[0]
    assert row["instrument"] == "RB2605"
    assert row["open_interest"] == -1305.0
    assert "negative:open_interest" in row["quality_flags"]


def test_zhengzhou_unique_date_resolution(tmp_path: Path) -> None:
    universe_csv = tmp_path / "universe.csv"
    universe_csv.write_text(
        "order_book_id,listed_date,de_listed_date,exchange\n"
        "TA505,2005-01-01,2005-05-20,CZCE\n"
        "TA1505,2015-01-01,2015-05-20,CZCE\n"
        "TA2505,2025-01-01,,CZCE\n",
        encoding="utf-8",
    )
    universe = load_futures_universe(universe_csv)
    assert len(resolve_three_digit_symbol("TA505", "2005-03-01", universe)) == 1
    unique = resolve_unique_symbol("TA505", "2005-03-01", universe)
    assert unique["order_book_id"] == "TA505"
    # 2025 has both TA2505 alive and older ones expired -> unique
    assert resolve_unique_symbol("TA505", "2025-03-01", universe)["order_book_id"] == "TA2505"
    with pytest.raises(AmbiguousSymbolError):
        # window with no listing evidence: refuse to guess the decade
        resolve_unique_symbol("TA505", "2010-03-01", universe)
