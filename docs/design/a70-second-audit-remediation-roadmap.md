# A70-A72 — 第二轮第三方审核（66/100）修复路线图

## 背景

2026-07-15，`ai-stock-trading-reviewer` v2.0.0 对 `examples/czsc_strategy` 做了第二次审核（快照
`9af87290`，即 A65-A69 路线图完成后），综合评分 66/100（C，及格但仍是研究系统），较第一次审核
（57/100）有实质提升。审核报告给出 6 条优先级修复建议。

claude-code（本文档作者）与用户讨论后，将 6 条建议按"是否是可判定的代码任务"分类：

| # | 审核原文 | 分类 | 处理方式 |
|---|---------|------|---------|
| 1 | 默认回测报告强制标注 research/off，防止被误作生产绩效 | 可执行 | → **A70** |
| 2 | 把 A69 稳健性检查升级为机器可执行晋级门禁 | 可执行 | → **A71** |
| 3 | 扩大 `limit_halt_model="enforce"` 真实样本验证窗口 | 非代码任务 | 需等待 post-2026-04-24 窗口自然增长后重跑既有报告，不建任务 |
| 4 | 清理/重命名 `signals.py` 旧 `get_all_signals()` | 可执行 | → **A72** |
| 5 | 完成 20 个有效 SimNow 观察日前不得有"可扩容/可实盘"结论 | 已是既定纪律 | `simnow_20d_promotion_decision.md` 已显式 `ready_to_expand=False`；不建任务，仅作为持续遵守的红线 |
| 6 | 补齐当前环境依赖后重跑根目录 `tests`（缺 `polars`） | 超出本工作区范围 | 根仓库 `pyproject.toml` 的 `alpha` optional extra 依赖问题，与 `examples/czsc_strategy` 无关；不建任务 |

用户已确认按此范围执行（"先讨论范围，不急着建路线图" → 选定后授权 A70-A72），并授权本轮起
所有需要人工决策的点位按 claude-code 的推荐方案直接确认实施，无需逐项征询。

## 通用契约（全部三个任务共享）

- 单一真相：`examples/czsc_strategy/VERSION` / `CHANGELOG.md`；任何对外可见改动同一提交内 bump。
- 不得使用 2026-04-24 之前的数据做任何新参数选择；不得调优阈值以迎合某个历史区间的回测结果。
- 不得改动任何 SimNow 下单/撤单路径。
- 门禁：`python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"`、
  `python tools/sync_check.py`、`python tools/sync_check.py --root examples/czsc_strategy`、
  `run_next_work.ps1 -Preflight`（全部必须通过，无 `--no-gate`）。
- 现有 diagnostics 工作树中存在与本路线图无关的并发工作流改动（SimNow 观察文档、
  `run_next_work.ps1` 的历史 DB 默认更新逻辑等）——这是另一个并发工作流的在制品，**不得触碰、
  不得提交、不得回滚**，继续保持 A69 收尾时的处理方式（原样保留在工作树，不入本路线图的提交）。

---

## A70 — 默认回测报告强制标注 research/off 模式标签

### Rationale

审核发现：`chan_strategy/config.py` 的 `sizing_model="research"`、`limit_halt_model="off"`、
`portfolio_risk="off"` 都是默认值，直接跑默认回测会得到"百分比研究曲线 + 不约束涨跌停成交"的结果，
但当前控制台报告（`BacktestEngine.print_report`/`generate_report`，
[backtest_engine.py:631](../../examples/czsc_strategy/chan_strategy/backtest_engine.py:631)、
[backtest_engine.py:755](../../examples/czsc_strategy/chan_strategy/backtest_engine.py:755)）
只逐项打印 `sizing_model`/`portfolio_risk` 字段值，没有一个醒目的、无法忽略的"本次为研究基线，
非生产/可交易结果"标签。`diagnostics/backtest_matrix_report.py` 等 markdown 报告已有 A68 的
`_sizing_caveat` + `build_banner()`，但 `run_chan_backtest.py` 的原始 console 输出路径没有等价物。

### Semantics（本任务自行决定的具体实现，dev 落地前需在 Decision Log 记录确认）

- 在 `BacktestEngine.generate_report()` 中新增一个 `mode_label` 字段：
  - 当 `sizing_model=="research"` 且 `limit_halt_model=="off"` 且 `portfolio_risk=="off"` 时，
    `mode_label = "RESEARCH_BASELINE"`。
  - 否则，`mode_label` 列出实际启用的非默认项，例如
    `"PARTIAL_PRODUCTION_FEATURES(sizing=risk)"` 或
    `"PARTIAL_PRODUCTION_FEATURES(sizing=risk,limit_halt=enforce)"`（具体格式由 dev 决定，
    要求：能让阅读者立刻看出偏离了纯研究基线的具体维度，不需要主观解读）。
- `print_report()` 在最顶部（`"缠论择时策略回测报告"` 标题之后的第一行）打印
  `mode_label`，并在 `mode_label=="RESEARCH_BASELINE"` 时额外打印一行醒目提示，
  明确指出"本报告为研究基线，不构成生产/可交易证据"（措辞可参考现有
  `diagnostics/declassify_historical_reports.py::build_banner()` 的语气，但不要求逐字复用，
  因为这里是 console 输出而非 markdown）。
- `report['limit_halt_model']` 目前未出现在 `generate_report()` 返回的字典里
  （只有 `sizing_model`/`portfolio_risk`）——需要补上，否则 `mode_label` 无法准确反映
  `limit_halt_model` 状态。
- 不要求改动任何 markdown 报告脚本（`backtest_matrix_report.py` 等已有 A68 的等价机制），
  仅需覆盖 `BacktestEngine` 自身的 `generate_report`/`print_report` 这条路径（`run_chan_backtest.py`
  与其他直接调用 `BacktestEngine` 的脚本都会因此受益，无需逐个修改调用方）。

### Acceptance Criteria

- [ ] `generate_report()` 返回字典新增 `mode_label` 与 `limit_halt_model` 字段。
- [ ] `mode_label` 在纯默认配置（`sizing_model="research"`、`limit_halt_model="off"`、
      `portfolio_risk="off"`）下等于 `"RESEARCH_BASELINE"`；在任一项偏离默认时，能明确列出
      偏离的维度（具体字符串格式允许 dev 自行设计，但必须可判定、必须包含维度名）。
- [ ] `print_report()` 在报告最前面打印 `mode_label`；当为 `RESEARCH_BASELINE` 时额外打印一行
      不可忽略的免责提示。
- [ ] 新增单测：覆盖"全默认→RESEARCH_BASELINE"与"任一维度偏离→非 RESEARCH_BASELINE 且提示对应
      维度名"两种情形，直接断言 `generate_report()` 返回字典与 `print_report()` 的 stdout 内容
      （可用 `capsys`）。
- [ ] 不改变任何既有回测数值输出（`total_return_pct`、`sharpe_ratio` 等）——只新增字段和打印行，
      不影响任何既有断言既有测试的数值部分。
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` 通过。
- [ ] 两个 `sync_check.py` 门禁通过；`run_next_work.ps1 -Preflight` 通过。
- [ ] VERSION/CHANGELOG 按惯例 bump（本任务改变 `generate_report()`/`print_report()` 的输出行为，
      属于对外可见改动）。

---

## A71 — 把 A69 测量型门禁升级为机器可判定的晋级门禁

### Rationale

A69（已 `done`）刻意只做了"诚实测量"（`evaluate_oos_gate()`/`evaluate_perturbation_gate()`/
`cost_sensitivity_report.py`），没有发明任何硬性阈值，理由记录在 A69 自己的 HANDOFF Decision Log
里："不发明阈值，除非有充分理由"。第二次审核认为这仍不足够——测量结果目前仍需要人工解读，
不构成自动化的晋级/阻断信号。

**这是一个需要谨慎处理的任务**：随意选取阈值本身就是本项目一直在警惕的"阈值调优/迎合历史数据"
反模式。为避免此任务本身违反其试图修复的原则，本任务的阈值必须满足：
1. 阈值本身要么是**符号翻转**这种无需校准的定性判据（已有），要么是一个**极端、显然安全**的
   数值（例如"OOS 最大回撤不得超过 IS 最大回撤的 3 倍"这种量级的、任何合理策略都不该触发的
   保护性上限，而不是贴着当前观测值画的阈值）。
2. 阈值的选取理由必须写入 Decision Log，说明为什么这个数值不是拟合当前数据得出的。
3. 阈值只作为**门禁失败/警告**信号，不作为策略参数自动调整的输入。

### Semantics（本任务自行决定，dev 落地前需在 Decision Log 记录确认）

在三个已有测量函数基础上新增判定层，不改变测量函数本身的既有返回结构（避免破坏 A69 的既有
测试），而是新增一个上层"判定"函数：

- **OOS 门禁**：`evaluate_oos_gate()` 已返回 per-symbol 的 `sign_flip`/ratio 数据。新增
  `oos_gate_verdict(oos_result: dict) -> dict`（放在 `backtest_matrix_report.py`），规则建议
  （dev 可调整数值但必须遵守"极端安全阈值"原则并记录理由）：
  - 任一 symbol 出现收益符号翻转 → `status="fail"`。
  - 任一 symbol 的 `oos_drawdown / is_drawdown > 3.0`（且 `is_drawdown` 非零）→ `status="warn"`。
  - 否则 `status="pass"`。
- **参数扰动门禁**：同理在 `risk_param_sensitivity_report.py` 新增
  `perturbation_gate_verdict(perturbation_result: dict) -> dict`：任一 variant 符号翻转 →
  `"fail"`；否则 `"pass"`（这一项本身就是无需校准的定性判据，不需要额外数值阈值）。
  - 使用建议：这条本身已足够安全清晰，是本次三个门禁里风险最低的部分。
  - 若 `sign_flip` 检测的粒度导致误报（例如某 symbol 基线本就接近 0 收益，微小扰动即可"翻转"
    符号），dev 需要在 Decision Log 记录该边界情形是否已在现有测试数据下观测到，以及如何处理
    （例如豁免 `abs(baseline_ret) < epsilon` 的 symbol，epsilon 需给出理由，不是拟合出来的）。
- **成本敏感性门禁**：`cost_sensitivity_report.py` 目前只做测量。新增
  `cost_sensitivity_gate_verdict(result: dict) -> dict`，建议规则：2.0x 成本下若
  `total_return_pct` 符号翻转 → `"fail"`；若 2.0x 成本相对 1.0x 的 `total_return_pct` 相对跌幅
  超过一个极端安全上限（例如 90%，即成本翻倍后收益几乎归零/转负的量级）→ `"warn"`；否则
  `"pass"`。
- 三个 verdict 函数都应输出人类可读的 `reasons: list[str]`，并汇总一个顶层
  `overall_status = "fail" if any fail else ("warn" if any warn else "pass")`（每个诊断脚本
  各自独立汇总，不要求跨脚本合并）。
- 这些 verdict 函数是**报告层新增的判定结果**，不阻断/不修改回测执行本身；是否要将
  `overall_status=="fail"` 接入某个未来的"能否晋级"流程，超出本任务范围，留给后续任务。

### Acceptance Criteria

- [ ] 三个新增 verdict 函数落地，且都记录清晰的、非拟合式的阈值选取理由到本任务的 HANDOFF
      Decision Log。
- [ ] 每个 verdict 函数都有覆盖 `"pass"`/`"warn"`/`"fail"` 三态（或至少 `"pass"`/`"fail"`，若某
      门禁不设 `"warn"` 态需说明理由）的单测，使用构造的 fixture 数据，不依赖真实历史数据库。
- [ ] 不改变 A69 已有的 `evaluate_oos_gate`/`evaluate_perturbation_gate`/`cost_sensitivity_report`
      的既有返回结构或既有测试（新函数是新增层，不是替换）。
- [ ] 阈值本身不得依据 `diagnostics/` 目录下任何历史报告的具体观测数值反推得出——Decision Log
      需明确写出"这个数字为什么安全，而不是为什么符合当前观测"。
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` 通过。
- [ ] 两个 `sync_check.py` 门禁通过；`run_next_work.ps1 -Preflight` 通过。
- [ ] VERSION/CHANGELOG 按惯例 bump。

---

## A72 — 清理 `signals.py` 遗留 `get_all_signals()`，防止误导入生产路径

### Rationale

A66（README 重写）已经明确生产信号路径是 `chan_strategy/sell_signals.py::get_all_signals()`；
`chan_strategy/signals.py` 内部仍保留一个同名的 `get_all_signals()`
（[signals.py:857](../../examples/czsc_strategy/chan_strategy/signals.py:857)），且调用了已废弃
的二买/三买实现。已确认的真实调用方（非测试）：
`skill_build/build_mapping.py:47`、`skill_build/scripts/analyze_symbol.py:61` ——两者都从
`chan_strategy.signals` 而非 `chan_strategy.sell_signals` 导入 `get_all_signals`，是审核指出的
"误导入生产路径"风险的具体体现。

### Semantics

- 将 `chan_strategy/signals.py` 中的 `get_all_signals()` 重命名为 `get_legacy_signals()`
  （函数体不变，仅改名 + docstring 补充"legacy, superseded by
  `chan_strategy.sell_signals.get_all_signals`"说明）。
- 在原名 `get_all_signals` 位置保留一个薄包装/别名，调用时通过 `warnings.warn(...,
  DeprecationWarning, stacklevel=2)` 显式告警，内部转发到 `get_legacy_signals()`——不删除旧入口
  （避免破坏尚未审查到的隐藏调用方），但任何新代码路径都不应再直接调用它。
- 更新两个真实调用方 `skill_build/build_mapping.py`、`skill_build/scripts/analyze_symbol.py`，
  改为显式调用 `get_legacy_signals()`（如果这两个脚本本身的用途确实需要旧的二买/三买逻辑，
  保留调用旧实现但去掉告警触发；如果两者其实应该改用生产路径
  `sell_signals.get_all_signals`，dev 需要读一下这两个脚本的实际用途再决定——**这是本任务内需要
  自行判断并记录到 Decision Log 的点**，不是预设好的答案）。
- 测试文件 `tests/unit/test_remaining_coverage.py:155`（`base_signals.get_all_signals(...)`）与
  `test_second_buy_real_path.py:19` 是在特意测试旧实现本身，应改为调用 `get_legacy_signals()`
  （不触发告警，测试的是遗留行为本身，不是误用）。

### Acceptance Criteria

- [ ] `chan_strategy/signals.py` 新增 `get_legacy_signals()`（原函数体），原 `get_all_signals()`
      变为触发 `DeprecationWarning` 的薄包装。
- [ ] `skill_build/build_mapping.py`、`skill_build/scripts/analyze_symbol.py` 的实际用途已被读过
      并记录到 Decision Log；按判断结果要么切到 `get_legacy_signals()`（消除告警），要么切到
      `sell_signals.get_all_signals()`（切到生产路径）——两种都可接受，但必须说明理由。
- [ ] 涉及测试旧实现本身的测试文件（`test_remaining_coverage.py`、`test_second_buy_real_path.py`
      等）改为直接调用 `get_legacy_signals()`，不产生告警噪音。
- [ ] 新增至少一个测试断言：调用旧名 `get_all_signals()` 会触发 `DeprecationWarning`
      （`pytest.warns(DeprecationWarning)`），且返回值与 `get_legacy_signals()` 一致（转发正确）。
- [ ] 不改变任何信号计算逻辑本身——纯粹是改名 + 告警 + 调用方更新，任何既有测试的数值断言必须
      保持字节级不变。
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` 通过（允许新增的
      `DeprecationWarning` 相关测试，但不允许既有测试因未预期的告警而失败——若 pytest 配置有
      "warnings as errors"，需要针对这一个告警显式 `filterwarnings` 放行）。
- [ ] 两个 `sync_check.py` 门禁通过；`run_next_work.ps1 -Preflight` 通过。
- [ ] VERSION/CHANGELOG 按惯例 bump。

---

## Dev Prompt（三个任务通用）

1. 先读本设计文档对应任务的完整 Rationale/Semantics 章节，再读所引用的源码行号确认当前状态未
   漂移。
2. 若发现本文档引用的行号/内容与当前代码不符，以当前代码为准，并在 Decision Log 记录差异。
3. 严格限定 diff 范围在本任务 Semantics 所列文件内；不得顺带"顺手"修改其他审核条目（尤其是
   #3/#5/#6 已明确不建任务，不要在这三个任务的实现里夹带处理它们）。
4. 完成后写 Manual Verification 区块（真实运行的命令与输出），再触发
   `python tools/handoff.py next --actor kimi-code`。

## Review Checklist（三个任务通用）

- diff 范围是否精确匹配 Semantics 所列文件，有无夹带无关改动（参考 A69 教训：commit 前用
  `git status --short` 核对，若发现无关并发工作流文件被扫入暂存区，先 `git reset` 拆分）。
- 新增测试是否真的覆盖了 Acceptance Criteria 里列出的每一态。
- A71 的阈值选取理由是否在 Decision Log 中站得住脚（不是拟合当前观测值）。
- 是否有 VERSION/CHANGELOG 同步 bump。
