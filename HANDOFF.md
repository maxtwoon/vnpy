---
task: A101 - Fix SimNow readiness gate soft-quota/docstring mismatch and None-passes-as-True gap (2nd re-audit H-NEW-2)
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-22
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/validation.py
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

`diagnostics_ai_stock_review_report_2026-07-22b.md` (the SECOND comprehensive re-audit, run after A98/A99/A100
closed the first re-audit's findings) flagged **H-NEW-2**: `SimNowReadinessChecker.check_readiness()`
(`chan_strategy/validation.py`) has two related problems in the same function.

**claude-code independently re-verified both by reading the code** (re-verify yourself in case line numbers
have drifted):

**Problem 1 — docstring implies all 10 conditions gate readiness; only 4 actually do:**

- The docstring (`validation.py:879-892`) lists 10 numbered conditions under "条件:" (conditions) with
  `[OK]/[NG]` framing, reading as if satisfying the list is what determines readiness — with no
  qualification that only some are mandatory.
- The actual `ready` computation (`validation.py:989-1011`):
  ```python
  passed_count = sum(1 for c in checks.values() if c["passed"] is True)
  ...
  signal_stable = (
      checks.get("增量一致性检查", {}).get("passed") is not False
      and checks.get("无重绘检查", {}).get("passed") is not False
      and checks.get("冻结快照确定性检查", {}).get("passed") is not False
  )
  enough_trades = checks.get("交易样本>=100", {}).get("passed") is not False
  return {..., "ready": passed_count >= 7 and signal_stable and enough_trades}
  ```
  Only 4 of the 10 checks (增量一致性检查/无重绘检查/冻结快照确定性检查/交易样本>=100) individually gate
  `ready` via `signal_stable`/`enough_trades`. The other 6 — win_rate>=45%, profit_factor>=1.0,
  max_drawdown<=20%, sharpe>=0.3 (A99), 样本外表现, and 参数稳定性 (hardcoded `passed: None`, so it can
  never contribute a `True`) — only contribute to a `passed_count >= 7` quota. **Confirmed via a concrete
  scenario**: `win_rate=0.40` (fails the documented 45% requirement) with all other backtest metrics passing
  and all three stability checks passing yields `passed_count=8`, `signal_stable=True`,
  `enough_trades=True` → `ready=True` — i.e. a strategy can fail a metric the docstring lists as a numbered
  condition and still be reported ready. `run_validation.py:140` prints this `ready` value directly as the
  human-facing "可以进入SimNow仿真" conclusion; `diagnostics/simnow_backfill_pending_replays.py:81/90` and
  `diagnostics/simnow_replay_readiness.py:83` both branch on the same boolean.
- The inline comment immediately above `signal_stable`/`enough_trades` (`validation.py:993-998`, "进入仿真
  的硬门槛：... 任何一项失败都不应进入仿真。") is actually self-consistent with the code — it explicitly
  scopes itself to exactly the 4 conditions it lists just above it, not all 10. **The mismatch is between
  the docstring's unqualified 10-item numbered list and the code**, not between this inline comment and the
  code. Don't conflate the two when writing the fix — the inline comment is fine as-is.

**Problem 2 — an omitted (`None`) hard-gate check silently counts as passing, not "unknown":**

- `signal_stable`/`enough_trades` use `passed is not False` rather than `passed is True`. When an optional
  stability param is omitted (`incremental_consistency=None`, etc. — the default for all three, and what
  happens on `SimNowReadinessChecker().check_readiness(report)` with only the backtest report, e.g.
  `tests/unit/test_simnow_readiness_sharpe.py:20`), the corresponding `checks[...]` entry is set to
  `{"passed": None, ...}` (`validation.py:914-916` etc.) — and `None is not False` evaluates `True`, so an
  *untested* hard-gate condition is silently treated as *passing*.
- **Confirmed via repo-wide search this is not currently live**: the one production call site
  (`run_full_validation`, `validation.py:1233-1239`) always supplies all four values as real dicts with a
  concrete `passed: True/False` (never `None`) — `inc_result`/`rp_result`/`sf_result` come from
  `SignalValidator.validate_*` methods (`validation.py:563-570`, `1121-1130`) which always return a real
  dict, and `oos_result` similarly from `robustness.out_of_sample_test()` (`validation.py:1216`). The only
  other call site in the repo, `tests/unit/test_simnow_readiness_sharpe.py`'s `_sharpe_check`/
  `_sharpe_suggestions` helpers (added by A99), calls `check_readiness(report)` with everything else
  omitted, but neither of A99's 4 tests reads `result["ready"]` — so no existing test currently observes
  this gap either.

## Decision: fix both, but conservatively

**Problem 1 fix — documentation only, mirroring A99's precedent.** Do NOT change `passed_count >= 7` or
which checks feed the quota — there's no independently-verifiable evidence for what the "correct" quota
threshold should be, and changing it would be a real, higher-risk behavior change to a live promotion gate
(same reasoning A99 applied to the Sharpe threshold: the enforced behavior is the live production behavior;
fix the docstring to describe it accurately instead of guessing at a "more correct" gate). Rewrite the
docstring's "条件:" list to explicitly mark which 4 are individually mandatory (hard gates) and which 6 only
contribute to the `>=7-of-10` quota, matching the code's actual, already-well-commented intent (the inline
comment at `:993-998` already correctly documents the 4-item hard-gate set — the docstring just needs to
stop implying all 10 are equally mandatory).

**Problem 2 fix — a real, deliberate, narrowly-scoped behavior change, following the A97 fail-closed
precedent.** Change `is not False` to `is True` for the three `signal_stable` conditions and `enough_trades`
in `validation.py:999-1004` only. Reasoning:
1. This mirrors A97's rationale exactly: a hard gate should not silently pass on missing/unproven
   information ("not yet proven safe" should mean "not ready," not "ready by default"). The current
   `is not False` treats "we never checked this" the same as "this passed," which is the same shape of bug
   A97 fixed for `rollover_open_gating`.
2. **Verified safe for the one production call site** (Background, Problem 2) — `run_full_validation` always
   supplies concrete non-None dicts for all four, so `is not False` and `is True` are behaviorally identical
   there; this change only tightens the not-currently-triggered direct-call path.
3. This does NOT touch `passed_count`/the `>=7` quota logic — only the 4 hard-gate booleans.

## Goal

1. Rewrite `check_readiness`'s docstring (`validation.py:879-892`) to distinguish the 4 mandatory hard-gate
   conditions (1-4: 增量一致性检查/无重绘检查/冻结快照确定性检查/交易样本>=100) from the 6 that only
   contribute to the `passed_count >= 7` quota (5-10) — state the quota threshold explicitly (e.g. "条件
   5-10 中至少需通过 7/10（含条件1-4）" or similar, phrase it however reads clearest, just be accurate and
   explicit about which is which). Re-verify the exact current wording/numbering yourself in case it's
   drifted from what's quoted in Background.
2. **Do not touch the inline comment at `:993-998`** — it's already accurate (scoped to exactly the 4 items
   it lists); don't inflate or rewrite it.
3. **Do not touch `passed_count >= 7`** or add/remove any check from `checks{}` or from what feeds
   `passed_count` — the quota mechanism and its threshold are unchanged, only documented accurately.
4. Change `validation.py:999-1004`'s four `is not False` comparisons to `is True` (three inside
   `signal_stable`, one for `enough_trades`). Re-verify surrounding structure before editing.
5. Add regression tests to `tests/unit/test_simnow_readiness_sharpe.py` (extending the existing A99 file,
   which already has the right imports/helpers for `SimNowReadinessChecker`) covering:
   - A quota-vs-hard-gate case: construct a report where `win_rate` fails (e.g. `0.40`) but every other
     backtest metric passes and all three stability checks + trade count pass (supply them explicitly, not
     omitted) → assert `ready is True` (documenting the INTENTIONAL soft-quota behavior — this is not a bug
     to "fix away," it's the accepted design once correctly documented) and that `passed_count` reflects the
     failing win_rate check correctly (i.e. one less than the all-pass case).
   - The None-passes-as-True regression (Problem 2, the actual fix): call `check_readiness` with a report
     and explicitly omit (or pass `None` for) the stability params → assert `ready is False` now (was `True`
     before this fix) since an unproven stability check must not silently pass. Use this to also confirm
     `test_simnow_readiness_sharpe.py`'s existing 4 tests (which never read `ready`) remain unaffected — run
     the full file, don't assume.
   - A positive case confirming `ready is True` is still reachable at all: full report with all four hard
     gates explicitly passing (not omitted) and enough quota checks passing.

## Acceptance Criteria

- [ ] `check_readiness`'s docstring explicitly distinguishes the 4 hard-gate conditions from the 6
      quota-contributing conditions and states the `>=7/10` threshold plainly.
- [ ] The inline comment at `:993-998` is unchanged (already accurate).
- [ ] `passed_count >= 7` and every check's membership in `checks{}`/`passed_count` is completely unchanged
      — verified in the diff.
- [ ] The four `is not False` → `is True` changes at `:999-1004` are the only logic change in this file —
      verified in the diff (everything else is docstring/comments).
- [ ] New regression tests added per Goal item 5, all passing; existing `test_simnow_readiness_sharpe.py`
      tests (from A99) still pass unchanged.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes (count increases only
      by the new tests added — note the exact delta in the Decision Log).
- [ ] `-m realdb` equivalence gate still passes unchanged (this task does not touch `backtest_engine.py`,
      `positions.py`, or `signals.py` — verify rather than assume per AGENTS.md rule, since `validation.py`
      may still be exercised somewhere in that gate; note the recurring pre-existing ULP float discrepancy
      from A98/A99/A100 if it recurs again — that's environment-specific and unrelated to this task).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] `ruff check` clean on touched files, or verify via diff against HEAD that any pre-existing lint-error
      count is unchanged (same pattern A99 used — `validation.py` had 45 pre-existing errors as of A99).
- [ ] VERSION/CHANGELOG bumped — CHANGELOG entry must clearly distinguish the two changes: (a) documentation
      clarification of the existing quota mechanism (no behavior change), and (b) the real, narrowly-scoped
      fail-closed behavior change for omitted stability checks (a hard-gate condition that was never tested
      now correctly blocks readiness instead of silently passing).
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.
- [ ] **Remember the `synccheck:ignore` marker** for any version-like string in this task's own HANDOFF
      notes.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **Two distinct changes in one task, each independently justified** — read the "Decision: fix both, but
   conservatively" section above in full. Problem 1 (docstring) is documentation-only, mirroring A99.
   Problem 2 (`is not False` → `is True`) IS a real behavior change, but a narrowly-scoped, well-justified
   one mirroring A97 — do not skip it or treat it as "just docs too."
2. **Do NOT change `passed_count >= 7`, which checks feed it, or the inline comment at `:993-998`.** Scope
   creep here (e.g. "let's also tighten the quota to 8" or "let's make win_rate a hard gate too") is
   explicitly out of scope — that would be guessing at intended policy with no independent evidence, exactly
   what this task's Decision Log explicitly avoids doing.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/WORK_LOG.md`, `diagnostics/simnow_20d_promotion_decision.md`, and any other SimNow-workstream
   files you see) — these belong to a concurrent, unrelated workstream. **Before committing, run
   `git status --short` and confirm only your own A101-scoped files are staged.**
4. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
5. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A101 SimNow readiness gate fix completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times out
   for environment reasons, do not manually hand-edit HANDOFF.md's stage/owner fields to bypass it — leave
   the working tree with your changes uncommitted and note the failure in the Decision Log; claude-code will
   verify and commit properly.
6. This is the sole High-severity finding from the second comprehensive re-audit
   (`diagnostics_ai_stock_review_report_2026-07-22b.md`); that report also flagged 4 Low findings
   (L-NEW-4 through L-NEW-7) that were NOT scoped as follow-up tasks — they're genuine but low-risk,
   defensive-coding gaps not currently triggered by any live call site, consistent with this project's
   practice of not chasing every Low finding into its own task.

## Decision Log

- 2026-07-22 (claude-code, design) - This is the sole High-severity finding from the SECOND comprehensive
  re-audit (after A98/A99/A100 closed the first re-audit's findings). Unlike the first re-audit's three
  follow-ups, this task combines a documentation fix (Problem 1, mirroring A99) with one narrowly-scoped
  real behavior change (Problem 2, mirroring A97) — both independently justified and both verified safe
  for the one live production call site before being scoped.
- 2026-07-22 (claude-code, design) - Explicitly did NOT scope a fix for whether win_rate/profit_factor/
  max_drawdown/sharpe/oos should become hard gates instead of quota-contributors — there's no independent
  evidence for what the "correct" policy is, and this project's consistent precedent (A95 M1, A96 M3, A99
  M-NEW-1) is to document actual behavior accurately rather than guess at intended behavior changes to a
  live gate.
- 2026-07-22 (claude-code, design) - Confirmed the inline comment at `validation.py:993-998` is NOT part of
  the reported mismatch — it already accurately scopes itself to the 4 hard-gate items only. The audit
  report's phrasing could be read as implicating this comment too; re-reading it directly, it does not
  claim all 10 checks are hard gates, only the 4 it explicitly enumerates. Recorded here so kimi doesn't
  waste time trying to "fix" a comment that isn't actually wrong.
- 2026-07-22 (claude-code, design) - Confirmed via repo-wide `grep` that only two call sites exist for
  `check_readiness`: the one production path (`run_full_validation`, always supplies concrete non-None
  values for all four hard-gate inputs) and A99's test helpers (never read `ready`) — so the Problem 2 fix
  is safe today and only tightens behavior for future/direct callers that omit stability params.
- 2026-07-22 (kimi-code, dev) - Implemented exactly as designed, no deviations. Re-verified line numbers
  before editing: docstring at `validation.py:879-893`, inline hard-gate comment at `:993-998` (untouched),
  `is not False` comparisons at `:999-1004`. Diff confirms the only logic change is the four
  `is not False` -> `is True` comparisons; everything else is docstring-only. `passed_count >= 7`, the
  `checks{}` membership, and the inline comment are byte-identical to HEAD.
- 2026-07-22 (kimi-code, dev) - Added 3 regression tests to `tests/unit/test_simnow_readiness_sharpe.py`:
  `test_readiness_quota_win_rate_failure_still_ready` (win_rate=0.40 fails its check yet ready=True,
  passed_count=8 — pins the INTENTIONAL soft-quota design), `test_readiness_untested_stability_check_blocks_ready`
  (two stability checks passing, signal_freeze omitted, everything else passing: passed_count=8 >= 7 but
  ready=False — the Problem 2 fail-closed regression; was True before the fix),
  `test_readiness_all_gates_passing_ready_true` (all hard gates explicitly passing: ready=True,
  passed_count=9). A99's 4 existing tests pass unchanged; not-realdb count 773 -> 776 (+3 net).
- 2026-07-22 (kimi-code, dev) - VERSION bumped 0.2.38 -> 0.2.39 (synccheck:ignore) with a CHANGELOG entry
  that explicitly separates (a) the documentation-only quota clarification from (b) the real fail-closed
  behavior change. `git status --short` verified only A101-scoped files modified by me; the two
  pre-existing SimNow-workstream files (`diagnostics/WORK_LOG.md`,
  `diagnostics/simnow_20d_promotion_decision.md`) were already modified before I started and were left
  untouched.
- 2026-07-22 (kimi-code, dev) - Environment note: `run_next_work.ps1` lives under
  `examples/czsc_strategy/diagnostics/` (not the czsc_strategy root); ran it from there. Ruff baseline
  comparison required extracting HEAD's validation.py via `cmd /c "git show ... > file"` because
  PowerShell 5.1 pipeline redirection mangles UTF-8 Chinese bytes (first attempt produced a corrupted
  stash that was safely popped back; working tree verified intact afterwards).

## Manual Verification

All commands run natively on Windows (PowerShell) from the repo root / `examples/czsc_strategy`.

1. Target test file (3 new + 4 A99 tests):
   ```
   PS> python -m pytest tests/unit/test_simnow_readiness_sharpe.py -q
   .......                                                                  [100%]
   7 passed in 0.23s
   ```
2. Full unit suite, not-realdb (773 -> 776, +3 net new tests, 4 realdb deselected):
   ```
   PS> python -m pytest tests/unit -q -m "not realdb"
   776 passed, 4 deselected in 46.35s
   ```
3. realdb equivalence gate (unchanged; the recurring A98/A99/A100 ULP float discrepancy did NOT recur):
   ```
   PS> python -m pytest tests/unit -q -m realdb
   4 passed, 776 deselected in 77.38s (0:01:17)
   ```
4. Both sync_check gates:
   ```
   PS> python tools/sync_check.py
   [SYNC-CHECK][OK] 版本单一真相 = 4.4.0  (source: vnpy/__init__.py::__version__)  # synccheck:ignore
   [SYNC-CHECK] PASS: 版本与文档一致
   PS> python tools/sync_check.py --root examples/czsc_strategy
   [SYNC-CHECK][OK] 版本单一真相 = 0.2.39  (source: VERSION::)  # synccheck:ignore
   [SYNC-CHECK] PASS: 版本与文档一致
   ```
5. Preflight (script located at `examples/czsc_strategy/diagnostics/run_next_work.ps1`):
   ```
   PS> .\run_next_work.ps1 -Preflight
   ==> Preflight complete; live SimNow capture was not requested
   exit=0  (SimNow workflow unit tests: 205 passed in 28.84s)
   ```
6. Ruff parity check (A99 pattern): HEAD `validation.py` extracted via `cmd /c "git show HEAD:... > tmp"`
   shows **45 errors**; current `validation.py` shows **45 errors** with an identical rule breakdown
   (25x UP006-list, 5x UP006-dict, 4x UP045, 2x UP035, 8x F401, 1x B905) — zero new lint errors;
   `test_simnow_readiness_sharpe.py` is fully clean ("All checks passed!").
7. Diff scope verification: `git diff examples/czsc_strategy/chan_strategy/validation.py` contains only
   (a) the docstring rewrite and (b) the four `is not False` -> `is True` lines; the inline comment at
   `:993-998`, `passed_count >= 7`, and all `checks{}` entries are unchanged. `git status --short` shows
   only the four A101 files plus the two pre-existing, untouched SimNow-workstream files.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-22 | claude-code → claude-code | design → design | A101 (SimNow readiness gate fix, 2nd re-audit H-NEW-2) scoped; drafting design brief |
| 2026-07-22 | claude-code → kimi-code | design → dev | A101 promoted design->dev |
| 2026-07-22 | kimi-code → codex | dev → review | A101 SimNow readiness gate fix completed |
