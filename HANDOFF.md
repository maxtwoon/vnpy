---
task: A44 P5 - Multi-Level Resonance Entry Filter
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

Continues the P1-P8 roadmap after A43 (P4 MACD-area divergence) reached `done`. P1-P4 are all
`done`, satisfying this phase's `Depends on` gate (P4 -> P5 -> P6 build win-rate on top of the
foundation).

**Task-ID renumbering (unchanged from A43's note):** the phase-contracts doc's original `Task
mapping` (`P5=A42`) is stale — A42 was consumed by the sync-guardian-hardening detour. Per the
2026-07-12 renumbering: **P4=A43 (done), P5=A44 (this task), P6=A45, P7=A46, P8a=A47, P8b=A48.**
Each phase is its own handoff task; P6 (A45) is not promoted until this task reaches `done`.

The daily trend filter is currently only a boolean "not clearly against me" gate:
`_daily_trend_filter_signals` (`chan_strategy/positions.py:18-38`, re-verified 2026-07-12 — line
numbers shifted slightly since the phase-contracts draft cited `:17-38` but the logic is
unchanged) excludes opens only when the daily position is in the blocked zone
(`中枢下方`/`中枢上方`), and for 二买/三买/二卖/三卖 additionally requires the daily direction
match; it never requires the daily structure to be *constructively* positioned. The core 缠论
win-rate mechanism is 级别共振 (multi-level resonance): take a lower-level buy point only when a
higher level (daily / 4H) is itself constructive, not merely "not negative." Confirmed no
`resonance_filter`/`resonance_freq_4h`/4H-level config or code exists yet (checked
`config.py`/`backtest_engine.py` 2026-07-12) — no drift since the draft was written.

Full contract: `docs/design/a38-phase-contracts-p2-p8.md` §"P5 (A42) - Multi-Level Resonance
Entry Filter" (the section header still says A42 — that is the stale label; this task's real ID
is A44, content is otherwise authoritative and unchanged).

## Goal

Add `resonance_filter` config gate (`"off"` default, byte-identical to current | `"daily"` |
`"daily_4h"`). Build a new 4H CZSC level (resample 1m -> 240min) in `backtest_engine`, updated
with the same no-lookahead `dt <=` advance pattern already used for the daily level. Under
`"daily"`: long opens additionally require daily `方向=向上` AND daily position in {中枢上方,
中枢内} (strictly positive, stricter than today's not-below gate); shorts symmetric. Under
`"daily_4h"`: additionally require the 4H level pass the same constructive test. Encoded as extra
`signals_all`/`signals_not` on the open Events. Add a read-only
`resonance_filter_comparison_report.py` (off/daily/daily_4h win-rate comparison, report only, not
for in-task selection).

## Acceptance Criteria

- [x] `resonance_filter="off"` (default) -> equity curve and every `Position.pairs` entry
      byte-identical to current (equivalence test).
- [x] `"daily"` blocks a long open when daily is 中枢下方 or 方向向下 even if the 30m signal
      fires (unit-tested); requires strictly-positive daily structure, not just not-below. Shorts
      symmetric.
- [x] `"daily_4h"` additionally blocks when the 4H level is non-constructive (unit-tested).
- [x] A new `test_4h_no_lookahead` (mirroring the existing `test_daily_no_lookahead`) passes; 4H
      bar timestamps are the last constituent 1m bar, and the loop only advances the 4H CZSC
      using bars up to and including the current one.
- [x] `resonance_filter_comparison_report.py` generated (report only, RESEARCH-ONLY banner);
      not used to select/tune parameters in-task.
- [x] No new numeric thresholds introduced ("constructive" reuses the existing categorical
      signals already produced by the daily/4H CZSC level, not a new tuned number); resonance
      gates entries only, exits unchanged; no third higher level (weekly) added.
- [x] No tuning of any threshold via backtest selection; no pre-2026-04-24 data used for any
      parameter choice; no SimNow order/cancel/send path changed; no `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` passes. **Correction (claude-code, 2026-07-12):** dev's
      completion summary claimed this script "does not exist in this working tree." That claim is
      false — it exists at `examples/czsc_strategy/diagnostics/run_next_work.ps1` (dev likely
      checked the wrong path) and runs cleanly; see the corrected Manual Verification block below.

## Manual Verification

Corrected and re-run natively by claude-code 2026-07-12 (dev's original claim that
`run_next_work.ps1` was absent was false):

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` -> **PASS** (467 passed,
  4 deselected).
- `python tools/sync_check.py` -> PASS (root). `python tools/sync_check.py --root
  examples/czsc_strategy` -> PASS (child).
- `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) -> **PASS**, 155 SimNow workflow
  unit tests passed, preflight completed cleanly, no WinError 5 sandbox issue.

### Note for reviewer (claude-code, 2026-07-12)

The `"off"` (default) equivalence acceptance item is currently backed only by
`test_off_mode_matches_legacy_daily_filter` (an `Event.is_match` signal-filter unit check) and the
`resonance_filter_comparison_report`'s `"off"` row — unlike A38-A43's precedent, there is no
dedicated full-`BacktestEngine.run()` pairs/equity diff proving `"off"` mode's output is
byte-identical to the pre-A44 baseline. By construction the `"off"` branch of
`_higher_level_filter_signals` calls `_daily_trend_filter_signals` with unchanged arguments, and
the new 4H-level code in `backtest_engine.py` is gated behind `resonance_filter == "daily_4h"`
only — so byte-identical output is very likely true, but this has not been proven the way prior
phases proved it. Flagging for the reviewer to judge whether this satisfies the acceptance
criterion's literal "equivalence test" requirement or whether dev should add one.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a38-phase-contracts-p2-p8.md`, section "P5 (A42) - Multi-Level
   Resonance Entry Filter" — ignore the stale `(A42)` label in the header, this task's real ID is
   **A44**. Full dev prompt and review checklist are in that section (verbatim, still accurate).
2. **Scope:** `chan_strategy/backtest_engine.py` (build/update the new 4H CZSC level, inject 4H
   signals), `chan_strategy/positions.py` (resonance conditions on open events, reusing/extending
   `_daily_trend_filter_signals`'s pattern), `chan_strategy/config.py` (new keys), plus tests and
   the new diagnostic. Do not touch `chan_strategy/signals.py`'s divergence logic (P4/A43, already
   done), 二买/三买 structural definitions (P6/A45), or any SimNow file.
3. **Gated + default-off discipline (standard house style):** `resonance_filter="off"` must
   reproduce current behavior byte-for-byte.
4. **No-lookahead is the highest-risk item this phase** — the 4H level must be built/advanced
   with exactly the same `dt <=` gating already proven correct for the daily level (see how
   `test_daily_no_lookahead` and the daily CZSC update path work in `backtest_engine.py` today;
   mirror that pattern, do not invent a new one). 4H bar timestamp = last constituent 1m bar.
5. **"Constructive" is categorical, not a new number:** `"daily"` reuses the daily level's
   existing 方向/位置 signals, just with a stricter condition (`中枢上方`/`中枢内` instead of
   "not 中枢下方"); do not introduce a new tuned numeric threshold to define "constructive."
6. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched;
   RESEARCH-ONLY banner on the new report; no `GOAL PASSED`; resonance must gate entries only
   (exits are P8's scope, do not touch them here).
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A44 (P5) multi-level resonance entry filter implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-12 - P5 promoted from the pre-authored phase-contracts draft to an active HANDOFF task
  as **A44** (not A42 — A42 was already consumed by the sync-guardian-hardening detour), following
  the same A43-A48 renumbering the user chose for A43. Sequential single-phase-at-a-time promotion
  continues: P6 (A45) waits until this task reaches `done`.
- 2026-07-12 - Re-verified `_daily_trend_filter_signals` (positions.py:18-38, was cited :17-38 in
  the original draft — line numbers shifted slightly from A43's signals.py changes elsewhere in
  the file, but the daily-filter logic itself is unchanged) and confirmed no
  `resonance_filter`/4H-level config or code exists yet — no drift from A43, which touched only
  `signals.py`/`sell_signals.py`/`validation.py`/`config.py`'s divergence keys.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-12 | codex → claude-code | done → design | P5 promoted from phase-contracts draft, renumbered A42→A44 (A42 consumed by sync-guardian-hardening detour) |
| 2026-07-12 | claude-code → kimi-code | design → dev | A44 (P5 multi-level resonance filter) started; re-verified no drift from A43 |
| 2026-07-12 | kimi-code → codex | dev → review | A44 (P5) multi-level resonance entry filter implemented |
