"""Immutable revisions: staging, validation, CAS publish, conflicts, recovery.

Publishing protocol per batch:

1. Record the base head of every target partition.
2. Stream importer batches into staging; validate schema, non-finite values,
   identity, key uniqueness/order.
3. Dedup against the current head (same key/same values, audit timestamps and
   provenance excluded); same key/different values become conflicts with a
   sidecar; conflicted candidate rows are never published (no last-wins).
4. Write the COMPLETE new file set per partition as content-hashed Zstandard
   Parquet: fsync, atomic same-volume rename, then the revision manifest.
5. Mark the batch ``prepared`` with a durable receipt listing all revision
   manifests (crash-recovery anchor).
6. Per partition, ONE ``BEGIN IMMEDIATE`` transaction compares the base head,
   inserts the revision, and updates the head. A changed base raises
   HeadConflictError — the loser rebuilds; no writer ever overwrites another
   writer's head. No conversion happens while a catalog transaction is held.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq

from . import schemas
from .models import (
    AssetRef,
    BatchRecovery,
    BatchState,
    Completeness,
    ConflictRecord,
    ConflictResolution,
    HeadConflictError,
    ImportReceipt,
    ImportRequest,
    IntegrityError,
    PartitionReceipt,
    RecoveryReport,
    RevisionReceipt,
    SealReceipt,
    SealRequest,
    SessionRecoveryReport,
    StoreError,
    compute_dataset_id,
    default_idempotency_key,
)
from .objects import (
    ObjectRef,
    hash_file,
    verify_object,
    write_json_manifest,
    write_parquet_object,
)
from .store import Store

PROVENANCE_COLUMNS = ("asset_id", "batch_id", "transform_version")

_COMPLETENESS_VALUES = {c.value for c in Completeness}


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_batch(
    batch: pa.RecordBatch,
    schema: pa.Schema,
    dataset_id: str,
    record_kind: str,
    interval: str,
) -> None:
    """Hard publish-time validation. Raises StoreError on any violation.

    Time contract (time-contract disposition, 2026-09-16): canonical interval
    bounds (bar_start/bar_end) are always real and NOT NULL. ``trading_date``
    may be NULL only for minute-interval datasets whose source lacks calendar
    evidence, and then must carry an explicit field_quality note. Daily
    datasets always require a non-null trading_date; daily identity/dedup is
    (instrument-or-series, trading_date) — never a natural date.

    Tick identity (core fix03 F3): ticks carry an explicit non-empty
    ``session_id`` plus an importer-assigned ``seq`` (ingest sequence within
    the session). Both are required, never defaulted by the core, and form the
    dedup/conflict/order key together with the instrument-or-series identity;
    ``ts`` is preserved at full precision but is not the identity.
    """

    if not batch.schema.equals(schema, check_metadata=False):
        raise StoreError(
            f"record batch schema mismatch for {record_kind}: "
            f"expected {schema.names}, got {batch.schema.names}"
        )
    if batch.num_rows == 0:
        return

    ds_values = set(batch.column("dataset_id").to_pylist())
    if ds_values != {dataset_id}:
        raise StoreError(f"batch dataset_id values {ds_values} != {dataset_id}")

    instruments = batch.column("instrument_id").to_pylist()
    series = batch.column("series_id").to_pylist()
    for inst, ser in zip(instruments, series, strict=True):
        if (inst is None) == (ser is None):
            raise StoreError(
                "exactly one of instrument_id/series_id must be non-null per row"
            )

    bad = schemas.contains_nonfinite(batch, record_kind)
    if bad:
        raise StoreError(
            f"non-finite values in measure columns {bad}; importers must convert "
            "inf/nan to NULL plus a field_quality note"
        )

    completeness = set(batch.column("completeness").to_pylist())
    if not completeness <= _COMPLETENESS_VALUES:
        raise StoreError(f"invalid completeness values {completeness}")

    starts = batch.column("bar_start" if record_kind == "bars" else "ts").to_pylist()
    if record_kind == "bars":
        ends = batch.column("bar_end").to_pylist()
        for start, end in zip(starts, ends, strict=True):
            if end <= start:
                raise StoreError(f"bar_end {end} <= bar_start {start}")

    identities = [
        str(i if i is not None else s) for i, s in zip(instruments, series, strict=True)
    ]
    keys: list[tuple]
    if record_kind == "ticks":
        # Tick identity is the canonical event (session, ingest seq); the
        # sequence is importer-supplied and never derived from ``ts`` or from
        # the current query order. An empty session id would be a silently
        # invented session and is rejected.
        sessions = batch.column("session_id").to_pylist()
        for session in sessions:
            if session is None or not str(session):
                raise StoreError(
                    "tick session_id must be a non-empty string; the core never "
                    "invents a session identity"
                )
        seqs = batch.column("seq").to_pylist()
        keys = [
            (identity, str(session), _as_int(seq))
            for identity, session, seq in zip(
                identities, sessions, seqs, strict=True
            )
        ]
    else:
        keys = list(zip(identities, starts, strict=True))
    if keys != sorted(keys):
        raise StoreError(
            "record stream must be sorted by "
            "(identity, trading_date|bar_start) for bars or "
            "(identity, session_id, seq) for ticks"
        )
    if len(set(keys)) != len(keys):
        raise StoreError("duplicate keys within candidate stream")

    if record_kind == "bars":
        trading_dates = batch.column("trading_date").to_pylist()
        if interval == "1d":
            # Daily identity is (instrument-or-series, trading_date); a NULL
            # trading day can never be a canonical daily bar. Series identity
            # (e.g. continuous candidates) is valid without instrument_id.
            if any(td is None for td in trading_dates):
                raise StoreError(
                    "daily datasets require non-null trading_date; the daily "
                    "key is (identity, trading_date), never a natural date"
                )
        else:
            field_quality = batch.column("field_quality").to_pylist()
            for td, fq in zip(trading_dates, field_quality, strict=True):
                if td is None and fq is None:
                    raise StoreError(
                        "minute bar with NULL trading_date requires an explicit "
                        "field_quality note; the missing day stays visible "
                        "quality metadata and is never derived from bar_start"
                    )


def _row_value_hash(row: Mapping[str, object], record_kind: str, interval: str = "") -> str:
    """Hash of all non-provenance values; audit timestamps/provenance excluded.

    For daily bars the source label (bar_start/bar_end/source_label) is a
    labeling convention, not part of the day's identity: it is excluded so
    same-day rows with different labels and identical values dedup.
    """

    excluded = set(PROVENANCE_COLUMNS)
    if record_kind == "bars" and interval == "1d":
        excluded |= {"bar_start", "bar_end", "source_label"}
    payload = {k: v for k, v in row.items() if k not in excluded}
    text = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _batch_rows(batch: pa.RecordBatch) -> list[dict[str, object]]:
    columns = {name: batch.column(name).to_pylist() for name in batch.schema.names}
    return [
        {name: values[i] for name, values in columns.items()}
        for i in range(batch.num_rows)
    ]


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise StoreError(f"expected integer-compatible value, got {type(value).__name__}")
    return int(value)


def _row_key(row: Mapping[str, object], record_kind: str, interval: str = "") -> tuple:
    """Identity key. Never derived from unstable query order.

    Daily bars key on trading_date (the source trading day, never a natural
    date); minute bars key on the normalized start timestamp; ticks key on
    the canonical event identity (session_id, ingest seq) so distinct events
    at the same ``ts`` both survive.
    """

    identity = (
        row["instrument_id"] if row["instrument_id"] is not None else row["series_id"]
    )
    if record_kind == "bars" and interval == "1d":
        trading = row["trading_date"]
        if isinstance(trading, str):
            trading = datetime.strptime(trading, "%Y-%m-%d").date()
        if trading is None:
            raise StoreError("daily row without trading_date has no identity key")
        return (str(identity), trading)
    if record_kind == "ticks":
        return (str(identity), str(row["session_id"]), _as_int(row["seq"]))
    time_col = "bar_start" if record_kind == "bars" else "ts"
    return (str(identity), _as_int(row[time_col]))


def _render_key(key: tuple) -> str:
    """Human-readable conflict key; identity joined with each key component."""

    return "@".join(str(part) for part in key)


def _gap_bounds(row: Mapping[str, object], record_kind: str) -> tuple[int, int]:
    """The disputed record's real normalized bounds: [bar_start, bar_end) for
    bars, [ts, ts+1) for ticks. The same bounds back the sidecar evidence,
    the public receipt, and the reader's quarantine interval."""

    if record_kind == "bars":
        return _as_int(row["bar_start"]), _as_int(row["bar_end"])
    ts = _as_int(row["ts"])
    return ts, ts + 1


def _rows_to_batches(
    rows: list[dict[str, object]], schema: pa.Schema, max_rows: int = 65536
) -> list[pa.RecordBatch]:
    return [
        pa.RecordBatch.from_pydict(
            {name: [row[name] for row in rows[i : i + max_rows]] for name in schema.names},
            schema=schema,
        )
        for i in range(0, len(rows), max_rows)
    ]


def _read_revision_rows(
    store: Store, manifest: Mapping[str, object]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    files = manifest.get("files", [])
    assert isinstance(files, list)
    for entry in files:
        relpath = str(entry["path"])
        verify_object(store.root, relpath, str(entry["sha256"]))
        table = pq.read_table(str(store.root / relpath))
        for batch in table.to_batches():
            rows.extend(_batch_rows(batch))
    return rows


def _load_manifest(path: Path, expected_sha256: str | None = None) -> dict:
    if not path.is_file():
        raise IntegrityError(f"missing manifest {path}")
    if expected_sha256 is not None and hash_file(path) != expected_sha256:
        raise IntegrityError(f"tampered manifest {path}")
    result = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(result, dict)
    return result


def _head_manifest(store: Store, revision_id: str) -> dict:
    row = store.catalog.get_revision(revision_id)
    if row is None:
        raise IntegrityError(f"head revision {revision_id} missing from catalog")
    return _load_manifest(Path(str(row["manifest_path"])), str(row["manifest_sha256"]))


# ---------------------------------------------------------------------------
# Asset registration
# ---------------------------------------------------------------------------


def register_asset(store: Store, asset: AssetRef, verified: bool) -> None:
    """Register a source asset. ``verified=False`` is fast discovery (hash may
    be unverified); a formal import must pass ``verified=True`` after hashing
    the actual input."""

    if verified and asset.sha256 is None:
        raise StoreError("verified asset registration requires the input sha256")
    store.catalog.upsert_asset(
        asset_id=asset.asset_id,
        origin=asset.origin,
        format=asset.format,
        size=asset.size,
        sha256=asset.sha256,
        discovery="formal" if verified else "fast",
        registered_at=_utcnow(),
    )


# ---------------------------------------------------------------------------
# Publish internals
# ---------------------------------------------------------------------------


class _PartitionBuild:
    def __init__(self, partition: str, base_revision: str | None) -> None:
        self.partition = partition
        self.base_revision = base_revision
        self.new_rows: list[dict[str, object]] = []
        self.merged_rows: list[dict[str, object]] = []
        self.duplicates = 0
        self.conflicts: list[ConflictRecord] = []
        self.conflict_evidence: list[dict[str, object]] = []


def _build_partition(
    store: Store,
    dataset_id: str,
    record_kind: str,
    schema: pa.Schema,
    interval: str,
    partition: str,
    candidate: Iterator[pa.RecordBatch],
) -> _PartitionBuild:
    base = store.catalog.get_head(dataset_id, partition)
    build = _PartitionBuild(partition, base)

    existing_rows: list[dict[str, object]] = []
    existing_by_key: dict[tuple, dict[str, object]] = {}
    if base is not None:
        manifest = _head_manifest(store, base)
        existing_rows = _read_revision_rows(store, manifest)
        for row in existing_rows:
            existing_by_key[_row_key(row, record_kind, interval)] = row

    candidate_rows: list[dict[str, object]] = []
    for batch in candidate:
        validate_batch(batch, schema, dataset_id, record_kind, interval)
        candidate_rows.extend(_batch_rows(batch))

    # Sortedness/uniqueness are stream-wide invariants, not per-batch.
    keys = [_row_key(r, record_kind, interval) for r in candidate_rows]
    if keys != sorted(keys):
        raise StoreError(
            "record stream must be sorted by its identity key "
            "(daily: identity+trading_date; minute: identity+bar_start; "
            "ticks: identity+session_id+seq)"
        )
    if len(set(keys)) != len(keys):
        raise StoreError("duplicate keys within candidate stream")

    for row in candidate_rows:
        key = _row_key(row, record_kind, interval)
        prior = existing_by_key.get(key)
        if prior is None:
            build.new_rows.append(row)
            continue
        if _row_value_hash(prior, record_kind, interval) == _row_value_hash(row, record_kind, interval):
            build.duplicates += 1  # same key/same values: dedup
            continue
        conflict_id = _new_id("conflict")
        # Real normalized bounds of the disputed record: one source of truth
        # for the public receipt, the sidecar, and the reader's gap interval.
        gap = _gap_bounds(prior, record_kind)
        build.conflicts.append(
            ConflictRecord(
                conflict_id=conflict_id,
                dataset_id=dataset_id,
                partition=partition,
                key=_render_key(key),
                existing_revision=str(base),
                existing_evidence=json.dumps(prior, sort_keys=True, default=str),
                candidate_evidence=json.dumps(row, sort_keys=True, default=str),
                resolution=None,
                gap_ns=gap,
            )
        )
        build.conflict_evidence.append(
            {
                "conflict_id": conflict_id,
                "key": list(key),
                # The disputed record's real normalized bounds, so a later
                # quarantine is a queryable gap interval (never derived from
                # a natural date).
                "gap_ns": list(gap),
                "existing": dict(prior),
                "candidate": dict(row),
            }
        )

    # Complete active file set = ALL existing rows (the existing side of a
    # conflict is retained) plus unaffected new rows. Conflicted candidate
    # rows stay in the sidecar only: no last-wins, no silent removal.
    merged = list(existing_rows)
    merged.extend(build.new_rows)
    merged.sort(key=lambda r: _row_key(r, record_kind, interval))
    build.merged_rows = merged
    return build


def _write_revision(
    store: Store,
    dataset_id: str,
    record_kind: str,
    schema: pa.Schema,
    build: _PartitionBuild,
    batch_id: str,
    extra: Mapping[str, object] | None = None,
) -> RevisionReceipt:
    revision_id = _new_id("rev")
    objects: list[ObjectRef] = []
    if build.merged_rows:
        batches = _rows_to_batches(build.merged_rows, schema)
        objects.append(
            write_parquet_object(
                store.path.staging, store.path.objects, batches, schema, store.root
            )
        )

    time_col = "bar_start" if record_kind == "bars" else "ts"
    starts = [_as_int(r[time_col]) for r in build.merged_rows]
    manifest = {
        "revision_id": revision_id,
        "dataset_id": dataset_id,
        "partition": build.partition,
        "parent_revision": build.base_revision,
        "batch_id": batch_id,
        "created_at": _utcnow(),
        "record_kind": record_kind,
        "files": [
            {"path": o.relpath, "sha256": o.sha256, "rows": o.rows, "size": o.size}
            for o in objects
        ],
        "rows": len(build.merged_rows),
        "coverage": {
            "start_ns": min(starts) if starts else None,
            "end_ns": max(starts) if starts else None,
        },
        "conflicts": [c.conflict_id for c in build.conflicts],
        **dict(extra or {}),
    }
    manifest_path = store.path.revision_manifests / f"{revision_id}.json"
    write_json_manifest(store.path.staging, manifest_path, manifest)
    return RevisionReceipt(
        dataset_id=dataset_id,
        partition=build.partition,
        revision_id=revision_id,
        parent_revision=build.base_revision,
        files=tuple(o.relpath for o in objects),
        rows=len(build.merged_rows),
        batch_id=batch_id,
    )


def _commit_partition_cas(store: Store, receipt: RevisionReceipt, now: str) -> None:
    """Single BEGIN IMMEDIATE transaction: verify base, insert revision, move
    head. Raises HeadConflictError on a changed base."""

    manifest_path = store.path.revision_manifests / f"{receipt.revision_id}.json"
    with store.catalog.transaction(immediate=True):
        current = store.catalog.get_head(receipt.dataset_id, receipt.partition)
        if current != receipt.parent_revision:
            raise HeadConflictError(
                f"partition {receipt.dataset_id}/{receipt.partition} head changed "
                f"during publish: base {receipt.parent_revision} -> {current}; "
                "rebuild from the new head"
            )
        store.catalog.insert_revision(
            receipt.revision_id,
            receipt.dataset_id,
            receipt.partition,
            receipt.parent_revision,
            str(manifest_path),
            hash_file(manifest_path),
            receipt.rows,
            receipt.batch_id,
            now,
        )
        store.catalog.set_head(
            receipt.dataset_id, receipt.partition, receipt.revision_id, now
        )


def _write_conflict_sidecars(
    store: Store, dataset_id: str, build: _PartitionBuild
) -> None:
    conflicts_dir = store.path.revision_manifests / "conflicts"
    for evidence in build.conflict_evidence:
        conflict_id = str(evidence["conflict_id"])
        path = conflicts_dir / f"{conflict_id}.json"
        write_json_manifest(store.path.staging, path, evidence)
        store.catalog.insert_quality_issue(
            issue_id=conflict_id,
            dataset_id=dataset_id,
            partition=build.partition,
            code="same_key_different_values",
            evidence={
                "sidecar": str(path),
                "key": evidence["key"],
                "gap_ns": evidence["gap_ns"],
            },
            created_at=_utcnow(),
        )


# ---------------------------------------------------------------------------
# Receipt (de)serialization — durable anchor for replay and recovery
# ---------------------------------------------------------------------------


def _request_payload(request: ImportRequest) -> dict:
    return {
        "asset": {
            "asset_id": request.asset.asset_id,
            "origin": request.asset.origin,
            "format": request.asset.format,
            "size": request.asset.size,
            "sha256": request.asset.sha256,
        },
        "spec_canonical": request.spec.canonical(),
        "adapter": request.adapter,
        "config": dict(sorted(request.config.items())),
        "partitions": list(request.partitions),
        "idempotency_key": request.idempotency_key,
    }


def _request_from_payload(payload: Mapping[str, object]) -> ImportRequest:
    from .models import SemanticSpec as _Spec  # local alias for clarity

    spec_raw = json.loads(str(payload["spec_canonical"]))
    asset_raw = payload["asset"]
    assert isinstance(asset_raw, Mapping)
    from .models import (
        Adjustment,
        AssetClass,
        Interval,
        OriginMethod,
        RecordKind,
        TimeLabel,
    )

    spec = _Spec(
        source_id=str(spec_raw["source_id"]),
        asset_class=AssetClass(spec_raw["asset_class"]),
        record_kind=RecordKind(spec_raw["record_kind"]),
        interval=Interval(spec_raw["interval"]),
        adjustment=Adjustment(spec_raw["adjustment"]),
        adjustment_version=str(spec_raw["adjustment_version"]),
        series_kind=str(spec_raw["series_kind"]),
        rule_version=str(spec_raw["rule_version"]),
        timezone=str(spec_raw["timezone"]),
        source_time_label=TimeLabel(spec_raw["source_time_label"]),
        volume_unit=str(spec_raw["volume_unit"]),
        turnover_unit=str(spec_raw["turnover_unit"]),
        origin_method=OriginMethod(spec_raw["origin_method"]),
        schema_version=int(spec_raw["schema_version"]),
    )
    asset = AssetRef(
        asset_id=str(asset_raw["asset_id"]),
        origin=str(asset_raw["origin"]),
        format=str(asset_raw["format"]),
        size=_as_int(asset_raw["size"]),
        sha256=None if asset_raw["sha256"] is None else str(asset_raw["sha256"]),
    )
    return ImportRequest(
        asset=asset,
        spec=spec,
        adapter=str(payload["adapter"]),
        config={
            str(k): str(v)
            for k, v in cast("Mapping[str, object]", payload["config"]).items()
        },
        partitions=tuple(
            str(p) for p in cast("Iterable[object]", payload["partitions"])
        ),
        idempotency_key=(
            None if payload["idempotency_key"] is None else str(payload["idempotency_key"])
        ),
    )


def _receipt_payload(receipt: ImportReceipt) -> dict:
    return {
        "batch_id": receipt.batch_id,
        "dataset_id": receipt.dataset_id,
        "state": receipt.state.value,
        "partitions": [
            {
                "partition": p.partition,
                "revision_id": p.revision_id,
                "files": list(p.files),
                "rows": p.rows,
                "base_revision": p.base_revision,
            }
            for p in receipt.partitions
        ],
        "input_rows": receipt.input_rows,
        "accepted_rows": receipt.accepted_rows,
        "duplicate_rows": receipt.duplicate_rows,
        "quarantined_rows": receipt.quarantined_rows,
        "parse_failures": receipt.parse_failures,
        "conflicts": [
            {
                "conflict_id": c.conflict_id,
                "partition": c.partition,
                "key": c.key,
                "gap_ns": list(c.gap_ns) if c.gap_ns is not None else None,
            }
            for c in receipt.conflicts
        ],
        "idempotency_key": receipt.idempotency_key,
        "request": _request_payload(receipt.request),
    }


def _parse_gap_ns(payload: Mapping[str, object]) -> tuple[int, int] | None:
    gap = payload.get("gap_ns")
    if isinstance(gap, list) and len(gap) == 2:
        return int(gap[0]), int(gap[1])
    return None


def _receipt_from_payload(payload: Mapping[str, object], detail: str = "") -> ImportReceipt:
    conflicts = tuple(
        ConflictRecord(
            conflict_id=str(c["conflict_id"]),
            dataset_id=str(payload["dataset_id"]),
            partition=str(c["partition"]),
            key=str(c["key"]),
            existing_revision="",
            existing_evidence="",
            candidate_evidence="",
            resolution=None,
            gap_ns=_parse_gap_ns(c),
        )
        for c in cast("Iterable[Mapping[str, object]]", payload["conflicts"])
    )
    return ImportReceipt(
        batch_id=str(payload["batch_id"]),
        dataset_id=str(payload["dataset_id"]),
        state=BatchState(str(payload["state"])),
        partitions=tuple(
            PartitionReceipt(
                partition=str(p["partition"]),
                revision_id=str(p["revision_id"]),
                files=tuple(str(f) for f in cast("Iterable[object]", p["files"])),
                rows=_as_int(p["rows"]),
                base_revision=(
                    None if p["base_revision"] is None else str(p["base_revision"])
                ),
            )
            for p in cast("Iterable[Mapping[str, object]]", payload["partitions"])
        ),
        input_rows=_as_int(payload["input_rows"]),
        accepted_rows=_as_int(payload["accepted_rows"]),
        duplicate_rows=_as_int(payload["duplicate_rows"]),
        quarantined_rows=_as_int(payload["quarantined_rows"]),
        parse_failures=_as_int(payload["parse_failures"]),
        conflicts=conflicts,
        idempotency_key=str(payload["idempotency_key"]),
        request=_request_from_payload(cast("Mapping[str, object]", payload["request"])),
        detail=detail,
    )


def _receipt_from_row(row: sqlite3.Row, detail: str) -> ImportReceipt:
    return _receipt_from_payload(json.loads(str(row["receipt_json"])), detail)


# ---------------------------------------------------------------------------
# Public import entry point
# ---------------------------------------------------------------------------


def import_asset(
    store: Store,
    request: ImportRequest,
    rows: Callable[[str], Iterator[pa.RecordBatch]],
    source_counts: Mapping[str, int] | None = None,
) -> ImportReceipt:
    """Drive an importer's streaming batch iterator to immutable publication.

    Idempotent: a repeated request (same idempotency key) returns the prior
    receipt without re-publishing. A prior ``running``/``failed`` batch is
    superseded and the import is retried from scratch.
    """

    dataset_id = compute_dataset_id(request.spec)
    record_kind = request.spec.record_kind.value
    schema = schemas.schema_for(record_kind)
    key = request.idempotency_key or default_idempotency_key(request)

    register_asset(store, request.asset, verified=True)
    store.catalog.ensure_dataset(
        dataset_id, request.spec.canonical(), request.spec.schema_version, _utcnow()
    )

    prior = store.catalog.find_batch_by_key(key)
    if prior is not None and str(prior["state"]) == BatchState.PUBLISHED.value:
        return _receipt_from_row(
            prior, "idempotent replay: prior receipt returned, nothing re-published"
        )
    if prior is not None and str(prior["state"]) == BatchState.CONFLICTED.value:
        return _receipt_from_row(
            prior, "idempotent replay: prior conflicted receipt returned"
        )
    if prior is not None and str(prior["state"]) == BatchState.PREPARED.value:
        report = recover(store, str(prior["batch_id"]))
        for item in report.batches:
            if item.receipt is not None:
                return item.receipt
        raise StoreError(
            f"recovery of prepared batch {prior['batch_id']} failed; "
            "fix the reported error before retrying"
        )
    if prior is not None:
        store.catalog.set_batch_state(
            str(prior["batch_id"]),
            BatchState.FAILED.value,
            _utcnow(),
            error="superseded by retry",
        )

    batch_id = _new_id("batch")
    store.catalog.begin_batch(
        batch_id, key, request.asset.asset_id, dataset_id,
        request.adapter, request.config, _utcnow(),
    )

    builds: list[_PartitionBuild] = []
    revision_receipts: list[RevisionReceipt] = []
    input_rows = 0
    duplicates = 0
    try:
        for partition in request.partitions:
            build = _build_partition(
                store, dataset_id, record_kind, schema,
                request.spec.interval.value, partition, rows(partition),
            )
            input_rows += len(build.new_rows) + build.duplicates + len(build.conflicts)
            duplicates += build.duplicates
            if build.conflicts:
                _write_conflict_sidecars(store, dataset_id, build)
            builds.append(build)
            revision_receipts.append(
                _write_revision(store, dataset_id, record_kind, schema, build, batch_id)
            )
    except BaseException as exc:
        store.catalog.set_batch_state(
            batch_id, BatchState.FAILED.value, _utcnow(),
            error=f"{type(exc).__name__}: {exc}",
        )
        raise

    # Durable crash anchor: files + manifests are on disk; record them before
    # any catalog commit so recover() can finish or fail loudly.
    anchor = {
        "revisions": [
            {
                "revision_id": r.revision_id,
                "dataset_id": r.dataset_id,
                "partition": r.partition,
                "parent_revision": r.parent_revision,
                "rows": r.rows,
                "new_rows": len(build.new_rows),
                "duplicates": build.duplicates,
                "conflicts": [c.conflict_id for c in build.conflicts],
            }
            for r, build in zip(revision_receipts, builds, strict=True)
        ],
        "request": _request_payload(request),
    }
    store.catalog.set_batch_state(
        batch_id, BatchState.PREPARED.value, _utcnow(),
        receipt_json=json.dumps(anchor, sort_keys=True),
    )

    all_conflicts: list[ConflictRecord] = []
    partition_receipts: list[PartitionReceipt] = []
    try:
        for build, rev in zip(builds, revision_receipts, strict=True):
            _commit_partition_cas(store, rev, _utcnow())
            all_conflicts.extend(build.conflicts)
            partition_receipts.append(
                PartitionReceipt(
                    partition=build.partition,
                    revision_id=rev.revision_id,
                    files=rev.files,
                    rows=len(build.new_rows),
                    base_revision=build.base_revision,
                )
            )
    except BaseException as exc:
        store.catalog.set_batch_state(
            batch_id, BatchState.FAILED.value, _utcnow(),
            error=f"{type(exc).__name__}: {exc}",
        )
        raise

    counts = dict(source_counts or {})
    final_state = BatchState.CONFLICTED if all_conflicts else BatchState.PUBLISHED
    receipt = ImportReceipt(
        batch_id=batch_id,
        dataset_id=dataset_id,
        state=final_state,
        partitions=tuple(partition_receipts),
        input_rows=int(counts.get("input_rows", input_rows)),
        accepted_rows=sum(p.rows for p in partition_receipts),
        duplicate_rows=duplicates,
        quarantined_rows=len(all_conflicts),
        parse_failures=int(counts.get("parse_failures", 0)),
        conflicts=tuple(all_conflicts),
        idempotency_key=key,
        request=request,
    )
    store.catalog.set_batch_counts(
        batch_id, receipt.input_rows, receipt.accepted_rows,
        receipt.duplicate_rows, receipt.quarantined_rows, receipt.parse_failures,
    )
    store.catalog.set_batch_state(
        batch_id, final_state.value, _utcnow(),
        receipt_json=json.dumps(_receipt_payload(receipt), sort_keys=True),
    )
    return receipt


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------


def resolve_conflict(
    store: Store,
    dataset_id: str,
    partition: str,
    conflict_id: str,
    resolution: ConflictResolution,
    reason: str,
) -> RevisionReceipt:
    """Resolve a same-key conflict by creating a NEW revision.

    Old revisions and snapshots are never altered. QUARANTINE drops both
    sides, leaving a visible gap; nothing is zero- or forward-filled.
    """

    if not reason:
        raise StoreError("conflict resolution requires a recorded reason")
    issue = store.catalog.query_one(
        "SELECT * FROM quality_issues WHERE issue_id=? AND scope_dataset_id=?"
        " AND scope_partition=?",
        (conflict_id, dataset_id, partition),
    )
    if issue is None:
        raise StoreError(f"unknown conflict {conflict_id}")
    if issue["resolution"] is not None:
        raise StoreError(
            f"conflict {conflict_id} already resolved as {issue['resolution']}"
        )

    sidecar = _load_manifest(Path(str(json.loads(str(issue["evidence_json"]))["sidecar"])))
    base = store.catalog.get_head(dataset_id, partition)
    if base is None:
        raise StoreError(f"partition {dataset_id}/{partition} has no head")

    dataset = store.catalog.get_dataset(dataset_id)
    if dataset is None:
        raise StoreError(f"unknown dataset {dataset_id}")
    semantic = json.loads(str(dataset["semantic_json"]))
    record_kind = str(semantic["record_kind"])
    interval = str(semantic["interval"])
    schema = schemas.schema_for(record_kind)

    manifest = _head_manifest(store, base)
    existing_rows = _read_revision_rows(store, manifest)
    raw_key = list(sidecar["key"])
    if record_kind == "bars" and interval == "1d":
        if isinstance(raw_key[1], str):
            raw_key[1] = datetime.strptime(str(raw_key[1]), "%Y-%m-%d").date()
    elif record_kind == "ticks":
        raw_key[1] = str(raw_key[1])
        raw_key[2] = _as_int(raw_key[2])
    elif raw_key[1] is not None and not isinstance(raw_key[1], int):
        raw_key[1] = _as_int(raw_key[1])
    key = tuple(raw_key)
    candidate_row = _decode_sidecar_row(sidecar["candidate"])

    merged = []
    for row in existing_rows:
        if _row_key(row, record_kind, interval) == key:
            if resolution is ConflictResolution.EXISTING:
                merged.append(row)
            elif resolution is ConflictResolution.CANDIDATE:
                merged.append(candidate_row)
            # QUARANTINE drops both sides: visible gap, no fill.
            continue
        merged.append(row)
    merged.sort(key=lambda r: _row_key(r, record_kind, interval))

    build = _PartitionBuild(partition, base)
    build.merged_rows = merged
    # Resolution decisions are recorded as their own batch, attributed to the
    # asset whose import surfaced the conflict.
    base_rev = store.catalog.get_revision(base)
    origin_batch = store.catalog.get_batch(str(base_rev["batch_id"])) if base_rev else None
    asset_id = str(origin_batch["asset_id"]) if origin_batch is not None else "resolution"
    batch_id = _new_id("resolve")
    store.catalog.begin_batch(
        batch_id, f"resolve:{conflict_id}", asset_id, dataset_id,
        "core/resolve_conflict", {"conflict_id": conflict_id, "resolution": resolution.value},
        _utcnow(),
    )
    store.catalog.set_batch_state(batch_id, BatchState.PUBLISHED.value, _utcnow())
    receipt = _write_revision(
        store, dataset_id, record_kind, schema, build, batch_id,
        extra={
            "resolution": {
                "conflict_id": conflict_id,
                "resolution": resolution.value,
                "reason": reason,
            }
        },
    )
    now = _utcnow()
    manifest_path = store.path.revision_manifests / f"{receipt.revision_id}.json"
    with store.catalog.transaction(immediate=True):
        current = store.catalog.get_head(dataset_id, partition)
        if current != base:
            raise HeadConflictError(
                f"partition {dataset_id}/{partition} head changed during resolve"
            )
        store.catalog.insert_revision(
            receipt.revision_id, dataset_id, partition, base,
            str(manifest_path), hash_file(manifest_path), receipt.rows, batch_id, now,
        )
        store.catalog.set_head(dataset_id, partition, receipt.revision_id, now)
        store.catalog.resolve_quality_issue_in_tx(
            conflict_id, resolution.value, receipt.revision_id, now
        )
    return receipt


def _decode_sidecar_row(payload: Mapping[str, object]) -> dict[str, object]:
    row = dict(payload)
    for time_col in ("bar_start", "bar_end", "ts"):
        if row.get(time_col) is not None:
            row[time_col] = _as_int(row[time_col])
    if isinstance(row.get("trading_date"), str):
        row["trading_date"] = datetime.strptime(
            str(row["trading_date"]), "%Y-%m-%d"
        ).date()
    return row


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


def recover(store: Store, batch_id: str | None = None) -> RecoveryReport:
    """Recover interrupted imports.

    - ``prepared`` batches: validate published files (existence + sha256 +
      manifest), re-check base heads, then complete the atomic publish or fail
      loudly. Missing/tampered objects never fall back.
    - ``failed`` batches: a partially published multi-partition batch keeps
      its durable prepared anchor; the sweep resumes it through the same
      CAS-verified path (already-committed partitions are skipped, changed
      heads raise instead of clobbering). A ``failed`` batch with no usable
      anchor is reported loudly with retry guidance — it is never silently
      invisible and never reported as published.
    - ``published`` batches return their prior receipt (idempotent).
    - ``running`` batches were interrupted before the durable anchor; they are
      marked failed and must be retried by the importer.
    - Orphan files are reported, never automatically deleted.
    """

    results: list[BatchRecovery] = []
    if batch_id is not None:
        row = store.catalog.get_batch(batch_id)
        candidates: list[sqlite3.Row] = [] if row is None else [row]
    else:
        candidates = store.catalog.query_all(
            "SELECT * FROM batches WHERE state IN"
            " ('prepared','published','running','failed')"
            " ORDER BY created_at"
        )

    for row in candidates:
        state = BatchState(str(row["state"]))
        bid = str(row["batch_id"])
        if state is BatchState.PUBLISHED:
            receipt = (
                _receipt_from_row(row, "recover: prior receipt returned")
                if row["receipt_json"]
                else None
            )
            results.append(
                BatchRecovery(bid, state, "returned_prior_receipt", receipt, None)
            )
            continue
        if state is BatchState.RUNNING:
            store.catalog.set_batch_state(
                bid, BatchState.FAILED.value, _utcnow(),
                error="interrupted before prepare; superseded",
            )
            results.append(
                BatchRecovery(bid, state, "failed", None, "interrupted running batch")
            )
            continue
        if state is BatchState.FAILED:
            # A FAILED batch may hold a durable prepared anchor from a
            # partially published multi-partition import; resume it when the
            # anchor allows, otherwise report loud per-batch retry guidance.
            if _prepared_anchor(row) is not None:
                results.append(_recover_prepared(store, row))
            else:
                results.append(
                    BatchRecovery(
                        bid,
                        state,
                        "failed",
                        None,
                        f"failed batch {bid} has no durable prepared anchor; "
                        f"retry the import with its idempotency_key "
                        f"{row['idempotency_key']!r} to rebuild from scratch",
                    )
                )
            continue
        results.append(_recover_prepared(store, row))

    orphans = _find_orphan_files(store)
    return RecoveryReport(
        root=store.root, batches=tuple(results), orphan_files=tuple(orphans)
    )


def _prepared_anchor(row: sqlite3.Row) -> dict | None:
    """The durable prepared anchor of a batch row, or None if absent/invalid."""

    if not row["receipt_json"]:
        return None
    try:
        payload = json.loads(str(row["receipt_json"]))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    entries = payload.get("revisions")
    if not isinstance(entries, list) or not entries:
        return None
    return payload


def _recover_prepared(store: Store, row: sqlite3.Row) -> BatchRecovery:
    bid = str(row["batch_id"])
    prior_state = BatchState(str(row["state"]))
    try:
        if not row["receipt_json"]:
            raise IntegrityError(f"prepared batch {bid} has no durable anchor")
        anchor = json.loads(str(row["receipt_json"]))
        entries = anchor.get("revisions")
        if not isinstance(entries, list) or not entries:
            raise IntegrityError(f"prepared batch {bid} anchor lists no revisions")

        for entry in entries:
            revision_id = str(entry["revision_id"])
            if store.catalog.get_revision(revision_id) is not None:
                continue  # this partition's commit already happened
            manifest_path = store.path.revision_manifests / f"{revision_id}.json"
            manifest = _load_manifest(manifest_path)
            if manifest.get("batch_id") != bid:
                raise IntegrityError(
                    f"manifest {manifest_path} batch mismatch for prepared {bid}"
                )
            for file_entry in manifest["files"]:
                verify_object(store.root, file_entry["path"], file_entry["sha256"])
            receipt = RevisionReceipt(
                dataset_id=str(entry["dataset_id"]),
                partition=str(entry["partition"]),
                revision_id=revision_id,
                parent_revision=entry["parent_revision"],
                files=tuple(str(f["path"]) for f in manifest["files"]),
                rows=int(manifest["rows"]),
                batch_id=bid,
            )
            _commit_partition_cas(store, receipt, _utcnow())

        has_conflicts = any(entry.get("conflicts") for entry in entries)
        final = BatchState.CONFLICTED if has_conflicts else BatchState.PUBLISHED

        # Rebuild and persist the full receipt so recovery and later replays
        # return the same durable result as an uninterrupted import.
        partition_payloads = []
        conflict_payloads = []
        for entry in entries:
            manifest = _load_manifest(
                store.path.revision_manifests / f"{entry['revision_id']}.json"
            )
            partition_payloads.append(
                {
                    "partition": entry["partition"],
                    "revision_id": entry["revision_id"],
                    "files": [str(f["path"]) for f in manifest["files"]],
                    "rows": int(entry.get("new_rows", manifest["rows"])),
                    "base_revision": entry["parent_revision"],
                }
            )
            for conflict_id in entry.get("conflicts", []):
                issue = store.catalog.query_one(
                    "SELECT * FROM quality_issues WHERE issue_id=?", (conflict_id,)
                )
                evidence = (
                    json.loads(str(issue["evidence_json"])) if issue is not None else {}
                )
                conflict_payloads.append(
                    {
                        "conflict_id": conflict_id,
                        "partition": entry["partition"],
                        "key": evidence.get("key", ""),
                        "gap_ns": evidence.get("gap_ns"),
                    }
                )
        new_rows = sum(p["rows"] for p in partition_payloads)
        duplicates = sum(int(e.get("duplicates", 0)) for e in entries)
        receipt_payload = {
            "batch_id": bid,
            "dataset_id": str(entries[0]["dataset_id"]),
            "state": final.value,
            "partitions": partition_payloads,
            "input_rows": new_rows + duplicates + len(conflict_payloads),
            "accepted_rows": new_rows,
            "duplicate_rows": duplicates,
            "quarantined_rows": len(conflict_payloads),
            "parse_failures": 0,
            "conflicts": conflict_payloads,
            "idempotency_key": str(row["idempotency_key"]),
            "request": anchor["request"],
        }
        store.catalog.set_batch_state(
            bid, final.value, _utcnow(),
            receipt_json=json.dumps(receipt_payload, sort_keys=True),
        )
        return BatchRecovery(
            bid, prior_state, "republished",
            _receipt_from_payload(receipt_payload, "recover: republished after interruption"),
            None,
        )
    except BaseException as exc:
        store.catalog.set_batch_state(
            bid, BatchState.FAILED.value, _utcnow(),
            error=f"recovery failed: {type(exc).__name__}: {exc}",
        )
        return BatchRecovery(
            bid, prior_state, "failed", None,
            f"{type(exc).__name__}: {exc}; the batch keeps its durable anchor — "
            f"fix the reported error and re-run recover, or retry the import "
            f"with idempotency_key {row['idempotency_key']!r}",
        )


def _find_orphan_files(store: Store) -> list[Path]:
    """Staging leftovers and objects not referenced by any revision manifest.

    Reported only — never automatically deleted.
    """

    orphans: list[Path] = []
    staging = store.path.staging
    if staging.is_dir():
        orphans.extend(p for p in staging.rglob("*") if p.is_file())

    referenced: set[str] = set()
    for path in store.path.revision_manifests.glob("rev-*.json"):
        try:
            manifest = _load_manifest(path)
        except (IntegrityError, json.JSONDecodeError):
            continue
        for entry in manifest.get("files", []):
            referenced.add(str(entry["path"]))

    objects = store.path.objects
    if objects.is_dir():
        for path in objects.rglob("*.parquet"):
            relpath = path.relative_to(store.root).as_posix()
            if relpath not in referenced:
                orphans.append(path)
    return orphans


# ---------------------------------------------------------------------------
# Recording sessions (WP08/WP09) — real implementations live in the journal,
# recovery, and sealing modules; these are the canonical public entry points.
# ---------------------------------------------------------------------------


def recover_session(
    store: Store,
    session_id: str,
    *,
    create_successor: bool = True,
    successor_source_spec: str | None = None,
    successor_calendar_spec: str | None = None,
) -> SessionRecoveryReport:
    """Recover an unclosed recording session (delegated implementation).

    Replays committed journal sequences of an unclosed session, durably marks
    it UNCLEAN_END while still holding the exclusive OS lock, and links an
    optional successor session. This canonical public entry point forwards
    every documented typed option to the real implementation in
    ``research_store.session_recovery`` (recording02I: ``create_successor``
    and the successor spec overrides were previously dropped here).
    """

    from .session_recovery import recover_session as _recover_session

    return _recover_session(
        store,
        session_id,
        create_successor=create_successor,
        successor_source_spec=successor_source_spec,
        successor_calendar_spec=successor_calendar_spec,
    )


def seal(store: Store, request: SealRequest) -> SealReceipt:
    """Idempotent seal of a committed session watermark range (delegated).

    Publishes verbatim ticks and aggregated minute bars through the immutable
    canonical publish API. See ``research_store.sealing``.
    """

    from .sealing import seal as _seal

    return _seal(store, request)
