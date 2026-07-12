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


- scenario: `trailing_overrides`
- symbols: `AP888, RB888, SC888, A888, ZN888`
- portfolio: five-symbol equal weight
- costs: strategy engine commission/slippage are included

## Out-Of-Sample Gate

| metric | strategy | target / benchmark | pass |
|---|---:|---:|---|
| trades | 98 | >= 100 | False |
| profit_factor | 1.01 | >= 1.20 | False |
| max_drawdown | 1.85% | <= 20.00% | True |
| sharpe | 0.18 | >= 0.50 | False |
| calmar | 0.13 | >= 0.50 | False |
| walk_forward_positive_ratio | 66.67% | >= 66.67% | True |
| risk_adjusted_vs_buy_hold | sharpe 0.18 / calmar 0.13 | bh sharpe 0.88 / bh calmar 1.35 | False |

**HISTORICAL GATE RESULT: `False` (DECLASSIFIED; NOT PROMOTION EVIDENCE)**

## Full Sample

| return | drawdown | sharpe | calmar | trades | PF |
|---:|---:|---:|---:|---:|---:|
| -0.97% | 1.95% | -0.17 | -0.10 | 381 | 0.91 |

## Walk Forward

| window | return | drawdown | sharpe | calmar | trades | PF |
|---|---:|---:|---:|---:|---:|---:|
| 2022H1 | -0.11% | 0.66% | -0.18 | -0.36 | 50 | 0.93 |
| 2022H2 | 0.31% | 0.72% | 0.61 | 0.82 | 60 | 1.14 |
| 2023H1 | -1.26% | 1.45% | -3.26 | -1.75 | 41 | 0.30 |
| 2023H2 | 0.34% | 0.30% | 1.05 | 2.18 | 35 | 1.56 |
| 2024H1 | 0.33% | 0.40% | 0.85 | 1.68 | 37 | 1.11 |
| 2024H2 | 0.75% | 0.56% | 1.27 | 2.52 | 44 | 1.46 |
| 2025H1 | 0.08% | 0.34% | 0.22 | 0.46 | 31 | 1.06 |
| 2025H2 | 1.38% | 0.37% | 2.08 | 6.99 | 41 | 2.74 |
| 2026YTD | -0.39% | 0.85% | -1.62 | -3.29 | 17 | 0.28 |