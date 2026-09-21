# research_store core interfaces — contract v0.1 (Kimi WP00–WP02)

Status: IMPLEMENTED as described unless marked **PENDING**. PENDING items are typed
stubs for later work packages and are never counted complete. This file is the
binding insertion boundary for OpenCode's importers (`research_store/importers/`),
quality/coverage modules, and the later `vnpy_researchstore` consumers. Do not
invent alternate core APIs; if something is missing, record it in
`.coordination/opencode-core-requests.md`.

Package: `research_store` (pure core — MUST NOT import `vnpy`, provider SDKs, or
touch `~/.vntrader`). Python >= 3.10. Hard dependencies: `pyarrow`, `duckdb`,
`zstandard` (import surface for tar.zst readers; used lazily by importers).

## 1. Store lifecycle (`research_store.store`)

```python
def init_store(root: Path | str) -> Store
def open_store(root: Path | str) -> Store
class Store:
    root: Path
    path: StorePaths          # catalog, objects, revision_manifests, snapshot_manifests,
                              # captures, staging, journals, configs, reports, exports, runtime
    catalog: Catalog          # open SQLite catalog, see §4
    def close(self) -> None
    def __enter__ / __exit__
```

- `init_store` creates `store.json` (`{"store_format": 1, "store_id": ..., "created_at": ...}`)
  plus the plan's directory layout. It refuses a non-empty directory that is not
  already an identified store (raises `StoreExistsError`); re-init of an
  identified store is a no-op returning the open `Store`.
- `open_store` requires a valid `store.json` with `store_format == 1`
  (raises `StoreNotFoundError` / `StoreError`).

## 2. Semantic identity (`research_store.models`, `research_store.schemas`)

```python
@dataclass(frozen=True)
class SemanticSpec:
    source_id: str
    asset_class: AssetClass        # equity|etf|index|futures|option|convertible|other
    record_kind: RecordKind        # bars|ticks|corporate_actions|reference
    interval: Interval             # M1|M5|M15|H1|D1  (enum values "1m","5m","15m","1h","1d")
    adjustment: Adjustment         # NONE|QFQ|HFQ|UNKNOWN
    adjustment_version: str        # "" when not applicable
    series_kind: str               # e.g. "instrument", "continuous_888", "dominant"
    rule_version: str              # selection/roll rule version, "" if none/unknown
    timezone: str                  # e.g. "Asia/Shanghai"
    source_time_label: TimeLabel   # START|END|UNKNOWN
    volume_unit: str               # e.g. "share", "lot", "unknown"
    turnover_unit: str             # e.g. "CNY", "unknown"
    origin_method: OriginMethod    # SOURCE|DERIVED|REPAIRED
    schema_version: int            # record schema version, currently 1

def compute_dataset_id(spec: SemanticSpec) -> str   # "ds-" + sha256(canonical JSON)[:32]
```

Canonical JSON: sorted keys, fixed separators, all fields present. Same contents
always hash to the same `dataset_id`; imports never invent new semantic IDs from
import dates. Different sources/adjustments/native-vs-derived therefore never
silently merge.

## 3. Record schema (`research_store.schemas`)

`BARS_SCHEMA_V1` (`pa.Schema`, `SCHEMA_VERSION = 1`). All float measures are
`float64` and **nullable — real NULLs are preserved end to end**; non-finite
input (inf/nan from sources) must be converted by importers to NULL plus a
field-quality note, and publish validation REJECTS non-finite values.

| column | type | notes |
|---|---|---|
| `dataset_id` | string | semantic id, repeated per row |
| `instrument_id` | string, nullable | real instrument identity; exactly one of `instrument_id`/`series_id` non-null |
| `series_id` | string, nullable | continuous/derived series identity |
| `symbol` | string | original source symbol, case preserved |
| `exchange` | string, nullable | source exchange label, unmapped |
| `bar_start` | int64 | UTC epoch ns, half-open start — always real, NOT NULL |
| `bar_end` | int64 | UTC epoch ns, exclusive end — always real, NOT NULL |
| `trading_date` | date32, nullable | source trading day; NOT derived from UTC midnight. NULL allowed ONLY for minute-interval datasets without calendar evidence (time-contract disposition 2026-09-16), and then the row MUST carry a non-null `field_quality` note; daily datasets must carry non-null `trading_date` (enforced at publish) |
| `source_label` | string, nullable | original timestamp/label verbatim |
| `open` `high` `low` `close` `volume` `turnover` `open_interest` | float64, nullable | real NULL; never zero-filled |
| `completeness` | string | `complete` / `partial` / `unknown` |
| `field_quality` | string, nullable | JSON object per-field notes (untrusted amount, negative OI, unknown trading day, ...) |
| `contract_id` | string, nullable | continuous→real contract mapping for this bar |
| `asset_id` `batch_id` `transform_version` | string | provenance |
| `extensions_json` | string, nullable | JSON object for nonstandard source columns (raw OI/amount etc.) |

`TICKS_SCHEMA_V1` mirrors this shape with two additional REQUIRED identity
columns (core fix03 F3): `session_id` (string, NOT NULL, non-empty — the
recording/import session) and `seq` (int64, NOT NULL — the ingest sequence
within that session). `ts` int64 UTC ns NOT NULL keeps the original event
timestamp at full precision but is NOT the identity. `trading_date` is
nullable under the same minute/unknown-evidence rule; quote/trade float64
columns are nullable. Schema compatibility: v1 is unreleased (`0.1.0.dev1`)
and was redefined in place — no tick dataset written against the earlier
ts-only shape exists, and the strict publish/read schema equality check
rejects any such store rather than misreading it. The core never invents or
defaults a `session_id` for historical rows; importers must supply the real
session identity.

**Identity keys** (dedup/conflict/order): minute bars key on
`(instrument_id or series_id, bar_start)`; **daily bars key on
`(instrument_id or series_id, trading_date)`** — never on a natural date or
UTC midnight; **ticks key on `(instrument_id or series_id, session_id, seq)`**
so two distinct events at the same `ts` both survive even with identical
market fields. Same tick identity replayed with an identical payload dedups
idempotently; the same identity with a changed payload (including a changed
`ts`) is an explicit conflict — never a silently accepted new event. Tick
conflict keys render as `identity@session_id@seq`; bar keys render as
`identity@bar_start` (daily: `identity@YYYY-MM-DD`). Daily value comparison excludes the labeling convention
(`bar_start`/`bar_end`/`source_label`), so same-day rows with different
source label timestamps and identical values dedup, and any real value
difference on the same trading date is a conflict. Daily series rows
(continuous candidates) are valid with NULL `instrument_id`; nothing derives
a missing day from a timestamp. Sort order is key order.

## 4. Catalog (`research_store.catalog`)

SQLite at `<root>/catalog.sqlite`: WAL, `foreign_keys=ON`, `synchronous=FULL`,
`busy_timeout=5000`, `user_version=1`. Tables: `assets`, `datasets`, `batches`,
`revisions`, `partition_heads`, `snapshots`, `quality_issues`,
`recording_sessions` (schema only; journal/aggregation is a later WP). Per-bar
rows are NEVER stored here. `Catalog` exposes typed helpers used by the modules
below plus `execute`/`transaction()`; consumers outside core should prefer the
higher-level APIs.

## 5. Import / publish boundary (OpenCode importers call THIS)

Importer flow: `inspect_asset` → build `ImportRequest` →
`import_asset(store, request)`. `import_asset` is the core entry point that
drives an importer-supplied **streaming** batch iterator through staging,
validation, content-hash object write, and the CAS publish. Importers never
write catalog rows or object files directly.

```python
@dataclass(frozen=True)
class AssetRef:                       # registered source asset (fast discovery may carry hash=None)
    asset_id: str
    origin: str                       # absolute path
    format: str                       # "sqlite" | "gzip_csv" | "tar_zst_csv" | "tar_zst_parquet" | ...
    size: int
    sha256: str | None                # None => unverified fast discovery; formal import hashes input

@dataclass(frozen=True)
class ImportRequest:
    asset: AssetRef
    spec: SemanticSpec
    adapter: str                      # importer name+version, e.g. "rq_etf/0.1"
    config: Mapping[str, str]         # normalized config affecting transform
    partitions: tuple[str, ...]       # partition keys this request publishes
    idempotency_key: str | None       # default: derived, see below

def default_idempotency_key(req: ImportRequest) -> str
    # sha256(asset content hash + member/table/range from config + dataset_id
    #          + adapter + config + mapping versions)  — audit timestamps excluded

@dataclass(frozen=True)
class ImportReceipt:
    batch_id: str
    dataset_id: str
    state: BatchState                 # PUBLISHED | PREPARED | FAILED | CONFLICTED
    partitions: tuple[PartitionReceipt, ...]
    input_rows: int
    accepted_rows: int
    duplicate_rows: int
    quarantined_rows: int
    parse_failures: int
    conflicts: tuple[ConflictRecord, ...]
    request: ImportRequest            # input configuration paths preserved verbatim

def import_asset(
    store: Store,
    request: ImportRequest,
    rows: Callable[[str], Iterator[pa.RecordBatch]],  # partition -> batch stream, BARS/TICKS schema
) -> ImportReceipt
```

Partition strings are opaque to the core; OpenCode owns the deterministic
mapping and must follow the plan's canonical scheme (daily `"{year}"`,
equity/ETF minute `"{exchange}/{year-month}/{bucket16}"`, futures minute
`"{product}/{year-month}"`). SSQuant `table x month` is an INPUT work unit for
resumability, not a permanent physical partition scheme.

`import_asset` also accepts an optional `source_counts: Mapping[str, int]`
keyword for importer-known `input_rows`/`parse_failures` overrides.

Publish semantics per partition (see `research_store.revisions`):

- Batch row created `running`; replay of the same `idempotency_key` returns the
  prior receipt without re-publishing (idempotency).
- Streams are written to `staging/` as Zstandard Parquet, validated (schema,
  non-finite rejection, key uniqueness+order, row counts), content-hashed
  (`objects/<2-hex>/<sha256>.parquet`), fsynced, atomically renamed on the same
  volume, then ONE `BEGIN IMMEDIATE` transaction compares the recorded base head,
  inserts the revision + manifest hash, updates `partition_heads`, and marks the
  batch `published`. A changed base raises `HeadConflictError` — the loser
  rebuilds, no writer ever overwrites another's head. No conversion work happens
  while the catalog transaction is held.
- Each revision's manifest (`manifests/revisions/rev-<id>.json`) lists the
  COMPLETE active file set for its partition with per-file sha256/rows — readers
  never glob directories.
- Same key / same values dedups (audit timestamps ignored, source counts
  preserved). Same key / different values => `CONFLICTED`: a conflict sidecar
  (`existing` vs `candidate` + evidence, including `gap_ns` — the disputed
  record's real normalized bounds) and a `quality_issues` row are written,
  the candidate file set is NOT published for those keys, and unaffected new rows
  may still publish. No last-wins, ever.
- `ConflictRecord` (core fix03 F1) exposes `gap_ns: tuple[int, int] | None` —
  the same real bounds as the sidecar: `[bar_start, bar_end)` for bars,
  `[ts, ts+1)` for ticks, taken from the existing row at detection. It is
  populated on the live receipt, on idempotent replays, and on receipts
  rebuilt by `recover()`. Callers resolve→QUARANTINE and build the explicit
  allowance as `KnownGap(dataset_id, conflict.gap_ns[0], conflict.gap_ns[1],
  reason)` from public receipt fields alone — no sidecar parsing, no assumed
  1ns width.
- `resolve_conflict(store, dataset_id, partition, conflict_id,
  resolution=EXISTING|CANDIDATE|QUARANTINE, reason) -> RevisionReceipt` creates a
  NEW revision; old snapshots are never altered. QUARANTINE leaves visible gaps —
  no zero/forward fill. Readers see a quarantined key as a `gap_ns` interval
  (real bounds, not a natural-date derivation) and raise
  `CoverageGapError` unless the snapshot explicitly allows it.

## 6. Recovery (`research_store.revisions`)

```python
@dataclass(frozen=True)
class RecoveryReport:
    root: Path
    batches: tuple[BatchRecovery, ...]   # per batch_id: prior state, action taken, receipt|error
    orphan_files: tuple[Path, ...]       # reported, NEVER auto-deleted

def recover(store: Store, batch_id: str | None = None) -> RecoveryReport
```

- `prepared` batches: validate staged/published files (existence + sha256 +
  manifest), re-check base head, then either complete the atomic publish or mark
  `failed` with evidence. A missing/tampered published object FAILS the recovery
  item loudly — no fallback, no silent skip.
- `failed` batches (core fix03 F2): a partially published multi-partition
  batch keeps its durable prepared anchor; the general sweep resumes it
  through the same CAS-verified path — partitions whose revision is already
  in the catalog are skipped (never re-published, never duplicated), and a
  head that moved since the recorded base raises `HeadConflictError` instead
  of clobbering. A `failed` batch with no usable anchor is reported with a
  loud per-batch error naming its `idempotency_key` for retry; it is never
  invisible and never reported as published. Repeating recovery and the
  same-key retry converge on the same durable result.
- `published` batches return their prior receipt (recover is idempotent).
- Orphan staging files are listed in `orphan_files` only.

**IMPLEMENTED (WP08/WP09 + recording02I; see RECORDING_INTERFACES.md for the
binding recording contract):**

```python
def recover_session(store: Store, session_id: str, *, create_successor: bool = True,
                    successor_source_spec: str | None = None,
                    successor_calendar_spec: str | None = None) -> SessionRecoveryReport
def seal(store: Store, request: SealRequest) -> SealReceipt
```

The `SessionRecoveryReport`, `SealRequest`, and `SealReceipt` dataclasses in
`models.py` are the typed results; recording semantics (recovery marking,
sealing idempotency/range safety, revised explicit asset/unit semantics) are
owned by `RECORDING_INTERFACES.md`. The top-level `recover_session` wrapper
is reconciled with the documented successor kwargs by the recording-core
owner (tracked in `.coordination/recorder03d-opencode-core-requests.md`).

## 7. Snapshots (`research_store.snapshots`)

```python
@dataclass(frozen=True)
class SnapshotRequest:
    selections: tuple[Selection, ...]        # (dataset_id, partition) pairs; partition "*" = all
    required_fields: tuple[str, ...]         # e.g. ("open","high","low","close","volume")
    allow_known_gaps: tuple[KnownGap, ...]   # explicit (dataset_id, start, end, reason); default ()
    conflict_policy: ConflictPolicy = ConflictPolicy.ERROR   # default: unresolved conflicts fail freeze

@dataclass(frozen=True)
class SnapshotRef:
    snapshot_id: str                 # "snap-" + sha256 of canonical manifest
    manifest_path: Path
    datasets: tuple[str, ...]
    created_at: str

def freeze(store: Store, request: SnapshotRequest) -> SnapshotRef
def open_snapshot(store: Store, snapshot_id: str) -> SnapshotReader
```

- `freeze` captures ALL selected partition heads, revision manifests, and
  versioned quality decisions in ONE short SQLite read transaction (N3); the
  immutable manifest JSON is written afterward from that capture. No independent
  per-dataset head reads. New heads/issues never change an existing snapshot.
- Default-qualified exclusions (qualified-fix04/05): `freeze` also evaluates the
  default-qualified policy over the selected published rows (all deterministic
  repaired keys, per `quality.DEFAULT_EXCLUSION_FLAGS` — the full repaired-key
  set, not merely the 118/119 disputed subsets) and captures the result in the
  manifest as `default_qualified_exclusions` (dataset_id, partition,
  instrument, real `[start_ns, end_ns)` bounds, source_label, flags). The
  Parquet scan runs AFTER the transaction exits, over immutable file references
  (partition, path, sha256) captured inside it — never by rereading mutable
  current heads (qualified-fix05 F2). Snapshots frozen before this capture
  (manifest format 1, no key) are recognizably LEGACY UNQUALIFIED (format 2 is
  written now): default qualified reads refuse them and observational access
  keeps its prior meaning — old bytes are never rewritten.
- Default `conflict_policy=ERROR`: any unresolved conflict overlapping a
  selection fails the freeze. Known gaps require explicit `allow_known_gaps`
  entries with recorded reasons.
- Ambiguous selection (unknown dataset, empty resolution) is an error, never a
  latest-source guess.

## 8. Reader (`research_store.reader`)

```python
class SnapshotReader:
    snapshot_id: str
    def bars(
        self,
        dataset_id: str,
        instruments: Sequence[str] | None = None,   # instrument_id or series_id values
        start: datetime | None = None,              # aware; converted to UTC ns
        end: datetime | None = None,
        required_fields: Sequence[str] = ("open", "high", "low", "close", "volume"),
        allow_missing_auxiliary: bool = False,
        include_default_excluded: bool = False,     # explicit observational mode
    ) -> Iterator[pa.RecordBatch]: ...              # half-open [start, end), key-sorted stream
    def ticks(self, dataset_id: str, instruments=None, start=None, end=None,
              required_fields: Sequence[str] = (),
              include_default_excluded: bool = False) -> Iterator[pa.RecordBatch]: ...
    def default_qualified_exclusions(self, dataset_id: str) -> list[dict]: ...
    def default_qualified_status(self, dataset_id: str) -> str: ...
    def close(self) -> None
```

- Reads EXACTLY the files listed in the snapshot manifest — never globs current
  directories. Each file's sha256 is verified on first touch (cached);
  missing/tampered => `IntegrityError`.
- DEFAULT QUALIFIED READS (qualified-fix04/05): queries intersecting a captured
  default-qualified exclusion raise `CoverageGapError` unless the snapshot
  explicitly allowed the gap via `allow_known_gaps`; allowed exclusions are
  filtered out of the returned rows (the allowance permits the missing
  interval, never the rejected row — no filler). This is the enforcement of
  the full repaired-key policy (all deterministic repaired keys, including
  repairs equal to their upstream candidates); the quarantine-gap contract
  above behaves unchanged. Snapshots that predate the policy capture
  (manifest format 1, no `default_qualified_exclusions` key) are LEGACY
  UNQUALIFIED: default qualified reads refuse them with an explicit
  `CoverageGapError` (never silently presenting repaired rows as qualified);
  `default_qualified_status(dataset_id)` returns the typed status
  `"qualified"` vs `"legacy_unqualified"`.
- `include_default_excluded=True` is the explicit OBSERVATIONAL mode: every
  pinned row is returned (excluded rows included, with their `field_quality`
  provenance) and no default-qualified refusal applies. It must never feed
  qualified backtest consumers; the native bridges never set it for loads.
  Store-level source-label inspection (`coverage.fetch_by_source_labels`)
  remains the inspection path for original source labels.
- Deterministic ordering: bars stream ordered by `(instrument-or-series,
  bar_start)`; ticks ordered by canonical event identity
  `(instrument-or-series, session_id, seq)` (core fix03 F3) — never by
  unstable file/query order. Tick `start`/`end` still filter on `ts`.
- Streaming: DuckDB (`threads=4`, `memory_limit='8GB'`, spill to store
  `staging/duckdb`) over the manifest file list, yielded as RecordBatches
  (~65k rows). No full-history pandas/polars materialization. One DuckDB
  instance per `SnapshotReader`; not shared.
- `[start, end)` half-open. Consumers with inclusive-end contracts (native
  `Database`, `ResearchAlphaLab.load_bar_data/load_bar_df`) must convert — see
  WP07/B2; the core does NOT pad ranges.
- Error taxonomy (all subclass `StoreError`): `UnknownDatasetError`,
  `UnavailableFieldError` (required field absent from schema / not produced by
  this dataset), `MissingFieldDataError` (NULLs in `required_fields`;
  `allow_missing_auxiliary=True` downgrades auxiliary NULLs to passthrough with
  NaN preserved), `CoverageGapError` (request intersects a recorded gap that the
  snapshot did not explicitly allow), `IntegrityError`. Plain absence of rows is
  NOT an error — the stream is simply empty (distinguish via
  `coverage()`/`quality()` from OpenCode's modules).

## 9. Errors (`research_store.models`)

```
StoreError
├── StoreNotFoundError / StoreExistsError
├── CatalogError
├── IdempotencyReplay          (informational, carried on receipt)
├── HeadConflictError          (CAS lost; rebuild and retry)
├── ConflictError              (same-key different-values detected)
├── UnresolvedConflictError    (freeze with default policy)
├── IntegrityError             (missing/tampered object or manifest)
├── CoverageGapError
├── UnavailableFieldError / MissingFieldDataError / UnknownDatasetError
├── ReadOnlyError / UnsupportedCapabilityError   (for later vnpy bridges)
└── PendingCapabilityError     (typed stubs for later WPs)
```

## 10. Non-goals for this file

CLI verbs, `importers/`, `quality.py`, `coverage.py`, and all `vnpy_researchstore`
bridges are OpenCode/later WP scope. The core guarantees above are the contract
those modules build against.
