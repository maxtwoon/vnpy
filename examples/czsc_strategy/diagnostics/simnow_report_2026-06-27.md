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


- observed_days: `2/20`
- pass_days: `0`
- pending_days: `1`
- skipped_days: `1`
- consistency_matched_days: `0`
- warning_days: `0`
- halt_days: `0`
- latest_record_date: `2026-06-27`
- last_valid_observation_date: ``
- consecutive_clean_days: `0`
- ready_to_expand: `False`
- promotion_blockers: `need_18_more_observed_days, pending_days_present, skipped_days_present, non_pass_days_present, consistency_not_fully_matched`

## Status Counts

| status | days |
|---|---:|
| pending | 1 |
| skipped | 1 |

## Pending / Skipped / Risk Reasons

| reason | days |
|---|---:|
| ctp_disconnect_097_no_snapshot | 1 |
| historical_db_lag | 1 |

## Recent Records

| date | status | reason | consistency | threshold | gross | day_loss_abs | symbol_top1 | strategy_top1 |
|---|---|---|---|---:|---:|---:|---:|---:|
| 2026-06-22 | pending | historical_db_lag | False | pass | 0.00% | 0.00% | 0.00% | 0.00% |
| 2026-06-27 | skipped | ctp_disconnect_097_no_snapshot | False | pass | 0.00% | 0.00% | 0.00% | 0.00% |