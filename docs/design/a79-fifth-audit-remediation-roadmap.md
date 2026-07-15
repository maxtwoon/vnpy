# A79-A81 — 第五轮第三方审核（70/100，持平）修复路线图

## 背景

2026-07-16，codex 对 `examples/czsc_strategy` 做了第五次审核（当前 git HEAD `5978714b`，A76-A78
完成后），综合评分 70/100（与第四轮持平），**无致命项**，6 条🟠中、3 条🟢低。完整报告：
`diagnostics_codex_audit_report.md`（仓库根目录）。

**重要背景说明（本轮路线图与前四轮的关键差异）**：评分已连续两轮持平在 70 分。剩余的中严重度问题
里，有相当一部分是"围绕研究基线 vs 正式评估这同一主题反复换角度提出"，而不是全新的、独立的缺陷——
例如 #1（默认入口仍是研究基线）本质上是 A70/A74/A78 已经系统性处理过的同一问题在不同措辞下再次出现。
本路线图会：(a) 挑出真正新增的、可界定的技术缺口做成任务；(b) 对"换个说法但本质已解决"的项目做
说明而非重新开发；(c) 继续标注架构级/非代码任务为不建任务。**完成本路线图后，若评分仍无法达到 75
且部分中严重度问题源于"设计上刻意保留 opt-in 而非默认"这一房屋风格本身，claude-code 会如实向用户
汇报这一现实，而非无限期开新路线图**。

### 问题范围裁定

| # | 审核原文摘要 | 分类 | 处理方式 |
|---|-------------|------|---------|
| 1 | 默认公开入口仍是研究基线 | 已系统性处理，本轮做最后的前置强化 | → **A81**（部分） |
| 2 | 连续合约拼接未做价差调整/重拼 | **已有 A73 的 `rollover_contribution_report.py` 满足"量化换月跳点贡献"这个具体子诉求** | 不建新任务，见下方说明 |
| 3 | 日线默认自然日聚合，交易日聚合(`trading_calendar`)未默认启用 | 可执行，复用既有基础设施 | → **A79** |
| 4 | 组合风控与 risk sizing 仍互斥 | 架构级，不建任务，理由同前三轮 | 不建任务 |
| 5 | verdict 函数未接入统一 acceptance gate | 可执行 | → **A81** |
| 6 | 数据解析失败行静默跳过，非 fail-closed | 可执行 | → **A80** |
| 🟢低 1-3 | 旧入口命名/README 局部说明/历史报告归档 | 规范性，不建任务 | 已有护栏（A75）覆盖核心风险，其余是打磨 |

**#2 不建新任务的理由（重要，避免误判为"忽略高优先级建议"）**：审核给出的具体建议是"至少提供一份
量化换月跳点对信号/止损/收益贡献的报告"——**这正是 A73 已经交付的 `diagnostics/rollover_contribution_report.py`
在做的事**（按品种拆分换月窗口内/外交易的收益贡献、胜率、平均盈亏）。审核报告在本轮似乎没有识别到
A73 的产物已经满足这个具体子诉求（审核建议里"价差调整/重拼"这个更大的诉求确实仍未做，但那属于第一轮
就已经裁定为"需要真实外部数据源或大架构工作"的范畴，参见 A73 路线图的裁定说明，不重复展开）。因此
本轮不为此新增任务，只需确认 A73 的报告仍然可运行、仍然准确即可（不要求新代码）。

## 通用契约（A79-A81 共享）

同前几轮：单一真相 `VERSION`/`CHANGELOG.md`；不使用 2026-04-24 之前数据做新参数选择；不改动 SimNow
下单/撤单路径；门禁全部通过；提交前核对无关并发工作流文件未被暂存；**Manual Verification 用字面
`## Manual Verification` 标题**（A77 曾因缺少这个字面标题被打回，即使内容已经记录在 Decision Log
里也不算数）。

---

## A79 — 正式评估默认启用交易日聚合（`daily_agg="trading_calendar"`）

### Rationale

`chan_strategy/data_adapter.py:46` 的 `_resample_daily_trading_calendar()` 和
`config.py:81` 的 `"daily_agg": "natural" | "trading_calendar"` 开关**均已完整实现**——这不是
"需要新功能"的缺口，而是和 A74/A76/A78 完全相同的模式："已有更严谨的可选实现，正式评估应该默认
启用它"。

### Semantics

- 在 `formal_evaluation_config()`（已被 A74/A76/A78 扩展三次）的覆盖字典中追加第五项：
  `daily_agg = "trading_calendar"`，退出时恢复原值，遵循完全相同的 save/restore 模式。
- 新增测试：验证覆盖生效、异常路径下正确恢复、非正式评估路径行为不变。

### Acceptance Criteria

- [ ] `formal_evaluation_config()` 追加覆盖 `daily_agg = "trading_calendar"`，成功/异常路径均正确
      恢复，新增测试验证（遵循 A74/A76/A78 已建立的测试模式）。
- [ ] 非正式评估路径的所有既有测试通过，无需修改任何既有断言。
- [ ] 门禁通过（同通用契约）。
- [ ] VERSION/CHANGELOG bump。

---

## A80 — 数据适配器无法解析行的 fail-closed 计数与报告

### Rationale

`data_adapter.py:404-407` 对无法解析的时间戳执行 `continue  # 跳过无法解析的行`，跳过的行数目前
既不计数也不上报。若数据库存在异常时间戳，回测会静默丢数据而不失败，可能改变 K 线合成、信号边界、
交易笔数。

### Semantics

- 在跳过无法解析行的代码路径中追加计数（不改变跳过行为本身——仍然跳过，不尝试修复或猜测数据）。
- 将跳过行数向上传递到 `BacktestEngine`，追加到 `generate_report()` 输出的字典中（字段名 dev 决定，
  建议 `unparseable_rows_skipped`），无论正式评估还是默认路径都应包含此字段（这是诚实报告底层数据
  质量，不属于"正式评估才启用"的特性，因此不通过 `formal_evaluation_config()` 覆盖，而是始终生效——
  需要在 Decision Log 记录这个"始终生效 vs 仅正式评估生效"的判断理由）。
- **不要求**在跳过行数 > 0 时让回测失败或阻断——本任务只做诚实计数/上报，不发明新的 fail-closed
  阈值行为（若 dev 认为阻断是合理的下一步，可以在 Decision Log 提议，但不在本任务范围内实现，避免
  未经充分设计就引入新的"多少行才算太多"这类阈值判断）。

### Acceptance Criteria

- [ ] 数据适配器对无法解析行的计数被追踪并可从加载结果中获取。
- [ ] `BacktestEngine.generate_report()` 输出字典包含跳过行数字段（正常路径和正式评估路径均包含，
      因为这是数据质量诚实报告，不是仅正式评估的特性——在 Decision Log 记录此判断）。
- [ ] 新增测试：构造含无法解析时间戳的数据集，验证计数准确；构造干净数据集，验证计数为 0。
- [ ] 不改变现有跳过行为本身（仍然跳过，不新增失败/阻断逻辑）。
- [ ] 门禁通过（同通用契约）。
- [ ] VERSION/CHANGELOG bump。

---

## A81 — 统一验收门禁函数 + 正式入口前置强警示

### Rationale

两条相关中严重度问题合并处理：

1. OOS/成本/参数扰动都已有 verdict 函数（A71），但没有一个统一入口把它们的 `overall_status` 汇总成
   单一的"是否可以晋级"判断——审核指出这是"流程风险"：报告生成了，但 fail 信号可能被忽略。
2. `run_chan_backtest.py`（默认公开入口）目前只在报告内部显示 `mode_label`，没有在运行**最前面**就
   给出足够醒目的警示——审核建议在默认入口的最前面就前置强警示，并把 `run_formal_evaluation.py` /
   `assert_not_research_baseline()`（A78）确立为晋级/对外报告的唯一合法路径。

### Semantics

- 新增一个统一验收门禁函数（放在 `chan_strategy/backtest_engine.py` 或新的
  `diagnostics/acceptance_gate.py`，dev 决定并记录理由），接受 OOS/成本/参数扰动三个 verdict 的
  `overall_status`，加上 `mode_label`（通过 A78 的 `assert_not_research_baseline` 复用），综合给出
  一个 `"pass"|"warn"|"fail"` 的顶层判断——任一输入为 `"fail"` 则顶层 `"fail"`；`mode_label ==
  RESEARCH_BASELINE` 直接顶层 `"fail"`（复用 A78 的判断逻辑，不重复实现）。
- `run_chan_backtest.py` 在 `main()` 函数最开始（在任何回测执行之前）打印一行不可忽略的警示，说明
  这是研究基线入口，正式评估请使用 `run_formal_evaluation.py`。
- 不要求把这个统一门禁函数接入任何现有的 SimNow 晋级脚本或 `simnow_20d_promotion_decision.md`
  流程——那是独立的 SimNow 观察工作流范畴，超出本任务范围（与 A78 的边界裁定一致）。

### Acceptance Criteria

- [ ] 新增统一验收门禁函数，正确综合 OOS/成本/参数扰动三个 verdict 的 `overall_status` 与
      `mode_label`，测试覆盖全 pass、任一 fail、`mode_label=RESEARCH_BASELINE` 三种情形。
- [ ] `run_chan_backtest.py` 的 `main()` 函数最前面新增不可忽略的研究基线警示，指向
      `run_formal_evaluation.py`。
- [ ] 不改变任何既有回测数值输出；不改变 `run_chan_backtest.py` 除新增警示打印之外的行为。
- [ ] 门禁通过（同通用契约）。
- [ ] VERSION/CHANGELOG bump。

---

## Dev Prompt / Review Checklist（三个任务通用）

同前几轮的通用要求。**A77 教训**：Manual Verification 必须是字面的 `## Manual Verification` 标题，
不能只写进 Decision Log。commit 前核对无关并发工作流文件未被暂存。
