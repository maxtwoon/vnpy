Review complete. No product/config/git changes were made — only the temporary repro script in `.coordination/review-consumers03/` (untracked, as required). Here is the final report:

---

# Claude Code — consumers03 review (independent, read-only)

Date: 2026-09-16. Reviewer: actual Claude Code (Sonnet 5), independent, read-only.
Package root: `D:/repo/vnpy/integrations/vnpy_researchstore`. Executable: package `.venv/Scripts/python.exe`.
Dispatched per `TASK_CLAUDE_CONSUMERS_03.md` after `.coordination/opencode-consumers02c-handoff.md` (actual OpenCode, quota exit1 on the *process*, not on the work — handoff and test evidence are real and not discarded). No product/dependency/config/git/memory writes. Only artifact created: `.coordination/review-consumers03/repro_default_qualified_gap.py` (untracked, temporary).

## Verdict: **PARTIAL** for this bounded consumers03 scope

The consumer-path code (importer/CLI/quality/export/datasource) matches what the handoff claims and its own tests pass (reran `tests/test_default_qualified.py`, `tests/test_dominant_overlay.py`, `tests/test_export.py` independently: 14 passed). Item 2 (real 3×10 Client store loop) and item 3 (gap_ns round trips, CLI recover surfacing) check out against existing evidence with no new defect found. But item 1 — the priority focus of this task — is a real, confirmed enforcement gap, not merely a documentation nuance.

## Finding 1 (Priority: HIGH) — `store_default_qualified` is reporting-only; no public data-read path actually excludes/refuses repaired or disputed rows

**Path:** `research_store/quality.py:44` (`DEFAULT_EXCLUSION_FLAGS`), `:326` (`store_default_qualified`), `:413` (`store_quality` embeds it) — vs. `research_store/reader.py:35` (`_QUARANTINE_CODES = {"same_key_different_values"}`), `:94-134` (`_check_gaps`, the *only* place `SnapshotReader.bars()`/`ticks()` can refuse a query).

**Trigger:** Publish a dataset containing a row carrying `repaired_deterministic` or `disputed_upstream_refetch*` provenance (the full 133-key policy target), then read it through any public backtest path: `freeze()` → `SnapshotReader.bars()` (programmatic) or `freeze` → `export` (CLI). `_check_gaps` only inspects `quality_decisions` whose `code` is in `_QUARANTINE_CODES` (`same_key_different_values`, i.e. overlay conflicts) — it never looks at `field_quality`/repair flags. `freeze()` itself (`snapshots.py`) only fails on `unresolved_issues`, which repaired/disputed rows never raise (they publish straight to `state=published`).

**Proof (independent, not reused from the handoff):**
```
$ .venv/Scripts/python.exe .coordination/review-consumers03/repro_default_qualified_gap.py
publish state: published (no conflict raised for repaired/disputed rows)
store_default_qualified(): {"excluded_by_flag": {"disputed_upstream_refetch": 1, "repaired_deterministic": 1}, "rows_excluded": 2, "rows_qualified": 1, "rows_total": 3}
store_quality has default_qualified key: True
freeze() OK, snapshot_id= snap-cab927ec24ae2887 , allow_known_gaps=() -- no gap needed
reader.bars() returned 3 rows (expected 3, including the 2 excluded-by-report rows):
 - 2017-09-19 13:01:00   (repaired_deterministic — reported excluded)
 - 2017-09-19 13:02:00   (disputed_upstream_refetch — reported excluded)
 - 2017-09-19 13:03:00
```
`store_default_qualified()` correctly *counts* both excluded rows with real bounds and preserved candidates — that part of the handoff's claim is accurate. But `freeze()` needed **zero** `allow_known_gaps` and `reader.bars()` returned **all 3 rows, unfiltered**, with no `CoverageGapError`. Confirmed system-wide: `grep -rn "default_qualified|repaired_deterministic|disputed_upstream_refetch|DEFAULT_EXCLUSION"` across `research_store/export.py`, `research_store/cli.py`, and the entire native package `../vnpy_researchstore/vnpy_researchstore/*.py` (incl. `native_common.py`, hash `58762f64…`) returns **zero matches** — no CLI verb, no export path, no native `resolve_bar_dataset`/`load_bars` admission layer consumes these flags anywhere. There is no CLI query/bars verb at all (`cli.py` only exposes `freeze`+`export`+`quality`/`coverage`/`report`), so `quality` is the *only* place this policy is visible, and it is read-only reporting.

This matches — and now concretely confirms — the gap already admitted in `.coordination/consumer-core-requests.md:24-35`: *"native admission enforcement belongs to the native owner... If central enforcement is wanted later, a core-level qualification marker would be a new request — none is being made now."* The risk is the `quality.py` module docstring (`:8-16`, "DEFAULT QUALIFIED BACKTEST DATA excludes ALL repaired keys") and the `store_default_qualified` docstring (`:335`, "usable directly as `KnownGap` intervals") read as if exclusion is already active; a caller who only reads the docstring/`quality` JSON output, not the reader/freeze source, would reasonably (and wrongly) believe repaired/disputed rows are refused from a "qualified" backtest today. They are not — every existing public read/export path returns them like any other row.

**Smallest complete correction:** either (a) wire `_default_qualified_accumulator`'s per-row gap list into `freeze()`'s quarantine set (extend `_QUARANTINE_CODES`-equivalent handling in `reader._check_gaps` to also consult `field_quality` flags, or have `store_default_qualified`'s gaps registered as `quality_issues` before freeze), giving an explicit `--qualified-only` freeze/export mode that actually raises/omits; or (b) if enforcement is intentionally deferred to the native admission layer (per the consumer-core-requests.md position), reword the `quality.py` docstring and `store_default_qualified` docstring from "excludes"/"policy" to explicitly "reports; does not filter reads — see \[native owner\] for actual admission," so the gap isn't discoverable only by reading source. Either fix is small; the current state — code says "excludes," behavior doesn't — is the defect.

**Owner:** native admission layer owner (per consumer-core-requests.md's own routing) for (a), or the quality.py doc author for (b) if enforcement stays out of scope.

## Items 2 & 3 — spot-checked, no new defect found (PASS, not re-litigated in depth)

- **Item 2 (target=store real Client loop):** `.coordination/opencode-consumers02c-realstore-evidence.json` exists, structurally matches the claimed 3-case shape (dataset/batch/snapshot ids, `verified_rows:10`, `readback:"research_store"`, `idempotent_replay:true`, `metadata_preserved:true`, `values_equal_no_reconversion:true` for all 3 files) and cites the same registry hash (`7442f141…`) as `REAL_INPUT_CANDIDATES.md`. Not independently re-executed against network-free Client JSON in this bounded pass (existing evidence sufficient per task's "may reuse exact-code developer results when sufficient"); no contradiction found.
- **Item 3 (gap_ns/export/CLI integrity):** `tests/test_dominant_overlay.py` (includes the 1ns-narrow-allowance refusal and exact-`gap_ns`-succeeds cases) and `tests/test_export.py` rerun independently — 14/14 pass, consistent with the handoff's claims.

## Remaining real-delivery limits (unchanged, not new defects)

Full historical import not executed, 10.22GB SSQuant capture not executed, source-time uncertainties open, WP10 delivered Database/Alpha loop not done, recording verbs (`recover-session`/`seal`/`replay`) honestly `pending_capability` — all as stated in the handoff; this review does not relabel these as new defects.

Not claiming v0.1 complete.
