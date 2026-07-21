---
task: A99 - Reconcile Sharpe-ratio threshold inconsistency in SimNow readiness gate (re-audit M-NEW-1)
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-22
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/validation.py
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
  - examples/czsc_strategy/tests/unit/test_simnow_readiness_sharpe.py
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

`diagnostics_ai_stock_review_report_2026-07-22.md` (the post-A97 comprehensive re-audit) flagged
**M-NEW-1**: the Sharpe-ratio threshold used by the SimNow readiness gate is stated as three different
numbers in three places that all describe the *same* gate:

- `chan_strategy/validation.py:890` — `SimNowReadinessChecker.check_readiness`'s docstring:
  `"8. 夏普比率 >= 0.5 [OK]/[NG]"`
- `chan_strategy/validation.py:964-967` — the actual enforced check:
  ```python
  sharpe = backtest_report.get("sharpe_ratio", 0)
  checks["夏普比率>=0.3"] = {
      "passed": sharpe >= 0.3,
      "value": f"{sharpe:.2f}",
  }
  ```
- `chan_strategy/validation.py:1341,1343` — `generate_optimization_suggestions`:
  ```python
  if sharpe < 0.5:
      suggestions.append(f"夏普比率偏低({sharpe:.2f}<0.5): 策略风险调整后收益不佳")
  ```

**claude-code independently confirmed** (re-verify yourself in case line numbers drifted):

- `git log -p --follow -- chan_strategy/validation.py` shows all three references were introduced together
  in the same original commit, with no divergent edit history since — this reads as a same-day
  copy/typo inconsistency (docstring said 0.5, the check itself was written as 0.3, and the suggestion
  generator's warning threshold was copied from the docstring's 0.5 rather than the actual check), not a
  deliberate later change to one of the three that the others just never caught up to.
- Every other metric in the same gate (`total_trades>=100`, `win_rate>=45%`, `profit_factor>=1.0`,
  `max_drawdown<=20%`) uses the identical numeric threshold in both its `checks[...]` entry and its
  matching `generate_optimization_suggestions` warning — Sharpe is the only metric where the check and
  the suggestion disagree.
- No design doc, changelog entry, or `docs/` reference documents an intentional 0.3-vs-0.5 distinction
  between "the enforced gate" and "the suggestion warning" for Sharpe specifically.
- **No existing test exercises either `SimNowReadinessChecker.check_readiness` or
  `generate_optimization_suggestions` at all** — confirmed via repo-wide search
  (`grep -rn "check_readiness\|generate_optimization_suggestions\|SimNowReadinessChecker" tests/`) —
  so there is no test today pinning either number that a fix could break.
- For any real strategy report with `0.3 <= sharpe_ratio < 0.5`, `run_full_validation` (which calls both
  functions against the same report) currently prints `[OK] 夏普比率>=0.3` in the readiness section
  (contributing to `passed_count`, i.e. actively counted as a passing gate toward SimNow readiness) while
  simultaneously emitting a `夏普比率偏低(...<0.5)` warning in the optimization-suggestions section —
  self-contradictory output for the same report.

## Decision: which number wins

This is a real, already-enforced production gate (it decides whether a strategy is "ready" for SimNow, a
real-money-adjacent promotion decision) — same category of risk as A97's `rollover_open_gating`, so a
numeric-behavior change here is not something to make lightly, and NOT to be confused with A95's M1 fix
(which was purely a naming/docstring clarification with zero behavior change).

**Decision: reconcile the docstring and the suggestion generator to match the ALREADY-ENFORCED check
(0.3), not the other way around.** Reasoning, recorded here so kimi doesn't need to re-litigate it:

1. `checks["夏普比率>=0.3"]` is the actual, currently-live production behavior — it is what has already
   been used (and, per this repo's own concurrent SimNow-workstream artifacts, is presumably still being
   used) to evaluate real strategy reports. Tightening it to 0.5 would be a silent, retroactive behavior
   change to an active gate with no design rationale recorded anywhere for why 0.5 was the "true" intended
   value over 0.3 — the only evidence for 0.5 is that a docstring and a suggestion-message string happen to
   also say 0.5, which is exactly consistent with "0.5 was an early draft number that the check itself was
   later tuned down from, and the other two references were simply never updated to match."
2. Changing the *enforced* threshold is the higher-risk, harder-to-reverse move (it could flip a real
   report's pass/fail from a currently-passing state) with no clear evidence it's what was originally
   intended; changing the two *descriptive* references to match the enforced value is a pure documentation
   fix with zero behavior change — the same conservative posture this project has consistently taken (A95's
   M1, A96's M3) when the "true" intended value/design isn't independently verifiable.
3. If a human maintainer later determines 0.3 genuinely was the bug and 0.5 was intended, tightening the
   gate is a one-line follow-up change they can make deliberately, with the contradiction already resolved
   and the two now-consistent descriptive references making the intended change obvious and easy to review.

## Goal

1. Change `chan_strategy/validation.py:890`'s docstring line from `"8. 夏普比率 >= 0.5 [OK]/[NG]"` to
   `"8. 夏普比率 >= 0.3 [OK]/[NG]"` — matching the actual `checks["夏普比率>=0.3"]` key/threshold exactly.
2. Change `chan_strategy/validation.py:1341,1343`'s suggestion-generator threshold from `0.5` to `0.3` (both
   the comparison `if sharpe < 0.5:` and the message string `f"...({sharpe:.2f}<0.5)..."` — update both to
   `0.3` consistently, matching the pattern every other metric in this function already follows (compare to
   the win_rate/profit_factor/max_drawdown blocks immediately above/below it, lines ~1322-1338).
3. **Do NOT touch `checks["夏普比率>=0.3"]`'s actual threshold** (`validation.py:964-967`) — that stays
   exactly `0.3`, unchanged. This task is documentation/message reconciliation only, matching the wording to
   already-enforced behavior — it is explicitly NOT a production-gate tightening. Re-read the Decision Log
   entry above before touching anything if this isn't clear.
4. Add a new test file `tests/unit/test_simnow_readiness_sharpe.py` covering what has zero coverage today:
   - `SimNowReadinessChecker.check_readiness` with `sharpe_ratio=0.3` exactly → `passed=True` (boundary
     pinned at the documented threshold).
   - `check_readiness` with `sharpe_ratio` just below 0.3 (e.g. `0.29`) → `passed=False`.
   - `generate_optimization_suggestions` with `sharpe_ratio=0.3` → no Sharpe-related suggestion is
     generated (since it now passes at exactly the same boundary the check uses).
   - `generate_optimization_suggestions` with `sharpe_ratio` just below 0.3 (e.g. `0.29`) → the Sharpe
     suggestion IS generated, and its message text says `<0.3` (not `<0.5`).
   Look at `chan_strategy/validation.py`'s existing docstring/signature for both functions to construct
   minimal valid `backtest_report`/`validation_results` dict fixtures — only the fields these two functions
   actually read are required (e.g. `sharpe_ratio`, plus whatever `check_readiness`/
   `generate_optimization_suggestions` unconditionally access — read the full function bodies before writing
   the fixture, don't guess at required keys).

## Acceptance Criteria

- [x] `validation.py:890`'s docstring says `>= 0.3`, matching the actual check.
- [x] `validation.py:1341,1343`'s suggestion generator uses `0.3` (both the comparison and the message
      string), matching the actual check.
- [x] `checks["夏普比率>=0.3"]` itself (the dict key name AND its `0.3` threshold) is completely unchanged —
      verified in the diff.
- [x] New test file added covering the four cases in Goal item 4, all passing.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes (count increases only
      by the new tests added — note the exact delta in the Decision Log).
- [x] `-m realdb` equivalence gate verified unaffected by A99 — `validation.py` is NOT exercised by the
      failing test; the one failure (`test_research_mode_equivalence_to_baseline`, last-ulp float repr vs
      stored snapshot) reproduces identically on unmodified HEAD code (control run in Manual Verification
      item 3). Pre-existing environmental issue, out of A99 scope, flagged for review.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [x] `ruff check` clean on touched files — new test file fully clean; `validation.py` has 45
      pre-existing errors byte-identical to the HEAD baseline, zero introduced by this diff.
- [x] VERSION/CHANGELOG bumped — CHANGELOG entry must state this is a **documentation/message
      reconciliation, not a change to the enforced SimNow readiness gate** (the enforced threshold stays
      0.3) — be explicit about this distinction so a future reader doesn't mistake it for a gate-tightening.
- [x] Include a literal `## Manual Verification` heading with natively-run command output.
- [x] **Remember the `synccheck:ignore` marker** for any version-like string in this task's own HANDOFF
      notes.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **This is documentation/message-only — the enforced gate value (0.3) does not change.** Read the
   Decision Log section above in full before touching anything; do not "fix" this by changing the enforced
   check to 0.5 instead — that was explicitly considered and rejected as the higher-risk option.
0. **`tests/unit/test_simnow_readiness_sharpe.py` is intentionally NOT in the `deliverables` list yet** —
   `sync_check.py` requires every listed deliverable to already exist on disk, and this is a new file that
   doesn't exist until you create it. Add it to the `deliverables` list yourself once you've created it
   (same pattern A97 used when it extended its own deliverables list for an unplanned second test file).
2. **Scope is exactly two edits** (the docstring line, and the suggestion-generator's comparison + message)
   plus one new test file. Do not touch `checks["夏普比率>=0.3"]`, any other metric's threshold in either
   function, or anything else in `validation.py`.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/WORK_LOG.md`, `diagnostics/simnow_20d_promotion_decision.md`, and any other SimNow-workstream
   files you see) — these belong to a concurrent, unrelated workstream. **Before committing, run
   `git status --short` and confirm only your own A99-scoped files are staged.**
4. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
5. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A99 Sharpe threshold reconciliation completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times out
   for environment reasons, do not manually hand-edit HANDOFF.md's stage/owner fields to bypass it — leave
   the working tree with your changes uncommitted and note the failure in the Decision Log; claude-code will
   verify and commit properly.

## Decision Log

- 2026-07-22 (claude-code, design) - This is the second of three follow-up tasks from the 2026-07-22
  re-audit (H-NEW-1 closed via A98; this is M-NEW-1; M-NEW-2 will be scoped as a third follow-up task once
  this one closes).
- 2026-07-22 (claude-code, design) - Full reasoning for reconciling toward 0.3 (not 0.5) is recorded in the
  "Decision: which number wins" section above — key point: the enforced check is the live production
  behavior; the docstring/suggestion are the ones out of sync with it, and there is no recorded rationale
  anywhere establishing 0.5 as the deliberately intended value. This mirrors A95's (M1) and A96's (M3)
  precedent of not changing behavior when true intent isn't independently verifiable.
- 2026-07-22 (claude-code, design) - Confirmed via `git log -p --follow` that all three references were
  introduced in the same original commit with no divergent history — this is a same-day
  copy-paste/inconsistency, not a considered later change to one of the three values.
- 2026-07-22 (claude-code, design) - Confirmed via repo-wide search that neither
  `SimNowReadinessChecker.check_readiness` nor `generate_optimization_suggestions` has ANY existing test
  coverage — this task adds the first tests for either function, not just a regression test for this one
  fix.
- 2026-07-22 (kimi-code, dev) - Implemented exactly the two scoped edits: `validation.py:890` docstring
  `>= 0.5` -> `>= 0.3`, and `generate_optimization_suggestions` comparison `sharpe < 0.5` -> `sharpe < 0.3`
  plus message `<0.5` -> `<0.3`. `checks["夏普比率>=0.3"]` (key + threshold) untouched — verified in diff:
  exactly 3 lines changed (3 insertions / 3 deletions). New test file
  `tests/unit/test_simnow_readiness_sharpe.py` added with the 4 boundary cases from Goal item 4; added to
  `deliverables` after creation per Note 0.
- 2026-07-22 (kimi-code, dev) - VERSION bumped 0.2.36 -> 0.2.37 (synccheck:ignore) with a CHANGELOG entry
  that explicitly states this is a documentation/message reconciliation, NOT a change to the enforced
  SimNow readiness gate (enforced threshold stays 0.3).
- 2026-07-22 (kimi-code, dev) - Unit suite `-m "not realdb"`: 768 -> 772 passed, delta exactly +4 (the new
  tests; baseline 768 per A98's changelog).
- 2026-07-22 (kimi-code, dev) - `-m realdb` gate: 3 passed, 1 failed —
  `test_position_sizing_research_equivalence.py::test_research_mode_equivalence_to_baseline` fails on a
  float-precision mismatch vs the stored snapshot (`sharpe_ratio: baseline=0.8091974663759458
  actual=0.809197466375945`). Verified PRE-EXISTING and unrelated to A99: (a) that test imports only
  `chan_strategy.backtest_engine` / `chan_strategy.config` — `validation.py` is never exercised; (b)
  re-ran it with `validation.py` temporarily reverted to HEAD (A99 edits stashed aside) — identical
  failure; (c) A99's diff touches docstring/message text only, no numeric behavior. The snapshot was
  evidently generated under a different numeric environment. Out of A99 scope (task forbids touching
  `backtest_engine.py`/`positions.py`/`signals.py`); flagged here for claude-code review instead of
  silently regenerating the snapshot.
- 2026-07-22 (kimi-code, dev) - ruff: new test file is clean; `validation.py` reports 45 pre-existing
  lint errors — verified identical to the HEAD baseline (`git show HEAD:...validation.py` -> same 45
  errors), i.e. zero new lint introduced by this diff. Did not auto-fix the pre-existing ones (would be
  a 42-line out-of-scope refactor).

## Manual Verification

Environment: repo-root `python` for sync_check/handoff; `D:\repo\vnpy\.venv_new\Scripts\python.exe`
(pytest 9.1.1 — synccheck:ignore) for pytest; system `ruff` for lint. All commands run natively on
Windows from `D:\repo\vnpy` unless noted.

1. New tests (4 boundary cases):

   ```text
   $ .venv_new\Scripts\python.exe -m pytest examples/czsc_strategy/tests/unit/test_simnow_readiness_sharpe.py -q
   ....                                                                     [100%]
   4 passed, 2 warnings in 0.09s
   ```

2. Full unit suite, not realdb (768 -> 772, delta = exactly the 4 new tests):

   ```text
   $ .venv_new\Scripts\python.exe -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
   772 passed, 4 deselected, 2 warnings in 46.22s
   ```

3. realdb equivalence gate (1 pre-existing environmental failure, proven not caused by A99):

   ```text
   $ .venv_new\Scripts\python.exe -m pytest examples/czsc_strategy/tests/unit -q -m "realdb"
   FAILED .../test_position_sizing_research_equivalence.py::test_research_mode_equivalence_to_baseline
   1 failed, 3 passed, 772 deselected, 2 warnings in 72.11s

   E   AssertionError: SC888: computed (Bucket-B) report fields differ from baseline:
   E       sharpe_ratio: baseline=0.8091974663759458 actual=0.809197466375945
   ```

   Control run with `validation.py` reverted to HEAD (A99 edits copied aside, then restored):

   ```text
   $ git checkout -- examples/czsc_strategy/chan_strategy/validation.py
   $ .venv_new\Scripts\python.exe -m pytest "...::test_research_mode_equivalence_to_baseline" -q --tb=line
   FAILED .../test_position_sizing_research_equivalence.py::test_research_mode_equivalence_to_baseline
   1 failed, 2 warnings in 30.95s        # identical failure on unmodified HEAD code
   ```

   The failing test imports only `backtest_engine` / `config` (never `validation.py`); the mismatch is a
   last-ulp float repr difference against the stored snapshot. Pre-existing, out of A99 scope.

4. ruff (touched files):

   ```text
   $ ruff check examples/czsc_strategy/tests/unit/test_simnow_readiness_sharpe.py
   All checks passed!

   $ ruff check examples/czsc_strategy/chan_strategy/validation.py
   Found 45 errors.   # pre-existing; `git show HEAD:...validation.py` yields the same 45 — zero new
   ```

5. Preflight (from `examples/czsc_strategy/`):

   ```text
   $ powershell -ExecutionPolicy Bypass -File diagnostics\run_next_work.ps1 -Preflight
   ...
   ==> Run SimNow workflow unit tests
   205 passed in 29.28s
   ==> Preflight complete; live SimNow capture was not requested
   (exit code 0)
   ```

6. sync_check, both roots:

   ```text
   $ python tools/sync_check.py
   [SYNC-CHECK][OK] 版本单一真相 = 4.4.0  (source: vnpy/__init__.py::__version__)   # synccheck:ignore
   [SYNC-CHECK] PASS: 版本与文档一致性

   $ python tools/sync_check.py --root examples/czsc_strategy
   [SYNC-CHECK][OK] 版本单一真相 = 0.2.37  (source: VERSION::)   # synccheck:ignore
   [SYNC-CHECK] PASS: 版本与文档一致性
   ```

7. Diff scope check — only the 3 intended lines in `validation.py`; unrelated SimNow-workstream files
   (`diagnostics/WORK_LOG.md`, `diagnostics/simnow_20d_promotion_decision.md`) left untouched:

   ```text
   $ git diff --stat examples/czsc_strategy/chan_strategy/validation.py
    1 file changed, 3 insertions(+), 3 deletions(-)
   $ git status --short
    M examples/czsc_strategy/chan_strategy/validation.py
    M examples/czsc_strategy/diagnostics/WORK_LOG.md                      (concurrent workstream, untouched)
    M examples/czsc_strategy/diagnostics/simnow_20d_promotion_decision.md (concurrent workstream, untouched)
    M examples/czsc_strategy/VERSION
    M examples/czsc_strategy/CHANGELOG.md
    M HANDOFF.md
   ?? examples/czsc_strategy/tests/unit/test_simnow_readiness_sharpe.py
   ```

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-22 | claude-code → claude-code | design → design | A99 (Sharpe threshold reconciliation, re-audit M-NEW-1) scoped; drafting design brief |
| 2026-07-22 | claude-code → kimi-code | design → dev | A99 promoted design->dev |
| 2026-07-22 | kimi-code → codex | dev → review | A99 Sharpe threshold reconciliation completed: docstring + suggestion message aligned to enforced 0.3 gate (no behavior change); 4 new boundary tests (768->772); VERSION/CHANGELOG bumped; realdb 1 pre-existing env failure verified unrelated to A99 |
