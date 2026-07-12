---
task: A43 P4 - MACD-Area Divergence (Replace _bi_power Proxy)
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-12
deliverables:
  - HANDOFF.md
  - docs/design/a38-phase-contracts-p2-p8.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

Resumes the P1-P8 backtest-return-quality roadmap (`docs/design/a38-strategy-improvement-roadmap.md`
Part I, `docs/design/a38-phase-contracts-p2-p8.md` Part II) after the diagnostics-integrity
detour (A41 SimNow authenticity fix, A42 sync-guardian hardening) reached `done`. P1 (A38 touch
stops), P2 (A39 rollover/trading-calendar), P3 (A40 real position sizing) are all `done`,
satisfying this phase's `Depends on` gate.

**Task-ID renumbering note:** the phase-contracts doc's original `Task mapping` table
(`P4=A41, P5=A42, ..., P8=A45`) is now stale — task IDs A41/A42 were consumed by the unplanned
SimNow-authenticity/sync-guardian audit line of work, not by P4/P5. Renumbered per user decision
2026-07-12: **P4=A43 (this task), P5=A44, P6=A45, P7=A46, P8a=A47, P8b=A48.** Each phase remains
its own handoff task (design→dev→review→done); do not batch multiple phases into one dev handoff
(explicit rule in the phase-contracts doc's Cross-Phase Notes) — P5 is not promoted until P4
reaches `done`.

背驰 (divergence) is currently approximated by raw stroke amplitude `_bi_power = abs(high-low)`
(`chan_strategy/signals.py:55`, re-verified unchanged 2026-07-12), a crude proxy that mislabels
many 一买/一卖 → low first-buy win rate (26-37% on several symbols per the original trading-expert
review). Standard 缠论 背驰 compares MACD area/DIF between the entering and leaving segments. This
is flagged as the single highest-leverage win-rate lever in the roadmap.

Full contract: `docs/design/a38-phase-contracts-p2-p8.md` §"P4 (A41) - MACD-Area Divergence" (the
section header still says A41 — that is the stale label; this task's real ID is A43, content is
otherwise authoritative and unchanged).

## Goal

Add `divergence_model` config gate (`"amplitude"` default, byte-identical to current | `"macd"`).
Under `"macd"`: compute `DIF = EMA(fast) - EMA(slow)`, `DEA = EMA(DIF, signal)`,
`hist = 2*(DIF-DEA)` on confirmed trade-frequency closes (fixed 12/26/9, NOT tuned in-task);
compare leaving-segment vs entering-segment MACD magnitude for 一买/一卖/一买多头/一卖空头
classification instead of `_bi_power`. Delete the orphaned amplitude `背驰=失效` branch
(`signals.py:268-284`, A37 already removed its consumers — confirmed still unreachable/orphaned
2026-07-12). Add a read-only `divergence_model_comparison_report.py` (amplitude vs macd win-rate,
report only, not for in-task selection).

## Acceptance Criteria

- [x] `divergence_model="amplitude"` (default) → equity curve and every `Position.pairs` entry
      byte-identical to current (equivalence test, ≥2 symbols × 1 year).
      *Evidence:* `diagnostics/divergence_amplitude_equivalence_check.py` on AP888/RB888
      2025-01-01~2025-12-31: pairs_equal=True, equity_equal=True.
- [x] `"macd"`: a fixture where amplitude flags divergence but MACD does not (and the reverse)
      yields the specified differing classifications; MACD params are exactly 12/26/9 and NOT
      tuned in-task.
      *Evidence:* `tests/unit/test_divergence_macd.py` fixtures and param assertions.
- [x] Orphan `背驰=失效` branch removed; no code references it; `chan_strategy/validation.py`
      exhaustiveness sets updated to match; a test enforces confirmed-BI direction alternation
      (no adjacent same-direction fake structure as coverage).
      *Evidence:* branch deleted from `signals.py`; `validation.py` updated; `test_signals.py`
      `test_confirmed_bi_directions_alternate`.
- [x] If a MACD `失效` class is added, real signal-history replay shows count > 0; else it is
      absent (no unreachable class shipped).  *Evidence:* no MACD `失效` class added.
- [x] `divergence_model_comparison_report.py` generated (report only, RESEARCH-ONLY banner
      `Diagnostic only, not a trading recommendation.`); not used to select/tune parameters
      in-task.
      *Evidence:* `diagnostics/divergence_model_comparison_report_2026-07-12.{json,md}`.
- [x] No tuning of any threshold via backtest selection; no pre-2026-04-24 data used for any
      parameter choice; no SimNow order/cancel/send path changed; no `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` passes (or the documented Manual-verification accommodation
      applies if the codex-sandbox symlink limitation recurs — add a fresh block to this
      HANDOFF.md if needed).

## Manual verification (symlink-privilege sandbox limitation)

Run natively (outside the codex sandbox) by claude-code 2026-07-12, in response to codex's
review-round finding that its own sandboxed run hit the documented `tmp_path`/
`PermissionError [WinError 5]` symlink-privilege limitation (see the NOTE above the review
command in `.synccheck.yml`):

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` -> **453 passed, 4
  deselected**, no WinError 5.
- `run_next_work.ps1 -Preflight` -> **155 passed** (SimNow workflow unit tests), preflight
  completed cleanly, no WinError 5.
- `python tools/sync_check.py` -> PASS (root). `python tools/sync_check.py --root
  examples/czsc_strategy` -> PASS (child).

Reviewer (codex, sandboxed) may trust these counts for the two sandbox-blocked acceptance items
instead of re-running them; everything else should still be verified normally.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

### Review Findings (codex, 2026-07-12)

1. ~~Remove the MACD-mode warmup fallback in
   `examples/czsc_strategy/chan_strategy/signals.py:95-100`.~~ **Resolved in this round:**
   the amplitude/close-difference fallback was removed from `_macd_power_for_segment`, and
   `test_macd_mode_does_not_fallback_to_close_difference_on_short_history` was added to
   `tests/unit/test_divergence_macd.py` to prove MACD mode stays MACD-based even when the
   confirmed-bar history is shorter than the conventional MACD warm-up length.

Previously rejected items now appear resolved: the unused `deepcopy`/`BACKTEST_CONFIG` imports were
removed, and the required Manual verification block is present with native pass counts for the
sandbox-blocked unit/preflight commands.

1. **Entry point:** `docs/design/a38-phase-contracts-p2-p8.md`, section "P4 (A41) - MACD-Area
   Divergence" — ignore the stale `(A41)` label in the header, this task's real ID is **A43**.
   Full dev prompt and review checklist are in that section (verbatim, still accurate).
2. **Scope:** `chan_strategy/signals.py` (new `signal_divergence_macd` helper; gate in
   `signal_divergence_status`/`signal_first_buy`; delete orphan `失效` branch),
   `chan_strategy/sell_signals.py` (`signal_first_sell` MACD path), `chan_strategy/validation.py`
   (keep exhaustiveness exact), `chan_strategy/config.py` (new keys), plus tests and the new
   diagnostic. Do not touch `positions.py`'s 二买/三买 structural definitions (P6/A45), resonance
   filtering (P5/A44), or any SimNow file.
3. **Gated + default-off discipline (standard, unlike A41's deliberate exception):**
   `divergence_model="amplitude"` must reproduce current behavior byte-for-byte. This is back to
   the normal A37-A40 house style — A41's safe-by-default deviation does NOT apply here.
4. **H3 resolution:** the amplitude `背驰=失效` branch (`signals.py:268-284`) is confirmed
   unreachable and orphaned (A37 already removed its consumers; re-verified 2026-07-12) — delete
   it under all modes, not just under `"macd"`. A MACD-based failure class may optionally be
   added under `"macd"` ONLY if real signal-history replay shows a nonzero count; do not ship an
   unreachable class either way.
5. **MACD params are fixed, not tunable in this task:** 12/26/9 standard values only. The
   comparison report is read-only evidence, never a selection mechanism — reject-on-violation if
   used to pick parameters in-task.
6. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched;
   RESEARCH-ONLY banner on the new report; no `GOAL PASSED`; validation exhaustiveness must stay
   exact (no orphaned or unreachable classes).
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A43 (P4) MACD-area divergence implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Completion Summary

A43 (P4) MACD-area divergence implemented by kimi-code 2026-07-12:

- Added `divergence_model` gate (`"amplitude"` default, `"macd"`) plus fixed MACD params
  (`macd_fast=12`, `macd_slow=26`, `macd_signal=9`) to `chan_strategy/config.py`.
- Implemented MACD |hist|-area divergence helper in `chan_strategy/signals.py` using only
  confirmed trade-frequency closes (no lookahead).
- Gated `signal_divergence_status`, `signal_first_buy` (signals.py) and `signal_first_sell`
  (sell_signals.py) through `_divergence_power`.
- Deleted the orphaned amplitude `背驰=失效` branch in `signal_divergence_status`; updated
  `chan_strategy/validation.py` exhaustiveness set and all unit tests referencing it.
- Added `tests/unit/test_divergence_macd.py` for amplitude/MACD fixture disagreement and
  standard-param assertions; added `test_confirmed_bi_directions_alternate` to `test_signals.py`.
- Added read-only `diagnostics/divergence_model_comparison_report.py` (RESEARCH-ONLY banner)
  and ran it for the post-2026-04-24 window, producing the 2026-07-12 report artifacts.
- Added `diagnostics/divergence_amplitude_equivalence_check.py` and verified amplitude-mode
  byte-identical reproduction on AP888/RB888 2025 full-year.
- All gates green: unit tests (452 passed), both sync checks, and `run_next_work.ps1 -Preflight`.

## Decision Log

- 2026-07-12 - P4 promoted from the pre-authored phase-contracts draft to an active HANDOFF task
  as **A43** (not A41 — A41/A42 were already consumed by the SimNow-authenticity/sync-guardian
  detour). User chose this renumbering (A43-A48 for P4-P8) plus sequential single-phase-at-a-time
  promotion over the phase-contracts doc's own explicit "one dev handoff per phase" rule.
- 2026-07-12 - Re-verified `_bi_power` (signals.py:55) and the orphaned amplitude `失效` branch
  (signals.py:268-284) are unchanged since the phase-contracts draft was written — no drift from
  A39/A40/A41/A42, none of which touched `chan_strategy/signals.py`.
- 2026-07-11 (design, original phase-contracts doc) - Fixed MACD params at the 12/26/9 standard,
  explicitly deferring tuning to a future holdout-validated task, to keep this phase's scope to
  the divergence *measure* only, not parameter selection.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-12 | codex → claude-code | (new) → design | P4 promoted from phase-contracts draft, renumbered A41→A43 (A41/A42 consumed by SimNow/sync-guardian detour) |
| 2026-07-12 | claude-code → kimi-code | design → dev | A43 (P4 MACD-area divergence) started; re-verified no drift in signals.py since draft |
| 2026-07-12 | kimi-code → codex | dev → review | A43 (P4) MACD-area divergence implemented |
| 2026-07-12 | codex → kimi-code | review → dev | 打回: CI lint blocker and missing manual verification block |
| 2026-07-12 | kimi-code → codex | dev → review | A43 (P4) MACD-area divergence implemented |
| 2026-07-12 | codex → kimi-code | review → dev | 打回: MACD mode has undocumented amplitude fallback |
| 2026-07-12 | kimi-code → codex | dev → review | A43 (P4) MACD-area divergence implemented |
| 2026-07-12 | codex → codex | review → done | A43 (P4) MACD-area divergence review accepted |
