# Symbol-Set Stability Scan

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> This report was produced using the historical out-of-sample window `2022-01-01~2026-04-24`, which was repeatedly used for parameter selection. High-precision weights such as `0.847` and any bare `GOAL PASSED` rows are gate-fitting signatures, not evidence of a robust trading discovery. This artifact is retained as negative / contaminated evidence only.
>
> - `is_promotion_evidence`: False
> - `research_only`: True
> - `used_data_windows`: `["2022-01-01~2026-04-24"]`
> - `decision_data_windows`: ['2026-04-24~present', 'SimNow observation']
> - `note`: Future validation must use post-2026-04-24 incremental data and SimNow observation before any promotion claim can be considered.


- scenario: `expanded_short_sc_0847`
- pass ratio: `1/4` = `25.00%`

| set | symbols | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | AP888, RB888, SC888, A888, ZN888 | True | 114/100 | 1.48 | 0.95% | 1.14 | 1.35 | 6/9 | 0.88 | 1.35 | - |
| no_RB | AP888, SC888, A888, ZN888 | False | 97/80 | 1.49 | 1.17% | 1.10 | 1.29 | 5/9 | 0.99 | 1.68 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
| no_SC | AP888, RB888, A888, ZN888 | False | 64/80 | 2.39 | 0.77% | 1.58 | 2.45 | 5/9 | 1.15 | 2.09 | trades_ge_scaled_min, walk_forward_ge_2_3 |
| core_AP_A_ZN | AP888, A888, ZN888 | False | 47/60 | 2.63 | 0.93% | 1.56 | 2.55 | 5/9 | 1.40 | 2.93 | trades_ge_scaled_min, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

## Interpretation

A candidate should not be promoted to a stable platform unless neighboring symbol sets also pass. If only one exact set passes, the edge is symbol-selection fragile.