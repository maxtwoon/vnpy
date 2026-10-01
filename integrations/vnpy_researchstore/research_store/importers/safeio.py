"""Safe low-level I/O primitives shared by all importers.

Guarantees implemented here:

* Archive members are validated before use: no absolute paths, no ``..``
  traversal, no backslashes, no drive letters, no symlinks or device nodes.
  ``tarfile.extractall`` is never called; members are consumed one at a time
  through streaming readers.
* ``.tar.zst`` archives are decompressed with the optional ``zstandard``
  package and read in streaming tar mode so only one member is resident.
* gzip CSV files are read in bounded row chunks (default 100,000 rows).
* Hashing is streaming and chunked.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import os
import tarfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .errors import MissingDependencyError, UnsafeMemberError

CHUNK_ROWS = 100_000
_HASH_BLOCK = 1024 * 1024

_ARCHIVES_PLAINTEXT = {"txt", "md", "csv", "json", "sha256"}


def _require_zstandard() -> Any:
    try:
        import zstandard
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise MissingDependencyError(
            "package 'zstandard' is required for .tar.zst archives; "
            "install it into the research store virtual environment"
        ) from exc
    return zstandard


def validate_member_name(name: str) -> str:
    """Validate a tar member name and return its normalised POSIX path.

    Rejects absolute paths, ``..`` segments, backslashes, Windows drive
    letters, empty names and any member that is not a plain relative path.
    """
    if not name:
        raise UnsafeMemberError("empty member name")
    if "\\" in name:
        raise UnsafeMemberError(f"backslash in member name: {name!r}")
    if ":" in name.split("/")[0] and name[0].isalpha():
        raise UnsafeMemberError(f"drive-letter-like member name: {name!r}")
    if name.startswith("/"):
        raise UnsafeMemberError(f"absolute member name: {name!r}")
    segments = name.split("/")
    if any(seg == ".." for seg in segments):
        raise UnsafeMemberError(f"traversal segment in member name: {name!r}")
    if name in (".", ".."):
        raise UnsafeMemberError(f"dot member name: {name!r}")
    return name


def validate_member(member: tarfile.TarInfo) -> tarfile.TarInfo:
    """Validate type-safety of a tar member (symlinks/devices rejected)."""
    validate_member_name(member.name)
    if member.issym() or member.islnk():
        raise UnsafeMemberError(f"symlink/hardlink member rejected: {member.name!r}")
    if member.isdev():
        raise UnsafeMemberError(f"device member rejected: {member.name!r}")
    return member


def file_sha256(path: str | os.PathLike[str]) -> str:
    """Stream a file through SHA-256 without loading it into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(_HASH_BLOCK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def read_sha256_sidecar(path: str | os.PathLike[str]) -> str:
    """Read a ``.sha256`` sidecar file and return the lowercase hex digest."""
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"empty sha256 sidecar: {path}")
    first_line = text.splitlines()[0].strip()
    token = first_line.split()[0]
    if len(token) != 64 or any(c not in "0123456789abcdefABCDEF" for c in token):
        raise ValueError(f"malformed sha256 sidecar: {path}")
    return token.lower()


def verify_sha256_sidecar(
    path: str | os.PathLike[str], sidecar: str | os.PathLike[str] | None = None
) -> str:
    """Hash ``path`` and compare with its ``.sha256`` sidecar.

    Returns the computed digest; raises :class:`HashMismatchError` on
    difference. The default sidecar path is ``str(path) + '.sha256'``.
    """
    from .errors import HashMismatchError

    sidecar_path = Path(sidecar) if sidecar is not None else Path(str(path) + ".sha256")
    expected = read_sha256_sidecar(sidecar_path)
    actual = file_sha256(path)
    if actual != expected:
        raise HashMismatchError(
            f"sha256 mismatch for {path}: expected {expected}, got {actual}"
        )
    return actual


def open_tar_zst(path: str | os.PathLike[str]) -> tarfile.TarFile:
    """Open a ``.tar.zst`` archive in streaming read mode.

    The returned ``TarFile`` uses ``r|`` semantics: members must be consumed
    strictly in order, one at a time, which is exactly the safety property the
    importers rely on.
    """
    zstandard = _require_zstandard()
    decompressor = zstandard.ZstdDecompressor()
    fh = open(path, "rb")
    try:
        stream = decompressor.stream_reader(fh)
        return tarfile.open(mode="r|", fileobj=stream)
    except BaseException:
        fh.close()
        raise


def iter_tar_zst_members(path: str | os.PathLike[str]) -> Iterator[tarfile.TarInfo]:
    """Yield validated file members of a ``.tar.zst`` archive one by one.

    Only metadata is read; call :func:`read_member_text` /
    :func:`read_member_bytes` on the open archive to consume content.
    Directory members are yielded as-is; callers skip them.
    """
    tf = open_tar_zst(path)
    try:
        for member in tf:
            if member.isdir():
                continue
            validate_member(member)
            yield member
    finally:
        tf.close()


def read_member_text(tf: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    """Read one already-validated member as UTF-8 text (bounded by member size
    as declared in the archive header; callers cap sizes beforehand)."""
    fileobj = tf.extractfile(member)
    if fileobj is None:
        raise UnsafeMemberError(f"member has no content: {member.name!r}")
    return fileobj.read().decode("utf-8")


def read_member_bytes(tf: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    """Read one already-validated member as raw bytes."""
    fileobj = tf.extractfile(member)
    if fileobj is None:
        raise UnsafeMemberError(f"member has no content: {member.name!r}")
    return fileobj.read()


def spool_member(
    tf: tarfile.TarFile, member: tarfile.TarInfo, staging_dir: Path
) -> Path:
    """Spool one member to a controlled staging directory for bounded random
    access (used for Parquet row-group reading).

    The spool file uses a flat, validated name so nothing outside
    ``staging_dir`` can be touched. Caller is responsible for deletion.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    safe_name = validate_member_name(member.name).replace("/", "__")
    target = staging_dir / safe_name
    if target.exists():
        raise UnsafeMemberError(f"staging collision: {target}")
    fileobj = tf.extractfile(member)
    if fileobj is None:
        raise UnsafeMemberError(f"member has no content: {member.name!r}")
    with open(target, "wb") as out:
        while True:
            block = fileobj.read(_HASH_BLOCK)
            if not block:
                break
            out.write(block)
    return target


def parse_csv_text(text: str) -> list[dict[str, str]]:
    """Parse CSV text into a list of string dicts (empty string stays empty,
    never coerced to zero by the reader layer)."""
    return list(csv.DictReader(io.StringIO(text)))


def iter_gzip_csv_chunks(
    path: str | os.PathLike[str], chunk_rows: int = CHUNK_ROWS
) -> Iterator[list[dict[str, str]]]:
    """Yield a gzip CSV file in chunks of at most ``chunk_rows`` dicts.

    Values are left as strings; NULL/empty handling belongs to normalisation
    so missing fields are never silently converted to zeros here.
    """
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        chunk: list[dict[str, str]] = []
        for row in reader:
            chunk.append(row)
            if len(chunk) >= chunk_rows:
                yield chunk
                chunk = []
        if chunk:
            yield chunk


def member_extension(name: str) -> str:
    """Return lowercase extension of a member or file name."""
    return Path(name).suffix.lower().lstrip(".")


def is_plaintext_member(name: str) -> bool:
    """True if the member extension is one of the known plaintext types."""
    return member_extension(name) in _ARCHIVES_PLAINTEXT
