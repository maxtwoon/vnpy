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


- scenario: `expanded_short_rb_sc`
- symbols: `AP888, RB888, SC888, A888, ZN888`
- portfolio: five-symbol equal weight
- costs: strategy engine commission/slippage are included

## Out-Of-Sample Gate

| metric | strategy | target / benchmark | pass |
|---|---:|---:|---|
| trades | 126 | >= 100 | True |
| profit_factor | 1.43 | >= 1.20 | True |
| max_drawdown | 0.97% | <= 20.00% | True |
| sharpe | 1.11 | >= 0.50 | True |
| calmar | 1.25 | >= 0.50 | True |
| walk_forward_positive_ratio | 55.56% | >= 66.67% | False |
| risk_adjusted_vs_buy_hold | sharpe 1.11 / calmar 1.25 | bh sharpe 0.88 / bh calmar 1.35 | False |

**HISTORICAL GATE RESULT: `False` (DECLASSIFIED; NOT PROMOTION EVIDENCE)**

## Full Sample

| return | drawdown | sharpe | calmar | trades | PF |
|---:|---:|---:|---:|---:|---:|
| 0.50% | 2.14% | 0.11 | 0.05 | 523 | 1.01 |

## Walk Forward

| window | return | drawdown | sharpe | calmar | trades | PF |
|---|---:|---:|---:|---:|---:|---:|
| 2022H1 | -0.30% | 0.52% | -0.55 | -1.19 | 78 | 0.84 |
| 2022H2 | 0.56% | 0.75% | 1.27 | 1.42 | 80 | 1.27 |
| 2023H1 | -1.63% | 1.72% | -4.65 | -1.91 | 56 | 0.29 |
| 2023H2 | -0.06% | 0.48% | -0.15 | -0.24 | 54 | 0.97 |
| 2024H1 | 0.72% | 0.42% | 1.79 | 3.55 | 49 | 1.45 |
| 2024H2 | 0.37% | 0.55% | 0.65 | 1.27 | 54 | 1.16 |
| 2025H1 | 0.48% | 0.59% | 1.07 | 1.66 | 39 | 1.22 |
| 2025H2 | 1.54% | 0.36% | 2.65 | 7.87 | 60 | 2.21 |
| 2026YTD | -0.28% | 0.74% | -0.98 | -2.67 | 26 | 0.51 |