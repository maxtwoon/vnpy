# VERIFICATION — v0.1.0.dev1 (final04N developer state)

Scope: final delivery assembly (TASK_OPENCODE_DELIVERY_FINAL_04N.md) on the
released 2026-09-30 source. This is the developer completion summary; the
actual independent Claude final audit follows and is the acceptance gate.
The machine-readable matrix (same content, bound to evidence-file hashes)
lives at `reports/delivery04n/verification-matrix.json` with a standalone
HTML render — regenerate with `tools/delivery_finalize.py report`. Facts are
extracted from machine evidence; prose claims are labeled as claims.
Store-global `verify` counts are work units of that verify run, NOT
per-snapshot object counts.

Status legend: MEASURED · PARTIAL · PENDING · NOT_RUN · UNKNOWN ·
LIVE_NOT_RUN · HISTORICAL (preserved record, never a current claim) ·
EVIDENCE_MISSING (bound evidence disappeared — matrix only).

## 1. First usable snapshot — real ETF same-snapshot loop (MEASURED)

* Binding: store `store-398306491d834f99`, snapshot `snap-030369f20bd18303`,
  datasets `ds-d939147fd6b633fd348fa62ed1fef74c` (1d) and
  `ds-b9bbad83ec09f4b9dcef6ea9a81c4b51` (1m).
* CURRENT runtime evidence: 16/16 checks PASS, 27.927 s
  (`.coordination/etf-current-runtime-20260930/utf8-run/result.json`) in the
  registered vnpy-alpha 3.14 runtime with hash-pinned local
  duckdb/zstandard/CTA/portfolio overlays only — no shared-env merge,
  process-local `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`; the first encoding
  failure is preserved in the parent directory.
* Covered: core reader, native Database (bare `510130`/`510300` + SSE), both
  Alpha methods, offline CTA/Portfolio bootstrap, snapshot verify, import
  idempotency + 133-key repair-index cross-checks. Original source
  import/repeat receipts reused — finished imports were NOT rerun.
* HISTORICAL: the first delivery04f run scored 13/16 (runner assertion
  defects, review-dispositioned, fixed); preserved at
  `opencode-loop.preserved-FAIL.stdout.json`. The 2026-09-17 plugin-venv
  16/16 run is retained as lineage.
* Standing limits: `expected_coverage` UNKNOWN; qualified range = 510130/
  510300 SSE, 2016 frozen selections only.

## 2. Inventory and representative validations (MEASURED)

| Item | Measured facts |
|---|---|
| Both source roots | SS 123 files / 19,667,963,677 bytes; holographic 3,608 files / 53,907,819,144 bytes (`delivery04d-evidence.json`; no bulk hashing) |
| Inventory fix 04B | failed/unrecognized records preserved; path escapes refused; 04a FAILURE record kept as HISTORICAL |
| Stock raw target=store, JQ 33-col/NULL, ETF 133 repaired keys, P4 catalog | delivery04k reports (HISTORICAL measured representatives; JQ adjustment unknown; catalog ≠ qualification) |
| RQ futures FINAL | PASS 14/14, 59.838 s, peak 3,070 MB: 222,180 contract + 392,640 dominant candidates, 1,035 window joins, ZERO canonical publication (`delivery04l-final-20260930/futures-final.json`; independent Claude scoped PASS). Time-label direction stays UNKNOWN by design |
| RQ futures HISTORICAL | `futures-fixed-final.json` FAIL_ASSERTIONS preserved unchanged (runner compared 199,425 all-instrument vs 7,125 A2505-only) |
| SSQuant capture | capture04H TERMINAL with current recovery receipt; captured_at uncertainty remains recorded; reused as-is (no new 10 GB copy/hash) |

## 3. SS representative case (MEASURED, scoped)

* Real rb2605 import/repeat/freeze/query/immutability: independent scoped
  PASS (claude-ss04m-20260930, 19 fresh tests). S1 `snap-ec86298119e47e9c`
  (60/12/4 rows), S2 `snap-ab182160a7c6eb31` (120/24/8 rows); 1/5/15m remain
  separate datasets (`delivery04m-phase1/phase2/phase2-repeat.json`).
* Exact 8 SimNow keys quarantined, healthy rows retained
  (`delivery04m-simnow-quarantine.json`, root exit 0).
* Missing-turnover normalization fix in source; fresh root registered-Alpha
  verification exit 0: snapshot `snap-0d3404a3803d93cf`, 1m
  `ds-07199d36904cd3bf728896e1c3f4783e` — 60 positive rows / 60 NULL
  turnover with raw amounts retained; 5m `ds-5ff33396aeb6833347ee073b9e85abf4`;
  15m `ds-3c2eced2f6eabed43eb7cbb979438eee`. MA 4,745 candidate-only rows
  normalized NULL (no fabricated bounds). Independent review exec40881 PASS
  (40 tests), which also corrected the stale "0 rows" observation.
* IMPORTANT: both public Alpha methods with default options on the postfix
  snapshot raise `StoreError` unmapped exchange — the EARLIER identity
  refusal — NOT a VWAP-specific exception; no VWAP-specific exception was
  reached. This limitation stays visible.
* Old numeric-turnover v1 snapshots remain immutable history; semantic-v2
  supersedes for new usage. SS scope = the evidenced windows ONLY; calendar,
  units and broader eligibility UNKNOWN.

## 4. Recording (MEASURED engineering, explicitly SYNTHETIC; live = LIVE_NOT_RUN)

* Durable synthetic engineering session on the real store:
  `sess-d7c9ad113b2e42f5` (CLOSED, sealed ticks `batch-0ddd90b14eca4cde` +
  bars `batch-61efad21d3b04f95`), snapshot `snap-7914084cde1ff139`,
  5 ticks + 2 bars
  (`recorder03d-installed-20260930/quantdata_same_session.result.json`,
  QUANTDATA_SYNTHETIC_SAME_SESSION_OK). Do not age/delete this journal.
* Installed acceptance: independent review found REQUIRE_CHANGES (F1
  recorder source_spec vs sealer grammar; F2 missing Windows tzdata) — both
  FIXED with independent scoped PASS (claude-recorder-fix-20260930; recorder
 .py `118fbcb9…`, pyproject `e1904b7f…`, r2 wheel `b2fb7dbb…`; tzdata
  installed in the disposable env only). Plain-script installed acceptance
  is valid focused evidence; pytest-in-installed-env was NOT run.
* Recorder EOF/retry repair: independent scoped PASS (7 launcher + 38
  related tests, REVIEW_RECORDER_20260930.md). Coverage/retention repair:
  independent scoped PASS (40 tests, REVIEW_RETENTION_20260930.md).
* Public report correction (authorized bounded scope):
  `research_store/report.py` now shows durable journal-only sessions
  (journal authority: status, committed watermark, `MAX(seq)`, successor
  lineage), retains catalog-only sessions with their missing journal as an
  error, reconciles duplicate ids (catalog status kept visible), reports
  unreadable/partial journals as errors, and keeps live in-memory counters
  (accepted/backlog/rejected/errors) `null` in the machine JSON — rendered
  as explicit **UNKNOWN** in HTML, never inferred zero. Reads are SQLite
  read-only, no lock file, no catalog writes, metadata/watermark only (no
  event scan). Tables wrap long paths/hashes so the page stays inside the
  viewport (root visual check: scrollWidth 1838 > 1536 fixed; final title
  replaces the phase-1 label). Successor lineage is computed for EVERY
  entry (journal and catalog-only) by comparing
  `other.predecessor_session_id` to `entry.session_id` with no predecessor
  prerequisite — the root-found defect (catalog-only root parents lost
  their durable children; non-root parents could list siblings) is CLOSED:
  root failed repro preserved (`report_catalog_lineage_probe.json`,
  actual `[]`), post-fix probe `lineage_fixed: true`
  (`delivery04n-dev/report_catalog_lineage_postfix.json`), three lineage
  regression tests. Evidence: 12 focused tests
  (`tests/test_report_recording_sessions.py`), post-fix probe
  (`delivery04n-dev/repro_postfix.stdout.json`, exit 0), real-store report
  (`store-report.stdout.json`: `sess-d7c9ad113b2e42f5` CLOSED committed 5),
  and the installed-artifact smoke. The pre-fix public repro is preserved
  unchanged at `repro_recording_report_20260930.json`.
* Known behavior documented: old key/value-formatted sessions remain
  replayable but cannot seal; repeated `recover-session` creates DISTINCT
  successors (advise `inspect` first; `--no-successor` for report-only
  repeats).
* `live_gateway_recording` = **LIVE_NOT_RUN**.

## 5. Final package and affected checks

* Final rebuild r3 (current; after the SS corrections, the visual closeout
  render changes AND the successor-lineage correction): wheel
  `vnpy_researchstore-0.1.0.dev1-py3-none-any.whl` sha256 `1e6761b9…` and
  sdist sha256 `4a7ac9d8…`
  (`delivery04n-dev/artifacts-final-r3/`, `final-build.json`), built with
  the disposable `build-env-20260930` used READ-ONLY (no env modification,
  no network). History preserved: r1 (`8bf32d66…`/`486b8409…`,
  pre-visual-closeout, at `artifacts-final/`) and r2
  (`e3e03ebd…`/`8c4a3e2e…`, pre-lineage-fix, at `artifacts-final-r2/`) are
  provisional-superseded, never deleted; the recorder-fix r2 wheel of
  record (`b2fb7dbb…`) is noted.
* Installed smoke (`delivery04n-dev/installed-smoke.json`, exit 0, rerun on
  r3 in the SAME disposable venv): wheel installed `--no-deps` (dependency
  imports resolve read-only from the base environment); module origins
  proven inside the venv site-packages (non-editable); the installed
  `research_store.report` behaviorally passes BOTH the journal-visibility
  probe AND the catalog-lineage probe (catalog-only root parent gains its
  durable child).
* Affected checks at final source state — ALL BOUND to actual command
  outputs under `.coordination/delivery04n-dev/checks-final/`
  (`summary.json` + per-check logs):
  - focused tests: 50 passed (12 report + 11 finalize + 18 loop-runner +
    CLI; `pytest-focused.txt`);
  - datasource suite rerun at FINAL state by final04N: 101 passed, exit 0
    (`pytest-datasource-venv.txt`; pre-existing pytz warning only);
  - ruff exit 0 on BOTH integrations (`ruff-plugin.txt`,
    `ruff-datasource.txt`);
  - scoped mypy exit 0 (`mypy vnpy_researchstore research_store/report.py`,
    `mypy-scoped.txt`);
  - root `tools/sync_check.py` exit 0 via registered Python 3.14 — PASS
    with the pre-existing informational `docs/archive` warning
    (`sync-check.txt`);
  - datasource 24-file baseline identity: **13/24 match, 11 files
    legitimately evolved** since the 2026-09-16 snapshot (warehouse
    integration + 2026-09-30 closeout, documented in the datasource
    VERIFICATION.md dated sections). The old baseline is therefore NOT a
    current identity proof — which is exactly why the suite was rerun at
    final state instead of reusing stale identity
    (`datasource-baseline-check.json`).
* Environment disposition 2026-09-30 (owner-run, reused): whole
  vnpy-environment 408 passed / 27 failed with missing Alpha/portfolio
  dependencies; 16 native Alpha tests in the isolated-dependency runtime;
  8 portfolio plugin tests. Runtimes are recorded separately and NOT
  equated; no single-runtime whole-package green is claimed;
  pytest-in-installed-env was not run (plain-script installed acceptance is
  the focused evidence). The current-runtime ETF loop evidence was produced
  on the registered vnpy-alpha route with hash-pinned overlays (see README
  runtime note); the plugin .venv commands are labeled historical.
* Deliberately not claimed: live gateway capture; market completeness;
  strategy efficacy; whole-package green under one runtime.

## 6. Configs (all validated read-only by `tools/delivery_finalize.py check-configs`, 6/6 clean)

* Repository templates (generic `REPLACE_ME`): `configs/smoke_import.json`,
  `configs/smoke_snapshot.json`, `configs/recorder_replay.json`,
  `configs/backtest_profile.json`.
* Real instances under `D:/quant-data/configs/`: `smoke_import.json` (2016
  two-ETF verified import), `smoke_snapshot.json` (verified freeze
  selections), `backtest_profile.json` (verified offline bootstrap),
  `delivery_etf_loop.json` (verified 16-check loop),
  `recorder_replay.json` (durable synthetic session reference — replay is
  read-only).

## 7. Intentionally absent / unknown

* `expected_coverage` UNKNOWN everywhere (no calendar/listing evidence).
* No fabricated publisher attribution; no bulk purchased data in reports.
* Nothing is presented as a PASS where the bound evidence is pending or
  historical; historical failures are retained as HISTORICAL, never
  overwritten.
