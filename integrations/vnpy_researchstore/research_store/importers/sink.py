"""Importer sink boundary toward the storage core.

The storage core (catalog/revisions/publish) is owned by the parallel core
workstream. Until its ``INTERFACES.md`` contract lands, importers emit
canonical rows through the small :class:`ImportSink` protocol below. The
core-side adapter will implement this protocol; standalone runs and tests use
:class:`JSONLImportSink` / :class:`CountingSink`.

This module must stay dependency-free (stdlib only) so the core can wrap it
without pulling importer internals.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class ImportSink(Protocol):
    """Receiver of canonical normalised rows, one member at a time."""

    def open_member(self, locator: str, meta: dict[str, Any]) -> None:
        """Announce the start of a member/table and its metadata."""

    def accept(self, rows: list[dict[str, Any]]) -> int:
        """Accept a chunk of rows; returns the number accepted."""

    def fail_member(self, locator: str, error: str) -> None:
        """Record that a member failed; previously accepted rows stand."""


@dataclass
class ImportCounts:
    input_rows: int = 0
    accepted_rows: int = 0
    quarantined_rows: int = 0
    parse_failures: int = 0
    members_opened: int = 0
    members_failed: int = 0
    extra: dict[str, int] = field(default_factory=dict)


class CountingSink:
    """Sink that only counts; used for dry runs and tests."""

    def __init__(self) -> None:
        self.counts = ImportCounts()
        self.rows: list[dict[str, Any]] = []
        self.failures: list[tuple[str, str]] = []

    def open_member(self, locator: str, meta: dict[str, Any]) -> None:
        self.counts.members_opened += 1

    def accept(self, rows: list[dict[str, Any]]) -> int:
        self.counts.input_rows += len(rows)
        self.counts.accepted_rows += len(rows)
        self.rows.extend(rows)
        return len(rows)

    def fail_member(self, locator: str, error: str) -> None:
        self.counts.members_failed += 1
        self.counts.parse_failures += 1
        self.failures.append((locator, error))


class JSONLImportSink:
    """Standalone sink writing canonical rows to gzipped JSONL.

    Used for real streaming runs before the core publisher is wired in and
    for evidence artefacts in reports. One output file per import batch.
    """

    def __init__(self, output_path: str | Path) -> None:
        self.path = Path(output_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = gzip.open(self.path, "wt", encoding="utf-8")
        self.counts = ImportCounts()

    def open_member(self, locator: str, meta: dict[str, Any]) -> None:
        self.counts.members_opened += 1
        self._fh.write(
            json.dumps({"_member": locator, "_meta": meta}, ensure_ascii=False) + "\n"
        )

    def accept(self, rows: list[dict[str, Any]]) -> int:
        for row in rows:
            self._fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.counts.input_rows += len(rows)
        self.counts.accepted_rows += len(rows)
        return len(rows)

    def fail_member(self, locator: str, error: str) -> None:
        self.counts.members_failed += 1
        self.counts.parse_failures += 1
        self._fh.write(
            json.dumps({"_failed_member": locator, "_error": error}) + "\n"
        )

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> JSONLImportSink:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = ["CountingSink", "ImportCounts", "ImportSink", "JSONLImportSink"]
