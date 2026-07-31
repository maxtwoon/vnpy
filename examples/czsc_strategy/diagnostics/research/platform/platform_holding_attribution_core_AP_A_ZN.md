# Platform Holding Attribution

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


- set: `core_AP_A_ZN`
- symbols: `AP888, A888, ZN888`
- period: `2025-01-01 ~ 2026-04-24`

## Summary

| group | trades | pnl_sum | win_rate | avg_pnl | PF | avg_bars |
|---|---:|---:|---:|---:|---:|---:|
| all | 42 | 41.94% | 61.90% | 1.00% | 2.42 | 194.64 |

## by_symbol

| group | trades | pnl_sum | win_rate | avg_pnl | PF | avg_bars |
|---|---:|---:|---:|---:|---:|---:|
| A888 | 16 | 14.05% | 56.25% | 0.88% | 2.04 | 219.81 |
| AP888 | 12 | 18.81% | 75.00% | 1.57% | 3.37 | 69.08 |
| ZN888 | 14 | 9.08% | 57.14% | 0.65% | 2.11 | 273.50 |

## by_strategy

| group | trades | pnl_sum | win_rate | avg_pnl | PF | avg_bars |
|---|---:|---:|---:|---:|---:|---:|
| 一买多头 | 24 | 8.44% | 50.00% | 0.35% | 1.55 | 118.42 |
| 三买多头 | 9 | 12.05% | 77.78% | 1.34% | 2.62 | 224.00 |
| 二买多头 | 9 | 21.45% | 77.78% | 2.38% | 4.22 | 368.56 |

## by_reason

| group | trades | pnl_sum | win_rate | avg_pnl | PF | avg_bars |
|---|---:|---:|---:|---:|---:|---:|
| signal_exit | 13 | -3.63% | 38.46% | -0.28% | 0.39 | 123.92 |
| stop_loss | 8 | -23.69% | 0.00% | -2.96% | 0.00 | 194.38 |
| timeout | 1 | 1.36% | 100.00% | 1.36% | inf | 1,000.00 |
| trailing_stop | 20 | 67.89% | 100.00% | 3.39% | inf | 200.45 |

## by_duration

| group | trades | pnl_sum | win_rate | avg_pnl | PF | avg_bars |
|---|---:|---:|---:|---:|---:|---:|
| 00-20 | 3 | -3.19% | 33.33% | -1.06% | 0.45 | 15.67 |
| 061-120 | 12 | -0.94% | 41.67% | -0.08% | 0.90 | 83.33 |
| 121-300 | 9 | 25.16% | 77.78% | 2.80% | 18.12 | 187.78 |
| 21-60 | 10 | 8.73% | 70.00% | 0.87% | 2.56 | 41.80 |
| 300+ | 8 | 12.17% | 75.00% | 1.52% | 2.71 | 627.50 |

## by_stale_loss

| group | trades | pnl_sum | win_rate | avg_pnl | PF | avg_bars |
|---|---:|---:|---:|---:|---:|---:|
| bars_gt_120_loss | 4 | -8.61% | 0.00% | -2.15% | 0.00 | 427.00 |
| bars_gt_120_win | 13 | 45.94% | 100.00% | 3.53% | inf | 384.77 |
| bars_le_120 | 25 | 4.60% | 52.00% | 0.18% | 1.22 | 58.60 |

## Worst Long Holds

| symbol | strategy | open_dt | close_dt | pnl | bars | reason |
|---|---|---|---|---:|---:|---|
| A888 | 三买多头 | 2025-06-27 09:59:00 | 2025-08-21 21:29:00 | -3.69% | 476 | 止损 |
| A888 | 二买多头 | 2025-05-08 09:29:00 | 2025-08-12 09:29:00 | -3.45% | 801 | 止损 |
| A888 | 一买多头 | 2025-07-03 10:59:00 | 2025-08-06 14:59:00 | -0.86% | 292 | 信号平仓-一买平多 |
| A888 | 一买多头 | 2025-05-07 10:14:00 | 2025-05-22 21:59:00 | -0.61% | 139 | 信号平仓-一买平多 |
| ZN888 | 一买多头 | 2025-08-06 00:29:00 | 2025-09-15 23:59:00 | 0.04% | 463 | 信号平仓-一买平多 |
| ZN888 | 二买多头 | 2025-08-26 21:59:00 | 2025-12-01 21:29:00 | 1.36% | 1,000 | 超时 |
| ZN888 | 一买多头 | 2025-11-21 00:29:00 | 2025-12-05 21:29:00 | 2.19% | 171 | 移动止损 |
| ZN888 | 一买多头 | 2025-07-03 11:29:00 | 2025-07-25 00:59:00 | 2.47% | 252 | 移动止损 |
| A888 | 二买多头 | 2025-09-02 13:59:00 | 2025-10-27 10:59:00 | 2.61% | 391 | 移动止损 |
| ZN888 | 一买多头 | 2025-10-17 10:14:00 | 2025-11-05 09:29:00 | 2.69% | 207 | 移动止损 |
| ZN888 | 三买多头 | 2025-08-20 00:29:00 | 2025-12-05 21:59:00 | 3.56% | 1,140 | 移动止损 |
| A888 | 一买多头 | 2026-03-24 21:59:00 | 2026-04-13 09:59:00 | 3.80% | 144 | 移动止损 |
| ZN888 | 二买多头 | 2025-12-24 22:59:00 | 2026-01-08 10:59:00 | 4.03% | 129 | 移动止损 |
| A888 | 二买多头 | 2025-11-26 09:59:00 | 2026-01-13 14:29:00 | 5.27% | 386 | 移动止损 |
| A888 | 一买多头 | 2025-12-19 21:59:00 | 2026-01-13 21:29:00 | 5.51% | 176 | 移动止损 |
| A888 | 二买多头 | 2025-03-25 14:29:00 | 2025-04-17 21:59:00 | 5.94% | 180 | 移动止损 |
| AP888 | 二买多头 | 2025-05-23 09:29:00 | 2025-07-28 10:14:00 | 6.47% | 363 | 移动止损 |