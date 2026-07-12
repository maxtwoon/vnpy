---
task: A45 P6 - 二买 Removal / Hard-Gate + ATR Chop Filter
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

Continues the P1-P8 roadmap after A44 (P5 multi-level resonance filter) reached `done`. P1-P5 are
all `done`, satisfying this phase's `Depends on` gate (P4 -> P5 -> P6 build win-rate on top of the
foundation).

**Task-ID renumbering (unchanged from A43/A44's note):** the phase-contracts doc's original `Task
mapping` (`P6=A43`) is stale — A43 is actually P4 under the 2026-07-12 renumbering. Confirmed
mapping: **P4=A43 (done), P5=A44 (done), P6=A45 (this task), P7=A46, P8a=A47, P8b=A48.** Each
phase is its own handoff task; P7 (A46) is not promoted until this task reaches `done`.

The original trading-expert review found 二买 (second-buy) to be measured negative expectancy in
backtests (RB 二买 0/6 all losses, SC 二买 PF 0.36, recurring -3% to -12.6% stops per
`key_trade_behavior_review.md`), and 缠论 buy points inside a compressed price range are
structurally unreliable (false breakout risk). Confirmed 2026-07-12: no `second_buy_mode` /
`atr_chop_filter` / ATR config or code exists yet in `config.py`/`positions.py`/`signals.py` — no
drift since the phase-contracts draft was written. `create_second_buy_position`
(`chan_strategy/positions.py:868`) is the 二买 sub-strategy factory; its open-gating path and
`ChanTimingStrategy.update` (`chan_strategy/positions.py:1463`, with the per-sub-strategy dispatch
around line 1531-1556) are the two integration points this phase touches.

Full contract: `docs/design/a38-phase-contracts-p2-p8.md` §"P6 (A43) - 二买 Removal / Hard-Gate +
ATR Chop Filter" (the section header still says A43 — that is the stale label; this task's real
ID is A45, content is otherwise authoritative and unchanged).

## Goal

Add two independent config gates:

- `second_buy_mode` (`"baseline"` default, legacy | `"gated"` | `"off"`). `"off"` blocks all NEW
  二买 opens (existing 二买 positions still receive exits/risk-control signals — the position is
  not deleted, only gated at open). `"gated"` opens 二买 only when P4 MACD divergence is present
  AND P5 resonance holds AND ATR is expanding (not in chop).
- `atr_chop_filter` (`"off"` default, legacy | `"on"`). Computes ATR(`atr_period`=14) on
  trade-frequency bars; if the current ATR's percentile vs the last `atr_lookback`=100 bars is
  below `atr_percentile_floor`=0.30, blocks ALL new opens that bar (range compression), across
  every sub-strategy, not just 二买.

Add a read-only `second_buy_and_atr_report.py` (二买 expectancy under baseline/gated/off, and
entry win-rate bucketed by ATR percentile, report only, not for in-task selection).

## Acceptance Criteria

- [x] `second_buy_mode="baseline"` and `atr_chop_filter="off"` (both defaults) -> equity curve
      and every `Position.pairs` entry byte-identical to current (full-`BacktestEngine`
      equivalence test with a git-tracked golden snapshot — follow the A44 pattern
      `test_resonance_filter_off_equivalence.py` established after review required it; do not
      ship with only a signal-filter unit check).
- [x] `second_buy_mode="off"` -> zero new 二买 opens across a replay; existing 二买 positions
      still receive exit/risk-control signals (unit-tested; do not delete the 二买 code path).
- [x] `second_buy_mode="gated"` -> a 二买 signal without MACD divergence (P4/A43), OR without P5
      resonance (A44), OR while ATR indicates chop, does NOT open (unit-tested for each missing
      condition individually); with all three conditions satisfied it opens.
- [x] `atr_chop_filter="on"` -> an open is blocked when the current ATR percentile <
      `atr_percentile_floor` (unit-tested); allowed above the floor. Applies to every
      sub-strategy's open path, not just 二买.
- [x] `second_buy_and_atr_report.py` generated (report only, RESEARCH-ONLY banner
      `Diagnostic only, not a trading recommendation.`); `atr_percentile_floor` is NOT tuned via
      the report in-task.
- [x] No threshold tuning via backtest/capture-data selection; no pre-2026-04-24 data used for
      any parameter choice; no SimNow order/cancel/send path changed; no `GOAL PASSED`; the 二买
      code path is kept behind `"off"`, not deleted; ATR filter gates opens only, never exits.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes — verify this script
      genuinely exists at `diagnostics/run_next_work.ps1` before claiming otherwise (A44's dev
      round falsely claimed it was absent; it is not).

## Manual Verification

Re-run natively by claude-code 2026-07-12:

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` -> **PASS** (490
  passed, 4 deselected).
- `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) -> **PASS**, 155 SimNow
  workflow unit tests passed, preflight completed cleanly, no WinError 5.

### Correction (claude-code, 2026-07-12): report generated against a placeholder symbol

Dev's initial `second_buy_and_atr_report_2026-07-12.{json,md}` was generated with
`symbols_attempted: ["TEST"]` (a placeholder that fails to load: `数据加载失败`) instead of the
script's own real default `SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]`
(`second_buy_and_atr_report.py:31`) — the report shipped with an empty per-symbol table and an
empty ATR-percentile-bucket table, demonstrating nothing. Re-ran
`python diagnostics/second_buy_and_atr_report.py` with no `--symbols` override (i.e. real
defaults) from `examples/czsc_strategy/`: now shows real trade counts/win-rates for
AP888/SC888/ZN888 (RB888/A888 report `交易周期数据不足`, an honest `error` field, consistent with
A43/A44's reports on the same post-2026-04-24 window) and a populated ATR-percentile-bucket
table. Replaced the placeholder report files with this real-data version before committing.

## Notes for the Next Agent

(review reject - codex, 2026-07-12)

1. Fix `second_buy_mode="gated"` resonance semantics. The P6 contract says gated 二买 requires
   P4 MACD divergence + P5 resonance + ATR expansion. Current code routes the resonance check
   through `_higher_level_filter_signals()`; when `resonance_filter="off"` this falls back to the
   legacy daily trend filter, so `_research_second_buy_allowed()` can return true without any P5
   resonance filter being enabled. The test suite currently codifies that bad case in
   `test_second_buy_mode.py::test_gated_opens_when_all_conditions_hold`, which sets
   `resonance_filter="off"` and still expects a gated open. Add/adjust tests so gated mode rejects
   missing P5 resonance, and make the open gate require the actual P5 resonance condition.

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a38-phase-contracts-p2-p8.md`, section "P6 (A43) - 二买 Removal
   / Hard-Gate + ATR Chop Filter" — ignore the stale `(A43)` label in the header, this task's
   real ID is **A45**. Full dev prompt and review checklist are in that section (verbatim, still
   accurate).
2. **Scope:** `chan_strategy/positions.py` (二买 mode gate in the buy2 open/update path around
   line 868/1531-1556; ATR filter in the open path of `ChanTimingStrategy.update` around line
   1463 — applies to ALL sub-strategies, not just 二买), a new ATR + percentile helper (either in
   `chan_strategy/signals.py` or a new util module — dev's choice per the design), `config.py`
   (new keys), tests, and the new diagnostic. Do not touch `signals.py`'s divergence logic
   (P4/A43, done) or `backtest_engine.py`'s resonance/4H-level code (P5/A44, done) beyond reading
   their existing signal outputs to gate `"gated"` mode.
3. **This phase depends on P4 (A43) and P5 (A44) outputs, both `done`:** `"gated"` mode's three
   conditions are P4's MACD divergence signal, P5's resonance signal, and this phase's own new
   ATR-expansion check — read the existing signal keys those phases produce, do not reimplement
   them.
4. **Gated + default-off discipline (standard house style):** both `second_buy_mode="baseline"`
   and `atr_chop_filter="off"` must reproduce current behavior byte-for-byte. Per the
   Acceptance Criteria above, this equivalence MUST be proven with a full-`BacktestEngine`
   golden-snapshot regression test from the start (A44 shipped without one and was rejected for
   it — do not repeat that mistake; write `test_second_buy_and_atr_off_equivalence.py` following
   `test_resonance_filter_off_equivalence.py`'s pattern up front).
5. **`"off"` blocks opens, not the position:** existing 二买 positions must continue to receive
   exit/risk-control signals when `second_buy_mode="off"` — this is an open-gate, not a deletion
   of the 二买 sub-strategy. Unit-test this distinction explicitly (existing positions still exit
   correctly).
6. **ATR filter is universal:** `atr_chop_filter="on"` blocks new opens for every sub-strategy
   when in a chop regime, not scoped to 二买 only — re-read the design's Semantics section
   carefully on this point.
7. **No new numeric tuning:** `atr_period`(14)/`atr_lookback`(100)/`atr_percentile_floor`(0.30)
   are conservative starting defaults per the design, not to be tuned via the comparison report
   in this task.
8. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched;
   RESEARCH-ONLY banner on the new report; no `GOAL PASSED`; 二买 code path retained (not
   deleted); ATR filter never touches exits.
9. **Before claiming any script "doesn't exist," verify the path carefully** —
   `run_next_work.ps1` lives at `examples/czsc_strategy/diagnostics/run_next_work.ps1`, not the
   `examples/czsc_strategy/` root. A44's dev round falsely claimed it was absent; this wasted a
   review round's worth of manual-verification correction.
10. Finish with the acceptance commands, then
    `python tools/handoff.py next --actor kimi-code --summary "A45 (P6) second-buy removal/hard-gate + ATR chop filter implemented"`.
    Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-12 - P6 promoted from the pre-authored phase-contracts draft to an active HANDOFF task
  as **A45** (not A43 — A43 is P4 under the established renumbering), continuing the sequential
  single-phase-at-a-time promotion. P7 (A46) waits until this task reaches `done`.
- 2026-07-12 - Re-verified no `second_buy_mode`/`atr_chop_filter`/ATR config or code exists yet in
  `config.py`/`positions.py`/`signals.py` — no drift from A43/A44, which touched
  `signals.py`/`sell_signals.py`/`validation.py` (A43) and `backtest_engine.py`/`positions.py`'s
  higher-level filter helpers (A44) but not the 二买 open path or any ATR logic.
- 2026-07-12 - Added an explicit acceptance criterion requiring a full-`BacktestEngine`
  golden-snapshot equivalence test from the start (not just a signal-filter unit check), directly
  incorporating the lesson from A44's review reject so this task doesn't repeat the same review
  round.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-12 | codex → claude-code | done → design | P6 promoted from phase-contracts draft, confirmed A45 under the established renumbering |
| 2026-07-12 | claude-code → kimi-code | design → dev | A45 (P6 二买 hard-gate + ATR chop filter) started; re-verified no drift from A43/A44 |
| 2026-07-12 | kimi-code → codex | dev → review | A45 (P6) second-buy removal/hard-gate + ATR chop filter implemented |
| 2026-07-12 | codex → kimi-code | review → dev | 打回: gated second-buy opens without required P5 resonance |
| 2026-07-12 | kimi-code → codex | dev → review | A45 (P6) second-buy removal/hard-gate + ATR chop filter implemented; gated mode now requires actual P5 resonance regardless of resonance_filter setting |
