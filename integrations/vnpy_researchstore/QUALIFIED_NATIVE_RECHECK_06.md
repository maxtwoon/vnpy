# Claude Code — qualified05/native06 combined recheck (independent, read-only)

Date: 2026-09-17. Reviewer: actual Claude Code (Sonnet 5), independent, read-only.
Package root: `D:/repo/vnpy/integrations/vnpy_researchstore`. Executable: package `.venv/Scripts/python.exe`. Repo vnpy on `sys.path`, isolated runtime cwd before any vnpy import (never touched default `.vntrader`). Real snapshot used: `snap-030369f20bd18303` (root `D:/quant-data`, read-only, never reimported/frozen/mutated). Temp artifacts only under `.coordination/review-qualified-native06/` (2 repro scripts, pytest basetemp dirs, tmp dir). No product/test/config/Git/memory/store writes.

## Source/input hashes

`.coordination/claude-qualified-native06-input-hashes.json` lists 53 files (source, tests, config, snapshot/manifest references).
- **Before review:** re-verified all 53 against current bytes → 0 missing, 0 mismatches.
- **After review:** re-verified again after all commands below → 0 missing, 0 mismatches.
- `git status --short` on `integrations/vnpy_researchstore/` shows only the pre-existing untracked plugin directory (`??`); no tracked-repo mutation of any kind was made or is possible (plugin dir isn't Git-tracked in this repo).

## F1/F2/F3 (QUALIFIED_RECHECK_04 accepted regressions, corrected by qualified-fix05)

**F1 (HIGH) — native clean ranges blocked by exclusions elsewhere in the symbol: CLOSED.**
Fix: `native_common.resolve_bar_dataset` discovery/validation scan now runs observationally (`include_default_excluded=True`); consumer reads still use the qualified default reader for the caller's actual range.
- `repro_wider_scope_clean_range.py` (original reviewer file, unchanged, hash `025637622132...`): 4/4 PASS — core reader, `Database.load_bar_data`, both `ResearchAlphaLab` methods all return 2 rows over the clean range with the exclusion elsewhere.
- `tests/test_qualified_fix05.py::test_f1_*` (4 tests) individually PASSED: clean range succeeds on all native paths; selected excluded range still refuses on Database + both Alpha methods; explicit `allow_known_gaps` leaves the excluded row absent (interval permitted, row never returned); non-aligned/strictly-before ranges still enforce qualification.
- Native03 whole-stream exchange-label validation (all-batch scan, empty-leading-batch handling) is preserved — only the reader mode flag changed on the discovery scan, confirmed by code inspection of `native_common.py`.

**F2 (MEDIUM) — freeze held the catalog lock across full Parquet scans: CLOSED.**
Fix: `snapshots.py:freeze()` now captures heads/manifests/immutable `(partition, relpath, sha256)` file references inside one short `with store.catalog.transaction():` block (lines 79–144); `quality.scan_exclusion_entries_in_files` (the hashing/Parquet-scanning call) runs after that block exits (lines 163–170+), operating only on the captured immutable references.
- `test_f2_freeze_scans_outside_transaction_and_ignores_later_head_moves` PASSED: spies confirm the scan runs with the transaction inactive, and a simulated concurrent head advance during the scan does not enter the frozen capture.

**F3 (MEDIUM) — legacy manifests indistinguishable from captured-clean: CLOSED.**
Fix: `SNAPSHOT_FORMAT = 2`; typed `SnapshotReader.default_qualified_status()` → `"qualified"` / `"legacy_unqualified"`; `_check_gaps` refuses default-qualified reads (core reader, native Database, `get_bar_overview`) on legacy (format-1) manifests with an explicit `CoverageGapError`; observational access (`include_default_excluded=True`) keeps its prior full-row meaning; old snapshot bytes are never rewritten.
- `test_f3_legacy_manifest_default_and_native_refusal_observational_preserved`, `test_f3_new_clean_snapshot_is_qualified_and_usable` PASSED.

## Scoped test suite

`pytest tests/test_qualified_fix05.py tests/test_default_qualified.py tests/test_dominant_overlay.py tests/test_export.py tests/test_core_conflict_gap.py tests/test_snapshot_freeze.py tests/test_core_reader.py tests/test_quality.py tests/test_coverage.py tests/test_store_sink.py tests/test_core_time_contract.py tests/test_core_ticks.py tests/test_native_database.py tests/test_native_alpha.py tests/test_native_fix03.py tests/test_native_bootstrap.py tests/test_native_support.py tests/test_native_symbol_resolution.py -q` → **152 passed**, 0 failed (reconciles with developer counts: 140 qualified05-scope + 12 symbol-resolution).

## Native real-identity: PASS

Read-only smoke against `snap-030369f20bd18303`:
- `native06-smoke-real.py` (Database): bare `510130`/`510300` + `Exchange.SSE`, MINUTE 09:30–09:35 → 6 rows each, `bar.symbol="510130"/"510300"` (no vendor-suffix leak), `bar.extra["source_identity"]="510130.XSHG"/"510300.XSHG"`; overview presents native symbols only (`['510130','510300']`), DAILY 244 rows/symbol, MINUTE 4800 rows/symbol. Exit 0.
- `native06-smoke-alpha.py`: `load_bar_data("510130.SSE", DAILY, 2016-01-04..08)` → 5 rows; `load_bar_df(["510130.SSE","510300.SSE"], ...)` → 10 rows, `vt_symbol` values are native (`510130.SSE`/`510300.SSE`), never a vendor compound. Exit 0.
- Compound `510130.XSHG.SSE` was not used as a success criterion anywhere in this verification — confirmed diagnostic-only per handoff and by the passing bare-symbol paths above.
- Ambiguity/label contracts independently confirmed via `tests/test_native_symbol_resolution.py` (already in the 152-pass run): bare+suffixed same dataset → `StoreError` ("ambiguous stored identities"); bare identity with unmapped exchange label → `StoreError` ("unmapped exchange label"); wrong-exchange request → `[]`; stored `510131.XZZZ` (suffix not in exchange map) vs. native request `510131`+SSE → ordinary empty `[]`/`None` on both Database and both Alpha methods (never an error) — the suffix is never formed as a candidate and never guessed/stripped. This is distinct from, and correctly not conflated with, the bare-`510131`-unknown-label `StoreError` case. `Database.diagnostics` reports the present-but-unmapped rows verbatim (label + count) after `get_bar_overview()` runs; `ResearchAlphaLab` has no equivalent overview-based diagnostic surface (it has no `get_bar_overview` at all) — this asymmetry is disclosed by the developer handoff itself (§4/§7) as a known, tested limit, not a hidden defect, and I found no evidence it silently discards a request the contract obligates it to serve: both Database and Alpha return the same ordinary-empty result for the same unknown-suffix input. **No new finding here.**

## Bounded 04F diagnostic (13/16 passed, 3 failed) — dispositions

Parsed only `checks[].name/pass/detail` from `.coordination/delivery04f-dev/opencode-loop.stdout.json` (867 KB; never dumped whole). Runner: `tools/delivery_etf_loop.py` (sha256 `094644d3...`, matches the 53-file manifest, unedited).

1. **`alpha_df_windows_and_preprocessing` — RUNNER ASSERTION DEFECT, not a product defect.**
   Trigger: `tools/delivery_etf_loop.py:1128-1133` compares `value_rows_digest` of `ResearchAlphaLab.load_bar_df(..., extended_days=0)` OHLC (which `alpha.py:295-302` intentionally divides by the window's first close, per its own documented "native OHLC first-close semantics" contract) directly, byte-for-byte, against `db_digest_by_key[..., "base"]` — the **raw, un-normalized** `Database.load_bar_data()` digest. These can only be hash-equal if the raw first-bar close is exactly `1.0`, which no real price series satisfies. The same function's own row-level check just above (`compare_rows` against `normalize_expectation`, which *does* apply the first-close division) reported **no** mismatches for these same symbol/interval/ext=0 combinations — independently confirming the product's normalization is correct and the final raw-digest re-check is redundant/wrong. Verified by direct repro (`.coordination/review-qualified-native06/repro_04f_digest_check.py`): raw DB first close `3.25`; Alpha ext=0 first-row close `1.0` (by construction). Minimal fix (not applied, runner is out of scope): drop the direct digest-equality check at those lines, or compare against `value_rows_digest(normalize_expectation(raw_rows))` instead of raw `db_digest_by_key`.

2. **`alpha_df_zero_volume_vwap_missing` — RUNNER ASSERTION DEFECT, not a product defect.**
   Trigger: `tools/delivery_etf_loop.py:1152` sets `close_0 = rows[0]["close"]` from the **already-normalized** Alpha dataframe (`rows` sourced from `lab.load_bar_df(...)`), where the first row's close is trivially `1.0` by construction, then computes `expected_ohlc = 3.25 / close_0 = 3.25`. The actual (correct) normalized value is `raw_target_close / raw_first_close = 3.25 / 3.595... ≈ 0.9040333796940194`, which is what Alpha returns. Verified by direct repro (`.coordination/review-qualified-native06/repro_04f_alpha_checks.py`): reproduces the exact 8 "field mismatch" problems the runner would report (`expected=3.25 actual=0.904...`); the VWAP-missing assertions themselves (NaN at zero volume, `3.275` at the resumed 13:00 bar) are correct and not part of the failure. Minimal fix (not applied): source `close_0` from a raw `Database.load_bar_data` reference row for the same expanded window, not from the Alpha dataframe's own first row.

3. **`snapshot_overview_scope` — RUNNER ASSERTION DEFECT, not a product defect.**
   Trigger: runner expects overview interval key `"1d"`; vnpy's own `Interval` enum (`vnpy/trader/constant.py:158`) defines `DAILY = "d"`, not `"1d"`. The product's `get_bar_overview()` correctly reports `Interval.DAILY` (value `"d"`), matching the vnpy core contract this whole plugin is bridging to. The runner's expectation string is wrong, not the product's enum value. Minimal fix (not applied): correct the runner's expected key from `"1d"` to `"d"` (or compare against `Interval.DAILY.value`).

No edits were made to the runner or product for any of the three; each disposition is independently reproduced and evidenced above without modifying `tools/delivery_etf_loop.py` or any `vnpy_researchstore`/`research_store` source.

## New findings

**0 new in-scope regressions found** (bound was ≤3). No speculative findings were raised for the unknown-suffix/bare-unknown-label distinction or the Alpha-diagnostics asymmetry — both are contractually distinct, correctly tested, and already disclosed as known limits rather than silent defects.

## Explicitly out of scope (unchanged, not touched, not approved by this review)

Recording02I calendar/null corrections, 03D recording-launcher B1 repair, futures04L, capture recovery, full delivery04F extended real loop, 03D installed entrypoints, full WP10 delivery, whole v0.1 acceptance.

## FINAL_VERDICT: PASS

All three qualified04-accepted regressions (F1/F2/F3) are CLOSED with independently reproduced evidence and passing scoped tests (152/152). Native06 real-symbol identity resolution is PASS against the real read-only snapshot for normal `510130`/`510300` + `Exchange.SSE` and both `ResearchAlphaLab` methods, with compound vendor-suffixed symbols confirmed diagnostic-only (never required for success). All three bounded 04F failing assertions are runner/helper defects in `tools/delivery_etf_loop.py`, not product defects, each independently reproduced with precise trigger evidence. All 53 tracked input hashes are unchanged before and after. No product/test/config/Git/memory/store mutation occurred; only temporary review artifacts were created under `.coordination/review-qualified-native06/`.