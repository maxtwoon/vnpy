# Extreme Trade Contribution Audit

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


- Uses `trade_difference_attribution.json` and audits whether the improvement depends on a few extreme trades.

| period | total_impact | without_top1_positive | without_top3_positive | without_bottom1_negative | without_bottom3_negative | top1_positive_share | top3_positive_share |
|---|---:|---:|---:|---:|---:|---:|---:|
| full | 11.39% | 8.87% | 5.64% | 14.25% | 16.60% | 22.12% | 50.45% |
| out_sample | 8.39% | 5.87% | 2.90% | 8.85% | 9.55% | 30.02% | 65.43% |

## full Top Positive

| type | symbol | strategy | open_dt | reason | impact | pnl |
|---|---|---|---|---|---:|---:|
| removed | SC888 | 二买多头 | 2026-04-07 14:59:00 | stop_loss | 2.52% | -12.60% |
| changed | RB888 | 三买多头 | 2025-12-08 09:29:00 | trailing_stop | 1.63% | 1.44% |
| changed | RB888 | 三买多头 | 2024-11-04 09:59:00 | trailing_stop | 1.60% | 1.56% |
| changed | SC888 | 一买多头 | 2026-04-02 23:29:00 | trailing_stop | 1.34% | 2.05% |
| added | SC888 | 一买多头 | 2022-09-29 14:29:00 | trailing_stop | 1.00% | 9.99% |
| removed | SC888 | 二买多头 | 2022-09-22 21:29:00 | stop_loss | 0.93% | -4.63% |
| removed | SC888 | 二买多头 | 2022-07-09 00:29:00 | stop_loss | 0.89% | -4.45% |
| removed | RB888 | 二买多头 | 2023-03-30 10:14:00 | stop_loss | 0.86% | -4.32% |
| removed | SC888 | 二买多头 | 2025-09-03 14:29:00 | stop_loss | 0.76% | -3.80% |
| removed | SC888 | 二买多头 | 2022-09-23 21:59:00 | stop_loss | 0.74% | -3.71% |

## full Top Negative

| type | symbol | strategy | open_dt | reason | impact | pnl |
|---|---|---|---|---|---:|---:|
| changed | SC888 | 三买多头 | 2023-08-29 23:29:00 | trailing_stop | -2.86% | 1.08% |
| changed | SC888 | 三买多头 | 2023-06-30 21:29:00 | trailing_stop | -1.19% | 1.22% |
| changed | SC888 | 一买多头 | 2023-08-24 22:59:00 | trailing_stop | -1.16% | 0.86% |
| changed | SC888 | 一买多头 | 2022-09-28 10:59:00 | trailing_stop | -0.80% | 4.05% |
| removed | SC888 | 二买多头 | 2022-06-27 14:59:00 | trailing_stop | -0.78% | 3.91% |
| removed | SC888 | 二买多头 | 2022-05-23 13:59:00 | trailing_stop | -0.66% | 3.30% |
| removed | SC888 | 二买多头 | 2022-08-10 14:29:00 | trailing_stop | -0.63% | 3.15% |
| removed | A888 | 二买多头 | 2022-09-15 10:14:00 | trailing_stop | -0.53% | 2.66% |
| changed | SC888 | 一买多头 | 2024-02-03 00:59:00 | trailing_stop | -0.52% | 1.31% |
| removed | SC888 | 二买多头 | 2022-08-08 22:59:00 | trailing_stop | -0.47% | 2.36% |

## out_sample Top Positive

| type | symbol | strategy | open_dt | reason | impact | pnl |
|---|---|---|---|---|---:|---:|
| removed | SC888 | 二买多头 | 2026-04-07 14:59:00 | stop_loss | 2.52% | -12.60% |
| changed | RB888 | 三买多头 | 2025-12-08 09:29:00 | trailing_stop | 1.63% | 1.44% |
| changed | SC888 | 一买多头 | 2026-04-02 23:29:00 | trailing_stop | 1.34% | 2.05% |
| removed | SC888 | 二买多头 | 2025-09-03 14:29:00 | stop_loss | 0.76% | -3.80% |
| removed | SC888 | 二买多头 | 2026-03-30 21:40:00 | stop_loss | 0.72% | -3.60% |
| removed | SC888 | 二买多头 | 2026-04-13 14:59:00 | stop_loss | 0.68% | -3.39% |
| removed | SC888 | 二买多头 | 2025-05-20 14:29:00 | stop_loss | 0.67% | -3.37% |
| removed | RB888 | 二买多头 | 2025-02-19 09:59:00 | stop_loss | 0.64% | -3.20% |
| changed | SC888 | 一买多头 | 2025-05-12 23:59:00 | trailing_stop | 0.35% | 1.25% |
| changed | RB888 | 一买多头 | 2025-03-11 09:29:00 | trailing_stop | 0.33% | 1.06% |

## out_sample Top Negative

| type | symbol | strategy | open_dt | reason | impact | pnl |
|---|---|---|---|---|---:|---:|
| removed | SC888 | 二买多头 | 2025-09-10 01:59:00 | trailing_stop | -0.45% | 2.27% |
| removed | SC888 | 二买多头 | 2025-08-18 23:29:00 | trailing_stop | -0.45% | 2.23% |
| changed | SC888 | 一买多头 | 2025-06-28 01:29:00 | trailing_stop | -0.25% | 0.87% |
| added | RB888 | 一买多头 | 2025-08-29 09:29:00 | stop_loss | -0.22% | -2.24% |
| added | RB888 | 一买多头 | 2025-03-13 21:29:00 | stop_loss | -0.22% | -2.22% |
| changed | SC888 | 一买多头 | 2026-01-12 10:14:00 | trailing_stop | -0.19% | 1.25% |
| changed | RB888 | 一买多头 | 2025-11-11 10:14:00 | trailing_stop | -0.16% | 1.42% |
| changed | RB888 | 一买多头 | 2025-02-14 21:59:00 | trailing_stop | -0.09% | 1.69% |
| changed | RB888 | 一买多头 | 2026-02-13 10:59:00 | trailing_stop | -0.09% | 1.57% |
| changed | SC888 | 一买多头 | 2026-01-09 00:59:00 | trailing_stop | -0.06% | 2.00% |