---
task: A69 - OOS/Parameter-Perturbation/Cost-Sensitivity Minimum Gate
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a65-third-party-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

Fifth and FINAL task of the 2026-07-14 third-party-audit remediation roadmap
(`docs/design/a65-third-party-audit-remediation-roadmap.md` §"A69"), promoted immediately after
A68 reached `done` (codex accepted on the first review round). Completing this task finishes the
entire A65-A69 roadmap.

**This task is intentionally under-specified in the design doc** — unlike A65-A68, the audit's own
framing was directional ("give OOS, parameter perturbation, and cost/slippage sensitivity a minimum
gate"), not a fully-specified mechanism with an exact file/function name. **This task's own design
step must make concrete decisions before any code is written** — mirroring the A56/A67
"decide, then implement" pattern.

**claude-code's own pre-promotion research (2026-07-15, evidence for dev's design step, NOT a
pre-made decision):**

1. **OOS infrastructure already exists but has no gate.** `diagnostics/backtest_matrix_report.py`
   already defines `DEFAULT_IS_START`/`DEFAULT_IS_END`/`DEFAULT_OOS_START`/`DEFAULT_OOS_END`
   (confirmed, lines 26-29) and computes both `"in_sample"` and `"out_sample"` periods
   (`build_matrix`, lines 148-153) — but the report only *displays* both periods' numbers side by
   side; nothing asserts or gates on the relationship between them (e.g. "OOS expectancy sign
   matches IS," "OOS Sharpe isn't catastrophically worse than IS"). **The gap here is "no gate
   checks the IS/OOS relationship," not "no OOS split exists."**
2. **Parameter-perturbation infrastructure already exists but has no gate.**
   `diagnostics/risk_param_sensitivity_report.py` already runs the strategy under several
   parameter `VARIANTS` (confirmed, e.g. `"stop_loss_tight"` with tightened stop-loss percentages
   vs. `"baseline"`) and produces a comparison report — but it is report-only; nothing asserts a
   pass/fail criterion (e.g. "no variant flips the sign of total return," "no variant's max
   drawdown exceeds N% of baseline's"). **Reuse this script's variant-comparison pattern rather
   than inventing a new one.**
3. **No dedicated cost/slippage-sensitivity script currently exists as a re-runnable mechanism.**
   Historical one-off reports (`diagnostics/platform_final_robustness_cost2_*.md/.json`, dated
   artifacts from an earlier task) explored 2x-cost scenarios, but there is no current script that
   re-runs this on demand the way `risk_param_sensitivity_report.py` does for stop-loss parameters.
   This is the one area of the three that may need genuinely new code, not just a new gate on
   existing output.

Full contract: `docs/design/a65-third-party-audit-remediation-roadmap.md` §"A69 —
OOS/Parameter-Perturbation/Cost-Sensitivity Minimum Gate (Own Sub-Design)" (the authoritative
design — this HANDOFF summarizes it).

## Goal

**Step 1 (required, before any code):** Record in this HANDOFF's Decision Log what "OOS gate,"
"parameter-perturbation gate," and "cost-sensitivity gate" concretely mean as implementable checks
in THIS codebase, informed by the research above. At minimum, decide:
- What OOS check to add on top of the already-existing IS/OOS split (e.g. a unit test or
  diagnostic-script assertion that OOS expectancy sign matches IS, or that OOS Sharpe/drawdown
  isn't catastrophically worse — pick a concrete, decidable threshold or comparison, not a vague
  "check that it's reasonable").
- What parameter-perturbation check to add on top of `risk_param_sensitivity_report.py`'s existing
  variant mechanism (e.g. assert no variant's total-return sign flips relative to baseline, or a
  similar concrete, decidable criterion).
- What minimal cost/slippage-sensitivity mechanism to add (e.g. re-run the same backtest at
  1.5x/2x the configured `commission_rate`/`slippage` and report the delta — a MEASUREMENT gate
  reporting honest sensitivity, not necessarily a hard pass/fail threshold, is an acceptable
  "minimum" bar per the design doc's own framing).

**Step 2:** Implement at least ONE of the three as a real, runnable check with a documented
pass/fail or honest-measurement output — implementing all three well is preferable to implementing
one poorly; if all three prove implementable within a reasonable dev round, do all three.

**If, after doing this analysis, the scope proves too large for one dev round, say so explicitly
and propose an A69a/A69b/A69c split** (mirroring the P8a/P8b precedent) rather than forcing an
oversized or corner-cut implementation into one handoff.

## Acceptance Criteria

- [x] A recorded design decision (in the Decision Log, BEFORE code) on what each of the three
      concepts (OOS, perturbation, cost-sensitivity) concretely means as an implementable check in
      this codebase, informed by the existing infrastructure cited in Background.
- [x] All three are implemented as real, runnable measurement gates:
  - OOS: `diagnostics/backtest_matrix_report.py::evaluate_oos_gate()` + markdown section.
  - Parameter perturbation: `diagnostics/risk_param_sensitivity_report.py::evaluate_perturbation_gate()` + markdown section.
  - Cost sensitivity: new `diagnostics/cost_sensitivity_report.py` (1.0x/1.5x/2.0x commission+slippage).
- [x] Existing `backtest_matrix_report.py`/`risk_param_sensitivity_report.py` behavior/output is
      NOT broken by any reuse of their infrastructure (their own existing tests, if any, stay
      byte-identical unless this task's own scope explicitly extends them).
- [x] No threshold tuning; no pre-2026-04-24 data used for any NEW parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `diagnostics/run_next_work.ps1 -Preflight` passes.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a65-third-party-audit-remediation-roadmap.md` §"A69". Fifth and
   FINAL task of the A65-A69 roadmap — completing this closes out the entire third-party-audit
   remediation wave.
2. **Do the design-decision step first, literally before writing any code.** Read
   `diagnostics/backtest_matrix_report.py`'s existing IS/OOS constants and
   `diagnostics/risk_param_sensitivity_report.py`'s existing variant mechanism yourself — don't
   just trust this HANDOFF's summary — before deciding what to add.
3. **Scope:** `diagnostics/*.py` (extending existing scripts preferred over new ones where
   possible) and/or `tests/unit/*.py`. Do not touch `chan_strategy/*.py` trading logic, any SimNow
   order/cancel/send path, or existing scripts' current numeric outputs.
4. **This is explicitly allowed to be smaller in final scope than "all three fully solved"** — a
   well-reasoned, honestly-scoped partial solution (e.g. "I implemented the OOS gate and the
   cost-sensitivity measurement; parameter-perturbation gating is proposed as a follow-up A69a
   because X" ) is acceptable and preferred over a rushed, corner-cut implementation of all three.
5. **"Minimum gate" does not require a hard pass/fail for every concept** — per the design doc's
   own framing, an honest MEASUREMENT (e.g. "here is how much the cost-sensitivity variant moves
   the numbers") satisfies the "minimum" bar for cost-sensitivity if a hard threshold isn't yet
   well-justified; do not invent an arbitrary threshold just to have one.
6. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any NEW parameter choice; no SimNow order/cancel/send paths touched;
   no `GOAL PASSED`; no fabricated claims of statistical significance from limited data.
7. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing.**
8. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A69 OOS/perturbation/cost-sensitivity gate implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. **This is the last task in the
   entire A65-A69 roadmap** — after this reaches `done`, the whole third-party-audit remediation
   wave is complete.

## Manual Verification

```text
pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
# 640 passed, 4 deselected

ruff check examples/czsc_strategy/diagnostics/backtest_matrix_report.py \
           examples/czsc_strategy/diagnostics/risk_param_sensitivity_report.py \
           examples/czsc_strategy/diagnostics/cost_sensitivity_report.py \
           examples/czsc_strategy/tests/unit/test_a69_robustness_gates.py
# All checks passed

python tools/sync_check.py
# PASS

python tools/sync_check.py --root examples/czsc_strategy
# PASS

powershell -ExecutionPolicy Bypass -File examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight
# Preflight complete
```

## Decision Log

- 2026-07-15 - A69 promoted from `docs/design/a65-third-party-audit-remediation-roadmap.md`'s
  draft to an active HANDOFF task, started immediately after A68 reached `done` (codex accepted on
  the first review round). This is the final task of the A65-A69 roadmap and the entire
  2026-07-14 third-party-audit remediation wave.
- 2026-07-15 - claude-code's pre-promotion research confirmed: OOS infrastructure
  (`backtest_matrix_report.py`'s IS/OOS constants) and parameter-perturbation infrastructure
  (`risk_param_sensitivity_report.py`'s variant mechanism) both already exist as report-only
  outputs with no gate; no re-runnable cost/slippage-sensitivity script currently exists (only
  historical one-off reports). This evidence is presented for dev's own design step to weigh, not
  as a pre-made decision.
- 2026-07-15 (kimi-code dev design step) — Concrete implementable checks decided BEFORE code:
  * **OOS gate:** Reuse `backtest_matrix_report.py`'s existing IS/OOS split. For each symbol,
    compare `in_sample` and `out_sample` `total_return_pct` signs. A sign flip (one positive, one
    negative) is flagged as an honest measurement of qualitative instability. Also report the
    OOS/IS return ratio and OOS/IS max-drawdown ratio as supplementary sensitivity metrics. No
    hard pass/fail threshold is invented; the gate is a measurement/reporting gate.
  * **Parameter-perturbation gate:** Reuse `risk_param_sensitivity_report.py`'s existing variant
    mechanism. For each symbol, compare every variant's `total_return_pct` sign against the
    baseline. Any sign flip is flagged. Also report the maximum absolute return delta across
    variants as a sensitivity metric. No threshold tuning; the gate is a measurement/reporting
    gate.
  * **Cost-sensitivity gate:** Add a new runnable script
    `diagnostics/cost_sensitivity_report.py`. It runs the same backtest at 1.0x (baseline),
    1.5x, and 2.0x the configured `commission_rate` + `slippage`, leveraging `BacktestEngine`'s
    existing constructor parameters. It reports absolute and relative deltas in
    `total_return_pct`, `max_drawdown_pct`, and `sharpe_ratio`. This is an honest measurement gate
    (no arbitrary pass/fail threshold), matching the audit's "minimum gate" framing.
  * Scope kept to `diagnostics/*.py` plus `tests/unit/*.py`; no `chan_strategy/*.py` trading logic
    or SimNow order/cancel/send paths are touched. All three gates are measurement/reporting-only
    and implemented in this single dev round because each reuses existing infrastructure with a
    small, well-bounded addition.
- 2026-07-15 (claude-code pre-review due diligence, before triggering codex) — kimi-code's original
  dev commit (`31879e56`) had two problems, found and fixed before review:
  1. `diagnostics/cost_sensitivity_report.py` — one of the three claimed-complete gates — was never
     actually committed. It lives under the git-ignored `diagnostics/` path and needs `git add -f`
     (the same class of omission as A59); the committed `test_a69_robustness_gates.py` imports it 5
     times, so a fresh checkout would fail on import. Fixed by `git add -f`-ing the file into the
     real A69 commit.
  2. The same commit bundled an entirely unrelated, unrequested change — making historical-DB
     auto-update default-on for formal `-LiveCapture` runs in `run_next_work.ps1`, plus matching
     doc/test updates — under the A69 commit message. This is the concurrent SimNow-observation
     workstream's own "2026-07-15 Formal Daily Flow Alignment Fix" (visible in
     `diagnostics/WORK_LOG.md`'s own entry of that name), which was sitting uncommitted in the
     working tree and got scooped in, not something kimi-code wrote for A69. Per this session's
     standing rule not to revert or interfere with that concurrent workstream's own files, this
     content was NOT discarded — it was left as uncommitted working-tree changes (unchanged from
     before A69's dev round started) so that workstream can commit it on its own terms. `git reset
     HEAD~1` (mixed, local-only, nothing pushed) was used to split the single bundled commit into
     the true A69-scoped commit (`834fe5e0`: `HANDOFF.md`, `backtest_matrix_report.py`,
     `risk_param_sensitivity_report.py`, `cost_sensitivity_report.py`, `test_a69_robustness_gates.py`)
     — the unrelated files were left unstaged, not committed by claude-code.
  3. Re-verified independently after the split: `pytest examples/czsc_strategy/tests/unit -q -m "not
     realdb"` → 640 passed, 4 deselected; `ruff check` on the four A69 files → all checks passed;
     both `sync_check.py` gates → PASS; `run_next_work.ps1 -Preflight` → preflight complete.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | codex → claude-code | done → dev | A69 (OOS/perturbation/cost-sensitivity gate) promoted from third-party audit remediation roadmap; handoff design->dev |
| 2026-07-15 | kimi-code → codex | dev → review | A69 OOS/perturbation/cost-sensitivity gate implemented |
