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


- scenario: `expanded_short_sc_half`
- symbols: `AP888, RB888, SC888, A888, ZN888`
- portfolio: five-symbol equal weight
- costs: strategy engine commission/slippage are included

## Out-Of-Sample Gate

| metric | strategy | target / benchmark | pass |
|---|---:|---:|---|
| trades | 114 | >= 100 | True |
| profit_factor | 1.40 | >= 1.20 | True |
| max_drawdown | 1.00% | <= 20.00% | True |
| sharpe | 0.96 | >= 0.50 | True |
| calmar | 1.07 | >= 0.50 | True |
| walk_forward_positive_ratio | 66.67% | >= 66.67% | True |
| risk_adjusted_vs_buy_hold | sharpe 0.96 / calmar 1.07 | bh sharpe 0.88 / bh calmar 1.35 | False |

**HISTORICAL GATE RESULT: `False` (DECLASSIFIED; NOT PROMOTION EVIDENCE)**

## Full Sample

| return | drawdown | sharpe | calmar | trades | PF |
|---:|---:|---:|---:|---:|---:|
| 0.00% | 1.84% | 0.01 | 0.00 | 455 | 0.97 |

## Walk Forward

| window | return | drawdown | sharpe | calmar | trades | PF |
|---|---:|---:|---:|---:|---:|---:|
| 2022H1 | -0.42% | 0.76% | -0.76 | -1.13 | 66 | 0.77 |
| 2022H2 | 0.43% | 0.59% | 1.06 | 1.36 | 68 | 1.27 |
| 2023H1 | -1.32% | 1.45% | -3.92 | -1.84 | 50 | 0.27 |
| 2023H2 | 0.14% | 0.37% | 0.46 | 0.71 | 41 | 1.21 |
| 2024H1 | 0.45% | 0.37% | 1.17 | 2.48 | 44 | 1.23 |
| 2024H2 | 0.36% | 0.56% | 0.63 | 1.20 | 47 | 1.17 |
| 2025H1 | 0.21% | 0.44% | 0.58 | 0.98 | 37 | 1.08 |
| 2025H2 | 1.53% | 0.26% | 2.44 | 11.07 | 52 | 3.19 |
| 2026YTD | -0.28% | 0.79% | -1.06 | -2.49 | 24 | 0.42 |