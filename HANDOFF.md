---
task: A89 - Forced-liquidation design (daily loss limit flatten, design-only, no production code)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-17
deliverables:
  - HANDOFF.md
  - docs/design/a89-forced-liquidation-design.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

A87/A88 (both `done`) implemented and real-data-validated the joint-clock replay's block-new-opens
gating, but explicitly descoped forced liquidation on a daily-loss-limit breach (the original A85 design
called for "block new opens AND flatten all positions"; the user chose to defer the flatten half to a
separate task, tentatively "A89", after claude-code found A86 hadn't built a close primitive). The user
has now asked to stand up that design task before any implementation.

claude-code (design role) has already written the full design document answering all four required
questions at `docs/design/a89-forced-liquidation-design.md`. **This task's "dev" stage is
verification/finalization of that document, not new feature development** — same shape as A85's dev
round, no production code to write.

**Key finding already recorded in the design doc**: `ChanTimingStrategy.flatten_all_positions()`
(`positions.py:2122`) already exists — comment says "used by portfolio daily loss limit" — but has
**zero callers anywhere in the codebase** (verified via `grep`). This means A89's eventual implementation
does not need to build a new close primitive at all; it only needs correct driver-side timing for when to
call this existing method. The design's hardest question is cross-symbol timing: since the joint driver
advances symbols' generators independently and some may lag behind the tick where the breach was
detected, the design decides forced liquidation must apply **per-symbol, at each symbol's own next
`"pre_open"` yield at or after the trigger tick** — not "instantaneously to all symbols" — to avoid
injecting a no-lookahead violation into a lagging symbol's own replay.

## Goal

1. Read `docs/design/a89-forced-liquidation-design.md` in full, and cross-check every code reference it
   makes (`positions.py:2122`'s `flatten_all_positions()`, its lack of callers, `portfolio_ledger.py`'s
   `check_daily_loss_limit()`/`update_trading_day()`, `portfolio_engine.py`'s `_build_joint_report()`
   driver shape, `PortfolioCoordinator.flat_events`'s existing field shape) against the actual current
   state of the codebase. If a cited line number has drifted but the referenced logic still exists, fix
   the line number. If something no longer matches, correct the design doc's prose.
2. Confirm the design doc's four decision sections (close primitive shape, which price, scope/timing
   across lagging symbols, re-arming) each give an unambiguous decision with a stated reason — tighten
   any spot a future implementer would have to guess, without inventing new architectural decisions
   beyond what's already written.
3. This is a **documentation-only** change. Do NOT write or modify any production code in
   `chan_strategy/` or `diagnostics/`. Do NOT implement the actual forced-liquidation driver logic. Do
   NOT wire up `flatten_all_positions()` to anything yet.
4. Bump VERSION/CHANGELOG for this documentation-only change.

## Acceptance Criteria

- [ ] Every code reference in `docs/design/a89-forced-liquidation-design.md` is verified accurate against
      the current codebase; any drift is corrected.
- [ ] Each of the 4 design areas (close primitive, price, cross-symbol timing, re-arming) states a
      concrete decision with a reason — no unresolved "option A or option B" left.
- [ ] No production code changed in `chan_strategy/` or `diagnostics/`.
- [ ] No changes to any existing test's assertions.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes unchanged (no code
      changed, so no test outcome should change).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped.
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **There is no code to write.** Your job is fact-checking and tightening a document claude-code already
   wrote, plus routine VERSION/CHANGELOG/test-gate bookkeeping. Do not start implementing the flatten
   logic — this task is design-only, same as A85.
2. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to a
   concurrent, unrelated SimNow-observation workstream. **Before committing, run `git status --short`
   and confirm only your own A89-scoped files are staged.**
3. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
4. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A89 forced-liquidation design verified/finalized"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times
   out for environment reasons (this has happened repeatedly on this machine, apparently correlated with
   the pipeline's timeout landing right at the finish line), do not manually hand-edit HANDOFF.md's
   stage/owner fields to bypass it — leave the working tree with your changes uncommitted and note the
   failure in the Decision Log; claude-code will verify and commit properly.

## Decision Log

- 2026-07-17 - User asked whether to stand up a design task for A89 (forced liquidation) before any
  implementation; claude-code recommended yes and outlined the four open questions in chat. User said to
  proceed.
- 2026-07-17 (claude-code, design) - Wrote `docs/design/a89-forced-liquidation-design.md`. Key finding:
  `ChanTimingStrategy.flatten_all_positions()` already exists (`positions.py:2122`) with zero callers —
  A89's implementation will not need a new close primitive, only correct driver-side timing. Decided
  forced liquidation must be applied per-symbol at each symbol's own next `"pre_open"` yield at or after
  the trigger tick (not instantaneously across all symbols), to preserve the no-lookahead invariant for
  symbols whose generator is currently lagging behind the tick where the breach was detected.

## Manual Verification

(dev to fill in with actual command output before requesting review)

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-17 | claude-code → kimi-code | design → dev | A89 (forced-liquidation design doc) promoted for verification/finalization; handoff design->dev |
