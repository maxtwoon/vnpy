---
task: A76 - Formal-Evaluation Rollover-Window Open-Gating
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a76-fourth-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
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

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a76-fourth-audit-remediation-roadmap.md` §"A76". First and highest-
   priority of the three A76-A78 tasks (addresses the audit's only 🔴 high finding).
2. **Read the design doc's full Semantics section** — it discusses whether to add a new dedicated
   `STRATEGY_CONFIG` key (e.g. `rollover_open_gating`) enabled by `formal_evaluation_config()`, vs.
   binding the behavior unconditionally into `formal_evaluation_config()` directly. The design doc
   recommends the dedicated-key approach for consistency with this project's "every feature gets
   its own explicit switch" convention (A51/A52/A67), but leaves the final call to you — record
   your choice and reasoning in the Decision Log.
3. **Suggested implementation shape**: reuse A67's `limit_halt_model="enforce"`
   "reject-this-bar's-fill" pattern (`Position._reject_fill_at_limit()`) as a model for how to
   reject an open without introducing a cross-bar state machine — `_get_operate()` re-evaluates
   Chan-theory structure every bar, so a rejected open on a rollover-window bar will naturally be
   re-attempted on a later bar once structure conditions are still met and the window has passed.
4. **Scope:** `chan_strategy/backtest_engine.py` (gate wiring), possibly `chan_strategy/positions.py`
   if the open-rejection needs a new helper analogous to A67's, plus a new/extended test file under
   `tests/unit/`. Do NOT apply any price adjustment to the continuous-contract data itself — that is
   explicitly out of scope (see design doc Rationale). Do NOT touch any SimNow order/cancel/send
   path.
5. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A76-scoped files are staged.**
6. **Guardrails (reject-on-violation):** no price adjustment to continuous-contract data; no
   force-closing of already-open positions inside the window; no threshold tuning; no pre-2026-
   04-24 data for any new parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; the gate must be provably scoped to formal-evaluation mode only — a leak into the
   default path is a reject-worthy bug, test for it explicitly.
7. **Include a Manual-verification block with natively-run counts**, and run `ruff check`
   proactively before finishing.
8. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A76 formal-evaluation rollover-window open-gating implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-15 - Fourth third-party audit (70/100, up from 67, no fatal items but its first 🔴 high
  finding) scoped down to A76/A77/A78 by claude-code; portfolio_risk/risk-sizing fusion remains
  out of scope (architecture-scale, same reasoning as the third roadmap); two low-severity findings
  are non-code (manual exchange-notice verification) or already mitigated (A75's import guard).
- 2026-07-15 - A76 promoted from `docs/design/a76-fourth-audit-remediation-roadmap.md`'s draft to
  an active HANDOFF task. First and highest-priority of three tasks in this roadmap.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | claude-code → kimi-code | design → dev | A76 (formal-evaluation rollover-window open-gating) promoted from fourth third-party audit remediation roadmap; handoff design->dev |
