---
task: A90 - Forced-liquidation implementation (daily loss limit flatten, per docs/design/a89-forced-liquidation-design.md)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-17
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/portfolio_engine.py
  - examples/czsc_strategy/chan_strategy/portfolio_ledger.py
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

`docs/design/a89-forced-liquidation-design.md` (accepted, `done`) answered the four open questions for
implementing forced liquidation on a daily-loss-limit breach in the A87 joint-clock replay. This task
(A90) is the implementation, following that design exactly — **A89 is a design-only task number already
used; this implementation task is A90, not a second A89.**

**Key finding the design already recorded**: `ChanTimingStrategy.flatten_all_positions(price, dt, reason)`
(`positions.py:2122`) already exists and has zero callers anywhere in the codebase. This task wires it up
via the joint driver — it does not need to build any new close/PnL primitive.

## Goal

Implement exactly what `docs/design/a89-forced-liquidation-design.md` specifies:

1. **Detect the trigger transition.** In `PortfolioEngine._build_joint_report()`
   (`portfolio_engine.py`), when `ledger.check_daily_loss_limit()` causes
   `ledger.daily_loss_limit_active` to go from `False` to `True` while processing symbol X's tick, this is
   the trigger moment (capture the before-value before calling `check_daily_loss_limit()`, compare after).
2. **Flatten the triggering symbol immediately.** Call
   `engines[X].strategy.flatten_all_positions(bar.close, current_dt, "daily_loss_limit_flatten")` for X
   right at the trigger tick (X is already at this timestamp, no lookahead concern).
3. **Defer flattening for every other symbol to its own next `"pre_open"` yield.** Maintain a
   `flatten_pending: set[symbol]` on the driver (not on `PortfolioLedger` — this is driver-loop state, the
   design doc keeps `PortfolioLedger` scoped to the shared ledger fields only). When the trigger fires, add
   every *other* successful symbol to `flatten_pending`. In the main loop, **before** processing a symbol's
   `"pre_open"` yield (i.e. before calling `ledger.pre_open_injection_for(symbol)`), check
   `if symbol in flatten_pending`: if so, call `flatten_all_positions()` for that symbol using **that
   symbol's own current-tick `bar.close`** (never the trigger tick's price — that would be a lookahead
   violation for a lagging symbol), then remove it from `flatten_pending` before proceeding with the
   normal pre_open/gating flow for that tick.
4. **New `flat_events` diagnostic list**, mirroring `PortfolioCoordinator.flat_events`'s existing shape
   (`portfolio_engine.py:125`, appended in `_flatten_all()` at `portfolio_engine.py:291-299`) minus the
   weight-bookkeeping-only `weight` field: each entry records `dt`, `symbol`, `strategy`, `open_dt`,
   `open_price`, `flat_price`, `reason`. Since `flatten_all_positions()` itself doesn't return what it
   closed, capture each symbol's `strategy.positions` open state (which ones have `pos.pos != 0`) *before*
   calling `flatten_all_positions()` for that symbol, so the driver can build accurate `flat_events`
   entries from the positions that were actually closed.
5. **Update the joint report output**: add `"flat_events": flat_events` to the report dict in
   `_build_joint_report()`; remove or update the `"flatten_on_breach": "not_implemented_see_A89"` marker
   (A87 added this to be honest about the gap — now that the gap is filled, either remove the key entirely
   or change its value to something accurate like `"implemented_see_A90"`; dev's call on the exact string,
   just don't leave a stale claim).
6. **No change to when new-open blocking starts or ends** — `daily_loss_limit_active`'s existing
   block-new-opens behavior and its trading-day reset (`ledger.update_trading_day()`) are unchanged; this
   task only adds the flatten action at the trigger moment and at each lagging symbol's catch-up tick.
7. **Real-data smoke check**: A88's acceptance run already found a real trigger (2022-03-30, single
   -3.0044% breach, 58 blocked opens). Re-run `diagnostics/joint_replay_acceptance_check.py` (or the
   underlying joint replay directly) against the same 5-symbol/window and confirm `flat_events` is now
   non-empty and coherent for that same date — this is a smoke check to fold into this task, not a
   separate A91-style acceptance task, since it's a narrow addition to an already-validated mechanism
   rather than a new coordination algorithm. Update the committed evidence artifact
   (`diagnostics/joint_replay_acceptance_check.json` / the `.md` write-up) to reflect the new `flat_events`
   output, or add a short addendum section — dev's call on whether to regenerate the whole artifact or add
   a delta note, as long as the real numbers are recorded honestly.

## Acceptance Criteria

- [ ] Forced liquidation fires exactly once per daily-loss-limit trigger (at the False→True transition),
      not repeatedly while `daily_loss_limit_active` stays `True`.
- [ ] The triggering symbol is flattened immediately at the trigger tick; every other symbol is flattened
      at its own next `"pre_open"` yield using that symbol's own current-tick price — verified with a
      constructed fixture where a lagging symbol's flatten price is NOT the trigger tick's price.
- [ ] `flat_events` is populated with accurate entries (only for positions that were actually open and
      closed, not fabricated for symbols with no open position at flatten time).
- [ ] New opens remain blocked for the rest of that trading day and reset at the next trading day —
      unchanged from A87 (regression-test this, don't just assume it still holds).
- [ ] Per-symbol/cluster margin-cap breaches still do NOT trigger any flatten — only daily-loss-limit does
      (per the design's explicit exclusion).
- [ ] No changes to `positions.py`, `backtest_engine.py`, or any A86/A87 test's assertions beyond what's
      strictly necessary (e.g. the `"flatten_on_breach"` marker key change, if any test asserted its old
      value).
- [ ] Real-data smoke check: `flat_events` is non-empty and coherent for the known 2022-03-30 trigger date
      when re-running against the same 5-symbol/window A83/A84/A88 already validated.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes, existing pass count
      unchanged plus new tests.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped.
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **Read `docs/design/a89-forced-liquidation-design.md` in full before writing any code** — it already
   resolved the hardest question (cross-symbol timing when generators lag). Do not re-derive or deviate
   from that decision.
2. **Read the current `_build_joint_report()` and `PortfolioLedger`** (`portfolio_engine.py`,
   `portfolio_ledger.py`) and their tests (`tests/unit/test_a87_joint_replay.py`) first — this task
   extends that existing driver loop, it doesn't replace it.
3. **`flatten_all_positions()` already exists and is fully correct** (`positions.py:2122`) — do not modify
   it, do not duplicate its close/PnL logic elsewhere. Your job is calling it at the right moments with
   the right price, and recording what it did.
4. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to a
   concurrent, unrelated SimNow-observation workstream. **Before committing, run `git status --short`
   and confirm only your own A90-scoped files are staged.**
5. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
6. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A90 forced-liquidation implementation completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times
   out for environment reasons (this has happened repeatedly on this machine, apparently correlated with
   the pipeline's timeout landing right at the finish line), do not manually hand-edit HANDOFF.md's
   stage/owner fields to bypass it — leave the working tree with your changes uncommitted and note the
   failure in the Decision Log; claude-code will verify and commit properly.

## Decision Log

- 2026-07-17 - User asked to stand up the A90 implementation task now that A89's design is accepted.
  claude-code noted the task-number nuance (A89 is the design task number; the implementation is A90, not
  a second A89) and the user confirmed.
- 2026-07-17 (claude-code, design) - Promoted A90 directly against the accepted A89 design, no new design
  decisions made — this HANDOFF translates the design's four already-decided questions into concrete
  acceptance criteria. Folded a real-data smoke check into this task rather than spinning up a separate
  A91-style acceptance task, since this is a narrow addition to an already real-data-validated mechanism
  (A88), not a new coordination algorithm needing its own dedicated validation task.

## Manual Verification

(dev to fill in with actual command output before requesting review)

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-17 | claude-code → kimi-code | design → dev | A90 (forced-liquidation implementation) promoted; handoff design->dev |
