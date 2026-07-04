---
task: A35 Stop-Loss Stress Diagnostics
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-04
deliverables:
  - HANDOFF.md
  - docs/design/a35-stop-loss-stress-diagnostics.md
blockers: []
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

A31-A34 converted the major audit findings into repeatable evidence and declassified old promotion claims.

The next unresolved high-severity issue is H2: fixed stop-loss exits are checked and filled at bar close, so actual losses can materially exceed nominal stop levels. The latest audit diagnostic reports:

- H2 `status=detected`.
- Nominal stop-loss baseline: `300bp` / `-3.0%`.
- Worst observed stop-loss loss: about `-12.60%`.
- Max overshoot multiple: about `4.20x`.
- Overshoot count: `12`.

A35 must design a read-only stress diagnostic. It must measure the tail-risk gap before any trading or Position logic is changed.

## Goal

Design a reproducible stop-loss stress report for the Chan strategy workspace.

The diagnostic must compare existing close-based stop-loss outcomes with alternative stress assumptions:

1. Current close-based observed outcome.
2. Intrabar low/high trigger model.
3. Gap/open-exit model.
4. Optional penalty-slippage model.

## Acceptance Criteria

- `docs/design/a35-stop-loss-stress-diagnostics.md` exists.
- The design states A35 is diagnostic-only and does not change strategy, Position, SimNow, order, cancel, or gateway logic.
- The design specifies a script named `examples/czsc_strategy/diagnostics/stop_loss_stress_report.py`.
- The design specifies generated outputs:
  - `examples/czsc_strategy/diagnostics/stop_loss_stress_report_YYYY-MM-DD.json`
  - `examples/czsc_strategy/diagnostics/stop_loss_stress_report_YYYY-MM-DD.md`
- The design defines required report fields:
  - `worst_loss_pct`
  - `overshoot_count`
  - `max_overshoot_multiple`
  - `affected_trade_count`
  - `affected_symbols`
  - baseline and stress scenario summaries
- The design defines deterministic behavior when SQLite K-line data is unavailable: mark intrabar/gap scenarios as `unavailable`, keep baseline diagnostics, and do not silently pass.
- The design includes unit-test acceptance for pure stress calculations, missing data handling, and report rendering.
- The design forbids new parameter tuning, old-OOS optimization, `GOAL PASSED`, and any SimNow trading interface changes.
- `python tools/sync_check.py` passes.
- `python tools/handoff.py next --summary "A35 design complete: stop-loss stress diagnostics"` succeeds and advances to `dev`.

## Notes for the Next Agent

Read this file and `docs/design/a35-stop-loss-stress-diagnostics.md` before writing code.

Implement only the diagnostic described there. Do not fix stop-loss logic yet. The intended implementation is:

- Add a read-only script `examples/czsc_strategy/diagnostics/stop_loss_stress_report.py`.
- Reuse existing evidence collection where reasonable, especially stop-loss pair scanning from `audit_issue_diagnostics.py`.
- Add focused tests in `examples/czsc_strategy/tests/unit/test_stop_loss_stress_report.py`.
- Generate JSON and Markdown reports with clear `Diagnostic only, not a trading recommendation.` disclaimers.
- If DB/K-line data is unavailable, keep the report explicit: baseline is available, intrabar/gap scenarios are unavailable.
- Do not tune parameters or regenerate strategy-performance claims.
- Do not touch SimNow order/cancel/send-order paths.

Suggested verification commands for dev:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_stop_loss_stress_report.py -q
python -m pytest examples\czsc_strategy\tests\unit\test_audit_issue_diagnostics.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python tools\handoff.py next --summary "A35 stop-loss stress diagnostics implemented"
```

## Decision Log

- 2026-07-04 - A35 started after A34 reached `done`.
- 2026-07-04 - Chose H2 stop-loss stress diagnostics as the next task because it is the highest remaining tail-risk issue and can be measured without changing trading logic.
- 2026-07-04 - Chose diagnostic-first scope: no Position logic changes, no strategy tuning, no SimNow trading changes.
- 2026-07-04 - Review rejection: duplicated stop-loss records across diagnostics JSON files and stale generated reports. Fixed by canonicalizing exit reasons, deduplicating trades, exposing raw/unique/duplicate counts, regenerating JSON/Markdown, and rerunning tests + preflight.

## Handoff History

| Date | From -> To | Stage Change | Summary |
|------|------------|--------------|---------|
| 2026-07-04 | codex -> claude-code | done -> design | A35 stop-loss stress diagnostics started |
| 2026-07-04 | claude-code -> kimi-code | design -> dev | A35 design complete: stop-loss stress diagnostics |
| 2026-07-04 | kimi-code -> codex | dev -> review | A35 stop-loss stress diagnostics implemented |
| 2026-07-04 | codex -> kimi-code | review -> dev | Rejected: duplicated stop-loss records and stale generated artifacts |
| 2026-07-04 | kimi-code -> codex | dev -> review | A35 remediation: deduplicated trades, exposed raw/unique/duplicate counts, regenerated reports, tests + preflight pass |

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-04 | claude-code → kimi-code | design → dev | A35 design complete: stop-loss stress diagnostics |
| 2026-07-04 | kimi-code → codex | dev → review | A35 stop-loss stress diagnostics implemented |
| 2026-07-04 | codex → kimi-code | review → dev | 打回：止损交易对在多份 diagnostics JSON 中重复，且生成的报告 artifact 已过期；要求去重、暴露 raw/unique/duplicate 计数、重新生成 JSON/Markdown、重跑测试与 preflight |
| 2026-07-04 | kimi-code → codex | dev → review | A35 修复完成：去重止损交易对，暴露 raw/unique/duplicate 计数，重新生成报告，测试与 preflight 全部通过 |
