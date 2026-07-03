# A34 Design: Audit Remediation Roadmap

**Task:** Convert the quantified A31-A33 audit findings into a phased remediation roadmap with explicit gates.

**Scope:** Design only. Do not implement strategy fixes, do not change trading logic, do not tune parameters, and do not present any historical result as a fresh profitability proof.

---

## 1. Background And Goal

A31-A33 changed the audit work from opinion into repeatable evidence:

- H1 is `detected`: high-precision weight evidence exists, including the `0.847` SC short multiplier family.
- H2 is `detected`: stop-loss overshoot exists; the current diagnostic shows worst loss near `-12.60%` versus a nominal `-3.0%` stop, with max overshoot around `4.20x`.
- H3 is `detected`: real signal-history replay found `背驰V260615_失效` count `0`, so the branch is not merely missing evidence; it is unreachable in the scanned real replay.
- H4 is `found_spliced`: the 888 series is a multi-contract raw splice according to SQLite metadata.
- M1 is `detected`: `BACKTEST_CONFIG` and `BacktestEngine` defaults disagree on commission/slippage.

A34 does not repair those issues directly. It defines a remediation sequence that prevents the team from continuing to optimize returns on a contaminated OOS window while the known audit findings remain unresolved.

The output of A34 is a development-ready roadmap. The next dev agent should implement it phase by phase, with each phase independently testable and logged.

---

## 2. Issue Triage And Treatment

### H1: OOS Reuse And 0.847-Style Overfit

**Finding:** The historical OOS window has been repeatedly used for parameter selection. The `0.847` family is a high-precision gate-fitting signature, not a robust trading discovery.

**Treatment:** Policy freeze first, not more optimization.

Requirements:

- Freeze all current parameters before further research changes.
- Do not use the 2022-2026 historical OOS window for new parameter selection.
- Treat 2026-04-24 onward incremental data plus SimNow observation as the only future validation stream.
- Retire or roll back weight-like parameters with more than one decimal place when used as promotion evidence.
- Add data-contact metadata to future diagnostics:
  - `used_data_windows`
  - `decision_data_windows`
  - `is_promotion_evidence`
  - `research_only`

Expected outcome:

- Historical reports remain useful as research artifacts.
- They stop being promotion evidence.

### H2: Stop-Loss Overshoot

**Finding:** Bar-close stop-loss checks can produce losses far larger than the nominal stop.

**Treatment:** Diagnose with stress reports before changing the live risk model.

Requirements:

- Add a stop-loss stress diagnostic that recomputes historical stop-loss exits under alternative assumptions:
  - current close-based model;
  - intrabar low/high trigger model;
  - overnight/gap open-exit model;
  - optional penalty slippage model.
- Produce before/after comparison fields:
  - `worst_loss_pct`
  - `overshoot_count`
  - `max_overshoot_multiple`
  - `affected_trade_count`
  - `affected_symbols`
- Do not replace official backtest conclusions until the stress report is produced and reviewed.

Expected outcome:

- The real tail-risk gap is measured before any Position logic is changed.

### H3: Dead `背驰=失效` Exit Branch

**Finding:** Real signal-history replay reports zero occurrences of `背驰V260615_失效`.

**Treatment:** Decide whether to repair or delete the branch. Do not leave it as a pretend covered path.

Options:

- **Option A: Repair.** Redefine failure comparison across alternating strokes, for example comparing `after_zs_bis[-3]` with `after_zs_bis[-1]` rather than adjacent same-direction strokes.
- **Option B: Delete.** Remove the exit factors that depend on `背驰=失效` and simplify the position rules.
- **Option C: Deprecate.** Keep the classification for compatibility but mark it deprecated and remove it from trading decisions.

Requirements:

- If repaired, real signal-history replay must show `背驰V260615_失效` count greater than zero, or the repair is not accepted.
- If deleted, `positions.py` must no longer reference the factor.
- Tests must enforce the domain invariant that confirmed BI directions alternate; adjacent same-direction fake structures cannot be the only coverage path.

Expected outcome:

- No trading factor depends on an unreachable classification.

### H4: Raw-Spliced 888 Continuous Contracts

**Finding:** SQLite metadata indicates that 888 tables switch `real_symbol`; no adjustment evidence has been established.

**Treatment:** Risk declaration plus rollover-pollution diagnostics before any data-source rebuild.

Requirements:

- Add a rollover exclusion diagnostic:
  - detect contract transition dates by symbol;
  - remove signals/trades within transition date +/- 1 trading day;
  - compare baseline and excluded results.
- Report:
  - `trade_count_before`
  - `trade_count_after`
  - `return_before`
  - `return_after`
  - `drawdown_before`
  - `drawdown_after`
  - `stop_loss_overshoot_before`
  - `stop_loss_overshoot_after`
- Add explicit documentation that current 888 data is `found_spliced` and adjustment is unverified.
- Do not assume vendor adjustment rules that are not present in DB metadata or documentation.

Expected outcome:

- The team can judge whether rollover days materially drive signals, losses, or H2 overshoot.

### M1: Cost Single Source Of Truth

**Finding:** `BACKTEST_CONFIG` and `BacktestEngine` constructor defaults use different commission/slippage values.

**Treatment:** Fix first. This is low-risk and high-certainty.

Requirements:

- `BacktestEngine` default costs must come from `BACKTEST_CONFIG`.
- Position defaults should either come from config or become explicit required values.
- Report headers must print actual commission/slippage used.
- `audit_issue_diagnostics.py` M1 should move from `detected` conflict to consistent after the fix.

Expected outcome:

- Backtests and diagnostics share one cost truth.

---

## 3. Recommended Implementation Order

### Phase 1: M1 Cost Single Source

Why first:

- It is deterministic.
- It does not change signal semantics.
- It removes a known false comparison between diagnostics and engine runs.

Deliverables:

- Code change in cost defaults.
- Tests proving defaults equal `BACKTEST_CONFIG`.
- Report header showing actual cost values.
- A refreshed audit diagnostic showing M1 consistent.

### Phase 2: H1 Parameter Freeze And Report Declassification

Why second:

- It stops further methodological damage before any new experiment.
- It does not change trading behavior.

Deliverables:

- Diagnostics metadata fields for data contact.
- Existing final-candidate reports marked as research-only.
- `0.847`-style high-precision weights removed from promotion criteria or explicitly rejected as promotion evidence.

### Phase 3: H2 Stop-Loss Stress Diagnostic

Why third:

- Tail risk matters before any signal repair.
- The team needs before/after evidence before changing Position logic.

Deliverables:

- `stop_loss_stress_report_YYYY-MM-DD.json`
- `stop_loss_stress_report_YYYY-MM-DD.md`
- Unit tests for intrabar and gap stress calculations.

### Phase 4: H3 Branch Decision

Why fourth:

- It changes signal/position semantics, so it should follow cost and methodology cleanup.

Deliverables:

- A decision record: repair, delete, or deprecate.
- If repair: signal-history replay shows count > 0.
- If delete: position rules no longer reference the factor.
- Tests enforce confirmed-BI direction alternation.

### Phase 5: H4 Rollover Pollution Diagnostic

Why fifth:

- It is data-heavy and may require broader report regeneration.
- It should not be mixed with strategy-rule changes.

Deliverables:

- `rollover_exclusion_report_YYYY-MM-DD.json`
- `rollover_exclusion_report_YYYY-MM-DD.md`
- Documentation of 888 raw-splice risk.

---

## 4. Expected File Changes By Phase

### Phase 1: M1

Likely files:

- `examples/czsc_strategy/chan_strategy/backtest_engine.py`
- `examples/czsc_strategy/chan_strategy/config.py`
- `examples/czsc_strategy/tests/unit/test_backtest_entrypoints.py`
- `examples/czsc_strategy/tests/unit/test_audit_issue_diagnostics.py`
- relevant diagnostics report generators that print backtest headers

### Phase 2: H1

Likely files:

- `examples/czsc_strategy/diagnostics/audit_issue_diagnostics.py`
- `examples/czsc_strategy/diagnostics/NEXT_WORK.md`
- `examples/czsc_strategy/diagnostics/ACCEPTANCE.md`
- `examples/czsc_strategy/diagnostics/WORK_LOG.md`
- generated final-candidate reports, with research-only annotations only

### Phase 3: H2

Likely files:

- `examples/czsc_strategy/diagnostics/stop_loss_stress_report.py`
- `examples/czsc_strategy/tests/unit/test_stop_loss_stress_report.py`
- generated stop-loss stress JSON/Markdown reports

### Phase 4: H3

Likely files:

- `examples/czsc_strategy/chan_strategy/signals.py`
- `examples/czsc_strategy/chan_strategy/positions.py`
- `examples/czsc_strategy/diagnostics/generate_signal_history.py`
- `examples/czsc_strategy/tests/unit/test_signals.py`
- `examples/czsc_strategy/tests/unit/test_audit_issue_diagnostics.py`

### Phase 5: H4

Likely files:

- `examples/czsc_strategy/diagnostics/rollover_exclusion_report.py`
- `examples/czsc_strategy/tests/unit/test_rollover_exclusion_report.py`
- a Chan strategy README or risk note documenting 888 `found_spliced`

### Files And Actions Explicitly Forbidden

- Do not modify SimNow order, cancel, or trading gateway calls.
- Do not tune `0.847` or any neighboring weight to regain a pass.
- Do not delete negative diagnostics evidence.
- Do not use the old OOS window for new parameter selection.
- Do not mark any repaired result as `GOAL PASSED` until a future holdout/SimNow observation window supports it.

---

## 5. Test And Acceptance Design

### M1 Acceptance

- [ ] `BacktestEngine` default commission/slippage equal `BACKTEST_CONFIG`.
- [ ] Position cost defaults are aligned with config or made explicit.
- [ ] Reports print actual commission/slippage.
- [ ] `audit_issue_diagnostics.py` reports M1 as consistent.
- [ ] `run_next_work.ps1 -Preflight` passes.

### H1 Acceptance

- [ ] Reports clearly mark historical final candidates as research-only.
- [ ] `0.847`-style high-precision weights are not promotion evidence.
- [ ] Diagnostics include `used_data_windows` and `decision_data_windows`.
- [ ] Future validation stream is documented as 2026-04-24 onward plus SimNow observation.

### H2 Acceptance

- [ ] Stop-loss stress report is generated in JSON and Markdown.
- [ ] Baseline and stress `worst_loss_pct` are both shown.
- [ ] `overshoot_count` and `max_overshoot_multiple` are shown.
- [ ] No stop-loss overshoot is hidden by aggregation.

### H3 Acceptance

- [ ] If repaired, real `signal_history` replay shows `背驰V260615_失效` count > 0.
- [ ] If deleted, no position factor references `背驰=失效`.
- [ ] Tests reject adjacent same-direction confirmed-BI fake structures as the only coverage source.

### H4 Acceptance

- [ ] Rollover exclusion report is generated in JSON and Markdown.
- [ ] AP/RB/SC/A/ZN transition windows are all evaluated.
- [ ] Report compares trade count, return, drawdown, and stop-loss overshoot before/after exclusion.
- [ ] Documentation states that current 888 data is `found_spliced` and adjustment remains unverified unless proven otherwise.

### Safety Acceptance

- [ ] No new `send_order`, `cancel_order`, `buy`, `sell`, `short`, or `cover` calls.
- [ ] No `password`, `auth_code`, `api_key`, `account_id`, or `setting_masked` leakage.
- [ ] Every new report contains `Diagnostic only, not a trading recommendation.`
- [ ] No report claims `GOAL PASSED` from the old OOS window.

---

## 6. Boundaries

A34 and its implementation phases do not:

- optimize profitability;
- expand capital or symbols;
- enable automatic live trading;
- convert old OOS results into promotion evidence;
- erase previous negative results;
- rebuild the historical data vendor pipeline.

Any future performance claim must use data that was not touched during this remediation design.

---

## 7. Dev Handoff Prompt

Use this prompt for the dev agent:

```text
Read HANDOFF.md and docs/design/a34-audit-remediation-roadmap.md. Implement A34 in phases.

Start with Phase 1 and Phase 2 only:

Phase 1:
- Align BacktestEngine and Position cost defaults with BACKTEST_CONFIG.
- Ensure reports print actual commission/slippage.
- Add tests proving cost defaults match config.
- Regenerate audit diagnostics and confirm M1 is consistent.

Phase 2:
- Add research-only / not-promotion-proof metadata to historical final-candidate diagnostics.
- Add used_data_windows and decision_data_windows fields where future diagnostics are generated.
- Ensure 0.847-style high-precision weights are not treated as promotion evidence.

Do not implement Phase 3-5 until Phase 1-2 pass review.

Run:
- python -m pytest examples/czsc_strategy/tests/unit/test_audit_issue_diagnostics.py -q
- powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
- python tools/handoff.py next --summary "A34 phase 1-2 implemented"

Do not modify SimNow order/cancel logic, do not tune parameters, and do not claim GOAL PASSED.
```

---

## 8. Review Checklist

The review agent should reject the implementation if:

- M1 is still inconsistent after Phase 1.
- Any new report hides the historical OOS contamination.
- Any code tunes a parameter instead of freezing/declassifying promotion evidence.
- Any stop-loss fix is made before the stress diagnostic exists.
- Any SimNow trading interface is changed.
- `python tools/sync_check.py` fails.
