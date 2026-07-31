# no_A Failure Attribution

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


- candidate: `sc075_a_zn010 + A/AP trailing 250/0.20`
- symbols: `AP888, RB888, SC888, ZN888`

## Portfolio Windows

| window | strategy_ret | strategy_sharpe | strategy_calmar | bh_ret | bh_sharpe | bh_calmar | risk_adj_gt_bh |
|---|---:|---:|---:|---:|---:|---:|---|
| OOS | 1.13% | 0.66 | 0.71 | 11.63% | 0.62 | 0.78 | False |
| 2022H1 | -0.07% | -0.11 | -0.17 | 13.43% | 1.15 | 1.75 | False |
| 2022H2 | 0.45% | 0.97 | 1.22 | -7.82% | -0.76 | -0.93 | True |
| 2023H1 | -1.53% | -3.74 | -1.81 | -5.82% | -0.80 | -0.76 | False |
| 2023H2 | 0.07% | 0.16 | 0.26 | 1.53% | 0.30 | 0.24 | False |
| 2024H1 | 0.77% | 1.69 | 3.83 | -0.53% | 0.03 | -0.09 | True |
| 2024H2 | 0.43% | 0.63 | 1.10 | -3.30% | -0.38 | -0.44 | True |
| 2025H1 | 0.16% | 0.37 | 0.53 | -5.47% | -0.73 | -0.99 | True |
| 2025H2 | 1.45% | 2.01 | 8.03 | 4.23% | 0.87 | 1.36 | True |
| 2026YTD | -0.59% | -1.69 | -4.51 | 4.89% | 0.97 | 2.02 | False |

## OOS By Symbol

| symbol | strategy_ret | strategy_sharpe | strategy_calmar | bh_ret | bh_sharpe | bh_calmar | trades | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| AP888 | 4.28% | 1.81 | 3.00 | 38.91% | 1.59 | 4.80 | 12 | 2.86 |
| RB888 | 0.95% | 0.68 | 0.80 | -2.98% | -0.11 | -0.18 | 14 | 1.34 |
| SC888 | -1.71% | -0.36 | -0.27 | 12.63% | 0.40 | 0.25 | 47 | 1.55 |
| ZN888 | 1.36% | 0.34 | 0.34 | -2.03% | -0.04 | -0.11 | 29 | 1.23 |

## OOS Sub-Strategy Weighted PnL

| symbol | strategy | trades | weighted_pnl | raw_pnl |
|---|---|---:|---:|---:|
| AP888 | 一买多头 | 4 | 0.00% | 0.04% |
| AP888 | 二买多头 | 3 | 0.25% | 1.24% |
| AP888 | 三买多头 | 5 | 4.03% | 13.43% |
| RB888 | 一买多头 | 13 | 0.19% | 1.94% |
| RB888 | 三买多头 | 1 | 0.43% | 1.44% |
| SC888 | 三买多头 | 3 | -4.31% | -14.37% |
| SC888 | 三卖空头 | 1 | -0.84% | -3.74% |
| SC888 | 一买多头 | 19 | -0.67% | -6.68% |
| SC888 | 一卖空头 | 24 | 4.11% | 54.84% |
| ZN888 | 三买多头 | 2 | -0.06% | -0.20% |
| ZN888 | 一卖空头 | 12 | -0.03% | -2.71% |
| ZN888 | 三卖空头 | 3 | -0.02% | -0.78% |
| ZN888 | 一买多头 | 10 | 0.39% | 3.89% |
| ZN888 | 二买多头 | 2 | 1.08% | 5.39% |