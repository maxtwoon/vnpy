---
task: A77 - Documentation Drift Fixes (README limit_halt_model + Verdict-Layer Docstrings)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-16
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

Second of three tasks (A76-A78) from the fourth third-party audit remediation roadmap
(`docs/design/a76-fourth-audit-remediation-roadmap.md`), promoted after A76 reached `done` (codex
accepted on the first review round, resolving the roadmap's only 🔴 high finding).

Two purely documentation-level drifts, both confirmed by claude-code against current code before
writing this HANDOFF:

1. `examples/czsc_strategy/README.md:160` still lists
   `` `limit_halt_model`: `"off" | "aware"` `` — missing `"enforce"`, which A67 introduced and A70/
   A74/A76 all actively use. Confirmed via direct grep.
2. `diagnostics/cost_sensitivity_report.py`'s `run_cost_sensitivity()`,
   `diagnostics/risk_param_sensitivity_report.py`'s `evaluate_perturbation_gate()`, and
   `diagnostics/backtest_matrix_report.py`'s `evaluate_oos_gate()` all still say, verbatim, "does
   not invent an arbitrary pass/fail threshold" / "No arbitrary pass/fail threshold is invented" in
   their docstrings. **These docstrings are still literally true for the functions they describe**
   — those specific measurement functions genuinely don't invent thresholds. The actual drift is
   that A71 added companion `*_gate_verdict()` functions in the SAME files
   (`oos_gate_verdict()`, `perturbation_gate_verdict()`, `cost_sensitivity_gate_verdict()`) that DO
   apply protective thresholds (e.g. `OOS_DRAWDOWN_RATIO_WARN = 3.0`,
   `COST_RELATIVE_RETURN_WARN_PCT = -90.0`) — a reader skimming just the measurement function's
   docstring could wrongly conclude the whole module/file has no thresholds anywhere.

**Full contract**: `docs/design/a76-fourth-audit-remediation-roadmap.md` §"A77" (this HANDOFF
summarizes it).

## Goal

1. Update `README.md`'s `limit_halt_model` switch documentation to the accurate three-value set
   (`"off" | "aware" | "enforce"`), and briefly mention `run_formal_evaluation.py` (A74) as the
   formal-evaluation entry point in the same section or nearby usage notes.
2. Add a brief clarifying note to the three measurement functions' docstrings
   (`run_cost_sensitivity()`, `evaluate_perturbation_gate()`, `evaluate_oos_gate()`) pointing to
   their companion verdict function and stating that the verdict layer (not the measurement layer)
   applies protective thresholds — e.g. "Note: the companion `X_gate_verdict()` function below
   layers protective thresholds on top of this measurement." Do NOT remove or contradict the
   existing "this function itself invents no threshold" statement — it's accurate; just add the
   pointer so a reader doesn't over-generalize it to the whole file.

This is a documentation-only task. No function behavior, return values, or existing test
assertions should change.

## Acceptance Criteria

- [ ] `README.md`'s `limit_halt_model` switch list is `"off" | "aware" | "enforce"`, matching
      `config.py`'s actual supported values.
- [ ] `README.md` mentions `run_formal_evaluation.py` as the formal-evaluation entry point
      (wherever fits naturally — near the `limit_halt_model` section or a "usage" section).
- [ ] `run_cost_sensitivity()`, `evaluate_perturbation_gate()`, `evaluate_oos_gate()` docstrings
      each gain a one-to-two-sentence pointer to their companion verdict function, clarifying that
      thresholds live in the verdict layer, not the measurement layer described by that docstring.
- [ ] No changes to any function's code, return structure, or behavior — this is docstring/README
      text only.
- [ ] All existing tests pass unmodified (no test should need updating for a pure documentation
      change; if any test asserts on exact docstring text, that's a pre-existing fragility, not
      something this task should paper over — flag it in the Decision Log if found, don't silently
      change the test).
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped (per house convention, even for documentation-only changes).

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a76-fourth-audit-remediation-roadmap.md` §"A77". Second of three
   A76-A78 tasks. This is the smallest/lowest-risk task in the roadmap — pure documentation.
2. **Scope:** `README.md`, and the three named docstrings in `diagnostics/cost_sensitivity_report.py`,
   `diagnostics/risk_param_sensitivity_report.py`, `diagnostics/backtest_matrix_report.py`. Do not
   touch any code logic, any SimNow path, or any other file.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A77-scoped files are staged.**
4. **Guardrails:** no code behavior changes; no SimNow paths touched; no `GOAL PASSED`.
5. **Include a Manual-verification block with natively-run counts**, and run `ruff check`
   proactively before finishing (docstring-only changes should never trip ruff, but confirm).
6. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A77 documentation drift fixes implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-15 - A77 promoted from `docs/design/a76-fourth-audit-remediation-roadmap.md`'s draft to
  an active HANDOFF task, immediately after A76 reached `done`. Second of three tasks in the fourth
  audit-remediation roadmap.
- 2026-07-15 (claude-code pre-promotion research) - Confirmed both drifts directly against current
  code: README's `limit_halt_model` line still lists only two values; the three measurement-function
  docstrings are individually accurate but don't point to their companion verdict functions'
  thresholds, which is the actual source of the audit's confusion.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | claude-code → kimi-code | design → dev | A77 (documentation drift fixes) promoted from fourth third-party audit remediation roadmap; handoff design->dev |
