---
task: A81 - Unified Acceptance Gate + Research-Baseline Entry Warning
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-16
deliverables:
  - HANDOFF.md
  - docs/design/a79-fifth-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

Third and FINAL task of the fifth third-party audit remediation roadmap
(`docs/design/a79-fifth-audit-remediation-roadmap.md`), promoted after A80 reached `done` (codex
accepted on the first review round). Completing this task finishes the entire A79-A81 roadmap.

Two related medium-severity findings, bundled into one task:

1. A71 added `oos_gate_verdict()` (`diagnostics/backtest_matrix_report.py:208`),
   `perturbation_gate_verdict()` (`diagnostics/risk_param_sensitivity_report.py:141`), and
   `cost_sensitivity_gate_verdict()` (`diagnostics/cost_sensitivity_report.py:136`) — all confirmed
   by claude-code, all returning an `overall_status: "pass"|"warn"|"fail"` field — but nothing
   combines these three plus A78's `assert_not_research_baseline()` into one top-level judgment.
   The audit calls this a "process risk": a report can be generated with a `"fail"` signal buried in
   it, and nothing forces that signal to actually block anything.
2. `run_chan_backtest.py` (the default, most-likely-to-be-run public entry point) only shows
   `mode_label` inside the generated report body — it doesn't warn the user BEFORE running that
   this is the research-baseline entry point, distinct from `run_formal_evaluation.py` (A74).

**Full contract**: `docs/design/a79-fifth-audit-remediation-roadmap.md` §"A81" (this HANDOFF
summarizes it).

## Goal

1. Add a unified acceptance-gate function (location and exact name is dev's call — e.g. in
   `chan_strategy/backtest_engine.py` alongside `assert_not_research_baseline()`, or a new
   `diagnostics/acceptance_gate.py` — record the choice and reasoning in the Decision Log) that
   takes the three verdict results' `overall_status` values plus a report's `mode_label`, and
   returns a single top-level `"pass"|"warn"|"fail"` judgment: any input `"fail"` → top-level
   `"fail"`; `mode_label == "RESEARCH_BASELINE"` → top-level `"fail"` (reuse
   `assert_not_research_baseline()`'s logic, don't duplicate it); otherwise `"warn"` if any input is
   `"warn"`, else `"pass"`.
2. Add an unmissable warning at the very start of `run_chan_backtest.py`'s `main()` function (before
   any backtest execution), stating this is the research-baseline entry point and that
   `run_formal_evaluation.py` should be used for formal evaluation.

**This task does NOT require wiring the new unified gate function into any existing SimNow
promotion-decision script or workflow** — that remains out of scope, consistent with A78's
established boundary (the guard function itself is the deliverable; wiring it into a specific
promotion pipeline is separate, larger work the user would need to explicitly request).

## Acceptance Criteria

- [ ] A new unified acceptance-gate function exists, combining the three verdict functions'
      `overall_status` values and `mode_label` into one top-level `"pass"|"warn"|"fail"` judgment,
      per the exact combination rule above.
- [ ] Tests cover: all three verdicts `"pass"` + non-`RESEARCH_BASELINE` mode_label → top-level
      `"pass"`; any verdict `"fail"` → top-level `"fail"`; `mode_label == "RESEARCH_BASELINE"` →
      top-level `"fail"` regardless of verdict statuses; any verdict `"warn"` with no `"fail"` →
      top-level `"warn"`.
- [ ] `run_chan_backtest.py`'s `main()` prints an unmissable warning at the very start (before any
      backtest execution) identifying this as the research-baseline entry and pointing to
      `run_formal_evaluation.py`.
- [ ] No changes to any existing backtest numeric output or existing test assertions.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a79-fifth-audit-remediation-roadmap.md` §"A81". Third and FINAL
   task of the A79-A81 roadmap — completing this closes out the entire fifth audit remediation
   wave.
2. **Reuse, don't duplicate**: the three verdict functions already exist and already compute
   `overall_status` — this task only adds a thin combining layer on top, plus reuses
   `assert_not_research_baseline()`'s logic for the `mode_label` check rather than re-implementing
   the `"RESEARCH_BASELINE"` string comparison separately.
3. **Scope:** likely `chan_strategy/backtest_engine.py` (new function near
   `assert_not_research_baseline()`) or a new `diagnostics/acceptance_gate.py` (dev's call), plus
   `run_chan_backtest.py`'s `main()` (new warning print at the top, before line 28's existing
   prints), plus test files under `tests/unit/`. Do NOT wire the new function into any SimNow
   promotion script. Do NOT touch any SimNow order/cancel/send path.
4. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A81-scoped files are staged.**
5. **Guardrails (reject-on-violation):** no threshold tuning (reuse existing verdict thresholds,
   don't invent new ones); no SimNow order/cancel/send paths touched; no `GOAL PASSED`; no wiring
   into any promotion/acceptance script beyond what's described above.
6. **Include a literal `## Manual Verification` heading** with natively-run counts (A77's first
   review round was rejected purely for lacking this literal heading — do not repeat that mistake).
   Run `ruff check` proactively before finishing.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A81 unified acceptance gate and research-baseline entry warning implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. **This is the last task in the
   entire A79-A81 roadmap** — after this reaches `done`, trigger a fresh third-party audit per the
   standing instruction. **Per A79's own note**: if the sixth audit still doesn't clear 75/no-
   medium+, report status honestly to the user rather than automatically opening a sixth roadmap —
   several remaining findings are deliberate opt-in-by-design tradeoffs, and the one genuinely
   large remaining item (portfolio_risk/risk-sizing fusion) needs the user's explicit sponsorship
   for a dedicated design effort, not another auto-scoped bounded task.

## Manual Verification

```text
pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
# 715 passed, 4 deselected

ruff check examples/czsc_strategy/chan_strategy/backtest_engine.py \
           examples/czsc_strategy/run_chan_backtest.py \
           examples/czsc_strategy/tests/unit/test_a81_acceptance_gate.py
# 5 pre-existing errors in run_chan_backtest.py (unrelated to this diff, confirmed via
# git stash comparison); backtest_engine.py and the new test file are clean

python tools/sync_check.py
# PASS

python tools/sync_check.py --root examples/czsc_strategy
# PASS

powershell -ExecutionPolicy Bypass -File examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight
# Preflight complete
```

## Decision Log

- 2026-07-16 - A81 promoted from `docs/design/a79-fifth-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task, immediately after A80 reached `done`. Third and final task of the fifth
  audit-remediation roadmap.
- 2026-07-16 (claude-code pre-promotion research) - Confirmed all three verdict functions'
  `overall_status` fields exist as designed (`backtest_matrix_report.py:270`,
  `risk_param_sensitivity_report.py:180`, `cost_sensitivity_report.py:214`); confirmed
  `run_chan_backtest.py`'s `main()` currently has no pre-execution warning (first print statements
  start at line 28 with the database path, no research-baseline notice).
- 2026-07-16 (claude-code independent verification, before triggering codex review) - Read the
  full diff: `unified_acceptance_gate()` correctly reuses `assert_not_research_baseline()` via
  try/except rather than duplicating the mode_label string comparison, and the fail/warn/pass
  precedence exactly matches the design's combination rule (RESEARCH_BASELINE first, then any fail,
  then any warn, else pass). The new test file covers every combination case including
  missing-`overall_status` defaults and empty `mode_label`. `run_chan_backtest.py`'s warning is
  unmissable and placed before any execution. Diffed `ruff check` before/after on
  `run_chan_backtest.py`: identical 5 pre-existing errors both times (unused import, f-strings
  without placeholders, unused variable) — all pre-existing, no regression;
  `backtest_engine.py`/the new test file are both clean. Re-ran everything independently, matching
  kimi-code's recorded counts: full unit suite `715 passed, 4 deselected`; both `sync_check.py`
  gates passed; `run_next_work.ps1 -Preflight` passed. Scope was clean (only A81-scoped files
  staged).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-16 | claude-code → kimi-code | design → dev | A81 (unified acceptance gate + research-baseline entry warning) promoted from fifth third-party audit remediation roadmap; handoff design->dev |
| 2026-07-16 | kimi-code → codex | dev → review | A81 unified acceptance gate and research-baseline entry warning implemented |
| 2026-07-16 | codex → codex | review → done | A81 review accepted |
