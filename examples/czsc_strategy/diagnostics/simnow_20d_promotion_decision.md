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
- observed_days: `2/20`
- valid_observation_days: `0/20`
- pass_days: `0`
- pending_days: `1`
- skipped_days: `0`
- consistency_matched_days: `1`
- warning_days: `0`
- halt_days: `1`
- last_valid_observation_date: ``
- promotion_blockers: `need_20_more_valid_observation_days, pending_days_present, non_pass_days_present, consistency_not_fully_matched, halt_threshold_breached`

## Status Counts

| status | days |
|---|---:|
| halt | 1 |
| pending | 1 |

## Pending / Skipped Reasons

| reason | days |
|---|---:|
| historical_db_lag | 1 |
| no_actionable_events_on_either_side | 1 |

## Action Summary

| date | status | reason | severity | action | counts_for_20d |
|---|---|---|---|---|---|
| 2026-07-14 | halt | consecutive_loss_abs_pct | critical | 阈值触发：drawdown_abs_pct=1.2992%, consecutive_loss_days=6.0000days, consecutive_loss_abs_pct=0.1218%；建议检查风险敞口并复核阈值配置。 | False |
| 2026-07-15 | pending | historical_db_lag | medium | 历史 DB 未覆盖当天；建议等待或执行 backfill。 | False |

## Decision

- Candidate cannot expand yet.
- blocker: need_20_more_valid_observation_days
- blocker: pending_days_present
- blocker: non_pass_days_present
- blocker: consistency_not_fully_matched
- blocker: halt_threshold_breached