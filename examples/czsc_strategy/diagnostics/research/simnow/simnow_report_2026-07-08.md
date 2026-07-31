# SimNow 20-Day Observation Report

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


- observed_days: `10/20`
- valid_observation_days: `4/20`
- pass_days: `4`
- pending_days: `5`
- skipped_days: `1`
- consistency_matched_days: `4`
- warning_days: `0`
- halt_days: `0`
- latest_record_date: `2026-07-09`
- last_valid_observation_date: `2026-07-08`
- consecutive_clean_days: `0`
- ready_to_expand: `False`
- promotion_blockers: `need_16_more_valid_observation_days, pending_days_present, skipped_days_present, non_pass_days_present, consistency_not_fully_matched`

## Status Counts

| status | days |
|---|---:|
| pass | 4 |
| pending | 5 |
| skipped | 1 |

## Pending / Skipped / Risk Reasons

| reason | days |
|---|---:|
| ctp_disconnect_097_no_snapshot | 1 |
| historical_db_lag | 1 |
| kline_coverage_incomplete | 1 |
| unknown | 3 |

## Action Summary

| date | status | reason | severity | action | counts_for_20d |
|---|---|---|---|---|---|
| 2026-06-22 | pending |  | medium | 观察条件未满足；建议查看详细日志。 | False |
| 2026-06-27 | skipped | ctp_disconnect_097_no_snapshot | info | CTP 连接失败；建议检查 SimNow 服务、网络、账号状态。 | False |
| 2026-06-29 | pending |  | medium | 观察条件未满足；建议查看详细日志。 | False |
| 2026-07-01 | pending | kline_coverage_incomplete | medium | 缺少 K 线品种：AP888；建议在活跃交易时段重新采集。 | False |
| 2026-07-02 | pass | no_actionable_events_on_either_side | ok | 计入 20 日有效观察。 | True |
| 2026-07-03 | pass | no_actionable_events_on_either_side | ok | 计入 20 日有效观察。 | True |
| 2026-07-06 | pass | no_actionable_events_on_either_side | ok | 计入 20 日有效观察。 | True |
| 2026-07-07 | pending |  | medium | 观察条件未满足；建议查看详细日志。 | False |
| 2026-07-08 | pass | no_actionable_events_on_either_side | ok | 计入 20 日有效观察。 | True |
| 2026-07-09 | pending | historical_db_lag | medium | 历史 DB 未覆盖当天；建议等待或执行 backfill。 | False |

## Recent Records

| date | valid | status | reason | consistency | threshold | order_safety | workflow_orders | raw_orders | raw_trades | subscription_missing | kline_missing | kline_short | gross | day_loss_abs | symbol_top1 | strategy_top1 |
|---|---|---|---|---|---|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|
| 2026-06-22 | False | pending |  | False | pass | unknown | 0 | 0 | 0 |  |  |  | 0.00% | 0.00% | 0.00% | 0.00% |
| 2026-06-27 | False | skipped | ctp_disconnect_097_no_snapshot | False | pass |  | 0 | 0 | 0 |  |  |  | 0.00% | 0.00% | 0.00% | 0.00% |
| 2026-06-29 | False | pending |  | False | pass | unknown | 0 | 2 | 2 |  |  |  | 0.00% | 0.00% | 0.00% | 0.00% |
| 2026-07-01 | False | pending | kline_coverage_incomplete | False | pass | unknown | 0 | 0 | 0 |  | AP888 | A888,RB888,SC888,ZN888 | 0.00% | 0.00% | 0.00% | 0.00% |
| 2026-07-02 | True | pass | no_actionable_events_on_either_side | True | pass | pass | 0 | 0 | 0 |  |  |  | 0.00% | 0.00% | 0.00% | 0.00% |
| 2026-07-03 | True | pass | no_actionable_events_on_either_side | True | pass | pass | 0 | 0 | 0 |  |  |  | 0.00% | 0.00% | 0.00% | 0.00% |
| 2026-07-06 | True | pass | no_actionable_events_on_either_side | True | pass | pass | 0 | 0 | 0 |  |  |  | 0.00% | 0.00% | 0.00% | 0.00% |
| 2026-07-07 | False | pending |  | False | pass | pass | 0 | 2 | 2 |  |  |  | 0.00% | 0.00% | 0.00% | 0.00% |
| 2026-07-08 | True | pass | no_actionable_events_on_either_side | True | pass | pass | 0 | 0 | 0 |  |  |  | 0.00% | 0.00% | 0.00% | 0.00% |
| 2026-07-09 | False | pending | historical_db_lag | False | pass | pass | 0 | 0 | 0 |  |  |  | 0.00% | 0.00% | 0.00% | 0.00% |