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
- observation_start_date: `2026-07-30`
- excluded_before_start_count: `3`
- observed_days: `3/20`
- valid_observation_days: `0/20`
- pass_days: `0`
- pending_days: `2`
- skipped_days: `0`
- consistency_matched_days: `1`
- warning_days: `1`
- halt_days: `0`
- last_valid_observation_date: ``
- promotion_blockers: `need_20_more_valid_observation_days, pending_days_present, failed_days_present, non_pass_days_present, consistency_not_fully_matched`

## Status Counts

| status | days |
|---|---:|
| failed | 1 |
| pending | 2 |

## Pending / Skipped Reasons

| reason | days |
|---|---:|
| kline_coverage_incomplete | 2 |
| no_actionable_events_on_either_side | 1 |

## Blocking Action Counts

| action_class | days |
|---|---:|
| resolve_observation_gaps | 1 |
| wait_for_data | 2 |

## Top Blocking Actions

| reason | days | action_class | blocker_class | governance_class | reasonableness |
|---|---:|---|---|---|---|
| kline_coverage_incomplete | 2 | wait_for_data | wait | data_readiness_gap | reasonable |
| no_actionable_events_on_either_side | 1 | resolve_observation_gaps | review_now | risk_control_halt | reasonable |

## Reason Governance

- reason_rationality_verdict: `mostly_reasonable_non_code`
- reason_rationality_cn: `最近阻塞日主要由环境、时段或数据准备因素构成，不应直接视为代码失败。`
- pareto_summary.top3_share_pct: `100.0`
- pareto_summary.summary_cn: `前 2 个阻塞原因占 100.0%（3/3），其中首要原因 kline_coverage_incomplete 占 66.7%。`

| governance_class | days |
|---|---:|
| data_readiness_gap | 2 |
| risk_control_halt | 1 |

## Action Summary

| date | status | reason | severity | action_class | blocker_class | action | counts_for_20d |
|---|---|---|---|---|---|---|---|
| 2026-07-30 | pass | no_actionable_events_on_either_side | warning | resolve_observation_gaps | review_now | status=pass 但仍有 gate 未满足：thresholds warning。 | False |
| 2026-08-10 | pending | kline_coverage_incomplete | medium | wait_for_data | wait | 缺少 K 线品种：SC888；建议在活跃交易时段重新采集。 | False |
| 2026-08-11 | pending | kline_coverage_incomplete | medium | wait_for_data | wait | 缺少 K 线品种：SC888；建议在活跃交易时段重新采集。 | False |

## Decision

- Candidate cannot expand yet.
- blocker: need_20_more_valid_observation_days
- blocker: pending_days_present
- blocker: failed_days_present
- blocker: non_pass_days_present
- blocker: consistency_not_fully_matched