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
| sc075_a_zn025 | False | 2/6 | 127 | 1.46 | 0.93% | 1.10 | 1.32 | 7/9 | all5, no_RB, core_AP_A_ZN, no_ZN |

## Symbol-Set Detail

### sc075_a_zn025

- params: `{"enable_short_symbols": ["SC888", "A888", "ZN888"], "sell_multiplier": 0.75, "symbol_position_overrides": {"A888": {"pos_1sell": 0.025, "pos_2sell": 0.05, "pos_3sell": 0.075}, "ZN888": {"pos_1sell": 0.025, "pos_2sell": 0.05, "pos_3sell": 0.075}}}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | False | 127/100 | 1.46 | 0.93% | 1.10 | 1.32 | 7/9 | 0.88 | 1.35 | risk_adjusted_gt_buy_hold |
| no_RB | False | 113/80 | 1.45 | 1.14% | 1.04 | 1.23 | 5/9 | 0.99 | 1.68 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
| no_SC | True | 80/80 | 2.31 | 0.68% | 1.58 | 2.70 | 6/9 | 1.15 | 2.09 | - |
| core_AP_A_ZN | False | 66/60 | 2.42 | 0.91% | 1.52 | 2.51 | 6/9 | 1.40 | 2.93 | risk_adjusted_gt_buy_hold |
| no_A | True | 102/80 | 1.39 | 1.11% | 0.75 | 0.82 | 6/9 | 0.62 | 0.78 | - |
| no_ZN | False | 98/80 | 1.44 | 1.16% | 1.12 | 1.12 | 5/9 | 0.98 | 1.63 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
