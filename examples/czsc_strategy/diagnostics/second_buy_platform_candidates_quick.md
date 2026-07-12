# Second-Buy Platform Candidates

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
- Goal: find a broader platform by changing only second-buy symbol eligibility.

| candidate | all5_pass | symbol_sets | trades | PF | drawdown | sharpe | calmar | WF | failing_sets |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| A_ZN_only | False | 0/3 | 111 | 1.42 | 0.95% | 1.03 | 1.18 | 6/9 | all5, no_SC, core_AP_A_ZN |

## Symbol-Set Detail

### A_ZN_only

| set | pass | trades | PF | sharpe | calmar | WF | failing_checks |
|---|---|---:|---:|---:|---:|---:|---|
| all5 | False | 111 | 1.42 | 1.03 | 1.18 | 6/9 | risk_adjusted_gt_buy_hold |
| no_SC | False | 61 | 2.35 | 1.49 | 1.97 | 6/9 | trades_ge_scaled_min, risk_adjusted_gt_buy_hold |
| core_AP_A_ZN | False | 44 | 2.61 | 1.47 | 2.02 | 6/9 | trades_ge_scaled_min, risk_adjusted_gt_buy_hold |
