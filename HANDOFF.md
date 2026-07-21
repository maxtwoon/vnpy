---
task: A92 - Validate A90 forced-liquidation actually flattens real positions + circuit-breaker caveat (audit H3)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-21
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/diagnostics/joint_replay_acceptance_check.py
  - examples/czsc_strategy/chan_strategy/backtest_engine.py
  - examples/czsc_strategy/chan_strategy/portfolio_engine.py
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

`diagnostics_ai_stock_review_report.md` H3: A90's forced-liquidation mechanism (`PortfolioLedger` +
`_build_joint_report()`'s `_flatten_symbol()`) is unit-tested with constructed fixtures, but on the real
5-symbol acceptance window it has **never actually flattened a position** — the one real trigger found
(2022-03-30) happened to occur at a moment when every symbol already had zero open positions (see A90's
own CHANGELOG entry and Decision Log). So the cross-symbol deferred-flatten timing logic — the part of A90
that's genuinely novel and easy to get subtly wrong (lagging symbols must flatten at their OWN tick's
price, never the trigger tick's) — has only ever been exercised by hand-built test fixtures, never by real
market data. Separately, H3 also flags that most users running the default config (`sizing_model="research"`
or `portfolio_risk="off"`) get **no circuit breaker at all**, and nothing in the report tells them that.

This task closes both gaps. It does NOT touch A90's actual flatten logic (`portfolio_ledger.py`,
`_build_joint_report()`'s flatten driver) unless a genuine bug is found while doing this — the mechanism
itself is validated as correct by its unit tests; this task is about proving it on real data and being
honest about when it doesn't apply.

## Goal

### Part 1 — real-data proof that forced liquidation actually closes an open position

1. Using the SAME 5 symbols / SAME real historical DB / SAME window (`AP888`/`RB888`/`SC888`/`A888`/`ZN888`,
   `2022-01-01`~`2026-04-24`) A83/A84/A88 already established as valid — do NOT introduce a different
   window or new symbols — construct a **high-fidelity** run that actually exercises the flatten path with
   a real open position at trigger time. The realistic way to do this without fabricating price data: run
   the joint replay with a **deliberately tightened `daily_loss_limit_pct`** (temporarily overridden just
   for this diagnostic run, not a config default change) chosen so a trigger occurs on this real data at a
   moment when at least one symbol demonstrably has an open position. **Do not guess a value up front and
   assume it works** — you will need to iterate: run the joint replay with a candidate tightened threshold,
   inspect whether the resulting `loss_limit_triggers` timestamps coincide with any symbol actually holding
   an open position (cross-reference against that symbol's own trade pairs, the same way claude-code's A90
   due-diligence investigation did), and adjust the threshold until you find one that does. Record every
   threshold you tried and why it didn't/did work in the Decision Log — this is exploratory, not a fixed
   recipe.
2. Once you have a run where at least one symbol had a genuinely open position at the trigger tick,
   independently verify (same style of check A90's own Decision Log used): the triggering symbol's flatten
   happened at its own trigger-tick `bar.close`; if any OTHER symbol was also flattened later (deferred,
   lagging), verify its flatten price is that symbol's OWN tick's `bar.close`, not the trigger tick's price
   — this is the exact invariant the design doc (`docs/design/a89-forced-liquidation-design.md` §3) exists
   to protect, and it's the one thing unit tests can assert cleanly but real multi-symbol timing can only
   be proven by an actual run with actual timestamp skew across symbols.
3. Extend `diagnostics/joint_replay_acceptance_check.py` (or add a new dedicated script, e.g.
   `diagnostics/joint_replay_flatten_stress_check.py` — your call which is cleaner) to run this
   tightened-threshold scenario and assert: `flat_events` is non-empty, every entry's `open_dt` predates
   its `flat_dt`, the triggering symbol's flatten price matches its own bar close, and any deferred
   symbol's flatten price matches ITS OWN bar close (not the trigger symbol's). Write up the real numbers
   (which symbol, which date, what threshold was needed, actual flatten prices) as a new acceptance
   artifact (e.g. `diagnostics/joint_replay_flatten_stress_2026-07-21.md`, `git add -f`'d per house
   convention) — state clearly this uses an artificially tightened threshold for stress-testing purposes,
   is NOT the production default, and does not imply `daily_loss_limit_pct=0.03` triggers this often on
   real data (A88 already established it triggers once in ~4 years for this symbol set at the real 0.03
   default).
4. If, while doing this, you find the deferred-flatten timing is WRONG on real data (a lagging symbol
   flattened at the wrong price, or flattened before its own generator reached that tick) — STOP, do not
   silently patch it as a side effect of this task. Record it in the Decision Log as a real bug and escalate
   rather than fixing it inline; that would be a scope change from "prove A90 works" to "fix A90", which
   needs its own due diligence.

### Part 2 — honest circuit-breaker caveat in reports

5. `BacktestEngine.generate_report()` (single-symbol path — the vast majority of runs in this project,
   since `PortfolioEngine`'s joint-replay path is opt-in) never had any concept of a portfolio-level
   circuit breaker to begin with — that's not a bug, single-symbol backtests don't have a "portfolio."
   But nothing in the report says so, and a reader who's seen A90's CHANGELOG entries could reasonably
   assume some drawdown protection exists. Add a field to `generate_report()`'s output — e.g.
   `"circuit_breaker_caveat"` — stating plainly that single-symbol runs (or any run not using
   `portfolio_risk="on"` + `sizing_model="risk"`) have no portfolio-level daily-loss-limit / forced-
   liquidation protection at all; that mechanism only exists in `PortfolioEngine._build_joint_report()`.
6. In `PortfolioEngine._build_off_report()` and `_build_on_report()` (the two non-joint paths:
   `portfolio_risk="off"`, and the weight-based `portfolio_risk="on"` + `sizing_model!="risk"` path) — add
   the same style of caveat: the weight-based `PortfolioCoordinator._flatten_all()` only adjusts its own
   internal weight bookkeeping, it never closes a real `Position` (confirmed in A90's own design doc
   background section) — so even "flatten" events reported from THAT path are not real capital actions.
   State this plainly rather than letting a reader conflate `PortfolioCoordinator.flat_events` (bookkeeping
   only) with `PortfolioEngine._build_joint_report()`'s `flat_events` (real closes, A90).
7. In `_build_joint_report()`'s own output (the one path that DOES really flatten), when `flat_events` is
   empty, add a short caveat distinguishing "the mechanism exists but never triggered this run" from "no
   protection exists" — e.g. reuse/extend the existing `"flatten_on_breach": "implemented_see_A90"` marker
   with a note like "no breach occurred in this run" when `flat_events` is empty and `loss_limit_triggers`
   is also empty, versus a distinct note when a trigger occurred but happened to find nothing to flatten
   (A90's already-documented 2022-03-30 case) — don't conflate these two very different situations under
   one vague marker.

## Acceptance Criteria

- [ ] A real-data run exists where forced liquidation actually closes a demonstrably-open position;
      documented with real dt/symbol/price numbers in a new evidence artifact.
- [ ] The cross-symbol deferred-flatten price invariant (lagging symbol flattens at ITS OWN tick's price,
      not the trigger tick's) is verified against this real run, not just synthetic fixtures.
- [ ] No bug found in the flatten mechanism itself during this exercise (if one is found, it's escalated
      in the Decision Log, not silently patched — that would be scope creep for this task).
- [ ] `generate_report()` (single-symbol) carries an explicit circuit-breaker caveat.
- [ ] `_build_off_report()`/`_build_on_report()` (weight-based paths) carry an explicit caveat that their
      "flatten" bookkeeping (if any) is not a real position close.
- [ ] `_build_joint_report()` distinguishes "no trigger occurred" from "trigger occurred but nothing was
      open to flatten" in its output, rather than one ambiguous empty-`flat_events` state.
- [ ] No changes to `portfolio_ledger.py`'s `PortfolioLedger` class or the flatten driver logic in
      `_build_joint_report()` unless a real bug was found and explicitly called out (see above) — this
      task adds validation and caveats, it does not touch the mechanism being validated, except by adding
      the new caveat fields to report output (that's fine, that's Part 2's explicit goal).
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes, count only grows by
      any new tests added.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped.
- [ ] Include a literal `## Manual Verification` heading with natively-run command output, including the
      real threshold-search process and final numbers from Part 1.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **Part 1 is exploratory — you will not get the threshold right on the first try, and that's expected.**
   Do not force a result by picking an absurdly extreme threshold (e.g. 0.0001%) just to guarantee a
   trigger with no real signal — the point is to find a threshold tight enough to trigger on real data
   while still being a plausible risk parameter, and to actually observe a real open position get closed.
   If after reasonable exploration (a handful of threshold values) you still can't find one that catches an
   open position, record what you tried and escalate rather than resorting to an absurd threshold just to
   force a green checkmark.
2. **Do not touch `chan_strategy/positions.py`** — no reason for this task to need it.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`, `simnow_daily_brief.py`,
   `simnow_run_summary.py`, `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`,
   `tests/unit/test_simnow_daily_brief.py`, `tests/unit/test_simnow_run_summary.py`) — these belong to a
   concurrent, unrelated SimNow-observation workstream (it has grown a couple more files since A91; check
   `git status --short` fresh, don't rely on this exact list). **Before committing, run `git status --short`
   and confirm only your own A92-scoped files are staged.**
4. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
5. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A92 forced-liquidation real-data validation completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times
   out for environment reasons (this has happened repeatedly on this machine), do not manually hand-edit
   HANDOFF.md's stage/owner fields to bypass it — leave the working tree with your changes uncommitted and
   note the failure in the Decision Log; claude-code will verify and commit properly.

## Decision Log

- 2026-07-21 - Continuing the audit-remediation queue after A91 (H1) closed. This task (A92) addresses H3.
- 2026-07-21 (claude-code, design) - Scoped this task to two independent halves: (1) prove the A90
  mechanism on real data via a deliberately tightened `daily_loss_limit_pct` diagnostic run (not a config
  default change), specifically targeting the cross-symbol deferred-flatten price invariant since that's
  the part unit tests alone can't fully exercise; (2) add honest circuit-breaker caveats across all three
  `PortfolioEngine` report paths plus the single-symbol path, since most runs in this project don't even
  reach code that has a circuit breaker concept. Explicitly forbade silently patching the flatten mechanism
  if a real bug surfaces during Part 1 — that's a scope change requiring its own review, not something to
  bundle into a validation task.

## Manual Verification

(dev to fill in with actual command output before requesting review)

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-21 | claude-code → kimi-code | design → dev | A92 (A90 real-data flatten validation + circuit-breaker caveats, audit H3) promoted; handoff design->dev |
