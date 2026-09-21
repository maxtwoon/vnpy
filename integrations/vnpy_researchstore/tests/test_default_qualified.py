"""Default-qualified exclusion policy over PUBLISHED store data.

Coordinator reconciliation 2026-09-16 (COORDINATOR_IMPORT_REQUIREMENTS):
ALL deterministic repaired ETF keys — the full 133-key set embedded in the
rebuilt base archives — are excluded from DEFAULT qualified backtest data.
The 118 volume/amount and 119 any-market-field disputed sets are subsets,
never replacements. Exclusions must be proven by explicit row/gap counts
with real bar bounds, and old/new/upstream candidates must be preserved.

These tests publish synthetic ETF data carrying a deterministic repair that
MATCHES the upstream refetch observation, a DISPUTED repair, and a plain
row through the real StoreSink core boundary, then evaluate the policy.

Fixture data is synthetic and clearly labelled; no real source archives are
touched. Real WP10 validation remains a later work package.
"""

from __future__ import annotations

import csv
import io
import json
import tarfile
from pathlib import Path
from typing import Any

import pytest

from _rs_import_bootstrap import PYARROW_AVAILABLE, ZSTANDARD_AVAILABLE

from research_store.importers.adapters import import_rq_etf
from research_store.importers.core_bridge import build_rq_etf_spec
from research_store.importers.repair_index import load_repair_index
from research_store.importers.store_sink import StoreSink
from research_store.models import (
    CoverageGapError,
    KnownGap,
    Selection,
    SnapshotRequest,
    compute_dataset_id,
)
from research_store.quality import store_default_qualified, store_quality
from research_store.snapshots import freeze, load_snapshot_manifest, open_snapshot
from research_store.store import init_store

pytestmark = pytest.mark.skipif(
    not (ZSTANDARD_AVAILABLE and PYARROW_AVAILABLE),
    reason="zstandard and pyarrow required",
)

_LABEL_MATCHING = "2017-09-19 13:01:00"
_LABEL_DISPUTED = "2017-09-19 13:02:00"
_LABEL_PLAIN = "2017-09-19 13:03:00"


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


def _repair_package(package: Path) -> None:
    """Two repaired keys: one matching the refetch, one disputed on volume."""
    (package / "QUALITY_REPAIR_20260905.json").write_text(
        json.dumps({"repair_date": "2026-09-05"}), encoding="utf-8"
    )
    changes = []
    for label, volume, amount, old_amount in (
        (_LABEL_MATCHING, "0", "0", "-100"),
        (_LABEL_DISPUTED, "0", "0", "-100"),
    ):
        base = {
            "order_book_id": "160105.XSHE",
            "datetime": label,
            "open": "1.0",
            "high": "1.0",
            "low": "1.0",
            "close": "1.0",
        }
        before = dict(base, volume=volume, amount=old_amount, num_trades="0.0")
        after = dict(base, volume=volume, amount=amount, num_trades="0.0")
        changes.append(
            {
                "dataset": "etf_lof",
                "file": "2017/160105.XSHE.csv",
                "order_book_id": "160105.XSHE",
                "datetime": label,
                "reasons": "negative_turnover_or_volume_to_zero",
                "before": json.dumps(before),
                "after": json.dumps(after),
            }
        )
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(changes[0]))
    writer.writeheader()
    writer.writerows(changes)
    (package / "quality_repair_changes_20260905.csv").write_text(
        out.getvalue(), encoding="utf-8"
    )

    audit_dir = package / "RQDataC_customer_feedback_supplement_20260912" / "01_etf_lof"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_rows = []
    for label, refetch_volume in (
        # repaired 0 matches the refetch observation -> deterministic
        (_LABEL_MATCHING, "0"),
        # repaired 0 differs from the refetched 15000 -> disputed
        (_LABEL_DISPUTED, "15000"),
    ):
        row: dict[str, str] = {name: "" for name in (
            "order_book_id", "datetime", "repair_rule",
            "open_old", "open_new", "open_upstream_refetch",
            "high_old", "high_new", "high_upstream_refetch",
            "low_old", "low_new", "low_upstream_refetch",
            "close_old", "close_new", "close_upstream_refetch",
            "volume_old", "volume_new", "volume_upstream_refetch",
            "amount_old", "amount_new", "amount_upstream_refetch",
            "num_trades_old", "num_trades_new", "num_trades_upstream_refetch",
        )}
        row.update(
            {
                "order_book_id": "160105.XSHE",
                "datetime": label,
                "repair_rule": "negative_turnover_or_volume_to_zero",
                "open_old": "1", "open_new": "1", "open_upstream_refetch": "1",
                "high_old": "1", "high_new": "1", "high_upstream_refetch": "1",
                "low_old": "1", "low_new": "1", "low_upstream_refetch": "1",
                "close_old": "1", "close_new": "1", "close_upstream_refetch": "1",
                "volume_old": "15000", "volume_new": "0",
                "volume_upstream_refetch": refetch_volume,
                "amount_old": "-100", "amount_new": "0",
                "amount_upstream_refetch": "0" if refetch_volume == "0" else "15840",
                "num_trades_old": "0", "num_trades_new": "0",
                "num_trades_upstream_refetch": "0",
            }
        )
        audit_rows.append(row)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(audit_rows[0]))
    writer.writeheader()
    writer.writerows(audit_rows)
    (audit_dir / "source_refetch_audit.csv").write_text(
        out.getvalue(), encoding="utf-8"
    )


@pytest.fixture()
def published_store(tmp_path: Path) -> dict[str, Any]:
    package = tmp_path / "etf"
    package.mkdir()
    archive = package / "rqdatac_etf_lof_1m_2017.tar.zst"
    _write_tar_zst(
        archive,
        [
            (
                "2017/160105.XSHE.csv",
                _etf_csv(
                    [
                        # repaired rows carry the repaired (0/0) values
                        f"160105.XSHE,{_LABEL_MATCHING},1,1,1,1,0,0,0",
                        f"160105.XSHE,{_LABEL_DISPUTED},1,1,1,1,0,0,0",
                        # plain row: never repaired
                        f"160105.XSHE,{_LABEL_PLAIN},1,1,1,1,10,10,1",
                    ]
                ),
            )
        ],
    )
    _repair_package(package)
    repair_index = load_repair_index(package)
    assert repair_index.repaired_count == 2
    assert repair_index.disputed_count == 1

    from research_store.importers.safeio import file_sha256

    store = init_store(tmp_path / "store")
    spec = build_rq_etf_spec("1m")
    sink = StoreSink(
        store,
        type(
            "A",
            (),
            {
                "asset_id": "asset-etf-2017",
                "origin": str(archive),
                "format": "tar_zst_csv",
                "size": archive.stat().st_size,
                "sha256": file_sha256(archive),
            },
        )(),
        spec,
        adapter="rq_etf/0.1",
        config={"archive": archive.name},
        batch_id="b-etf-2017",
    )
    receipt_adapter = import_rq_etf(
        package,
        sink,
        batch_id="b-etf-2017",
        frequency="1m",
        years=[2017],
        repair_index=repair_index,
    )
    assert receipt_adapter.rows_accepted == 3
    receipt = sink.publish()
    assert receipt is not None and receipt.state.value == "published"
    sink.cleanup_spool()
    return {
        "store": store,
        "root": tmp_path / "store",
        "dataset_id": compute_dataset_id(spec),
    }


def test_all_repaired_keys_excluded_from_default_qualified(
    published_store: dict[str, Any],
) -> None:
    store = published_store["store"]
    dataset_id = published_store["dataset_id"]
    payload = store_default_qualified(store, dataset_id)
    # BOTH repaired keys are excluded: the matching (deterministic) repair
    # AND the disputed one — the full repaired-key rule, not 118/119 subsets.
    assert payload["rows_total"] == 3
    assert payload["rows_excluded"] == 2
    assert payload["rows_qualified"] == 1
    assert payload["excluded_by_flag"]["repaired_deterministic"] == 1
    assert payload["excluded_by_flag"]["disputed_upstream_refetch"] == 1
    assert payload["excluded_gap_count"] == 2
    # old/new/upstream candidates preserved on every excluded row
    assert payload["candidates_preserved"] == {
        "old_new": 2,
        "upstream_refetch": 2,
        "missing": 0,
    }
    # gap bounds are the rows' REAL normalized bounds (END label 13:01
    # covers 13:00-13:01 Asia/Shanghai -> bar_start != bar_end)
    gaps = payload["excluded_gaps"]
    assert len(gaps) == 2
    for gap in gaps:
        assert gap["instrument"] == "160105.XSHE"
        assert isinstance(gap["start_ns"], int) and isinstance(gap["end_ns"], int)
        assert gap["end_ns"] - gap["start_ns"] == 60_000_000_000  # one minute
    labels = {gap["source_label"] for gap in gaps}
    assert labels == {_LABEL_MATCHING, _LABEL_DISPUTED}


def test_store_quality_carries_default_qualified_section(
    published_store: dict[str, Any],
) -> None:
    payload = store_quality(published_store["store"], published_store["dataset_id"])
    dq = payload["default_qualified"]
    assert dq["rows_excluded"] == 2
    assert dq["rows_qualified"] == 1
    # annotation counts still distinguish provenance from damage
    assert payload["issue_counts"]["annotation:repaired_deterministic"] == 1
    assert payload["issue_counts"]["annotation:disputed_upstream_refetch"] == 1


def test_cli_quality_surfaces_default_qualified(
    published_store: dict[str, Any], capsys: pytest.CaptureFixture
) -> None:
    from research_store.cli import EXIT_OK, main

    store = published_store["store"]
    store.close()
    code = main(
        [
            "--root",
            str(published_store["root"]),
            "quality",
            "--dataset-id",
            published_store["dataset_id"],
        ]
    )
    out = capsys.readouterr()
    assert code == EXIT_OK, out.out
    payload = json.loads(out.out)
    assert payload["quality"]["default_qualified"]["rows_excluded"] == 2
    assert payload["quality"]["default_qualified"]["excluded_gap_count"] == 2


def test_partition_scoping(published_store: dict[str, Any]) -> None:
    payload = store_default_qualified(
        published_store["store"], published_store["dataset_id"], partitions=[]
    )
    assert payload["rows_total"] == 0
    assert payload["rows_excluded"] == 0


# ---------------------------------------------------------------------------
# Default enforcement through freeze -> snapshot reader (consumers03 HIGH fix)
# ---------------------------------------------------------------------------


def _freeze(store: Any, dataset_id: str, gaps: tuple[KnownGap, ...] = ()) -> Any:
    return freeze(store, SnapshotRequest(selections=(Selection(dataset_id, "*"),), allow_known_gaps=gaps))


def _read_labels(store: Any, snapshot_id: str, dataset_id: str, **kwargs: Any) -> list[str]:
    reader = open_snapshot(store, snapshot_id)
    try:
        rows = [
            r
            for b in reader.bars(
                dataset_id, required_fields=(), allow_missing_auxiliary=True, **kwargs
            )
            for r in b.to_pylist()
        ]
    finally:
        reader.close()
    return sorted(r["source_label"] for r in rows)


def test_freeze_captures_default_qualified_exclusions(
    published_store: dict[str, Any],
) -> None:
    store = published_store["store"]
    dataset_id = published_store["dataset_id"]
    ref = _freeze(store, dataset_id)
    manifest = load_snapshot_manifest(store, ref.snapshot_id)
    captured = manifest["default_qualified_exclusions"]
    assert len(captured) == 2
    labels = {e["source_label"] for e in captured}
    assert labels == {_LABEL_MATCHING, _LABEL_DISPUTED}
    for entry in captured:
        assert entry["dataset_id"] == dataset_id
        assert entry["instrument"] == "160105.XSHE"
        assert entry["end_ns"] - entry["start_ns"] == 60_000_000_000
    assert {tuple(e["flags"]) for e in captured} == {
        ("repaired_deterministic",),
        ("disputed_upstream_refetch",),
    }


def test_default_reader_refuses_excluded_rows(
    published_store: dict[str, Any],
) -> None:
    store = published_store["store"]
    dataset_id = published_store["dataset_id"]
    ref = _freeze(store, dataset_id)
    reader = open_snapshot(store, ref.snapshot_id)
    try:
        with pytest.raises(CoverageGapError, match="default-qualified exclusion"):
            list(
                reader.bars(
                    dataset_id, required_fields=(), allow_missing_auxiliary=True
                )
            )
    finally:
        reader.close()


def test_explicit_gap_allowance_keeps_excluded_rows_absent(
    published_store: dict[str, Any],
) -> None:
    """The allowance permits the missing interval, never the rejected row."""
    store = published_store["store"]
    dataset_id = published_store["dataset_id"]
    payload = store_default_qualified(store, dataset_id)
    gaps = tuple(
        KnownGap(
            dataset_id=dataset_id,
            start_ns=int(g["start_ns"]),
            end_ns=int(g["end_ns"]),
            reason="synthetic fixture: accepted known gap for deterministic repaired key",
        )
        for g in payload["excluded_gaps"]
    )
    ref_default = _freeze(store, dataset_id)
    ref_allowed = _freeze(store, dataset_id, gaps)
    assert ref_allowed.snapshot_id != ref_default.snapshot_id
    labels = _read_labels(store, ref_allowed.snapshot_id, dataset_id)
    assert labels == [_LABEL_PLAIN]


def test_observational_read_returns_all_rows_with_provenance(
    published_store: dict[str, Any],
) -> None:
    """Explicit observational access stays distinguishable: every pinned row
    (including excluded ones) is visible with its repair provenance."""
    store = published_store["store"]
    dataset_id = published_store["dataset_id"]
    ref = _freeze(store, dataset_id)
    reader = open_snapshot(store, ref.snapshot_id)
    try:
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
    finally:
        reader.close()
    assert len(rows) == 3
    repaired = [
        r for r in rows
        if r["source_label"] in {_LABEL_MATCHING, _LABEL_DISPUTED}
    ]
    assert len(repaired) == 2
    for row in repaired:
        quality = json.loads(str(row["field_quality"]))
        assert quality["repair"]["old"]  # old/new candidate preserved


def test_pre_policy_snapshot_is_recognizably_legacy_unqualified(
    published_store: dict[str, Any],
) -> None:
    """A manifest without the capture key (frozen before this policy existed)
    is recognizably LEGACY UNQUALIFIED: default qualified reads refuse it
    (never silently presenting repaired rows as qualified), observational
    access keeps its prior meaning, and the old bytes are never rewritten."""
    store = published_store["store"]
    dataset_id = published_store["dataset_id"]
    ref = _freeze(store, dataset_id)
    manifest = load_snapshot_manifest(store, ref.snapshot_id)
    legacy = dict(manifest)
    legacy.pop("default_qualified_exclusions")
    legacy["snapshot_format"] = 1
    legacy["snapshot_id"] = "snap-legacyqfix04000"
    legacy_path = published_store["root"] / "manifests" / "snapshots" / "snap-legacyqfix04000.json"
    legacy_bytes = json.dumps(legacy).encode("utf-8")
    legacy_path.write_bytes(legacy_bytes)
    try:
        reader = open_snapshot(store, "snap-legacyqfix04000")
        try:
            assert reader.default_qualified_status(dataset_id) == "legacy_unqualified"
            with pytest.raises(CoverageGapError, match="predates the default-qualified"):
                list(
                    reader.bars(
                        dataset_id, required_fields=(), allow_missing_auxiliary=True
                    )
                )
            labels = _read_labels(
                store, "snap-legacyqfix04000", dataset_id, include_default_excluded=True
            )
            assert sorted(labels) == sorted(
                [_LABEL_MATCHING, _LABEL_DISPUTED, _LABEL_PLAIN]
            )
        finally:
            reader.close()
        # Old bytes unchanged: the refusal never mutates the manifest.
        assert legacy_path.read_bytes() == legacy_bytes
    finally:
        legacy_path.unlink()


def test_clean_dataset_default_read_unchanged(tmp_path: Path) -> None:
    """Ordinary clean data: no exclusions captured, default read unchanged."""
    package = tmp_path / "etf_clean"
    package.mkdir()
    archive = package / "rqdatac_etf_lof_1m_2017.tar.zst"
    _write_tar_zst(
        archive,
        [
            (
                "2017/160105.XSHE.csv",
                _etf_csv([f"160105.XSHE,{_LABEL_PLAIN},1,1,1,1,10,10,1"]),
            )
        ],
    )
    from research_store.importers.safeio import file_sha256

    store = init_store(tmp_path / "store_clean")
    spec = build_rq_etf_spec("1m")
    sink = StoreSink(
        store,
        type(
            "C",
            (),
            {
                "asset_id": "asset-etf-clean",
                "origin": str(archive),
                "format": "tar_zst_csv",
                "size": archive.stat().st_size,
                "sha256": file_sha256(archive),
            },
        )(),
        spec,
        adapter="rq_etf/0.1",
        config={"archive": archive.name},
        batch_id="b-clean",
    )
    receipt_adapter = import_rq_etf(
        package, sink, batch_id="b-clean", frequency="1m", years=[2017]
    )
    assert receipt_adapter.rows_accepted == 1
    receipt = sink.publish()
    assert receipt is not None and receipt.state.value == "published"
    sink.cleanup_spool()
    dataset_id = compute_dataset_id(spec)
    ref = _freeze(store, dataset_id)
    manifest = load_snapshot_manifest(store, ref.snapshot_id)
    assert manifest["default_qualified_exclusions"] == []
    assert manifest["snapshot_format"] == 2
    reader = open_snapshot(store, ref.snapshot_id)
    try:
        assert reader.default_qualified_status(dataset_id) == "qualified"
    finally:
        reader.close()
    assert _read_labels(store, ref.snapshot_id, dataset_id) == [_LABEL_PLAIN]
    store.close()
