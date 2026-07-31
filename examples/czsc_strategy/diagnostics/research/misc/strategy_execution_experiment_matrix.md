# Strategy Execution Experiment Matrix

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


- generated_at: `2026-06-18T07:24:15.305919+00:00`
- db_path: `D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db`
- scenarios: baseline / second_buy_filters / trailing_overrides / combined

## full (2022-01-01 ~ 2026-04-24)

| scenario | combo_return | combo_drawdown | combo_trades | combo_win_rate | max_gross_exposure | errors |
|---|---:|---:|---:|---:|---:|---:|
| baseline | -2.20% | 8.15% | 358 | 43.04% | 60.00% | 0 |
| second_buy_filters | 0.05% | 6.20% | 326 | 44.05% | 60.00% | 0 |
| trailing_overrides | -0.98% | 6.51% | 381 | 49.51% | 60.00% | 0 |
| combined | 0.08% | 5.53% | 345 | 49.18% | 60.00% | 0 |

| scenario | symbol | return | drawdown | trades | win_rate | sharpe | gross |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline | AP888 | 6.48% | 3.58% | 67 | 56.72% | 0.52 | 60.00% |
| baseline | RB888 | -8.02% | 8.75% | 43 | 30.23% | -1.23 | 40.00% |
| baseline | SC888 | -10.87% | 15.80% | 123 | 46.34% | -0.50 | 60.00% |
| baseline | A888 | -0.20% | 5.90% | 47 | 38.30% | -0.02 | 60.00% |
| baseline | ZN888 | 1.62% | 6.73% | 78 | 43.59% | 0.14 | 60.00% |
| second_buy_filters | AP888 | 6.02% | 4.04% | 66 | 56.06% | 0.49 | 60.00% |
| second_buy_filters | RB888 | -3.89% | 4.62% | 37 | 35.14% | -0.74 | 40.00% |
| second_buy_filters | SC888 | -2.80% | 9.23% | 99 | 48.48% | -0.17 | 40.00% |
| second_buy_filters | A888 | -0.73% | 6.35% | 46 | 36.96% | -0.08 | 60.00% |
| second_buy_filters | ZN888 | 1.62% | 6.73% | 78 | 43.59% | 0.14 | 60.00% |
| trailing_overrides | AP888 | 6.48% | 3.58% | 67 | 56.72% | 0.52 | 60.00% |
| trailing_overrides | RB888 | -1.72% | 3.18% | 51 | 50.98% | -0.37 | 30.00% |
| trailing_overrides | SC888 | -11.11% | 13.14% | 138 | 57.97% | -0.64 | 60.00% |
| trailing_overrides | A888 | -0.20% | 5.90% | 47 | 38.30% | -0.02 | 60.00% |
| trailing_overrides | ZN888 | 1.62% | 6.73% | 78 | 43.59% | 0.14 | 60.00% |
| combined | AP888 | 6.02% | 4.04% | 66 | 56.06% | 0.49 | 60.00% |
| combined | RB888 | -0.45% | 2.11% | 45 | 51.11% | -0.12 | 30.00% |
| combined | SC888 | -6.06% | 8.42% | 110 | 58.18% | -0.51 | 40.00% |
| combined | A888 | -0.73% | 6.35% | 46 | 36.96% | -0.08 | 60.00% |
| combined | ZN888 | 1.62% | 6.73% | 78 | 43.59% | 0.14 | 60.00% |

## out_sample (2025-01-01 ~ 2026-04-24)

| scenario | combo_return | combo_drawdown | combo_trades | combo_win_rate | max_gross_exposure | errors |
|---|---:|---:|---:|---:|---:|---:|
| baseline | -0.52% | 4.66% | 92 | 49.86% | 60.00% | 0 |
| second_buy_filters | 0.50% | 3.66% | 84 | 50.65% | 60.00% | 0 |
| trailing_overrides | 0.39% | 4.11% | 98 | 56.62% | 60.00% | 0 |
| combined | 1.16% | 3.27% | 89 | 56.48% | 60.00% | 0 |

| scenario | symbol | return | drawdown | trades | win_rate | sharpe | gross |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline | AP888 | 5.37% | 1.77% | 15 | 73.33% | 2.15 | 60.00% |
| baseline | RB888 | -1.54% | 3.17% | 13 | 38.46% | -0.70 | 40.00% |
| baseline | SC888 | -11.24% | 11.56% | 32 | 31.25% | -1.26 | 60.00% |
| baseline | A888 | 3.67% | 3.83% | 16 | 56.25% | 1.01 | 60.00% |
| baseline | ZN888 | 1.16% | 2.98% | 16 | 50.00% | 0.29 | 60.00% |
| second_buy_filters | AP888 | 5.37% | 1.77% | 15 | 73.33% | 2.15 | 60.00% |
| second_buy_filters | RB888 | -0.90% | 2.21% | 12 | 41.67% | -0.45 | 40.00% |
| second_buy_filters | SC888 | -6.80% | 7.51% | 25 | 32.00% | -1.09 | 40.00% |
| second_buy_filters | A888 | 3.67% | 3.83% | 16 | 56.25% | 1.01 | 60.00% |
| second_buy_filters | ZN888 | 1.16% | 2.98% | 16 | 50.00% | 0.29 | 60.00% |
| trailing_overrides | AP888 | 5.37% | 1.77% | 15 | 73.33% | 2.15 | 60.00% |
| trailing_overrides | RB888 | 1.03% | 1.35% | 18 | 61.11% | 0.70 | 30.00% |
| trailing_overrides | SC888 | -9.30% | 10.62% | 33 | 42.42% | -1.23 | 50.00% |
| trailing_overrides | A888 | 3.67% | 3.83% | 16 | 56.25% | 1.01 | 60.00% |
| trailing_overrides | ZN888 | 1.16% | 2.98% | 16 | 50.00% | 0.29 | 60.00% |
| combined | AP888 | 5.37% | 1.77% | 15 | 73.33% | 2.15 | 60.00% |
| combined | RB888 | 0.78% | 1.27% | 17 | 58.82% | 0.55 | 30.00% |
| combined | SC888 | -5.17% | 6.52% | 25 | 44.00% | -1.04 | 30.00% |
| combined | A888 | 3.67% | 3.83% | 16 | 56.25% | 1.01 | 60.00% |
| combined | ZN888 | 1.16% | 2.98% | 16 | 50.00% | 0.29 | 60.00% |
