---
task: A100 - Document divergence enter/leave-leg direction mismatch as accepted behavior (re-audit M-NEW-2)
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-22
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/signals.py
  - examples/czsc_strategy/chan_strategy/sell_signals.py
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
  - examples/czsc_strategy/tests/unit/test_divergence_macd.py
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

`diagnostics_ai_stock_review_report_2026-07-22.md` (the post-A97 comprehensive re-audit) flagged
**M-NEW-2**: the 背驰 (divergence) power comparison used by `signal_divergence_status`, `signal_first_buy`
(`chan_strategy/signals.py`), and `signal_first_sell` (`chan_strategy/sell_signals.py`) does not guarantee
that the "entering" (`enter_bi`) and "leaving" (`leave_bi`) bi legs share the same direction before
comparing their magnitudes.

**claude-code independently re-verified this by reading the code** (re-verify yourself in case line numbers
have drifted):

- All three functions select `enter_bi` the same way:
  ```python
  if zs_start_idx > 0:
      enter_bi = bi_list[zs_start_idx - 1]
  else:
      enter_bi = bi_list[zs_start_idx]   # falls back to the zhongshu's own first bi
  ```
  (`signals.py:325-329` inside `signal_divergence_status`; `signals.py:463-466` inside `signal_first_buy`;
  the equivalent `enter_idx = last_zs["start_idx"] - 1 if ... else last_zs["start_idx"]` at
  `sell_signals.py:132-134` inside `signal_first_sell`.) `leave_bi` is always the last bi after the
  zhongshu, filtered by direction. Since a zhongshu's own bi count (`n_bis`, `zhongshu.py:39`) is
  data-dependent, whether `enter_bi` (from `zs_start_idx - 1`, or the zhongshu's own first bi when
  `zs_start_idx == 0`) ends up the same direction as `leave_bi` is not fixed — it can legitimately end up
  opposite.
- `_divergence_power`/`_bi_power`/`_macd_power_for_segment` (`signals.py:60-134`) compute pure magnitude
  (`abs(high-low)` or summed `|hist|`), agnostic of direction — so an opposite-direction `enter_bi` is
  compared against `leave_bi` exactly as if it were same-direction.
- **This is NOT a clear-cut bug, and claude-code is explicitly NOT claiming to know the correct chan-theory
  answer here.** `tests/unit/test_divergence_macd.py:178-212`
  (`test_signal_first_buy_differs_between_models`) already constructs a fixture where `zs_start_idx == 0`,
  so `enter_bi` is the zhongshu's own first bi (`Direction.Up`) while `leave_bi` is `Direction.Down` —
  opposite directions — and the test does not treat this as invalid; it only asserts the amplitude/MACD
  models disagree on the resulting classification. This existing, already-passing test is direct evidence
  that the current behavior (direction-agnostic comparison) is at least tolerated by the project's own test
  suite, and quite possibly an accepted design choice rather than an overlooked defect.
- However, neither `signal_divergence_status`'s docstring (`signals.py:277-292`) nor either call site
  documents that direction-matching is intentionally not required — a future reader (human or agent) could
  reasonably assume "进入段"/"离开段" ("entering segment"/"leaving segment") implies a matched pair of
  trend legs, which is the standard chan-theory framing for divergence, and be surprised to find the code
  doesn't enforce it.

## Decision: scope this to documentation only, not a behavior change

The audit report itself is explicit that this "needs chan-theory domain review, not just code reading" —
claude-code has read the code carefully but has no independent authority to declare whether direction
constraint was chan-theory-intended or not, and the audit's own suggested fix (b) (search backward for the
nearest same-direction bi) is a real signal-generation behavior change with unknown impact on every
existing 背驰/一买/一卖/一卖 classification in the whole test suite and any historical backtest results that
depend on today's behavior.

**Decision: this task implements the audit's suggested fix (a) only — document the current behavior
explicitly, do not change signal logic.** This mirrors the project's established precedent for exactly this
situation (A95's M1, A96's M3): when the "correct" intended behavior can't be independently verified and a
real domain expert would need to weigh in, the safe move is honest documentation of the current, tested
behavior — not a guessed behavior change that could silently alter every 背驰-based signal in the system.
If a human/domain-expert later determines direction-matching genuinely should be enforced, that becomes a
separate, deliberately-scoped follow-up task with its own regression-impact analysis — explicitly NOT this
task.

## Goal

1. Add a note to `signal_divergence_status`'s docstring (`signals.py:277-292`, near "力度计算:") stating
   plainly that `enter_bi` and `leave_bi` are not required or guaranteed to share the same `direction` —
   `enter_bi` is chosen purely by position (the bi immediately before the zhongshu, or the zhongshu's own
   first bi when there is none before it), independent of `leave_bi`'s direction — and that the magnitude
   comparison (`_divergence_power`) is intentionally direction-agnostic. State this as a description of
   current, tested behavior (referencing `test_signal_first_buy_differs_between_models` as the test that
   already exercises the opposite-direction case), not as a chan-theory justification claude-code isn't
   qualified to assert.
2. Add a short inline comment at each of the three `enter_bi`/`enter_idx` selection sites (`signals.py:
   325-329`, `signals.py:463-466`, `sell_signals.py:132-134`) noting that the selected leg's direction is
   not checked against `leave_bi`'s — a one- or two-line comment is enough, don't duplicate the full
   docstring explanation three times; point back to `signal_divergence_status`'s docstring as the fuller
   explanation.
3. **Do not change any comparison logic, any direction filtering, or the `enter_bi`/`enter_idx` selection
   itself in any of the three functions** — this is a documentation-only task, exactly like A96 (M3). If you
   find yourself editing anything other than docstrings/comments in `signals.py`/`sell_signals.py`, stop —
   that's out of scope.
4. Add a regression test to `tests/unit/test_divergence_macd.py` that explicitly pins today's accepted
   behavior for the mismatched-direction case (rather than relying only on the existing
   `test_signal_first_buy_differs_between_models`, which exercises it incidentally without naming it) —
   e.g. a small, direct unit test on `_divergence_power`/`_bi_power` (or a targeted `signal_divergence_status`
   call) using two bis with opposite `direction` values, asserting the function runs and returns a sensible
   magnitude comparison without raising or filtering on direction. Keep it minimal — this is locking down
   documented behavior, not building new coverage infrastructure.

## Acceptance Criteria

- [x] `signal_divergence_status`'s docstring documents that enter/leave leg directions are not
      required/guaranteed to match, referencing the existing test that already exercises this.
- [x] Short inline comments added at all three `enter_bi`/`enter_idx` selection sites, pointing back to the
      fuller docstring explanation.
- [x] **Zero changes to comparison logic, direction filtering, or leg-selection logic** in `signals.py` or
      `sell_signals.py` — verified in the diff (docstring/comment lines only).
- [x] New regression test added pinning the mismatched-direction case as accepted/tested behavior.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes (count increases only
      by the new test(s) added — note the exact delta in the Decision Log).
- [x] `-m realdb` equivalence gate still passes unchanged (this task does not touch `backtest_engine.py`,
      `positions.py`, or any numeric signal-generation logic — verify rather than assume per AGENTS.md rule).
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [x] `ruff check` clean on touched files (or, if pre-existing lint errors exist in these files, verify via
      diff against HEAD that the count is unchanged — same pattern A99 used for `validation.py`'s 45
      pre-existing errors).
- [x] VERSION/CHANGELOG bumped — CHANGELOG entry must state this is a **documentation clarification of
      already-existing, already-tested behavior, not a signal-generation logic change** — be explicit, same
      as A96's (M3) CHANGELOG wording.
- [x] Include a literal `## Manual Verification` heading with natively-run command output.
- [x] **Remember the `synccheck:ignore` marker** for any version-like string in this task's own HANDOFF
      notes.

## Notes for the Next Agent

(review = claude-code must read this before starting)

1. **Dev work is complete; all acceptance criteria above are ticked and evidenced in
   `## Manual Verification` below.** Verify each criterion against the diff and the recorded command
   output; the diff scope is exactly: one docstring section in `signals.py`
   (`signal_divergence_status`), three two-line inline comments (two in `signals.py`, one in
   `sell_signals.py`), one new test function in `tests/unit/test_divergence_macd.py`, VERSION bump
   (`0.2.38`, synccheck:ignore), and one CHANGELOG entry. **Zero logic changes** — the `git diff` on
   `chan_strategy/` contains docstring/comment lines only (shown in Manual Verification item 7).
2. **The new regression test** `test_divergence_power_ignores_leg_direction_mismatch` deliberately
   constructs enter_bi (Direction.Up) / leave_bi (Direction.Down) with opposite directions and asserts
   `_divergence_power` returns the plain magnitude comparison under both `amplitude` and `macd`
   models without raising or direction-filtering. Unit count delta is exactly +1 (772 → 773,
   synccheck:ignore).
3. **realdb gate**: `test_research_mode_equivalence_to_baseline` still fails with the identical
   last-ulp float-repr diff A99 already documented as pre-existing/environmental; A100 re-ran the
   control on unmodified HEAD code (A100 edits copied aside, `git checkout --`, rerun, restore) and
   the failure reproduces byte-identically — out of A100 scope, flagged for awareness only.
4. **Unrelated SimNow-workstream files** (`diagnostics/WORK_LOG.md`,
   `diagnostics/simnow_20d_promotion_decision.md`) were left untouched; `git status --short` before
   handoff shows only A100-scoped files plus those two concurrent-workstream files.
5. **This closes the last of the three re-audit follow-up tasks** (H-NEW-1 via A98, M-NEW-1 via A99,
   M-NEW-2 via this task). After review passes, per the user's standing instruction, launch another
   comprehensive re-audit subagent to check for any remaining or newly-introduced issues.

## Decision Log

- 2026-07-22 (claude-code, design) - This is the third and final follow-up task from the 2026-07-22
  re-audit (H-NEW-1 closed via A98; M-NEW-1 closed via A99; this is M-NEW-2).
- 2026-07-22 (claude-code, design) - Full reasoning for the documentation-only scope (not implementing
  direction-matching) is recorded in the "Decision: scope this to documentation only" section above — key
  point: the audit itself says this needs chan-theory domain review, and an existing passing test
  (`test_signal_first_buy_differs_between_models`) already relies on/tolerates the mismatched-direction
  case, so changing the logic risks silently altering real signal classifications with no independent way
  to verify the change is chan-theory-correct. Mirrors A95 (M1) and A96 (M3) precedent.
- 2026-07-22 (claude-code, design) - Confirmed via code reading that all three call sites
  (`signal_divergence_status`, `signal_first_buy` in `signals.py`; `signal_first_sell` in
  `sell_signals.py`) share the identical `enter_bi`/`enter_idx` selection pattern, so the docstring/comment
  clarification needs to touch all three, not just the one the audit's code excerpt happened to show.
- 2026-07-22 (kimi-code, dev) - Implemented exactly the designed scope: (a) new 「方向约束」 section in
  `signal_divergence_status`'s docstring (framed as a description of current, tested behavior referencing
  `test_signal_first_buy_differs_between_models`, explicitly NOT a chan-theory justification); (b) two-line
  inline comments at all three `enter_bi`/`enter_idx` selection sites pointing back to that docstring
  section; (c) one new regression test `test_divergence_power_ignores_leg_direction_mismatch` in
  `tests/unit/test_divergence_macd.py` pinning the opposite-direction enter/leave pair as accepted behavior
  under both `amplitude` and `macd` divergence models. Diff on `chan_strategy/` is docstring/comment lines
  only — verified in Manual Verification item 7.
- 2026-07-22 (kimi-code, dev) - Unit suite delta is exactly +1: 772 → 773 passed (not-realdb), matching
  the single new test; no existing test was modified. `test_divergence_macd.py` alone: 10 → 11 passed
  (synccheck:ignore).
- 2026-07-22 (kimi-code, dev) - VERSION bumped `0.2.37` → `0.2.38` (synccheck:ignore) with a CHANGELOG
  entry explicitly worded as a documentation clarification of already-existing, already-tested behavior,
  not a signal-generation logic change (A96 M3 wording pattern). Added
  `tests/unit/test_divergence_macd.py` to the deliverables list (pre-existing file, extended in-place).
- 2026-07-22 (kimi-code, dev) - realdb gate: `test_research_mode_equivalence_to_baseline` fails with the
  same last-ulp float-repr diff A99 documented as pre-existing/environmental; control run on unmodified
  HEAD code (A100 edits aside) reproduces the identical failure, so it is not caused by A100. All other
  realdb tests pass (3 passed).

## Manual Verification

Environment: repo-root `python` for sync_check/handoff; `D:\repo\vnpy\.venv_new\Scripts\python.exe`
for pytest; system `ruff` for lint. All commands run natively on Windows from `D:\repo\vnpy` unless noted.

1. New regression test file (10 -> 11, delta = exactly the 1 new test):

   ```text
   $ .venv_new\Scripts\python.exe -m pytest examples/czsc_strategy/tests/unit/test_divergence_macd.py -q
   11 passed, 2 warnings in 0.16s
   ```

2. Full unit suite, not realdb (772 -> 773, synccheck:ignore; delta = exactly the 1 new test):

   ```text
   $ .venv_new\Scripts\python.exe -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
   773 passed, 4 deselected, 2 warnings in 45.30s
   ```

3. realdb equivalence gate (same 1 pre-existing environmental failure A99 documented, proven not caused
   by A100):

   ```text
   $ .venv_new\Scripts\python.exe -m pytest examples/czsc_strategy/tests/unit -q -m "realdb"
   FAILED .../test_position_sizing_research_equivalence.py::test_research_mode_equivalence_to_baseline
   1 failed, 3 passed, 773 deselected, 2 warnings in 71.40s
   ```

   Control run with A100 code edits reverted to HEAD (copied aside, `git checkout --`, rerun, restored;
   files re-verified identical after restore):

   ```text
   $ git checkout -- examples/czsc_strategy/chan_strategy/signals.py examples/czsc_strategy/chan_strategy/sell_signals.py
   $ .venv_new\Scripts\python.exe -m pytest "...::test_research_mode_equivalence_to_baseline" -q --tb=line
   FAILED .../test_position_sizing_research_equivalence.py::test_research_mode_equivalence_to_baseline
   1 failed, 2 warnings in 30.47s        # identical failure on unmodified HEAD code
   ```

   A100's `chan_strategy/` diff is docstring/comment-only (item 7), and the failing test exercises
   `backtest_engine`/snapshot comparison untouched by this task. Pre-existing, out of A100 scope.

4. ruff (all three touched code/test files — clean, and byte-identical result on the HEAD baseline via
   `git stash` / `git stash pop`):

   ```text
   $ ruff check examples/czsc_strategy/chan_strategy/signals.py examples/czsc_strategy/chan_strategy/sell_signals.py examples/czsc_strategy/tests/unit/test_divergence_macd.py
   All checks passed!        # exit=0; baseline (HEAD, stashed) also: All checks passed!
   ```

5. Preflight (from `examples/czsc_strategy/`, run twice; second run captured for the record):

   ```text
   $ powershell -ExecutionPolicy Bypass -File diagnostics\run_next_work.ps1 -Preflight
   ==> Compile SimNow capture script
   ==> Run SimNow workflow unit tests
   205 passed in 29.49s
   ==> Build pending replay backfill plan
   ==> Preflight complete; live SimNow capture was not requested
   (exit code 0)
   ```

6. sync_check, both roots:

   ```text
   $ python tools/sync_check.py
   [SYNC-CHECK][OK] 版本单一真相 = 4.4.0  (source: vnpy/__init__.py::__version__)   # synccheck:ignore
   [SYNC-CHECK] PASS: 版本与文档一致   (exit 0)
   $ python tools/sync_check.py --root examples/czsc_strategy
   [SYNC-CHECK][OK] 版本单一真相 = 0.2.38  (source: VERSION::)   # synccheck:ignore
   [SYNC-CHECK] PASS: 版本与文档一致   (exit 0)
   ```

7. Diff scope check — `chan_strategy/` changes are docstring/comment lines only (insertions: 15-line
   docstring section + 3 two-line comments; the single "deletion" is the one-line `# 计算进入段力度`
   comment replaced by its expanded two-line form); unrelated SimNow-workstream files left untouched:

   ```text
   $ git diff --stat examples/czsc_strategy/chan_strategy/signals.py examples/czsc_strategy/chan_strategy/sell_signals.py
    examples/czsc_strategy/chan_strategy/sell_signals.py |  2 ++
    examples/czsc_strategy/chan_strategy/signals.py      | 20 +++++++++++++++++++-
    2 files changed, 21 insertions(+), 1 deletion(-)
   $ git status --short
    M examples/czsc_strategy/CHANGELOG.md
    M examples/czsc_strategy/VERSION
    M examples/czsc_strategy/chan_strategy/sell_signals.py
    M examples/czsc_strategy/chan_strategy/signals.py
    M examples/czsc_strategy/diagnostics/WORK_LOG.md                      (concurrent workstream, untouched)
    M examples/czsc_strategy/diagnostics/simnow_20d_promotion_decision.md (concurrent workstream, untouched)
    M examples/czsc_strategy/tests/unit/test_divergence_macd.py
    M HANDOFF.md
   ```

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-22 | claude-code → claude-code | design → design | A100 (divergence direction-mismatch documentation, re-audit M-NEW-2) scoped; drafting design brief |
| 2026-07-22 | claude-code → kimi-code | design → dev | A100 promoted design->dev |
| 2026-07-22 | kimi-code → codex | dev → review | A100 divergence direction-mismatch documented |
| 2026-07-22 | codex → codex | review → done | A100 review passed: documentation-only divergence direction-mismatch clarification verified; touched-file ruff/sync gates pass; unit/preflight sandbox WinError 5 covered by recorded native manual verification. |
