# czsc_strategy 文档索引

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

本目录存放 `examples/czsc_strategy/` 子项目的说明性文档。按文档性质分为三类，阅读前请先确认自己需要的是哪一类：

| 目录 | 用途 | 稳定性 | 适合读者 |
|------|------|--------|----------|
| [`architecture/`](./architecture/) | 架构提案、长期演进设想、与其他系统的集成方案 | 不一定反映当前代码；作为设计讨论稿阅读 | 需要理解整体架构选择的开发者 |
| [`design/`](./design/) | 逐任务（Axxx）设计文档，含审计发现、方案、验收标准、决策记录 | 任务完成后作为历史记录保留；`design/README.md` 提供索引 | 需要追踪某项改动为何如此设计的开发者/reviewer |
| [`reference/`](./reference/) | 理论笔记、API 参考、最小可运行示例 | API 文档随代码维护；示例需在对应环境下可运行 | 新加入的开发者、需要快速确认公开 API 的 agent |

## 快速入口

- 想跑第一次回测 → 仓库根目录 [`README.md`](../README.md) 的"快速开始"小节。
- 想看 `chan_strategy/` 公开 API 清单 → [`reference/chan_strategy_api.md`](./reference/chan_strategy_api.md)。
- 想看最小 API 示例 → [`reference/quickstart_example.py`](./reference/quickstart_example.py)。
- 想了解 czsc vendor 来历 → [`reference/czsc_vendor_notes.md`](./reference/czsc_vendor_notes.md)。
- 想追踪设计任务 → [`design/README.md`](./design/README.md)。

## 说明

- `docs/` 本身不存放诊断报告；研究产出保留在 [`diagnostics/`](../diagnostics/)，受其自身的 `RESEARCH-ONLY / NOT PROMOTION EVIDENCE` 横幅约束。
- `tools/`（`handoff.py`、`sync_check.py`）在仓库根目录 [`AGENTS.md`](../AGENTS.md) 中说明；`skill_build/` 有自文档化的 `SKILL_DRAFT.md`，本任务范围未新增专门文档。
