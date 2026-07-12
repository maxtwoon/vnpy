---
task: A47 P8a - Exit Overhaul (structural_atr)
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-12
deliverables:
  - HANDOFF.md
  - docs/design/a38-phase-contracts-p2-p8.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

Continues the P1-P8 roadmap after A46 (P7 symmetric regime-gated shorts) reached `done`. P1-P7
are all `done`. P8 is the final, heaviest phase, explicitly shipped as two sub-tasks per the
design's own note: **P8a (exits, this task) must ship and pass review BEFORE P8b (portfolio
risk, A48) is even started** — do not promote A48 until A47 reaches `done`.

**Task-ID renumbering (unchanged from A43-A46's note):** the phase-contracts doc's original
`Task mapping` (`P8=A45`) is stale — A45 is actually P6 under the 2026-07-12 renumbering.
Confirmed mapping: **P4=A43 (done), P5=A44 (done), P6=A45 (done), P7=A46 (done), P8a=A47 (this
task), P8b=A48.**

`key_trade_behavior_review.md` (the original trading-expert review) found exits are the dominant
PnL lever: the current exit set is a fixed-percentage-giveback trailing stop
(`Position._check_trailing_stop`, `chan_strategy/positions.py:671-686`, re-verified 2026-07-12 —
triggers when `drawback >= max_profit_bp * trailing_drawback_pct`, i.e. a percentage-of-max-profit
giveback, NOT ATR-based) that both exits winners too early and lets some give back, plus a
"confirmed-structure reversal" exit (`结构失效`, e.g. `positions.py:470/954/1054/1141/1219`) that
lags. Confirmed 2026-07-12: no `exit_model`/`atr_trail_mult`/`partial_tp_frac` config or code
exists yet in `config.py`/`positions.py` — no drift since the phase-contracts draft was written.

Full contract: `docs/design/a38-phase-contracts-p2-p8.md` §"P8 (A45) - Exit Overhaul + Portfolio
Risk", specifically the **P8a** subsection (the section header still says A45 — that is the stale
label; this task's real ID is A47, content is otherwise authoritative and unchanged). Only the
P8a portion of that section applies to this task; the P8b portion (portfolio coordinator) is out
of scope here and belongs to A48.

## Goal

Add `exit_model` config gate (`"legacy"` default, byte-identical to current | `"structural_atr"`).

Under `"structural_atr"`:
- Replace the profit-side fixed-percentage-giveback trailing with an ATR trailing stop:
  `trail = peak - atr_trail_mult * ATR` (long; symmetric for short), using the ATR helper already
  shipped in A45 (`chan_strategy/signals.py`'s `AtrStateTracker`/ATR computation — reuse it, do
  not reimplement).
- Keep the structural stop (center/结构失效 break) as the hard structural exit, unchanged.
- Add a partial take-profit: scale out `partial_tp_frac` of the position at the next center
  boundary / measured target, then trail the remainder with the ATR trailing stop.
- The fixed stop-loss (P1/A38's touch-based stop) and timeout exit are UNCHANGED under both
  modes — this phase only replaces the profit-side trailing behavior and adds partial TP.

Add read-only `exit_model_report.py`: per-trade give-back (peak-to-exit) and early-exit
(exit-to-subsequent-extreme) stats, legacy vs structural_atr, on the honest post-2026-04-24
baseline (report only, not for in-task selection).

## Acceptance Criteria

- [ ] `exit_model="legacy"` (default) -> equity curve and every `Position.pairs` entry
      byte-identical to current (full-`BacktestEngine` equivalence test with a git-tracked golden
      snapshot, per the A44-A46 house pattern — do not ship with only a signal-filter unit check).
- [ ] `"structural_atr"`: a fixture proves partial TP scales out exactly `partial_tp_frac` of the
      position at the target and the remainder trails by `atr_trail_mult * ATR` from the peak
      (unit-tested, long and short).
- [ ] `"structural_atr"`: the structural stop (`结构失效`) and the P1/A38 fixed stop-loss still
      fire exactly as before — this phase does not touch stop-loss logic (unit-tested that a
      structural-failure signal still exits under both `exit_model` values).
- [ ] `"structural_atr"`: the timeout exit is unchanged (unit-tested that `bars_since_open >=
      timeout` still exits under both `exit_model` values).
- [ ] `exit_model_report.py` generated (report only, RESEARCH-ONLY banner
      `Diagnostic only, not a trading recommendation.`); NOT used to select/tune
      `atr_trail_mult`/`partial_tp_frac` in-task. Must be regenerated with the script's own real
      default symbols on the post-2026-04-24 window (`WINDOW_START="2026-04-24"`,
      `WINDOW_END="2026-07-09"`, matching every A43-A46 report script's precedent) — verify the
      output before committing; do not ship a placeholder/empty report (A45's first dev round
      shipped one against a fake "TEST" symbol; A46's first dev round hardcoded the window
      backwards — both had to be corrected after the fact).
- [ ] No threshold tuning via backtest/capture-data selection; no pre-2026-04-24 data used for
      any parameter choice; no SimNow order/cancel/send path changed; no `GOAL PASSED`; this
      phase does not touch position sizing (P3/A40's scope) or the P8b portfolio coordinator
      (A48's scope, not started).
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes — this script
      genuinely exists at `diagnostics/run_next_work.ps1`; verify the path carefully before
      claiming otherwise (A44's dev round falsely claimed it was absent).

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a38-phase-contracts-p2-p8.md`, section "P8 (A45) - Exit Overhaul
   + Portfolio Risk", **P8a subsection only**. Ignore the stale `(A45)` label in the header, this
   task's real ID is **A47**. Full dev prompt and review checklist are in that section; do NOT
   implement any P8b (portfolio) content — that's a separate future task (A48), gated to start
   only after this task reaches `done`.
2. **Scope:** `chan_strategy/positions.py` (the `structural_atr` exit model in `Position`'s
   exit-check path, replacing/gating `_check_trailing_stop`'s call site; partial-TP scale-out
   logic), `chan_strategy/config.py` (new `exit_model`/`atr_trail_mult`/`partial_tp_frac` keys).
   Reuse A45's ATR helper (`AtrStateTracker` in `signals.py`) — do not reimplement ATR
   computation. Do not touch `backtest_engine.py`'s core loop structure, position sizing
   (`_size_open`, P3/A40), or add any portfolio-level coordinator (P8b/A48's scope).
3. **Gated + default-off discipline (standard house style):** `exit_model="legacy"` must
   reproduce current behavior byte-for-byte — this is the ONE required full-`BacktestEngine`
   golden-snapshot equivalence proof for this task (unlike A46, there is no second/independent
   mode requiring a separate proof — `"structural_atr"` is opt-in only, no default-path ambiguity
   here).
4. **Stop-loss and timeout are explicitly OUT of scope** — this phase only changes the
   profit-side trailing exit and adds partial TP. Verify with a unit test that a structural-
   failure signal and a timeout condition still produce an exit identically under both
   `exit_model` values.
5. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection
   (this specifically includes `atr_trail_mult`/`partial_tp_frac` — the report evidence must not
   be used to pick these values in this task); no pre-2026-04-24 data for any parameter choice;
   no SimNow order/cancel/send paths touched; RESEARCH-ONLY banner on the new report; no
   `GOAL PASSED`; does not touch position sizing or start any P8b/portfolio work.
6. **Verify diagnostic report window and symbols before committing** — this is now the third time
   this note appears. Use `WINDOW_START="2026-04-24"`, `WINDOW_END="2026-07-09"` (copy the
   constants from an existing A43-A46 report script, do not hardcode new/different dates), and
   confirm the generated report actually contains real per-symbol data on real default symbols
   before finishing (A45 shipped an empty report against a placeholder symbol; A46 shipped one
   with the date window backwards — both had to be corrected after the fact by claude-code).
7. **Before claiming any script "doesn't exist," verify the path carefully** — `run_next_work.ps1`
   lives at `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
8. **If you get stuck for more than a few debugging iterations on a single acceptance item,
   re-read this HANDOFF.md's Acceptance Criteria for an internal contradiction before continuing**
   — A46's first dev round timed out at 2400s because its original acceptance criteria (written
   by claude-code) were self-contradictory; this HANDOFF.md has been written carefully to avoid
   that this time, but if something still seems logically impossible to satisfy, that is a signal
   to stop and let the next review round flag it rather than debug-looping.
9. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A47 (P8a) exit overhaul (structural_atr) implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-12 - P8a promoted from the pre-authored phase-contracts draft to an active HANDOFF task
  as **A47** (not A45 — A45 is P6 under the established renumbering), continuing sequential
  single-phase-at-a-time promotion. Per the design's own explicit note, P8b (A48) must not be
  promoted until this task (P8a) reaches `done` — this is a stronger sequencing requirement than
  the general "one phase at a time" rule already used for P4-P7, since P8a/P8b are two halves of
  the same phase with an explicit ship-order dependency in the design itself.
- 2026-07-12 - Re-verified `_check_trailing_stop` (positions.py:671-686, percentage-of-max-profit
  giveback, confirmed NOT ATR-based) and confirmed no `exit_model`/ATR-trailing/partial-TP config
  or code exists yet — no drift from A43-A46, none of which touched the exit-check path.
- 2026-07-12 - Pre-emptively added explicit notes incorporating lessons from every prior phase's
  review rounds: only ONE golden-snapshot equivalence proof is required (learned from A46's
  self-contradiction incident); diagnostic report window/symbols must be verified against
  A43-A46 precedent before committing (learned from A45's placeholder-symbol and A46's
  backwards-window incidents); a debug-loop-detection instruction was added for dev (learned from
  A46's first round timing out at 2400s).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-12 | codex → claude-code | done → design | P8a promoted from phase-contracts draft, confirmed A47 under the established renumbering |
| 2026-07-12 | claude-code → kimi-code | design → dev | A47 (P8a exit overhaul) started; re-verified no drift from A43-A46 |
| 2026-07-12 | kimi-code → codex | dev → review | A47 (P8a) exit overhaul (structural_atr) implemented |
