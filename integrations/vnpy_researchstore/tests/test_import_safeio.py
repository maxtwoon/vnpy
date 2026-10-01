from __future__ import annotations

import gzip
import tarfile
from pathlib import Path

import pytest

from _rs_import_bootstrap import ZSTANDARD_AVAILABLE

from research_store.importers.errors import (
    HashMismatchError,
    UnsafeMemberError,
)
from research_store.importers.safeio import (
    iter_gzip_csv_chunks,
    member_extension,
    read_sha256_sidecar,
    validate_member_name,
    verify_sha256_sidecar,
)


def _tarinfo(name: str, symlink: bool = False) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    if symlink:
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
    return info


@pytest.mark.parametrize(
    ("name", "ok"),
    [
        ("2011/510300.XSHG.csv", True),
        ("2025/unit_0000.parquet", True),
        ("manifest.json", True),
        ("../escape.csv", False),
        ("/abs/path.csv", False),
        ("back\\slash.csv", False),
        ("C:drive.csv", False),
        ("", False),
        ("..", False),
    ],
)
def test_validate_member_name(name: str, ok: bool) -> None:
    if ok:
        assert validate_member_name(name) == name
    else:
        with pytest.raises(UnsafeMemberError):
            validate_member_name(name)


def test_symlink_member_rejected() -> None:
    with pytest.raises(UnsafeMemberError):
        from research_store.importers.safeio import validate_member

        validate_member(_tarinfo("evil.csv", symlink=True))


def test_sidecar_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "data.bin"
    target.write_bytes(b"payload")
    sidecar = tmp_path / "data.bin.sha256"
    import hashlib

    sidecar.write_text(
        hashlib.sha256(b"payload").hexdigest() + "  data.bin\n", encoding="utf-8"
    )
    assert read_sha256_sidecar(sidecar) == hashlib.sha256(b"payload").hexdigest()
    assert verify_sha256_sidecar(target) == hashlib.sha256(b"payload").hexdigest()
    target.write_bytes(b"tampered")
    with pytest.raises(HashMismatchError):
        verify_sha256_sidecar(target)


def test_gzip_csv_chunking(tmp_path: Path) -> None:
    lines = ["code,value"] + [f"00000{i},1.5" for i in range(5)]
    path = tmp_path / "mini.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(lines) + "\n")
    chunks = list(iter_gzip_csv_chunks(path, chunk_rows=2))
    assert [len(chunk) for chunk in chunks] == [2, 2, 1]
    assert chunks[0][0] == {"code": "000000", "value": "1.5"}


def test_gzip_csv_empty_values_preserved(tmp_path: Path) -> None:
    path = tmp_path / "holes.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        fh.write("code,volume,amount\nA,,\nB,3,\n")
    chunk = next(iter_gzip_csv_chunks(path))
    assert chunk[0]["volume"] == "" and chunk[0]["amount"] == ""
    assert chunk[1]["volume"] == "3" and chunk[1]["amount"] == ""


def test_member_extension() -> None:
    assert member_extension("2025/unit_0000.parquet") == "parquet"
    assert member_extension("a/b/c.CSV") == "csv"


@pytest.mark.skipif(not ZSTANDARD_AVAILABLE, reason="zstandard not installed")
def test_tar_zst_streaming_reads_one_member_at_a_time(tmp_path: Path) -> None:
    import io

    import zstandard

    from research_store.importers.safeio import open_tar_zst, read_member_text

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tf:
        payload = "order_book_id,datetime,close\n510300.XSHG,2026-07-31 09:31:00,4.677\n"
        info = tarfile.TarInfo("2026/510300.XSHG.csv")
        data = payload.encode()
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    compressed = zstandard.ZstdCompressor().compress(buffer.getvalue())
    archive = tmp_path / "mini.tar.zst"
    archive.write_bytes(compressed)

    # streaming mode: members must be consumed inside the iteration
    tf = open_tar_zst(archive)
    texts = []
    count = 0
    for member in tf:
        count += 1
        texts.append(read_member_text(tf, member))
    tf.close()
    assert count == 1
    assert "4.677" in texts[0]
