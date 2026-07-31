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


- scenario: `expanded_short_sc`
- symbols: `AP888, RB888, SC888, A888, ZN888`
- portfolio: five-symbol equal weight
- costs: strategy engine commission/slippage are included

## Out-Of-Sample Gate

| metric | strategy | target / benchmark | pass |
|---|---:|---:|---|
| trades | 114 | >= 100 | True |
| profit_factor | 1.51 | >= 1.20 | True |
| max_drawdown | 0.93% | <= 20.00% | True |
| sharpe | 1.21 | >= 0.50 | True |
| calmar | 1.48 | >= 0.50 | True |
| walk_forward_positive_ratio | 55.56% | >= 66.67% | False |
| risk_adjusted_vs_buy_hold | sharpe 1.21 / calmar 1.48 | bh sharpe 0.88 / bh calmar 1.35 | True |

**HISTORICAL GATE RESULT: `False` (DECLASSIFIED; NOT PROMOTION EVIDENCE)**

## Full Sample

| return | drawdown | sharpe | calmar | trades | PF |
|---:|---:|---:|---:|---:|---:|
| -0.10% | 2.11% | -0.01 | -0.01 | 455 | 0.96 |

## Walk Forward

| window | return | drawdown | sharpe | calmar | trades | PF |
|---|---:|---:|---:|---:|---:|---:|
| 2022H1 | -0.57% | 0.82% | -0.99 | -1.44 | 66 | 0.72 |
| 2022H2 | 0.36% | 0.66% | 0.87 | 1.03 | 68 | 1.20 |
| 2023H1 | -1.35% | 1.49% | -4.00 | -1.83 | 50 | 0.30 |
| 2023H2 | -0.06% | 0.43% | -0.16 | -0.26 | 41 | 0.96 |
| 2024H1 | 0.48% | 0.37% | 1.22 | 2.62 | 44 | 1.25 |
| 2024H2 | 0.26% | 0.61% | 0.46 | 0.80 | 47 | 1.10 |
| 2025H1 | 0.40% | 0.59% | 0.90 | 1.39 | 37 | 1.15 |
| 2025H2 | 1.64% | 0.26% | 2.61 | 11.86 | 52 | 3.05 |
| 2026YTD | -0.16% | 0.74% | -0.56 | -1.57 | 24 | 0.53 |