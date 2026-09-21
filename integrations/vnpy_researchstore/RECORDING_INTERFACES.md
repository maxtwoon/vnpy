# RECORDING_INTERFACES.md — Recording Journal Public API Contract

This document is the binding contract for the recording journal subsystem
(WP08/WP09, revised by recording02I). It is owned by the
journal/aggregation/sealing agent and is separate from `INTERFACES.md`
(qualified05-owned) and `NATIVE_INTERFACES.md` (native/CLI-owned).

recording02I revision (2026-09-17) closes the four accepted 02H findings:
F1 tail-bar truthfulness, F2 seal identity vs idempotency separation, F3
admission-lateness preservation, F4 explicit validated asset/source/unit
semantics. recording02IA revision (2026-09-17, same session) corrects the
calendar contract: a timezone-only calendar_spec is display/UTC-conversion
only and NEVER a trading calendar; trading_date comes only from explicit
source payload evidence; ticks without an event time are excluded from
publication (never fabricated as epoch zero); genuine numeric zeros are
preserved verbatim.

All types are importable from `research_store` (the package `__init__.py`)
unless noted as submodule-only.

---

## 1. Journal Session (durable recording)

### Creation

```python
from research_store.journal import create_session

session = create_session(
    store: Store,
    source_spec: str,          # "<kind>:<name>[@<version>]" or bare "<name>"
    calendar_spec: str,        # "" | IANA tz name | "tz:<IANA tz name>"
    *,
    session_id: str | None = None,               # auto-generated if omitted
    predecessor_session_id: str | None = None,   # link to a prior session
) -> JournalSession
```

Creation is deliberately permissive: raw capture must never lose data.
Format VALIDATION applies at the publication boundary (`plan_seal`/`seal`,
see §4). Recorder/CLI configs should still emit conformant strings; see the
grammar in §4.3 and the migration note for `recorder_simulated.json`-style
session calendar names (`"CN.FUTURES.DAY"` is NOT resolvable and is refused
at seal time with an explicit error).

### Open (exclusive)

```python
from research_store.journal import open_session

session = open_session(
    store: Store,
    session_id: str,
    *,
    readonly: bool = False,
) -> JournalSession
```

- `readonly=False` (default): refuses if the session is not OPEN on disk
  (CLOSED, UNCLEAN_END, or ERROR). Starts the writer thread.
- `readonly=True`: accepts any disk state (OPEN, CLOSED, UNCLEAN_END).
  No writer thread is started. `admit()` and `close_at_cutoff()` raise
  `JournalClosedError`. Use for sealing, recovery, aggregation, audit.

### Admission

```python
receipt: AdmissionReceipt = session.admit(
    event: JournalEvent,
    *,
    timeout: float = 0.0,   # seconds; 0 = non-blocking
)
```

`JournalEvent` fields:

| Field | Type | Meaning |
|-------|------|---------|
| `kind` | `str` | Event kind, e.g. `"tick"`, `"trade"`, `"bar"` |
| `instrument` | `str` | Real instrument identity, e.g. `"IF2403.CFFEX"` |
| `event_ts_ns` | `int \| None` | Original event time, full ns precision |
| `source_event_id` | `str \| None` | Gateway/source event id, unmapped |
| `payload` | `Mapping[str, Any]` | Full original payload (deep-copied) |

`AdmissionReceipt` fields: `accepted: bool`, `assigned_seq: int | None`,
`reason: str | None`.

The journal durably records BOTH `event_ts_ns` (source event time) and
`received_ts_ns` (receipt time, taken at commit). `received_ts_ns` is
accurate receipt metadata only — it is never compared against
`event_ts_ns` (different clocks) and never used to fabricate event times.

### Status

```python
status: JournalStatus = session.status()
```

`JournalStatus` fields:

| Field | Type | Meaning |
|-------|------|---------|
| `session_id` | `str` | |
| `state` | `SessionState` | `OPEN`, `CLOSED`, `UNCLEAN_END`, `ERROR` |
| `accepted_seq` | `int` | Last assigned ingest sequence |
| `committed_seq` | `int` | Durable committed watermark |
| `backlog` | `int` | Accepted but not yet committed |
| `rejected` | `int` | |
| `errors` | `int` | |
| `last_error` | `str \| None` | Detail of the most recent writer/admission error |

### Close

```python
result: CloseResult = session.close_at_cutoff(
    *, timeout: float = DEFAULT_CLOSE_TIMEOUT_S,
)
result: CloseResult = session.retry_close(
    *, timeout: float = DEFAULT_CLOSE_TIMEOUT_S,
)
```

`CloseResult` fields: `session_id`, `state`, `accepted_seq`,
`committed_seq`, `committed_through_cutoff: bool`, `detail: str`.

`state` is `CLOSED` only when the committed watermark reached the exact
accepted cutoff. A bounded failure never reports a false `CLOSED`.

**F1 truthfulness:** `CLOSED` proves ONLY that the local accepted cutoff
drained. It is NOT proof that the final minute interval completed. Tail
bars without independent completion evidence stay `PARTIAL` (§3) and are
excluded from canonical/backtest publication (§4). Committed raw ticks
remain fully available.

### Interval completion evidence (F1)

```python
session.record_completion_boundary_ns(boundary_ns: int) -> None
value: str | None = session.read_meta(key: str)
```

- `record_completion_boundary_ns` durably asserts: market data through this
  event-time ns boundary has been observed for this session (e.g. the
  exchange session close from a calendar the caller vouches for). It is
  explicit evidence, never a wall-clock or natural-date guess. Refuses on
  readonly opens and torn-down sessions; requires a positive int.
- `read_meta` is the public read accessor for durable `session_meta`
  values (aggregation/sealing use it; no private connection access).

Completion evidence for a tail bar means EITHER a later committed event
whose `event_ts_ns >= bar_end_ns`, OR a recorded completion boundary
`>= bar_end_ns`. Session state (OPEN/CLOSED) is never itself evidence.

Calendar truthfulness (recording02IA): a timezone-only ``calendar_spec``
(IANA name or ``tz:IANA``) establishes display timezone / normalised UTC
conversion ONLY — never a trading day, holiday, or session applicability.
``trading_date`` is set exclusively from explicit source payload evidence
(``payload["trading_date"]``, ISO ``YYYY-MM-DD`` — e.g. a gateway
trading-day field); without it, trading_date stays NULL with the explicit
``trading_date_unknown`` status and a field_quality note. An unproven
Friday-night date is never inferred. ``out_of_session`` is RESERVED for
positive session evidence and is never asserted from missing calendar data
(unknown ≠ false). No explicit calendar-mapping form exists in v1
(documented decision: no calendar service, no next-day guessing); a
mapping form may be added later only with versioned, scoped evidence.

### Unclean end (crash marker)

```python
session.mark_unclean_end() -> None
```

Durable `UNCLEAN_END` while holding the session lock. Production crash path;
tests may also call this directly.

### Replay

```python
events: Iterator[CommittedEvent] = session.replay_committed()
```

Yields committed events in `(event_ts_ns, seq)` order. Only committed rows;
uncommitted rows are never yielded. `CommittedEvent` carries `seq`, `kind`,
`instrument`, `event_ts_ns`, `received_ts_ns`, `source_event_id`,
`payload`, `payload_sha256` — original ingest identity and receipt metadata
survive sealing/replay/recovery.

### Close handle

```python
session.close() -> None
```

Releases the exclusive lock and stops the writer thread. Idempotent.

---

## 2. Session Recovery

The canonical top-level export forwards every documented typed option
(recording02I fix of the 03D-reported `create_successor` rejection):

```python
from research_store import recover_session, SessionRecoveryError

report: SessionRecoveryReport = recover_session(
    store: Store,
    session_id: str,
    *,
    create_successor: bool = True,
    successor_source_spec: str | None = None,
    successor_calendar_spec: str | None = None,
) -> SessionRecoveryReport
```

(`research_store.session_recovery.recover_session` is the real
implementation; `research_store.revisions.recover_session` and the
top-level export forward faithfully to it.)

- Replays COMMITTED events only to report committed sequences.
- Marks the unclosed old session `UNCLEAN_END`; already-closed sessions are
  left untouched.
- With `create_successor=True` (default), opens a new journal session
  linked via `predecessor_session_id`, inheriting the stored specs unless
  overridden by `successor_source_spec` / `successor_calendar_spec`.
- No successor is created for already-CLOSED sessions.

`SessionRecoveryReport` fields (actual — corrected here; earlier revisions
of this file listed `prior_state`/`committed_seq`/`committed_events`, which
never existed):

| Field | Type | Meaning |
|-------|------|---------|
| `session_id` | `str` | The recovered (old) session |
| `prior_status` | `str` | Disk state before recovery |
| `replayed_committed_seq` | `tuple[int, ...]` | Committed sequences replayed |
| `predecessor_session_id` | `str \| None` | This session's predecessor link |
| `detail` | `str` | Human-readable outcome |
| `successor_session_id` | `str \| None` | New session id (if created) |
| `last_error` | `str \| None` | Error detail if successor creation failed |

Raises `SessionRecoveryError` for unknown sessions or unrecoverable states.

---

## 3. Aggregation

```python
from research_store import (
    aggregate_session,
    AggregatedSession,
    AggregatedBar,
    AggregationError,       # submodule: research_store.aggregation
)

result: AggregatedSession = aggregate_session(
    store: Store,
    session_id: str,
    *,
    final: bool = True,
)
```

- Opens the session `readonly=True`.
- Reads only committed events in `(event_ts_ns, seq)` order.
- Aggregates into minute bars keyed by `(instrument, minute_start)`.

`AggregatedSession` fields:

| Field | Type | Meaning |
|-------|------|---------|
| `session_id` | `str` | |
| `source_spec` | `str` | |
| `calendar_spec` | `str` | |
| `committed_seq_end` | `int` | Watermark used |
| `bars` | `tuple[AggregatedBar, ...]` | All aggregated bars |
| `provisional_bars` | `tuple[AggregatedBar, ...]` | Tail bars without completion evidence (and any OPEN-session tail) |
| `skipped_events` | `int` | Committed events with no usable payload |
| `statuses` | `tuple[str, ...]` | Union of bar statuses |

`AggregatedBar` fields:

| Field | Type | Meaning |
|-------|------|---------|
| `instrument` | `str` | |
| `bar_start_ns` | `int` | Minute boundary, ns |
| `bar_end_ns` | `int` | Exclusive end, ns |
| `trading_date` | `date \| None` | Source payload evidence ONLY (recording02IA); NULL + `trading_date_unknown` otherwise |
| `open` / `high` / `low` / `close` | `float \| None` | |
| `volume` | `float \| None` | Real aggregated delta; None if unknown |
| `turnover` | `float \| None` | |
| `first_seq` / `last_seq` | `int` | Session lineage |
| `event_count` | `int` | |
| `statuses` | `tuple[str, ...]` | See status vocabulary below |
| `source_kind` | `str` | Observed event kind(s) |
| `completeness` | `str` | |
| `field_quality` | `str \| None` | JSON notes |

### F1 provisional contract (revised)

`bars` always contains every aggregated bar. A tail bar is `PARTIAL` and
duplicated in `provisional_bars` when its minute interval is NOT
independently evidenced complete. Evidence (§1) is a later committed event
with `event_ts_ns >= bar_end_ns`, or a recorded completion boundary
`>= bar_end_ns`. An OPEN session's tail is always provisional (it can still
gain data). `CLOSED` alone NEVER clears `PARTIAL` — the previous behavior
("CLOSED clears PARTIAL") was an accepted 02H defect and is corrected;
tests asserting it were corrected too. Mid-session bars carry implicit
completion evidence (a later same-instrument event in a newer minute) and
are never flagged by the tail rule.

### F3 late-admission status (revised)

Admission lateness is detected BEFORE chronological replay normalizes it:
events are walked in original committed ingest (`seq`) order against the
running maximum source `event_ts_ns`. An event whose `event_ts_ns` is
earlier than that running maximum at its ingest position is LATE
(`seq1/T0, seq2/T10, seq3/T1` → replay order `T0,T1,T10` with `LATE`
retained on the bar containing seq3). The status attaches to the bar
CONTAINING the late event whether it creates or joins that bar.
`received_ts_ns` is preserved as receipt metadata and is never compared
against source event time.

### Status vocabulary

| Status | Meaning |
|--------|---------|
| `first_baseline` | First event for instrument; delta volume unknown |
| `reset` | Counter decreased vs. prior; delta unknown |
| `gap` | Time gap before this bar (> one minute since prior event) |
| `reconnect` | Reserved for source-reconnect evidence |
| `late` | Admitted after a later-source-time event (detected from ingest order, F3) |
| `partial` | Bar interval not independently evidenced complete (F1) |
| `trading_date_unknown` | No source trading-day evidence; timezone-only calendar_spec proves nothing (recording02IA) |
| `out_of_session` | RESERVED: requires positive session evidence; not asserted from missing calendar data |
| `zero_volume` | Bar aggregated zero real volume (or volume unknown) |
| `negative_delta` | Raw delta was negative (not clamped; reported with status) |

### Delta semantics

- `_delta()` returns `(0.0, None)` when current counter is missing but a
  baseline exists (quote tick = zero delta).
- Returns `(None, first_baseline)` when no baseline exists.
- Returns `(None, reset)` on counter decrease.
- Never negative-clamps without recording a status.
- Missing source trading_date evidence never becomes a natural-date or
  timezone-derived inference: `trading_date` stays NULL with the explicit
  `trading_date_unknown` status and a field_quality note
  (recording02IA).

---

## 4. Sealing

### 4.1 API

```python
from research_store import (
    seal, plan_seal,
    SealRequest, SealReceipt, SealPlan, SealError,
    seal_idempotency_key,   # submodule: research_store.sealing
)

plan: SealPlan = plan_seal(store: Store, request: SealRequest) -> SealPlan
receipt: SealReceipt = seal(store: Store, request: SealRequest) -> SealReceipt
```

`SealRequest` fields:

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `session_id` | `str` | — | Journal session to seal |
| `committed_seq_start` | `int` | — | Inclusive start |
| `committed_seq_end` | `int` | — | Inclusive end |
| `transform_version` | `str` | — | Aggregation transform version |
| `source_spec` | `str` | — | Must equal the session's stored source_spec |
| `calendar_spec` | `str` | — | Must resolve to the session's stored calendar (or both empty) |
| `asset_class` | `AssetClass` | `OTHER` | Declared asset semantics (F4) |
| `volume_unit` | `str` | `"unknown"` | Declared volume unit (F4) |
| `turnover_unit` | `str` | `"unknown"` | Declared turnover unit (F4) |

The F4 defaults are the HONEST UNQUALIFIED combination: an untyped seal
publishes `other`/`unknown` semantics visibly; it NEVER defaults to
FUTURES. A typed `source_spec` (below) constrains `asset_class` further.

`SealPlan` fields: `session_id`, `committed_seq_start`,
`committed_seq_end`, `committed_watermark`, `event_count`,
`idempotency_key`.

`SealReceipt` fields:

| Field | Type | Meaning |
|-------|------|---------|
| `session_id` | `str` | |
| `seal_id` | `str` | Ticks batch id |
| `partitions` | `tuple[PartitionReceipt, ...]` | Ticks + bars partitions |
| `idempotent_replay` | `bool` | True if this was a no-op replay |
| `dataset_id` | `str \| None` | Ticks dataset id |
| `input_events` | `int` | Events read from journal |
| `accepted_rows` | `int` | Total rows published (ticks + bars) |
| `detail` | `str` | Human-readable summary |

### 4.2 Identity vs idempotency (F2, revised)

- RUNTIME IDEMPOTENCY KEY (`seal_idempotency_key(request, record_kind)`)
  covers session_id, committed range, transform version, source_spec,
  calendar_spec, asset_class, units, record_kind, and adapter version. An
  identical repeat seal returns the same receipt with
  `idempotent_replay=True`.
- SEMANTIC DATASET IDENTITY (`_spec()` → `SemanticSpec.canonical()`)
  covers source (`journal:<source_spec>`), asset_class, record_kind,
  interval, adjustment, series rule (`seal-<transform_version>`),
  timezone, time label, units, origin method, schema version — and
  deliberately EXCLUDES the session id and the committed sequence range.
  The range is runtime provenance (idempotency key + row metadata), never
  a `rule_version` discriminator. This corrects the accepted 02H defect
  where the range was smuggled into `rule_version`.

Consequences (all proven by tests):

- Range extension (seal `[1,3]`, then `[1,6]`) extends the SAME dataset:
  the extension publishes a NEW partition revision whose
  `base_revision`/parent is the previous head, already-sealed ticks dedup
  (`duplicate_rows`), and the effective partition manifest is complete
  (reader queries return the full committed range). Real lineage, not
  disconnected hashes.
- Sealing a subset after the full range dedups to a no-content chained
  revision on the same dataset.
- A changed `transform_version` (actual changed semantics) produces a
  genuinely NEW dataset.
- Sessions with otherwise-identical semantics share the semantic dataset
  (session provenance lives in tick rows/partitions), never forked
  datasets per session/range.
- A changed previously sealed bar (late correction) flows through the
  existing explicit conflict / new-revision machinery — never silent
  last-wins; old snapshots are unchanged.
- A partial publication failure never marks the session fully sealed: the
  journal seal record is written only after both publications return, and
  a mid-seal crash resumes through the standard import recovery sweep.

### 4.3 Source/calendar spec grammar and validation (F4)

Validation happens in `plan_seal`/`seal` (publication boundary) and is
also available directly:

```python
from research_store.sealing import (
    validate_source_spec, SourceSemantics,
    validate_calendar_spec,
)
```

`source_spec` (v1):

```
source_spec := <name> | <kind> ":" <name> [ "@" <version> ]
kind        := futures | equity | etf | index | option | convertible | unknown
name/version: [A-Za-z0-9._-]{1,64}
```

- A declared kind pins the ONLY accepted `SealRequest.asset_class`
  (`futures` → `FUTURES`, `equity` → `EQUITY`, `etf` → `ETF`, ...). A
  mismatch is an explicit `SealError` (stock volume can never be tagged
  as contracts).
- A bare name (no colon) means kind `unknown`: any explicitly declared
  asset class is accepted (units still validated), and the honest
  OTHER/unknown default is fine.
- `request.source_spec` must EQUAL the session's stored source_spec.

Known units per asset class (others are `SealError`):

| Asset class | volume_unit | turnover_unit |
|-------------|-------------|----------------|
| futures | contracts, lots, unknown | currency, CNY, USD, unknown |
| equity | shares, unknown | currency, CNY, USD, unknown |
| etf | shares, units, unknown | currency, CNY, USD, unknown |
| index | points, unknown | currency, CNY, USD, unknown |
| option | contracts, unknown | currency, CNY, USD, unknown |
| convertible | bonds, unknown | currency, CNY, USD, unknown |
| other | unknown | unknown |

`calendar_spec` (v1):

```
calendar_spec := ""                     # no calendar evidence (honest)
               | "tz:" <IANA zone>      # timezone-only (display/UTC conversion)
               | <IANA zone>            # v1 shorthand for "tz:..."
```

- `""` → no evidence; bars/ticks carry NULL `trading_date` with the
  explicit `trading_date_unknown` status/note; sealing proceeds honestly.
- A resolvable IANA zone (or `tz:` form) establishes the DISPLAY timezone
  / normalised UTC conversion ONLY (recording02IA). It NEVER establishes a
  trading day, holiday, or session applicability — a Friday-night event
  keeps `trading_date = NULL` with explicit uncertainty even under
  `Asia/Shanghai`. Trading-day evidence comes only from the source
  payload (`payload["trading_date"]`, ISO `YYYY-MM-DD`); provenance is
  recorded in `field_quality` ("source payload evidence"). Conflicting
  source dates within one bar → NULL + explicit conflict note; an
  invalid claim is ignored with a note and marks the TICK row `partial`.
- No explicit calendar-mapping form exists in v1 (documented decision:
  no calendar service, no next-day guessing).
- Anything else (e.g. `"CN.FUTURES.DAY"` from older recorder configs) is
  an explicit `SealError` naming the expected format — never guessed into
  futures `trading_day` values. Coordinator note (2026-09-17): configs
  carrying such strings (recorder/CLI side, 03D-owned) must migrate to
  the grammar above; this core returns the exact refusal rather than
  silently adjusting another owner's config.
- `request.calendar_spec` must resolve to the same zone as the session's
  stored calendar_spec (or both be empty).

Concrete test example: `tests/test_sealing.py::test_f4_futures_and_etf_sources_have_distinct_identity`
(FUTURES/contracts vs ETF/shares and EQUITY/shares sessions seal to
distinct datasets), `...::test_f4_units_not_valid_for_asset_class_refused`,
and `...::test_f4_calendar_specs_at_seal`.

### 4.4 F1 exclusion from canonical publication

Bars flagged `partial` (no completion evidence, §3) are EXCLUDED from the
sealed bars publication; only evidenced-complete minutes become
canonical/backtest-ready bars. Committed raw ticks are ALWAYS published
regardless of bar completeness. `SealReceipt.accepted_rows` therefore
counts ticks + evidenced bars only. Field-level `trading_date_unknown`
does NOT degrade row completeness or exclude anything (no blanket
rejection of recording without a full calendar).

### 4.7 Tick materialization truthfulness (recording02IA)

- A committed tick WITHOUT `event_ts_ns` cannot be published honestly
  (canonical `ts` is NOT NULL). It is EXCLUDED from the seal with an
  explicit count in `SealReceipt.detail` ("excluded N tick(s) with
  unknown event time"); the raw row stays preserved in the journal. No
  tick is ever fabricated as epoch zero (`ts=0`).
- Field fallbacks preserve genuine numeric zeros: `last_price` falls back
  to `payload["price"]` only via explicit `is None` checks (a real
  `last_price = 0.0` is never replaced); same for `turnover`/`amount`.
- `trading_date`: source payload evidence only, with provenance in
  `field_quality`; absent → NULL + explicit unknown note (row stays
  `complete`); an invalid source claim → NULL + note + row `partial`.
- Aggregated bars follow the same evidence rule and never derive dates
  from the display timezone.

### 4.5 Range safety and session state

`plan_seal` refuses (typed `SealError`): unknown session; empty range;
range exceeding the committed watermark; unsupported/inconsistent
asset/unit/source/calendar semantics. `seal` opens the session
`readonly=True`; ERROR-state sessions are refused; CLOSED and
UNCLEAN_END sessions are accepted.

### 4.6 Crash recovery

A durable seal record (batch ids + idempotency keys + request) is written
to the journal's `session_meta` (`last_seal` / `seals`) after both
publications return; a crash before that leaves the standard import
recovery anchor in the catalog so `recover()` converges a repeat seal
without duplicating ticks.

---

## 5. Retention

```python
from research_store import (
    evaluate_retention, apply_retention,
    RetentionDecision,
    RetentionError,         # submodule: research_store.retention
)

decision: RetentionDecision = evaluate_retention(store: Store, session_id: str)
decision: RetentionDecision = apply_retention(store: Store, session_id: str)
```

Eligibility criteria (ALL must hold):

1. Session has only journal-owned files (`.sqlite`, `.sqlite-wal`,
   `.sqlite-shm`, `.lock`) inside `<store>/journals/`.
2. At least one verified complete seal exists (all seal batches PUBLISHED
   in catalog; a conflicted/partial publication is NOT verified).
3. Newest seal is at least 14 days old.
4. No live process holds the session lock (msvcrt `LK_NBLCK` probe).

CLOSED-without-seal sessions are NOT eligible. All target paths are
resolved and validated to stay inside `<store>/journals/` — path
traversal, junction, and symlink escapes are refused
(`tests/test_retention.py` covers traversal always; the junction/symlink
case is capability-honest: if the host denies link creation the test
records a precise `NOT_RUN` skip, never a fabricated PASS).

`RetentionDecision` fields:

| Field | Type | Meaning |
|-------|------|---------|
| `session_id` | `str` | |
| `eligible` | `bool` | |
| `reason` | `str` | Human-readable explanation |
| `paths` | `tuple[Path, ...]` | Journal files that would be removed |
| `sealed_at` | `str \| None` | ISO timestamp of newest verified seal |

`apply_retention` evaluates then deletes eligible files. Canonical
objects/snapshots/raw captures are never touched.

---

## 6. Catalog — recording_sessions helpers

```python
# All on the Catalog class (store.catalog or equivalent accessor).

catalog.upsert_recording_session(
    session_id: str,
    source_spec: str,
    calendar_spec: str,
    journal_path: str,
    status: str,
    predecessor_session_id: str | None,
    created_at: str,        # ISO timestamp
    updated_at: str,        # ISO timestamp
) -> None

row: sqlite3.Row | None = catalog.get_recording_session(session_id: str)

catalog.update_recording_session_status(
    session_id: str,
    status: str,
    updated_at: str,
    sealed_output_json: str | None = None,
) -> None

rows: list[sqlite3.Row] = catalog.recording_sessions_by_status(status: str)
```

---

## 7. Typed gap fills (WP09 / recording02I)

| Dataclass | Field | Type | Default |
|-----------|-------|------|---------|
| `JournalStatus` | `last_error` | `str \| None` | `None` |
| `SessionRecoveryReport` | `successor_session_id` | `str \| None` | `None` |
| `SessionRecoveryReport` | `last_error` | `str \| None` | `None` |
| `SealReceipt` | `dataset_id` | `str \| None` | `None` |
| `SealReceipt` | `input_events` | `int` | `0` |
| `SealReceipt` | `accepted_rows` | `int` | `0` |
| `SealReceipt` | `detail` | `str` | `""` |
| `SealRequest` (02I) | `asset_class` | `AssetClass` | `AssetClass.OTHER` |
| `SealRequest` (02I) | `volume_unit` | `str` | `"unknown"` |
| `SealRequest` (02I) | `turnover_unit` | `str` | `"unknown"` |

New methods (02I): `JournalSession.read_meta`,
`JournalSession.record_completion_boundary_ns`. New helpers (02I):
`sealing.validate_source_spec`, `sealing.validate_calendar_spec`,
`sealing.SourceSemantics`.

---

## 8. Pending (not recording-core-owned)

| Item | Owner |
|------|-------|
| Recorder bridge (native → journal admit) | recorder03C (done) / 03D integration |
| CLI verbs (recover-session, replay, seal) | recorder03D |
| UI integration | recorder03D |
| WP10 delivery/verification | delivery04A |
| `INTERFACES.md` reconciliation | qualified05 |

03D integration notes (recording02I): the top-level
`research_store.recover_session` now forwards `create_successor` /
`successor_source_spec` / `successor_calendar_spec` (03D smoke finding
closed); `SealRequest` gained three OPTIONAL typed-semantics fields
(defaults are honest OTHER/unknown, so existing request JSON keeps
working), and a typed `source_spec` (e.g. `"futures:ctp@v1"`) plus a
supported `calendar_spec` (`""` / IANA / `"tz:<IANA>"`) are required for
typed semantics — `"CN.FUTURES.DAY"`-style values are refused with an
explicit error at seal time.
