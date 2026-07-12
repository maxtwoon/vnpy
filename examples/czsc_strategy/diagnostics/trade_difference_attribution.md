# Baseline vs Combined Trade Difference Attribution

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


- generated_at: `2026-06-19T00:43:44.464414+00:00`
- db_path: `D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db`
- diff key: `(strategy, open_dt, open_price)`

## full (2022-01-01 ~ 2026-04-24)

| scope | trades | avg_pnl | median_pnl | max_loss | max_profit | weighted_sum | losing_streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 358 | -0.19% | -0.63% | -15.19% | 12.50% | -12.69% | 9 |
| combined | 345 | -0.02% | 0.10% | -15.19% | 11.88% | -1.30% | 7 |

| removed | added | changed | unchanged | removed_weighted | added_weighted | changed_delta | total_impact |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 34 | 21 | 59 | 265 | -11.67% | 1.86% | -2.14% | 11.39% |

### By Symbol

| symbol | base_trades | combo_trades | removed | added | changed | total_impact | base_weighted | combo_weighted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| AP888 | 67 | 66 | 1 | 0 | 0 | -0.46% | 6.48% | 6.02% |
| RB888 | 43 | 45 | 8 | 10 | 15 | 7.57% | -8.34% | -0.77% |
| SC888 | 123 | 110 | 24 | 11 | 44 | 4.81% | -10.87% | -6.06% |
| A888 | 47 | 46 | 1 | 0 | 0 | -0.53% | -1.58% | -2.11% |
| ZN888 | 78 | 78 | 0 | 0 | 0 | 0.00% | 1.62% | 1.62% |

### Exit Reason Weighted PnL

| scope | reason | trades | weighted_pnl |
|---|---|---:|---:|
| baseline | signal_exit | 88 | 1.47% |
| baseline | stop_loss | 155 | -76.42% |
| baseline | timeout | 1 | 0.27% |
| baseline | trailing_stop | 114 | 61.98% |
| combined | signal_exit | 83 | 0.91% |
| combined | stop_loss | 128 | -55.83% |
| combined | timeout | 1 | 0.27% |
| combined | trailing_stop | 133 | 53.35% |

### Top Positive Impacts

| type | symbol | strategy | open_dt | close_dt | reason | impact | pnl |
|---|---|---|---|---|---|---:|---:|
| removed | SC888 | 二买多头 | 2026-04-07 14:59:00 | 2026-04-08 09:29:00 | stop_loss | 2.52% | -12.60% |
| changed | RB888 | 三买多头 | 2025-12-08 09:29:00 | 2026-01-07 22:59:00 | trailing_stop | 1.63% | 1.44% |
| changed | RB888 | 三买多头 | 2024-11-04 09:59:00 | 2024-11-05 14:59:00 | trailing_stop | 1.60% | 1.56% |
| changed | SC888 | 一买多头 | 2026-04-02 23:29:00 | 2026-04-03 11:29:00 | trailing_stop | 1.34% | 2.05% |
| added | SC888 | 一买多头 | 2022-09-29 14:29:00 | 2022-10-11 14:59:00 | trailing_stop | 1.00% | 9.99% |
| removed | SC888 | 二买多头 | 2022-09-22 21:29:00 | 2022-09-23 21:29:00 | stop_loss | 0.93% | -4.63% |
| removed | SC888 | 二买多头 | 2022-07-09 00:29:00 | 2022-07-12 21:29:00 | stop_loss | 0.89% | -4.45% |
| removed | RB888 | 二买多头 | 2023-03-30 10:14:00 | 2023-04-06 09:29:00 | stop_loss | 0.86% | -4.32% |
| removed | SC888 | 二买多头 | 2025-09-03 14:29:00 | 2025-09-05 21:29:00 | stop_loss | 0.76% | -3.80% |
| removed | SC888 | 二买多头 | 2022-09-23 21:59:00 | 2022-09-26 14:29:00 | stop_loss | 0.74% | -3.71% |

### Top Negative Impacts

| type | symbol | strategy | open_dt | close_dt | reason | impact | pnl |
|---|---|---|---|---|---|---:|---:|
| changed | SC888 | 三买多头 | 2023-08-29 23:29:00 | 2023-08-30 22:59:00 | trailing_stop | -2.86% | 1.08% |
| changed | SC888 | 三买多头 | 2023-06-30 21:29:00 | 2023-07-05 22:29:00 | trailing_stop | -1.19% | 1.22% |
| changed | SC888 | 一买多头 | 2023-08-24 22:59:00 | 2023-08-25 10:59:00 | trailing_stop | -1.16% | 0.86% |
| changed | SC888 | 一买多头 | 2022-09-28 10:59:00 | 2022-09-29 13:59:00 | trailing_stop | -0.80% | 4.05% |
| removed | SC888 | 二买多头 | 2022-06-27 14:59:00 | 2022-06-29 11:29:00 | trailing_stop | -0.78% | 3.91% |
| removed | SC888 | 二买多头 | 2022-05-23 13:59:00 | 2022-05-27 14:29:00 | trailing_stop | -0.66% | 3.30% |
| removed | SC888 | 二买多头 | 2022-08-10 14:29:00 | 2022-08-12 21:29:00 | trailing_stop | -0.63% | 3.15% |
| removed | A888 | 二买多头 | 2022-09-15 10:14:00 | 2022-09-26 09:29:00 | trailing_stop | -0.53% | 2.66% |
| changed | SC888 | 一买多头 | 2024-02-03 00:59:00 | 2024-02-07 22:59:00 | trailing_stop | -0.52% | 1.31% |
| removed | SC888 | 二买多头 | 2022-08-08 22:59:00 | 2022-08-09 23:29:00 | trailing_stop | -0.47% | 2.36% |

## out_sample (2025-01-01 ~ 2026-04-24)

| scope | trades | avg_pnl | median_pnl | max_loss | max_profit | weighted_sum | losing_streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 92 | -0.29% | -0.20% | -12.60% | 6.47% | -4.29% | 10 |
| combined | 89 | 0.24% | 0.17% | -11.76% | 6.47% | 4.10% | 7 |

| removed | added | changed | unchanged | removed_weighted | added_weighted | changed_delta | total_impact |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 5 | 16 | 68 | -5.09% | -0.12% | 3.42% | 8.39% |

### By Symbol

| symbol | base_trades | combo_trades | removed | added | changed | total_impact | base_weighted | combo_weighted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| AP888 | 15 | 15 | 0 | 0 | 0 | 0.00% | 5.37% | 5.37% |
| RB888 | 13 | 17 | 1 | 5 | 7 | 2.32% | -1.86% | 0.46% |
| SC888 | 32 | 25 | 7 | 0 | 9 | 6.08% | -11.24% | -5.17% |
| A888 | 16 | 16 | 0 | 0 | 0 | 0.00% | 2.29% | 2.29% |
| ZN888 | 16 | 16 | 0 | 0 | 0 | 0.00% | 1.16% | 1.16% |

### Exit Reason Weighted PnL

| scope | reason | trades | weighted_pnl |
|---|---|---:|---:|
| baseline | signal_exit | 26 | -0.83% |
| baseline | stop_loss | 33 | -21.69% |
| baseline | timeout | 1 | 0.27% |
| baseline | trailing_stop | 32 | 17.95% |
| combined | signal_exit | 24 | -0.99% |
| combined | stop_loss | 24 | -13.13% |
| combined | timeout | 1 | 0.27% |
| combined | trailing_stop | 40 | 17.95% |

### Top Positive Impacts

| type | symbol | strategy | open_dt | close_dt | reason | impact | pnl |
|---|---|---|---|---|---|---:|---:|
| removed | SC888 | 二买多头 | 2026-04-07 14:59:00 | 2026-04-08 09:29:00 | stop_loss | 2.52% | -12.60% |
| changed | RB888 | 三买多头 | 2025-12-08 09:29:00 | 2026-01-07 22:59:00 | trailing_stop | 1.63% | 1.44% |
| changed | SC888 | 一买多头 | 2026-04-02 23:29:00 | 2026-04-03 11:29:00 | trailing_stop | 1.34% | 2.05% |
| removed | SC888 | 二买多头 | 2025-09-03 14:29:00 | 2025-09-05 21:29:00 | stop_loss | 0.76% | -3.80% |
| removed | SC888 | 二买多头 | 2026-03-30 21:40:00 | 2026-03-31 09:59:00 | stop_loss | 0.72% | -3.60% |
| removed | SC888 | 二买多头 | 2026-04-13 14:59:00 | 2026-04-14 21:59:00 | stop_loss | 0.68% | -3.39% |
| removed | SC888 | 二买多头 | 2025-05-20 14:29:00 | 2025-05-30 09:29:00 | stop_loss | 0.67% | -3.37% |
| removed | RB888 | 二买多头 | 2025-02-19 09:59:00 | 2025-03-10 13:59:00 | stop_loss | 0.64% | -3.20% |
| changed | SC888 | 一买多头 | 2025-05-12 23:59:00 | 2025-05-14 09:29:00 | trailing_stop | 0.35% | 1.25% |
| changed | RB888 | 一买多头 | 2025-03-11 09:29:00 | 2025-03-13 11:29:00 | trailing_stop | 0.33% | 1.06% |

### Top Negative Impacts

| type | symbol | strategy | open_dt | close_dt | reason | impact | pnl |
|---|---|---|---|---|---|---:|---:|
| removed | SC888 | 二买多头 | 2025-09-10 01:59:00 | 2025-09-17 23:29:00 | trailing_stop | -0.45% | 2.27% |
| removed | SC888 | 二买多头 | 2025-08-18 23:29:00 | 2025-08-26 14:59:00 | trailing_stop | -0.45% | 2.23% |
| changed | SC888 | 一买多头 | 2025-06-28 01:29:00 | 2025-07-02 21:59:00 | trailing_stop | -0.25% | 0.87% |
| added | RB888 | 一买多头 | 2025-08-29 09:29:00 | 2025-09-01 09:59:00 | stop_loss | -0.22% | -2.24% |
| added | RB888 | 一买多头 | 2025-03-13 21:29:00 | 2025-03-18 14:59:00 | stop_loss | -0.22% | -2.22% |
| changed | SC888 | 一买多头 | 2026-01-12 10:14:00 | 2026-01-13 09:59:00 | trailing_stop | -0.19% | 1.25% |
| changed | RB888 | 一买多头 | 2025-11-11 10:14:00 | 2025-11-17 21:29:00 | trailing_stop | -0.16% | 1.42% |
| changed | RB888 | 一买多头 | 2025-02-14 21:59:00 | 2025-02-19 13:59:00 | trailing_stop | -0.09% | 1.69% |
| changed | RB888 | 一买多头 | 2026-02-13 10:59:00 | 2026-03-09 13:59:00 | trailing_stop | -0.09% | 1.57% |
| changed | SC888 | 一买多头 | 2026-01-09 00:59:00 | 2026-01-09 21:29:00 | trailing_stop | -0.06% | 2.00% |
