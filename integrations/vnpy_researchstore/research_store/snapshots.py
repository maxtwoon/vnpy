"""Immutable snapshots: consistent freeze and snapshot opening.

``freeze`` captures ALL selected partition heads, revision manifests, and
versioned quality decisions in ONE short SQLite read transaction (audit N3);
the immutable snapshot manifest is written afterward from that capture. No
independent per-dataset head reads, and later imports/issues never change an
existing snapshot's interpretation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .models import (
    ConflictPolicy,
    SnapshotRef,
    SnapshotRequest,
    StoreError,
    UnknownDatasetError,
    UnresolvedConflictError,
)
from .objects import hash_file, write_json_manifest
from .store import Store

if TYPE_CHECKING:
    from .reader import SnapshotReader

# Manifest format version. Format 2 adds the default-qualified exclusion
# capture (`default_qualified_exclusions`); format 1 manifests predate the
# policy capture and are treated as LEGACY UNQUALIFIED by default qualified
# reads (see SnapshotReader.default_qualified_status) — their bytes and
# observational meaning are preserved, never rewritten.
SNAPSHOT_FORMAT = 2


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def freeze(store: Store, request: SnapshotRequest) -> SnapshotRef:
    """Capture selected dataset/partition heads into an immutable snapshot.

    Default policy: unresolved conflicts overlapping a selection fail the
    freeze; known gaps require explicit ``allow_known_gaps`` with reasons.
    Ambiguous selections (unknown dataset, empty partition resolution) are
    errors, never latest-source guesses.

    The default-qualified exclusion set (all deterministic repaired keys, per
    ``quality.DEFAULT_EXCLUSION_FLAGS``) is evaluated over the selected
    published rows and captured into the manifest as
    ``default_qualified_exclusions`` (manifest format 2);
    ``SnapshotReader`` default reads refuse intersecting queries unless the
    gap was explicitly allowed, and allowed exclusions are filtered out of
    returned rows. Snapshots frozen before this capture (format 1, no key)
    are recognizably LEGACY UNQUALIFIED: default qualified reads refuse them
    with an explicit error while observational access keeps its prior
    meaning. The Parquet exclusion scan runs AFTER the short catalog
    transaction, over immutable file references captured inside it.
    """

    if not request.selections:
        raise StoreError("freeze requires at least one selection")
    if request.conflict_policy is not ConflictPolicy.ERROR:
        raise StoreError(f"unsupported conflict policy {request.conflict_policy}")

    for gap in request.allow_known_gaps:
        if not gap.reason:
            raise StoreError("allow_known_gaps entries require a recorded reason")

    captured_selections: list[dict] = []
    captured_issues: list[dict] = []
    # Immutable file references (partition, relpath, sha256) per dataset,
    # captured inside the short transaction; Parquet scanning happens only
    # AFTER the transaction exits (qualified-fix05 F2).
    captured_file_refs: list[tuple[str, str, list[tuple[str, str, str]]]] = []
    with store.catalog.transaction():  # one short consistent read transaction
        for selection in request.selections:
            dataset = store.catalog.get_dataset(selection.dataset_id)
            if dataset is None:
                raise UnknownDatasetError(
                    f"unknown dataset {selection.dataset_id} in freeze selection"
                )
            if selection.partition == "*":
                heads = store.catalog.query_all(
                    "SELECT * FROM partition_heads WHERE dataset_id=?",
                    (selection.dataset_id,),
                )
            else:
                row = store.catalog.query_one(
                    "SELECT * FROM partition_heads WHERE dataset_id=? AND partition=?",
                    (selection.dataset_id, selection.partition),
                )
                heads = [] if row is None else [row]
            if not heads:
                raise StoreError(
                    f"selection {selection.dataset_id}/{selection.partition} "
                    "resolves to no published partitions"
                )
            selection_file_refs: list[tuple[str, str, str]] = []
            for head in heads:
                partition = str(head["partition"])
                revision = store.catalog.get_revision(str(head["revision_id"]))
                if revision is None:
                    raise StoreError(
                        f"head revision {head['revision_id']} missing from catalog"
                    )
                manifest_path = Path(str(revision["manifest_path"]))
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                unresolved = store.catalog.unresolved_issues(
                    selection.dataset_id, partition
                )
                for issue in unresolved:
                    raise UnresolvedConflictError(
                        f"unresolved issue {issue['issue_id']} "
                        f"({issue['code']}) overlaps selection "
                        f"{selection.dataset_id}/{partition}; resolve or quarantine "
                        "before freezing"
                    )
                captured_selections.append(
                    {
                        "dataset_id": selection.dataset_id,
                        "partition": partition,
                        "revision_id": str(revision["revision_id"]),
                        "revision_manifest_sha256": str(revision["manifest_sha256"]),
                        "rows": int(revision["rows"]),
                        "files": manifest.get("files", []),
                        "coverage": manifest.get("coverage", {}),
                        "semantic": json.loads(str(dataset["semantic_json"])),
                    }
                )
                for file_entry in manifest.get("files", []):
                    selection_file_refs.append(
                        (
                            partition,
                            str(file_entry["path"]),
                            str(file_entry["sha256"]),
                        )
                    )
            captured_file_refs.append(
                (selection.dataset_id, selection.partition, selection_file_refs)
            )
        issue_rows = store.catalog.query_all(
            "SELECT * FROM quality_issues WHERE resolution IS NOT NULL"
        )
        for issue in issue_rows:
            evidence = json.loads(str(issue["evidence_json"]))
            captured_issues.append(
                {
                    "issue_id": issue["issue_id"],
                    "dataset_id": issue["scope_dataset_id"],
                    "partition": issue["scope_partition"],
                    "code": issue["code"],
                    "resolution": issue["resolution"],
                    "resolved_by_revision": issue["resolved_by_revision"],
                    "key": evidence.get("key"),
                    "gap_ns": evidence.get("gap_ns"),
                }
            )

    # Outside the transaction: compute the default-qualified exclusion set
    # from the captured immutable file references only — never by rereading
    # mutable current heads (qualified-fix05 F2). Hash verification and
    # Parquet scans run here, after the catalog lock is released.
    from .quality import scan_exclusion_entries_in_files

    captured_exclusions: list[dict] = []
    for dataset_id, _partition, file_refs in captured_file_refs:
        for entry in scan_exclusion_entries_in_files(
            store.root, dataset_id, file_refs
        ):
            captured_exclusions.append(
                {
                    "dataset_id": entry["dataset_id"],
                    "partition": entry["partition"],
                    "instrument": entry["instrument"],
                    "start_ns": entry["start_ns"],
                    "end_ns": entry["end_ns"],
                    "source_label": entry["source_label"],
                    "flags": entry["flags"],
                }
            )

    manifest = {
        "snapshot_format": SNAPSHOT_FORMAT,
        "selections": captured_selections,
        "required_fields": list(request.required_fields),
        "allowed_gaps": [
            {
                "dataset_id": g.dataset_id,
                "start_ns": g.start_ns,
                "end_ns": g.end_ns,
                "reason": g.reason,
            }
            for g in request.allow_known_gaps
        ],
        "quality_decisions": captured_issues,
        "default_qualified_exclusions": captured_exclusions,
        "conflict_policy": request.conflict_policy.value,
    }
    # Content-derived id over the semantic capture only (created_at excluded):
    # identical captures share a snapshot id; any change produces a new one.
    import hashlib

    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    snapshot_id = f"snap-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"
    manifest_path = store.path.snapshot_manifests / f"{snapshot_id}.json"

    existing = store.catalog.get_snapshot(snapshot_id)
    if existing is not None:
        prior = load_snapshot_manifest(store, snapshot_id)
        return SnapshotRef(
            snapshot_id=snapshot_id,
            manifest_path=Path(str(existing["manifest_path"])),
            datasets=tuple(sorted({s["dataset_id"] for s in captured_selections})),
            created_at=str(prior["created_at"]),
        )

    manifest["snapshot_id"] = snapshot_id
    manifest["created_at"] = _utcnow()
    manifest_sha = write_json_manifest(store.path.staging, manifest_path, manifest)
    store.catalog.insert_snapshot(
        snapshot_id, str(manifest_path), manifest_sha, _utcnow()
    )
    return SnapshotRef(
        snapshot_id=snapshot_id,
        manifest_path=manifest_path,
        datasets=tuple(sorted({s["dataset_id"] for s in captured_selections})),
        created_at=str(manifest["created_at"]),
    )


def load_snapshot_manifest(store: Store, snapshot_id: str) -> dict:
    """Open a snapshot manifest with integrity verification."""

    row = store.catalog.get_snapshot(snapshot_id)
    if row is None:
        # Allow opening a manifest that exists on disk but is not cataloged
        # (e.g. copied store) — still verified by content.
        path = store.path.snapshot_manifests / f"{snapshot_id}.json"
        if not path.is_file():
            raise StoreError(f"unknown snapshot {snapshot_id}")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("snapshot_id") != snapshot_id:
            raise StoreError(f"snapshot manifest {path} id mismatch")
        return manifest  # type: ignore[no-any-return]
    path = Path(str(row["manifest_path"]))
    if not path.is_file():
        from .models import IntegrityError

        raise IntegrityError(f"missing snapshot manifest {path}")
    if hash_file(path) != str(row["manifest_sha256"]):
        from .models import IntegrityError

        raise IntegrityError(f"tampered snapshot manifest {path}")
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def open_snapshot(store: Store, snapshot_id: str) -> SnapshotReader:
    from .reader import SnapshotReader

    return SnapshotReader(store, load_snapshot_manifest(store, snapshot_id))
