# Platform Short Symbol Candidates

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


- base long gate: `block_1buy_daily_down`
- Goal: test whether low-weight AP/A/ZN shorts can supply robust core/no_SC trades.

| candidate | all5_pass | symbol_sets | trades | PF | drawdown | sharpe | calmar | WF | failing_sets |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| base_sc_075 | True | 1/6 | 105 | 1.64 | 0.86% | 1.19 | 1.40 | 2/2 | no_SC, core_AP_A_ZN, no_A, no_RB, no_ZN |
| a_short_025 | False | 0/6 | 89 | 1.44 | 0.97% | 0.73 | 0.76 | 2/2 | all5, no_SC, core_AP_A_ZN, no_A, no_RB, no_ZN |
| ap_a_short_025 | False | 0/6 | 99 | 1.37 | 0.97% | 0.66 | 0.67 | 2/2 | all5, no_SC, core_AP_A_ZN, no_A, no_RB, no_ZN |
| a_zn_short_025 | False | 1/6 | 106 | 1.41 | 0.97% | 0.72 | 0.75 | 2/2 | all5, core_AP_A_ZN, no_A, no_RB, no_ZN |
| ap_zn_short_025 | False | 2/6 | 107 | 1.35 | 0.97% | 0.65 | 0.67 | 2/2 | all5, no_A, no_RB, no_ZN |
| ap_a_zn_short_025 | False | 1/6 | 116 | 1.34 | 0.97% | 0.64 | 0.66 | 2/2 | all5, core_AP_A_ZN, no_A, no_RB, no_ZN |

## Symbol-Set Detail

### base_sc_075

- params: `{"enable_short_symbols": ["SC888"], "sell_multiplier": 0.75}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | True | 105/100 | 1.64 | 0.86% | 1.19 | 1.40 | 2/2 | 0.88 | 1.35 | - |
| no_SC | False | 58/80 | 3.42 | 0.43% | 1.83 | 4.21 | 2/2 | 1.15 | 2.09 | trades_ge_scaled_min |
| core_AP_A_ZN | False | 44/60 | 3.97 | 0.57% | 1.79 | 3.92 | 2/2 | 1.40 | 2.93 | trades_ge_scaled_min |
| no_A | False | 87/80 | 1.28 | 1.12% | 0.55 | 0.56 | 2/2 | 0.62 | 0.78 | risk_adjusted_gt_buy_hold |
| no_RB | False | 91/80 | 1.64 | 1.05% | 1.13 | 1.30 | 2/2 | 0.99 | 1.68 | risk_adjusted_gt_buy_hold |
| no_ZN | False | 91/80 | 1.65 | 1.06% | 1.29 | 1.26 | 1/2 | 0.98 | 1.63 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

### a_short_025

- params: `{"enable_short_symbols": ["A888"], "sell_multiplier": 0.25}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | False | 89/100 | 1.44 | 0.97% | 0.73 | 0.76 | 2/2 | 0.88 | 1.35 | trades_ge_scaled_min, risk_adjusted_gt_buy_hold |
| no_SC | False | 67/80 | 3.30 | 0.41% | 1.82 | 4.39 | 2/2 | 1.15 | 2.09 | trades_ge_scaled_min |
| core_AP_A_ZN | False | 53/60 | 3.79 | 0.54% | 1.78 | 4.09 | 1/2 | 1.40 | 2.93 | trades_ge_scaled_min, walk_forward_ge_2_3 |
| no_A | False | 62/80 | 1.03 | 1.27% | 0.07 | 0.06 | 2/2 | 0.62 | 0.78 | trades_ge_scaled_min, pf_ge_1_2, sharpe_ge_0_5, calmar_ge_0_5, risk_adjusted_gt_buy_hold |
| no_RB | False | 75/80 | 1.42 | 1.20% | 0.66 | 0.67 | 2/2 | 0.99 | 1.68 | trades_ge_scaled_min, risk_adjusted_gt_buy_hold |
| no_ZN | False | 75/80 | 1.42 | 1.21% | 0.73 | 0.64 | 1/2 | 0.98 | 1.63 | trades_ge_scaled_min, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

### ap_a_short_025

- params: `{"enable_short_symbols": ["AP888", "A888"], "sell_multiplier": 0.25}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | False | 99/100 | 1.37 | 0.97% | 0.66 | 0.67 | 2/2 | 0.88 | 1.35 | trades_ge_scaled_min, risk_adjusted_gt_buy_hold |
| no_SC | False | 77/80 | 2.87 | 0.43% | 1.75 | 3.92 | 2/2 | 1.15 | 2.09 | trades_ge_scaled_min |
| core_AP_A_ZN | False | 63/60 | 3.17 | 0.57% | 1.71 | 3.63 | 1/2 | 1.40 | 2.93 | walk_forward_ge_2_3 |
| no_A | False | 72/80 | 0.98 | 1.27% | -0.02 | -0.02 | 2/2 | 0.62 | 0.78 | trades_ge_scaled_min, pf_ge_1_2, sharpe_ge_0_5, calmar_ge_0_5, risk_adjusted_gt_buy_hold |
| no_RB | False | 85/80 | 1.35 | 1.20% | 0.58 | 0.58 | 2/2 | 0.99 | 1.68 | risk_adjusted_gt_buy_hold |
| no_ZN | False | 85/80 | 1.34 | 1.21% | 0.63 | 0.55 | 1/2 | 0.98 | 1.63 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

### a_zn_short_025

- params: `{"enable_short_symbols": ["A888", "ZN888"], "sell_multiplier": 0.25}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | False | 106/100 | 1.41 | 0.97% | 0.72 | 0.75 | 2/2 | 0.88 | 1.35 | risk_adjusted_gt_buy_hold |
| no_SC | True | 84/80 | 3.01 | 0.39% | 1.81 | 4.58 | 2/2 | 1.15 | 2.09 | - |
| core_AP_A_ZN | False | 70/60 | 3.35 | 0.51% | 1.77 | 4.30 | 1/2 | 1.40 | 2.93 | walk_forward_ge_2_3 |
| no_A | False | 79/80 | 1.02 | 1.27% | 0.06 | 0.05 | 2/2 | 0.62 | 0.78 | trades_ge_scaled_min, pf_ge_1_2, sharpe_ge_0_5, calmar_ge_0_5, risk_adjusted_gt_buy_hold |
| no_RB | False | 92/80 | 1.39 | 1.20% | 0.64 | 0.65 | 2/2 | 0.99 | 1.68 | risk_adjusted_gt_buy_hold |
| no_ZN | False | 75/80 | 1.42 | 1.21% | 0.73 | 0.64 | 1/2 | 0.98 | 1.63 | trades_ge_scaled_min, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

### ap_zn_short_025

- params: `{"enable_short_symbols": ["AP888", "ZN888"], "sell_multiplier": 0.25}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | False | 107/100 | 1.35 | 0.97% | 0.65 | 0.67 | 2/2 | 0.88 | 1.35 | risk_adjusted_gt_buy_hold |
| no_SC | True | 85/80 | 2.73 | 0.42% | 1.74 | 4.04 | 2/2 | 1.15 | 2.09 | - |
| core_AP_A_ZN | True | 71/60 | 2.97 | 0.56% | 1.70 | 3.74 | 2/2 | 1.40 | 2.93 | - |
| no_A | False | 89/80 | 0.97 | 1.27% | -0.03 | -0.04 | 2/2 | 0.62 | 0.78 | pf_ge_1_2, sharpe_ge_0_5, calmar_ge_0_5, risk_adjusted_gt_buy_hold |
| no_RB | False | 93/80 | 1.33 | 1.20% | 0.57 | 0.58 | 2/2 | 0.99 | 1.68 | risk_adjusted_gt_buy_hold |
| no_ZN | False | 76/80 | 1.35 | 1.21% | 0.64 | 0.56 | 1/2 | 0.98 | 1.63 | trades_ge_scaled_min, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

### ap_a_zn_short_025

- params: `{"enable_short_symbols": ["AP888", "A888", "ZN888"], "sell_multiplier": 0.25}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | False | 116/100 | 1.34 | 0.97% | 0.64 | 0.66 | 2/2 | 0.88 | 1.35 | risk_adjusted_gt_buy_hold |
| no_SC | True | 94/80 | 2.66 | 0.40% | 1.73 | 4.19 | 2/2 | 1.15 | 2.09 | - |
| core_AP_A_ZN | False | 80/60 | 2.88 | 0.53% | 1.69 | 3.91 | 1/2 | 1.40 | 2.93 | walk_forward_ge_2_3 |
| no_A | False | 89/80 | 0.97 | 1.27% | -0.03 | -0.04 | 2/2 | 0.62 | 0.78 | pf_ge_1_2, sharpe_ge_0_5, calmar_ge_0_5, risk_adjusted_gt_buy_hold |
| no_RB | False | 102/80 | 1.32 | 1.20% | 0.56 | 0.57 | 2/2 | 0.99 | 1.68 | risk_adjusted_gt_buy_hold |
| no_ZN | False | 85/80 | 1.34 | 1.21% | 0.63 | 0.55 | 1/2 | 0.98 | 1.63 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
