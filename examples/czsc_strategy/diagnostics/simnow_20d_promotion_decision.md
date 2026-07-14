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
- observation_start_date: `2026-07-14`
- excluded_before_start_count: `12`
- observed_days: `1/20`
- valid_observation_days: `0/20`
- pass_days: `0`
- pending_days: `0`
- skipped_days: `1`
- consistency_matched_days: `0`
- warning_days: `0`
- halt_days: `1`
- last_valid_observation_date: ``
- promotion_blockers: `need_20_more_valid_observation_days, skipped_days_present, non_pass_days_present, consistency_not_fully_matched, halt_threshold_breached`

## Status Counts

| status | days |
|---|---:|
| skipped | 1 |

## Pending / Skipped Reasons

| reason | days |
|---|---:|
| ctp_disconnect_097_no_snapshot | 1 |

## Action Summary

| date | status | reason | severity | action | counts_for_20d |
|---|---|---|---|---|---|
| 2026-07-14 | skipped | ctp_disconnect_097_no_snapshot | info | CTP 连接失败；建议检查 SimNow 服务、网络、账号状态。 | False |

## Decision

- Candidate cannot expand yet.
- blocker: need_20_more_valid_observation_days
- blocker: skipped_days_present
- blocker: non_pass_days_present
- blocker: consistency_not_fully_matched
- blocker: halt_threshold_breached