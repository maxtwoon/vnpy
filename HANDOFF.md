---
task: A100 - Document divergence enter/leave-leg direction mismatch as accepted behavior (re-audit M-NEW-2)
version: 4.4.0
stage: design
owner: claude-code
updated: 2026-07-22
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/signals.py
  - examples/czsc_strategy/chan_strategy/sell_signals.py
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
blockers: []
last_transition_kind: fix
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: design
last_transition_from_owner: claude-code
last_transition_to_owner: claude-code
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

- [ ] `signal_divergence_status`'s docstring documents that enter/leave leg directions are not
      required/guaranteed to match, referencing the existing test that already exercises this.
- [ ] Short inline comments added at all three `enter_bi`/`enter_idx` selection sites, pointing back to the
      fuller docstring explanation.
- [ ] **Zero changes to comparison logic, direction filtering, or leg-selection logic** in `signals.py` or
      `sell_signals.py` — verified in the diff (docstring/comment lines only).
- [ ] New regression test added pinning the mismatched-direction case as accepted/tested behavior.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes (count increases only
      by the new test(s) added — note the exact delta in the Decision Log).
- [ ] `-m realdb` equivalence gate still passes unchanged (this task does not touch `backtest_engine.py`,
      `positions.py`, or any numeric signal-generation logic — verify rather than assume per AGENTS.md rule).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] `ruff check` clean on touched files (or, if pre-existing lint errors exist in these files, verify via
      diff against HEAD that the count is unchanged — same pattern A99 used for `validation.py`'s 45
      pre-existing errors).
- [ ] VERSION/CHANGELOG bumped — CHANGELOG entry must state this is a **documentation clarification of
      already-existing, already-tested behavior, not a signal-generation logic change** — be explicit, same
      as A96's (M3) CHANGELOG wording.
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.
- [ ] **Remember the `synccheck:ignore` marker** for any version-like string in this task's own HANDOFF
      notes.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **This is documentation/comments-only — no signal-generation logic changes anywhere.** Read the
   "Decision: scope this to documentation only" section above in full before touching anything; do not
   "fix" this by adding direction-matching logic or searching backward for a same-direction bi — that was
   explicitly considered (it's the audit's own suggested option (b)) and rejected as out of scope for this
   task, since neither claude-code nor kimi-code has the chan-theory domain authority to make that call
   unilaterally.
2. **Scope is exactly**: one docstring addition, three short inline comments, one new regression test. Do
   not touch `_divergence_power`, `_bi_power`, `_macd_power_for_segment`, any `enter_bi`/`leave_bi`
   selection code, or any direction-filtering code.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/WORK_LOG.md`, `diagnostics/simnow_20d_promotion_decision.md`, and any other SimNow-workstream
   files you see) — these belong to a concurrent, unrelated workstream. **Before committing, run
   `git status --short` and confirm only your own A100-scoped files are staged.**
4. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
5. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A100 divergence direction-mismatch documented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times out
   for environment reasons, do not manually hand-edit HANDOFF.md's stage/owner fields to bypass it — leave
   the working tree with your changes uncommitted and note the failure in the Decision Log; claude-code will
   verify and commit properly.
6. **This is the LAST of the three re-audit follow-up tasks** (H-NEW-1 closed via A98, M-NEW-1 closed via
   A99, this is M-NEW-2). After this closes, all High/Medium findings from BOTH the original 2026-07-21
   audit and the 2026-07-22 re-audit are closed or explicitly, permanently documented/parked. Per the
   user's standing instruction, claude-code will then launch another comprehensive re-audit subagent to
   check for any remaining or newly-introduced issues.

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

## Manual Verification

(pending — dev fills in)

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-22 | claude-code → claude-code | design → design | A100 (divergence direction-mismatch documentation, re-audit M-NEW-2) scoped; drafting design brief |
