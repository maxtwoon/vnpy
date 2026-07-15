# Changelog — czsc_strategy 诊断工作流

版本单一真相：`VERSION` 文件。每个对外可见改动 = 代码 + 版本 bump + 本文件一条 + 相关文档，同一提交完成。

## 0.2.3 — 2026-07-15

- A66 重写 `README.md` 以反映当前策略实现。
  - 将 README 主题从已废止的 2021-2022 A 股"波段战法"原型更新为当前 `chan_strategy/` 期货 CTA 实现。
  - 明确生产信号路径为 `chan_strategy/sell_signals.py` 的 `get_all_signals()`，并说明 `signals.py` 内部同名函数为兼容遗留实现。
  - 全部默认参数（周期、标的、仓位、止损、超时、回测窗口、成本）引用 `chan_strategy/config.py` 的当前真实值。
  - 新增 `RESEARCH-ONLY / NOT PROMOTION EVIDENCE` 顶部横幅，符合 A54 建立的报告免责声明风格。
  - 原 README 内容完整归档至 `README.legacy.md`，并在新 README 中给出明确指针，未静默删除历史记录。
  - 不改动任何 `chan_strategy/*.py` 文件、诊断脚本或策略参数。

## 0.2.2 — 2026-07-14

- A60 project-level VERSION/CHANGELOG gate + banner-exemption config cleanup.
  - 新增 `project_version_freshness` 门禁：`chan_strategy/config.py` 的 `STRATEGY_CONFIG` / `BACKTEST_CONFIG` 顶层键被修改时，同一提交必须 touch `VERSION` 或 `CHANGELOG.md`。
  - 将 `tools/sync_guardian/sync_check.py` 中硬编码的 `audit_issue_diagnostics_*` banner 豁免迁移到 `.synccheck.yml` 的 `skip` 配置（glob 模式）。
  - 明确声明 `diagnostics/archive/` 为 banner 检查豁免目录（历史 HANDOFF 归档，非活诊断报告）。
  - 本版本同时补齐 A52/A53/A54 的 retroactive backfill（见下）。

### Retroactive backfill — documented by A60 on 2026-07-14 (VERSION was not bumped when these originally shipped)

- A52 连续合约 rollover-window stat tagging：新增 `STRATEGY_CONFIG["rollover_stat_tagging"] = "off" | "on"`，在 `Position.pairs` 中追加 `is_rollover_window` 布尔字段，不改变成交、价格或持仓。
- A53 config/signal 单一来源清理：新增 5 个 first-buy research gates（`enable_1buy_symbols` / `block_1buy_daily_down` / `block_1buy_daily_not_up` / `block_1buy_daily_below_zs` / `trailing_overrides`），并明确 `equity_mode="compound"` 仅文档化、未实现（会 raise `NotImplementedError`）。
- A54 report-disclaimer hygiene + sync_check gate：新增 `diagnostics/*.md` RESEARCH-ONLY banner 检查；所有活诊断报告补齐 `<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->` 横幅；`audit_issue_diagnostics_*.md` 与归档区按配置豁免。

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
