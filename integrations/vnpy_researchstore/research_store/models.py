"""Core data model: semantic identity, receipts, conflicts, and error types.

Pure storage core — this module (and the whole ``research_store`` package) must
never import ``vnpy`` or any provider SDK, and must never touch ``~/.vntrader``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class StoreError(Exception):
    """Base class for all research_store errors."""


class StoreNotFoundError(StoreError):
    """Root is not an identified research store."""


class StoreExistsError(StoreError):
    """Refusing to initialize a non-empty, unidentified directory."""


class CatalogError(StoreError):
    """Catalog schema/state violation."""


class HeadConflictError(StoreError):
    """Partition head changed between base recording and publish (CAS lost)."""


class ConflictError(StoreError):
    """Same-key different-values conflict detected during publish."""


class UnresolvedConflictError(StoreError):
    """Freeze requested over unresolved conflicts with default policy."""


class IntegrityError(StoreError):
    """Missing or tampered immutable object/manifest."""


class CoverageGapError(StoreError):
    """Query intersects a recorded gap the snapshot did not explicitly allow."""


class UnknownDatasetError(StoreError):
    """Dataset id is not part of the snapshot/store selection."""


class UnavailableFieldError(StoreError):
    """Required field is absent from the schema or not produced by the dataset."""


class MissingFieldDataError(StoreError):
    """NULLs present in caller-required fields."""


class ReadOnlyError(StoreError):
    """Write attempted against a read-only view."""


class UnsupportedCapabilityError(StoreError):
    """Capability not provided by this version (distinct from PENDING stubs)."""


class PendingCapabilityError(StoreError):
    """Typed stub for a later work package; never counted as complete."""


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class AssetClass(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"
    FUTURES = "futures"
    OPTION = "option"
    CONVERTIBLE = "convertible"
    OTHER = "other"


class RecordKind(str, Enum):
    BARS = "bars"
    TICKS = "ticks"
    CORPORATE_ACTIONS = "corporate_actions"
    REFERENCE = "reference"


class Interval(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    D1 = "1d"


class Adjustment(str, Enum):
    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"
    UNKNOWN = "unknown"


class TimeLabel(str, Enum):
    START = "start"
    END = "end"
    UNKNOWN = "unknown"


class OriginMethod(str, Enum):
    SOURCE = "source"
    DERIVED = "derived"
    REPAIRED = "repaired"


class Completeness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class BatchState(str, Enum):
    RUNNING = "running"
    PREPARED = "prepared"
    PUBLISHED = "published"
    FAILED = "failed"
    CONFLICTED = "conflicted"


class ConflictResolution(str, Enum):
    EXISTING = "existing"
    CANDIDATE = "candidate"
    QUARANTINE = "quarantine"


class ConflictPolicy(str, Enum):
    ERROR = "error"


# ---------------------------------------------------------------------------
# Semantic identity
# ---------------------------------------------------------------------------


def _canonical_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class SemanticSpec:
    """Full semantic identity of a dataset.

    Contents determine the dataset id; imports never invent new semantic ids
    from import dates. Sources, adjustments, and native-vs-derived data never
    silently merge because every discriminating field participates in the hash.
    """

    source_id: str
    asset_class: AssetClass
    record_kind: RecordKind
    interval: Interval
    adjustment: Adjustment
    adjustment_version: str
    series_kind: str
    rule_version: str
    timezone: str
    source_time_label: TimeLabel
    volume_unit: str
    turnover_unit: str
    origin_method: OriginMethod
    schema_version: int

    def canonical(self) -> str:
        payload = {
            "source_id": self.source_id,
            "asset_class": self.asset_class.value,
            "record_kind": self.record_kind.value,
            "interval": self.interval.value,
            "adjustment": self.adjustment.value,
            "adjustment_version": self.adjustment_version,
            "series_kind": self.series_kind,
            "rule_version": self.rule_version,
            "timezone": self.timezone,
            "source_time_label": self.source_time_label.value,
            "volume_unit": self.volume_unit,
            "turnover_unit": self.turnover_unit,
            "origin_method": self.origin_method.value,
            "schema_version": self.schema_version,
        }
        return _canonical_json(payload)


def compute_dataset_id(spec: SemanticSpec) -> str:
    digest = hashlib.sha256(spec.canonical().encode("utf-8")).hexdigest()
    return f"ds-{digest[:32]}"


# ---------------------------------------------------------------------------
# Assets and import requests / receipts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssetRef:
    """Registered source asset.

    Fast discovery may register ``sha256=None`` (unverified); a formal import
    must hash the actual input and record it on the batch.
    """

    asset_id: str
    origin: str
    format: str
    size: int
    sha256: str | None


@dataclass(frozen=True)
class ImportRequest:
    asset: AssetRef
    spec: SemanticSpec
    adapter: str
    config: Mapping[str, str]
    partitions: tuple[str, ...]
    idempotency_key: str | None = None


def default_idempotency_key(request: ImportRequest) -> str:
    """Content-addressed replay key.

    Combines the asset content hash, member/table/range from config, dataset
    identity, and adapter/config versions. Audit timestamps are excluded so a
    repeated import of unchanged input replays to the same key.
    """

    if request.asset.sha256 is None:
        raise StoreError(
            "default idempotency key requires a verified asset content hash; "
            "hash the actual input before import"
        )
    payload = {
        "asset_sha256": request.asset.sha256,
        "asset_origin": request.asset.origin,
        "dataset_id": compute_dataset_id(request.spec),
        "adapter": request.adapter,
        "config": dict(sorted(request.config.items())),
        "partitions": sorted(request.partitions),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ConflictRecord:
    """Same-key / different-values evidence. Never resolved by last-wins.

    ``gap_ns`` carries the disputed record's real normalized UTC-epoch-ns
    bounds — [bar_start, bar_end) for bars, [ts, ts+1) for ticks — taken from
    the existing row at conflict detection. A QUARANTINE resolution removes
    exactly that interval, so callers can build the explicit
    ``KnownGap(dataset_id, gap_ns[0], gap_ns[1], reason)`` allowance from the
    public receipt alone, without parsing sidecars or assuming a 1ns point.
    """

    conflict_id: str
    dataset_id: str
    partition: str
    key: str
    existing_revision: str
    existing_evidence: str
    candidate_evidence: str
    resolution: ConflictResolution | None
    gap_ns: tuple[int, int] | None = None


@dataclass(frozen=True)
class PartitionReceipt:
    partition: str
    revision_id: str
    files: tuple[str, ...]
    rows: int
    base_revision: str | None


@dataclass(frozen=True)
class ImportReceipt:
    batch_id: str
    dataset_id: str
    state: BatchState
    partitions: tuple[PartitionReceipt, ...]
    input_rows: int
    accepted_rows: int
    duplicate_rows: int
    quarantined_rows: int
    parse_failures: int
    conflicts: tuple[ConflictRecord, ...]
    idempotency_key: str
    request: ImportRequest
    detail: str = ""


# ---------------------------------------------------------------------------
# Revisions and recovery
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RevisionReceipt:
    dataset_id: str
    partition: str
    revision_id: str
    parent_revision: str | None
    files: tuple[str, ...]
    rows: int
    batch_id: str


@dataclass(frozen=True)
class BatchRecovery:
    batch_id: str
    prior_state: BatchState
    action: str  # "republished" | "returned_prior_receipt" | "failed" | "orphan_only"
    receipt: ImportReceipt | None
    error: str | None


@dataclass(frozen=True)
class RecoveryReport:
    root: Path
    batches: tuple[BatchRecovery, ...]
    orphan_files: tuple[Path, ...]


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Selection:
    dataset_id: str
    partition: str  # "*" selects all partitions of the dataset


@dataclass(frozen=True)
class KnownGap:
    dataset_id: str
    start_ns: int
    end_ns: int
    reason: str


@dataclass(frozen=True)
class SnapshotRequest:
    selections: tuple[Selection, ...]
    required_fields: tuple[str, ...] = ("open", "high", "low", "close", "volume")
    allow_known_gaps: tuple[KnownGap, ...] = ()
    conflict_policy: ConflictPolicy = ConflictPolicy.ERROR


@dataclass(frozen=True)
class SnapshotRef:
    snapshot_id: str
    manifest_path: Path
    datasets: tuple[str, ...]
    created_at: str


# ---------------------------------------------------------------------------
# Recording session reports and sealing (WP08/WP09 — implemented; see
# research_store.journal / session_recovery / aggregation / sealing)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionRecoveryReport:
    """Result of recovering an unclosed recording session."""

    session_id: str
    prior_status: str
    replayed_committed_seq: tuple[int, ...]
    predecessor_session_id: str | None
    detail: str
    successor_session_id: str | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class SealRequest:
    """Idempotent seal of a committed session watermark range.

    F4 (recording02I): asset class, volume unit, and turnover unit carry
    explicit semantics — there is no unconditional FUTURES default. When a
    caller omits them they deliberately default to the HONEST UNQUALIFIED
    combination ``AssetClass.OTHER`` + ``"unknown"`` units, which the
    sealer publishes visibly (it never guesses futures semantics). The
    sealer validates the combination (``SealError`` for unsupported
    pairings) and requires the declared asset class to be consistent with
    the session's stored ``source_spec`` kind (e.g. a ``"futures:..."`
    source must seal as ``AssetClass.FUTURES``).
    """

    session_id: str
    committed_seq_start: int
    committed_seq_end: int
    transform_version: str
    source_spec: str
    calendar_spec: str
    asset_class: AssetClass = AssetClass.OTHER
    volume_unit: str = "unknown"
    turnover_unit: str = "unknown"

    def __post_init__(self) -> None:
        # Normalize the enum's string value (e.g. from a JSON/CLI payload) to
        # the enum so identity hashing and unit validation always see
        # AssetClass. An invalid value is a typed StoreError, never a
        # downstream AttributeError.
        if not isinstance(self.asset_class, AssetClass):
            try:
                object.__setattr__(self, "asset_class", AssetClass(self.asset_class))
            except ValueError as exc:
                raise StoreError(
                    f"invalid asset_class {self.asset_class!r}; expected one of "
                    f"{sorted(c.value for c in AssetClass)}"
                ) from exc


@dataclass(frozen=True)
class SealReceipt:
    """Receipt of a sealed session output publication."""

    session_id: str
    seal_id: str
    partitions: tuple[PartitionReceipt, ...]
    idempotent_replay: bool
    dataset_id: str | None = None
    input_events: int = 0
    accepted_rows: int = 0
    detail: str = ""
