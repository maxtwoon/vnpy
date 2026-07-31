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
| base | False | 0/3 | 103 | 1.50 | 0.93% | 1.13 | 1.36 | 1/2 | all5, no_RB, no_ZN |
| ap_a_zn_mid_200_020 | True | 1/3 | 105 | 1.64 | 0.86% | 1.19 | 1.40 | 2/2 | no_RB, no_ZN |

## Symbol-Set Detail

### base

- overrides: `{}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | False | 103/100 | 1.50 | 0.93% | 1.13 | 1.36 | 1/2 | 0.88 | 1.35 | walk_forward_ge_2_3 |
| no_RB | False | 89/80 | 1.49 | 1.15% | 1.08 | 1.27 | 1/2 | 0.99 | 1.68 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
| no_ZN | False | 89/80 | 1.46 | 1.16% | 1.14 | 1.15 | 0/2 | 0.98 | 1.63 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

### ap_a_zn_mid_200_020

- overrides: `{"AP888": {"trailing_start_bp": 200, "trailing_drawback_pct": 0.2}, "A888": {"trailing_start_bp": 200, "trailing_drawback_pct": 0.2}, "ZN888": {"trailing_start_bp": 200, "trailing_drawback_pct": 0.2}}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | True | 105/100 | 1.64 | 0.86% | 1.19 | 1.40 | 2/2 | 0.88 | 1.35 | - |
| no_RB | False | 91/80 | 1.64 | 1.05% | 1.13 | 1.30 | 2/2 | 0.99 | 1.68 | risk_adjusted_gt_buy_hold |
| no_ZN | False | 91/80 | 1.65 | 1.06% | 1.29 | 1.26 | 1/2 | 0.98 | 1.63 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
