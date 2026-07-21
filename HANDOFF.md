---
task: A92 - Validate A90 forced-liquidation actually flattens real positions + circuit-breaker caveat (audit H3)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-21
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/diagnostics/joint_replay_acceptance_check.py
  - examples/czsc_strategy/diagnostics/joint_replay_flatten_stress_check.py
  - examples/czsc_strategy/diagnostics/joint_replay_flatten_stress_check.json
  - examples/czsc_strategy/diagnostics/joint_replay_flatten_stress_2026-07-21.md
  - examples/czsc_strategy/chan_strategy/backtest_engine.py
  - examples/czsc_strategy/chan_strategy/portfolio_engine.py
  - examples/czsc_strategy/tests/unit/test_position_sizing_research_equivalence.py
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: review
last_transition_to_stage: dev
last_transition_from_owner: codex
last_transition_to_owner: kimi-code
---

## claude-code pre-review due-diligence (2026-07-21) — sent back before codex ever ran

The dev round's actual work is excellent (see Decision Log below for the full stress-check summary) —
this is a small, mechanical fix, not a substantive rejection. Caught this myself before triggering codex,
to save a round-trip.

1. **Fix required**: `ruff check` on this round's touched files reports one error:
   ```
   F401 `datetime.datetime` imported but unused
     --> examples/czsc_strategy/diagnostics/joint_replay_flatten_stress_check.py:53
   ```
   Run `ruff check --fix examples/czsc_strategy/diagnostics/joint_replay_flatten_stress_check.py` (or
   remove the import by hand) and re-verify `ruff check` is clean on all A92-touched files before
   re-requesting review.
2. **The `sharpe_ratio` 1-ULP-class escalation you recorded is accepted as-is, no action needed in this
   task.** claude-code independently re-read your reproduction (git-stash-based, reproduces identical on
   pristine HEAD with A92 changes removed) and agrees this is pre-existing, unrelated to A92, and not
   something to fix here. Likely cause: `sharpe_ratio` is computed via pandas `.std()` on a floating-point
   series, and reduction order for float sums/std is not strictly associative across runs/environments —
   this is exactly the kind of thing an exact-equality baseline diff (A91's gate) is too strict for.
   claude-code will open a separate follow-up task to either give `sharpe_ratio` (and any other
   float-reduction-derived Bucket-B field) a tolerance-based comparison in the equivalence gate, or pin
   down why the reduction order isn't stable — do not attempt that here, it's out of scope for A92 and
   already correctly escalated rather than fixed inline.
3. Everything else in this round — the threshold-search methodology, the real stress run at
   `daily_loss_limit_pct=0.005`, the independently-verified `flat_price` invariant, the deferred cross-symbol
   proof, the same-bar edge case documentation, the honest scope statement — was independently reviewed by
   claude-code and is accepted. Once ruff is clean, re-run the acceptance commands and go straight back to
   `handoff.py next`.

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
- 2026-07-21 (kimi-code, dev) - Part 1 done via shadow-probe-guided threshold search. A single shadow
  replay (`.tmp/a92_shadow_probe.py`, limit disarmed at 10.0, 358.8s, 68,223 check samples) mapped the
  full daily-PnL trajectory: thresholds 0.025/0.02/0.015/0.01/0.0075 ALL first-cross at 2022-03-30 09:29
  (the known empty-flatten case — no open positions), so they would prove nothing new; 0.005 first-crosses
  2022-01-14 22:29 with ZN888 一买多头 genuinely open. Real run at 0.005 (plausible risk parameter, same
  magnitude as the A87/A90 unit fixtures' 0.4-0.5%, not an absurd forcing value): 49 triggers, 101
  flat_events (68 immediate + 33 deferred), every flat_price verified against independently re-loaded bar
  data == that symbol's OWN tick close; deferred invariant proven with real skew (trigger 2022-04-22 21:59:
  A888 flattened immediately at own close 6115.0; lagging AP888 flattened 3,570 min later at 2022-04-25
  09:29 at its own close 8561.0). NO bug found in the flatten mechanism; `portfolio_ledger.py` and the
  flatten driver untouched.
- 2026-07-21 (kimi-code, dev) - Deviation from the literal "open_dt predates flat_dt" wording, with
  evidence: exactly 1 of 101 events (ZN888 一买多头 @ 2024-09-05 13:59, immediate/triggering symbol) has
  open_dt == flat_dt — the triggering symbol opened at the trigger bar's own pre_open (bar open 23030.0,
  limit not yet active so the open was allowed) and was flattened at the SAME bar's close (22900.0).
  Causally ordered within the bar, no lookahead. The checker therefore gates `open_dt <= flat_dt` plus a
  `same_bar => immediate-kind` rule, which preserves the design's intent (never close before the position
  exists). Documented in the evidence artifact.
- 2026-07-21 (kimi-code, dev) - Chose a NEW dedicated script `diagnostics/joint_replay_flatten_stress_check.py`
  over extending `joint_replay_acceptance_check.py` (the design left this open): the stress scenario needs
  a tightened-threshold override the A88 acceptance check must never carry, and mixing them would blur the
  A88 checker's production-default semantics.
- 2026-07-21 (kimi-code, dev) - PRE-EXISTING FAILURE FOUND (not caused by A92, escalated not fixed):
  `pytest tests/unit -m realdb` fails `test_research_mode_equivalence_to_baseline` on SC888 with a 1-ULP
  float diff `sharpe_ratio: baseline=0.8091974663759458 actual=0.809197466375945`. Reproduced byte-identical
  on PRISTINE HEAD (A92 changes stashed — pairs/equity_curve/sub_strategies all match; only sharpe_ratio
  differs), so the A91-regenerated baseline does not reproduce on this machine/environment. A92 does not
  touch sharpe computation. Per the escalation rule this is recorded here rather than silently patched —
  fixing the equivalence gate's float-strictness (or regenerating the baseline) is out of A92 scope and
  needs its own task. The HANDOFF acceptance command `-m "not realdb"` passes (760 passed).

## Manual Verification

All commands run natively on this machine (Windows PowerShell, `.venv_new` Python 3.13.13). <!-- synccheck:ignore -->

### Part 1 — threshold search (shadow probe, one full joint replay)

```
$ .\.venv_new\Scripts\python.exe .tmp\a92_shadow_probe.py
# .tmp/a92_shadow_probe.out.json:
#   elapsed_sec=358.8, n_check_samples=68223, n_pairs=242, symbol_errors={}
#   threshold 0.025/0.02/0.015/0.01/0.0075 -> first crossing ALWAYS 2022-03-30 09:29 (-3.004%),
#     open_symbols_at_crossing = {} (the known empty-flatten case; proves nothing new)
#   threshold 0.005 -> first crossing 2022-01-14 22:29 (-0.5148%),
#     open_symbols_at_crossing = {"ZN888": ["一买多头"]}  <- chosen
```

### Part 1 — real stress run + independent price verification

```
$ python diagnostics\joint_replay_flatten_stress_check.py 0.005   # (cwd: examples/czsc_strategy)
# diagnostics/joint_replay_flatten_stress_check.json:
#   no_symbol_errors=True, n_triggers=49, flat_events_count=101
#   by_symbol: ZN888:31, AP888:30, RB888:22, A888:18
#   immediate_flat_events_count=68, deferred_flat_events_count=33, deferred_invariant_exercised=True
#   all_prices_match_own_bar_close=True   (verified against independently re-loaded trade bars)
#   all_open_dt_not_after_flat_dt=True, same_bar_open_flatten_count=1 (ZN888 2024-09-05 13:59,
#     immediate kind; bar open 23030.0 -> close 22900.0, causally ordered, not a bug)
#   overall_accepted=True
# Deferred-invariant showcase: trigger 2022-04-22 21:59 -> A888 immediate @ own close 6115.0;
#   AP888 deferred 3570 min (weekend) -> 2022-04-25 09:29 @ its OWN close 8561.0 (not 6115).
# First trigger 2022-01-14 22:29: ZN888 一买多头 (opened 2022-01-13 09:29) flattened @ own close
#   24460.0 — exactly as the shadow probe predicted.
```

### Unit tests (acceptance command)

```
$ python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
760 passed, 4 deselected, 2 warnings in 40.78s
```

### realdb run (required by czsc AGENTS.md because generate_report() was touched)

```
$ python -m pytest tests/unit -m realdb -q
1 failed, 3 passed, 760 deselected in 72.21s
FAILED test_research_mode_equivalence_to_baseline
  E  sharpe_ratio: baseline=0.8091974663759458 actual=0.809197466375945   # 1-ULP float diff
# PRE-EXISTING, NOT caused by A92 — identical failure reproduced with all A92 changes stashed
# (pristine HEAD), same single-field diff:
$ git stash push -- <a92 files>; pytest <same test>  -> same sharpe_ratio diff; git stash pop
# Escalated in Decision Log; not silently patched (equivalence-gate fix is out of A92 scope).
```

### sync_check (both roots) + Preflight

```
$ python tools/sync_check.py
[SYNC-CHECK] PASS: 版本与文档一致。   (version 4.4.0)
$ python tools/sync_check.py --root examples/czsc_strategy
[SYNC-CHECK][OK] 版本单一真相 = 0.2.29  (source: VERSION::) <!-- synccheck:ignore -->
[SYNC-CHECK] PASS: 版本与文档一致。
$ powershell -ExecutionPolicy Bypass -File .\diagnostics\run_next_work.ps1 -Preflight   # (cwd: examples/czsc_strategy)
200 passed in 22.32s
==> Preflight complete; live SimNow capture was not requested
```

### VERSION/CHANGELOG

`examples/czsc_strategy/VERSION` 0.2.28 -> 0.2.29; `CHANGELOG.md` entry added (same commit). <!-- synccheck:ignore -->

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-21 | claude-code → kimi-code | design → dev | A92 (A90 real-data flatten validation + circuit-breaker caveats, audit H3) promoted; handoff design->dev |
| 2026-07-21 | kimi-code → codex | dev → review | A92 forced-liquidation real-data validation completed |
