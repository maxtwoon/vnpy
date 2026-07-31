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


- scenario: `expanded`
- symbols: `AP888, RB888, SC888, A888, ZN888`
- portfolio: five-symbol equal weight
- costs: strategy engine commission/slippage are included

## Out-Of-Sample Gate

| metric | strategy | target / benchmark | pass |
|---|---:|---:|---|
| trades | 89 | >= 100 | False |
| profit_factor | 1.28 | >= 1.20 | True |
| max_drawdown | 1.08% | <= 20.00% | True |
| sharpe | 0.69 | >= 0.50 | True |
| calmar | 0.72 | >= 0.50 | True |
| walk_forward_positive_ratio | 66.67% | >= 66.67% | True |
| risk_adjusted_vs_buy_hold | sharpe 0.69 / calmar 0.72 | bh sharpe 0.88 / bh calmar 1.35 | False |

**HISTORICAL GATE RESULT: `False` (DECLASSIFIED; NOT PROMOTION EVIDENCE)**

## Full Sample

| return | drawdown | sharpe | calmar | trades | PF |
|---:|---:|---:|---:|---:|---:|
| 0.30% | 1.50% | 0.07 | 0.04 | 347 | 0.99 |

## Walk Forward

| window | return | drawdown | sharpe | calmar | trades | PF |
|---|---:|---:|---:|---:|---:|---:|
| 2022H1 | -0.17% | 0.62% | -0.31 | -0.58 | 47 | 0.89 |
| 2022H2 | 0.60% | 0.53% | 1.45 | 2.15 | 52 | 1.47 |
| 2023H1 | -1.28% | 1.41% | -3.75 | -1.84 | 37 | 0.24 |
| 2023H2 | 0.33% | 0.30% | 1.21 | 2.12 | 30 | 1.72 |
| 2024H1 | 0.43% | 0.37% | 1.10 | 2.33 | 35 | 1.21 |
| 2024H2 | 0.46% | 0.56% | 0.81 | 1.53 | 40 | 1.25 |
| 2025H1 | 0.02% | 0.31% | 0.07 | 0.14 | 28 | 0.99 |
| 2025H2 | 1.43% | 0.30% | 2.25 | 8.98 | 38 | 3.37 |
| 2026YTD | -0.39% | 0.85% | -1.62 | -3.29 | 17 | 0.28 |