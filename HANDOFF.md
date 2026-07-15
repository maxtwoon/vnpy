---
task: A79 - Formal-Evaluation trading_calendar Daily Aggregation Default
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-16
deliverables:
  - HANDOFF.md
  - docs/design/a79-fifth-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

First of three tasks (A79-A81) from the FIFTH third-party audit remediation roadmap
(`docs/design/a79-fifth-audit-remediation-roadmap.md`), promoted after A78 (final task of the
A76-A78 roadmap) reached `done`. A fresh audit scored 70/100 — unchanged from the fourth round —
with **no fatal items** and 6 medium-severity findings. claude-code scoped this roadmap carefully
given the score plateau: one finding (continuous-contract splice impact quantification) is already
satisfied by A73's `rollover_contribution_report.py` and needs no new work; one remains
architecture-scale (portfolio_risk/risk-sizing fusion, unchanged reasoning from the third and
fourth roadmaps); three are scoped into A79/A80/A81. See the design doc's scoping table and its
explicit note about diminishing returns on repeatedly-recurring "research baseline vs formal
evaluation" framings.

**Note for whoever reads this after A81 reaches `done`**: if the sixth audit still doesn't clear
75/no-medium+, this may be the point to report status honestly to the user rather than open a
sixth roadmap automatically — several remaining findings are variations on a theme this project has
deliberately addressed via opt-in mechanisms (house style: gated defaults, not changed defaults),
and genuinely new architecture-scale work (portfolio fusion) needs its own dedicated design effort
the user should explicitly sponsor, not another auto-scoped bounded task.

**Full contract**: `docs/design/a79-fifth-audit-remediation-roadmap.md` §"A79" (this HANDOFF
summarizes it).

## Goal

`chan_strategy/config.py`'s `daily_agg` defaults to `"natural"` (calendar-date daily aggregation);
`"trading_calendar"` (maps night-session bars past midnight to the next trading day — more
accurate for futures) is already fully implemented in
`data_adapter.py::_resample_daily_trading_calendar()` but not the default. This is the exact same
pattern as A74 (`sizing_model`)/A76 (`rollover_open_gating`)/A78 (`stop_execution_model`): existing,
already-implemented stricter behavior that formal evaluation should default to.

Extend `formal_evaluation_config()` (already extended three times by A74/A76/A78) with a fourth
override: `daily_agg = "trading_calendar"`, following the exact same save/restore pattern.

## Acceptance Criteria

- [ ] `formal_evaluation_config()` additionally overrides `STRATEGY_CONFIG["daily_agg"]` to
      `"trading_calendar"` and restores the original value afterward, including on exception —
      proven by a dedicated test following A74/A76/A78's established pattern.
- [ ] A test proves `run_formal_evaluation()`'s effective `daily_agg` is `"trading_calendar"`
      during the run.
- [ ] No changes to the non-formal-evaluation default path's behavior — all existing tests pass
      unmodified.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a79-fifth-audit-remediation-roadmap.md` §"A79". First of three
   A79-A81 tasks.
2. **Scope:** `chan_strategy/backtest_engine.py`'s `formal_evaluation_config()` only, plus test
   additions in `tests/unit/test_formal_evaluation.py` (the existing test file, following its
   established pattern for each prior override addition). Do NOT touch
   `_resample_daily_trading_calendar()` itself or any signal-calculation logic.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A79-scoped files are staged.**
4. **Guardrails:** no threshold tuning; no pre-2026-04-24 data for any new parameter choice; no
   SimNow order/cancel/send paths touched; no `GOAL PASSED`; the override must be provably restored
   on both success and exception paths.
5. **Include a literal `## Manual Verification` heading** with natively-run counts (A77's first
   review round was rejected purely for lacking this literal heading — do not repeat that mistake).
   Run `ruff check` proactively before finishing.
6. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A79 formal-evaluation trading_calendar daily_agg default implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Manual Verification

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` → 703 passed, 4 deselected.
- `python tools/sync_check.py` → PASS (vnpy 4.4.0).
- `python tools/sync_check.py --root examples/czsc_strategy` → PASS (project VERSION matches CHANGELOG).
- `examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight` → preflight complete (191 SimNow workflow unit tests passed).
- `ruff check examples/czsc_strategy/chan_strategy/backtest_engine.py examples/czsc_strategy/tests/unit/test_formal_evaluation.py` → All checks passed.
- Full `ruff check .` still reports pre-existing lint issues in unrelated files (e.g. `docs/chanlunnew/`, `examples/czsc_strategy/_debug_zs.py`, `examples/czsc_strategy/_patch_backtest*.py`, `examples/czsc_strategy/chan_strategy/__init__.py`, `data_adapter.py`, `positions.py`, `utils.py`, `validation.py`, notebooks); no new issues were introduced by the A79-scoped edits.
- `git status --short` confirms only A79-scoped files were modified (`VERSION`, `CHANGELOG.md`, `chan_strategy/backtest_engine.py`, `tests/unit/test_formal_evaluation.py`) in addition to the unrelated SimNow workstream files that were already modified before this task started.

## Decision Log

- 2026-07-16 - Fifth third-party audit (70/100, unchanged from fourth round, no fatal items) scoped
  down to A79/A80/A81 by claude-code, noting the score plateau and that some findings recur across
  rounds as re-framings of the same "research baseline by design" theme. One finding (splice-impact
  quantification) is already satisfied by A73's existing `rollover_contribution_report.py`; one
  remains architecture-scale (portfolio_risk/risk-sizing fusion). See design doc for full reasoning.
- 2026-07-16 - A79 promoted from `docs/design/a79-fifth-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task. First of three tasks in this roadmap.
- 2026-07-16 (claude-code independent verification, before triggering codex review) - Read the
  full diff: `formal_evaluation_config()`'s keys/overrides tuples both extended consistently with
  the established pattern; kimi-code also updated `run_formal_evaluation()`'s docstring to list
  all five overrides (incidentally addressing the fifth audit's low-severity "incomplete entry-
  point docstring" finding as a natural side effect of the edit, not separately requested). Re-ran
  everything independently, matching kimi-code's recorded counts exactly: full unit suite `703
  passed, 4 deselected`; `ruff check` clean; both `sync_check.py` gates passed; `run_next_work.ps1
  -Preflight` passed. Scope was clean (only A79-scoped files staged).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-16 | claude-code → kimi-code | design → dev | A79 (formal-evaluation trading_calendar daily_agg default) promoted from fifth third-party audit remediation roadmap; handoff design->dev |
| 2026-07-16 | kimi-code → codex | dev → review | A79 formal-evaluation trading_calendar daily_agg default implemented |
