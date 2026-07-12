# Portfolio Goal Evaluation

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> This report was produced using the historical out-of-sample window `2022-01-01~2026-04-24`, which was repeatedly used for parameter selection. High-precision weights such as `0.847` and any `GOAL PASSED` rows are gate-fitting signatures, not evidence of a robust trading discovery. This artifact is retained as negative / contaminated evidence only.
>
> - `is_promotion_evidence`: False
> - `research_only`: True
> - `used_data_windows`: `["2022-01-01~2026-04-24"]`
> - `decision_data_windows`: ['2026-04-24~present', 'SimNow observation']
> - `note`: Future validation must use post-2026-04-24 incremental data and SimNow observation before any promotion claim can be considered.


- scenario: `expanded_short_sc_085`
- symbols: `AP888, RB888, SC888, A888, ZN888`
- portfolio: five-symbol equal weight
- costs: strategy engine commission/slippage are included

## Out-Of-Sample Gate

| metric | strategy | target / benchmark | pass |
|---|---:|---:|---|
| trades | 114 | >= 100 | True |
| profit_factor | 1.48 | >= 1.20 | True |
| max_drawdown | 0.95% | <= 20.00% | True |
| sharpe | 1.14 | >= 0.50 | True |
| calmar | 1.35 | >= 0.50 | True |
| walk_forward_positive_ratio | 55.56% | >= 66.67% | False |
| risk_adjusted_vs_buy_hold | sharpe 1.14 / calmar 1.35 | bh sharpe 0.88 / bh calmar 1.35 | True |

**HISTORICAL GATE RESULT: `False` (DECLASSIFIED; NOT PROMOTION EVIDENCE)**

## Full Sample

| return | drawdown | sharpe | calmar | trades | PF |
|---:|---:|---:|---:|---:|---:|
| -0.07% | 2.03% | -0.01 | -0.01 | 455 | 0.96 |

## Walk Forward

| window | return | drawdown | sharpe | calmar | trades | PF |
|---|---:|---:|---:|---:|---:|---:|
| 2022H1 | -0.53% | 0.80% | -0.92 | -1.35 | 66 | 0.73 |
| 2022H2 | 0.38% | 0.64% | 0.93 | 1.13 | 68 | 1.22 |
| 2023H1 | -1.34% | 1.48% | -3.99 | -1.83 | 50 | 0.29 |
| 2023H2 | -0.00% | 0.41% | -0.00 | -0.01 | 41 | 1.02 |
| 2024H1 | 0.47% | 0.37% | 1.21 | 2.58 | 44 | 1.25 |
| 2024H2 | 0.29% | 0.58% | 0.51 | 0.94 | 47 | 1.12 |
| 2025H1 | 0.35% | 0.55% | 0.82 | 1.29 | 37 | 1.13 |
| 2025H2 | 1.61% | 0.26% | 2.56 | 11.63 | 52 | 3.09 |
| 2026YTD | -0.20% | 0.76% | -0.70 | -1.86 | 24 | 0.50 |