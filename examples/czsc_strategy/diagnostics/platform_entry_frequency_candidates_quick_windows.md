# Platform Entry Frequency Candidates

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


- base: `block_1buy_daily_down + SC short multiplier 0.75`
- Goal: add enough low-risk entries for adjacent symbol sets without damaging weak windows.

| candidate | all5_pass | symbol_sets | trades | PF | drawdown | sharpe | calmar | WF | failing_sets |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| base | False | 0/2 | 103 | 1.50 | 0.93% | 1.13 | 1.36 | 1/3 | no_SC, core_AP_A_ZN |
| 3buy_0h | False | 0/2 | 106 | 1.42 | 1.07% | 1.05 | 1.08 | 1/3 | no_SC, core_AP_A_ZN |

## Symbol-Set Detail

### base

| set | pass | trades | PF | sharpe | calmar | WF | failing_checks |
|---|---|---:|---:|---:|---:|---:|---|
| no_SC | False | 56 | 2.53 | 1.61 | 2.73 | 0/3 | trades_ge_scaled_min, walk_forward_ge_2_3 |
| core_AP_A_ZN | False | 42 | 2.71 | 1.55 | 2.54 | 0/3 | trades_ge_scaled_min, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

### 3buy_0h

| set | pass | trades | PF | sharpe | calmar | WF | failing_checks |
|---|---|---:|---:|---:|---:|---:|---|
| no_SC | False | 56 | 2.53 | 1.61 | 2.73 | 0/3 | trades_ge_scaled_min, walk_forward_ge_2_3 |
| core_AP_A_ZN | False | 42 | 2.71 | 1.55 | 2.54 | 0/3 | trades_ge_scaled_min, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
