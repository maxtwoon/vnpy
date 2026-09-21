"""SQLite catalog: metadata for assets, datasets, batches, revisions,
partition heads, snapshots, quality issues, and recording sessions.

Hard pragmas: WAL, foreign_keys=ON, synchronous=FULL, busy_timeout=5000,
user_version=1. Per-bar rows are NEVER stored here — detailed
security/calendar/coverage/conflict payloads live in versioned Parquet/sidecar
files referenced by hash.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from .models import CatalogError

USER_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    origin TEXT NOT NULL,
    format TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT,
    discovery TEXT NOT NULL DEFAULT 'fast',
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    semantic_json TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    adapter TEXT NOT NULL,
    config_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN
        ('running','prepared','published','failed','conflicted')),
    input_rows INTEGER NOT NULL DEFAULT 0,
    accepted_rows INTEGER NOT NULL DEFAULT 0,
    duplicate_rows INTEGER NOT NULL DEFAULT 0,
    quarantined_rows INTEGER NOT NULL DEFAULT 0,
    parse_failures INTEGER NOT NULL DEFAULT 0,
    receipt_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revisions (
    revision_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    partition TEXT NOT NULL,
    parent_revision TEXT,
    manifest_path TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    rows INTEGER NOT NULL,
    batch_id TEXT NOT NULL REFERENCES batches(batch_id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS partition_heads (
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    partition TEXT NOT NULL,
    revision_id TEXT NOT NULL REFERENCES revisions(revision_id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (dataset_id, partition)
);

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    manifest_path TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_issues (
    issue_id TEXT PRIMARY KEY,
    scope_dataset_id TEXT NOT NULL,
    scope_partition TEXT NOT NULL,
    code TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    resolution TEXT,
    resolved_by_revision TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS recording_sessions (
    session_id TEXT PRIMARY KEY,
    source_spec TEXT NOT NULL,
    calendar_spec TEXT NOT NULL,
    journal_path TEXT NOT NULL,
    status TEXT NOT NULL,
    predecessor_session_id TEXT,
    sealed_output_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class Catalog:
    """Thin typed wrapper over the catalog SQLite database."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn = sqlite3.connect(
            str(path), timeout=5.0, isolation_level=None, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._apply_pragmas()
        self._apply_schema()

    def _apply_pragmas(self) -> None:
        cur = self._conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=FULL")
        cur.execute("PRAGMA busy_timeout=5000")
        row = cur.execute("PRAGMA user_version").fetchone()
        if row[0] not in (0, USER_VERSION):
            raise CatalogError(
                f"catalog user_version {row[0]} unsupported (expected {USER_VERSION})"
            )
        cur.close()

    def _apply_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA)
            self._conn.execute(f"PRAGMA user_version={USER_VERSION}")

    def close(self) -> None:
        self._conn.close()

    # -- generic helpers ----------------------------------------------------

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def query_one(
        self, sql: str, params: tuple[object, ...] = ()
    ) -> sqlite3.Row | None:
        return cast("sqlite3.Row | None", self._conn.execute(sql, params).fetchone())

    def query_all(
        self, sql: str, params: tuple[object, ...] = ()
    ) -> list[sqlite3.Row]:
        return list(self._conn.execute(sql, params).fetchall())

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        """Short atomic transaction. ``immediate=True`` takes the write lock up
        front (used by the publish CAS); default is a deferred read/write
        transaction (used by freeze's consistent capture).

        Transactions are serialized per connection (SQLite is single-writer);
        concurrent publishers therefore race on the base-head compare, which
        is exactly the CAS the publish protocol relies on.
        """

        mode = "IMMEDIATE" if immediate else "DEFERRED"
        with self._lock:
            self._conn.execute(f"BEGIN {mode}")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    # -- typed accessors ------------------------------------------------------

    def upsert_asset(
        self,
        asset_id: str,
        origin: str,
        format: str,
        size: int,
        sha256: str | None,
        discovery: str,
        registered_at: str,
    ) -> None:
        with self.transaction():
            self._conn.execute(
                """
                INSERT INTO assets (asset_id, origin, format, size, sha256,
                                    discovery, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    origin=excluded.origin, format=excluded.format,
                    size=excluded.size,
                    sha256=COALESCE(excluded.sha256, assets.sha256),
                    discovery=excluded.discovery
                """,
                (asset_id, origin, format, size, sha256, discovery, registered_at),
            )

    def ensure_dataset(
        self, dataset_id: str, semantic_json: str, schema_version: int, created_at: str
    ) -> None:
        # Check-and-insert must be atomic: concurrent publishers of the same
        # new dataset race here.
        with self.transaction(immediate=True):
            existing = self._conn.execute(
                "SELECT semantic_json, schema_version FROM datasets WHERE dataset_id=?",
                (dataset_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["semantic_json"] != semantic_json
                    or existing["schema_version"] != schema_version
                ):
                    raise CatalogError(
                        f"dataset {dataset_id} already registered with different semantics"
                    )
                return
            self._conn.execute(
                "INSERT INTO datasets (dataset_id, semantic_json, schema_version, created_at)"
                " VALUES (?, ?, ?, ?)",
                (dataset_id, semantic_json, schema_version, created_at),
            )

    def get_dataset(self, dataset_id: str) -> sqlite3.Row | None:
        return self.query_one(
            "SELECT * FROM datasets WHERE dataset_id=?", (dataset_id,)
        )

    def begin_batch(
        self,
        batch_id: str,
        idempotency_key: str,
        asset_id: str,
        dataset_id: str,
        adapter: str,
        config: Mapping[str, str],
        created_at: str,
    ) -> None:
        with self.transaction():
            self._conn.execute(
                """
                INSERT INTO batches (batch_id, idempotency_key, asset_id,
                    dataset_id, adapter, config_json, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?)
                """,
                (
                    batch_id,
                    idempotency_key,
                    asset_id,
                    dataset_id,
                    adapter,
                    json.dumps(dict(sorted(config.items())), sort_keys=True),
                    created_at,
                    created_at,
                ),
            )

    def get_batch(self, batch_id: str) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM batches WHERE batch_id=?", (batch_id,))

    def find_batch_by_key(self, idempotency_key: str) -> sqlite3.Row | None:
        """Latest batch for an idempotency key (superseded retries share it)."""

        return self.query_one(
            "SELECT * FROM batches WHERE idempotency_key=?"
            " ORDER BY created_at DESC, batch_id DESC LIMIT 1",
            (idempotency_key,),
        )

    def set_batch_state(
        self,
        batch_id: str,
        state: str,
        updated_at: str,
        error: str | None = None,
        receipt_json: str | None = None,
    ) -> None:
        with self.transaction():
            self.set_batch_state_in_tx(batch_id, state, updated_at, error, receipt_json)

    def set_batch_state_in_tx(
        self,
        batch_id: str,
        state: str,
        updated_at: str,
        error: str | None = None,
        receipt_json: str | None = None,
    ) -> None:
        """Caller must hold a ``transaction()`` context (used by publish CAS)."""

        self._conn.execute(
            "UPDATE batches SET state=?, error=COALESCE(?, error),"
            " receipt_json=COALESCE(?, receipt_json), updated_at=?"
            " WHERE batch_id=?",
            (state, error, receipt_json, updated_at, batch_id),
        )

    def set_batch_counts(
        self,
        batch_id: str,
        input_rows: int,
        accepted_rows: int,
        duplicate_rows: int,
        quarantined_rows: int,
        parse_failures: int,
    ) -> None:
        with self.transaction():
            self._conn.execute(
                "UPDATE batches SET input_rows=?, accepted_rows=?, duplicate_rows=?,"
                " quarantined_rows=?, parse_failures=? WHERE batch_id=?",
                (
                    input_rows,
                    accepted_rows,
                    duplicate_rows,
                    quarantined_rows,
                    parse_failures,
                    batch_id,
                ),
            )

    def get_head(self, dataset_id: str, partition: str) -> str | None:
        row = self.query_one(
            "SELECT revision_id FROM partition_heads WHERE dataset_id=? AND partition=?",
            (dataset_id, partition),
        )
        return None if row is None else str(row["revision_id"])

    def insert_revision(
        self,
        revision_id: str,
        dataset_id: str,
        partition: str,
        parent_revision: str | None,
        manifest_path: str,
        manifest_sha256: str,
        rows: int,
        batch_id: str,
        created_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO revisions (revision_id, dataset_id, partition,
                parent_revision, manifest_path, manifest_sha256, rows,
                batch_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                dataset_id,
                partition,
                parent_revision,
                manifest_path,
                manifest_sha256,
                rows,
                batch_id,
                created_at,
            ),
        )

    def set_head(
        self, dataset_id: str, partition: str, revision_id: str, updated_at: str
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO partition_heads (dataset_id, partition, revision_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(dataset_id, partition) DO UPDATE SET
                revision_id=excluded.revision_id, updated_at=excluded.updated_at
            """,
            (dataset_id, partition, revision_id, updated_at),
        )

    def get_revision(self, revision_id: str) -> sqlite3.Row | None:
        return self.query_one(
            "SELECT * FROM revisions WHERE revision_id=?", (revision_id,)
        )

    def insert_snapshot(
        self, snapshot_id: str, manifest_path: str, manifest_sha256: str, created_at: str
    ) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO snapshots (snapshot_id, manifest_path, manifest_sha256, created_at)"
                " VALUES (?, ?, ?, ?)",
                (snapshot_id, manifest_path, manifest_sha256, created_at),
            )

    def get_snapshot(self, snapshot_id: str) -> sqlite3.Row | None:
        return self.query_one(
            "SELECT * FROM snapshots WHERE snapshot_id=?", (snapshot_id,)
        )

    def insert_quality_issue(
        self,
        issue_id: str,
        dataset_id: str,
        partition: str,
        code: str,
        evidence: Mapping[str, object],
        created_at: str,
    ) -> None:
        with self.transaction():
            self._conn.execute(
                "INSERT INTO quality_issues (issue_id, scope_dataset_id,"
                " scope_partition, code, evidence_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    issue_id,
                    dataset_id,
                    partition,
                    code,
                    json.dumps(evidence, sort_keys=True, default=str),
                    created_at,
                ),
            )

    def resolve_quality_issue(
        self, issue_id: str, resolution: str, resolved_by_revision: str, resolved_at: str
    ) -> None:
        with self.transaction():
            self.resolve_quality_issue_in_tx(
                issue_id, resolution, resolved_by_revision, resolved_at
            )

    def resolve_quality_issue_in_tx(
        self, issue_id: str, resolution: str, resolved_by_revision: str, resolved_at: str
    ) -> None:
        """Caller must hold a ``transaction()`` context."""

        self._conn.execute(
            "UPDATE quality_issues SET resolution=?, resolved_by_revision=?,"
            " resolved_at=? WHERE issue_id=?",
            (resolution, resolved_by_revision, resolved_at, issue_id),
        )

    def unresolved_issues(self, dataset_id: str, partition: str) -> list[sqlite3.Row]:
        return self.query_all(
            "SELECT * FROM quality_issues WHERE scope_dataset_id=?"
            " AND scope_partition=? AND resolution IS NULL",
            (dataset_id, partition),
        )

    def batches_by_state(self, state: str) -> list[sqlite3.Row]:
        return self.query_all(
            "SELECT * FROM batches WHERE state=? ORDER BY created_at", (state,)
        )

    # -- recording sessions (WP08/WP09 journal/recording scope) ---------------

    def upsert_recording_session(
        self,
        session_id: str,
        source_spec: str,
        calendar_spec: str,
        journal_path: str,
        status: str,
        predecessor_session_id: str | None,
        created_at: str,
        updated_at: str,
    ) -> None:
        with self.transaction():
            self._conn.execute(
                """
                INSERT INTO recording_sessions (session_id, source_spec,
                    calendar_spec, journal_path, status,
                    predecessor_session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    source_spec=excluded.source_spec,
                    calendar_spec=excluded.calendar_spec,
                    journal_path=excluded.journal_path,
                    status=excluded.status,
                    predecessor_session_id=excluded.predecessor_session_id,
                    updated_at=excluded.updated_at
                """,
                (
                    session_id,
                    source_spec,
                    calendar_spec,
                    journal_path,
                    status,
                    predecessor_session_id,
                    created_at,
                    updated_at,
                ),
            )

    def get_recording_session(self, session_id: str) -> sqlite3.Row | None:
        return self.query_one(
            "SELECT * FROM recording_sessions WHERE session_id=?", (session_id,)
        )

    def update_recording_session_status(
        self,
        session_id: str,
        status: str,
        updated_at: str,
        sealed_output_json: str | None = None,
    ) -> None:
        with self.transaction():
            if sealed_output_json is None:
                self._conn.execute(
                    "UPDATE recording_sessions SET status=?, updated_at=?"
                    " WHERE session_id=?",
                    (status, updated_at, session_id),
                )
            else:
                self._conn.execute(
                    "UPDATE recording_sessions SET status=?, updated_at=?,"
                    " sealed_output_json=? WHERE session_id=?",
                    (status, updated_at, sealed_output_json, session_id),
                )

    def recording_sessions_by_status(self, status: str) -> list[sqlite3.Row]:
        return self.query_all(
            "SELECT * FROM recording_sessions WHERE status=? ORDER BY created_at",
            (status,),
        )
