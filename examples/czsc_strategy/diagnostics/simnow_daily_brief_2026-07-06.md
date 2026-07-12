# SimNow 每日观察日报 - 2026-07-06

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


- automation_status: `pending`
- automation_exit_code: `20`
- automation_reason: `historical_db_lag`
- automation_action: `resolve pending gate before counting`
- record.status: `pending`
- record.valid_observation: `false`
- kline.missing_symbols: `无`
- kline.short_symbols: `无`
- promotion.valid_observation_days: `0`
- promotion.ready_to_expand: `false`
- needs_user_action: `false`

## 20 日进度

- valid_observation_days: `0/20`
- consecutive_valid_days: `0`
- ready_to_expand: `false`
- promotion_blockers: `need_20_more_valid_observation_days,pending_days_present,skipped_days_present`

## 结论

当前不计入 20 日有效观察；历史 DB 未覆盖当天；建议等待或执行 backfill。

## 下一步

按 automation_action 执行：resolve pending gate before counting。
