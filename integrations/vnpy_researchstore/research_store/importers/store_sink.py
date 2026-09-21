"""Store-bound import sink: canonical rows -> core publish boundary.

:class:`StoreSink` implements the importer :class:`ImportSink` protocol against
a real research store:

* accepted rows are converted to ``BARS_SCHEMA_V1`` core rows immediately and
  spooled per CANONICAL partition (``importers.partitions``) as Arrow IPC
  stream files under a caller-controlled spool directory, so memory stays
  bounded regardless of archive size;
* rows that cannot become canonical bars (unknown label semantics, missing
  daily trading_date, ...) are NOT dropped: they are preserved with original
  labels and full payload in a gzip JSONL candidate file for the
  observation/inspection path, and counted in the receipt;
* :meth:`publish` sorts each partition spool into the core key order and
  drives the real ``research_store.revisions.import_asset`` boundary — no
  mock, no stand-in sink.

SSQuant ``table x month`` jobs and other input work units all feed the same
canonical partitions; the work unit is recorded in the batch config, not in
the partition strings.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.ipc as ipc

from .core_bridge import TRANSFORM_VERSION, CoreBridgeError, to_core_row
from .partitions import partition_for_row
from .sink import ImportCounts
from ..models import (
    AssetRef,
    ImportReceipt,
    ImportRequest,
    SemanticSpec,
    compute_dataset_id,
)
from ..revisions import import_asset
from ..schemas import BARS_SCHEMA_V1
from ..store import Store


class StoreSink:
    """ImportSink that publishes one source asset into a real store."""

    def __init__(
        self,
        store: Store,
        asset: AssetRef,
        spec: SemanticSpec,
        adapter: str,
        config: dict[str, str],
        batch_id: str,
        spool_dir: str | Path | None = None,
        candidate_dir: str | Path | None = None,
        transform_version: str = TRANSFORM_VERSION,
    ) -> None:
        self.store = store
        self.asset = asset
        self.spec = spec
        self.adapter = adapter
        self.config = config
        self.batch_id = batch_id
        self.transform_version = transform_version
        self.dataset_id = compute_dataset_id(spec)
        self.counts = ImportCounts()
        self.member_meta: dict[str, dict[str, Any]] = {}
        self.failures: list[tuple[str, str]] = []
        self._spool_dir = Path(spool_dir) if spool_dir else store.path.staging / "import_spool" / batch_id
        self._spool_dir.mkdir(parents=True, exist_ok=True)
        self._candidate_dir = (
            Path(candidate_dir)
            if candidate_dir
            else store.path.reports / "candidates"
        )
        self._writers: dict[str, tuple[pa.OSFile, ipc.RecordBatchStreamWriter]] = {}
        self._partition_rows: dict[str, int] = {}
        self._candidate_fh: Any = None
        self.candidate_path: Path | None = None

    # -- ImportSink protocol --------------------------------------------------

    def open_member(self, locator: str, meta: dict[str, Any]) -> None:
        self.counts.members_opened += 1
        self.member_meta[locator] = meta

    def accept(self, rows: list[dict[str, Any]]) -> int:
        accepted = 0
        for row in rows:
            self.counts.input_rows += 1
            try:
                core_row = to_core_row(
                    row,
                    dataset_id=self.dataset_id,
                    asset_id=self.asset.asset_id,
                    batch_id=self.batch_id,
                    transform_version=self.transform_version,
                    interval=self.spec.interval.value,
                )
                partition = partition_for_row(
                    row, self.spec.interval.value, self.spec.asset_class.value
                )
            except (CoreBridgeError, ValueError) as exc:
                self._write_candidate(row, f"{type(exc).__name__}: {exc}")
                continue
            self._write_core_row(partition, core_row)
            accepted += 1
        self.counts.accepted_rows += accepted
        return accepted

    def fail_member(self, locator: str, error: str) -> None:
        self.counts.members_failed += 1
        self.counts.parse_failures += 1
        self.failures.append((locator, error))

    # -- internals ------------------------------------------------------------

    def _write_core_row(self, partition: str, core_row: dict[str, Any]) -> None:
        writer_entry = self._writers.get(partition)
        if writer_entry is None:
            path = self._spool_path(partition)
            fh = pa.OSFile(str(path), "wb")
            writer_entry = (fh, ipc.new_stream(fh, BARS_SCHEMA_V1))
            self._writers[partition] = writer_entry
            self._partition_rows[partition] = 0
        fh, writer = writer_entry
        batch = pa.RecordBatch.from_pydict(
            {name: [core_row[name]] for name in BARS_SCHEMA_V1.names},
            schema=BARS_SCHEMA_V1,
        )
        writer.write_batch(batch)
        self._partition_rows[partition] += 1

    def _write_candidate(self, row: dict[str, Any], reason: str) -> None:
        if self._candidate_fh is None:
            self._candidate_dir.mkdir(parents=True, exist_ok=True)
            self.candidate_path = (
                self._candidate_dir / f"{self.batch_id}-{self.dataset_id}.jsonl.gz"
            )
            self._candidate_fh = gzip.open(self.candidate_path, "wt", encoding="utf-8")
        self._candidate_fh.write(
            json.dumps(
                {"candidate": row, "reason": reason}, ensure_ascii=False, default=str
            )
            + "\n"
        )
        self.counts.quarantined_rows += 1

    def _spool_path(self, partition: str) -> Path:
        safe = partition.replace("/", "__")
        return self._spool_dir / f"{safe}.arrow"

    def _close_writers(self) -> None:
        for fh, writer in self._writers.values():
            writer.close()
            fh.close()
        self._writers.clear()
        if self._candidate_fh is not None:
            self._candidate_fh.close()
            self._candidate_fh = None

    def _iter_partition_batches(self, partition: str) -> Iterator[pa.RecordBatch]:
        """Sorted (identity, bar_start) stream of one spooled partition."""
        path = self._spool_path(partition)
        with pa.memory_map(str(path), "rb") as source:
            table = ipc.open_stream(source).read_all()
        identity = [
            inst if inst is not None else ser
            for inst, ser in zip(
                table.column("instrument_id").to_pylist(),
                table.column("series_id").to_pylist(),
                strict=True,
            )
        ]
        order = sorted(
            range(table.num_rows),
            key=lambda i: (identity[i], table.column("bar_start")[i].as_py()),
        )
        sorted_table = table.take(pa.array(order))
        yield from sorted_table.to_batches(max_chunksize=65_536)

    # -- publish --------------------------------------------------------------

    def publish(self) -> ImportReceipt | None:
        """Publish all spooled partitions through the real core boundary.

        Returns ``None`` when nothing publishable was accepted (candidates are
        still preserved and counted). Conflicts surface on the returned
        receipt (state ``conflicted``); they are never resolved here.
        """
        self._close_writers()
        partitions = tuple(sorted(self._partition_rows))
        if not partitions:
            return None
        request = ImportRequest(
            asset=self.asset,
            spec=self.spec,
            adapter=self.adapter,
            config=self.config,
            partitions=partitions,
        )
        receipt = import_asset(
            self.store,
            request,
            self._iter_partition_batches,
            source_counts={
                "input_rows": self.counts.input_rows,
                "parse_failures": self.counts.parse_failures,
            },
        )
        return receipt

    def cleanup_spool(self) -> None:
        """Remove spool files after a terminal publish state (never before)."""
        for partition in self._partition_rows:
            self._spool_path(partition).unlink(missing_ok=True)

    def summary(self, receipt: ImportReceipt | None) -> dict[str, Any]:
        """Machine-readable import summary for CLI output and receipts."""
        payload: dict[str, Any] = {
            "batch_id": self.batch_id,
            "dataset_id": self.dataset_id,
            "adapter": self.adapter,
            "asset_id": self.asset.asset_id,
            "asset_sha256": self.asset.sha256,
            "transform_version": self.transform_version,
            "counts": {
                "input_rows": self.counts.input_rows,
                "accepted_rows": self.counts.accepted_rows,
                "candidate_rows": self.counts.quarantined_rows,
                "members_opened": self.counts.members_opened,
                "members_failed": self.counts.members_failed,
                "parse_failures": self.counts.parse_failures,
            },
            "failures": [{"member": m, "error": e} for m, e in self.failures],
            "candidate_file": (
                str(self.candidate_path) if self.candidate_path else None
            ),
        }
        if receipt is None:
            payload["publish"] = {"state": "no_publishable_rows"}
        else:
            payload["publish"] = {
                "state": receipt.state.value,
                "core_batch_id": receipt.batch_id,
                "idempotency_key": receipt.idempotency_key,
                "input_rows": receipt.input_rows,
                "accepted_rows": receipt.accepted_rows,
                "duplicate_rows": receipt.duplicate_rows,
                "quarantined_rows": receipt.quarantined_rows,
                "partitions": [
                    {
                        "partition": p.partition,
                        "revision_id": p.revision_id,
                        "rows": p.rows,
                        "base_revision": p.base_revision,
                    }
                    for p in receipt.partitions
                ],
                "conflicts": [
                    {
                        "conflict_id": c.conflict_id,
                        "partition": c.partition,
                        "key": c.key,
                        # Public real normalized bounds of the disputed
                        # record: the basis for explicit KnownGap allowances
                        # after quarantine, never a guessed 1ns point.
                        "gap_ns": (
                            [int(c.gap_ns[0]), int(c.gap_ns[1])]
                            if c.gap_ns is not None
                            else None
                        ),
                    }
                    for c in receipt.conflicts
                ],
            }
        return payload


def candidate_reason_counts(candidate_path: str | Path) -> dict[str, int]:
    """Aggregate reason codes of a preserved candidate file (inspection)."""
    counts: dict[str, int] = {}
    with gzip.open(candidate_path, "rt", encoding="utf-8") as fh:
        for line in fh:
            reason = json.loads(line).get("reason", "")
            code = reason.split(":", 1)[0]
            counts[code] = counts.get(code, 0) + 1
    return counts


def iter_candidates(candidate_path: str | Path) -> Iterator[dict[str, Any]]:
    """Stream preserved candidate rows with original labels and payload."""
    with gzip.open(candidate_path, "rt", encoding="utf-8") as fh:
        for line in fh:
            yield json.loads(line)


__all__ = ["StoreSink", "candidate_reason_counts", "iter_candidates"]
