# SimNow Precheck Risk Report

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


- candidate: `sc025_a_zn010_sc3buy_half + A/AP trailing 250/0.20`
- period: `2022-01-01 ~ 2026-04-24`
- cost_factor: `1.0`

## Portfolio Risk

| metric | value |
|---|---:|
| total_return | 2.28% |
| max_single_day_loss | -0.29% (2022-03-15) |
| max_single_day_gain | 0.52% (2024-10-30) |
| max_drawdown | -1.32% |
| max_recovery_days | 614 |
| max_consecutive_loss_days | 6 |
| max_consecutive_loss_return | -0.06% |
| max_gross_exposure | 28.00% |
| max_net_exposure_abs | 28.00% |
| max_long_exposure | 28.00% |
| max_short_exposure | 2.50% |
| both_long_short_days | 231 |
| max_both_long_short_symbols | 2 |
| trades | 534 |

## Symbol Risk

| symbol | return | max_day_loss | max_dd | max_gross | both_ls_days | trades |
|---|---:|---:|---:|---:|---:|---:|
| AP888 | 7.50% | -1.43% | -2.79% | 60.00% | 0 | 59 |
| RB888 | 0.61% | -0.37% | -1.37% | 30.00% | 0 | 40 |
| SC888 | -2.94% | -1.53% | -4.30% | 27.50% | 13 | 205 |
| A888 | 4.19% | -0.48% | -3.77% | 40.00% | 81 | 84 |
| ZN888 | 1.79% | -1.14% | -6.28% | 61.00% | 142 | 146 |

## Symbol Concentration

- top1 abs share: `44.79%`
- top3 abs share: `87.60%`

| symbol | weighted_pnl | abs_share |
|---|---:|---:|
| AP888 | 1.50% | 44.79% |
| A888 | 0.84% | 25.08% |
| SC888 | -0.59% | 17.72% |
| ZN888 | 0.36% | 10.70% |
| RB888 | 0.06% | 1.70% |

## Sub-Strategy Concentration

- top1 abs share: `65.60%`
- top3 abs share: `93.77%`

| strategy | weighted_pnl | abs_share |
|---|---:|---:|
| 二买多头 | 1.59% | 65.60% |
| 三买多头 | 0.41% | 16.94% |
| 一买多头 | 0.27% | 11.23% |
| 三卖空头 | -0.13% | 5.39% |
| 一卖空头 | 0.02% | 0.84% |