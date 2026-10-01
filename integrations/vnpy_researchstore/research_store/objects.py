"""Immutable content-hashed object storage.

Parquet files are written to staging, hashed, fsynced, and atomically renamed
into ``objects/<2-hex>/<sha256>.parquet`` on the same volume. Published objects
are never overwritten; a name collision with identical content is a dedup hit,
with different content it is an integrity failure (SHA-256 collision or bug).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .models import IntegrityError


@dataclass(frozen=True)
class ObjectRef:
    relpath: str  # relative to store root, forward slashes
    sha256: str
    size: int
    rows: int


def hash_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_path(path: Path) -> None:
    if path.is_dir():
        if os.name == "nt":
            return  # directory fsync is not supported on Windows
        fd = os.open(str(path), os.O_RDONLY)
    else:
        # Windows requires write access for fsync.
        fd = os.open(str(path), os.O_RDWR if os.name == "nt" else os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_rename(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)  # same-volume atomic rename
    _fsync_path(dst.parent)


def write_parquet_object(
    staging_dir: Path,
    objects_dir: Path,
    batches: list[pa.RecordBatch],
    schema: pa.Schema,
    root: Path,
) -> ObjectRef:
    """Write record batches as a Zstandard Parquet object.

    The file is first written to ``staging_dir`` (same volume as ``objects``),
    hashed, then atomically renamed to its content-addressed final path.
    """

    staging_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="obj-", suffix=".parquet", dir=staging_dir)
    os.close(fd)
    tmp_path = Path(tmp_name)
    rows = 0
    try:
        with pq.ParquetWriter(
            str(tmp_path), schema, compression="zstd", write_statistics=True
        ) as writer:
            for batch in batches:
                writer.write_batch(batch)
                rows += batch.num_rows
        _fsync_path(tmp_path)
        sha256 = hash_file(tmp_path)
        relpath = f"objects/{sha256[:2]}/{sha256}.parquet"
        final = root / relpath
        if final.exists():
            existing = hash_file(final)
            if existing != sha256:
                raise IntegrityError(f"object hash collision at {final}")
            tmp_path.unlink()  # dedup hit: identical content already published
        else:
            _atomic_rename(tmp_path, final)
        return ObjectRef(relpath=relpath, sha256=sha256, size=final.stat().st_size, rows=rows)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def write_json_manifest(staging_dir: Path, final_path: Path, payload: dict) -> str:
    """Atomically write an immutable JSON manifest; returns its sha256."""

    staging_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="mf-", suffix=".json", dir=staging_dir)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        text = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
        tmp_path.write_text(text, encoding="utf-8")
        _fsync_path(tmp_path)
        sha256 = hash_file(tmp_path)
        if final_path.exists():
            if hash_file(final_path) != sha256:
                raise IntegrityError(
                    f"manifest {final_path} already exists with different content"
                )
            tmp_path.unlink()
        else:
            _atomic_rename(tmp_path, final_path)
        return sha256
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def verify_object(root: Path, relpath: str, expected_sha256: str) -> None:
    """Fail loudly on missing/tampered published objects. Never falls back."""

    path = root / relpath
    if not path.is_file():
        raise IntegrityError(f"missing published object {path}")
    actual = hash_file(path)
    if actual != expected_sha256:
        raise IntegrityError(
            f"tampered object {path}: expected {expected_sha256}, got {actual}"
        )
