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


- scenario: `expanded_short`
- symbols: `AP888, RB888, SC888, A888, ZN888`
- portfolio: five-symbol equal weight
- costs: strategy engine commission/slippage are included

## Out-Of-Sample Gate

| metric | strategy | target / benchmark | pass |
|---|---:|---:|---|
| trades | 160 | >= 100 | True |
| profit_factor | 1.16 | >= 1.20 | False |
| max_drawdown | 0.97% | <= 20.00% | True |
| sharpe | 0.60 | >= 0.50 | True |
| calmar | 0.68 | >= 0.50 | True |
| walk_forward_positive_ratio | 66.67% | >= 66.67% | True |
| risk_adjusted_vs_buy_hold | sharpe 0.60 / calmar 0.68 | bh sharpe 0.88 / bh calmar 1.35 | False |

**HISTORICAL GATE RESULT: `False` (DECLASSIFIED; NOT PROMOTION EVIDENCE)**

## Full Sample

| return | drawdown | sharpe | calmar | trades | PF |
|---:|---:|---:|---:|---:|---:|
| 0.76% | 2.03% | 0.15 | 0.08 | 674 | 1.02 |

## Walk Forward

| window | return | drawdown | sharpe | calmar | trades | PF |
|---|---:|---:|---:|---:|---:|---:|
| 2022H1 | -0.15% | 0.57% | -0.29 | -0.56 | 100 | 0.90 |
| 2022H2 | 0.62% | 0.71% | 1.16 | 1.66 | 106 | 1.19 |
| 2023H1 | -1.25% | 1.29% | -3.03 | -1.95 | 68 | 0.50 |
| 2023H2 | 0.01% | 0.67% | 0.03 | 0.03 | 74 | 1.04 |
| 2024H1 | 1.41% | 0.36% | 3.09 | 8.00 | 57 | 1.78 |
| 2024H2 | 0.36% | 0.91% | 0.60 | 0.74 | 74 | 1.10 |
| 2025H1 | 0.75% | 0.65% | 1.51 | 2.37 | 51 | 1.36 |
| 2025H2 | 1.00% | 0.43% | 1.78 | 4.27 | 78 | 1.32 |
| 2026YTD | -0.65% | 0.97% | -2.23 | -4.71 | 33 | 0.41 |