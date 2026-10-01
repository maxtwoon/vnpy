# OpenCode development assignment 04 — WP10 real-data loop and delivery

Actual OpenCode develops; Codex coordinates; actual Claude Code independently audits/tests. Read IMPLEMENTATION_PLAN.md mandatory amendments, PLAN_AUDIT_DISPOSITION.md, INTERFACES.md, latest developer handoffs and Claude findings. This assignment finishes the approved v0.1, not merely a CLI sample. Personal local research: useful local commands, a lightweight HTML report, proportionate validation. No new service or institutional certification.

## Dependencies and ownership

Codex dispatches after core/importers/consumers/recorder/sealing interfaces are handed off and blocking findings resolved. Prepare documentation and input selection earlier only when explicitly assigned. Do not run acceptance against concurrently changing product files or call unfinished capabilities PASS.

Own README.md, VERIFICATION.md, CHANGELOG.md, configs/, tools/, already assigned OpenCode product paths and tests for necessary final fixes; additive datasource paths already assigned. Write run artifacts under correctly initialized D:/quant-data and .coordination/opencode-wp10-handoff.md. Do not edit coordinator TASKS/plan/audit/task files. Core defects go to Codex/Kimi with a minimal reproduction, not a consumer workaround. No vnpy core/site-packages, raw data, ledger/credentials, default .vntrader, archived Chan, unrelated ETF or root HANDOFF edits. No account/gateway connection, trading, git commit/push.

Use the package .venv without upgrading Studio. Record actual executable, cwd, dependency versions, module origins, Git HEAD plus hashes of relevant dirty/untracked code, configuration path/hash and store ID. New consumer processes must bind repository core and isolated cwd BEFORE transitive vnpy utility imports.

## Inventory and real imports

Deliver a machine-readable inventory covering both complete source roots and all catalog-only categories. Separate discovered files/members, inspected schemas, verified hashes, formally imported members/tables/ranges, missing files, version conflicts and unknown semantics. Fast discovery hashes may remain unverified; formal import must hash actual input. LOG row totals and min/max dates are not full coverage or quality checks. Use streaming readers and consistent read-only SQLite backup, no full extraction or whole-year minute-data materialization.

First usable snapshot: select actual RQ ETF510130/510300 1d and1m ranges with known semantics and enough real records for multiple days, lunch boundaries and Alpha extended window. Choose dates from actual data. Use159915 existing evidence for unit comparison if appropriate. Load repair index before base. Record package/member/hash, normalization, input/accepted/duplicate/quarantine/failure counts and observed/expected coverage. Repeat import to prove idempotency. Freeze real selections and verify manifest files/hashes.

Read .coordination/REAL_INPUT_CANDIDATES.md for three already-located real Client JSON inputs, exact paths/hashes and existing units evidence. In particular stock_raw.json and tushare_raw.json are real600519.SSE observations saved before BarData conversion. Keep their historical metadata and limitations; no new source query is needed for that path.

For the real futures/night window, .coordination/FUTURES_INPUT_CANDIDATES.md locates A2505 exact source trading_date mappings and hashes, plus a package-label metadata conflict requiring explicit resolution before qualification. Repeat actual scoped joins/checks; no natural-date filling or continuous-price substitution. This locator is not a validation receipt.

The SAME snapshot_id must be actually read through BOTH Database and ResearchAlphaLab. Compare Database counts/symbols/timestamps/OHLCV with core/source. Invoke BOTH Alpha load_bar_data and load_bar_df; verify inclusive end, extended_days, columns, OHLC normalization and original VWAP preprocessing. Include exact final timestamp==native end and nonaligned boundary. Compare preprocessed columns with their mathematically appropriate expected values, not raw price blindly. Record runtime module origin, actual adapter class, snapshot binding and isolated lab results. Verify CTA and Portfolio bootstrap loading/reading paths offline; no gateway or live strategy. A failing consumer means no first-usable-snapshot claim yet.

Known gaps may only be accepted by explicit scoped configuration with reasons under the implemented policy; do not disable quality globally. Unknown expected coverage remains unknown. State exactly the imported/qualified securities and ranges. Full asset discovery, real streaming import capability, representative closed loops and executable expansion commands are required; importing and re-auditing every byte of all historical archives is not a newly imposed release gate. Clearly list unimported ranges and batch commands.

Other representative real validations, without needing all history:

- Datasource raw-stock target=store from an existing real successful Client raw result: preserve records/NULL/metadata/attempts/request/registry hash; do not fabricate a result or run through zero-filling conversion. Locate existing authorized evidence first. If missing, report the specific input gap to Codex; never substitute mock success or new unauthorized source connection.
- SSQuant real contract capture and1/5/15m distinction, exact SimNow8-key/staging isolation, original symbols/mapping and selected-range semantics. MA untrusted amount remains raw evidence with normalized missing turnover and VWAP rejection.
- RQ real futures with actual trading_date/night session/member identity, continuous dominant mapping kept separate and unknown roll rules visible.
- JQ33source columns/NULL/factor1=>adjustment unknown; query capability does not confer return-backtest qualification.
- Real ETF repaired base keys and upstream conflict evidence; old/new/upstream candidates traceable and disputed observations excluded by default.
- P4 catalog-only plus missing convertible overlay, index manifest version difference, shares fallback and PIT knowledge-time limits.

Software function status and dataset qualification must be separate. READY is always bound to dataset+instruments+range+revision/snapshot and evidence, not inherited from a passing unit test.

## Recording and performance

Use public CLI/APIs to demonstrate offline journal acceptance/commit state, clean stop vs UNCLEAN_END, recover-session, committed-only replay, seal into a real canonical revision and query it. Repeat replay/seal deterministically. Preserve first cumulative baseline/reset/gap/late/partial statuses. The UI/CLI must expose rejected/backlog/accepted/committed/error/seal status. Label synthetic/test input explicitly. Engineering recording PASS does not imply real gateway capture: absent an authorized live run, write live_gateway_recording=LIVE_NOT_RUN with actual limits. Do not connect an account to remove that label.

Use representative import/query/replay sizes to record time, peak memory and backlog. Fix sustained backlog or streaming/memory contract failures, without inventing throughput promises or full-market benchmark gates. Retention checks should prove eligibility/path boundaries using temporary files; no need to delete real historical journals, and never delete raw/canonical data.

## Usable artifacts

Deliver actual runnable instance configs under D:/quant-data/configs: smoke_import.json, smoke_snapshot.json, recorder_replay.json, backtest_profile.json, using real paths/dataset/snapshot/session IDs from verified runs. Repository templates may be generic but must be clearly distinguished from actual instance configs. No credentials.

Machine-readable outputs: assets, coverage (observed/accepted/quarantined/expected plus interval reasons), conflicts (candidates/evidence/resolution/revisions), verification, runtime recording/disk status. When calendar/listing/session/suspension evidence is unavailable, expected=unknown, never infer completeness from min/max.

Lightweight standalone HTML: source inventory, ready ranges, gaps, quality/conflicts, recording watermarks/errors, disk use and validation status. Do not embed bulk purchased data or add a backend. README must document commands actually checked for install/inspect/import/freeze/two-consumer read/bootstrap/record/stop/recover/replay/seal/report, separating tested offline steps and instructions awaiting real-gateway authorization. Rollback is original launcher/environment, no default config change.

## Checks and handoff

After relevant source stabilizes, run scoped new integration tests, FULL existing datasource tests, Ruff both integrations, scoped mypy, package build, pure-core import without vnpy/provider SDK side effects, and root sync_check. Preserve unrelated baseline failures; never weaken gates. Reuse valid identical-code results; repeat affected checks after fixes, not unrelated suites without cause. These are development results, not a substitute for Claude independent audit.

Each verification item records check_id/WP/dimension, status PASS|FAIL|PARTIAL|NOT_RUN|UNKNOWN, code hashes/runtime origins, actual input hash/member/table/security/time/config, dataset/snapshot/session IDs, exact command/exit, counts and assertions, evidence paths, limitations and failure owner. Null/not-applicable is permitted; placeholder IDs cannot be presented as real results. Explain count reconciliation including conflicts and rejected rows.

Write .coordination/opencode-wp10-handoff.md with changed files, exact first usable snapshot scope and two-consumer evidence, instance configs and one-step commands, READY/CANDIDATE/QUARANTINED/UNKNOWN dataset table, recording engineering vs LIVE_NOT_RUN, tests/failures/not-run and remaining ownership, reports/log locations, rollout/rollback steps. Only report development complete pending Claude when required software and real-data consumer loops are actually complete. Do not rename missing required functionality as a later enhancement to claim completion.
