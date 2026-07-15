# A76-A78 — 第四轮第三方审核（70/100）修复路线图

## 背景

2026-07-15，codex 对 `examples/czsc_strategy` 做了第四次审核（当前 git HEAD `c4e856b6`，A73-A75
完成后），综合评分 70/100（B，较第三次 67/100 提升），**无致命项**，但出现了 1 条 🔴高 严重度问题
（前几轮都只有🟠中），另有 5 条🟠中、2 条🟢低。完整报告：`diagnostics_codex_audit_report.md`
（仓库根目录，未纳入版本控制的临时审核产物）。

user 的标准指令（持续适用）：不停迭代直至评分 > 75 且无中以上问题，人工决策点按 claude-code 自己的
推荐方案直接执行。

### 问题范围裁定

| 严重度 | # | 审核原文摘要 | 处理方式 |
|-------|---|-------------|---------|
| 🔴高 | 1 | 888 连续合约 raw splice 仍进入生产信号路径 | → **A76**（正式评估模式下门控换月窗口开仓） |
| 🟠中 | 1 | 默认回测入口仍是研究基线；建议禁止 promotion 报告消费 `RESEARCH_BASELINE` | → **A78**（部分处理，见下） |
| 🟠中 | 2 | 组合级风控与真实手数模型不能同时启用 | 不建任务，架构级，理由同 A73 路线图 |
| 🟠中 | 3 | 默认止损仍按收盘价检查，intrabar 只是可选模式 | → **A78** |
| 🟠中 | 4 | README 研究开关列表漏掉 `limit_halt_model="enforce"` | → **A77** |
| 🟠中 | 5 | 诊断脚本 docstring 仍写"无任意阈值"，但已有 verdict 阈值 | → **A77** |
| 🟢低 | 1 | 旧 A 股原型和兼容信号入口仍保留（已有护栏） | 不建任务，风险已被 A75 的护栏测试覆盖，纯规范性问题 |
| 🟢低 | 2 | 涨跌停临时扩板来源未独立验证 | 不建任务，需要人工核对交易所公告原文，非代码任务 |

**🟠中#2 不建任务的理由**：与第三轮路线图 A73 中"组合风控与 risk sizing 融合"的裁定完全相同——这是
一个需要独立设计文档的架构级工作，不适合塞进 under-specified 任务，本路线图不重复展开。

## 通用契约（A76-A78 共享）

同前几轮：单一真相 `VERSION`/`CHANGELOG.md`；不使用 2026-04-24 之前数据做新参数选择；不改动 SimNow
下单/撤单路径；门禁全部通过；提交前核对无关并发工作流文件未被暂存。

---

## A76 — 正式评估模式下门控换月窗口开仓（解决 🔴高 问题）

### Rationale

`RISK_NOTE_888_SPLICE.md` 明确：888 连续合约是未复权原始拼接，换月跳变会被缠论笔/中枢/背驰当作真实
价格结构，可能产生假突破、假止损、假背驰信号。A52 的 `rollover_stat_tagging`（已 `done`）和 A73 的
`rollover_contribution_report.py`（已 `done`）都只是**测量/标记**换月窗口的影响，没有任何机制真正
阻止换月窗口内开仓——这正是审核指出的核心缺口。

**claude-code 已确认可复用的现有基础设施**（`chan_strategy/backtest_engine.py`）：
- `_rollover_excluded_dates()`（[backtest_engine.py:645](../../examples/czsc_strategy/chan_strategy/backtest_engine.py:645)）
  已经能返回换月排除窗口内的日期集合（best-effort，元数据缺失时优雅降级为空集，不会让回测失败）。
- `rollover_config.py` 的 `_detect_transitions()`/`_exclusion_dates()`/`_pair_in_exclusion_window()`
  是底层检测逻辑，已被 A52 使用，无需重新发明换月检测算法。

### Semantics（dev 需在动手前决定并记录）

- 新增一个只在**正式评估模式**下生效的门控机制（不是全局默认行为，遵循 house style 的
  byte-identical-by-default 原则）：在 `A74` 已有的 `formal_evaluation_config()` 覆盖范围内，追加
  第三个覆盖行为——在换月排除窗口内的交易日，阻止新开仓（不影响窗口内已有持仓的正常止损/超时/平仓
  逻辑，只阻止新开仓，避免"半途改变已有持仓的既定风控规则"这种更复杂、更易出错的行为）。
- 具体实现位置由 dev 决定，但建议的落点：在 `_get_operate()` 或开仓判定路径中增加一个检查——若当前
  bar 的日期在 `_rollover_excluded_dates()` 返回的集合中，且新的门控开关处于启用状态，则本 bar 拒绝
  开仓（可以复用 A67 `limit_halt_model="enforce"` 引入的
  `Position._reject_fill_at_limit()` 风格的"本 bar 拒绝"模型，而不是引入新的跨 bar 状态机）。
- 是否需要一个独立的 `STRATEGY_CONFIG` 键（例如 `rollover_open_gating = "off"|"on"`，默认
  `"off"`）由 formal_evaluation_config() 临时启用，还是直接把这个行为无条件绑定进
  formal_evaluation_config()（不新增独立开关），由 dev 决定并记录理由——两种都可接受，但优先考虑
  "新增独立开关 + formal evaluation 默认启用"这个方案，因为它给未来只想单独测试这一个特性的场景
  留了空间，且与 A51/A67/A52 一路建立的"每个特性都有自己的显式开关"惯例一致。
- **不要求**对已拼接的历史价格做任何前复权/后复权/价差平滑——审核给出的两个选项里，dev 采纳的是
  "门控开仓"这个更小、更可验证的选项，不是"价格调整"。

### Acceptance Criteria

- [ ] 正式评估模式（`run_formal_evaluation()`/`formal_evaluation_config()`）下，换月排除窗口内的
      交易日不会产生新开仓（多头或空头）；窗口外或非正式评估模式下行为完全不变。
- [ ] 换月窗口内已持有的仓位，其止损/超时/平仓逻辑不受本任务影响（不引入"窗口内强制平仓"这类新
      行为，除非 dev 有充分理由并在 Decision Log 记录后采纳更激进的方案）。
- [ ] 新增回归测试：构造一个数据集，使某个信号本应在换月窗口内某一 bar 触发开仓，验证在正式评估
      模式下该开仓被拒绝，在非正式评估模式（默认路径）下开仓正常发生。
- [ ] 元数据缺失/换月检测失败时的降级行为与 A52 一致（不让回测失败，退化为不门控，不静默产生
      误导性的"看起来生效了"的假象——需要在报告或日志中可辨识地体现"本次运行未能确认换月窗口"）。
- [ ] 不改变非正式评估路径的任何既有测试断言（数值必须字节级不变）。
- [ ] 门禁通过（同通用契约）。
- [ ] VERSION/CHANGELOG bump。

---

## A77 — 文档漂移修正（README 涨跌停开关 + 诊断脚本 docstring）

### Rationale

两处纯文档/注释层面的漂移，均已被审核明确指出且行不言之有据：
1. `README.md:159-165` 的开关列表写 `limit_halt_model: "off" | "aware"`，遗漏了 A67 引入、A70/A74
   已经在用的 `"enforce"`。
2. `diagnostics/cost_sensitivity_report.py:47-51`/`diagnostics/risk_param_sensitivity_report.py:101-105`
   的函数 docstring 仍写"这是纯测量报告，不发明任何 pass/fail 阈值"，但 A71 已经在同文件里加了
   `cost_sensitivity_gate_verdict()`/`perturbation_gate_verdict()`，两者确实有 `COST_RELATIVE_RETURN_WARN_PCT`
   等阈值。

### Semantics

- README 更新 `limit_halt_model` 开关说明为 `"off" | "aware" | "enforce"`，并简要提及
  `run_formal_evaluation.py` 是正式评估入口（呼应 A74）。
- 两个诊断脚本的相关函数（`run_cost_sensitivity()`/`evaluate_perturbation_gate()`）docstring
  改为区分两层：底层测量函数（`run_cost_sensitivity()`/`evaluate_perturbation_gate()` 本身）确实
  不设阈值；上层 verdict 函数（`cost_sensitivity_gate_verdict()`/`perturbation_gate_verdict()`）
  才引入保护性阈值——措辞需清楚点出这个分层，不能笼统地说"整个模块不设阈值"。
- 纯文档改动，不改变任何代码行为。

### Acceptance Criteria

- [ ] README 涨跌停开关列表更新为三态，且提及 `run_formal_evaluation.py`。
- [ ] 两个诊断脚本相关函数的 docstring 更新，清楚区分"测量层无阈值"与"verdict 层有保护性阈值"。
- [ ] 不改变任何函数行为、返回值结构或既有测试断言。
- [ ] 门禁通过（同通用契约）。
- [ ] VERSION/CHANGELOG bump（文档修正也需要按惯例记录，即使不改变代码行为）。

---

## A78 — 正式评估默认改为 intrabar 止损 + 晋级报告消费护栏

### Rationale

两条中严重度问题，都与"正式评估应该比研究基线更贴近真实可交易证据"这个主线相关，合并到一个任务里
处理，避免第三次单独修改 `formal_evaluation_config()`：

1. 默认止损执行模型是 `"close"`（只在收盘价检查止损），`"intrabar"`（使用 bar 内最高/最低价判断
   触发）是可选模式——正式评估应该默认使用更保守的 `intrabar`，因为期货存在跳空和 bar 内穿透，
   `close` 模型可能让回测止损晚于真实触发时点。
2. 审核建议"禁止任何 acceptance/promotion 报告消费 `mode_label == RESEARCH_BASELINE` 的输出"——
   这是一个轻量级的护栏：新增一个校验函数/测试，若某个报告/晋级判定逻辑读取了标注为
   `RESEARCH_BASELINE` 的 `mode_label` 却仍然产生"可晋级/可实盘"结论，应该失败。

### Semantics

- 在 `formal_evaluation_config()`（A74）的覆盖字典中追加 `stop_execution_model = "intrabar"`（连同
  已有的 `sizing_model="risk"`、`limit_halt_model="enforce"`，以及 A76 若已落地的换月门控开关）。
- 新增单测验证：`run_formal_evaluation()`/`formal_evaluation_config()` 覆盖期间
  `STRATEGY_CONFIG["stop_execution_model"] == "intrabar"`，且退出后正确恢复。
- 护栏机制：新增一个轻量函数（例如 `assert_not_research_baseline(report: dict)`，放在合适的
  diagnostics 共享模块或 `chan_strategy/backtest_engine.py`），若 `report.get("mode_label") ==
  "RESEARCH_BASELINE"` 则抛出异常——供任何未来的"晋级/acceptance"脚本调用。本任务不要求改造现有
  的 `simnow_20d_promotion_decision.md` 或 SimNow 晋级判定逻辑去调用它（那是 SimNow 观察工作流的
  范畴，超出本任务），只需要提供这个可复用的护栏函数本身，并有测试证明其行为正确。

### Acceptance Criteria

- [ ] `formal_evaluation_config()` 追加覆盖 `stop_execution_model = "intrabar"`，覆盖后正确恢复
      （包括异常路径），新增测试验证。
- [ ] 新增 `assert_not_research_baseline()`（或等效命名，dev 决定）函数，对
      `mode_label == "RESEARCH_BASELINE"` 的报告抛出异常，对非该值的报告不抛异常；新增测试覆盖
      两种情形。
- [ ] 不改变非正式评估路径的任何既有测试断言。
- [ ] 门禁通过（同通用契约）。
- [ ] VERSION/CHANGELOG bump。

---

## Dev Prompt / Review Checklist（三个任务通用）

同 A70-A75 路线图的通用要求：先读设计文档对应任务段落并核对当前代码是否漂移，diff 范围严格限定，
commit 前核对无关并发工作流文件未被暂存，Manual Verification 区块必须包含。A76 尤其需要 review
仔细核对"门控只影响正式评估模式下的新开仓，不影响已有持仓的风控逻辑"这条边界是否真的守住。
