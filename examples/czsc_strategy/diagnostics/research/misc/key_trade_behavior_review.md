# Key Trade Behavior Review

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


- This is a structured review queue, not a replacement for chart replay.
- Positive impact means combined is better than baseline for that trade event.

## full

| type | symbol | strategy | open_dt | close_dt | reason | impact | pnl | review_hint |
|---|---|---|---|---|---|---:|---:|---|
| changed | SC888 | 三买多头 | 2023-08-29 23:29:00 | 2023-08-30 22:59:00 | trailing_stop | -2.86% | 1.08% | negative: tighter trailing exited too early and lost follow-through profit. |
| removed | SC888 | 二买多头 | 2026-04-07 14:59:00 | 2026-04-08 09:29:00 | stop_loss | 2.52% | -12.60% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| changed | RB888 | 三买多头 | 2025-12-08 09:29:00 | 2026-01-07 22:59:00 | trailing_stop | 1.63% | 1.44% | strong: tighter trailing locked profit or reduced give-back. |
| changed | RB888 | 三买多头 | 2024-11-04 09:59:00 | 2024-11-05 14:59:00 | trailing_stop | 1.60% | 1.56% | strong: tighter trailing locked profit or reduced give-back. |
| changed | SC888 | 一买多头 | 2026-04-02 23:29:00 | 2026-04-03 11:29:00 | trailing_stop | 1.34% | 2.05% | strong: tighter trailing locked profit or reduced give-back. |
| changed | SC888 | 三买多头 | 2023-06-30 21:29:00 | 2023-07-05 22:29:00 | trailing_stop | -1.19% | 1.22% | negative: tighter trailing exited too early and lost follow-through profit. |
| changed | SC888 | 一买多头 | 2023-08-24 22:59:00 | 2023-08-25 10:59:00 | trailing_stop | -1.16% | 0.86% | negative: tighter trailing exited too early and lost follow-through profit. |
| added | SC888 | 一买多头 | 2022-09-29 14:29:00 | 2022-10-11 14:59:00 | trailing_stop | 1.00% | 9.99% | positive add: check whether shorter trailing released the entry interval. |
| removed | SC888 | 二买多头 | 2022-09-22 21:29:00 | 2022-09-23 21:29:00 | stop_loss | 0.93% | -4.63% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2022-07-09 00:29:00 | 2022-07-12 21:29:00 | stop_loss | 0.89% | -4.45% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | RB888 | 二买多头 | 2023-03-30 10:14:00 | 2023-04-06 09:29:00 | stop_loss | 0.86% | -4.32% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| changed | SC888 | 一买多头 | 2022-09-28 10:59:00 | 2022-09-29 13:59:00 | trailing_stop | -0.80% | 4.05% | negative: tighter trailing exited too early and lost follow-through profit. |
| removed | SC888 | 二买多头 | 2022-06-27 14:59:00 | 2022-06-29 11:29:00 | trailing_stop | -0.78% | 3.91% | negative: profitable trade was filtered out; check whether the filter is too strict. |
| removed | SC888 | 二买多头 | 2025-09-03 14:29:00 | 2025-09-05 21:29:00 | stop_loss | 0.76% | -3.80% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2022-09-23 21:59:00 | 2022-09-26 14:29:00 | stop_loss | 0.74% | -3.71% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2026-03-30 21:40:00 | 2026-03-31 09:59:00 | stop_loss | 0.72% | -3.60% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2023-10-27 22:59:00 | 2023-11-02 02:29:00 | stop_loss | 0.72% | -3.58% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2022-06-22 00:59:00 | 2022-06-22 10:14:00 | stop_loss | 0.69% | -3.45% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2024-08-26 14:29:00 | 2024-09-02 09:29:00 | stop_loss | 0.69% | -3.44% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2026-04-13 14:59:00 | 2026-04-14 21:59:00 | stop_loss | 0.68% | -3.39% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |

## out_sample

| type | symbol | strategy | open_dt | close_dt | reason | impact | pnl | review_hint |
|---|---|---|---|---|---|---:|---:|---|
| removed | SC888 | 二买多头 | 2026-04-07 14:59:00 | 2026-04-08 09:29:00 | stop_loss | 2.52% | -12.60% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| changed | RB888 | 三买多头 | 2025-12-08 09:29:00 | 2026-01-07 22:59:00 | trailing_stop | 1.63% | 1.44% | strong: tighter trailing locked profit or reduced give-back. |
| changed | SC888 | 一买多头 | 2026-04-02 23:29:00 | 2026-04-03 11:29:00 | trailing_stop | 1.34% | 2.05% | strong: tighter trailing locked profit or reduced give-back. |
| removed | SC888 | 二买多头 | 2025-09-03 14:29:00 | 2025-09-05 21:29:00 | stop_loss | 0.76% | -3.80% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2026-03-30 21:40:00 | 2026-03-31 09:59:00 | stop_loss | 0.72% | -3.60% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2026-04-13 14:59:00 | 2026-04-14 21:59:00 | stop_loss | 0.68% | -3.39% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2025-05-20 14:29:00 | 2025-05-30 09:29:00 | stop_loss | 0.67% | -3.37% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | RB888 | 二买多头 | 2025-02-19 09:59:00 | 2025-03-10 13:59:00 | stop_loss | 0.64% | -3.20% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2025-09-10 01:59:00 | 2025-09-17 23:29:00 | trailing_stop | -0.45% | 2.27% | negative: profitable trade was filtered out; check whether the filter is too strict. |
| removed | SC888 | 二买多头 | 2025-08-18 23:29:00 | 2025-08-26 14:59:00 | trailing_stop | -0.45% | 2.23% | negative: profitable trade was filtered out; check whether the filter is too strict. |
| changed | SC888 | 一买多头 | 2025-05-12 23:59:00 | 2025-05-14 09:29:00 | trailing_stop | 0.35% | 1.25% | strong: tighter trailing locked profit or reduced give-back. |
| changed | RB888 | 一买多头 | 2025-03-11 09:29:00 | 2025-03-13 11:29:00 | trailing_stop | 0.33% | 1.06% | strong: tighter trailing locked profit or reduced give-back. |
| changed | SC888 | 一买多头 | 2025-05-20 02:29:00 | 2025-05-21 01:59:00 | trailing_stop | 0.33% | 0.96% | strong: tighter trailing locked profit or reduced give-back. |
| changed | SC888 | 一买多头 | 2025-06-28 01:29:00 | 2025-07-02 21:59:00 | trailing_stop | -0.25% | 0.87% | negative: tighter trailing exited too early and lost follow-through profit. |
| added | RB888 | 一买多头 | 2025-08-29 09:29:00 | 2025-09-01 09:59:00 | stop_loss | -0.22% | -2.24% | risk: parameter change introduced a new stop-loss trade. |
| added | RB888 | 一买多头 | 2025-03-13 21:29:00 | 2025-03-18 14:59:00 | stop_loss | -0.22% | -2.22% | risk: parameter change introduced a new stop-loss trade. |
| changed | SC888 | 一买多头 | 2026-01-12 10:14:00 | 2026-01-13 09:59:00 | trailing_stop | -0.19% | 1.25% | negative: tighter trailing exited too early and lost follow-through profit. |
| changed | RB888 | 一买多头 | 2025-11-11 10:14:00 | 2025-11-17 21:29:00 | trailing_stop | -0.16% | 1.42% | negative: tighter trailing exited too early and lost follow-through profit. |
| changed | RB888 | 一买多头 | 2025-08-25 22:29:00 | 2025-08-28 22:29:00 | trailing_stop | 0.15% | 1.63% | strong: tighter trailing locked profit or reduced give-back. |
| added | RB888 | 一买多头 | 2025-02-19 14:29:00 | 2025-02-21 13:59:00 | trailing_stop | 0.13% | 1.32% | positive add: check whether shorter trailing released the entry interval. |
