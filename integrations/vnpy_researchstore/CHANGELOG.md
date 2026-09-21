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
  checks (`tools/delivery_etf_loop.py`).
* Representative validations: stock raw target=store, JQ 33-col/NULL, ETF
  133 repaired-key exclusion, P4 catalog branches (delivery04k reports).
* Repository templates (`configs/smoke_import.json`,
  `configs/smoke_snapshot.json`, `configs/recorder_replay.json`,
  `configs/backtest_profile.json`) kept generic; real instance configs live
  under `D:/quant-data/configs` and are validated read-only by
  `tools/delivery_finalize.py check-configs`.
* Phase verification matrix + standalone HTML report from bound machine
  evidence (`tools/delivery_finalize.py report` →
  `reports/delivery04n/`), with PENDING/UNKNOWN/LIVE_NOT_RUN states
  preserved for the in-flight 04H/04L/02IA/03D/04M scopes.

### Known limitations (standing)

* Expected market coverage UNKNOWN everywhere (no calendar/listing
  evidence in scope).
* Durable recording sessions on the real store: none yet; instance
  replay/seal config intentionally absent.
* Live gateway recording: LIVE_NOT_RUN.
* Final stable checks (full datasource suite, ruff/mypy both integrations,
  build + installed entrypoints, sync_check, 24-file baseline) deferred to
  phase 2 against stable dependencies.
