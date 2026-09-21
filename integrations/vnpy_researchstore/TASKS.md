# STORE-20260916 — 当前执行任务

更新：2026-09-17 10:26:27（北京时间）。完整WP00–WP10未完成；用户确认OpenCode额度恢复，实际续接工具工作已验证。qualified05/native06实际Claude局部PASS，三项qualified问题关闭、152测试、53哈希不变。现按各分支最新任务继续开发。详细事实见 EXECUTION_STATUS.md；完整执行历史与CLI句柄见 .coordination/runtime.json。此前已审方案继续有效，不缩减为原型。

Codex只负责规划、协调、状态和发现的处置；实际Kimi/OpenCode开发，实际Claude审核。根HANDOFF属于其他任务，不更改。

| 工作包 | 当前事实 | 剩余工作 |
| --- | --- | --- |
| WP00 环境/基线 | 初始24文件/81测试已审；隔离venv已用 | 最终允许变化对照、完整dataSource回归 |
| WP01 契约/目录 | core03原问题已独立关闭 | 最终接口与安装包核对 |
| WP02 不可变发布/快照/恢复 | core03已审；qualified05开发完成 | qualified05/native06实际Claude已PASS，最终受影响路径复核 |
| WP03 盘点/流式读取 | 两源目录盘点04E已审通过 | 04H当前恢复收据已生成，待正式终态交接 |
| WP04 ETF真实闭环 | snap-030369f20bd18303；04F16/16检查及18测试通过 | 正式交接已完成；最终CLI变更后受影响入口复核 |
| WP05 datasource target=store | 历史真实Client原始结果入库开发验证通过 | 最终原有功能完整回归和独立验收 |
| WP06 其他导入/质量 | stock/JQ/repair/P4实际case；期货精确日期映射已审 | 公共期货UNKNOWN时间语义04L；真实SS04M |
| WP07 vnpy原生消费 | native06开发完成77测试及真实DB/BOTHAlpha自测 | 实际Claude局部审核通过；真实04F闭环已完成 |
| WP08 录制/恢复/UI | journal02G已审；03D部分接线完成 | 硬退出已删除；EOF真实重试控制及非editable离线E2E仍待验收 |
| WP09 聚合/封存 |02I四问题开发修复，75专项测试通过 | 02IA终态0/58测试；实际Claude02J正在审核 |
| WP10 交付/验证 | 多个实测报告已保留 | 最终实例配置/HTML/文档/检查04N及实际Claude总验收 |

恢复开发时按以下有界任务续接原会话；不允许旧全范围任务覆盖其他owner：

1. recording02IA: TASK_OPENCODE_RECORDING_CALENDAR_02IA.md，session ses_f5335ad96ffe2KeRp3gKXiQjNI。
2. recorder03D B1 FIRST: TASK_KIMI_RECORDER_03D_DISPATCH.md + .coordination/recorder03d-opencode-coordinator-notice.md，session ses_f5335976dffeAZfd2RnS1PfRjp；核心稳定后才最终E2E。
3. capture04H: TASK_KIMI_CAPTURE_RECOVERY_04H.md + .coordination/delivery04h-coordinator-inbox.md，session ses_f533c11deffe9vVcMYSP2fvZrI。
4. futures04L: .coordination/TASK_OPENCODE_FUTURES_TIME_04L_DRAFT.md（已批准），session ses_f53300e7bffedgvcFBA7Lu04zY；移除04K旁路，公共导入器修复后重跑。
5. 04N阶段1: TASK_OPENCODE_DELIVERY_FINAL_04N.md，session ses_f53250e45ffeoc0pc0Jex2wZuP；04F已经完成，当前整理独立文档/配置/HTML。
6. 可信capture及适配器稳定后，TASK_OPENCODE_SS_REPRESENTATIVE_04M.md；所有必要路径齐备后 TASK_OPENCODE_DELIVERY_FINAL_04N.md；最后TASK_CLAUDE_FINAL_AUDIT_03.md。

OpenCode已实际恢复，旧09:33重置时间属历史；Kimi周额度重置未知，不重复探测。按当前所有权继续执行，不重复启动同会话，不购买额度/切换模型，不用Codex或Claude替代开发。未安排自动唤醒。真实网关 LIVE_NOT_RUN；原始数据、账本、凭据、默认设置、vnpy核心、已归档项目、Git生命周期均未获扩大授权。


