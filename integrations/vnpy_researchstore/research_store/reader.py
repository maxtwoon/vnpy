"""Snapshot reader: streaming Arrow RecordBatch queries over pinned files.

Reads EXACTLY the files listed in the snapshot manifest — never globs current
directories. Each file's sha256 is verified on first touch. Queries are
half-open ``[start, end)``; consumers with inclusive-end contracts must
convert before calling (the core never pads ranges).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path

import duckdb
import pyarrow as pa

from .models import (
    CoverageGapError,
    IntegrityError,
    MissingFieldDataError,
    StoreError,
    UnavailableFieldError,
    UnknownDatasetError,
)
from .objects import verify_object
from .schemas import schema_for
from .store import Store

_OHLCV = ("open", "high", "low", "close", "volume")

# Gap intervals quarantined by conflict resolution are point gaps at the key
# timestamp; the reader rejects queries that intersect them unless the
# snapshot explicitly allowed them.
_QUARANTINE_CODES = {"same_key_different_values"}


def _escape_sql_string(value: str) -> str:
    return value.replace("'", "''")


def _to_ns(value: datetime) -> int:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise StoreError(f"naive datetime {value!r} rejected; use aware datetimes")
    return int(value.timestamp() * 1_000_000_000)


class SnapshotReader:
    """Streaming reader bound to one immutable snapshot manifest."""

    def __init__(self, store: Store, manifest: dict) -> None:
        self._store = store
        self._manifest = manifest
        self.snapshot_id: str = str(manifest.get("snapshot_id", ""))
        self._verified: set[str] = set()
        spill = store.path.staging / "duckdb"
        spill.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(":memory:")
        self._conn.execute("SET threads=4")
        self._conn.execute("SET memory_limit='8GB'")
        self._conn.execute(f"SET temp_directory='{spill.as_posix()}'")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SnapshotReader:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- selection helpers --------------------------------------------------

    def _selections_for(self, dataset_id: str) -> list[dict]:
        selections = [
            s for s in self._manifest.get("selections", [])
            if s["dataset_id"] == dataset_id
        ]
        if not selections:
            known = sorted({s["dataset_id"] for s in self._manifest.get("selections", [])})
            raise UnknownDatasetError(
                f"dataset {dataset_id} is not part of snapshot {self.snapshot_id}; "
                f"available: {known}"
            )
        return selections

    def _verified_files(self, selections: list[dict]) -> list[str]:
        files: list[str] = []
        for selection in selections:
            for entry in selection.get("files", []):
                relpath = str(entry["path"])
                if relpath not in self._verified:
                    verify_object(self._store.root, relpath, str(entry["sha256"]))
                    self._verified.add(relpath)
                files.append(str(self._store.root / relpath))
        return files

    def default_qualified_exclusions(self, dataset_id: str) -> list[dict]:
        """Exclusions captured at freeze time for one dataset ([] when nothing
        is excluded or the snapshot predates the capture — check
        :meth:`default_qualified_status` to tell those apart)."""
        return [
            e
            for e in self._manifest.get("default_qualified_exclusions", [])
            if e.get("dataset_id") == dataset_id
        ]

    def default_qualified_status(self, dataset_id: str) -> str:
        """Typed qualification status of one dataset in this snapshot:

        * ``"qualified"`` — manifest format >= 2 carries the policy capture;
          the dataset's exclusions (possibly none) are known and default
          qualified reads enforce them.
        * ``"legacy_unqualified"`` — the manifest predates the policy capture
          (format 1, no ``default_qualified_exclusions`` key): default
          qualified reads REFUSE this dataset; only explicit observational
          access is available. Old bytes are never rewritten.
        """
        if "default_qualified_exclusions" not in self._manifest:
            return "legacy_unqualified"
        return "qualified"

    def _check_gaps(
        self,
        dataset_id: str,
        start_ns: int | None,
        end_ns: int | None,
        include_default_excluded: bool,
    ) -> list[dict]:
        """Refuse queries over recorded gaps the snapshot did not allow.

        Returns the default-qualified exclusion entries whose gaps WERE
        explicitly allowed; the caller must filter those rows out of the
        result stream (the allowance permits the missing interval, never the
        rejected row).
        """
        allowed = {
            (g["start_ns"], g["end_ns"])
            for g in self._manifest.get("allowed_gaps", [])
            if g["dataset_id"] == dataset_id
        }
        for decision in self._manifest.get("quality_decisions", []):
            if decision.get("dataset_id") != dataset_id:
                continue
            if decision.get("resolution") != "quarantine":
                continue
            if decision.get("code") not in _QUARANTINE_CODES:
                continue
            # Preferred: the disputed bar's real normalized bounds, recorded
            # at conflict detection. Fallback: legacy point keys.
            gap = decision.get("gap_ns")
            if isinstance(gap, list) and len(gap) == 2 and gap[0] is not None:
                g_start, g_end = int(gap[0]), int(gap[1])
            else:
                key = decision.get("key")
                if isinstance(key, list) and len(key) == 2:
                    ts = int(key[1])
                elif isinstance(key, str) and "@" in key:
                    ts = int(key.rsplit("@", 1)[1])
                else:
                    continue
                g_start, g_end = ts, ts + 1
            if any(a_start <= g_start and g_end <= a_end for a_start, a_end in allowed):
                continue
            if start_ns is not None and g_end <= start_ns:
                continue
            if end_ns is not None and g_start >= end_ns:
                continue
            raise CoverageGapError(
                f"query over {dataset_id} intersects quarantined gap "
                f"[{g_start}, {g_end}) ns (key {decision.get('key')}); "
                "the gap is visible and unfilled — re-freeze with an explicit "
                "allow_known_gaps entry and reason to proceed"
            )
        allowed_exclusions: list[dict] = []
        if include_default_excluded:
            # Explicit observational read: every pinned row is visible and no
            # default-qualified refusal applies. Callers must not pass this
            # through to qualified backtest consumers.
            return allowed_exclusions
        if self.default_qualified_status(dataset_id) == "legacy_unqualified":
            # The snapshot predates the default-qualified policy capture:
            # repaired rows in its pinned files were never evaluated and must
            # not be silently presented as qualified. Refuse default qualified
            # reads; observational access (include_default_excluded=True) and
            # the store-level inspection paths keep their prior meaning.
            raise CoverageGapError(
                f"query over {dataset_id} uses snapshot {self.snapshot_id} "
                "which predates the default-qualified policy capture "
                "(legacy manifest format); its repaired/disputed rows were "
                "never evaluated and cannot be presented as qualified — "
                "re-freeze from the current published heads to capture the "
                "policy, or use explicit observational access "
                "(include_default_excluded=True) / store-level source-label "
                "inspection"
            )
        for entry in self.default_qualified_exclusions(dataset_id):
            g_start, g_end = int(entry["start_ns"]), int(entry["end_ns"])
            if any(a_start <= g_start and g_end <= a_end for a_start, a_end in allowed):
                allowed_exclusions.append(entry)
                continue
            if start_ns is not None and g_end <= start_ns:
                continue
            if end_ns is not None and g_start >= end_ns:
                continue
            raise CoverageGapError(
                f"query over {dataset_id} intersects default-qualified "
                f"exclusion [{g_start}, {g_end}) ns "
                f"({entry.get('instrument')} @ {entry.get('source_label')}, "
                f"flags {entry.get('flags')}); repaired/disputed rows are "
                "excluded from default qualified backtest data — re-freeze "
                "with an explicit allow_known_gaps entry and reason to "
                "proceed; the allowed interval stays missing (the rejected "
                "row is never returned); observational access stays available "
                "via include_default_excluded=True or the store-level "
                "source-label inspection path"
            )
        return allowed_exclusions

    # -- queries ------------------------------------------------------------

    def bars(
        self,
        dataset_id: str,
        instruments: Sequence[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        required_fields: Sequence[str] = _OHLCV,
        allow_missing_auxiliary: bool = False,
        include_default_excluded: bool = False,
    ) -> Iterator[pa.RecordBatch]:
        """Stream bars of one dataset.

        Default reads are QUALIFIED: queries intersecting a default-qualified
        exclusion (repaired/disputed rows captured at freeze time) raise
        :class:`CoverageGapError` unless the snapshot explicitly allowed the
        gap; allowed exclusions are filtered out of the stream.
        ``include_default_excluded=True`` is the explicit observational mode
        (every pinned row, no refusal) — it must never feed qualified
        backtest consumers.
        """
        selections = self._selections_for(dataset_id)
        return self._query(
            selections, "bars", dataset_id, instruments, start, end,
            required_fields, allow_missing_auxiliary, include_default_excluded,
        )

    def ticks(
        self,
        dataset_id: str,
        instruments: Sequence[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        required_fields: Sequence[str] = (),
        allow_missing_auxiliary: bool = False,
        include_default_excluded: bool = False,
    ) -> Iterator[pa.RecordBatch]:
        selections = self._selections_for(dataset_id)
        return self._query(
            selections, "ticks", dataset_id, instruments, start, end,
            required_fields, allow_missing_auxiliary, include_default_excluded,
        )

    def _query(
        self,
        selections: list[dict],
        record_kind: str,
        dataset_id: str,
        instruments: Sequence[str] | None,
        start: datetime | None,
        end: datetime | None,
        required_fields: Sequence[str],
        allow_missing_auxiliary: bool,
        include_default_excluded: bool,
    ) -> Iterator[pa.RecordBatch]:
        schema = schema_for(record_kind)
        for selection in selections:
            kind = selection.get("semantic", {}).get("record_kind")
            if kind is not None and kind != record_kind:
                raise StoreError(
                    f"dataset {dataset_id} holds {kind} records, not {record_kind}"
                )
        unavailable = [f for f in required_fields if f not in schema.names]
        if unavailable:
            raise UnavailableFieldError(
                f"fields {unavailable} are not in the {record_kind} v1 schema"
            )

        start_ns = _to_ns(start) if start is not None else None
        end_ns = _to_ns(end) if end is not None else None
        allowed_exclusions = self._check_gaps(
            dataset_id, start_ns, end_ns, include_default_excluded
        )

        files = self._verified_files(selections)
        if not files:
            return iter(())  # selection legitimately empty: no data, not an error

        time_col = "bar_start" if record_kind == "bars" else "ts"
        # Deterministic canonical order: bars by (identity, bar_start) — daily
        # by (identity, ts-of-bar_start); ticks by canonical event identity
        # (identity, session_id, seq), never by unstable file/query order.
        order_cols = (
            "COALESCE(instrument_id, series_id), session_id, seq"
            if record_kind == "ticks"
            else f"COALESCE(instrument_id, series_id), {time_col}"
        )
        where = []
        if start_ns is not None:
            where.append(f"{time_col} >= {start_ns}")
        if end_ns is not None:
            where.append(f"{time_col} < {end_ns}")
        if instruments:
            listed = ", ".join(f"'{i.replace(chr(39), chr(39) * 2)}'" for i in instruments)
            where.append(f"(instrument_id IN ({listed}) OR series_id IN ({listed}))")
        if record_kind == "bars":
            # Allowed default-qualified exclusions stay missing from
            # qualified reads: filter the rejected rows by their exact
            # (identity, bar_start, bar_end) key — never return them.
            for entry in allowed_exclusions:
                identity = _escape_sql_string(str(entry["instrument"]))
                where.append(
                    "NOT (COALESCE(instrument_id, series_id) = "
                    f"'{identity}' AND bar_start = {int(entry['start_ns'])} "
                    f"AND bar_end = {int(entry['end_ns'])})"
                )
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        file_list = ", ".join(f"'{Path(f).as_posix()}'" for f in files)
        sql = (
            f"SELECT * FROM read_parquet([{file_list}], union_by_name=true) "
            f"{where_sql} ORDER BY {order_cols}"
        )
        cursor = self._conn.cursor()  # independent cursor; execute() returns self
        cursor.execute(sql)
        return self._stream(cursor, required_fields, allow_missing_auxiliary)

    def _stream(
        self,
        cursor: duckdb.DuckDBPyConnection,
        required_fields: Sequence[str],
        allow_missing_auxiliary: bool,
    ) -> Iterator[pa.RecordBatch]:
        strict = [f for f in required_fields if f in _OHLCV or not allow_missing_auxiliary]
        try:
            reader = cursor.to_arrow_reader(65536)
            for batch in reader:
                missing = [
                    name for name in strict
                    if batch.column(name).null_count > 0
                ]
                if missing:
                    raise MissingFieldDataError(
                        f"NULLs present in required fields {missing}; re-query with "
                        "allow_missing_auxiliary=True for auxiliary NaN passthrough "
                        "(OHLCV NULLs are never passed through)"
                    )
                yield batch
        finally:
            cursor.close()

    def check_integrity(self) -> None:
        """Verify every pinned file upfront (hash check over the manifest)."""

        for selection in self._manifest.get("selections", []):
            for entry in selection.get("files", []):
                verify_object(
                    self._store.root, str(entry["path"]), str(entry["sha256"])
                )
        if not self._manifest.get("selections"):
            raise IntegrityError(f"snapshot {self.snapshot_id} pins no selections")
