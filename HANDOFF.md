---
task: A71 - A69 Measurement-Gate Hardening (OOS/Perturbation/Cost-Sensitivity Verdicts)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a70-second-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

Second of three tasks (A70-A72) from the second third-party audit remediation roadmap
(`docs/design/a70-second-audit-remediation-roadmap.md`), promoted after A70 reached `done`
(codex accepted on the first review round).

A69 (done in the first A65-A69 roadmap) deliberately implemented three *measurement-only* gates
(`evaluate_oos_gate()` in `diagnostics/backtest_matrix_report.py`, `evaluate_perturbation_gate()`
in `diagnostics/risk_param_sensitivity_report.py`, and `cost_sensitivity_report.py`'s delta
computation) with no invented pass/fail threshold — its own Decision Log explicitly recorded "no
threshold tuning" as the guiding principle. The second audit (66/100) flagged this as insufficient:
these measurements still require human interpretation, not an automated promotion/blocking signal.

**This is a delicate task.** Picking thresholds carelessly would itself be the "threshold
tuning/overfitting to observed data" anti-pattern this whole project has guarded against all
along. Any new threshold in this task must be an extreme, self-evidently-safe protective ceiling —
never a value backed into from what the current diagnostics data happens to show. The reasoning for
each threshold's safety (not its fit to current data) must be recorded in this task's own Decision
Log before merging.

**Full contract**: `docs/design/a70-second-audit-remediation-roadmap.md` §"A71" (this HANDOFF
summarizes it — read the full Rationale/Semantics there before writing code; it is more detailed
than this summary, including specific example rule text and known edge cases like near-zero
baseline returns causing spurious sign-flip "detections").

## Goal

Add a new verdict layer on top of each of the three existing A69 measurement functions, without
changing their existing return shapes or breaking their existing tests:

- `oos_gate_verdict(oos_result: dict) -> dict` in `diagnostics/backtest_matrix_report.py`, built on
  `evaluate_oos_gate()`'s existing per-symbol `sign_flip`/ratio output
  (`diagnostics/backtest_matrix_report.py:157`).
- `perturbation_gate_verdict(perturbation_result: dict) -> dict` in
  `diagnostics/risk_param_sensitivity_report.py`, built on `evaluate_perturbation_gate()`'s existing
  per-symbol sign-flip/delta output (`diagnostics/risk_param_sensitivity_report.py:100`).
- `cost_sensitivity_gate_verdict(result: dict) -> dict` in `diagnostics/cost_sensitivity_report.py`,
  built on `run_cost_sensitivity()`'s existing `symbols[symbol]["deltas"]` structure
  (`diagnostics/cost_sensitivity_report.py:40`/`:91`), which already has per-multiplier
  `delta_return_pct`/`relative_return_pct` vs. the `x1.0` baseline.

Each verdict function returns a `"pass"`/`"warn"`/`"fail"` status (or `"pass"`/`"fail"` only, if a
particular gate has no natural "warn" tier — must be justified if so) plus a human-readable
`reasons: list[str]`, and an overall rolled-up status per report (each diagnostic script's own
verdict is independent — no cross-script aggregation required).

## Acceptance Criteria

- [ ] All three verdict functions implemented, each with its threshold-selection reasoning recorded
      in this HANDOFF's Decision Log (see design doc §"A71" for the suggested starting rules —
      dev may adjust the exact numbers but must keep the "extreme, self-evidently-safe, not fit to
      observed data" property and explain why).
- [ ] Each verdict function has unit tests covering `"pass"`, and its failure/warning tier(s), using
      constructed fixture dicts — no dependency on real historical DB data.
- [ ] The existing `evaluate_oos_gate`/`evaluate_perturbation_gate`/A69's cost-sensitivity delta
      computation and their existing tests are unchanged (new functions are additive, not
      replacements).
- [ ] No threshold is backed into matching any specific value observed in
      `diagnostics/*.md`/`diagnostics/*.json` historical reports — the Decision Log must argue
      safety, not fit.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped if this changes any report script's user-visible output (it likely
      does not change `chan_strategy/config.py`'s `STRATEGY_CONFIG`/`BACKTEST_CONFIG` values, so the
      automated `project_version_freshness` gate won't force a bump — but house style still expects
      one for any user-visible diagnostics behavior addition; bump anyway).

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a70-second-audit-remediation-roadmap.md` §"A71". Second of three
   A70-A72 tasks.
2. **Read the design doc's full Semantics section** — it includes a specific known edge case (near-
   zero baseline returns causing a spurious "sign flip" on the perturbation gate) that you must
   explicitly decide how to handle and record in this HANDOFF's Decision Log, not silently ignore.
3. **Scope:** `diagnostics/backtest_matrix_report.py`, `diagnostics/risk_param_sensitivity_report.py`,
   `diagnostics/cost_sensitivity_report.py`, plus their corresponding test files under
   `tests/unit/`. Do not touch `chan_strategy/*.py` trading logic, any SimNow order/cancel/send
   path, or A69's existing measurement-function return shapes.
4. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A71-scoped files are staged.** A70's dev round
   got this right by checking status before committing — keep doing that.
5. **Guardrails (reject-on-violation):** no threshold tuning fit to observed diagnostics data; no
   pre-2026-04-24 data for any new parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; do not wire `overall_status` into any automatic promotion/blocking flow — this
   task only adds the verdict signal itself, wiring it into a gate that blocks something is future
   work and out of scope.
6. **Include a Manual-verification block with natively-run counts** (claude-code will also
   independently re-run everything before triggering review, but do not skip this yourself), and
   run `ruff check` proactively before finishing.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A71 OOS/perturbation/cost-sensitivity gate verdicts implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-15 - A71 promoted from `docs/design/a70-second-audit-remediation-roadmap.md`'s draft to
  an active HANDOFF task, immediately after A70 reached `done` (codex accepted on the first review
  round). Second of three tasks in the second audit-remediation roadmap.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | claude-code → kimi-code | design → dev | A71 (A69 measurement-gate hardening) promoted from second third-party audit remediation roadmap; handoff design->dev |
