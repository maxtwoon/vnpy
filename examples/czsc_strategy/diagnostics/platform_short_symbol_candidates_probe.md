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
| base_sc_075 | True | 1/4 | 105 | 1.64 | 0.86% | 1.19 | 1.40 | 2/2 | no_SC, core_AP_A_ZN, no_A |
| ap_a_zn_short_025 | False | 1/4 | 116 | 1.34 | 0.97% | 0.64 | 0.66 | 2/2 | all5, core_AP_A_ZN, no_A |
| ap_a_zn_sc_short_025 | False | 1/4 | 141 | 1.41 | 0.93% | 0.80 | 0.85 | 2/2 | all5, core_AP_A_ZN, no_A |
| ap_a_zn_sc_short_050 | False | 0/4 | 141 | 1.38 | 0.89% | 0.85 | 0.93 | 2/2 | all5, no_SC, core_AP_A_ZN, no_A |

## Symbol-Set Detail

### base_sc_075

- params: `{"enable_short_symbols": ["SC888"], "sell_multiplier": 0.75}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | True | 105/100 | 1.64 | 0.86% | 1.19 | 1.40 | 2/2 | 0.88 | 1.35 | - |
| no_SC | False | 58/80 | 3.42 | 0.43% | 1.83 | 4.21 | 2/2 | 1.15 | 2.09 | trades_ge_scaled_min |
| core_AP_A_ZN | False | 44/60 | 3.97 | 0.57% | 1.79 | 3.92 | 2/2 | 1.40 | 2.93 | trades_ge_scaled_min |
| no_A | False | 87/80 | 1.28 | 1.12% | 0.55 | 0.56 | 2/2 | 0.62 | 0.78 | risk_adjusted_gt_buy_hold |

### ap_a_zn_short_025

- params: `{"enable_short_symbols": ["AP888", "A888", "ZN888"], "sell_multiplier": 0.25}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | False | 116/100 | 1.34 | 0.97% | 0.64 | 0.66 | 2/2 | 0.88 | 1.35 | risk_adjusted_gt_buy_hold |
| no_SC | True | 94/80 | 2.66 | 0.40% | 1.73 | 4.19 | 2/2 | 1.15 | 2.09 | - |
| core_AP_A_ZN | False | 80/60 | 2.88 | 0.53% | 1.69 | 3.91 | 1/2 | 1.40 | 2.93 | walk_forward_ge_2_3 |
| no_A | False | 89/80 | 0.97 | 1.27% | -0.03 | -0.04 | 2/2 | 0.62 | 0.78 | pf_ge_1_2, sharpe_ge_0_5, calmar_ge_0_5, risk_adjusted_gt_buy_hold |

### ap_a_zn_sc_short_025

- params: `{"enable_short_symbols": ["AP888", "A888", "ZN888", "SC888"], "sell_multiplier": 0.25}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | False | 141/100 | 1.41 | 0.93% | 0.80 | 0.85 | 2/2 | 0.88 | 1.35 | risk_adjusted_gt_buy_hold |
| no_SC | True | 94/80 | 2.66 | 0.40% | 1.73 | 4.19 | 2/2 | 1.15 | 2.09 | - |
| core_AP_A_ZN | False | 80/60 | 2.88 | 0.53% | 1.69 | 3.91 | 1/2 | 1.40 | 2.93 | walk_forward_ge_2_3 |
| no_A | False | 114/80 | 1.06 | 1.22% | 0.13 | 0.11 | 2/2 | 0.62 | 0.78 | pf_ge_1_2, sharpe_ge_0_5, calmar_ge_0_5, risk_adjusted_gt_buy_hold |

### ap_a_zn_sc_short_050

- params: `{"enable_short_symbols": ["AP888", "A888", "ZN888", "SC888"], "sell_multiplier": 0.5}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | False | 141/100 | 1.38 | 0.89% | 0.85 | 0.93 | 2/2 | 0.88 | 1.35 | risk_adjusted_gt_buy_hold |
| no_SC | False | 94/80 | 2.21 | 0.42% | 1.61 | 3.67 | 1/2 | 1.15 | 2.09 | walk_forward_ge_2_3 |
| core_AP_A_ZN | False | 80/60 | 2.31 | 0.55% | 1.57 | 3.41 | 1/2 | 1.40 | 2.93 | walk_forward_ge_2_3 |
| no_A | False | 114/80 | 1.08 | 1.17% | 0.18 | 0.17 | 2/2 | 0.62 | 0.78 | pf_ge_1_2, sharpe_ge_0_5, calmar_ge_0_5, risk_adjusted_gt_buy_hold |
