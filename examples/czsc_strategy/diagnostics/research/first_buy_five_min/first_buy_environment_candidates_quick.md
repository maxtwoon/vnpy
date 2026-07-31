# First-Buy Environment Candidates

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> This report was produced using the historical out-of-sample window `2022-01-01~2026-04-24`, which was repeatedly used for parameter selection. High-precision weights such as `0.847` and any `GOAL PASSED` rows are gate-fitting signatures, not evidence of a robust trading discovery. This artifact is retained as negative / contaminated evidence only.
>
> - `is_promotion_evidence`: False
> - `research_only`: True
> - `used_data_windows`: `["2022-01-01~2026-04-24"]`
> - `decision_data_windows`: ['2026-04-24~present', 'SimNow observation']
> - `note`: Future validation must use post-2026-04-24 incremental data and SimNow observation before any promotion claim can be considered.


- SC short multiplier: `0.847`
- Goal: reduce weak-window first-buy damage without creating a narrow single-point fix.

| candidate | all5_pass | symbol_sets | trades | PF | drawdown | sharpe | calmar | WF | failing_sets |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| current | True | 1/3 | 114 | 1.48 | 0.95% | 1.14 | 1.35 | 6/9 | no_SC, core_AP_A_ZN |
| block_daily_down | True | 1/3 | 103 | 1.52 | 0.92% | 1.18 | 1.44 | 6/9 | no_SC, core_AP_A_ZN |

## Symbol-Set Detail

### current

| set | pass | trades | PF | sharpe | calmar | WF | failing_checks |
|---|---|---:|---:|---:|---:|---:|---|
| all5 | True | 114 | 1.48 | 1.14 | 1.35 | 6/9 | - |
| no_SC | False | 64 | 2.39 | 1.58 | 2.45 | 5/9 | trades_ge_scaled_min, walk_forward_ge_2_3 |
| core_AP_A_ZN | False | 47 | 2.63 | 1.56 | 2.55 | 5/9 | trades_ge_scaled_min, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

### block_daily_down

| set | pass | trades | PF | sharpe | calmar | WF | failing_checks |
|---|---|---:|---:|---:|---:|---:|---|
| all5 | True | 103 | 1.52 | 1.18 | 1.44 | 6/9 | - |
| no_SC | False | 56 | 2.53 | 1.61 | 2.73 | 6/9 | trades_ge_scaled_min |
| core_AP_A_ZN | False | 42 | 2.71 | 1.55 | 2.54 | 6/9 | trades_ge_scaled_min, risk_adjusted_gt_buy_hold |
