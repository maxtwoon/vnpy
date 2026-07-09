---
task: A38 Chan Strategy Improvement Roadmap (Phase 1 - touch-based stop execution)
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-10
deliverables:
  - HANDOFF.md
  - docs/design/a38-strategy-improvement-roadmap.md
  - docs/design/a38-phase-contracts-p2-p8.md
  - examples/czsc_strategy/chan_strategy/config.py
  - examples/czsc_strategy/chan_strategy/positions.py
  - examples/czsc_strategy/chan_strategy/backtest_engine.py
  - examples/czsc_strategy/tests/unit/test_stop_execution_model.py
  - examples/czsc_strategy/tests/unit/test_stop_execution_crosscheck.py
  - examples/czsc_strategy/diagnostics/stop_execution_model_crosscheck.py
  - examples/czsc_strategy/diagnostics/stop_execution_model_crosscheck_2026-07-10.json
  - examples/czsc_strategy/diagnostics/stop_execution_model_crosscheck_2026-07-10.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

The 2026-07-09 futures-trading review turned into an action checklist (three tiers: foundation
/ win-rate / profitability). A34-A37 already handled the audit-remediation slice as diagnostics
(M1 cost single-source, H1 declassification, A35 stop-loss stress diagnostic, A37 exit-event
restructure). What remains un-built: the actual touch-based stop *implementation* (H2 - A35 only
measured it; `Position._check_stop_loss` is still close-based), 888 rollover handling (H4), and
the entire win-rate / profitability edge program that A34 explicitly excluded.

A38 sequences the full improvement program into a phased, gated roadmap (P1-P8) and ships the
first, highest-certainty slice. The user (2026-07-09) explicitly authorized modifying strategy
code in this root `vnpy` workflow for this line of work, so A38 is NOT diagnostics-only; but the
A34-style guardrails still bind (gated default-off switches, no OOS tuning, research-only
banner, no SimNow order changes).

Single source of truth for the plan: `docs/design/a38-strategy-improvement-roadmap.md`
(Part I = full P1-P8 roadmap; Part II = Phase 1 dev contract).

## Goal

Implement **Phase 1 only**: gap-aware / intrabar touch-based stop-loss execution, gated behind
`STRATEGY_CONFIG["stop_execution_model"]` (`"close"` default = byte-identical legacy;
`"intrabar"` = touch-based trigger + realistic fill). A35's `intrabar_trigger` stress scenario
is the acceptance oracle. Phases P2-P8 are deferred to A39+.

Why Phase 1 first: it is a pure execution-accuracy fix (no signal semantics change), it targets
the largest single loss source (stop path = 155 trades / 0% win / ~-489% cumulative in the A37
attribution; A35 shows up to ~4.2x overshoot, worst ~-12.60% on a 3% stop), and it is a
prerequisite for honestly measuring any later win-rate / PnL change.

## Acceptance Criteria

- [ ] `STRATEGY_CONFIG["stop_execution_model"]` exists with values `"close"` (default) and
      `"intrabar"`, plus `stop_penalty_bp` (default `0`); both documented in `config.py`.
- [ ] Legacy equivalence: with `"close"`, before/after trade-pair diff is empty on >=2 symbols
      x 1 year (long baseline) AND >=1 symbol x 1 year with `enable_short=True`.
- [ ] Intrabar trigger: unit tests prove long fires on `bar_low <= cost*(1-bp)` and fills
      `min(trigger, close)`; short fires on `bar_high >= cost*(1+bp)` and fills
      `max(trigger, close)`; `stop_penalty_bp` worsens the fill in the correct direction.
- [ ] No-lookahead: the intrabar check reads only the current bar's high/low; a test asserts no
      future bar is consulted, and `BacktestEngine.run` step ordering is unchanged beyond
      threading high/low.
- [ ] A35 cross-check (well-posed; design 2.5, revised 2026-07-10): on the close-model run's
      stop pairs for one uniform-stop sub-strategy on >=1 symbol, the cross-check reuses A35's
      `scenario_intrabar_trigger` / `_scenario_summary` and asserts (a) A38 fill == A35 fill
      within `1e-6` on every non-gap trade, and (b) `A38_loss >= A35_loss` on every gap trade;
      it reports `worst_loss_pct` / `overshoot_count` / `max_overshoot_multiple` for both models
      plus the committed A35 full-sample values. Tolerance and gap invariant printed. Evidence
      tracked (not only regenerated on disk).
- [ ] Backtest report header prints the active `stop_execution_model` and `stop_penalty_bp`.
- [ ] No stop-loss threshold tuned (`stop_loss_*bp` unchanged); no pre-2026-04-24 data used for
      any selection; every generated report carries the RESEARCH-ONLY disclaimer; no
      `GOAL PASSED`.
- [ ] No SimNow order/cancel/send paths changed; no new `send_order`/`cancel_order`/`buy`/
      `sell`/`short`/`cover`; no secret fields in output.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight`
      passes.
- [ ] Part I roadmap present in the design doc: all Tier A/B/C review items mapped to P1-P8,
      each with a default-off gate and boundaries.

## Notes for the Next Agent

(review = codex; second review after the 2026-07-10 reject was addressed)

### How the 2026-07-10 review reject was addressed

The reject was correct: the A35 cross-check had been downgraded to a qualitative direction. Root
cause (now recorded as a design decision): A35 `scenario_intrabar_trigger` fills at the trigger
(never overshoots) while A38 fills at `min(trigger, close)` (conservative on gaps) - different
fill models, so blanket numeric agreement is ill-posed. The criterion was **amended at design**
(design 2.5, revised) to a well-posed same-population two-model comparison, and the cross-check
was rebuilt:

- `diagnostics/stop_execution_model_crosscheck.py` now runs the close-model backtest, takes the
  `一买多头` (200bp) stop pairs on sc888 + rb888, and drives BOTH models at 30m granularity:
  A35 model via A35's own `scenario_intrabar_trigger` (through a 30m loader), A38 model via
  `a38_intrabar_trades` (`min/max(trigger, close)`); metrics via A35's `_scenario_summary`.
- It asserts (a) A38 exit == A35 exit within `1e-6` on every non-gap trade, (b)
  `A38_loss >= A35_loss` on every gap trade; it reports `worst_loss_pct` / `overshoot_count` /
  `max_overshoot_multiple` for both models and loads the committed A35 report for reference.
- New non-realdb unit test `test_stop_execution_crosscheck.py` covers `a38_intrabar_trades`.
- Strategy code (`config.py` / `positions.py` / `backtest_engine.py`), the stop unit tests, and
  the close-model equivalence proof are **unchanged from the accepted first submission**.

### What changed (Phase 1 only; P2-P8 untouched)

- `chan_strategy/config.py`: added `stop_execution_model` (`"close"` default | `"intrabar"`)
  and `stop_penalty_bp` (0 default), documented.
- `chan_strategy/positions.py`:
  - `Position.update` gained optional `bar_high` / `bar_low` (default `None`).
  - The fixed-stop branch now calls `_stop_triggered(price, bar_high, bar_low)` then fills via
    `_stop_fill(price, bar_high, bar_low)`. `_check_stop_loss` is **unchanged**; under `"close"`
    (or when bar extremes are `None`) `_stop_triggered` returns exactly `_check_stop_loss(price)`
    and `_stop_fill` returns exactly `price` -> byte-identical baseline by construction.
  - Under `"intrabar"`: long fires on `bar_low <= cost*(1-stop_loss/1e4)` filling
    `min(trigger, close)`; short fires on `bar_high >= cost*(1+stop_loss/1e4)` filling
    `max(trigger, close)`; `stop_penalty_bp` worsens the fill. Trailing/timeout unchanged.
  - `ChanTimingStrategy.update` forwards `bar_high`/`bar_low` to all sub-position updates.
- `chan_strategy/backtest_engine.py`: threads the **current** bar's `high`/`low` into both
  `strategy.update` calls (no lookahead; ordering otherwise unchanged); report dict + header
  now carry `stop_execution_model` / `stop_penalty_bp`.

### How to verify

- Unit: `python -m pytest examples/czsc_strategy/tests/unit/test_stop_execution_model.py -q`
  (10 tests: intrabar long/short trigger+fill, penalty direction, gap-through fills at close,
  close-model ignores bar extremes, missing-extremes fallback, and a close-model
  with/without-extremes equivalence).
- Full non-realdb suite: `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"`
  -> **353 passed**.
- Real-data proof: `python examples/czsc_strategy/diagnostics/stop_execution_model_crosscheck.py`
  and the tracked artifacts `stop_execution_model_crosscheck_2026-07-10.{json,md}`.

### Self-test results (2026-07-10, local SQLite DB)

- **Close-model equivalence (byte-identical):** git-stash the 3 source files, run baseline
  close-model, diff stats (window 2024) -> PASS on sc888 (long), rb888 (long), sc888
  (`enable_short=True`); all of `stop_trades/worst_loss_pct/max_overshoot_x/total_return_pct/
  total_trades` equal. Also unit-proven.
- **A35 cross-check (well-posed; window 2022-2024, `一买多头` 200bp):** non-gap trades A38 exit
  == A35 exit to `1e-6` (`max_non_gap_exit_diff = 0.0`); gap-conservatism invariant
  `A38_loss >= A35_loss` holds. sc888: 22 stops, A35 worst -2.00% / overshoot 0, A38 worst
  **-4.599% / overshoot 14 / max 2.299x** (14 gap trades). rb888: 14 stops, A35 -2.00% / 0,
  A38 **-2.394% / overshoot 9 / 1.197x**. The committed A35 full-sample report's
  `intrabar_trigger` is itself `unavailable` (A35's 1-min loader cannot reach the per-symbol
  tables), so the numeric reference reuses A35's scenario functions with a working 30m loader.
- Unit: **361 passed** (`-m "not realdb"`), incl. `test_stop_execution_crosscheck.py` (3).
- Root + child `sync_check` PASS; `run_next_work.ps1 -Preflight` PASS.

### Deviations from design

- Minor: three existing test doubles (`test_positions.py`, `test_portfolio_accounting.py`,
  `test_branch_completion.py`) stub `ChanTimingStrategy.update`; their `update` signatures were
  extended with `bar_high=None, bar_low=None` to match the new interface. No assertions changed.
  Logged in the Decision Log.
- The diagnostics artifacts live under the git-ignored `diagnostics/` dir and are force-tracked
  (`git add -f`) to avoid the A37 "proof not reproducible from a clean checkout" rejection.

### Reviewer focus

Confirm: `"close"` byte-identical (stash diff + unit test); intrabar trigger/fill math matches
2.3; trailing/timeout untouched; only current-bar OHLC read; no threshold tuned; no
pre-2026-04-24 selection; no SimNow order path; no `GOAL PASSED`; artifacts git-tracked.

## Review Findings

2026-07-10 codex review result: **rejected to dev**.

Blocking issue:

- The A38 acceptance contract requires the A35 cross-check to compare an
  `intrabar` backtest's recomputed `worst_loss_pct`, `overshoot_count`, and
  `max_overshoot_multiple` against A35's `intrabar_trigger` scenario **within a
  stated tolerance** on at least one symbol. The implementation instead records
  a qualitative / directional check: `stop_execution_model_crosscheck.py` says
  it is "cross-referenced qualitatively", the tracked JSON/Markdown report says
  it "matches the A35 intrabar_trigger direction", and the Decision Log says the
  gate is "satisfied qualitatively ... rather than an exact numeric replica".
  That is a contract downgrade without a design-stage decision.

Evidence:

- `docs/design/a38-strategy-improvement-roadmap.md` §2.5 and §3 require
  `worst_loss_pct` / `overshoot_count` / `max_overshoot_multiple` to agree with
  A35 `intrabar_trigger` within tolerance.
- `HANDOFF.md` acceptance lines 69-71 repeat the same requirement.
- `HANDOFF.md` Decision Log lines 162-166 explicitly admits the current
  cross-check is qualitative rather than exact.
- `examples/czsc_strategy/diagnostics/stop_execution_model_crosscheck.py` only
  reports `stop_trades`, `worst_loss_pct`, and `max_overshoot_x`; it does not
  read the A35 stress report, does not compute/report `overshoot_count`, and
  does not apply a stated tolerance.
- `examples/czsc_strategy/diagnostics/stop_execution_model_crosscheck_2026-07-09.json`
  contains no `overshoot_count` field and no A35 comparison block.

Required remediation:

1. Make `stop_execution_model_crosscheck.py` consume the A35
   `stop_loss_stress_report_*.json` (or a tracked A35 fixture/summary) and
   compare the required metrics: `worst_loss_pct`, `overshoot_count`, and
   `max_overshoot_multiple`.
2. Define and print the tolerance used for each metric. If exact agreement is
   impossible because A35 is pair-reconstruction based while A38 is live-engine
   based, return to design and explicitly change the acceptance contract before
   claiming the gate passes.
3. Regenerate and track the cross-check JSON/Markdown evidence with the A35
   comparison block.
4. Re-run the full A38 acceptance commands and hand off again to review.

## Decision Log

- 2026-07-09 - A38 started after A37 reached `done`; scope = the 2026-07-09 futures-review action
  checklist, sequenced as a gated P1-P8 roadmap. User authorized strategy-code changes in the
  root workflow (vs the czsc_strategy sub-workflow, which is read-only diagnostics and could not
  host this).
- 2026-07-09 - Chose touch-based stop execution as Phase 1: highest certainty (execution-accuracy
  fix, no signal-semantics change), highest leverage (stop path is the dominant loss source), and
  a prerequisite for honestly measuring later Tier B/C win-rate / PnL changes. A35 already
  produced the acceptance oracle.
- 2026-07-09 - Kept the fixed-stop change isolated from trailing/timeout (P8 owns exits) to keep
  the Phase 1 equivalence proof small and the review surface minimal.
- 2026-07-09 (dev) - Extended three existing test-double `update` signatures with
  `bar_high=None, bar_low=None` to match the new `Position.update` / `ChanTimingStrategy.update`
  interface. Interface-compat only, no assertion changes. Design contract unchanged.
- 2026-07-09 (dev) - Equivalence proven via a git-stash before/after diff of the 3 source files
  (close-model byte-identical on 2 long symbols + 1 enable_short leg), complementing the unit
  equivalence test; the A35 cross-check is satisfied qualitatively by the intrabar tail-bounding
  direction (short overshoot 2.77x -> 1.41x) rather than an exact numeric replica of A35's
  post-hoc scenario, since A35 recomputed from saved pairs while this runs the live engine.
- 2026-07-10 (design, after review reject) - The 2026-07-09 (dev) qualitative substitution above
  was a contract downgrade without a design decision (correctly caught in review). Root cause:
  A35 `scenario_intrabar_trigger` fills at the trigger (never overshoots) while A38 fills at
  `min(trigger, close)` (conservative on gaps) - different fill models, so blanket numeric
  agreement is impossible by construction. **Decision:** redefine the A35 cross-check (design 2.5)
  to a well-posed same-population, two-model comparison reusing A35's `scenario_intrabar_trigger`
  / `_scenario_summary`: exact convergence (`1e-6`) on non-gap trades + an `A38_loss >= A35_loss`
  conservatism invariant on gap trades, reporting `worst_loss_pct` / `overshoot_count` /
  `max_overshoot_multiple` for both models plus the committed A35 full-sample values. This keeps
  A38's more-conservative gap fill (the modeling improvement) instead of forcing it to match A35.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-09 | codex → claude-code | done → design | A38 improvement roadmap started (Phase 1: touch-based stop execution) |
| 2026-07-09 | claude-code → kimi-code | design → dev | A38 design complete: strategy improvement roadmap (P1-P8); Phase 1 = touch-based stop execution spec + acceptance |
| 2026-07-09 | kimi-code → codex | dev → review | A38 phase 1 touch-based stop execution implemented (gated, close byte-identical, intrabar tail-bounded; unit+realdb proof) |
| 2026-07-10 | codex → kimi-code | review → dev | 打回: A38 A35 cross-check was downgraded to qualitative direction instead of numeric tolerance agreement |
| 2026-07-10 | kimi-code → claude-code | dev → design | 打回: A35 cross-check criterion is ill-posed: A35 scenario_intrabar_trigger fills at the trigger level (never overshoots) while A38 fills at min(trigger,close) (conservative on gap-through) - two different fill models, so blanket numeric agreement is impossible by construction. Amend the acceptance to a well-posed same-population two-model comparison (exact convergence on non-gap trades + A38>=A35 conservatism invariant on gap trades), consuming A35's module and reporting overshoot_count. |
| 2026-07-10 | claude-code → kimi-code | design → dev | A38 design amend: well-posed A35 cross-check (same-population two-model; exact non-gap convergence + gap conservatism invariant) |
| 2026-07-10 | kimi-code → codex | dev → review | A38 remediation: well-posed A35 cross-check (same-population two-model; non-gap exact 1e-6, gap conservatism invariant); rebuilt crosscheck + unit test + tracked 2026-07-10 evidence |
