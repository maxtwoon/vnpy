---
task: A82 - Fail-Closed Allow-List Fix for assert_not_research_baseline
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-16
deliverables:
  - HANDOFF.md
  - docs/design/a82-sixth-audit-critical-fix.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

A sixth third-party audit (score 64/100, down from 70) surfaced the pipeline's first FATAL-tier
finding since the third round: `assert_not_research_baseline()` (A78) and `unified_acceptance_gate()`
(A81) are a **blocklist**, not a fail-closed allow-list. They only raise when
`report.get("mode_label") == "RESEARCH_BASELINE"` exactly — any missing key, `None`, empty string,
typo, or unrecognized value silently passes as "not research baseline." This is confirmed by
claude-code directly: `tests/unit/test_formal_evaluation.py:222-226`
(`test_assert_not_research_baseline_passes_on_other_labels`) and
`tests/unit/test_a81_acceptance_gate.py:116-124` (`test_empty_mode_label_does_not_fail`) both
explicitly assert that `{}` and `{"mode_label": ""}` currently PASS — these test assertions are
the audit's own evidence of the gap, not a testing mistake.

**This is a genuine design flaw claude-code introduced in A78/A81**, being fixed directly rather
than deferred as "yet another audit finding to scope into a future roadmap." A dedicated design
doc (`docs/design/a82-sixth-audit-critical-fix.md`) covers only this one fix — the sixth audit's
other findings (mostly further variations on "more things should default to formal_evaluation_config()")
are explicitly NOT being scoped into new tasks this round; claude-code will report status to the
user after this fix lands rather than auto-opening a seventh roadmap.

**Full contract**: `docs/design/a82-sixth-audit-critical-fix.md` (this HANDOFF summarizes it).

## Goal

Change `assert_not_research_baseline()` from "reject if it exactly matches the known-bad string"
to "reject unless it matches a known-safe format." Confirmed by claude-code:
`_compute_mode_label()` (`chan_strategy/backtest_engine.py`) only ever produces two string shapes:
`"RESEARCH_BASELINE"` (all defaults) or `"PARTIAL_PRODUCTION_FEATURES(...)"` (any deviation). The
fix: only the `"PARTIAL_PRODUCTION_FEATURES("`-prefixed shape should pass; everything else
(missing key, `None`, empty string, `"RESEARCH_BASELINE"`, any unrecognized string) must raise.

`unified_acceptance_gate()` (A81) reuses `assert_not_research_baseline()` via try/except, so fixing
the one function fixes both.

## Acceptance Criteria

- [ ] `assert_not_research_baseline()` raises `ValueError` for: `{}`, `{"mode_label": None}`,
      `{"mode_label": ""}`, `{"mode_label": "RESEARCH_BASELINE"}`, `{"mode_label": "SOME_TYPO"}`.
- [ ] `assert_not_research_baseline()` does NOT raise for
      `{"mode_label": "PARTIAL_PRODUCTION_FEATURES(...)"}` (any concrete instance actually producible
      by `_compute_mode_label()`).
- [ ] `unified_acceptance_gate()` returns top-level `"fail"` for all the same "unknown/missing"
      inputs above, via its existing reuse of `assert_not_research_baseline()`.
- [ ] `test_formal_evaluation.py`'s `test_assert_not_research_baseline_passes_on_other_labels` is
      corrected: the line asserting `{"mode_label": ""}` passes must be changed to assert it now
      raises (this is fixing the bug's own evidence, not weakening test coverage).
- [ ] `test_a81_acceptance_gate.py`'s `test_empty_mode_label_does_not_fail` is corrected the same
      way — rename/rewrite to assert empty `mode_label` now returns `"fail"`.
- [ ] No changes to `_compute_mode_label()` itself or any backtest numeric output.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a82-sixth-audit-critical-fix.md`. This is a single, focused,
   critical-severity fix — not part of a larger roadmap this time.
2. **Scope:** `chan_strategy/backtest_engine.py`'s `assert_not_research_baseline()` only, plus
   correcting the two existing test assertions named above that currently encode the bug as
   "expected behavior." Do NOT touch `_compute_mode_label()`'s actual string-generation logic, any
   SimNow order/cancel/send path, or any other diagnostic script (the sixth audit's other findings
   are explicitly out of scope for this task).
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A82-scoped files are staged.**
4. **Guardrails:** no threshold tuning beyond the exact fix described; no SimNow order/cancel/send
   paths touched; no `GOAL PASSED`; do not weaken test coverage — correcting a wrong assertion to
   match fixed behavior is required, silently deleting the test is not acceptable.
5. **Include a literal `## Manual Verification` heading** with natively-run counts (A77's and A81's
   dev rounds both needed this pointed out — do not omit it again). Run `ruff check` proactively
   before finishing.
6. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A82 fail-closed allow-list fix for assert_not_research_baseline implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-16 - Sixth third-party audit (64/100, down from 70, first fatal-tier finding since the
  third round) surfaced a genuine design flaw claude-code introduced in A78/A81:
  `assert_not_research_baseline()` is a blocklist, not a fail-closed allow-list. claude-code is
  fixing this directly as A82 rather than scoping it into a larger roadmap — the sixth audit's
  other findings (mostly repeated variations on "more diagnostics should default to formal
  evaluation") are explicitly not being scoped this round; status will be reported to the user
  after this fix lands.
- 2026-07-16 - A82 promoted from `docs/design/a82-sixth-audit-critical-fix.md`'s draft to an
  active HANDOFF task.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-16 | claude-code → kimi-code | design → dev | A82 (fail-closed allow-list fix for research-baseline guard) promoted from sixth audit critical fix; handoff design->dev |
