# SimNow 每日观察验收自动化提示词

自动化名称：`SimNow 每日观察验收`

工作区：`D:\repo\vnpy`

建议执行时间：每周一到周五，北京时间 `15:20` 之后。自动化本身不识别交易所节假日；如果当天节假日、非交易时段、SimNow 服务不可用或无有效行情，记录为 `skipped` 或 `pending`，不要当作代码失败。

## 安全底线（必须遵守）

- 默认只读，**不得发送任何委托**。不要调用任何下单、撤单、交易接口。
- 不得打印或传播私有 SimNow 配置、账户、密码、授权码、API key。
- 所有 artifact 仅作为本地排障材料，不对外提交。

## 正式每日观察

请在 `D:\repo\vnpy` 工作区执行 SimNow 每日观察流程。

任务目标：

按照 `examples\czsc_strategy\diagnostics\NEXT_WORK.md`、`ACCEPTANCE.md` 和 `WORK_LOG.md` 的规则，推进 SimNow 观察台账。默认只读，不得发送任何委托。

执行步骤：

1. 先读取：
   - `examples\czsc_strategy\diagnostics\NEXT_WORK.md`
   - `examples\czsc_strategy\diagnostics\ACCEPTANCE.md`
   - `examples\czsc_strategy\diagnostics\WORK_LOG.md`

2. 运行离线预检：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
   ```

3. 如果预检通过，运行正式只读观察采集：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 1800 -MinKlineBarsPerSymbol 30
   ```

4. 检查 `run_next_work.ps1 -LiveCapture` 是否正常退出，并确认以下两个**核心工件**已生成：
   - `examples\czsc_strategy\diagnostics\simnow_run_summary_YYYY-MM-DD.json`（唯一机器判定来源）
   - `examples\czsc_strategy\diagnostics\simnow_daily_brief_YYYY-MM-DD.md`（人类可读日报来源）

   以下工件仅用于排障或复核，**不得作为最终状态判定来源**：
   - `simnow_export_YYYY-MM-DD.json`
   - `simnow_kline_update_YYYY-MM-DD.json`
   - `simnow_replay_YYYY-MM-DD.json`
   - `simnow_record_YYYY-MM-DD.json`
   - `simnow_report_YYYY-MM-DD.md`
   - `simnow_20d_observation_report.md`
   - `simnow_20d_promotion_decision.md`
   - `simnow_ledger_summary.json`

5. **最终机器判定来源：run summary**。

   `examples\czsc_strategy\diagnostics\simnow_run_summary_YYYY-MM-DD.json` 是每日最终状态的**唯一机器判定来源**，也是 20 日进度的最终机器判定来源。不要通过解析多个 markdown 文件判断最终状态。

   必须读取的 automation 层字段：
   - `automation_status`
   - `automation_exit_code`
   - `automation_reason`
   - `automation_action`

6. **20 日进度只读取 run summary 中的 ledger_summary**。

   必须读取的 20 日进度字段：
   - `ledger_summary.valid_observation_days`
   - `ledger_summary.consecutive_valid_days`
   - `ledger_summary.ready_to_expand`
   - `ledger_summary.promotion_blockers`
   - `ledger_summary.next_action`

7. **日报输出优先使用 daily brief**。

   `simnow_daily_brief_YYYY-MM-DD.md` 是人类可读日报来源，可直接复制或总结到最终回复中；daily brief 只用于展示/复制日报，**不作为机器判定源**。

8. 状态处理规则：

   - `automation_status=valid`：记录为有效观察日，计入 20 日观察台账；可以继续推进。
   - `automation_status=skipped`：说明当天为非交易日、无行情、SimNow 服务不可用或连接未产生快照；不算代码失败，记录原因后继续下一个交易日。
   - `automation_status=pending`：记录阻塞原因，按 `automation_action` 给出处置；如需等待数据覆盖或补采，向用户说明原因和预计动作。
   - `automation_status=halt`：立即停止后续自动化，要求人工审查；不要自动重跑或继续推进。
   - `automation_status=failed`：检查缺失的 artifact、脚本失败或未知状态；先定位是配置、网络、交易时段还是代码错误，能自动修复的修复后重跑，不能修复的列出需要用户提供的信息。

9. 如果当天不是交易日、SimNow 服务不可用、没有行情、或非交易时段导致无有效 tick，不要当作代码失败；根据 run summary 记录为 `skipped` 或 `pending`，并说明原因。

10. 完成后更新：
    - `examples\czsc_strategy\diagnostics\WORK_LOG.md`

11. 输出简短日报，必须包含以下字段：
    - `date`
    - `automation_status`
    - `automation_exit_code`
    - `automation_reason`
    - `automation_action`
    - `ledger_summary.valid_observation_days`
    - `ledger_summary.consecutive_valid_days`
    - `ledger_summary.ready_to_expand`
    - `ledger_summary.promotion_blockers`
    - `ledger_summary.next_action`
    - `record.status`
    - `record.valid_observation`
    - `kline.missing_symbols`
    - `kline.short_symbols`
    - 是否需要用户处理

    日报中的状态描述可以直接引用 `automation_action` 和 daily brief，不再要求手工解析多个 markdown。

## 短烟测

如果只是验证 SimNow 连接和脚本可运行，不希望计入正式观察日，使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

短烟测不会满足 K 线覆盖门槛，不应作为 20 日观察台账的有效观察日。

## Delayed Replay Accounting Semantics

- `local historical DB is the only strategy market-data source`.
- `strategy PnL comes only from delayed replay`.
- `SimNow account balance/PnL must not be used as strategy PnL`.
- `environment_capture` reports SimNow connection, subscription, tick, read-only, and workflow-order-safety counts.
- `account_contamination` reports external SimNow account orders, trades, and active positions. `external SimNow account activity is audit evidence only`; it must never be treated as strategy PnL.
- `delayed_replay` reports whether the post-close DB replay/virtual ledger is available, whether it passed, and which DB symbols are still lagged.
- A `matched` or `valid` daily result means delayed replay validation passed under the observation gates; it does not mean real SimNow order/trade reconciliation unless a future phase explicitly enables strategy-generated SimNow orders.
