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
| sc075_a_zn025 | False | 2/6 | 131 | 1.68 | 0.85% | 1.31 | 1.57 | 5/9 | all5, no_RB, no_A, no_ZN |

## Symbol-Set Detail

### sc075_a_zn025

- params: `{"enable_short_symbols": ["SC888", "A888", "ZN888"], "sell_multiplier": 0.75, "symbol_position_overrides": {"A888": {"pos_1sell": 0.025, "pos_2sell": 0.05, "pos_3sell": 0.075}, "ZN888": {"pos_1sell": 0.025, "pos_2sell": 0.05, "pos_3sell": 0.075}}}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | False | 131/100 | 1.68 | 0.85% | 1.31 | 1.57 | 5/9 | 0.88 | 1.35 | walk_forward_ge_2_3 |
| no_RB | False | 117/80 | 1.68 | 1.04% | 1.25 | 1.48 | 5/9 | 0.99 | 1.68 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
| no_SC | True | 84/80 | 3.25 | 0.48% | 1.95 | 4.18 | 7/9 | 1.15 | 2.09 | - |
| core_AP_A_ZN | True | 70/60 | 3.65 | 0.63% | 1.91 | 3.92 | 7/9 | 1.40 | 2.93 | - |
| no_A | False | 104/80 | 1.35 | 1.12% | 0.70 | 0.74 | 6/9 | 0.62 | 0.78 | risk_adjusted_gt_buy_hold |
| no_ZN | False | 100/80 | 1.74 | 1.06% | 1.43 | 1.45 | 5/9 | 0.98 | 1.63 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
