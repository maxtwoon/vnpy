# Changelog — czsc_strategy 诊断工作流

版本单一真相：`VERSION` 文件。每个对外可见改动 = 代码 + 版本 bump + 本文件一条 + 相关文档，同一提交完成。

## 0.2.1 — 2026-07-13

- A56 `structural_atr` 盈利保护缺口：决策为文档澄清（Option B），不修改行为。
  - 在 `chan_strategy/config.py` 的 `exit_model` 注释中显式披露：ATR trailing 仅在部分止盈事件触发后才会评估；未触及方向目标的头寸仅依赖固定止损和超时。
  - 在 `docs/design/a38-phase-contracts-p2-p8.md` 新增 2026-07-13 addendum，说明 P8a 原文 "then trail the remainder" 是顺序语义，保留原文不变。
  - 在 `diagnostics/exit_model_report.py` 新增 Methodology 章节，诚实说明 `structural_atr` 的 ATR trailing 前置条件。
  - 不改动 `positions.py`、不调整阈值、不影响 `exit_model="legacy"` 基线。

## 0.2.0 — 2026-07-13

- A51 涨跌停/停牌填充标记（tagging-only）：新增 `STRATEGY_CONFIG["limit_halt_model"] = "off" | "aware"`。
  - `"off"`（默认）保持历史基线字节一致。
  - `"aware"` 为每笔 `Position.pairs` 记录追加只读的 `is_entry_at_limit` / `is_exit_at_limit` 布尔字段，不改动开仓/平仓、成交价、成交量、持仓时间。
  - 复用 A50 的 `SYMBOL_LIMIT_CONFIG`（抽至 `chan_strategy/limit_config.py` 作为单一真相）。
  - 新增完整回测等价快照测试（off 模式）与 aware 标记/等价单测。
  - 更新 A50 诊断报告 Methodology，说明 `limit_halt_model="aware"` 可作为逐笔标记选项。

## 0.1.0 — 2026-07-03

- 接入 sync-guardian 门禁：`VERSION` 单一真相 + `.synccheck.yml` + `tools/sync_check.py` + `tools/handoff.py` + `HANDOFF.md` 多 agent 交接。
- A31 基线：`diagnostics/audit_issue_diagnostics.py` 只读诊断（H1/H2/H3/H4/M1）与 14 项单测（外部复核通过，见 diagnostics/WORK_LOG.md A31 节）。
- 启动 A32 设计：审核问题数据接入与三项复核瑕疵修复（见 docs/design/A32_audit_issue_data_feed.md）。
