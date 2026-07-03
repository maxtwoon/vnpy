---
task: A34 Audit Remediation Roadmap
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-04
deliverables:
  - HANDOFF.md
  - docs/design/a34-audit-remediation-roadmap.md
blockers: []
---

## Background

A31-A33 turned the major audit findings in `examples/czsc_strategy/AUDIT_REPORT_2026-07-03.md` into repeatable evidence.

- H1 is `detected`: high-precision weight evidence exists, including the SC `0.847` family.
- H2 is `detected`: stop-loss overshoot exists, with worst loss near `-12.60%` versus a nominal `-3.0%` stop.
- H3 is `detected`: real signal-history replay found `背驰V260615_失效` count `0`.
- H4 is `found_spliced`: SQLite metadata shows 888 tables switch `real_symbol`.
- M1 is `detected`: `BACKTEST_CONFIG` and `BacktestEngine` defaults disagree on costs.

A34 must produce a remediation roadmap so the next dev agent fixes the issues in a controlled order without continuing to optimize historical OOS results.

## Goal

Produce a design document that specifies phased remediation for:

1. M1 cost single source of truth.
2. H1 parameter freeze and declassification of old promotion evidence.
3. H2 stop-loss overshoot stress diagnostics.
4. H3 dead-branch repair/delete/deprecation decision.
5. H4 rollover/raw-splice pollution diagnostics.

## Acceptance Criteria

- `docs/design/a34-audit-remediation-roadmap.md` exists and covers H1/H2/H3/H4/M1.
- The design explicitly says A34 does not implement strategy fixes, tune parameters, or optimize returns.
- The design recommends Phase 1 = M1 cost single source and Phase 2 = H1 freeze/declassification before H2/H3/H4 remediation.
- The design includes concrete acceptance criteria for each phase.
- The design forbids changing SimNow order/cancel/trading interfaces and forbids new old-OOS optimization.
- `python tools/handoff.py next` succeeds and advances the stage to `dev`.

## Notes for the Next Agent

Read this file and `docs/design/a34-audit-remediation-roadmap.md` before writing code.

Review findings from Codex on 2026-07-04:

1. Phase 1 / M1 passed verification: `audit_issue_diagnostics_2026-07-03.json` now reports M1 `status=ok`, `consistent=True`, `conflicts=[]`; `BacktestEngine` and `Position` defaults resolve to `BACKTEST_CONFIG`; targeted tests and preflight pass.
2. Phase 2 is incomplete: new audit diagnostics mark H1 as `research_only=True` and `is_promotion_evidence=False`, but existing historical final-candidate reports are still not declassified. In particular:
   - `examples/czsc_strategy/diagnostics/portfolio_goal_expanded_short_sc_0847.md` still contains `**GOAL PASSED: `True`**`.
   - `examples/czsc_strategy/diagnostics/sc_short_weight_neighborhood_final_candidate.md` still presents the `0.847` row as `pass=True` without a research-only / not-promotion-evidence warning.
   - `examples/czsc_strategy/diagnostics/platform_optimization_round2.md` and `platform_optimization_round8.md` still show `0.847` pass rows without the Phase 2 declassification metadata.
3. Do not tune parameters or regenerate a new passing candidate. The required fix is to mark these historical artifacts as research-only / not promotion evidence, preserve them as negative/contaminated evidence, and ensure future generators emit the same metadata.

Implementation guardrails:

- Start with Phase 1 and Phase 2 only. Do not implement Phase 3-5 until Phase 1-2 pass review.
- Do **not** modify SimNow order or cancel interfaces.
- Do **not** tune `0.847` or any neighboring parameter to recover a pass.
- Do **not** use the old OOS window for new parameter selection.
- Do **not** claim `GOAL PASSED`.
- Keep prior negative diagnostics as evidence.

## Decision Log

- 2026-07-03 - Initialized the sync-guardian workflow in the repository root.
- 2026-07-03 - A33 design stage: chose a real-bar replay for H3 and DB metadata heuristics for H4.
- 2026-07-04 - A34 design stage: chose a phased remediation roadmap, with M1/H1 first and H2/H3/H4 deferred behind explicit diagnostics.

## Handoff History

| Date | From -> To | Stage Change | Summary |
|------|------------|--------------|---------|
| 2026-07-03 | none -> claude-code | none -> design | Workflow initialized |
| 2026-07-03 | claude-code -> kimi-code | design -> dev | A33 design: H3 signal-history replay + H4 DB metadata inspection specified |
| 2026-07-03 | kimi-code -> codex | dev -> review | A33 evidence closure implemented |
| 2026-07-03 | codex -> codex | review -> done | A33 review passed: H3 signal-history replay and H4 DB metadata evidence verified |
| 2026-07-04 | codex -> claude-code | done -> design | A34 remediation roadmap started |
| 2026-07-04 | claude-code -> kimi-code | design -> dev | A34 design complete: audit remediation roadmap |
| 2026-07-04 | kimi-code -> codex | dev -> review | A34 Phase 1-2 implemented: M1 cost truth + H1 freeze/declassification metadata, tests pass |
| 2026-07-04 | codex -> kimi-code | review -> dev | Rejected: A34 Phase 2 incomplete: historical final-candidate reports still show GOAL PASSED/0.847 pass without research-only declassification |
| 2026-07-04 | kimi-code -> codex | dev -> review | A34 Phase 2 remediation: historical final-candidate reports declassified, reproducible declassify script + tests added |

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-04 | claude-code → kimi-code | design → dev | A34 design complete: audit remediation roadmap |
| 2026-07-04 | kimi-code → codex | dev → review | A34 Phase 1-2 implemented: M1 cost truth + H1 freeze/declassification metadata, tests pass |
| 2026-07-04 | codex → kimi-code | review → dev | 打回: A34 Phase 2 incomplete: historical final-candidate reports still show GOAL PASSED/0.847 pass without research-only declassification |
| 2026-07-04 | kimi-code → codex | dev → review | A34 Phase 2 remediation: historical final-candidate reports declassified, reproducible declassify script + tests added |
