---
task: A70 - Backtest Report research/off Mode Labeling
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a70-second-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

First of three tasks (A70-A72) from the second third-party audit remediation roadmap
(`docs/design/a70-second-audit-remediation-roadmap.md`), promoted after A69 (final task of the
first A65-A69 roadmap) reached `done`. The 2026-07-15 audit (`ai-stock-trading-reviewer` v2.0.0 <!-- synccheck:ignore -->,
snapshot `9af87290`) scored 66/100 (up from 57/100) and gave 6 priority recommendations;
claude-code and the user scoped 3 of the 6 down to actionable dev tasks (A70/A71/A72) — the other
3 are either non-code (waiting for more data / an already-standing discipline rule) or out of
this workspace's scope (root-repo `polars` dependency gap). See the design doc's own scoping table
for the full reasoning.

**Standing instruction for this whole second roadmap (user-authorized)**: keep iterating — after
A70/A71/A72 reach `done`, trigger codex to run the `ai-stock-trading-reviewer` skill for a fresh
audit, scope any new findings the same way, and repeat — until the audit score exceeds 75 with no
medium-or-higher-severity open issues. Human-decision points should be resolved per claude-code's
own recommended judgment call (already pre-authorized), not re-asked each time.

**Full contract**: `docs/design/a70-second-audit-remediation-roadmap.md` §"A70" (this HANDOFF
summarizes it — read the full Rationale/Semantics there before writing code).

## Goal

`chan_strategy/config.py`'s defaults (`sizing_model="research"`, `limit_halt_model="off"`,
`portfolio_risk="off"`) mean a default backtest run produces a research-baseline curve with no
limit/halt fill constraints — but `BacktestEngine.generate_report()`/`print_report()`
(`chan_strategy/backtest_engine.py:631`/`:755`) has no unmissable label saying so. Add a
`mode_label` field to the report dict (`"RESEARCH_BASELINE"` when all three config knobs are at
their legacy default, otherwise a string naming which dimensions deviate from baseline), print it
prominently at the top of `print_report()`'s output with an explicit disclaimer when it's
`RESEARCH_BASELINE`, and add the currently-missing `limit_halt_model` field to the report dict (it
already has `sizing_model`/`portfolio_risk` but not `limit_halt_model`, so `mode_label` can't be
computed accurately without it).

## Acceptance Criteria

- [ ] `generate_report()` returns dict includes new `mode_label` and `limit_halt_model` fields.
- [ ] `mode_label == "RESEARCH_BASELINE"` under the pure-default config (`sizing_model="research"`,
      `limit_halt_model="off"`, `portfolio_risk="off"`); under any deviation, `mode_label` names the
      specific deviating dimension(s) (exact string format is dev's call, but must be decidable and
      must name the dimension).
- [ ] `print_report()` prints `mode_label` at the very top of its output; prints an additional
      unmissable disclaimer line when it's `RESEARCH_BASELINE`.
- [ ] New unit tests cover both "all-default → RESEARCH_BASELINE" and "any dimension deviates →
      non-RESEARCH_BASELINE naming that dimension", asserting directly on `generate_report()`'s
      dict and `print_report()`'s stdout (via `capsys`).
- [ ] No existing backtest numeric output changes (`total_return_pct`, `sharpe_ratio`, etc.) — only
      new fields/print lines are added; all existing tests' numeric assertions stay byte-identical.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped (this changes `generate_report()`/`print_report()`'s user-visible
      output).

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a70-second-audit-remediation-roadmap.md` §"A70". First of the
   three A70-A72 tasks from the second audit roadmap.
2. **Scope: `chan_strategy/backtest_engine.py`'s `generate_report()`/`print_report()` only** (plus
   a new/extended test file under `tests/unit/`). Do NOT touch `diagnostics/backtest_matrix_report.py`
   or other markdown report scripts — they already have an equivalent mechanism from A68
   (`_sizing_caveat` + `build_banner()`). Do NOT touch any SimNow order/cancel/send path.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream (see A69's Decision Log for the full
   story of how this was discovered and handled). **Before committing, run `git status --short` and
   confirm only your own A70-scoped files are staged** — if any of the above files appear staged,
   unstage them. This exact mistake (an unrelated bundle sneaking into the commit) happened in
   A69's first dev round and had to be split out by claude-code before review.
4. **Guardrails (reject-on-violation):** no threshold tuning; no pre-2026-04-24 data for any new
   parameter choice; no SimNow order/cancel/send paths touched; no `GOAL PASSED`; no numeric output
   changes to existing backtest results.
5. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing.**
6. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A70 mode_label/research-baseline labeling implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-15 - Second third-party audit (66/100, up from 57/100) scoped down to A70/A71/A72 by
  claude-code after discussing with the user; the other 3 of 6 recommendations are non-code
  (waiting for more data / already-standing discipline) or out of this workspace's scope (root
  `polars` dependency). User pre-authorized claude-code to resolve any human-decision points in
  this second roadmap per its own recommended judgment, without re-asking each time.
- 2026-07-15 - A70 promoted from `docs/design/a70-second-audit-remediation-roadmap.md`'s draft to
  an active HANDOFF task. First of three tasks in this roadmap.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | claude-code → kimi-code | design → dev | A70 (backtest report research/off mode labeling) promoted from second third-party audit remediation roadmap; handoff design->dev |
| 2026-07-15 | kimi-code → codex | dev → review | A70 mode_label/research-baseline labeling implemented |
