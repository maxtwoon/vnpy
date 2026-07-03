---
task: A34 Audit Remediation Roadmap
version: 4.4.0
stage: dev
owner: kimi-code
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

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-04 | claude-code → kimi-code | design → dev | A34 design complete: audit remediation roadmap |
