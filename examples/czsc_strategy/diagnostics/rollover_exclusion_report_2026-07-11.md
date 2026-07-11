# Rollover Exclusion Diagnostic Report

**Generated at:** 2026-07-11T05:21:31.555171+00:00
**Window:** 2026-04-24 ~ 2026-07-09

> RESEARCH-ONLY — Diagnostic only, not a trading recommendation.

## Method

- Rollover transitions are detected from the raw table's `real_symbol` column (primary).
- For each transition date, trades with open or close in `{prev, transition, next}` trading dates are excluded.
- The baseline backtest uses the default `stop_execution_model='close'`.
- `return` and `drawdown` are computed from the cumulative pair P&L curve; `stop_loss_overshoot` reuses the A35/A38 definition.

## Results by Symbol

### AP888

- **Detection method:** real_symbol
- **Transitions:** 0
- **Excluded dates:** 

| Metric | Before | After |
|--------|--------|-------|
| trade_count | 2 | 2 |
| return | -5.8398 | -5.8398 |
| drawdown | 5.8398 | 5.8398 |
| stop_loss_overshoot_count | 0 | 0 |
| stop_loss_worst_loss_pct | None | None |

### RB888

- **Unavailable:** insufficient_bars_in_window
- **Detection method:** real_symbol

| Metric | Before | After |
|--------|--------|-------|
| trade_count | 0 | 0 |
| return | 0.0 | 0.0 |
| drawdown | 0.0 | 0.0 |
| stop_loss_overshoot_count | 0 | 0 |
| stop_loss_worst_loss_pct | None | None |

### SC888

- **Detection method:** real_symbol
- **Transitions:** 1
  - 2026-07-01: sc2606 -> sc2608
- **Excluded dates:** 2026-07-01, 2026-07-02
- **Exclusion notes:**
  - 2026-07-01: previous side absent_from_diagnostic_window

| Metric | Before | After |
|--------|--------|-------|
| trade_count | 0 | 0 |
| return | 0.0 | 0.0 |
| drawdown | 0.0 | 0.0 |
| stop_loss_overshoot_count | 0 | 0 |
| stop_loss_worst_loss_pct | None | None |

### A888

- **Unavailable:** insufficient_bars_in_window
- **Detection method:** real_symbol

| Metric | Before | After |
|--------|--------|-------|
| trade_count | 0 | 0 |
| return | 0.0 | 0.0 |
| drawdown | 0.0 | 0.0 |
| stop_loss_overshoot_count | 0 | 0 |
| stop_loss_worst_loss_pct | None | None |

### ZN888

- **Detection method:** real_symbol
- **Transitions:** 1
  - 2026-07-01: zn2606 -> zn2608
- **Excluded dates:** 2026-07-01, 2026-07-02
- **Exclusion notes:**
  - 2026-07-01: previous side absent_from_diagnostic_window

| Metric | Before | After |
|--------|--------|-------|
| trade_count | 0 | 0 |
| return | 0.0 | 0.0 |
| drawdown | 0.0 | 0.0 |
| stop_loss_overshoot_count | 0 | 0 |
| stop_loss_worst_loss_pct | None | None |

## Notes

- 888 continuous contracts are raw splices (`found_spliced`).
- `real_symbol` is the primary rollover source; no cross-rollover price adjustment is applied.
- This diagnostic excludes rollover windows for comparison only; it does not alter live prices or gating.
