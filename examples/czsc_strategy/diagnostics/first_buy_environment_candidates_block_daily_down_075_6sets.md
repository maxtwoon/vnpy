# First-Buy Environment Candidates

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


- SC short multiplier: `0.75`
- Goal: reduce weak-window first-buy damage without creating a narrow single-point fix.

| candidate | all5_pass | symbol_sets | trades | PF | drawdown | sharpe | calmar | WF | failing_sets |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| block_daily_down | True | 2/6 | 103 | 1.50 | 0.93% | 1.13 | 1.36 | 7/9 | no_RB, no_SC, core_AP_A_ZN, no_ZN |

## Symbol-Set Detail

### block_daily_down

| set | pass | trades | PF | sharpe | calmar | WF | failing_checks |
|---|---|---:|---:|---:|---:|---:|---|
| all5 | True | 103 | 1.50 | 1.13 | 1.36 | 7/9 | - |
| no_RB | False | 89 | 1.49 | 1.08 | 1.27 | 6/9 | risk_adjusted_gt_buy_hold |
| no_SC | False | 56 | 2.53 | 1.61 | 2.73 | 6/9 | trades_ge_scaled_min |
| core_AP_A_ZN | False | 42 | 2.71 | 1.55 | 2.54 | 6/9 | trades_ge_scaled_min, risk_adjusted_gt_buy_hold |
| no_A | True | 87 | 1.42 | 0.77 | 0.83 | 6/9 | - |
| no_ZN | False | 89 | 1.46 | 1.14 | 1.15 | 5/9 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
