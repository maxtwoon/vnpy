# SimNow 20-Day Promotion Decision

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


- ready_to_expand: `False`
- observed_days: `11/20`
- valid_observation_days: `8/20`
- pass_days: `8`
- pending_days: `2`
- skipped_days: `1`
- consistency_matched_days: `8`
- warning_days: `0`
- halt_days: `0`
- last_valid_observation_date: `2026-07-09`
- promotion_blockers: `need_12_more_valid_observation_days, pending_days_present, skipped_days_present, non_pass_days_present, consistency_not_fully_matched`

## Status Counts

| status | days |
|---|---:|
| pass | 8 |
| pending | 2 |
| skipped | 1 |

## Pending / Skipped Reasons

| reason | days |
|---|---:|
| ctp_disconnect_097_no_snapshot | 1 |
| historical_db_lag | 1 |
| kline_coverage_incomplete | 1 |
| no_actionable_events_on_either_side | 8 |

## Action Summary

| date | status | reason | severity | action | counts_for_20d |
|---|---|---|---|---|---|
| 2026-06-22 | pass | no_actionable_events_on_either_side | ok | 计入 20 日有效观察。 | True |
| 2026-06-27 | skipped | ctp_disconnect_097_no_snapshot | info | CTP 连接失败；建议检查 SimNow 服务、网络、账号状态。 | False |
| 2026-06-29 | pass | no_actionable_events_on_either_side | ok | 计入 20 日有效观察。 | True |
| 2026-07-01 | pending | kline_coverage_incomplete | medium | 缺少 K 线品种：AP888；建议在活跃交易时段重新采集。 | False |
| 2026-07-02 | pass | no_actionable_events_on_either_side | ok | 计入 20 日有效观察。 | True |
| 2026-07-03 | pass | no_actionable_events_on_either_side | ok | 计入 20 日有效观察。 | True |
| 2026-07-06 | pass | no_actionable_events_on_either_side | ok | 计入 20 日有效观察。 | True |
| 2026-07-07 | pass | no_actionable_events_on_either_side | ok | 计入 20 日有效观察。 | True |
| 2026-07-08 | pass | no_actionable_events_on_either_side | ok | 计入 20 日有效观察。 | True |
| 2026-07-09 | pass | no_actionable_events_on_either_side | ok | 计入 20 日有效观察。 | True |
| 2026-07-10 | pending | historical_db_lag | medium | 历史 DB 未覆盖当天；建议等待或执行 backfill。 | False |

## Decision

- Candidate cannot expand yet.
- blocker: need_12_more_valid_observation_days
- blocker: pending_days_present
- blocker: skipped_days_present
- blocker: non_pass_days_present
- blocker: consistency_not_fully_matched