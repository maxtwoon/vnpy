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
| no_AP | RB888, SC888, A888, ZN888 | False | 99/80 | 1.16 | 1.33% | 0.55 | 0.54 | 5/9 | 0.50 | 0.46 | pf_ge_1_2, walk_forward_ge_2_3 |
| no_A | AP888, RB888, SC888, ZN888 | True | 98/80 | 1.40 | 1.16% | 0.78 | 0.83 | 6/9 | 0.62 | 0.78 | - |
| no_ZN | AP888, RB888, SC888, A888 | False | 98/80 | 1.46 | 1.16% | 1.19 | 1.20 | 5/9 | 0.98 | 1.63 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
| metals_energy | RB888, SC888, ZN888 | False | 83/60 | 1.01 | 1.54% | 0.08 | 0.07 | 5/9 | 0.18 | 0.10 | pf_ge_1_2, sharpe_ge_0_5, calmar_ge_0_5, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

## Interpretation

A candidate should not be promoted to a stable platform unless neighboring symbol sets also pass. If only one exact set passes, the edge is symbol-selection fragile.