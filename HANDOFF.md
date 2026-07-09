---
task: A38 Chan Strategy Improvement Roadmap (Phase 1 - touch-based stop execution)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-09
deliverables:
  - HANDOFF.md
  - docs/design/a38-strategy-improvement-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
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
- [ ] A35 cross-check: an `"intrabar"` backtest's recomputed stop-loss `worst_loss_pct` /
      `overshoot_count` / `max_overshoot_multiple` agree with A35's `intrabar_trigger` scenario
      within a stated tolerance on >=1 symbol; the evidence artifact is tracked (not only
      regenerated on disk).
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

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a38-strategy-improvement-roadmap.md`. Implement **Part II only**
   (Phase 1). The full dev prompt is in design doc S5. Do not implement P2-P8 - they are separate
   future tasks; scope creep here is a reject reason.
2. **Core change (design doc 2.3):** honor the switch in `positions.py`. Under `"intrabar"`,
   long stop fires when `bar_low <= cost*(1-stop_loss_bp/10000)` and fills at
   `min(trigger, bar_close)`; short fires when `bar_high >= cost*(1+stop_loss_bp/10000)` and
   fills at `max(trigger, bar_close)`; then apply `stop_penalty_bp` adversely. Thread `bar.high`
   / `bar.low` into `Position.update` via NEW optional params defaulting to `None` (fallback to
   `price`, so existing call sites and the `"close"` path stay byte-identical).
3. **Only the fixed stop changes.** Trailing-stop and timeout keep their current price basis in
   this task (P8 owns the exit overhaul). The `Position.update` priority order
   (trailing > stop > timeout) is unchanged.
4. **No-lookahead is load-bearing:** the risk check must read only the CURRENT bar's OHLC - the
   same bar whose close already drives the existing risk block (`backtest_engine.py:271-284`).
   Do not read any future bar; do not otherwise reorder `BacktestEngine.run`.
5. **Correctness proof = A35 cross-check.** A35's `stop_loss_stress_report` already computed the
   `intrabar_trigger` scenario independently. Your `"intrabar"` backtest overshoot metrics must
   converge to it within a stated tolerance on >=1 symbol. Track that evidence as a committed
   artifact - the A37 review rejected twice for relying on git-ignored `diagnostics/` files, so
   do not repeat that: put reusable scripts and proof under tracked paths (or add a tracked
   summary artifact carrying the numbers).
6. **Guardrails (reject-on-violation):** do not tune any threshold/weight/interval; do not use
   pre-2026-04-24 data for selection; do not touch SimNow order/cancel/send paths; reports carry
   the RESEARCH-ONLY banner; no `GOAL PASSED`.
7. **Why gated + default-off:** same discipline as A37 - the `"close"` default must reproduce the
   current baseline byte-for-byte (equivalence test), so P1 adds a capability without changing
   any published result until it is deliberately switched on.
8. Finish by running the four commands in the acceptance list, then
   `python tools/handoff.py next --actor kimi-code --summary "A38 phase 1 touch-based stop execution implemented"`.
   The gate is transactional - if it blocks, fix and retry; do not use `--no-gate`.

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

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-09 | codex → claude-code | done → design | A38 improvement roadmap started (Phase 1: touch-based stop execution) |
| 2026-07-09 | claude-code → kimi-code | design → dev | A38 design complete: strategy improvement roadmap (P1-P8); Phase 1 = touch-based stop execution spec + acceptance |
