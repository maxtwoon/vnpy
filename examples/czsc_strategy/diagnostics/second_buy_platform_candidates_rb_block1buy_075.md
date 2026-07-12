# Second-Buy Platform Candidates

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
- Goal: find a broader platform by changing only second-buy symbol eligibility.

| candidate | all5_pass | symbol_sets | trades | PF | drawdown | sharpe | calmar | WF | failing_sets |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| AP_RB_A_ZN | True | 1/5 | 104 | 1.52 | 0.93% | 1.16 | 1.40 | 7/9 | no_SC, core_AP_A_ZN, no_RB, no_ZN |

## Symbol-Set Detail

### AP_RB_A_ZN

| set | pass | trades | PF | sharpe | calmar | WF | failing_checks |
|---|---|---:|---:|---:|---:|---:|---|
| all5 | True | 104 | 1.52 | 1.16 | 1.40 | 7/9 | - |
| no_SC | False | 57 | 2.57 | 1.64 | 2.79 | 6/9 | trades_ge_scaled_min |
| core_AP_A_ZN | False | 42 | 2.71 | 1.55 | 2.54 | 6/9 | trades_ge_scaled_min, risk_adjusted_gt_buy_hold |
| no_RB | False | 89 | 1.49 | 1.08 | 1.27 | 6/9 | risk_adjusted_gt_buy_hold |
| no_ZN | False | 90 | 1.48 | 1.18 | 1.19 | 5/9 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
