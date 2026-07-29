# 设计文档索引

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

本目录保存 `examples/czsc_strategy/` 子项目的逐任务设计文档。索引条目数等于本目录下 `*.md` 文件数。

| 文件 | 任务 | 标题 | 阶段（HANDOFF 视角） |
|------|------|------|---------------------|
| [`A32_audit_issue_data_feed.md`](./A32_audit_issue_data_feed.md) | A32 | 审核问题数据接入 + A31 复核瑕疵修复 | 未知，见文件内容（文件未标注阶段字段） |
| [`A102_trade_freq_5min_filter_generalization.md`](./A102_trade_freq_5min_filter_generalization.md) | A102 | 5 分钟交易级别 + 过滤层泛化 | design（claude-cowork） |
| [`A106_trend_type_signal.md`](./A106_trend_type_signal.md) | A106 | 走势类型分类信号（盘整 / 趋势） | dev implemented |
| [`A107_scaffolding_docs_overhaul.md`](./A107_scaffolding_docs_overhaul.md) | A107 | 项目手脚架整改 + 基础库文档/示例完善 | dev implemented |

## 说明

- 阶段字段优先读取各文件首部的"阶段"记录；无明确字段时标注"未知，见文件内容"，不编造。
- 最新任务状态以仓库根目录 [`HANDOFF.md`](../HANDOFF.md) 为准。
- 本目录文档均为设计/审计/决策记录，**不是**面向新人的稳定参考文档；新人请先看 [`docs/reference/`](../reference/) 与仓库根目录 [`README.md`](../README.md)。
