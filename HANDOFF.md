---
task: A83 - Read-Only Portfolio Margin/PnL Ledger Report (Phase 1)
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-16
deliverables:
  - HANDOFF.md
  - docs/design/portfolio-risk-fusion-design.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

First phase of the portfolio-risk/risk-sizing unification work
(`docs/design/portfolio-risk-fusion-design.md`), following the user's explicit decision on 2026-07-16:
lots/real-margin accounting is the source of truth for a unified portfolio account (not
weight-based); `risk_parity`/`cluster_gross_cap` remain as pre-trade budget/priority constraints,
not final accounting. The user specified a three-phase rollout — this task is Phase 1 ONLY:
a read-only ledger report, no gating, no changes to the existing
`sizing_model="risk"` + `portfolio_risk="on"` `NotImplementedError` block.

`PortfolioCoordinator.run()` (`chan_strategy/portfolio_engine.py:606-615`) raises
`NotImplementedError` when both flags are `"on"`, but this check fires BEFORE
`_run_per_symbol()` is called — confirmed by claude-code: `_run_per_symbol()`
(`portfolio_engine.py:338`) is a plain per-symbol loop over independent `BacktestEngine.run()`
calls, with no weight-coordination logic and no dependency on the gate. This means Phase 1 can be
built as a **new, standalone diagnostic script** that calls each symbol's own `BacktestEngine.run()`
directly (`sizing_model="risk"`), reads the margin/PnL data each engine already produces, and
aggregates it into a portfolio-level view — without touching `PortfolioCoordinator.run()`,
its existing gate, or any existing test.

**Full contract**: `docs/design/portfolio-risk-fusion-design.md` §"已确认的下一步（阶段一...）"
(this HANDOFF summarizes it — read the full design doc for the complete background and the user's
stated rationale before writing code).

## Goal

Add a new diagnostic script (e.g. `diagnostics/portfolio_ledger_report.py`) that, for a given set
of symbols and date range, runs each symbol's own `BacktestEngine` independently with
`sizing_model="risk"` (reusing the same per-symbol execution pattern as
`PortfolioCoordinator._run_per_symbol()` — either by importing/calling that method directly, or by
writing an equivalent loop if reuse proves awkward; dev's call, record the choice), then aggregates
by timestamp across symbols into a read-only portfolio ledger:

- Portfolio-level total margin occupied (sum of each symbol's `total_open_margin`, already present
  in `generate_report()`'s output per A40).
- Portfolio-level realized currency PnL (sum of each symbol's closed-trade `pnl_currency` from
  `strategy.get_combined_trades()`).
- Max portfolio margin utilization (portfolio total margin / initial capital, over the run).
- Per-symbol margin/PnL breakdown.
- Per-cluster margin breakdown, reusing `STRATEGY_CONFIG["corr_clusters"]`'s existing symbol
  groupings (`config.py:149-151`) — do not invent a new clustering mechanism.

**This is a measurement-only report** — no pass/fail threshold, no gating, no changes to any
existing execution path. It must NOT touch `PortfolioCoordinator.run()`'s existing
`NotImplementedError` gate, `_build_on_report()`'s weight-based coordination logic, or any existing
test. RESEARCH-ONLY banner required per A54 convention (`build_banner()`).

## Acceptance Criteria

- [ ] New diagnostic script produces, for a set of symbols run independently with
      `sizing_model="risk"`: portfolio-level total margin occupied over time, portfolio-level
      realized currency PnL, max margin utilization, per-symbol breakdown, per-cluster breakdown
      (using existing `corr_clusters` config).
- [ ] The report clearly states it is a measurement-only aggregation of independently-run
      per-symbol backtests — NOT a true joint/coordinated portfolio replay (that's Phase 2, out of
      scope here). Do not word it in a way that implies this is already a unified account.
- [ ] `PortfolioCoordinator.run()`'s existing `NotImplementedError` for
      `sizing_model="risk"` + `portfolio_risk="on"` is completely untouched — still raises exactly
      as before.
- [ ] No changes to `_run_per_symbol()`, `_build_on_report()`, `_build_off_report()`, or any
      existing test's assertions.
- [ ] New unit tests using constructed fixtures (no real historical DB dependency) verify the
      aggregation math (margin sum, PnL sum, cluster grouping) is correct.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/portfolio-risk-fusion-design.md` — read the full design doc,
   including the background on why `sizing_model="risk"` and `portfolio_risk="on"` are currently
   mutually exclusive, and the user's explicit phasing decision, before writing code. This HANDOFF
   summarizes it but the design doc has the full reasoning.
2. **Re-verify the technical claim yourself**: confirm `_run_per_symbol()`
   (`portfolio_engine.py:338`) really doesn't touch the `NotImplementedError` gate before relying on
   that assumption — read `PortfolioCoordinator.run()`'s current code directly.
3. **Scope:** new `diagnostics/portfolio_ledger_report.py` (or similar name), plus a new test file
   under `tests/unit/`. Do NOT modify `chan_strategy/portfolio_engine.py`,
   `chan_strategy/backtest_engine.py`, or any signal-calculation logic. Do NOT touch any SimNow
   order/cancel/send path.
4. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A83-scoped files are staged.**
5. **Guardrails (reject-on-violation):** no gating/threshold logic (measurement only); no changes
   to `PortfolioCoordinator`'s existing gate or coordination logic; no pre-2026-04-24 data for any
   new parameter choice; no SimNow order/cancel/send paths touched; no `GOAL PASSED`; do not imply
   this report is a true joint portfolio replay — it is an aggregation of independent per-symbol
   runs, and the report text must say so honestly.
6. **Include a literal `## Manual Verification` heading** with natively-run counts — this has been
   a recurring omission across several recent tasks (A77, A81, A82 all needed it added mid-review);
   include it proactively this time. Run `ruff check` proactively before finishing.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A83 read-only portfolio ledger report implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. This is Phase 1 of a
   multi-phase effort — Phase 2 (joint replay + real gating) and Phase 3 (circuit-breaker action
   decision) are explicitly out of scope and will be separate future tasks after this one is
   validated.

## Review Findings (codex, 2026-07-16)

Rejecting A83 for two aggregation correctness issues in
`examples/czsc_strategy/diagnostics/portfolio_ledger_report.py`:

1. `_build_ledger()` claims margins are forward-filled only within each symbol's own timestamp
   range, but `df = df.ffill().fillna(0.0)` carries a symbol's last margin past its final bar when
   another symbol has later timestamps. That can overstate portfolio total margin, max/final margin,
   utilization, and cluster margin for mismatched symbol data ranges. Add a constructed fixture where
   one symbol ends earlier than another and assert it contributes 0 after its final timestamp, then
   mask each per-symbol series outside its own `[first_dt, last_dt]` range after forward fill.
2. Per-cluster aggregation is not actually case-insensitive. `_symbol_clusters()` builds a
   case-insensitive membership map, but `_build_ledger()` later uses
   `member_symbols = [s for s in valid_symbols if s in members]`, so a lower-case requested symbol
   such as `rb888` is excluded from `industrial_energy` while also not appearing in
   `_uncategorized`. Reuse the case-insensitive cluster map, or normalize both sides, for the actual
   `per_cluster` membership and add a test that exercises `_build_ledger()` with case-mismatched
   symbols, not only `_symbol_clusters()`.

Verification notes from review:
- Targeted new tests passed: `python -m pytest examples/czsc_strategy/tests/unit/test_portfolio_ledger_report.py -q` -> 10 passed.
- `ruff check examples/czsc_strategy/diagnostics/portfolio_ledger_report.py examples/czsc_strategy/tests/unit/test_portfolio_ledger_report.py` passed.
- `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` passed.
- Full unit suite and `run_next_work.ps1 -Preflight` hit the documented Windows sandbox
  `tmp_path`/`PermissionError [WinError 5]` signature; per `.synccheck.yml`, use the recorded
  manual verification block for those two items until the sandbox symlink issue is resolved.

## Decision Log

- 2026-07-16 - User reviewed the portfolio-risk-fusion design doc and decided Q2 (lots vs. weights)
  in favor of lots/real-margin as the account source of truth, with `risk_parity`/`cluster_gross_cap`
  demoted to pre-trade budget constraints. User specified the three-phase rollout (read-only ledger
  → gating → circuit-breaker decision) and confirmed SimNow stays a separate read-only fact source.
- 2026-07-16 - A83 promoted as Phase 1 of this rollout. claude-code confirmed the technical
  implementation shape: a new standalone diagnostic script reusing per-symbol
  `BacktestEngine.run()` execution, entirely avoiding `PortfolioCoordinator.run()`'s existing
  `NotImplementedError` gate (which fires before `_run_per_symbol()` is even called).
- 2026-07-16 (kimi-code dev) - Implemented `diagnostics/portfolio_ledger_report.py`, calling
  `PortfolioEngine._run_per_symbol()` directly (the correct class name — both `_run_per_symbol()`
  and the `NotImplementedError`-raising `run()` are methods of `PortfolioEngine`, not the separate
  `PortfolioCoordinator` helper class referenced imprecisely in this HANDOFF's earlier text;
  claude-code verified this is still the correct bypass). Reuses `STRATEGY_CONFIG["corr_clusters"]`
  for cluster grouping (case-insensitive symbol matching), forward-fills each symbol's margin
  series within its own timestamp range before summing, and explicitly labels the report as an
  aggregation of independent per-symbol runs, not a joint replay.
- 2026-07-16 (claude-code independent verification, before triggering codex review) - Read the
  full script and test file. Confirmed `_run_per_symbol_engines()` correctly bypasses
  `PortfolioEngine.run()`'s `NotImplementedError` gate (line 611, unchanged) by calling
  `_run_per_symbol()` directly; confirmed no changes to `portfolio_engine.py`, `backtest_engine.py`,
  or any existing test file (`git diff --stat` on all three came back empty). Confirmed the
  `_risk_sizing_config()` context manager restores `STRATEGY_CONFIG["sizing_model"]` via `finally`
  (matching the established A74/A76/A78/A79 save/restore pattern). Re-ran everything independently:
  full unit suite `727 passed, 4 deselected` (was 717 before this task — 10 new tests, all pass);
  `ruff check` clean; both `sync_check.py` gates passed; `run_next_work.ps1 -Preflight` passed.
  Scope was clean (only A83-scoped files staged).
- 2026-07-16 (kimi-code fix round) - Fixed both codex-reported bugs: (1) added
  `symbol_margin_range` tracking per symbol and applied `df.where(mask, 0.0)` after `ffill()` so a
  symbol's margin correctly zeroes out past its own final timestamp instead of persisting; (2) the
  per-cluster loop now filters via `cluster_map.get(s, [])` (the case-insensitive map already built
  by `_symbol_clusters()`) instead of the case-sensitive `s in members` check. Also filled in the
  markdown report's "Manual Verification" placeholder counts with actual computed values instead of
  leaving `__` blanks.
- 2026-07-16 (claude-code independent verification, before triggering codex re-review) - Read both
  fixes in full: the margin-range mask correctly zeroes contributions outside `[first_dt, last_dt]`
  per symbol; the cluster fix correctly reuses the case-insensitive map. Confirmed the two new
  tests (`test_margin_not_carried_past_symbol_end`, `test_cluster_grouping_is_case_insensitive_in_build_ledger`)
  precisely target the reported bugs and would have failed against the pre-fix code. Re-ran
  everything independently, matching kimi-code's recorded counts: full unit suite `729 passed, 4
  deselected`; `ruff check` clean; both `sync_check.py` gates passed; `run_next_work.ps1 -Preflight`
  passed. Scope was clean (only A83-scoped files staged).

## Manual Verification

```text
pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
# 729 passed, 4 deselected (after fixing the two codex-reported bugs: forward-fill leak past
# symbol end, and cluster case-insensitivity)

ruff check examples/czsc_strategy/diagnostics/portfolio_ledger_report.py \
           examples/czsc_strategy/tests/unit/test_portfolio_ledger_report.py
# All checks passed

python tools/sync_check.py
# PASS

python tools/sync_check.py --root examples/czsc_strategy
# PASS

powershell -ExecutionPolicy Bypass -File examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight
# Preflight complete

git diff --stat -- examples/czsc_strategy/chan_strategy/portfolio_engine.py examples/czsc_strategy/chan_strategy/backtest_engine.py
# (empty — confirms the existing NotImplementedError gate and coordination logic are untouched)
```

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-16 | claude-code → kimi-code | design → dev | A83 (Phase 1: read-only portfolio ledger report) promoted from portfolio-risk-fusion design doc; handoff design->dev |
| 2026-07-16 | kimi-code → codex | dev → review | A83 read-only portfolio ledger report implemented |
| 2026-07-16 | codex → kimi-code | review → dev | 打回: A83 portfolio ledger aggregation overcounts after symbol end and case-mismatches clusters |
| 2026-07-16 | kimi-code → codex | dev → review | A83 read-only portfolio ledger report aggregation fixes (end-of-range mask + case-insensitive clusters) |
| 2026-07-16 | codex → codex | review → done | A83 review accepted |
