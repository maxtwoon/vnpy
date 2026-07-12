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
| sc025_a_zn010_sc3buy_half | True | 6/6 | 128 | 2.04 | 0.44% | 1.59 | 3.32 | 7/9 | - |

## Symbol-Set Detail

### sc025_a_zn010_sc3buy_half

- params: `{"enable_short_symbols": ["SC888", "A888", "ZN888"], "sell_multiplier": 0.25, "symbol_position_overrides": {"A888": {"pos_1sell": 0.01, "pos_2sell": 0.02, "pos_3sell": 0.03}, "ZN888": {"pos_1sell": 0.01, "pos_2sell": 0.02, "pos_3sell": 0.03}, "SC888": {"pos_3buy": 0.15}}}`

| set | pass | trades/min | PF | drawdown | sharpe | calmar | WF | bh_sharpe | bh_calmar | failing_checks |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| all5 | True | 128/100 | 2.04 | 0.44% | 1.59 | 3.32 | 7/9 | 0.88 | 1.35 | - |
| no_RB | True | 114/80 | 2.09 | 0.54% | 1.54 | 3.19 | 7/9 | 0.99 | 1.68 | - |
| no_SC | True | 81/80 | 3.62 | 0.50% | 1.96 | 4.30 | 7/9 | 1.15 | 2.09 | - |
| core_AP_A_ZN | True | 67/60 | 4.16 | 0.66% | 1.92 | 4.05 | 7/9 | 1.40 | 2.93 | - |
| no_A | True | 102/80 | 1.49 | 0.59% | 0.79 | 1.35 | 6/9 | 0.62 | 0.78 | - |
| no_ZN | True | 99/80 | 2.11 | 0.52% | 1.82 | 3.05 | 6/9 | 0.98 | 1.63 | - |
