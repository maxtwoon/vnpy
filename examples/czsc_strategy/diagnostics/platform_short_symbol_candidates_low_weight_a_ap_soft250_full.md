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
| sc075_a_zn010 | True | 3/6 | 128 | 1.76 | 0.88% | 1.37 | 1.67 | 7/9 | no_RB, no_A, no_ZN |

## Symbol-Set Detail

### sc075_a_zn010

- params: `{"enable_short_symbols": ["SC888", "A888", "ZN888"], "sell_multiplier": 0.75, "symbol_position_overrides": {"A888": {"pos_1sell": 0.01, "pos_2sell": 0.02, "pos_3sell": 0.03}, "ZN888": {"pos_1sell": 0.01, "pos_2sell": 0.02, "pos_3sell": 0.03}}}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | True | 128/100 | 1.76 | 0.88% | 1.37 | 1.67 | 7/9 | 0.88 | 1.35 | - |
| no_RB | False | 114/80 | 1.77 | 1.07% | 1.32 | 1.59 | 7/9 | 0.99 | 1.68 | risk_adjusted_gt_buy_hold |
| no_SC | True | 81/80 | 3.62 | 0.50% | 1.96 | 4.30 | 7/9 | 1.15 | 2.09 | - |
| core_AP_A_ZN | True | 67/60 | 4.16 | 0.66% | 1.92 | 4.05 | 7/9 | 1.40 | 2.93 | - |
| no_A | False | 102/80 | 1.35 | 1.12% | 0.66 | 0.71 | 6/9 | 0.62 | 0.78 | risk_adjusted_gt_buy_hold |
| no_ZN | False | 99/80 | 1.76 | 1.06% | 1.45 | 1.50 | 5/9 | 0.98 | 1.63 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
