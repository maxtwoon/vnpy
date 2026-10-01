"""Streaming readers for source archive formats.

Readers enforce the contract's streaming rules:

* CSV members and gzip CSV files are read in chunks of at most 100,000 rows.
* Exactly one compressed member of a ``.tar.zst`` archive is open at a time
  (streaming tar mode ``r|``).
* Parquet members are spooled to a controlled staging directory under an
  explicit byte budget and read row group by row group; the spool file is
  removed immediately after reading. Exceeding the budget fails loudly
  instead of silently materialising a whole archive.
* A member that fails to parse is reported to the caller and does not abort
  the remaining members.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import tarfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import MemberReadError
from .safeio import (
    CHUNK_ROWS,
    open_tar_zst,
    read_member_bytes,
    spool_member,
    validate_member,
)

_PARQUET_MAGIC = b"PAR1"


@dataclass
class MemberStats:
    """Per-member accounting required by the batch receipt."""

    member: str
    rows_read: int = 0
    parse_failed: bool = False
    error: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemberChunk:
    """One chunk of rows from one member, with provenance attached."""

    member: str
    rows: list[dict[str, Any]]


def _csv_chunks_from_bytes(
    data: bytes, chunk_rows: int
) -> Iterator[list[dict[str, str]]]:
    text = data.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    chunk: list[dict[str, str]] = []
    for row in reader:
        chunk.append(row)
        if len(chunk) >= chunk_rows:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def iter_tar_zst_csv(
    path: str | Path,
    chunk_rows: int = CHUNK_ROWS,
    member_filter: Callable[[str], bool] | None = None,
) -> Iterator[tuple[MemberStats, MemberChunk | None]]:
    """Stream all CSV members of a ``.tar.zst`` archive.

    Yields ``(stats, chunk)`` pairs. ``chunk`` is ``None`` for a member that
    failed validation or parsing; ``stats.parse_failed`` is set and the
    archive scan continues with the next member so one bad member can never
    be swallowed by successful neighbours. Directory and non-CSV members are
    skipped. When ``member_filter`` is given, members whose name fails the
    predicate are validated but their content is never read (fast
    instrument-restricted imports).
    """
    tf = open_tar_zst(path)
    try:
        for member in tf:
            if member.isdir():
                continue
            validate_member(member)
            if not member.name.lower().endswith(".csv"):
                continue
            if member_filter is not None and not member_filter(member.name):
                continue
            stats = MemberStats(member=member.name)
            try:
                data = read_member_bytes(tf, member)
            except Exception as exc:  # noqa: BLE001 - isolated per member
                stats.parse_failed = True
                stats.error = f"read failed: {exc}"
                yield stats, None
                continue
            try:
                for chunk in _csv_chunks_from_bytes(data, chunk_rows):
                    stats.rows_read += len(chunk)
                    yield stats, MemberChunk(member=member.name, rows=chunk)
            except Exception as exc:  # noqa: BLE001 - isolated per member
                stats.parse_failed = True
                stats.error = f"csv parse failed: {exc}"
                yield stats, None
    finally:
        tf.close()


class ParquetSpoolBudget:
    """Global byte budget for staged Parquet spool files."""

    def __init__(self, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("max_spool_bytes must be positive")
        self.max_bytes = max_bytes
        self.used = 0

    def charge(self, size: int) -> None:
        if self.used + size > self.max_bytes:
            raise MemberReadError(
                f"parquet spool budget exceeded: {self.used + size} > {self.max_bytes}"
            )
        self.used += size

    def release(self, size: int) -> None:
        self.used = max(0, self.used - size)


def iter_tar_zst_parquet(
    path: str | Path,
    staging_dir: str | Path,
    max_spool_bytes: int = 2 * 1024 * 1024 * 1024,
    slice_rows: int = 500_000,
) -> Iterator[tuple[MemberStats, list[dict[str, Any]] | None]]:
    """Stream Parquet members of a ``.tar.zst`` archive slice by slice.

    Each Parquet member is spooled to ``staging_dir`` (charged against the
    global budget), validated by magic bytes, read with pyarrow in slices of
    ``slice_rows`` rows, then deleted and the budget released. JSON sidecar
    members are yielded once with parsed content in
    ``stats.extras['json']`` and ``rows=None``.

    Yields ``(stats, rows)``; ``rows`` is ``None`` for JSON sidecars and for
    members that failed (``stats.parse_failed`` set).
    """
    import pyarrow.parquet as pq

    budget = ParquetSpoolBudget(max_spool_bytes)
    staging = Path(staging_dir)
    tf: tarfile.TarFile = open_tar_zst(path)
    try:
        for member in tf:
            if member.isdir():
                continue
            validate_member(member)
            lower = member.name.lower()
            stats = MemberStats(member=member.name)
            if lower.endswith(".json"):
                try:
                    stats.extras["json"] = json.loads(
                        read_member_bytes(tf, member).decode("utf-8")
                    )
                except Exception as exc:  # noqa: BLE001 - isolated per member
                    stats.parse_failed = True
                    stats.error = f"json parse failed: {exc}"
                yield stats, None
                continue
            if not lower.endswith(".parquet"):
                continue
            yield from _spool_read_release(
                tf, member, staging, budget, stats, slice_rows, pq
            )
    finally:
        tf.close()
        shutil.rmtree(staging, ignore_errors=True)


def _spool_read_release(
    tf: tarfile.TarFile,
    member: tarfile.TarInfo,
    staging: Path,
    budget: ParquetSpoolBudget,
    stats: MemberStats,
    slice_rows: int,
    pq: Any,
) -> Iterator[tuple[MemberStats, list[dict[str, Any]] | None]]:
    spool_path: Path | None = None
    try:
        budget.charge(member.size)
        try:
            spool_path = spool_member(tf, member, staging)
        except Exception as exc:  # noqa: BLE001 - isolated per member
            budget.release(member.size)
            stats.parse_failed = True
            stats.error = f"spool failed: {exc}"
            yield stats, None
            return
        try:
            with open(spool_path, "rb") as probe:
                if probe.read(4) != _PARQUET_MAGIC:
                    stats.parse_failed = True
                    stats.error = "missing parquet magic"
                    yield stats, None
                    return
            table = pq.read_table(spool_path)
        except Exception as exc:  # noqa: BLE001 - isolated per member
            stats.parse_failed = True
            stats.error = f"parquet read failed: {exc}"
            yield stats, None
            return
        total = table.num_rows
        offset = 0
        while offset < total:
            end = min(offset + slice_rows, total)
            stats.rows_read += end - offset
            yield stats, table.slice(offset, end - offset).to_pylist()
            offset = end
    finally:
        if spool_path is not None:
            spool_path.unlink(missing_ok=True)
            budget.release(member.size)
