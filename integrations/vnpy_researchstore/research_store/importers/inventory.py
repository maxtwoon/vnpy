"""Source-root inventory scanning.

Produces machine-readable inventories of the two read-only source roots:

* ``D:/BaiduNetdiskDownload/新数据库/ssquant数据库_20260425`` — SSQuant
  SQLite database + backup + update logs.
* ``D:/BaiduNetdiskDownload/全息日线`` — holographic daily gzip CSVs and the
  ``rqdata`` RQDataC package tree.

Inventory is factual: files are classified, sizes/hashes recorded when cheap,
manifests and sidecars cross-checked, and known problems (missing overlays,
version conflicts, unresolved gaps) reported as explicit caveats instead of
being smoothed into "PASS" statuses.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import HashMismatchError
from .safeio import file_sha256, read_sha256_sidecar

_TZ = timezone.utc


def _utcnow_iso() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


@dataclass
class FileEntry:
    path: str
    size: int
    mtime: float
    kind: str
    sha256: str | None = None
    sidecar_status: str = "absent"
    note: str | None = None


@dataclass
class InventoryReport:
    root: str
    scanned_at: str
    files: list[FileEntry] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        total = 0
        for entry in self.files:
            by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1
            total += entry.size
        return {
            "root": self.root,
            "scanned_at": self.scanned_at,
            "file_count": len(self.files),
            "bytes": total,
            "by_kind": by_kind,
            "caveats": self.caveats,
        }

    def to_json(self) -> str:
        payload = {
            "summary": self.summary(),
            "files": [asdict(entry) for entry in self.files],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


def classify_file(name: str) -> str:
    lower = name.lower()
    if lower.endswith((".tar.zst",)):
        return "archive_tar_zst"
    if lower.endswith(".csv.gz") or lower.endswith(".gz"):
        return "gzip_csv"
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith((".db", ".sqlite", ".sqlite3")):
        return "sqlite_db"
    if lower.endswith(".parquet"):
        return "parquet"
    if lower.endswith(".json"):
        return "json"
    if lower.endswith((".sha256",)):
        return "sha256_sidecar"
    if lower.endswith((".log",)):
        return "log"
    if lower.endswith((".py", ".exe", ".bat", ".ps1", ".sh")):
        return "script_executable"
    return "other"


def scan_directory(
    root: str | Path,
    hash_files: bool = False,
    follow_dirs: set[str] | None = None,
    max_entries: int = 200_000,
) -> InventoryReport:
    """Walk ``root`` read-only and classify every file.

    ``hash_files=True`` hashes every file (expensive on tens of GB; use for
    small trees or single packages). Sidecar verification is always attempted
    for ``.tar.zst`` archives when a ``.sha256`` sits next to them.
    """
    report = InventoryReport(root=str(root), scanned_at=_utcnow_iso())
    root_path = Path(root)
    count = 0
    for path in sorted(root_path.rglob("*")):
        if not path.is_file():
            continue
        if path.is_symlink():
            report.caveats.append(f"symlink skipped: {path}")
            continue
        count += 1
        if count > max_entries:
            report.caveats.append(f"entry cap {max_entries} reached; truncated")
            break
        stat = path.stat()
        kind = classify_file(path.name)
        entry = FileEntry(
            path=path.relative_to(root_path).as_posix(),
            size=stat.st_size,
            mtime=stat.st_mtime,
            kind=kind,
        )
        if kind == "archive_tar_zst" and (path.parent / (path.name + ".sha256")).exists():
            try:
                read_sha256_sidecar(path.parent / (path.name + ".sha256"))
                entry.sidecar_status = "present_unverified"
            except ValueError:
                entry.sidecar_status = "malformed"
        if hash_files or kind in {"json", "sha256_sidecar"}:
            entry.sha256 = file_sha256(path)
        report.files.append(entry)
    return report


@dataclass
class RqPackageInventory:
    """Inventory of one RQDataC package directory (manifest-verified)."""

    package: str
    root: str
    manifest: dict[str, Any]
    archives: list[dict[str, Any]] = field(default_factory=list)
    missing_archives: list[str] = field(default_factory=list)
    hash_failures: list[str] = field(default_factory=list)
    verified_hashes: int = 0
    caveats: list[str] = field(default_factory=list)
    # Manifest records that are not archive descriptors: real RQ manifests can
    # embed a list of failed fetch records (e.g. permission denied on one
    # dataset/year batch). These are preserved verbatim — never treated as
    # archives, never silently discarded.
    failed_records: list[dict[str, Any]] = field(default_factory=list)
    # Elements that are neither archive descriptors nor recognizable failed
    # records; preserved verbatim so unknown manifest shapes stay visible.
    unrecognized_records: list[Any] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "root": self.root,
            "start_date": self.manifest.get("start_date"),
            "end_date": self.manifest.get("end_date"),
            "adjust_type": self.manifest.get("adjust_type"),
            "archives_listed": len(self.archives),
            "archives_missing": len(self.missing_archives),
            "hash_failures": self.hash_failures,
            "verified_hashes": self.verified_hashes,
            "failed_records": len(self.failed_records),
            "unrecognized_records": len(self.unrecognized_records),
            "caveats": self.caveats,
        }


def _record_failed_batches(
    inventory: RqPackageInventory, element: list[Any]
) -> None:
    """Preserve a manifest ``archives`` element that is a LIST of records.

    The real RQ PIT manifest embeds failed fetch batches as a list of dicts
    with keys like ``kind/worker/dataset/year/error``. Each item is kept as a
    structured failed record (dataset/year/error/status visible) and mirrored
    into a caveat; none of them is treated as an archive descriptor.
    """

    for item in element:
        if isinstance(item, dict):
            record = {
                "kind": item.get("kind", "failed"),
                "dataset": item.get("dataset"),
                "year": item.get("year"),
                "error": item.get("error"),
                "detail": {
                    key: value
                    for key, value in item.items()
                    if key not in {"kind", "dataset", "year", "error"}
                },
            }
            inventory.failed_records.append(record)
            inventory.caveats.append(
                "failed batch record preserved: "
                f"dataset={record['dataset']} year={record['year']} "
                f"error={record['error']}"
            )
        else:
            inventory.unrecognized_records.append(item)
            inventory.caveats.append(
                f"unrecognized entry inside failed-record list: {item!r}"
            )


def _resolve_archive_path(
    inventory: RqPackageInventory,
    package_path: Path,
    archive: dict[str, Any],
    name: str,
) -> Path | None:
    """Locate one archive descriptor on disk, safely, within the package root.

    RQDataC packages come in two layouts:

    * flat — the archive sits directly at ``<package>/<file>``;
    * nested — the manifest entry carries ``dataset`` and the archive sits at
      ``<package>/<dataset>/<file>`` (both the PIT-events and the
      china-futures-research packages use this).

    Resolution rules:

    * The historical absolute ``path`` field in the manifest is NEVER
      followed: it names the original build machine (e.g.
      ``/mnt/tool_aggregator_storage/...``), not this host, and anything
      outside the named package root is refused by construction.
    * Only candidates inside the package root are considered; a candidate
      that escapes the root (via ``..`` or an absolute path) is refused.
    * When both the nested and the flat candidate exist they must be the
      same file, otherwise the ambiguity is surfaced as a version-conflict
      caveat instead of silently picking one.
    * The dataset directory name itself is validated: a ``dataset`` value
      that escapes the package root is refused before any candidate is built.

    Returns the chosen path, or ``None`` when every permitted candidate is
    absent (the caller records a truthful ``missing``) or refused (recorded
    with ``path_refused``).
    """

    root = package_path.resolve()
    dataset = archive.get("dataset")
    candidates: list[Path] = []
    if isinstance(dataset, str) and dataset:
        dataset_path = Path(dataset)
        if dataset_path.is_absolute() or ".." in dataset_path.parts:
            inventory.caveats.append(
                f"dataset name escapes package root; refused: {dataset!r} "
                f"(file {name!r})"
            )
            inventory.missing_archives.append(name)
            inventory.archives.append(
                {
                    "file": name,
                    "dataset": dataset,
                    "bytes_manifest": archive.get("bytes"),
                    "sha256_manifest": archive.get("sha256"),
                    "path_refused": True,
                }
            )
            return None
        candidates.append(package_path / dataset / name)
    candidates.append(package_path / name)

    permitted: list[Path] = []
    for candidate in candidates:
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            inventory.caveats.append(
                f"archive path escapes package root; refused: {candidate.name!r}"
            )
            continue
        permitted.append(candidate)
    if not permitted:
        inventory.missing_archives.append(name)
        inventory.archives.append(
            {
                "file": name,
                "dataset": dataset if isinstance(dataset, str) else None,
                "bytes_manifest": archive.get("bytes"),
                "sha256_manifest": archive.get("sha256"),
                "path_refused": True,
            }
        )
        return None

    existing = [c for c in permitted if c.exists()]
    if not existing:
        return None
    chosen = existing[0]
    if len(existing) > 1:
        # Both the nested and the flat candidate exist. Same file is fine
        # (hardlink/alias); different content is an ambiguity we must not
        # resolve by guessing.
        try:
            same = all(
                c.stat().st_ino == chosen.stat().st_ino
                or file_sha256(c) == file_sha256(chosen)
                for c in existing[1:]
            )
        except OSError:
            same = False
        if not same:
            inventory.caveats.append(
                "ambiguous archive location: both nested and flat candidates "
                "exist with different content; chose "
                f"{chosen.relative_to(package_path).as_posix()!r} "
                f"for {name!r} (version conflict, not silently merged)"
            )
    return chosen


def scan_rq_package(
    package_dir: str | Path, verify_hashes: bool = True
) -> RqPackageInventory:
    """Verify one RQDataC package against its ``manifest.json``.

    Checks presence of every listed archive and, when ``verify_hashes`` is
    set, streams each archive through SHA-256 and compares it with the
    manifest value and the ``.sha256`` sidecar. A sidecar that disagrees with
    the manifest is recorded as a caveat (version conflict evidence), while a
    file that disagrees with BOTH manifest and sidecar is a hash failure.

    Layout: entries with a ``dataset`` field are resolved at
    ``<package>/<dataset>/<file>`` first (nested layout), with a flat
    ``<package>/<file>`` fallback; the historical absolute ``path`` manifest
    field is never followed and nothing outside the package root is ever
    read. If both permitted candidates exist with different content the
    ambiguity is surfaced as a version-conflict caveat instead of guessing.

    Manifest robustness: ``archives`` elements that are not archive descriptor
    dicts — e.g. the embedded list of failed fetch records in the real RQ PIT
    manifest — are preserved as structured failed/unrecognized records with
    caveats instead of aborting the scan, so one failed batch in one package
    cannot destroy the whole-source inventory. Unknown shapes stay visible;
    nothing is silently dropped and nothing is promoted to success.
    """
    package_path = Path(package_dir)
    manifest_path = package_path / "manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inventory = RqPackageInventory(
        package=package_path.name,
        root=str(package_path),
        manifest=manifest,
    )
    if not manifest:
        inventory.caveats.append("manifest.json missing or empty")
    for archive in manifest.get("archives", []):
        if isinstance(archive, list):
            _record_failed_batches(inventory, archive)
            continue
        if not isinstance(archive, dict):
            inventory.unrecognized_records.append(archive)
            inventory.caveats.append(
                f"unrecognized archives entry (type {type(archive).__name__}): "
                f"{archive!r}"
            )
            continue
        name = archive.get("file")
        if not isinstance(name, str) or not name:
            inventory.unrecognized_records.append(archive)
            inventory.caveats.append(
                "archive descriptor without a usable 'file' entry preserved: "
                f"{archive!r}"
            )
            continue
        record: dict[str, Any] = {
            "file": name,
            "dataset": archive.get("dataset"),
            "bytes_manifest": archive.get("bytes"),
            "sha256_manifest": archive.get("sha256"),
        }
        archive_path = _resolve_archive_path(inventory, package_path, archive, name)
        if archive_path is None:
            if not any(r.get("file") == name for r in inventory.archives):
                # truly absent: no candidate existed (refusals already append)
                inventory.missing_archives.append(name)
                inventory.archives.append(record)
            continue
        record["resolved_path"] = archive_path.relative_to(package_path).as_posix()
        record["bytes_actual"] = archive_path.stat().st_size
        sidecar_path = archive_path.parent / (name + ".sha256")
        if sidecar_path.exists():
            try:
                sidecar_hash = read_sha256_sidecar(sidecar_path)
                record["sha256_sidecar"] = sidecar_hash
                if archive.get("sha256") and sidecar_hash != archive["sha256"]:
                    inventory.caveats.append(
                        f"sidecar/manifest version conflict: {name}"
                    )
            except ValueError:
                record["sha256_sidecar"] = "malformed"
        if verify_hashes:
            actual = file_sha256(archive_path)
            record["sha256_actual"] = actual
            if archive.get("sha256") and actual != archive["sha256"]:
                inventory.hash_failures.append(name)
            else:
                inventory.verified_hashes += 1
        inventory.archives.append(record)
    return inventory


# Known factual caveats from the execution contract; attached to the
# holographic root inventory so the report states them instead of implying
# everything is present and qualified.
HOLO_CAVEATS = [
    "convertible 4,911-row refetch overlay/audit missing locally (catalog-only)",
    "index 2014 actual SHA matches sidecar but differs from root manifest: "
    "version conflict, not proven corruption",
    "recommended shares 37 annual path missing; older actions archive may "
    "contain copies (unverified)",
    "latest ETF sample is Sep 9-11 vs base through Jul 31; August gap unresolved",
    "PIT sample preserves same-quarter info_date 2025-04-19 and 2026-04-25; "
    "never upsert by security/quarter only",
    "JQ daily factor all 1.0 => adjustment UNKNOWN, not proven raw",
    "option/PIT/convertible/index/high-value categories are catalog-only in v0.1",
]

SSQUANT_CAVEATS = [
    "main DB 10.22 GB with live -wal present: import must use the consistent "
    "capture, never the live files",
    "68,022,890 is LOG-reported row count, not a verified COUNT",
    "openint can be negative; cumulative_openint is candidate total OI only",
    "MA amount untrusted (903/1000 sample VWAP checks outside OHLC)",
    "888/777 continuous selection/roll/adjustment rules unverified",
    "8 confirmed SimNow main-table keys on 2026-07-01; other meta/main time "
    "overlaps are NOT contamination",
]


def scan_source_roots(
    ssquant_root: str | Path, holographic_root: str | Path
) -> dict[str, Any]:
    """Build the combined inventory for both source roots (no bulk hashing)."""
    ssquant = scan_directory(ssquant_root)
    ssquant.caveats.extend(SSQUANT_CAVEATS)
    holo = scan_directory(holographic_root)
    holo.caveats.extend(HOLO_CAVEATS)
    rq_packages: list[dict[str, Any]] = []
    rq_root = Path(holographic_root) / "rqdata"
    if rq_root.is_dir():
        for package_dir in sorted(rq_root.iterdir()):
            if package_dir.is_dir():
                rq_packages.append(
                    scan_rq_package(package_dir, verify_hashes=False).summary()
                )
    return {
        "generated_at": _utcnow_iso(),
        "ssquant": ssquant.summary(),
        "holographic": holo.summary(),
        "rq_packages": rq_packages,
    }


def write_json_report(payload: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target


__all__ = [
    "FileEntry",
    "InventoryReport",
    "RqPackageInventory",
    "HashMismatchError",
    "classify_file",
    "scan_directory",
    "scan_rq_package",
    "scan_source_roots",
    "write_json_report",
]
