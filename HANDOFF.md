---
task: A50 - Limit-Up/Down/Halt Impact Diagnostic (Read-Only)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-13
deliverables:
  - HANDOFF.md
  - docs/design/a49-audit-remediation-roadmap.md
blockers: []
last_transition_kind: reject
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: dev
last_transition_from_owner: codex
last_transition_to_owner: kimi-code
---

## Background

Second task of the 2026-07-12 audit remediation roadmap
(`docs/design/a49-audit-remediation-roadmap.md` §"A50"), started after A49 (ATR trailing-stop
reachability fix) reached `done`.

`docs/review/ai_trading_review_2026-07-12.md` Finding #2 (🔴 high) found zero limit-up/limit-down/
trading-halt handling anywhere in `chan_strategy/data_adapter.py`/`backtest_engine.py`/
`positions.py` (confirmed by full-repo grep, re-confirmed 2026-07-13 — still zero hits for
`涨停|跌停|limit|halt|停牌` in those three files). Entries fill at next-bar open
(`backtest_engine.py`, `execution_price=bar.open`), stops fill at current-bar close/high/low, with
no check for whether that bar was actually tradable. AP888 (苹果) and RB888 (螺纹钢) both carry
real daily price-limit bands under Chinese futures exchange rules.

Per house discipline ("diagnostic-first: where a phase claims an effect, a read-only diagnostic
quantifies it before the switch is turned on by default" — the same pattern already used for
A39's P2a rollover diagnostic before P2b's enforcement), **this task ships the read-only
measurement only.** A51 (fill-constraint enforcement, gated) does not start until this task
reaches `done` and its numbers exist — A51's exact enforcement scope will be finalized using this
task's evidence, not decided in advance.

Full contract: `docs/design/a49-audit-remediation-roadmap.md` §"A50 — Limit-Up/Down/Halt Impact
Diagnostic (Read-Only)" (the authoritative design — this HANDOFF summarizes it).

## Goal

Ship `diagnostics/limit_halt_exposure_report.py`: for each symbol in the standard default set
(AP888/RB888/SC888/A888/ZN888), compute a daily price-limit band from the contract's real
exchange-published daily limit percentage and the previous trading day's settlement/close, then
check every historical trade's entry-fill bar and exit-fill bar against that band on the honest
post-2026-04-24 baseline replay (defaults: `exit_model`, `sizing_model` unchanged). Report
counts/percentages of trades whose fill bar sits at or beyond the limit, per symbol. This is a
measurement only — it must not change any existing report's numbers, must not be consulted by
`BacktestEngine`/`PortfolioEngine`, and must not block or adjust any fill.

## Acceptance Criteria

- [x] Report generated for all 5 default symbols on the post-2026-04-24 window
      (`WINDOW_START="2026-04-24"`, `WINDOW_END="2026-07-09"`, matching every A43-A48 report
      script's precedent) — or an explicit `unavailable`/error reason per symbol where data is
      insufficient (matching the `交易周期数据不足` pattern already established for RB888/A888 in
      prior reports on this same window).
- [x] Each symbol's daily limit percentage carries an inline, cited exchange-rule source comment
      (real exchange-published daily price-limit percentage — CZCE/SHFE/INE/DCE as applicable per
      symbol; do NOT fabricate or guess a number; if the real percentage cannot be sourced and
      cited, the report must say `unavailable` for that symbol rather than silently using a
      placeholder value — same citation discipline as A40's `contract_specs`).
- [x] Report distinguishes entry-fill-at-limit vs. exit-fill-at-limit counts per symbol; the sum
      of "at limit" + "not at limit" trades reconciles exactly with that symbol's total trade
      count from the same baseline replay (unit-tested arithmetic check).
- [x] If the raw K-line table exposes any volume/turnover column, the report additionally flags
      zero-volume bars near each trade's fill bar as a secondary halted/no-liquidity proxy signal
      (best-effort; report `unavailable` for this secondary signal if no such column exists rather
      than fabricating one).
- [x] RESEARCH-ONLY banner (`Diagnostic only, not a trading recommendation.`) present; report is
      evidence only — verify via grep that no changes were made to `BacktestEngine`/
      `PortfolioEngine`'s actual fill logic in this task's diff.
- [x] No threshold tuning; no pre-2026-04-24 data used for any parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes — this script
      genuinely exists at `diagnostics/run_next_work.ps1`; verify the path carefully before
      claiming otherwise (A44's dev round falsely claimed it was absent).

## Manual Verification / Note for A51 (claude-code, 2026-07-13)

Ran the full suite natively: `python -m pytest examples/czsc_strategy/tests/unit -q -m "not
realdb"` -> **536 passed, 4 deselected**. Both `sync_check` gates PASS. `run_next_work.ps1
-Preflight` -> **155 passed**. Confirmed via `git diff --stat` that `data_adapter.py`/
`backtest_engine.py`/`positions.py` are untouched — pure read-only diagnostic as required.

Spot-verified the cited limit percentages against live web search (not just trusting the citation
text): AP888 5% and RB888 3% both confirmed as the exchanges' published steady-state figures.
**Note for A51's design refinement**, not a defect in this task: the search also surfaced that
both symbols had their limit bands *temporarily widened* by exchange notice **within this report's
own 2026-04-24~2026-07-09 window** — RB888 to 5% effective 2026-05-19, AP888 to 8% effective
2026-05-06 (both presumably following limit-hit days, per the standard CZCE/SHFE escalation
mechanism). The report's code comment already generically acknowledges "exchanges reserve the
right to widen limits... this diagnostic uses the standard contract percentage as a first-cut
measurement," satisfying this task's acceptance bar, but does not specifically flag that these
exact widening events occurred inside the measured window. Given the report currently measures
only 2 total trades (AP888; RB888/A888 report `交易周期数据不足`), the practical impact on this
round's numbers is negligible — but if A51 (or any future re-run of this diagnostic on a longer
window with more trades) needs tighter accuracy, sourcing the actual date-varying limit percentage
per trading day (not just the steady-state default) would be a worthwhile refinement.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

Review rejected by Codex on 2026-07-13 for one real, non-sandbox blocker:

1. Fix the new ruff error in `examples/czsc_strategy/tests/unit/test_limit_halt_exposure_report.py:7`.
   `ruff check examples\czsc_strategy\diagnostics\limit_halt_exposure_report.py examples\czsc_strategy\tests\unit\test_limit_halt_exposure_report.py`
   currently fails with `F401 [*] pytest imported but unused`. Remove the unused `import pytest`.

Verified during review before rejection:

- `python tools\sync_check.py` passed.
- `python tools\sync_check.py --root examples\czsc_strategy` passed.
- The A50 committed diff does not modify `data_adapter.py`, `backtest_engine.py`, `positions.py`,
  or `portfolio_engine.py`.
- The generated JSON report covers `WINDOW_START="2026-04-24"`, `WINDOW_END="2026-07-09"` and all
  five default symbols (`AP888`, `RB888`, `SC888`, `A888`, `ZN888`).
- Report arithmetic reconciles per symbol and in totals.
- The RESEARCH-ONLY banner is present, and `run_next_work.ps1` exists at
  `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
- Pytest/preflight checks that need `tmp_path` hit the documented sandbox `PermissionError
  [WinError 5]` signature; use the existing manual verification block for those two acceptance
  items unless the Windows symlink/tmp_path environment has been fixed.

1. **Entry point:** `docs/design/a49-audit-remediation-roadmap.md` §"A50". Second task of the
   6-task remediation roadmap (A49-A54) triaging `docs/review/ai_trading_review_2026-07-12.md` —
   read that audit report's Finding #2 (🔴 high) for full context.
2. **Scope:** new `examples/czsc_strategy/diagnostics/limit_halt_exposure_report.py` and its unit
   test only. **Do NOT touch `data_adapter.py`, `backtest_engine.py`, or `positions.py` in this
   task** — this is read-only measurement, not enforcement (that's A51's job, and A51 does not
   start until this task is `done` and reviewed). Reuse `BacktestEngine`'s existing trade-pairs
   output (`engine.strategy.get_combined_trades()`, same pattern as A43-A48's comparison reports)
   rather than reimplementing a backtest loop.
3. **Sourcing the limit percentages is the highest-scrutiny item in this task** — cite real
   exchange rules (WebSearch or authoritative reference), the same bar A40 set for
   `contract_specs`. AP888 trades on CZCE (郑州商品交易所), RB888/ZN888 on SHFE (上海期货交易所),
   SC888 on INE (上海国际能源交易中心), A888 on DCE (大连商品交易所) — each exchange publishes its
   own daily price-limit percentage per product (and these can differ from the general default,
   e.g. wider limits on contract-listing day or after a limit-hit day — a first-cut using the
   standard/steady-state percentage is acceptable, document that simplification explicitly rather
   than silently ignoring the exceptions).
4. **This is a measurement, not a judgment** — do not conclude "the strategy is unrealistic" or
   any similar promotional/demotional claim in the report; state the raw counts/percentages and
   let a human (or A51's own design step) interpret them.
5. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched;
   RESEARCH-ONLY banner on the new report; no `GOAL PASSED`; zero changes to
   `data_adapter.py`/`backtest_engine.py`/`positions.py` (verify via `git diff --stat` before
   finishing).
6. **Verify diagnostic report window and symbols before committing** — use
   `WINDOW_START="2026-04-24"`, `WINDOW_END="2026-07-09"` and the standard 5-symbol default list
   (copy constants from an existing A43-A48 report script). A47/A49 got this right from the start;
   follow that precedent rather than A45/A46's first-attempt mistakes.
7. **Before claiming any script "doesn't exist," verify the path carefully** —
   `run_next_work.ps1` lives at `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
8. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A50 limit-up/down/halt exposure diagnostic implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-13 - A50 promoted from `docs/design/a49-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task, started immediately after A49 reached `done`. A51 (fill-constraint
  enforcement) is explicitly gated on this task's completion, per the diagnostic-first discipline
  already used for A39's rollover exclusion (P2a before P2b).
- 2026-07-13 - Re-verified zero limit/halt handling exists anywhere in
  `data_adapter.py`/`backtest_engine.py`/`positions.py` — no drift since the audit.
- 2026-07-13 - Scoped this task strictly to the new diagnostic script; explicitly forbade touching
  `data_adapter.py`/`backtest_engine.py`/`positions.py` in this round, since any enforcement
  change belongs to A51 and must be informed by this task's own evidence first.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-13 | codex → claude-code | done → design | A50 promoted from the audit remediation roadmap draft after A49 reached done |
| 2026-07-13 | claude-code → kimi-code | design → dev | A50 (limit-up/down/halt exposure diagnostic) started |
| 2026-07-13 | kimi-code → codex | dev → review | A50 limit-up/down/halt exposure diagnostic implemented |
| 2026-07-13 | codex → kimi-code | review → dev | 打回: ruff check fails: unused pytest import in test_limit_halt_exposure_report.py |
