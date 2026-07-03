---
task: A33 Audit Diagnostics Evidence Closure
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-03
deliverables:
  - HANDOFF.md
  - docs/design/a33-audit-diagnostics-evidence-closure.md
blockers: []
---

## Background

A33 is the design stage for closing the H3/H4 evidence gaps in `examples/czsc_strategy/diagnostics/audit_issue_diagnostics.py`.

- H3 ("背驰失效" branch reachability) was `unavailable` because no real signal-history artifact existed.
- H4 (888 continuous-contract assumptions) was `unknown` because no DB path was wired into the diagnostic.

A32 already closed H1, H2, and M1 using real project inputs. A33 must produce a concrete plan so the next dev agent can wire real DB metadata and real signal replay into the audit diagnostic.

## Goal

Produce a design document that specifies:

1. How to generate real `signal_history` from a 1-minute SQLite replay without creating fake bi structures.
2. How to resolve the SQLite DB path and inspect 888 table metadata for rollover/adjustment evidence.
3. The exact file/interface changes, test design, and acceptance criteria.

## Acceptance Criteria

- `docs/design/a33-audit-diagnostics-evidence-closure.md` exists and covers H3, H4, file changes, tests, and acceptance criteria.
- The design relies only on existing strategy code paths (no new signal/position logic).
- H4 status values are unambiguous (`found_adjusted`, `found_spliced`, `found_single_contract`, `no_evidence`, `unavailable`, `unknown`).
- H3 artifact schema matches the existing `collect_signal_records_from_diagnostics` collector.
- `python tools/handoff.py next` succeeds and advances the stage to `dev`.

## Notes for the Next Agent

Read this file and `docs/design/a33-audit-diagnostics-evidence-closure.md` before writing code.

Implementation guardrails:

- Do **not** modify `chan_strategy/signals.py`, `chan_strategy/positions.py`, `chan_strategy/backtest_engine.py`, or any SimNow order interface.
- Keep changes minimal and focused on `audit_issue_diagnostics.py`, the new `generate_signal_history.py`, and tests.
- After implementation, run the generator, the audit diagnostic, and the unit tests before advancing the handoff.

## Decision Log

- 2026-07-03 - Initialized the sync-guardian workflow in the repository root.
- 2026-07-03 - A33 design stage: chose a real-bar replay for H3 (bypassing `BacktestEngine` to avoid 100-bar sampling) and DB metadata heuristics for H4.

## Handoff History

| Date | From -> To | Stage Change | Summary |
|------|------------|--------------|---------|
| 2026-07-03 | none -> claude-code | none -> design | Workflow initialized |

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-03 | claude-code → kimi-code | design → dev | A33 design: H3 signal-history replay + H4 DB metadata inspection specified |
| 2026-07-03 | kimi-code → codex | dev → review | A33 evidence closure implemented |
| 2026-07-03 | codex → codex | review → done | A33 review passed: H3 signal-history replay and H4 DB metadata evidence verified |
