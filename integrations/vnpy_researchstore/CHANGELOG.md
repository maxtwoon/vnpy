# Changelog

All notable changes to `vnpy_researchstore` are documented here. The plugin
is personal local research software (MIT); versions are pre-1.0 development
stages. This changelog was assembled at delivery04N phase 1 from the
per-task handoffs and evidence; entries are grouped by work package (WP).

## 0.1.0.dev1 (2026-09-16 / 2026-09-17, unreleased)

### Storage core (WP01–WP03)

* Immutable store core: catalog, content-addressed parquet objects, streamed
  imports with formal input hashing, revisions and partition heads, conflicts
  (existing/candidate/quarantine) with explicit resolution, observed coverage
  and observational quality reports, deterministic snapshots with manifest
  verification (`init/inspect/import/freeze/verify/coverage/quality/
  resolve-conflict/export/report` CLI).
* Snapshot manifests capture the default-qualified policy; legacy
  (format-1) manifests are refused for default consumption instead of being
  silently treated as clean.
* Inventory: both source roots inventoried without bulk hashing (SS 123
  files / ~19.7 GB; holographic 3,608 files / ~53.9 GB); broken archive-list
  records are preserved as failed/unrecognized records and path escapes are
  refused (04B), with the original inventory failure record kept visible.

### Native bridge (WP06)

* Read-only `BaseDatabase` plugin over one frozen snapshot: bare native
  symbol resolution against stored vendor-suffixed identities at read time
  (`510130` + `Exchange.SSE` → rows stored as `510130.XSHG`), native
  inclusive-end contract, precise nonaligned boundary filtering, unmapped
  exchange labels refused (never guessed), snapshot-bound overview with
  native symbol presentation and diagnostics. No SQLite fallback.
* `ResearchAlphaLab`: snapshot-bound read-only `AlphaLab` with native
  `extended_days` windowing, first-close OHLC normalization, suspended-row
  masking, equity VWAP = turnover/volume (zero volume → missing VWAP),
  futures VWAP only with a verified single-side lot multiplier. Both read
  methods verified against the real ETF snapshot (16-check loop).
* Guarded offline bootstrap for CTA/Portfolio backtesters: repo vnpy +
  isolated cwd before any vnpy import, singleton/no-fallback assertions,
  fresh-process requirement, run receipts.

### Importers and semantics (WP04/WP05/WP08)

* RQ ETF/LOF adapter: archive sidecar hash verification, repair index
  loaded before base archives (133 keys), disputed repaired keys excluded
  from default backtests with visible gaps, END→START minute normalization,
  idempotent repeat imports.
* SSQuant adapter with consistent read-only SQLite capture staging (live
  -wal never imported), scoped table/month work units.
* RQ futures adapter: exact source `trading_date` night-session mappings
  kept separate from continuous/dominant mappings; time-label direction
  defaults to UNKNOWN pending scoped time evidence (04L in flight).
* JQ adapter: 33 source columns, NULL preservation, unknown adjustment is
  refusal, not a guess.
* Recording source ingestion with cumulative baseline/reset/gap/late/
  partial statuses; journal admission, clean stop vs UNCLEAN_END,
  recover-session, committed-only replay, idempotent sealing (WP08/WP09).
  Engineering-level only; no authorized live gateway capture
  (LIVE_NOT_RUN).

### Delivery (WP10)

* First usable snapshot proven end-to-end on real data:
  `snap-030369f20bd18303` (store `store-398306491d834f99`), RQ ETF
  510130/510300 2016 1d+1m, read through core reader, native Database and
  both Alpha methods plus offline CTA/Portfolio bootstrap with 16 passing
  checks (`tools/delivery_etf_loop.py`), re-verified on the current
  registered runtime (2026-09-30, 27.9 s) with hash-pinned local dependency
  overlays.
* Public store report correction: durable journal-only recording sessions
  are now visible with journal authority (status, committed watermark,
  `MAX(seq)`, successor lineage); catalog-only sessions are retained with
  their missing journal marked as an error; duplicate session ids are
  reconciled (catalog status kept visible); unreadable/partial journals are
  visible as errors; live in-memory counters stay `null`, never inferred
  zero; reads are SQLite read-only (no lock file, no catalog writes,
  metadata/watermark only). Twelve focused tests
  (`tests/test_report_recording_sessions.py`).
* Recorder installed defects F1 (source_spec vs sealer grammar) and F2
  (Windows tzdata dependency) fixed with independent scoped PASS; recorder
  EOF/retry repair and coverage/retention repair independently scoped PASS.
* RQ futures final real case PASS 14/14 (222,180 contract + 392,640
  dominant candidates, 1,035 window joins, zero canonical publication);
  time-label direction stays UNKNOWN by design. SS rb2605 representative
  case import/repeat/freeze/query PASS with 1/5/15m isolation, exact 8
  SimNow keys quarantined, and missing-turnover normalization (semantic-v2
  datasets supersede numeric-turnover v1, which remains immutable
  history).
* Final wheel/sdist rebuilt after the SS/report corrections and the visual
  closeout (wrapped contained tables, explicit UNKNOWN cells for null live
  counters, final report title) and proven in a disposable non-editable
  install (module origins + installed report smoke). Prior builds remain
  on disk marked provisional-superseded in `final-build.json` history.
* Repository templates (`configs/smoke_import.json`,
  `configs/smoke_snapshot.json`, `configs/recorder_replay.json`,
  `configs/backtest_profile.json`) kept generic; real instance configs live
  under `D:/quant-data/configs` and are validated read-only by
  `tools/delivery_finalize.py check-configs`.
* Phase verification matrix + standalone HTML report from bound machine
  evidence (`tools/delivery_finalize.py report` →
  `reports/delivery04n/`), with MEASURED/PARTIAL/PENDING/UNKNOWN/HISTORICAL
  and LIVE_NOT_RUN states preserved; historical failures (04F first-run
  13/16, futures FAIL_ASSERTIONS) retained as history, never overwritten.

### Known limitations (standing)

* Expected market coverage UNKNOWN everywhere (no calendar/listing
  evidence in scope).
* SS scope = evidenced rb2605 windows only; both public Alpha entrypoints on
  the postfix snapshot refuse at the earlier unmapped-exchange identity
  check — no VWAP-specific exception is reached.
* RQ futures time-label direction UNKNOWN by design pending scoped time
  evidence.
* Durable recording proof is SYNTHETIC engineering evidence (session
  `sess-d7c9ad113b2e42f5`); old key/value-formatted sessions remain
  replayable but cannot seal; repeated recover-session creates distinct
  successors.
* Live gateway recording: LIVE_NOT_RUN.
* No single-runtime whole-package equivalence is claimed (environment
  disposition: 408/27 with missing Alpha/portfolio dependencies; isolated
  runtimes for Alpha and portfolio).
