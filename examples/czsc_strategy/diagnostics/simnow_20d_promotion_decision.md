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
- observation_start_date: `2026-08-12`
- excluded_before_start_count: `6`
- observed_days: `12/20`
- valid_observation_days: `10/20`
- pass_days: `10`
- pending_days: `2`
- skipped_days: `0`
- consistency_matched_days: `10`
- warning_days: `0`
- halt_days: `0`
- last_valid_observation_date: `2026-08-27`
- promotion_blockers: `need_10_more_valid_observation_days, pending_days_present, non_pass_days_present, consistency_not_fully_matched`

## Status Counts

| status | days |
|---|---:|
| pass | 10 |
| pending | 2 |

## Pending / Skipped Reasons

| reason | days |
|---|---:|
| kline_coverage_incomplete | 1 |
| no_captured_session_data_only_replay_derived | 1 |

## Blocking Action Counts

| action_class | days |
|---|---:|
| investigate_infra | 1 |
| wait_for_data | 1 |

## Top Blocking Actions

| reason | days | action_class | blocker_class | governance_class | reasonableness |
|---|---:|---|---|---|---|
| kline_coverage_incomplete | 1 | wait_for_data | wait | data_readiness_gap | reasonable |
| no_captured_session_data_only_replay_derived | 1 | investigate_infra | review_now | infra_or_mapping_gap | needs_fix |

## Reason Governance

- reason_rationality_verdict: `mixed_action_required`
- reason_rationality_cn: `最近阻塞日中需要修配置、流程或安全问题的占比较高，应优先处理可修复项。`
- pareto_summary.top3_share_pct: `100.0`
- pareto_summary.summary_cn: `前 2 个阻塞原因占 100.0%（2/2），其中首要原因 kline_coverage_incomplete 占 50.0%。`

| governance_class | days |
|---|---:|
| data_readiness_gap | 1 |
| infra_or_mapping_gap | 1 |

## Action Summary

| date | status | reason | severity | action_class | blocker_class | action | counts_for_20d |
|---|---|---|---|---|---|---|---|
| 2026-08-12 | pass | no_actionable_events_on_either_side | ok | counts_for_20d | none | 计入 20 日有效观察。 | True |
| 2026-08-13 | pass | no_actionable_events_on_either_side | ok | counts_for_20d | none | 计入 20 日有效观察。 | True |
| 2026-08-14 | pass | no_actionable_events_on_either_side | ok | counts_for_20d | none | 计入 20 日有效观察。 | True |
| 2026-08-17 | pass | no_actionable_events_on_either_side | ok | counts_for_20d | none | 计入 20 日有效观察。 | True |
| 2026-08-20 | pass | no_actionable_events_on_either_side | ok | counts_for_20d | none | 计入 20 日有效观察。 | True |
| 2026-08-21 | pass | no_actionable_events_on_either_side | ok | counts_for_20d | none | 计入 20 日有效观察。 | True |
| 2026-08-24 | pass | no_actionable_events_on_either_side | ok | counts_for_20d | none | 计入 20 日有效观察。 | True |
| 2026-08-25 | pass | no_actionable_events_on_either_side | ok | counts_for_20d | none | 计入 20 日有效观察。 | True |
| 2026-08-26 | pass | no_actionable_events_on_either_side | ok | counts_for_20d | none | 计入 20 日有效观察。 | True |
| 2026-08-27 | pass | no_actionable_events_on_either_side | ok | counts_for_20d | none | 计入 20 日有效观察。 | True |
| 2026-08-28 | pending | kline_coverage_incomplete | medium | wait_for_data | wait | 缺少 K 线品种：ZN888；建议在活跃交易时段重新采集。 | False |
| 2026-08-31 | pending | no_captured_session_data_only_replay_derived | medium | investigate_infra | review_now | 观察条件未满足；建议查看详细日志。 | False |

## Decision

- Candidate cannot expand yet.
- blocker: need_10_more_valid_observation_days
- blocker: pending_days_present
- blocker: non_pass_days_present
- blocker: consistency_not_fully_matched