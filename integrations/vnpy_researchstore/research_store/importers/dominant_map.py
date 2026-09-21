"""RQ futures dominant-map ingestion and contract trading-date transfer.

Facts (see ``.coordination/FUTURES_INPUT_CANDIDATES.md``):

* ``dominant_1m_*`` members carry ``dominant_id`` + source ``trading_date``;
  ``contract_1m_none`` members do NOT carry ``trading_date``.
* A real contract's source trading_date may be transferred by EXACT key
  ``(order_book_id == dominant_id, source datetime)`` from the dominant rows —
  sourced date lineage, NOT natural-date arithmetic and NOT copying continuous
  prices into the contract. Only matched keys are mapped; unmatched keys stay
  unknown and are counted, never propagated to periods when the contract was
  not dominant.
* Duplicate mapping keys and same-key/different-date conflicts are counted
  and surfaced; conflicting keys are never used.

The mapping is a versioned artifact (gzip JSON + sha256 sidecar); its version
hash participates in the contract import's transform identity.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import ImporterError
from .readers import iter_tar_zst_parquet
from .safeio import file_sha256, read_sha256_sidecar

_TZ = timezone.utc


@dataclass
class DominantMapping:
    """Exact-key ``(dominant_id, source datetime) -> trading_date`` mapping."""

    entries: dict[tuple[str, str], str] = field(default_factory=dict)
    duplicate_keys: int = 0
    conflict_keys: list[dict[str, str]] = field(default_factory=list)
    source_archives: list[str] = field(default_factory=list)

    @property
    def version(self) -> str:
        canonical = json.dumps(
            {
                "entries": sorted(
                    [list(key), value] for key, value in self.entries.items()
                ),
                "source_archives": sorted(self.source_archives),
            },
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def add(self, dominant_id: str, label: str, trading_date: str) -> None:
        key = (dominant_id, label)
        prior = self.entries.get(key)
        if prior is None:
            self.entries[key] = trading_date
        elif prior == trading_date:
            self.duplicate_keys += 1
        else:
            self.conflict_keys.append(
                {
                    "dominant_id": dominant_id,
                    "datetime": label,
                    "kept": prior,
                    "rejected": trading_date,
                }
            )

    def stats(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "keys": len(self.entries),
            "duplicate_keys": self.duplicate_keys,
            "conflict_keys": len(self.conflict_keys),
            "source_archives": sorted(self.source_archives),
        }


def build_dominant_mapping(
    category_dir: str | Path,
    staging_dir: str | Path,
    years: list[int] | None = None,
    dataset: str = "dominant_1m_none",
    max_spool_bytes: int = 2 * 1024 * 1024 * 1024,
) -> DominantMapping:
    """Ingest ``dominant_*`` Parquet members into an exact-key mapping.

    Streams the same archives the bar importer reads; only the identity
    columns (``dominant_id``, ``datetime``, ``trading_date``,
    ``underlying_symbol``) are consumed. Rows lacking any key column are
    skipped and counted as conflicts evidence via stats (never guessed).
    """
    directory = Path(category_dir)
    archives = sorted(directory.glob(f"rqdatac_{dataset}_*.tar.zst"))
    if years is not None:
        wanted = {f"{year}.tar.zst" for year in years}
        archives = [a for a in archives if a.name.endswith(tuple(wanted))]
    if not archives:
        raise ImporterError(
            f"no rqdatac_{dataset}_*.tar.zst archives under {directory}"
        )
    mapping = DominantMapping()
    for archive in archives:
        mapping.source_archives.append(archive.name)
        for _stats, rows in iter_tar_zst_parquet(
            archive,
            staging_dir=Path(staging_dir) / archive.stem,
            max_spool_bytes=max_spool_bytes,
        ):
            if rows is None:
                continue
            for record in rows:
                dominant_id = record.get("dominant_id")
                label = record.get("datetime")
                trading_date = record.get("trading_date")
                if dominant_id is None or label is None or trading_date is None:
                    continue
                mapping.add(
                    str(dominant_id), str(label)[:19], str(trading_date)[:10]
                )
    return mapping


def save_dominant_mapping(mapping: DominantMapping, directory: str | Path) -> Path:
    """Write the mapping as gzip JSON plus a sha256 sidecar; returns path."""
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"dominant_map_{mapping.version[:12]}.json.gz"
    payload = {
        "format": "rq_dominant_map/1",
        "created_at": datetime.now(_TZ).isoformat(timespec="seconds"),
        "stats": mapping.stats(),
        "conflicts": mapping.conflict_keys,
        "entries": [
            [dominant_id, label, trading_date]
            for (dominant_id, label), trading_date in sorted(mapping.entries.items())
        ],
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    with gzip.open(path, "wb") as fh:
        fh.write(blob)
    digest = file_sha256(path)
    Path(str(path) + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return path


def load_dominant_mapping(path: str | Path) -> DominantMapping:
    """Load a mapping artifact, verifying its sha256 sidecar first."""
    artifact = Path(path)
    actual = file_sha256(artifact)
    expected = read_sha256_sidecar(Path(str(artifact) + ".sha256"))
    if actual != expected:
        raise ImporterError(
            f"dominant mapping {artifact} sha256 mismatch: {actual} != {expected}"
        )
    with gzip.open(artifact, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    if payload.get("format") != "rq_dominant_map/1":
        raise ImporterError(f"unsupported dominant mapping format in {artifact}")
    mapping = DominantMapping()
    mapping.source_archives = list(payload.get("stats", {}).get("source_archives", []))
    for dominant_id, label, trading_date in payload.get("entries", []):
        mapping.entries[(str(dominant_id), str(label))] = str(trading_date)
    return mapping


@dataclass
class ContractDateMapper:
    """Applies a :class:`DominantMapping` to real-contract rows.

    ``lookup`` returns the source trading_date for an exact
    ``(contract_id, source datetime)`` key, or ``None`` when the key is
    unmatched or conflicted. Counts are surfaced for the import receipt.
    """

    mapping: DominantMapping
    matched: int = 0
    unmatched: int = 0
    conflicted: int = 0

    def __post_init__(self) -> None:
        self._conflicted_keys = {
            (entry["dominant_id"], entry["datetime"])
            for entry in self.mapping.conflict_keys
        }

    def lookup(self, contract_id: str, label: str) -> str | None:
        key = (contract_id, str(label)[:19])
        if key in self._conflicted_keys:
            self.conflicted += 1
            return None
        trading_date = self.mapping.entries.get(key)
        if trading_date is None:
            self.unmatched += 1
            return None
        self.matched += 1
        return trading_date

    def stats(self) -> dict[str, Any]:
        return {
            "map_version": self.mapping.version,
            "matched_keys": self.matched,
            "unmatched_keys": self.unmatched,
            "conflicted_keys": self.conflicted,
        }


__all__ = [
    "ContractDateMapper",
    "DominantMapping",
    "build_dominant_mapping",
    "load_dominant_mapping",
    "save_dominant_mapping",
]
