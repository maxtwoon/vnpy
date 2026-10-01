"""Dominant-map ingestion, contract trading-date transfer, unique-date
symbol resolution wiring, and overlay conflict behaviour."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from _rs_import_bootstrap import PYARROW_AVAILABLE, ZSTANDARD_AVAILABLE

from research_store.importers.adapters import (
    import_rq_etf,
    import_rq_futures,
    resolve_three_digit_symbol,
)
from research_store.importers.core_bridge import build_rq_etf_spec
from research_store.importers.dominant_map import (
    ContractDateMapper,
    build_dominant_mapping,
    load_dominant_mapping,
    save_dominant_mapping,
)
from research_store.importers.errors import ImporterError
from research_store.importers.sink import CountingSink
from research_store.importers.store_sink import StoreSink
from research_store.models import AssetRef, ConflictResolution, compute_dataset_id
from research_store.revisions import resolve_conflict
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


def _parquet_bytes(rows: list[dict]) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.Table.from_pylist(rows)
    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    return buffer.getvalue()


def _asset(path: Path, format: str = "tar_zst_parquet") -> AssetRef:
    from research_store.importers.safeio import file_sha256

    return AssetRef(
        asset_id=f"asset-{path.stem}",
        origin=str(path),
        format=format,
        size=path.stat().st_size,
        sha256=file_sha256(path),
    )


_DOMINANT_ROWS = [
    {
        "datetime": "2025-01-02 21:01:00",
        "dominant_id": "A2505",
        "underlying_symbol": "a",
        "trading_date": "2025-01-03",
        "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05,
        "volume": 10.0, "total_turnover": 100.0, "open_interest": 5.0,
    },
    {
        "datetime": "2025-01-03 09:02:00",
        "dominant_id": "A2505",
        "underlying_symbol": "a",
        "trading_date": "2025-01-03",
        "open": 1.05, "high": 1.2, "low": 1.0, "close": 1.15,
        "volume": 20.0, "total_turnover": 200.0, "open_interest": 6.0,
    },
]

_CONTRACT_ROWS = [
    {
        "datetime": "2025-01-02 21:01:00",
        "order_book_id": "A2505",
        "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05,
        "volume": 10.0, "total_turnover": 100.0, "open_interest": 5.0,
    },
    {
        # not dominant at this time -> key unmatched, stays unknown
        "datetime": "2025-06-02 09:02:00",
        "order_book_id": "A2505",
        "open": 2.0, "high": 2.1, "low": 1.9, "close": 2.05,
        "volume": 30.0, "total_turnover": 300.0, "open_interest": 7.0,
    },
]


@pytest.fixture()
def futures_package(tmp_path: Path) -> Path:
    package = tmp_path / "futures"
    package.mkdir()
    _write_tar_zst(
        package / "rqdatac_dominant_1m_none_2025.tar.zst",
        [("2025/unit_0000.parquet", _parquet_bytes(_DOMINANT_ROWS))],
    )
    _write_tar_zst(
        package / "rqdatac_contract_1m_none_2025.tar.zst",
        [("2025/unit_0000.parquet", _parquet_bytes(_CONTRACT_ROWS))],
    )
    return package


def test_dominant_mapping_build_and_transfer(futures_package: Path, tmp_path: Path) -> None:
    mapping = build_dominant_mapping(futures_package, staging_dir=tmp_path / "spool")
    assert len(mapping.entries) == 2
    assert mapping.entries[("A2505", "2025-01-02 21:01:00")] == "2025-01-03"

    # artifact roundtrip with sidecar verification
    path = save_dominant_mapping(mapping, tmp_path / "maps")
    loaded = load_dominant_mapping(path)
    assert loaded.entries == mapping.entries
    assert loaded.version == mapping.version
    # tamper is detected loudly
    sidecar = Path(str(path) + ".sha256")
    sidecar.write_text("0" * 64 + f"  {path.name}\n", encoding="utf-8")
    with pytest.raises(ImporterError, match="sha256 mismatch"):
        load_dominant_mapping(path)

    mapper = ContractDateMapper(load_dominant_mapping(
        save_dominant_mapping(mapping, tmp_path / "maps2")
    ))
    assert mapper.lookup("A2505", "2025-01-02 21:01:00") == "2025-01-03"
    assert mapper.lookup("A2505", "2025-06-02 09:02:00") is None
    assert mapper.stats()["unmatched_keys"] == 1


def test_contract_import_with_mapper_and_universe(futures_package: Path, tmp_path: Path) -> None:
    mapping = build_dominant_mapping(futures_package, staging_dir=tmp_path / "spool")
    mapper = ContractDateMapper(mapping)
    universe = [
        {
            "order_book_id": "A2505",
            "exchange": "DCE",
            "listed_date": "2024-05-20",
            "de_listed_date": "2025-05-19",
        }
    ]
    sink = CountingSink()
    receipt = import_rq_futures(
        futures_package,
        "contract_1m_none",
        sink,
        batch_id="b-fut",
        staging_dir=tmp_path / "staging",
        years=[2025],
        date_mapper=mapper,
        universe=universe,
    )
    assert receipt.rows_accepted == 2
    matched, unmatched = sink.rows
    # exact-key trading_date transfer with lineage, never natural-date math
    assert matched["trading_date"] == "2025-01-03"
    assert matched["extensions"]["trading_date_source"]["method"] == "dominant_map_exact_key"
    assert matched["extensions"]["trading_date_source"]["map_version"] == mapping.version
    assert "trading_date_unknown_no_calendar" not in matched["quality_flags"]
    # unmatched key stays honestly unknown
    assert unmatched["trading_date"] is None
    assert "trading_date_unknown_no_calendar" in unmatched["quality_flags"]
    # universe resolution attributes the exchange, keeps identity
    assert matched["exchange"] == "DCE"
    assert matched["instrument"] == "A2505"
    assert receipt.extras["trading_date_transfer"]["matched_keys"] == 1
    assert receipt.extras["identity_resolution"]["resolved"] == 2


def test_zhengzhou_unique_date_resolution() -> None:
    universe = [
        {"order_book_id": "TA1605", "exchange": "CZCE",
         "listed_date": "2015-05-01", "de_listed_date": "2016-05-19"},
        {"order_book_id": "TA2605", "exchange": "CZCE",
         "listed_date": "2025-05-20", "de_listed_date": "2026-05-19"},
    ]
    assert resolve_three_digit_symbol("TA605", "2026-01-05", universe)[0]["order_book_id"] == "TA2605"
    assert resolve_three_digit_symbol("TA605", "2016-01-05", universe)[0]["order_book_id"] == "TA1605"
    # ambiguous: both windows cover the date -> no resolution, never a guess
    overlapping = [
        {"order_book_id": "TA1605", "exchange": "CZCE",
         "listed_date": "2015-01-01", "de_listed_date": "2030-01-01"},
        {"order_book_id": "TA2605", "exchange": "CZCE",
         "listed_date": "2025-01-01", "de_listed_date": "2026-12-31"},
    ]
    assert len(resolve_three_digit_symbol("TA605", "2026-01-05", overlapping)) == 2


def test_zhengzhou_ambiguity_flagged_in_import(futures_package: Path, tmp_path: Path) -> None:
    package = tmp_path / "futures2"
    package.mkdir()
    _write_tar_zst(
        package / "rqdatac_contract_1m_none_2025.tar.zst",
        [("2025/unit_0000.parquet", _parquet_bytes([
            {
                "datetime": "2025-01-02 21:01:00",
                "order_book_id": "TA605",
                "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05,
                "volume": 10.0, "total_turnover": 100.0, "open_interest": 5.0,
            },
        ]))],
    )
    ambiguous_universe = [
        {"order_book_id": "TA1605", "exchange": "CZCE",
         "listed_date": "2015-01-01", "de_listed_date": "2030-01-01"},
        {"order_book_id": "TA2605", "exchange": "CZCE",
         "listed_date": "2025-01-01", "de_listed_date": "2026-12-31"},
    ]
    sink = CountingSink()
    receipt = import_rq_futures(
        package, "contract_1m_none", sink, batch_id="b-zz",
        staging_dir=tmp_path / "staging", years=[2025],
        universe=ambiguous_universe,
    )
    (row,) = sink.rows
    assert row["instrument"] == "TA605"  # original identity kept
    assert "symbol_resolution_ambiguous" in row["quality_flags"]
    assert receipt.extras["identity_resolution"]["ambiguous"] == 1


def _etf_csv(rows: list[str]) -> bytes:
    header = "order_book_id,datetime,open,high,low,close,volume,amount,num_trades\n"
    return (header + "\n".join(rows) + "\n").encode()


def test_overlay_import_conflicts_not_last_wins(tmp_path: Path) -> None:
    """The latest-increment overlay is a separate asset; a same-key
    different-value row surfaces as a core conflict (never last-wins), and
    quarantine resolution leaves a visible gap."""
    package = tmp_path / "etf"
    package.mkdir()
    base = package / "rqdatac_etf_lof_1m_2026.tar.zst"
    _write_tar_zst(
        base,
        [("2026/510300.XSHG.csv", _etf_csv([
            "510300.XSHG,2026-07-31 09:31:00,4.0,4.1,3.9,4.05,100,405,3",
            "510300.XSHG,2026-07-31 09:32:00,4.05,4.1,4.0,4.08,90,365,2",
        ]))],
    )
    overlay = package / "daily_increment_latest__rqdatac_etf_lof_1m_2026.tar.zst"
    _write_tar_zst(
        overlay,
        [("2026/510300.XSHG.csv", _etf_csv([
            # same key, corrected close -> conflict
            "510300.XSHG,2026-07-31 09:32:00,4.05,4.1,4.0,4.09,90,365,2",
            # new September key -> publishes normally; August stays uncovered
            "510300.XSHG,2026-09-09 09:31:00,4.2,4.3,4.1,4.25,80,340,2",
        ]))],
    )
    store = init_store(tmp_path / "store")
    try:
        spec = build_rq_etf_spec("1m")
        dataset_id = compute_dataset_id(spec)
        sink = StoreSink(store, _asset(base, "tar_zst_csv"), spec,
                         adapter="rq_etf/0.1", config={"archive": base.name},
                         batch_id="b-base")
        import_rq_etf(package, sink, batch_id="b-base", frequency="1m", years=[2026])
        base_receipt = sink.publish()
        assert base_receipt is not None and base_receipt.state.value == "published"

        sink2 = StoreSink(store, _asset(overlay, "tar_zst_csv"), spec,
                          adapter="rq_etf/0.1",
                          config={"archive": overlay.name, "overlay": "true"},
                          batch_id="b-overlay")
        import_rq_etf(package, sink2, batch_id="b-overlay", frequency="1m",
                      overlay=True)
        overlay_receipt = sink2.publish()
        assert overlay_receipt is not None
        assert overlay_receipt.state.value == "conflicted"
        assert len(overlay_receipt.conflicts) == 1
        conflict = overlay_receipt.conflicts[0]
        # the new September key still published; the conflicting key did not
        assert overlay_receipt.accepted_rows == 1

        # the serialized (CLI-visible) receipt preserves the public bounds,
        # and an idempotent replay of the same conflicted import returns the
        # same receipt WITH gap_ns — no private sidecar parsing needed
        summary = sink2.summary(overlay_receipt)
        serialized = summary["publish"]["conflicts"][0]
        assert serialized["gap_ns"] == list(conflict.gap_ns)
        sink_replay = StoreSink(
            store, _asset(overlay, "tar_zst_csv"), spec,
            adapter="rq_etf/0.1",
            config={"archive": overlay.name, "overlay": "true"},
            batch_id="b-overlay",
            spool_dir=tmp_path / "spool-replay",
        )
        import_rq_etf(package, sink_replay, batch_id="b-overlay",
                      frequency="1m", overlay=True)
        replay_receipt = sink_replay.publish()
        assert replay_receipt is not None
        assert replay_receipt.state.value == "conflicted"
        assert replay_receipt.conflicts[0].gap_ns == conflict.gap_ns
        assert (
            sink_replay.summary(replay_receipt)["publish"]["conflicts"][0]["gap_ns"]
            == list(conflict.gap_ns)
        )
        sink_replay.cleanup_spool()

        # default freeze fails on the unresolved conflict
        from research_store.models import (
            KnownGap,
            Selection,
            SnapshotRequest,
            UnresolvedConflictError,
        )
        from research_store.snapshots import freeze

        with pytest.raises(UnresolvedConflictError):
            freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))

        # quarantine resolution: new revision, visible gap, no fill
        revision = resolve_conflict(
            store, dataset_id, conflict.partition, conflict.conflict_id,
            ConflictResolution.QUARANTINE,
            reason="overlay correction disputed; quarantined pending review",
        )
        assert revision.revision_id != base_receipt.partitions[0].revision_id

        from research_store.snapshots import open_snapshot

        ref = freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),)))
        reader = open_snapshot(store, ref.snapshot_id)
        try:
            from research_store.models import CoverageGapError

            # any query intersecting the quarantined point fails loudly while
            # the snapshot does not explicitly allow the gap
            with pytest.raises(CoverageGapError):
                list(
                    reader.bars(
                        dataset_id, required_fields=(), allow_missing_auxiliary=True
                    )
                )
        finally:
            reader.close()

        # a deliberately 1ns-narrow allowance still refuses: the gap is the
        # record's REAL bounds, so a point-sized allowance cannot cover it
        assert conflict.gap_ns is not None
        ref_narrow = freeze(
            store,
            SnapshotRequest(
                selections=(Selection(dataset_id, "*"),),
                allow_known_gaps=(
                    KnownGap(
                        dataset_id=dataset_id,
                        start_ns=conflict.gap_ns[0],
                        end_ns=conflict.gap_ns[0] + 1,
                        reason="deliberately too narrow",
                    ),
                ),
            ),
        )
        reader = open_snapshot(store, ref_narrow.snapshot_id)
        try:
            from research_store.models import CoverageGapError

            with pytest.raises(CoverageGapError):
                list(
                    reader.bars(
                        dataset_id, required_fields=(), allow_missing_auxiliary=True
                    )
                )
        finally:
            reader.close()

        # re-freeze with an explicit allowed gap (recorded reason), then read.
        # The allowance comes from the PUBLIC conflict receipt field — the
        # disputed record's real normalized [bar_start, bar_end) bounds —
        # never from parsing the key string or guessing a bar width
        # (core-fix03 consumer handoff, F1).
        assert conflict.gap_ns is not None
        start_ns, end_ns = conflict.gap_ns
        assert end_ns > start_ns  # real interval, not a 1ns point
        ref2 = freeze(
            store,
            SnapshotRequest(
                selections=(Selection(dataset_id, "*"),),
                allow_known_gaps=(
                    KnownGap(
                        dataset_id=dataset_id,
                        start_ns=start_ns,
                        end_ns=end_ns,
                        reason="quarantined disputed overlay correction",
                    ),
                ),
            ),
        )
        reader = open_snapshot(store, ref2.snapshot_id)
        try:
            rows = [
                r
                for b in reader.bars(
                    dataset_id, required_fields=(), allow_missing_auxiliary=True
                )
                for r in b.to_pylist()
            ]
            labels = {r["source_label"] for r in rows}
            assert "2026-07-31 09:31:00" in labels  # uncontested base row
            assert "2026-09-09 09:31:00" in labels  # overlay new key
            assert "2026-07-31 09:32:00" not in labels  # quarantined gap
        finally:
            reader.close()

        # coverage reports the observed partitions; the August hole is the
        # absence of 2026-08 partitions, never filled
        from research_store.coverage import store_coverage

        report = store_coverage(store, dataset_id)
        parts = report["datasets"][dataset_id]["partitions"]
        assert report["expected_status"] == "unknown"
        assert any("2026-07" in p for p in parts)
        assert any("2026-09" in p for p in parts)
        assert not any("2026-08" in p for p in parts)
    finally:
        store.close()
