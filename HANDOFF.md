---
task: A73 - Rollover-Window Return Contribution Report
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a73-third-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

First of three tasks (A73-A75) from the THIRD third-party audit remediation roadmap
(`docs/design/a73-third-audit-remediation-roadmap.md`), promoted after A72 (final task of the
A70-A72 roadmap) reached `done`. A fresh audit run by codex (using the `ai-stock-trading-reviewer`
methodology) scored 67/100 (up from 66), with **no fatal items** and 6 medium-severity findings.
claude-code scoped 3 of the 6 down to actionable dev tasks (A73/A74/A75); the other 3 are either
non-code (waiting for more real calendar time to accumulate genuine out-of-sample data — cannot be
accelerated by any code change), architecture-scale work needing its own dedicated design effort
(unifying `portfolio_risk` weight-based accounting with `sizing_model="risk"` lot-based accounting
— currently a deliberate `NotImplementedError` from A53), or blocked on an external data source this
repo doesn't have access to (exchange-published date/contract-specific limit/margin tables). See
the design doc's own scoping table for full reasoning on all 6 findings.

**Standing instruction for this whole third roadmap (user pre-authorized, same as the second
roadmap)**: keep iterating — after A73/A74/A75 reach `done`, trigger a fresh audit again, scope any
new findings the same way, and repeat — until the audit score exceeds 75 with no medium-or-higher
open issues. Human-decision points resolved per claude-code's own recommended judgment, not
re-asked each time. **Note**: given 3 of the current 6 medium findings are explicitly non-code
(time-gated) or out of this repo's current scope (external data access), reaching "no medium+
issues" purely through bounded dev tasks may not be fully achievable — this should be surfaced
honestly when reporting status, not silently declared solved.

**Full contract**: `docs/design/a73-third-audit-remediation-roadmap.md` §"A73" (this HANDOFF
summarizes it — read the full Rationale/Semantics there before writing code).

## Goal

The audit found `chan_strategy/data_adapter.py:347-354` documents that the 888 continuous-contract
tables are raw, unadjusted contract splices with rollover-transition price discontinuities. A52
(`rollover_stat_tagging`, already `done`) tags each closed `Position.pairs` entry with a boolean
`is_rollover_window` (`backtest_engine.py:572-576`) — but no report currently splits "rollover-
window trades" vs "non-rollover-window trades" to show their separate return contribution. Add
`diagnostics/rollover_contribution_report.py`: run a backtest with `rollover_stat_tagging="on"`,
split closed trades by `is_rollover_window`, and report each group's total return contribution, win
rate, and average P&L per symbol. This is an honest measurement report — no pass/fail threshold,
no exclusion logic, just visibility into how much of the reported performance sits inside rollover
windows.

## Acceptance Criteria

- [ ] `diagnostics/rollover_contribution_report.py` implemented: per-symbol comparison of
      "rollover-window" vs "non-rollover-window" closed trades — total return contribution, win
      rate, average P&L, and trade count for each group.
- [ ] The report errors clearly (not silently produces misleading all-zero/empty output) if run
      without `rollover_stat_tagging="on"`.
- [ ] New unit tests use constructed `Position.pairs` fixtures (no real historical DB dependency) to
      verify the grouping/aggregation logic.
- [ ] `backtest_engine.py`'s existing A52 tagging logic and its existing tests are unchanged.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a73-third-audit-remediation-roadmap.md` §"A73". First of three
   A73-A75 tasks from the third audit roadmap.
2. **Reuse the existing "run a backtest, read `Position.pairs`" pattern** already used by
   `diagnostics/backtest_matrix_report.py`/`risk_param_sensitivity_report.py` — do not invent a new
   way of invoking `BacktestEngine`.
3. **Scope:** new `diagnostics/rollover_contribution_report.py` plus a new test file under
   `tests/unit/`. Do not touch `chan_strategy/backtest_engine.py`'s existing A52 tagging logic, any
   SimNow order/cancel/send path, or any signal-calculation logic.
4. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A73-scoped files are staged.**
5. **Guardrails (reject-on-violation):** no pass/fail threshold invented (this is a measurement
   report only); no pre-2026-04-24 data for any new parameter choice; no SimNow order/cancel/send
   paths touched; no `GOAL PASSED`; RESEARCH-ONLY banner required per A54 convention
   (`build_banner()`).
6. **Include a Manual-verification block with natively-run counts** (claude-code will also
   independently re-run everything before triggering review — this has become the norm across
   every task in this pipeline, do not skip writing your own), and run `ruff check` proactively
   before finishing.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A73 rollover-window contribution report implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-15 - Third third-party audit (67/100, up from 66, no fatal items) scoped down to
  A73/A74/A75 by claude-code; the other 3 of 6 findings are non-code (real-time-gated OOS evidence),
  architecture-scale (portfolio_risk/risk-sizing accounting unification, already a deliberate A53
  `NotImplementedError`), or blocked on an external data source this repo doesn't have (exchange
  limit/margin tables). User's standing pre-authorization from the second roadmap carries forward
  to this third roadmap without re-asking.
- 2026-07-15 - A73 promoted from `docs/design/a73-third-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task. First of three tasks in this roadmap.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | claude-code → kimi-code | design → dev | A73 (rollover-window contribution report) promoted from third third-party audit remediation roadmap; handoff design->dev |
