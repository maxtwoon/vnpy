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
- observation_start_date: `2026-07-28`
- excluded_before_start_count: `1`
- observed_days: `2/20`
- valid_observation_days: `0/20`
- pass_days: `1`
- pending_days: `0`
- skipped_days: `0`
- consistency_matched_days: `2`
- warning_days: `1`
- halt_days: `1`
- last_valid_observation_date: ``
- promotion_blockers: `need_20_more_valid_observation_days, non_pass_days_present, halt_threshold_breached`

## Status Counts

| status | days |
|---|---:|
| halt | 1 |
| pass | 1 |

## Pending / Skipped Reasons

| reason | days |
|---|---:|
| no_actionable_events_on_either_side | 1 |
| symbol_top1_abs_share,strategy_top1_abs_share | 1 |

## Blocking Action Counts

| action_class | days |
|---|---:|
| manual_review_required | 1 |
| resolve_observation_gaps | 1 |

## Top Blocking Actions

| reason | days | action_class | blocker_class | governance_class | reasonableness |
|---|---:|---|---|---|---|
| no_actionable_events_on_either_side | 1 | resolve_observation_gaps | review_now | risk_control_halt | reasonable |
| symbol_top1_abs_share,strategy_top1_abs_share | 1 | manual_review_required | review_now | risk_control_halt | reasonable |

## Reason Governance

- reason_rationality_verdict: `mostly_reasonable_non_code`
- reason_rationality_cn: `最近阻塞日主要由环境、时段或数据准备因素构成，不应直接视为代码失败。`
- pareto_summary.top3_share_pct: `100.0`
- pareto_summary.summary_cn: `前 2 个阻塞原因占 100.0%（2/2），其中首要原因 no_actionable_events_on_either_side 占 50.0%。`

| governance_class | days |
|---|---:|
| risk_control_halt | 2 |

## Action Summary

| date | status | reason | severity | action_class | blocker_class | action | counts_for_20d |
|---|---|---|---|---|---|---|---|
| 2026-07-28 | pass | no_actionable_events_on_either_side | warning | resolve_observation_gaps | review_now | status=pass 但仍有 gate 未满足：thresholds warning。 | False |
| 2026-07-29 | halt | symbol_top1_abs_share,strategy_top1_abs_share | critical | manual_review_required | review_now | 阈值触发：symbol_top1_abs_share=0.8917, strategy_top1_abs_share=0.7576；建议检查风险敞口并复核阈值配置。 | False |

## Decision

- Candidate cannot expand yet.
- blocker: need_20_more_valid_observation_days
- blocker: non_pass_days_present
- blocker: halt_threshold_breached