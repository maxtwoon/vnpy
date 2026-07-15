---
task: A76 - Formal-Evaluation Rollover-Window Open-Gating
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a76-fourth-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

First of three tasks (A76-A78) from the FOURTH third-party audit remediation roadmap
(`docs/design/a76-fourth-audit-remediation-roadmap.md`), promoted after A75 (final task of the
A73-A75 roadmap) reached `done`. A fresh audit run by codex scored 70/100 (up from 67), with **no
fatal items**, but this round surfaced the pipeline's first 🔴 HIGH-severity finding: `888`
continuous-contract raw splices (documented in `RISK_NOTE_888_SPLICE.md`) still enter the
production signal/backtest path unadjusted, and can produce fake breakouts/stops/divergence
signals at rollover transitions. claude-code scoped 3 of the 6 findings (1 high + 5 medium) into
A76/A77/A78; the remaining medium/low findings are either architecture-scale (portfolio_risk/risk-
sizing fusion, same reasoning as the third roadmap) or non-code (require manual verification
against primary exchange notices). See the design doc's own scoping table for full reasoning.

**This task addresses the high-severity finding and is first in priority.**

**Standing instruction (carries forward from the second and third roadmaps, user pre-authorized)**:
keep iterating — after A76/A77/A78 reach `done`, trigger a fresh audit again, scope any new
findings the same way, and repeat — until the audit score exceeds 75 with no medium-or-higher open
issues. Human-decision points resolved per claude-code's own recommended judgment.

**Full contract**: `docs/design/a76-fourth-audit-remediation-roadmap.md` §"A76" (this HANDOFF
summarizes it — read the full Rationale/Semantics there before writing code).

## Goal

Add a gate, active ONLY in formal-evaluation mode (via A74's `formal_evaluation_config()`), that
blocks NEW position opens on trading dates inside a rollover-transition exclusion window. Do NOT
apply any price adjustment/splice-smoothing to the underlying continuous-contract data — the
audit's second, smaller option (gate opens, don't adjust prices) is what's being adopted here,
matching the design doc's reasoning.

**Reuse existing infrastructure** (already used by A52's `rollover_stat_tagging`, confirmed by
claude-code):
- `BacktestEngine._rollover_excluded_dates()` (`backtest_engine.py:645`) already returns the set of
  dates inside any rollover exclusion window for the current symbol, with best-effort graceful
  degradation to an empty set when transition metadata is unavailable (does not fail the backtest).
- The underlying detection lives in `chan_strategy/rollover_config.py`
  (`_detect_transitions`/`_exclusion_dates`/`_pair_in_exclusion_window`) — do not reinvent rollover
  detection.

The gate should ONLY block new opens (long or short) on excluded dates — it must NOT alter the
risk-control behavior (stop-loss, timeout, exit) of positions already open before or during the
window; this is a deliberate scope limit to keep the change small and verifiable (see design doc's
Rationale for why the more aggressive "force-close positions in-window" option was not chosen).

## Acceptance Criteria

- [ ] In formal-evaluation mode, no new long/short position opens on a trading date inside the
      rollover exclusion window (as returned by `_rollover_excluded_dates()`); behavior outside the
      window, or when not in formal-evaluation mode, is completely unchanged.
- [ ] Already-open positions inside the window are unaffected — their existing stop-loss/timeout/
      exit logic continues to operate normally (this task does not force-close anything).
- [ ] New regression test: construct a dataset where a signal would trigger an open on a bar inside
      the rollover window, and verify the open is rejected in formal-evaluation mode but occurs
      normally in the default (non-formal-evaluation) path.
- [ ] Graceful-degradation behavior matches A52 when rollover metadata is missing/detection fails
      (does not crash the backtest; degrades to no gating) — but this degraded state must be
      identifiable in the run's output/logs, not silently indistinguishable from "gating worked and
      found nothing to exclude."
- [ ] No changes to any existing test's numeric assertions on the non-formal-evaluation path.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped.

## Notes for the Next Agent

(review = claude-cowork; verify against the acceptance criteria and design doc §"A76")

1. **What changed:** A76 adds a formal-evaluation-only rollover-window open gate. A new
   `STRATEGY_CONFIG["rollover_open_gating"] = "off" | "on"` switch (default `"off"`) is enabled to
   `"on"` by `formal_evaluation_config()`. `BacktestEngine.run()` pre-computes
   `_rollover_excluded_dates()` when the switch is on, passes a per-bar
   `rollover_open_blocked` flag to `ChanTimingStrategy.update()` / `Position.update()`, and the
   open branches skip the fill when the flag is true. Already-open positions continue to exit,
   stop-loss, timeout and risk-control normally. No price adjustment is applied to the continuous
   contract data.
2. **Key files to review:**
   - `examples/czsc_strategy/chan_strategy/config.py` — new `rollover_open_gating` default.
   - `examples/czsc_strategy/chan_strategy/backtest_engine.py` — `formal_evaluation_config()`
     override, per-bar blocked flag, report audit fields (`rollover_open_gating_rejected_opens`,
     `rollover_open_gating_unavailable`), mode-label update.
   - `examples/czsc_strategy/chan_strategy/positions.py` — open-branch skip + rejection counter.
   - `examples/czsc_strategy/tests/unit/test_rollover_open_gating.py` — new regression tests.
   - `examples/czsc_strategy/tests/unit/test_formal_evaluation.py` — updated to assert the new
     override and mode label.
   - Minor test-fake signature updates in `test_branch_completion.py`,
     `test_portfolio_accounting.py`, `test_positions.py` to accept the new `rollover_open_blocked`
     kwarg.
3. **Review focus:** confirm the gate only blocks **new** opens and never forces closes; confirm
   behavior is byte-identical when `rollover_open_gating="off"`; confirm degraded/unavailable
   rollover detection is visible in the report; confirm no SimNow order/cancel/send paths were
   touched.
4. **Unrelated modified files in the working tree** (`diagnostics/ACCEPTANCE.md`,
   `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`, `run_next_work.ps1`,
   `simnow_20d_promotion_decision.md`, `tests/unit/test_run_next_work_wrapper.py`,
   `tests/unit/test_simnow_docs.py`) belong to a concurrent SimNow-observation workstream and were
   not staged by A76.

## Manual Verification

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` → 700 passed, 4 deselected.
- `python tools/sync_check.py` → PASS.
- `python tools/sync_check.py --root examples/czsc_strategy` → PASS.
- `examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight` → preflight complete.
- `ruff check` on A76-scoped source/test files → clean. (`chan_strategy/positions.py` carries
  pre-existing `typing.List/Dict/Tuple` style warnings unrelated to this change.)

## Decision Log

- 2026-07-15 - Fourth third-party audit (70/100, up from 67, no fatal items but its first 🔴 high
  finding) scoped down to A76/A77/A78 by claude-code; portfolio_risk/risk-sizing fusion remains
  out of scope (architecture-scale, same reasoning as the third roadmap); two low-severity findings
  are non-code (manual exchange-notice verification) or already mitigated (A75's import guard).
- 2026-07-15 - A76 promoted from `docs/design/a76-fourth-audit-remediation-roadmap.md`'s draft to
  an active HANDOFF task. First and highest-priority of three tasks in this roadmap.
- 2026-07-15 - Implemented A76 with a dedicated `STRATEGY_CONFIG["rollover_open_gating"] = "off" | "on"`
  switch (default `"off"`) that `formal_evaluation_config()` temporarily enables to `"on"`. This
  matches the project's "every feature gets its own explicit switch" convention (A51/A52/A67) and
  leaves room for testing the gate in isolation. The gate reuses A52's `_rollover_excluded_dates()`
  infrastructure, blocks only NEW long/short opens on excluded trading dates, and does not affect
  exits, stop-loss, timeout or risk-control for already-open positions. No price adjustment is
  applied to the underlying continuous-contract data.
- 2026-07-15 (claude-code independent verification, before triggering codex review) - Read every
  diff in full given the higher risk of this change (touches core position-open logic in
  `positions.py`): confirmed the gate only intercepts the `Operate.LO`/`Operate.SO` open branches
  (never `LC`/`SC` exits), `Position.update()`'s `rollover_open_blocked` parameter defaults to
  `False` so the legacy call signature and behavior are preserved when unpassed, and
  `ChanTimingStrategy.update()` always forwards a deterministic `False` when gating is off (never
  omits it), which keeps off-mode byte-identical while still allowing the flag to be threaded
  through unconditionally. Confirmed the new test file covers the critical edge case (an
  already-open position continues to exit normally inside the window) and graceful degradation
  when rollover metadata is missing. Confirmed `test_rollover_off_equivalence.py` (A52's existing
  equivalence snapshot) was untouched and still passes. Diffed ruff output before/after this
  change: all 30 flagged issues (`typing.List`/`Dict`/`Tuple` style, one unused `pytest` import in
  `test_positions.py`) are pre-existing and unrelated to this diff, confirmed via `git stash`
  comparison. Re-ran everything independently, matching kimi-code's recorded counts exactly: full
  unit suite `700 passed, 4 deselected`; both `sync_check.py` gates passed; `run_next_work.ps1
  -Preflight` passed. Scope was clean (only A76-scoped files staged).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | claude-code → kimi-code | design → dev | A76 (formal-evaluation rollover-window open-gating) promoted from fourth third-party audit remediation roadmap; handoff design->dev |
| 2026-07-15 | kimi-code → codex | dev → review | A76 formal-evaluation rollover-window open-gating implemented |
