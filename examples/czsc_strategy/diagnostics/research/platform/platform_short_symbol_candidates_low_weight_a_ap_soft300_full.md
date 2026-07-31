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
| sc075_a_zn010 | False | 1/6 | 128 | 1.54 | 0.88% | 1.06 | 1.34 | 7/9 | all5, no_RB, core_AP_A_ZN, no_A, no_ZN |

## Symbol-Set Detail

### sc075_a_zn010

- params: `{"enable_short_symbols": ["SC888", "A888", "ZN888"], "sell_multiplier": 0.75, "symbol_position_overrides": {"A888": {"pos_1sell": 0.01, "pos_2sell": 0.02, "pos_3sell": 0.03}, "ZN888": {"pos_1sell": 0.01, "pos_2sell": 0.02, "pos_3sell": 0.03}}}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | False | 128/100 | 1.54 | 0.88% | 1.06 | 1.34 | 7/9 | 0.88 | 1.35 | risk_adjusted_gt_buy_hold |
| no_RB | False | 114/80 | 1.54 | 1.08% | 1.00 | 1.25 | 7/9 | 0.99 | 1.68 | risk_adjusted_gt_buy_hold |
| no_SC | True | 81/80 | 2.57 | 0.78% | 1.52 | 2.29 | 6/9 | 1.15 | 2.09 | - |
| core_AP_A_ZN | False | 67/60 | 2.74 | 1.05% | 1.47 | 2.12 | 6/9 | 1.40 | 2.93 | risk_adjusted_gt_buy_hold |
| no_A | False | 102/80 | 1.36 | 1.12% | 0.67 | 0.72 | 6/9 | 0.62 | 0.78 | risk_adjusted_gt_buy_hold |
| no_ZN | False | 99/80 | 1.51 | 1.07% | 1.06 | 1.16 | 5/9 | 0.98 | 1.63 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
