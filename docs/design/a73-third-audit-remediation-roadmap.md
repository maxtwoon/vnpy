# A73-A75 — 第三轮第三方审核（67/100）修复路线图

## 背景

2026-07-15，codex 使用 `ai-stock-trading-reviewer` 方法论对 `examples/czsc_strategy` 做了第三次审核
（当前 git HEAD `4211f83e`，即 A70-A72 完成后），综合评分 67/100（C，较第二次 66/100 略有提升），
**无致命项**，6 条 🟠中 严重度问题（无 🔴高）。完整报告：`diagnostics_codex_audit_report.md`（仓库根目录，
未纳入版本控制的临时审核产物，正式路线图内容以本设计文档为准）。

user 的标准指令（本轮及后续轮次均适用，已预授权）：不停迭代直至评分 > 75 且无中以上问题，人工决策点按
claude-code 自己的推荐方案直接执行，不再逐项征询。

### 6 条中严重度问题的范围裁定

| # | 审核原文摘要 | 分类 | 处理方式 |
|---|-------------|------|---------|
| 1 | 默认回测仍是研究基线（`sizing_model="research"`） | 部分可执行 | → **A74**（正式评估入口默认切到 risk+enforce，而非改动库默认值） |
| 2 | 组合风控默认关闭且与 risk sizing 互斥（`NotImplementedError`） | 架构级，超出单任务范围 | 不建任务，见下方说明 |
| 3 | 样本外证据不足（历史 OOS 窗口已被声明为污染证据） | 非代码任务 | 需要真实日历时间推进（2026-04-24 之后的增量数据自然积累），不建任务 |
| 4 | 默认 `limit_halt_model="off"` 不拦截涨跌停 | 部分可执行 | → **A74**（同上，合并处理） |
| 5 | 连续合约未复权换月跳变 | 可执行（复用 A52 既有 tagging 基础设施） | → **A73** |
| 6 | 涨跌停规则未覆盖交易所临时调参/特殊合约 | 需要外部数据源，本仓库不具备 | 不建任务，见下方说明 |
| 7 | 废弃信号入口仍存在（`signals.py` 仍保留 `get_legacy_signals`） | 可执行 | → **A75** |

**未建任务的三项，逐一说明理由：**

- **#2（组合风控与 risk sizing 融合）**：`portfolio_engine.py:609-615` 的 `NotImplementedError` 是
  A53 就已明确记录的、有意为之的未实现状态（组合层用权重记账，risk sizing 用手数/保证金记账，两者数据
  模型不兼容）。真正统一两套记账体系是一个需要独立设计文档、可能跨越多个任务的架构级工作，不适合作为
  本路线图下的一个"under-specified, decide-then-implement"任务塞入 —— 强行压缩会重演本项目一直警惕的
  "corner-cut implementation"反模式。**建议作为独立的、需要用户明确立项的大型工作**，本路线图不代为
  展开。
- **#3（真实样本外证据）**：审核原文自己承认"历史 OOS 窗口已被反复用于参数选择，只能作为负面/受污染证据"。
  解决这个问题的唯一诚实路径是：冻结当前参数与代码，让真实日历时间在 2026-04-24 之后继续推进，积累一段
  从未被用来调参的增量数据，然后单独产出一份"未参与调参"的 OOS 报告。这不是任何代码改动能加速的，与第一
  轮路线图的"SimNow 20 日观察"同理——**这是等待，不是开发任务**。
- **#6（交易所涨跌停/保证金按日期动态参数表）**：审核建议"接入按日期/合约的交易所保证金和涨跌停参数
  表"——这需要一个真实、可审计的外部数据源（交易所逐日公告的涨跌停幅度、保证金比例调整记录），本仓库当前
  没有这样的数据源，也没有获取渠道的信息。在没有真实数据源的前提下，任何"实现"都只能是继续用近似值或占位
  符，不会真正解决审核指出的问题，反而可能制造"看起来解决了"的假象。**留待用户提供数据源接入方式后再立项**。

## 通用契约（A73-A75 共享）

- 单一真相：`examples/czsc_strategy/VERSION`/`CHANGELOG.md`；对外可见改动同一提交内 bump。
- 不使用 2026-04-24 之前的数据做任何新参数选择；不调优阈值以迎合某段历史回测结果。
- 不改动任何 SimNow 下单/撤单路径。
- 门禁：`python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"`、两个
  `sync_check.py`、`run_next_work.ps1 -Preflight`，全部必须通过，无 `--no-gate`。
- 工作树中存在与本路线图无关的并发工作流改动（SimNow 观察文档、`run_next_work.ps1` 的历史 DB 默认更新
  逻辑等）——不得触碰、不得提交、不得回滚，继续沿用 A69 起建立的处理方式：提交前 `git status --short`
  核对，只暂存本任务范围内文件。

---

## A73 — 连续合约换月窗口收益贡献单列报告

### Rationale

`chan_strategy/data_adapter.py:347-354` 明确 AP/RB/SC/A/ZN 888 连续合约表是未复权原始拼接，换月存在
价格跳变。A52（`rollover_stat_tagging`，已 `done`）已经在 `Position.pairs` 上打上
`is_rollover_window` 布尔标记（[backtest_engine.py:572-576](../../examples/czsc_strategy/chan_strategy/backtest_engine.py:572)），
但目前只是标记，没有任何报告把"换月窗口内 vs 窗口外"的收益贡献分开展示——审核指出的真正缺口是"换月
窗口对信号和收益的贡献未单列"，不是"没有标记机制"。

### Semantics

- 新增 `diagnostics/rollover_contribution_report.py`（复用 `backtest_matrix_report.py` 或
  `risk_param_sensitivity_report.py` 已有的"跑一次回测→读取 `Position.pairs`"模式，不重新发明回测
  调用方式），要求 `rollover_stat_tagging="on"` 运行回测，然后按 `is_rollover_window` 把已平仓交易
  分成两组，分别统计每组的总收益贡献、胜率、平均盈亏——一份纯粹的诚实测量报告，不设任何 pass/fail
  阈值（换月窗口的收益贡献占比高低本身不是错误信号，只是需要可见）。
- 报告输出遵循 A54 起的 RESEARCH-ONLY 横幅约定（`build_banner()`）。
- 不改变 `is_rollover_window` 标记逻辑本身、不改变回测执行路径、不改变任何现有测试断言。

### Acceptance Criteria

- [ ] `diagnostics/rollover_contribution_report.py` 新增，按品种输出"换月窗口内/外"两组交易的收益
      贡献、胜率、平均盈亏、交易笔数对比。
- [ ] 报告运行时若 `rollover_stat_tagging` 不是 `"on"`，需给出清晰的报错/提示（不能静默产出全 0 或
      误导性的空对比）。
- [ ] 新增单测：使用构造的 `Position.pairs` fixture（不依赖真实历史库）验证分组统计逻辑正确。
- [ ] 不改变 `backtest_engine.py`/A52 既有标记逻辑或既有测试。
- [ ] 门禁通过（同上通用契约）。
- [ ] VERSION/CHANGELOG bump。

---

## A74 — 正式评估入口默认切换到 risk+enforce（不改动库默认值）

### Rationale

审核 #1/#4 建议"正式评估默认使用 `sizing_model='risk'` + `limit_halt_model='enforce'`"。但直接改动
`STRATEGY_CONFIG` 的默认值，会违背本项目贯穿始终的"gated config 默认字节级不变"house style，且会让
所有既有测试（大量假定默认值为 `research`/`off` 的等价性快照测试）需要重新审视——这个代价和收益不成
比例，也不是审核报告的真实诉求：审核关心的是"人容易被默认结果误导"，不是"库的默认参数值本身必须改变"。

**采纳的折中方案**：`chan_strategy/config.py` 的 `STRATEGY_CONFIG`/`BACKTEST_CONFIG` 默认值保持完全
不变（继续 byte-identical，任何直接 `import chan_strategy.config` 或直接构造 `BacktestEngine` 的既有
调用方行为不变）；但为"正式评估"这个使用场景新增一个显式入口（例如
`run_chan_backtest.py` 新增一个 `--formal` / `--production-eval` 命令行参数，或新增一个独立的
`run_formal_evaluation.py` 脚本——具体由 dev 决定，需在 Decision Log 记录理由），该入口在启动时
**主动覆盖** `sizing_model="risk"`、`limit_halt_model="enforce"`，并在报告顶部用 A70 的
`mode_label` 机制明确标注"这是正式评估口径，非默认研究口径"。

### Semantics（dev 需在动手前明确记录的决策点）

- 新入口的具体形态（CLI flag vs 独立脚本）由 dev 决定，但必须满足：
  1. 不修改 `STRATEGY_CONFIG`/`BACKTEST_CONFIG` 字典本身的默认值；
  2. 通过某种覆盖机制（如函数参数传入、临时 monkeypatch-safe 的覆盖字典、或显式构造
     `BacktestEngine` 时传入非默认参数）在正式评估路径上启用 `risk`+`enforce`；
  3. 覆盖后必须仍然产出 A70 的 `mode_label`，且此时 `mode_label` 应准确反映"非 RESEARCH_BASELINE"。
- 不要求这个新入口自动被现有的 `diagnostics/*.py` 报告脚本调用——本任务只新增入口本身，不要求迁移
  既有报告的调用方式（避免连带影响既有报告数值）。

### Acceptance Criteria

- [ ] 新增的正式评估入口（具体形态由 dev 决定并记录理由）在启用时使用
      `sizing_model="risk"`、`limit_halt_model="enforce"`，且不修改 `config.py` 里的默认字典值。
- [ ] 新入口产出的报告/输出包含 A70 的 `mode_label`，且能正确反映非默认状态。
- [ ] 既有默认路径（不使用新入口的所有既有调用方式）行为完全不变，既有测试全部通过、无需修改任何
      既有断言。
- [ ] 新增单测覆盖新入口本身的行为（覆盖是否生效、`mode_label` 是否正确）。
- [ ] 门禁通过（同上通用契约）。
- [ ] VERSION/CHANGELOG bump。

---

## A75 — 废弃信号实现物理隔离 + 生产路径导入护栏测试

### Rationale

A72 已经给 `chan_strategy/signals.py` 的 `get_all_signals()` 加了改名 + `DeprecationWarning`
包装（现为 `get_legacy_signals()`），但审核 #7 指出：物理上，遗留实现仍然和现行实现共存在同一个仍被
广泛 import 的模块文件里，长期共存本身仍是误用风险的来源，建议"移到 `legacy_signals.py`，或要求所有
入口测试断言生产回测只从 `sell_signals` 导入"。

### Semantics

- **采纳审核建议的第二个选项（导入护栏测试），不做物理搬迁**：将 `get_legacy_signals()` 整个函数体
  搬到新文件 `chan_strategy/legacy_signals.py` 属于较大的重构（需要梳理其内部依赖的私有辅助函数，
  逐一判断该复制还是该跨模块导入），收益（进一步降低误用概率）相对有限，而 A72 的
  `DeprecationWarning` 已经能在运行时捕获误用。**更具性价比、且不引入新的跨模块依赖复杂度的方案**：
  新增一个测试（可以是 `tests/unit/test_signal_path_hygiene.py` 或类似命名），静态扫描
  `chan_strategy/`、`diagnostics/`、`run_chan_backtest.py` 中"生产/回测执行路径"的文件（不包括
  `chan_strategy/signals.py` 自身与显式测试遗留行为的测试文件），断言它们不包含
  `from chan_strategy.signals import get_all_signals`（不带 `get_legacy_signals` 后缀别名）这种直接
  引用旧名的写法——已经存在的 `except ImportError: from chan_strategy.signals import
  get_legacy_signals as get_all_signals`（A72 引入的写法）应被显式允许，因为它导入的是新名
  `get_legacy_signals` 只是本地重新绑定到 `get_all_signals` 这个局部变量名，不是从
  `chan_strategy.signals` 直接拿旧入口。
- 若 dev 认为物理搬迁其实工作量可控且更彻底，可以在 Decision Log 记录理由后改为物理搬迁方案——两种
  方案都可接受，但必须先在 Decision Log 说明选择理由。

### Acceptance Criteria

- [ ] 新增一个可运行的护栏测试，能检测"生产/回测执行路径文件直接从 `chan_strategy.signals` import
      `get_all_signals`（不通过 `get_legacy_signals as get_all_signals` 这种显式重命名）"这种模式，
      并在检测到时失败。
- [ ] 该测试在当前代码库上通过（当前不存在违规写法）。
- [ ] 新增一个专门验证"检测确实生效"的反向测试（构造一个临时违规样例，验证护栏测试的检测逻辑本身
      正确——可以是对护栏测试内部扫描函数的单元测试，不需要真的往生产代码里插入违规代码）。
- [ ] 门禁通过（同上通用契约）。
- [ ] VERSION/CHANGELOG bump（如果护栏测试本身被认为是"新增强制规则"，值得记录一条 CHANGELOG）。

---

## Dev Prompt / Review Checklist（三个任务通用）

同 A70-A72 路线图的通用要求：先读设计文档对应任务段落，diff 范围严格限定在任务 Semantics 所列文件，
commit 前 `git status --short` 核对无关并发工作流文件未被暂存，Manual Verification 区块必须包含，
codex review 时优先核对 diff 范围与阈值/口径变化是否忠实于本文档的裁定。
