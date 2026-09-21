from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from _rs_import_bootstrap import PYARROW_AVAILABLE, ZSTANDARD_AVAILABLE

needs_archive_deps = pytest.mark.skipif(
    not (ZSTANDARD_AVAILABLE and PYARROW_AVAILABLE),
    reason="zstandard and pyarrow required",
)


def _write_tar_zst(
    path: Path, entries: list[tuple[str, bytes]]
) -> None:
    import zstandard

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tf:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    path.write_bytes(zstandard.ZstdCompressor().compress(buffer.getvalue()))


@needs_archive_deps
def test_csv_member_failure_isolated(tmp_path: Path) -> None:
    from research_store.importers.readers import iter_tar_zst_csv

    good = b"a,b\n1,2\n"
    bad = b"\xff\xfe not utf8"
    archive = tmp_path / "mixed.tar.zst"
    _write_tar_zst(
        archive,
        [
            ("2026/good.csv", good),
            ("2026/broken.csv", bad),
            ("2026/readme.txt", b"skipped"),
        ],
    )
    results = list(iter_tar_zst_csv(archive))
    chunks = [(stats, chunk) for stats, chunk in results if chunk is not None]
    failures = [stats for stats, chunk in results if chunk is None]
    assert len(chunks) == 1
    assert chunks[0][1].rows == [{"a": "1", "b": "2"}]
    assert len(failures) == 1
    assert failures[0].member == "2026/broken.csv"
    assert failures[0].parse_failed


@needs_archive_deps
def test_unsafe_member_rejected_stream(tmp_path: Path) -> None:
    from research_store.importers.errors import UnsafeMemberError
    from research_store.importers.readers import iter_tar_zst_csv

    archive = tmp_path / "evil.tar.zst"
    _write_tar_zst(archive, [("../evil.csv", b"a\n1\n")])
    with pytest.raises(UnsafeMemberError):
        list(iter_tar_zst_csv(archive))


@needs_archive_deps
def test_csv_chunking_within_member(tmp_path: Path) -> None:
    from research_store.importers.readers import iter_tar_zst_csv

    rows = "x,y\n" + "\n".join(f"{i},{i}" for i in range(5)) + "\n"
    archive = tmp_path / "chunky.tar.zst"
    _write_tar_zst(archive, [("2026/big.csv", rows.encode())])
    results = list(iter_tar_zst_csv(archive, chunk_rows=2))
    chunks = [chunk for _, chunk in results if chunk is not None]
    assert [len(chunk.rows) for chunk in chunks] == [2, 2, 1]
    stats = [item for item, _ in results]
    assert stats[-1].rows_read == 5


@needs_archive_deps
def test_parquet_streaming_with_json_sidecar(tmp_path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    from research_store.importers.readers import iter_tar_zst_parquet

    table = pa.table(
        {
            "order_book_id": pa.array(["RB2605", "RB2605"]),
            "datetime": pa.array(
                ["2026-02-24 13:30:00", "2026-02-24 13:31:00"]
            ),
            "close": pa.array([3030.0, 3028.0]),
        }
    )
    sink = io.BytesIO()
    pq.write_table(table, sink)
    parquet_bytes = sink.getvalue()
    sidecar = b'{"dataset": "test", "unit": 0}'
    archive = tmp_path / "futures.tar.zst"
    _write_tar_zst(
        archive,
        [
            ("2026/unit_0000.parquet", parquet_bytes),
            ("2026/unit_0000.json", sidecar),
            ("2026/notparquet.parquet", b"NOPE" + b"x" * 10),
        ],
    )
    staging = tmp_path / "staging"
    results = list(
        iter_tar_zst_parquet(archive, staging_dir=staging, max_spool_bytes=10_000_000)
    )
    parquet_rows = [rows for _, rows in results if rows is not None]
    assert parquet_rows == [
        [
            {"order_book_id": "RB2605", "datetime": "2026-02-24 13:30:00", "close": 3030.0},
            {"order_book_id": "RB2605", "datetime": "2026-02-24 13:31:00", "close": 3028.0},
        ]
    ]
    json_members = [stats for stats, _ in results if "json" in stats.extras]
    assert json_members[0].extras["json"]["dataset"] == "test"
    failed = [stats for stats, _ in results if stats.parse_failed]
    assert any("magic" in (stats.error or "") for stats in failed)
    assert not staging.exists() or not any(staging.iterdir())


@needs_archive_deps
def test_parquet_spool_budget_enforced(tmp_path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    from research_store.importers.errors import MemberReadError
    from research_store.importers.readers import iter_tar_zst_parquet

    table = pa.table({"x": pa.array(list(range(1000)))})
    sink = io.BytesIO()
    pq.write_table(table, sink)
    archive = tmp_path / "big.tar.zst"
    _write_tar_zst(archive, [("2026/unit_0000.parquet", sink.getvalue())])
    with pytest.raises(MemberReadError):
        list(
            iter_tar_zst_parquet(
                archive,
                staging_dir=tmp_path / "staging",
                max_spool_bytes=8,  # far below the member size
            )
        )
