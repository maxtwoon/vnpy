"""Focused futures minute-label semantics tests (WP10L).

Default RQ futures minute rows are UNKNOWN (no canonical bounds, standard
candidate path); explicit typed ``FuturesLabelScope`` evidence converts
only the rows it covers; the public adapter verifies spec/evidence pairing
and supports bounded member selection; the exact trading-date transfer
stays independent of label qualification; daily and ETF behavior is
unchanged.
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from _rs_import_bootstrap import PYARROW_AVAILABLE, ZSTANDARD_AVAILABLE

from research_store.importers.adapters import import_rq_futures
from research_store.importers.core_bridge import (
    build_jq_daily_spec,
    build_rq_etf_spec,
    build_rq_futures_spec,
)
from research_store.importers.dominant_map import (
    ContractDateMapper,
    DominantMapping,
    build_dominant_mapping,
)
from research_store.importers.errors import MemberReadError
from research_store.importers.normalize import (
    FuturesLabelScope,
    normalize_rq_futures_row,
)
from research_store.importers.sink import CountingSink
from research_store.importers.store_sink import StoreSink, iter_candidates
from research_store.models import Adjustment, TimeLabel
from research_store.store import init_store

pytestmark = pytest.mark.skipif(
    not (ZSTANDARD_AVAILABLE and PYARROW_AVAILABLE),
    reason="zstandard and pyarrow required",
)

_SHA = "a" * 64


def _scope(**overrides: object) -> FuturesLabelScope:
    values: dict[str, object] = {
        "conclusion": "end",
        "source_id": "rqdatac",
        "dataset": "contract_1m_none",
        "archive": "rqdatac_contract_1m_none_2025.tar.zst",
        "member": "2025/unit_0000.parquet",
        "frequency": "1m",
        "interval_minutes": 1,
        "instrument": "A2505",
        "label_start": "2025-01-02 00:00:00",
        "label_end": "2025-01-07 00:00:00",
        "input_sha256": _SHA,
        "evidence_ref": "review/evidence.md",
        "evidence_sha256": "b" * 64,
    }
    values.update(overrides)
    return FuturesLabelScope(**values)  # type: ignore[arg-type]


def _contract_record(label: str, instrument: str = "A2505") -> dict[str, object]:
    return {
        "datetime": label,
        "order_book_id": instrument,
        "open": 1.0,
        "high": 1.1,
        "low": 0.9,
        "close": 1.05,
        "volume": 10.0,
        "total_turnover": 100.0,
        "open_interest": 5.0,
    }


# ---------------------------------------------------------------------------
# Default UNKNOWN semantics
# ---------------------------------------------------------------------------


def test_default_minute_rows_are_unknown_candidates() -> None:
    row = normalize_rq_futures_row(
        _contract_record("2025-01-02 21:01:00"),
        dataset="contract_1m_none",
        archive="rqdatac_contract_1m_none_2025.tar.zst",
        member="2025/unit_0000.parquet",
        batch_id="b",
        interval_minutes=1,
    )
    assert row["bar_start_ns"] is None and row["bar_end_ns"] is None
    assert "source_time_label_unknown" in row["quality_flags"]
    assert "trading_date_unknown_no_calendar" in row["quality_flags"]
    # original label and payload preserved verbatim; NULLs stay NULL
    assert row["source_label"] == "2025-01-02 21:01:00"
    assert row["close"] == 1.05 and row["open_interest"] == 5.0
    record_null_turnover = _contract_record("2025-01-02 21:02:00")
    record_null_turnover["total_turnover"] = None
    row_null = normalize_rq_futures_row(
        record_null_turnover,
        dataset="contract_1m_none",
        archive="a.tar.zst",
        member="m",
        batch_id="b",
        interval_minutes=1,
    )
    assert row_null["turnover"] is None
    assert "nonfinite:turnover" not in row_null["quality_flags"]


def test_dominant_rows_keep_date_level_transfer_unknown_bounds() -> None:
    record = {
        "datetime": "2025-01-02 21:01:00",
        "dominant_id": "A2505",
        "underlying_symbol": "a",
        "trading_date": "2025-01-03",
        "open": 1.0,
        "close": 1.05,
        "volume": 10.0,
    }
    row = normalize_rq_futures_row(
        record,
        dataset="dominant_1m_none",
        archive="rqdatac_dominant_1m_none_2025.tar.zst",
        member="2025/unit_0000.parquet",
        batch_id="b",
        interval_minutes=1,
    )
    assert row["bar_start_ns"] is None and row["bar_end_ns"] is None
    assert "source_time_label_unknown" in row["quality_flags"]
    # date-level evidence is independent of label direction
    assert row["trading_date"] == "2025-01-03"
    assert row["extensions"]["dominant_id"] == "A2505"


def test_daily_futures_rows_keep_date_semantics() -> None:
    row = normalize_rq_futures_row(
        {
            "datetime": "2025-01-06",
            "dominant_id": "A2505",
            "underlying_symbol": "a",
            "trading_date": "2025-01-06",
            "open": 1.0,
            "close": 1.05,
        },
        dataset="dominant_1d_none",
        archive="rqdatac_dominant_1d_none_2025.tar.zst",
        member="2025/unit_0000.parquet",
        batch_id="b",
        interval_minutes=0,
    )
    assert row["bar_start_ns"] is not None and row["bar_end_ns"] is not None
    assert row["trading_date"] == "2025-01-06"
    assert "source_time_label_unknown" not in row["quality_flags"]


# ---------------------------------------------------------------------------
# Typed scoped evidence
# ---------------------------------------------------------------------------


def test_scoped_end_and_start_convert_only_covered_rows() -> None:
    end_scope = _scope(conclusion="end")
    row = normalize_rq_futures_row(
        _contract_record("2025-01-03 21:01:00"),
        dataset="contract_1m_none",
        archive=end_scope.archive,
        member=end_scope.member,
        batch_id="b",
        interval_minutes=1,
        label_scope=end_scope,
    )
    assert row["bar_start_ns"] is not None and row["bar_end_ns"] is not None
    # END: [label - interval, label)
    from research_store.importers.normalize import end_label_bounds_ns, parse_label

    expected = end_label_bounds_ns(parse_label("2025-01-03 21:01:00"), 1)
    assert (row["bar_start_ns"], row["bar_end_ns"]) == expected
    assert "source_time_label_unknown" not in row["quality_flags"]
    evidence = row["extensions"]["label_evidence"]
    assert evidence["scope_identity"] == end_scope.identity
    assert evidence["conclusion"] == "end"
    assert evidence["evidence_sha256"] == "b" * 64

    start_scope = _scope(conclusion="start")
    row_start = normalize_rq_futures_row(
        _contract_record("2025-01-03 21:01:00"),
        dataset="contract_1m_none",
        archive=start_scope.archive,
        member=start_scope.member,
        batch_id="b",
        interval_minutes=1,
        label_scope=start_scope,
    )
    from research_store.importers.normalize import shanghai_to_utc_ns

    label_ns = shanghai_to_utc_ns(parse_label("2025-01-03 21:01:00"))
    minute_ns = 60 * 1_000_000_000
    assert row_start["bar_start_ns"] == label_ns
    assert row_start["bar_end_ns"] == label_ns + minute_ns


def test_out_of_scope_rows_stay_candidates() -> None:
    scope = _scope()
    out_rows = [
        # different instrument inside the same member/window
        _contract_record("2025-01-03 21:01:00", instrument="B2505"),
        # same instrument, label outside the interval
        _contract_record("2025-02-03 21:01:00"),
        # same instrument, different member
        (_contract_record("2025-01-03 21:01:00"), "2025/unit_0001.parquet"),
    ]
    for record in out_rows:
        record_dict, member = record if isinstance(record, tuple) else (record, scope.member)
        row = normalize_rq_futures_row(
            record_dict,
            dataset="contract_1m_none",
            archive=scope.archive,
            member=member,
            batch_id="b",
            interval_minutes=1,
            label_scope=scope,
        )
        assert row["bar_start_ns"] is None and row["bar_end_ns"] is None
        assert "source_time_label_unknown" in row["quality_flags"]
        assert "outside_label_evidence_scope" in row["quality_flags"]


def test_malformed_scopes_are_rejected() -> None:
    with pytest.raises(ValueError, match="conclusion"):
        _scope(conclusion="middle")
    with pytest.raises(ValueError, match="sha256"):
        _scope(input_sha256="not-a-digest")
    with pytest.raises(ValueError, match="label_start"):
        _scope(label_start="2025-01-07 00:00:00", label_end="2025-01-02 00:00:00")
    with pytest.raises(ValueError, match="interval_minutes"):
        _scope(interval_minutes=0)
    with pytest.raises(ValueError, match="non-empty"):
        _scope(member="  ")
    # identity is stable and content-derived
    assert _scope().identity == _scope().identity
    assert _scope(conclusion="start").identity != _scope(conclusion="end").identity


# ---------------------------------------------------------------------------
# Spec builders: default UNKNOWN, explicit labels distinct
# ---------------------------------------------------------------------------


def test_futures_spec_defaults_to_unknown_and_labels_are_distinct() -> None:
    spec = build_rq_futures_spec("contract_1m_none", "1m")
    assert spec.source_time_label is TimeLabel.UNKNOWN
    assert spec.adjustment is Adjustment.NONE  # units/roll unchanged
    ids = {
        build_rq_futures_spec("contract_1m_none", "1m", time_label=label)
        for label in ("unknown", "start", "end")
    }
    assert len(ids) == 3  # UNKNOWN/START/END never share a semantic identity
    with pytest.raises(ValueError, match="time_label"):
        build_rq_futures_spec("contract_1m_none", "1m", time_label="end-ish")
    # daily and ETF semantics unchanged
    assert build_rq_etf_spec("1m").source_time_label is TimeLabel.END
    assert build_jq_daily_spec().source_time_label is TimeLabel.START


# ---------------------------------------------------------------------------
# Adapter: pairing verification + bounded member selection + date transfer
# ---------------------------------------------------------------------------


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

    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), buffer)
    return buffer.getvalue()


def _futures_package(tmp_path: Path) -> Path:
    package = tmp_path / "futures"
    package.mkdir()
    _write_tar_zst(
        package / "rqdatac_contract_1m_none_2025.tar.zst",
        [
            (
                "2025/unit_0000.parquet",
                _parquet_bytes(
                    [
                        _contract_record("2025-01-02 21:01:00"),
                        _contract_record("2025-01-03 09:01:00"),
                    ]
                ),
            ),
            (
                "2025/unit_0001.parquet",
                _parquet_bytes([_contract_record("2025-01-03 21:01:00")]),
            ),
        ],
    )
    return package


def test_adapter_refuses_spec_evidence_mismatch(tmp_path: Path) -> None:
    package = _futures_package(tmp_path)
    store = init_store(tmp_path / "store")
    try:
        from research_store.models import AssetRef

        from research_store.importers.safeio import file_sha256

        archive = package / "rqdatac_contract_1m_none_2025.tar.zst"
        asset = AssetRef(
            asset_id="asset-x",
            origin=str(archive),
            format="tar_zst_parquet",
            size=archive.stat().st_size,
            sha256=file_sha256(archive),
        )
        # declared END without any evidence scope: refused before reading
        sink_end = StoreSink(
            store,
            asset,
            build_rq_futures_spec("contract_1m_none", "1m", time_label="end"),
            adapter="rq_futures/0.1",
            config={},
            batch_id="b-end",
            spool_dir=tmp_path / "spool-end",
            candidate_dir=tmp_path / "cand-end",
        )
        with pytest.raises(ValueError, match="source_time_label"):
            import_rq_futures(
                package,
                "contract_1m_none",
                sink_end,
                batch_id="b-end",
                staging_dir=tmp_path / "staging-end",
            )
        # evidence scope with a mismatching UNKNOWN spec: refused as well
        sink_unknown = StoreSink(
            store,
            asset,
            build_rq_futures_spec("contract_1m_none", "1m"),
            adapter="rq_futures/0.1",
            config={},
            batch_id="b-unk",
            spool_dir=tmp_path / "spool-unk",
            candidate_dir=tmp_path / "cand-unk",
        )
        with pytest.raises(ValueError, match="source_time_label"):
            import_rq_futures(
                package,
                "contract_1m_none",
                sink_unknown,
                batch_id="b-unk",
                staging_dir=tmp_path / "staging-unk",
                label_scope=_scope(input_sha256=file_sha256(archive)),
            )
        # wrong dataset scope: refused
        with pytest.raises(ValueError, match="dataset"):
            import_rq_futures(
                package,
                "dominant_1m_none",
                sink_unknown,
                batch_id="b-ds",
                staging_dir=tmp_path / "staging-ds",
                label_scope=_scope(),
            )
    finally:
        store.close()


def test_adapter_member_filter_is_bounded_and_loud(tmp_path: Path) -> None:
    package = _futures_package(tmp_path)
    sink = CountingSink()
    receipt = import_rq_futures(
        package,
        "contract_1m_none",
        sink,
        batch_id="b-members",
        staging_dir=tmp_path / "staging",
        years=[2025],
        members={"2025/unit_0000.parquet"},
    )
    assert receipt.rows_read == 2  # only the requested member's rows
    assert receipt.extras["members_filter"] == ["2025/unit_0000.parquet"]
    assert [row["source_label"] for row in sink.rows] == [
        "2025-01-02 21:01:00",
        "2025-01-03 09:01:00",
    ]
    with pytest.raises(MemberReadError, match="unit_0009"):
        import_rq_futures(
            package,
            "contract_1m_none",
            CountingSink(),
            batch_id="b-missing",
            staging_dir=tmp_path / "staging2",
            members={"2025/unit_0009.parquet"},
        )


def test_default_path_routes_unknown_rows_to_candidates_with_dates(
    tmp_path: Path,
) -> None:
    """The real-situation shape: default UNKNOWN rows plus the exact-key
    date mapper produce candidate-only output that keeps trading-date
    lineage; nothing canonical is published."""
    package = _futures_package(tmp_path)
    mapping = DominantMapping()
    mapping.add("A2505", "2025-01-02 21:01:00", "2025-01-03")
    mapping.add("A2505", "2025-01-03 09:01:00", "2025-01-03")
    mapper = ContractDateMapper(mapping)

    store = init_store(tmp_path / "store")
    try:
        from research_store.models import AssetRef

        from research_store.importers.safeio import file_sha256

        archive = package / "rqdatac_contract_1m_none_2025.tar.zst"
        asset = AssetRef(
            asset_id="asset-contract",
            origin=str(archive),
            format="tar_zst_parquet",
            size=archive.stat().st_size,
            sha256=file_sha256(archive),
        )
        sink = StoreSink(
            store,
            asset,
            build_rq_futures_spec("contract_1m_none", "1m"),
            adapter="rq_futures/0.1",
            config={"archive": archive.name},
            batch_id="b-cand",
            spool_dir=tmp_path / "spool",
            candidate_dir=tmp_path / "cand",
        )
        receipt = import_rq_futures(
            package,
            "contract_1m_none",
            sink,
            batch_id="b-cand",
            staging_dir=tmp_path / "staging",
            years=[2025],
            date_mapper=mapper,
        )
        assert receipt.rows_read == 3
        publish = sink.publish()
        assert publish is None  # nothing canonical: all rows stay candidates
        summary = sink.summary(publish)
        assert summary["publish"]["state"] == "no_publishable_rows"
        assert summary["counts"]["candidate_rows"] == 3
        candidates = list(iter_candidates(summary["candidate_file"]))
        by_label = {entry["candidate"]["source_label"]: entry for entry in candidates}
        matched = by_label["2025-01-02 21:01:00"]["candidate"]
        assert matched["bar_start_ns"] is None  # still an unknown-label row
        assert "source_time_label_unknown" in matched["quality_flags"]
        # ... but the exact-key date transfer survived on the candidate
        assert matched["trading_date"] == "2025-01-03"
        assert (
            matched["extensions"]["trading_date_source"]["method"]
            == "dominant_map_exact_key"
        )
        unmatched = by_label["2025-01-03 21:01:00"]["candidate"]
        assert unmatched["trading_date"] is None
        assert "trading_date_unknown_no_calendar" in unmatched["quality_flags"]
        # no batch and no dataset ever reached the catalog
        assert store.catalog.query_one(
            "SELECT batch_id FROM batches WHERE batch_id='b-cand'"
        ) is None
        assert store.catalog.query_one(
            "SELECT dataset_id FROM datasets"
        ) is None
    finally:
        store.close()


def test_scoped_import_publishes_only_evidenced_rows(tmp_path: Path) -> None:
    """Engineering proof with a SYNTHETIC scope: covered rows publish with
    END bounds, uncovered rows stay candidates. This does not qualify any
    real archive (the real A2505 window has no accepted label evidence)."""
    package = _futures_package(tmp_path)
    from research_store.models import AssetRef

    from research_store.importers.safeio import file_sha256

    archive = package / "rqdatac_contract_1m_none_2025.tar.zst"
    archive_sha = file_sha256(archive)
    scope = _scope(input_sha256=archive_sha)

    store = init_store(tmp_path / "store")
    try:
        asset = AssetRef(
            asset_id="asset-scoped",
            origin=str(archive),
            format="tar_zst_parquet",
            size=archive.stat().st_size,
            sha256=archive_sha,
        )
        sink = StoreSink(
            store,
            asset,
            build_rq_futures_spec("contract_1m_none", "1m", time_label="end"),
            adapter="rq_futures/0.1",
            config={
                "archive": archive.name,
                "label_scope_identity": scope.identity,
            },
            batch_id="b-scoped",
            spool_dir=tmp_path / "spool",
            candidate_dir=tmp_path / "cand",
        )
        receipt = import_rq_futures(
            package,
            "contract_1m_none",
            sink,
            batch_id="b-scoped",
            staging_dir=tmp_path / "staging",
            years=[2025],
            members={"2025/unit_0000.parquet"},
            label_scope=scope,
        )
        assert receipt.extras["label_conclusion"] == "end"
        publish = sink.publish()
        assert publish is not None and publish.state.value == "published"
        # both unit_0000 rows are inside the synthetic scope and publish;
        # the unit_0001 row was never read (member filter)
        assert publish.accepted_rows == 2
        assert json.loads(
            store.catalog.query_one(
                "SELECT semantic_json FROM datasets"
            )["semantic_json"]
        )["source_time_label"] == "end"
    finally:
        store.close()


def test_dominant_mapping_build_unchanged(tmp_path: Path) -> None:
    package = tmp_path / "dom"
    package.mkdir()
    _write_tar_zst(
        package / "rqdatac_dominant_1m_none_2025.tar.zst",
        [
            (
                "2025/unit_0000.parquet",
                _parquet_bytes(
                    [
                        {
                            "datetime": "2025-01-02 21:01:00",
                            "dominant_id": "A2505",
                            "trading_date": "2025-01-03",
                        },
                        {
                            "datetime": "2025-01-02 21:01:00",
                            "dominant_id": "B2505",
                            "trading_date": "2025-01-03",
                        },
                    ]
                ),
            )
        ],
    )
    mapping = build_dominant_mapping(package, staging_dir=tmp_path / "spool")
    assert mapping.entries[("A2505", "2025-01-02 21:01:00")] == "2025-01-03"
    assert mapping.duplicate_keys == 0
    assert ContractDateMapper(mapping).lookup("A2505", "2025-01-02 21:01:00") == (
        "2025-01-03"
    )
