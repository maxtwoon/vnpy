All confirmed reproducible and stable. Everything checks out consistently with my earlier analysis. Here is the final independent review.

---

# Claude Code — qualified-recheck04 (independent, read-only)

Date: 2026-09-17. Reviewer: actual Claude Code (Sonnet 5), independent, read-only.
Package root: `D:/repo/vnpy/integrations/vnpy_researchstore`. Executable: package `.venv/Scripts/python.exe`. Lint: Studio `ruff` (`D:/veighna_studio/python.exe -m ruff`, read-only). Dispatched per `TASK_CLAUDE_QUALIFIED_RECHECK_04.md` after `.coordination/kimi-qualified-fix04-handoff.md` (exit0, attempt2). No product/dependency/config/git/memory writes. Only artifact created: `.coordination/review-qualified04/repro_wider_scope_clean_range.py` (untracked, temporary). All 20 files in `claude-qualified04-input-hashes.json` re-verified byte-identical at review time (`NONE` mismatched) — inputs are stable as claimed.

## Verdict: **OPEN** for this accepted defect — **FINAL_VERDICT: FAIL**

The original accepted HIGH defect (`store_default_qualified` reporting-only; no public read path actually excluded repaired/disputed rows) **is fixed at the core store→freeze→`SnapshotReader`/CLI-export layer** — independently reconfirmed below. But the correction introduces a new HIGH-severity regression in exactly the two consumer paths the dispatch explicitly named for scrutiny (native `Database` and **both** `ResearchAlphaLab` load methods), plus one binding-contract violation each in freeze-transaction scope and legacy-manifest handling. Per the task's own bar ("Documentation-only deferral... do not meet the binding approved requirement" / "clean query windows remain usable"), this does not close as a clean PASS.

## Core-path fix: confirmed working (re-verified independently)

Command: `.venv/Scripts/python.exe .coordination/review-consumers03/repro_default_qualified_gap.py` (original file, hash `544e43a4ae...` unchanged, not modified by this review):
```
publish state: published (no conflict raised for repaired/disputed rows)
store_default_qualified(): {"rows_excluded": 2, "rows_qualified": 1, "rows_total": 3, ...}
freeze() OK, snapshot_id= snap-6b9468b125b88856 , allow_known_gaps=() -- no gap needed
CoverageGapError: query over ds-... intersects default-qualified exclusion [...] (160105.XSHE @ 2017-09-19 13:01:00, flags ['repaired_deterministic']); ...
```
`reader.bars()` now refuses instead of silently returning all 3 rows — the original gap is closed at this layer. Scoped suite reconfirmed: `pytest tests/test_default_qualified.py tests/test_native_database.py tests/test_native_alpha.py tests/test_cli.py tests/test_export.py tests/test_dominant_overlay.py tests/test_snapshot_freeze.py tests/test_core_reader.py` → **73 passed**. `ruff check` on the 9 changed files → clean. `mypy` on the 8 changed core/native modules → clean.

## Regression 1 (HIGH) — native `Database`/`ResearchAlphaLab` reject clean date ranges whenever the SAME symbol has an exclusion anywhere else in its history

**Path:** `vnpy_researchstore/native_common.py:270-276` (`resolve_bar_dataset`) calls `reader.bars(entry.dataset_id, instruments=[symbol], required_fields=(), allow_missing_auxiliary=True)` with **no `start`/`end`** for its exchange-label validation scan. `reader.py:107-186` (`_check_gaps`) with `start_ns=start_ns=None`/`end_ns=None` never satisfies either skip condition (`start_ns is not None and ...` / `end_ns is not None and ...`), so it raises `CoverageGapError` on the **first** exclusion found anywhere in the dataset — regardless of the caller's actual requested window.

**Independent repro** (`.coordination/review-qualified04/repro_wider_scope_clean_range.py`, hash `025637622132e3649f34f147d4339abf5c4241b97ef9452864257ab5107994f1`): one daily dataset, instrument `000009`, 5 trading days; only day 1 (`2024-01-02`) carries `repaired_deterministic`; days 3-4 (`2024-01-04`..`2024-01-05`) are completely clean.
```
excluded_day=2024-01-02 clean_range=[2024-01-04,2024-01-05]
PASS core reader.bars() over clean range succeeded, rows = 2
FAIL native Database.load_bar_data() over clean range raised CoverageGapError: ...
FAIL ResearchAlphaLab.load_bar_data() over clean range raised CoverageGapError: ...
FAIL ResearchAlphaLab.load_bar_df() over clean range raised CoverageGapError: ...
```
The core reader (properly range-scoped) reads the clean window fine; **all three** native entry points fail on it. Since the policy target is "ALL 133 repaired ETF keys" (i.e., essentially every instrument in scope is expected to carry at least one exclusion somewhere in its history by design), this makes native `Database.load_bar_data` and **both** `ResearchAlphaLab.load_bar_data`/`load_bar_df` unusable for their primary intended dataset — directly violating the dispatch's explicit requirement ("clean query windows remain usable") and its named test scenario ("native Database and BOTH Alpha clean-range reads when another range of the same symbol contains excluded rows"). Not caught by `verify_qualified_fix04.py` because its fixture keeps excluded and clean rows in the same single-day window (no separated range case).

## Regression 2 (MEDIUM/HIGH) — freeze() now holds the catalog lock across full Parquet scans, violating the "SHORT read transaction" contract

**Path:** `research_store/snapshots.py:67-160`. The `with store.catalog.transaction():` block (confirmed via raw indentation inspection) now contains the call to `scan_default_qualified_exclusions` (`snapshots.py:129-142`), which itself does per-file manifest hash verification and full `pq.read_table(...)` reads (`quality.py:293-322`) for every file in every selected partition — **inside** the transaction. `catalog.py:164-184` shows `transaction()` holds `self._lock` (a process-level `threading.Lock` serializing the single sqlite connection, per its own docstring) for the entire `with` body. This directly contradicts the task's explicit binding requirement: "large Parquet scans, if necessary, should operate on the captured immutable file list outside that transaction rather than rereading mutable heads or holding a DB transaction for a full-history scan." Pre-fix, `freeze()`'s transaction only issued catalog `SELECT`s; this is new behavior introduced by qualifiedfix04, proportional to selected data volume, and blocks all other catalog operations sharing that `Catalog`/lock instance (including concurrent publishes) for the scan's duration.

## Regression 3 (MEDIUM) — legacy (pre-policy) manifests are silently indistinguishable from verified-clean ones

**Path:** `research_store/snapshots.py:31` (`SNAPSHOT_FORMAT = 1`, unbumped despite the new manifest field) plus `reader.py:98-105` (`default_qualified_exclusions()` returns `[]` both when the key is absent and when it is present-but-empty). `tests/test_default_qualified.py:420-439` (`test_pre_policy_snapshot_manifest_keeps_prior_meaning`) confirms by design: a legacy manifest missing the capture key "still returns every pinned row" with **no distinguishing signal** exposed to any caller. This is exactly the outcome the dispatch named as unacceptable: "If an older manifest lacks policy metadata, it must be recognizably observational/unqualified or explicitly refused for default native qualified use; silently presenting legacy permissive rows as qualified would leave the defect open." There is no version bump, flag, or diagnostic that lets a native/CLI caller tell a pre-fix snapshot apart from a post-fix snapshot that legitimately has zero exclusions.

## Explicitly checked and PASS (not re-litigated in depth)

- Deterministic-matching repair AND disputed repair both excluded by default (core level) — confirmed via original repro + scoped suite.
- Explicit `allow_known_gaps` allowance leaves the excluded row absent (never filled) — `test_explicit_gap_allowance_keeps_excluded_rows_absent` passed; matches the "allowance permits the interval, never the row" contract.
- Observational access (`include_default_excluded=True`) stays distinguishable and separate from default qualified reads — code-reviewed, test-covered, unchanged.
- Immutable-snapshot content: snapshot id remains content-derived; identical captures dedupe (`snapshots.py:186-194`).
- No git/product/memory mutations by this review; all 20 captured input hashes verified unchanged before and after this session.

## FINAL_VERDICT: FAIL

Reason: the accepted defect is closed at the core store/freeze/reader/CLI-export layer, but the same correction breaks native `Database` and both `ResearchAlphaLab` load paths for clean query windows (Regression 1 — directly the scenario this task named), and separately violates two binding implementation contracts from the dispatch (short-transaction freeze scope; legacy-manifest recognizability). This is not a documentation nuance — it is a newly introduced functional break in the consumer paths the task required to be exercised, so the correction is not ready to accept as-is.