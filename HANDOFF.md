---
task: A90 - Forced-liquidation implementation (daily loss limit flatten, per docs/design/a89-forced-liquidation-design.md)
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-20
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/portfolio_engine.py
  - examples/czsc_strategy/chan_strategy/portfolio_ledger.py
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
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
   underlying joint replay directly) against the same 5-symbol/window and record what `flat_events` shows
   for that date — this is a smoke check to fold into this task, not a separate A91-style acceptance task,
   since it's a narrow addition to an already-validated mechanism rather than a new coordination algorithm.
   Update the committed evidence artifact (`diagnostics/joint_replay_acceptance_check.json` / the `.md`
   write-up) to reflect the new `flat_events` output, or add a short addendum section — dev's call on
   whether to regenerate the whole artifact or add a delta note, as long as the real numbers are recorded
   honestly.

   **claude-code independently re-ran this real-data check while doing due diligence and found
   `flat_events` is EMPTY on this real run — this is NOT a bug, do not "fix" the driver to force a
   non-empty result.** Root cause, confirmed by monkeypatching `flatten_all_positions` to trace every
   call: at the exact trigger tick (2022-03-30 09:29:00), `AP888`'s own trade record shows
   `2022-03-24 14:29:00 -> 2022-03-30 09:29:00 止损` — its stop-loss fired on the *same bar* that
   triggered the daily-loss-limit breach, closing its position *before* `check_daily_loss_limit()` runs
   (stop-loss is evaluated inside `strategy.update()`, which happens earlier in the same tick than the
   post-`post_bar` daily-loss-limit check). By the time the breach is detected, AP888 already has zero
   open positions; the other four symbols also had none open at that moment (RB888/ZN888's most recent
   closes were days earlier). `_flatten_symbol()`'s `if not open_before: return` guard is doing exactly
   what it should — flattening nothing when there's nothing to flatten is the honest, correct outcome,
   not a sign the mechanism didn't fire.
   **The actual bug is in `joint_replay_acceptance_check.py`'s `flat_events_cover_trigger_days` check
   — it currently assumes a trigger day must always produce a non-empty `flat_events`, which is a false
   assumption.** Fix that check's logic (do not touch `_build_joint_report()` — it's correct as-is):
   replace the "must be non-empty" assumption with something like: if `flat_events` is non-empty, its
   dates must fall on/after a `loss_limit_triggers` date (existing check, keep it); if `flat_events` is
   empty despite a real trigger existing, that's an acceptable outcome **only if** it can be explained —
   add a check that, for each trigger, looks at whether any symbol actually had an open position at/after
   the trigger tick (e.g. by checking `pairs` for a close reason of `"daily_loss_limit_flatten"` OR a
   stop-loss/timeout close landing exactly on the trigger tick) and surface that explanation in the report
   rather than silently failing `overall_accepted`. Update the acceptance write-up
   (`joint_replay_acceptance_2026-07-17.md`'s A90 addendum) to state this finding honestly: forced
   liquidation is implemented and unit-tested against constructed scenarios that do have open positions at
   trigger time (this is required — see Acceptance Criteria), and this particular real-data run happened
   to have no positions left to flatten because the triggering symbol's own stop-loss fired on the same
   bar. Do not claim "flat_events confirmed non-empty on real data" — that would be dishonest.

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
- [ ] Real-data smoke check re-run and its actual result (empty or non-empty `flat_events`) recorded
      honestly with an explanation, not assumed to be non-empty. Given the known 2022-03-30 trigger
      coincides with AP888's own stop-loss firing on the same bar (see Decision Log / Goal §7), an empty
      `flat_events` on this specific real-data window is an expected, explainable outcome — the acceptance
      script's `flat_events_cover_trigger_days` check must be fixed to reflect that instead of failing
      `overall_accepted` on this legitimate case.
- [ ] The constructed-fixture unit tests (already required above) are the actual proof the flatten
      mechanism fires correctly when positions exist — these must pass regardless of what the real-data
      run happens to show.
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
- 2026-07-17 (claude-code, due diligence mid-dev) - kimi-code's first dev pass implemented the driver
  changes correctly (verified: nested-generator injection, `flatten_pending`, `_flatten_symbol()` all read
  as correct against the design) but its own `handoff.py next` transaction timed out again while it was
  waiting on its real-data re-run subprocess to finish (same pattern as A85/A86/A87 — timeout lands right
  at the finish line). While independently re-running the real-data check myself before committing on its
  behalf, found `overall_accepted: false` in the committed-but-uncommitted acceptance JSON, traced it to
  `flat_events_count: 0`. Independently reproduced with a monkeypatch on `flatten_all_positions` (0 calls
  traced) and confirmed via the `pairs` output that AP888's own stop-loss closed its position on the exact
  trigger bar (`2022-03-24 14:29:00 -> 2022-03-30 09:29:00 止损`), before `check_daily_loss_limit()` even
  runs for that tick. Confirmed this means `_build_joint_report()`'s flatten logic is correct (nothing to
  flatten = correctly flattens nothing) and the real bug is the acceptance script's own assumption that a
  trigger day must show non-empty `flat_events`. Did NOT touch `_build_joint_report()`, `portfolio_ledger.py`,
  or the acceptance script myself — recorded the finding and fix instructions above (Goal §7 / Acceptance
  Criteria) and left `stage: dev` for kimi-code to apply the fix, per the design/dev/review role split
  (writing/fixing diagnostics-script logic is dev's job, not design's).

## Manual Verification

(kimi-code, 2026-07-20 — all commands run natively on this machine)

```text
# 1. Unit tests
> python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
755 passed, 4 deselected in 38.29s

# 2. Real-data smoke check (re-run with fixed acceptance script)
> python examples/czsc_strategy/diagnostics/joint_replay_acceptance_check.py
flat_events_count: 0 | flat_events_coherent: true | flat_events_cover_trigger_days: false
flat_events_non_empty_or_explained: true
flat_events_trigger_explanations: [{trigger_dt: "2022-03-30 09:29:00",
  closes_on_trigger_tick: [{symbol: AP888, strategy: 一买多头,
  open_dt: "2022-03-24 14:29:00", close_dt: "2022-03-30 09:29:00", reason: 止损}],
  explains_empty_flat_events: true}]
joint_total_realized_pnl: -57473.587 (unchanged vs A88 baseline)
loss_limit_triggers: 1 (2022-03-30, -3.0044%) | flatten_on_breach: implemented_see_A90
overall_accepted: true

# 3. Sync gates
> python tools/sync_check.py
[SYNC-CHECK] PASS: 版本与文档一致。
> python tools/sync_check.py --root examples/czsc_strategy
[SYNC-CHECK][OK] 版本单一真相 = 0.2.26 <!-- synccheck:ignore --> /  [SYNC-CHECK] PASS

# 4. Preflight (from examples/czsc_strategy/)
> powershell -ExecutionPolicy Bypass -File diagnostics\run_next_work.ps1 -Preflight
195 passed in 20.50s
==> Preflight complete; live SimNow capture was not requested
```

Honest summary: `flat_events` is empty on the real-data window and that is the correct,
explained outcome (AP888's own stop-loss closed its only open position on the exact trigger
tick before `check_daily_loss_limit()` ran — surfaced via `flat_events_trigger_explanations`).
The flatten mechanism itself is proven by the constructed-fixture unit tests
(`test_daily_loss_limit_flattens_open_positions`,
`test_daily_loss_limit_lagging_symbol_flattens_at_own_price`). The acceptance-script bug
(trigger day must produce non-empty `flat_events`) was fixed by gating
`flat_events_non_empty_or_explained` instead of raw trigger-day coverage; the driver
(`_build_joint_report`) was verified correct and not modified as part of that fix.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-17 | claude-code → kimi-code | design → dev | A90 (forced-liquidation implementation) promoted; handoff design->dev |
| 2026-07-20 | kimi-code → codex | dev → review | A90 forced-liquidation implementation completed |
