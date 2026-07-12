# Platform Trailing Candidates

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
- Goal: protect weak adjacent symbol sets without shortening every profitable long hold.

| candidate | all5_pass | symbol_sets | trades | PF | drawdown | sharpe | calmar | WF | failing_sets |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| base | False | 0/3 | 103 | 1.50 | 0.93% | 1.13 | 1.36 | 1/2 | no_SC, core_AP_A_ZN, no_A |
| ap_a_zn_tight_150_015 | False | 0/3 | 107 | 1.29 | 0.86% | 0.56 | 0.62 | 1/2 | no_SC, core_AP_A_ZN, no_A |
| ap_a_zn_mid_200_020 | True | 0/3 | 105 | 1.64 | 0.86% | 1.19 | 1.40 | 2/2 | no_SC, core_AP_A_ZN, no_A |

## Symbol-Set Detail

### base

- overrides: `{}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| no_SC | False | 56/80 | 2.53 | 0.69% | 1.61 | 2.73 | 1/2 | 1.15 | 2.09 | trades_ge_scaled_min, walk_forward_ge_2_3 |
| core_AP_A_ZN | False | 42/60 | 2.71 | 0.93% | 1.55 | 2.54 | 1/2 | 1.40 | 2.93 | trades_ge_scaled_min, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
| no_A | False | 87/80 | 1.42 | 1.12% | 0.77 | 0.83 | 1/2 | 0.62 | 0.78 | walk_forward_ge_2_3 |

### ap_a_zn_tight_150_015

- overrides: `{"AP888": {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15}, "A888": {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15}, "ZN888": {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15}}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| no_SC | False | 60/80 | 2.29 | 0.62% | 1.05 | 1.58 | 1/2 | 1.15 | 2.09 | trades_ge_scaled_min, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
| core_AP_A_ZN | False | 46/60 | 2.49 | 0.79% | 0.97 | 1.46 | 1/2 | 1.40 | 2.93 | trades_ge_scaled_min, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
| no_A | False | 88/80 | 1.08 | 1.13% | 0.15 | 0.15 | 1/2 | 0.62 | 0.78 | pf_ge_1_2, sharpe_ge_0_5, calmar_ge_0_5, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

### ap_a_zn_mid_200_020

- overrides: `{"AP888": {"trailing_start_bp": 200, "trailing_drawback_pct": 0.2}, "A888": {"trailing_start_bp": 200, "trailing_drawback_pct": 0.2}, "ZN888": {"trailing_start_bp": 200, "trailing_drawback_pct": 0.2}}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| no_SC | False | 58/80 | 3.42 | 0.43% | 1.83 | 4.21 | 2/2 | 1.15 | 2.09 | trades_ge_scaled_min |
| core_AP_A_ZN | False | 44/60 | 3.97 | 0.57% | 1.79 | 3.92 | 2/2 | 1.40 | 2.93 | trades_ge_scaled_min |
| no_A | False | 87/80 | 1.28 | 1.12% | 0.55 | 0.56 | 2/2 | 0.62 | 0.78 | risk_adjusted_gt_buy_hold |
