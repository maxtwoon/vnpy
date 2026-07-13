# SimNow 每日观察日报 - 2026-07-10

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


- automation_status: `halt`
- automation_exit_code: `30`
- automation_reason: `no_captured_session_data_only_replay_derived`
- automation_action: `stop automation and review manually`
- record.status: `halt`
- record.valid_observation: `false`
- kline.missing_symbols: `无`
- kline.short_symbols: `无`
- promotion.valid_observation_days: `8`
- promotion.ready_to_expand: `false`
- needs_user_action: `true`

## SimNow 环境采集

- ticks: `4`
- contracts_count: `17971`
- accounts: `1`
- subscribed_count: `5`
- read_only: `true`
- orders_sent_by_workflow: `0`

## 账户污染监控

- account_contamination.detected: `true`
- external_orders: `0`
- external_trades: `0`
- external_active_positions: `1`
- external_position_symbols: `sc2608`
- note: `SimNow 账户活动仅作为外部污染审计证据，不计入策略收益`

## 盘后 DB 延迟回放

- delayed_replay.available: `true`
- delayed_replay.status: `halt`
- delayed_replay.valid_observation: `false`
- delayed_replay.reason: `no_captured_session_data_only_replay_derived`
- latest_db_date: `2026-07-13`
- missing_or_lagged_symbols: `无`
- replay_signals: `5`
- replay_trades: `1`
- replay_positions: `67`
- risk_source: `replay_only`

## 20 日进度

- valid_observation_days: `8/20`
- consecutive_valid_days: `0`
- ready_to_expand: `false`
- promotion_blockers: `need_12_more_valid_observation_days,pending_days_present,skipped_days_present,halt_days_present`

## 结论

观察流程触发停止条件，必须停止自动化并人工审查；阈值触发：；建议检查风险敞口并复核阈值配置。

## 下一步

按 automation_action 执行：stop automation and review manually。
