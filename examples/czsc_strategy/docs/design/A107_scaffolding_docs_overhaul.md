# A107 项目手脚架整改 + 基础库文档/示例完善 设计

- 任务：A107
- 阶段：dev implemented
- 日期：2026-07-29
- 范围：`examples/czsc_strategy/` 子项目本身（不含上游 `vnpy/` 核心框架目录结构）
- 铁律：**只搬迁/归档/新增文档，不改动任何交易逻辑代码**；`chan_strategy/` 内部文件不移动、
  不改名、不改公开 API；默认配置下回测结果必须字节不变。

## 1. 背景

用户要求对本子项目做一次详细审计，并据此设计、完善目录架构/手脚架，同时补齐基础库
（`chan_strategy/` 内部库、`chan_strategy/vendor/` 第三方 vendor 库、vnpy 核心接入点）的
文档与示例。审计由 4 个并行只读子代理完成，分别覆盖：`chan_strategy/` 核心库、
`diagnostics/`（约 480 个文件）、根目录散落脚本、`docs/`/`tests/`/`tools/`/`skill_build/`。
完整原始发现见下节摘要；本设计只对**低风险、高价值**的整改项排期，高风险大体量项目
（`diagnostics/` 重组）作为独立后续任务建议，不纳入本任务交付范围（见 §6）。

## 2. 审计发现摘要

### 2.1 `chan_strategy/` 核心库（14 个模块 + `vendor/`）

- 各模块**普遍有模块级 docstring**，部分异常坦诚地记录了设计取舍（如 `zhongshu.py`、
  `portfolio_ledger.py`）；`config.py` 的 `STRATEGY_CONFIG`/`BACKTEST_CONFIG` 键有行内注释
  文档，并非完全依赖散落的 diagnostics 记录。
- 但**没有任何面向新人的整体入口文档**：`validation.py`（1372 行）、`portfolio_ledger.py`、
  `zhongshu.py`、`rollover_config.py`、`limit_config.py` 完全未被 README/docs 提及。
- 存在一个真实的认知陷阱：`signals.py` 和 `sell_signals.py` **各自**定义了一个
  `get_all_signals()`，`__init__.py` 导出的是 `sell_signals.py` 版本（"更全"版本），
  但没有任何文档说明这一点，盲目 grep 到 `signals.py` 版本的人会拿到不完整的信号集合。
- `vendor/` 只是 czsc 0.9.51 `kline_pro.echarts_plot` 的一个文件级 vendor（因 czsc≥1.0.0rc8
  移除了该模块），不是完整第三方库副本；`html_report.py` 模块 docstring 已解释缘由，
  但没有独立的 vendor 说明文档。

### 2.2 `diagnostics/`（约 480 个文件：163 md / 144 json / 115 py / 38 html / 17 txt）

- 分三层：①4 个核心治理文档（`ACCEPTANCE.md`/`WORK_LOG.md`/`NEXT_WORK.md`/
  `AUTOMATION_PROMPT.md`，路径被工具/文档硬编码引用，禁止移动）；②一批**可复用脚本模块**
  （`simnow_*.py` 中的引擎脚本、`signal_funnel.py`、`sc_short_weight_neighborhood.py` 等，
  被其他 diagnostics 脚本 `import`，禁止随意搬迁 import 路径）；③约 400+ 个一次性研究
  脚本+定时产出（`.md`/`.json`/`.html`/`.txt`）配对文件，可安全归档但体量大、拆分风险高。
- `.synccheck.yml` 的 `diagnostics_banner_check` 递归扫描 `diagnostics/` 全部子目录并已有
  `exempt_dirs: [diagnostics/archive]` 先例，说明子目录化本身不会破坏门禁，但脚本间的
  `import` 耦合需要逐一审计才能安全拆分。

### 2.3 根目录散落脚本（19 个 `.py`/`.ipynb`）

- **12 个可安全归档**：`_debug_zs.py`、`_patch_backtest{1..4}.py`、`debug_pos.py`、
  `inspect_db.py`、`test_czsc_api.py`/`test_czsc_api2.py`（6 个"一次性调试脚本"，文件内
  均已自带 "ONE-SHOT/开发期调试脚本" 标注）+ `czsc_adapter.py`、
  `czsc_multi_timeframe_strategy.py`、`run_akshare_backtest.py`、`run_baostock_backtest.py`、
  `run_stock_backtest.py`、`backtesting_demo.ipynb`（6 个"已废止 A 股原型"集群，文件内均已
  自带 "LEGACY / 已停止维护" 标注，且 `README.legacy.md` 已是这一集群的历史指针文档）。
  经 grep 确认：`chan_strategy/`、`tests/`、`tools/` 均**零处 import** 这 12 个文件。
- **仅 3 个是现役入口脚本**：`run_chan_backtest.py`、`run_formal_evaluation.py`、
  `run_validation.py`，当前直接摊平在仓库根目录，与死代码混在一起。
- 额外发现一个潜在陷阱：`test_czsc_api.py`/`test_czsc_api2.py` 文件名匹配 pytest 默认
  收集模式（`test_*.py`），若脚本内容不小心被无范围 `pytest` 调用会尝试收集/报错——
  当前 CI 用 `pytest examples/czsc_strategy/tests/unit -q` 限定了路径所以未触发，但仍是
  命名层面的隐患。

### 2.4 `docs/`/`README`/`tests/`/`tools/`/`skill_build/`

- `docs/architecture/` 只有 1 篇长文（19 节的架构提案文档，非稳定参考文档）；
  `docs/design/*.md` 是逐任务设计文档（A102/A106/A32...），**没有索引**，不知道有哪些
  任务、状态如何；`docs/reference/` 目前只有一份缠论理论笔记，不是 API 参考。
- `README.md` 已完全取代 `README.legacy.md`（后者已标注为历史指针），但 README.md
  开篇即 RESEARCH-ONLY 免责声明 + 信号体系细节，**全文没有"如何跑第一次回测"的快速开始
  路径**；grep "快速开始/quickstart/第一次" 在 README/AGENTS/docs 全部为 0 命中。
- `tests/TEST_REPORT.md` 有明确的 pytest 命令，是目前唯一"如何跑起来"的落地文档，但
  README 没有指向它；`tests/conftest.py` 定义了 fixture（FakeBI/FakeCZSC/内存 sqlite）
  但没有说明它们的文档。
- `tools/`（`handoff.py`/`sync_check.py`）只在根 `AGENTS.md` 中被提及，README 完全不提。
- `skill_build/`（缠论"解盘"叙事 NLG 子系统）自成一体、自文档化良好（`SKILL_DRAFT.md`），
  但没有任何顶层文档告诉新人"这是什么、为什么在这里"。

**核心结论**：本子项目的深层文档质量其实不差（模块 docstring、config 注释、逐任务设计文档
都在），但缺一个"前门"——没有面向新人/新 agent 的入口，导致同样的知识需要每次重新从源码
或几百个 diagnostics 文件里重新发现。

## 3. 设计方案：目标目录结构（本任务范围）

```text
examples/czsc_strategy/
├── README.md                      # 新增"快速开始"小节（§3.5）
├── HANDOFF.md / CHANGELOG.md / VERSION / AGENTS.md(根级，不动)
├── chan_strategy/                 # 不动，零文件移动
├── scripts/                       # 新增：现役入口脚本迁入
│   ├── run_chan_backtest.py       # git mv 自根目录
│   ├── run_formal_evaluation.py   # git mv 自根目录
│   └── run_validation.py          # git mv 自根目录
├── legacy/                        # 新增：已废止 A 股原型集群整体迁入
│   ├── README.md                  # 迁移自 README.legacy.md 内容 + 迁移说明
│   ├── czsc_adapter.py
│   ├── czsc_multi_timeframe_strategy.py
│   ├── run_akshare_backtest.py
│   ├── run_baostock_backtest.py
│   ├── run_stock_backtest.py
│   └── backtesting_demo.ipynb
├── archive/                       # 新增：一次性调试脚本 + 历史点状报告
│   ├── one_shot_scripts/
│   │   ├── debug_zs.py                (原 _debug_zs.py，去掉下划线前缀)
│   │   ├── patch_backtest_1.py .. 4.py (原 _patch_backtest{1..4}.py)
│   │   ├── debug_pos.py
│   │   ├── inspect_db.py
│   │   ├── czsc_api_probe_1.py        (原 test_czsc_api.py，改名避开 pytest 收集)
│   │   └── czsc_api_probe_2.py        (原 test_czsc_api2.py)
│   └── reports/
│       ├── AUDIT_REPORT_2026-07-03.md
│       ├── AI_REVIEW_REPORT_2026-07-26.md
│       └── AI_REVIEW_REPORT_2026-07-26_v2.md
├── docs/
│   ├── README.md                  # 新增：docs/ 总索引
│   ├── design/
│   │   └── README.md              # 新增：任务索引（扫描现有 *.md 生成表格）
│   ├── architecture/               # 不动
│   └── reference/
│       ├── chan_theory_book_notes.txt          # 不动
│       ├── chan_strategy_api.md                # 新增：chan_strategy/ 全模块 API 参考
│       ├── czsc_vendor_notes.md                # 新增：vendor/ 与 czsc 依赖说明
│       └── quickstart_example.py               # 新增：最小可运行示例（非 CLI 全量脚本）
├── diagnostics/ ...                # 不动（本任务不含，见 §6）
├── tests/ ...                      # 不动，仅 conftest.py 补充文档字符串
├── tools/ ...                      # 不动
└── skill_build/ ...                # 不动
```

### 3.1 根目录清理

- **`scripts/`**：`git mv` 3 个现役入口脚本。更新所有引用其旧路径的文档
  （README.md 目录树/快速开始命令、`tests/TEST_REPORT.md` 若有提及、`HANDOFF.md`
  若有历史提及则不回溯改动，只改活跃文档）为 `python scripts/run_chan_backtest.py`
  等新路径。`run_formal_evaluation.py` 内部若有 `run_chan_backtest.py` 的相对路径/
  文档字符串引用，需同步更新。
- **`legacy/`**：`git mv` 6 个已标注"LEGACY"的 A 股原型文件 + `README.legacy.md`
  （改名为 `legacy/README.md`，内容基础上补一句迁移说明和迁移日期）。README.md 第 17/148
  行提到这些文件路径的地方同步更新为 `legacy/` 前缀。
- **`archive/one_shot_scripts/`**：`git mv` 6 个一次性调试脚本，去掉下划线前缀（下划线
  前缀在这个仓库没有特殊纳入约定，改成清晰目录名更直观），`test_czsc_api{,2}.py` 改名为
  `czsc_api_probe_{1,2}.py` 以彻底避免未来 `pytest`（无路径限定时）误收集的隐患
  （§2.3 发现）。这些脚本内部若硬编码了到根目录数据库/文件的相对路径，需要在迁移时
  同步改为相对 `archive/one_shot_scripts/` 或改为可运行时定位仓库根的写法——**若脚本已经
  完全过时不可运行（部分本就是一次性用完即弃的 patch 脚本），允许仅迁移不修复可运行性，
  但需在文件顶部现有的 legacy 注释后追加一行"路径已随 A107 迁移，未重新验证可运行性"**。
- **`archive/reports/`**：`git mv` 3 份历史点状审计/复审报告（`AUDIT_REPORT_2026-07-03.md`、
  `AI_REVIEW_REPORT_2026-07-26.md`、`AI_REVIEW_REPORT_2026-07-26_v2.md`）。
  `CHANGELOG.md`/`docs/theory_code_crosscheck.md`/`diagnostics/*.md` 等处对这三份文件的
  历史引用**不回溯修改**（历史记录不改写，这是本仓库既有惯例），只需确认这些引用文件本身
  不依赖相对路径可解析性（它们是纯文字提及，不是程序化路径依赖，无需改动）。
- `IN_FLIGHT_CHANGES.md`、`RISK_NOTE_888_SPLICE.md` 保持原位（仍是活跃文档，非历史快照）。

### 3.2 `docs/` 索引与基础库文档

- **`docs/README.md`**（新增）：一段导航，说明 `architecture/`（架构提案类文档）、
  `design/`（逐任务设计文档，见索引）、`reference/`（理论笔记 + API 参考 + 示例）三者
  各自定位，避免新人混淆"这是不是稳定参考文档"。
- **`docs/design/README.md`**（新增）：一张表，列出现有 `docs/design/*.md` 每个文件的
  任务号、标题、当前 `HANDOFF.md` 记录的阶段（design/dev/review/done，若已知）。
  dev 落地时**读取当前各文件首部的"任务/阶段"字段生成**，而不是手写猜测状态；若某文件
  没有明确阶段字段，标注"未知，见文件内容"，不得编造。
- **`docs/reference/chan_strategy_api.md`**（新增）：按 §2.1 审计结果逐模块列出：一句话
  职责、公开 API（类/函数签名级别，不展开实现）、是否有独立示例、关键陷阱。**必须包含**
  一条明确条目说明 `signals.py.get_all_signals()` 与 `sell_signals.py.get_all_signals()`
  的关系（后者是 `__init__.py` 实际导出、更完整的版本），消除 §2.1 发现的认知陷阱。
  纯文档整理，不得包含未经验证的行为描述——每条公开 API 描述必须能在对应源文件中找到
  依据（函数签名、docstring、或调用点），不得推测未读代码的行为。
- **`docs/reference/czsc_vendor_notes.md`**（新增）：说明 `chan_strategy/vendor/` 只是
  `echarts_plot.py` 一个文件级 vendor（非完整第三方库副本），vendor 原因（czsc≥1.0.0rc8
  移除该模块）、来源版本（czsc 0.9.51 kline_pro），以及仓库实际安装的 `czsc` 版本
  （`requirements.txt` 中的 pin，含版本 guard 注释）。
- **`docs/reference/quickstart_example.py`**（新增）：一个**最小、可独立运行**的示例脚本
  （不是 `scripts/run_chan_backtest.py` 的复制品），演示 `chan_strategy/__init__.py`
  导出的核心 API 如何组合使用（`get_all_signals`、某个 `create_*_position` 工厂、
  `resample_bars`）到"能看到输出"的最小闭环。若该闭环需要真实历史数据库才能跑通，
  脚本必须在顶部注明数据依赖与获取方式，不得静默失败或需要用户猜测。

### 3.3 `README.md` 快速开始

在现有 RESEARCH-ONLY 声明之后、信号体系细节之前，插入一个"快速开始"小节：
安装依赖（指向根 `AGENTS.md`/`install.bat` 或本目录 `requirements.txt`）→
运行 `pytest tests/unit -m "not realdb"` 验证环境 → 运行
`python scripts/run_chan_backtest.py` 看一次真实回测 → 指向
`docs/reference/quickstart_example.py` 看最小 API 示例 → 指向
`tests/TEST_REPORT.md` 看完整测试矩阵。同时修正目录树小节和第 17/140/141/148/156 行
等处因 `scripts/`/`legacy/` 迁移产生的路径引用。

### 3.4 `tests/conftest.py`

仅新增模块级 docstring，说明 `FakeBI`/`FakeCZSC`/内存 sqlite 等核心 fixture 各自代表什么、
供哪类测试使用；不改动任何 fixture 实现或测试逻辑。

## 4. 接入边界（本任务只做这些）

- 允许：`git mv` 文件/改名（含更新引用它们新路径的**活跃**文档）、新增纯文档文件
  （`.md`/一个新增的最小示例 `.py`）、在 `tests/conftest.py` 顶部加 docstring。
- 不允许：修改 `chan_strategy/` 任何文件的代码逻辑或公开 API、修改
  `diagnostics/` 任何文件（含不移动、不改名，见 §6）、修改任何测试断言、修改
  `.synccheck.yml` 治理规则本身、回溯改写历史 `CHANGELOG.md`/`HANDOFF.md` 条目中对
  旧路径的文字提及。
- `docs/reference/quickstart_example.py` 若被判定为"脚本"而非"文档"，需确认
  `.coveragerc`（scope 是 `chan_strategy`）/`pytest.ini` 不会把它当作测试或覆盖率目标
  误收集；若existing tooling 对根目录外的裸 `.py` 文件有隐式行为，需在 Manual
  Verification 中证明。

## 5. 验收标准（review 合同，逐条可判定）

- [ ] AC1 目录结构：`ls examples/czsc_strategy` 顶层出现 `scripts/`、`legacy/`、
      `archive/one_shot_scripts/`、`archive/reports/`；原 19 个根级散落 `.py`/`.ipynb`
      文件在根目录不再存在（`git status`/`git mv` 历史可查，非删除）。
- [ ] AC2 零行为变化：`git diff` 中 `chan_strategy/**` 与 `diagnostics/**` 无任何改动；
      默认配置下 `pytest tests/unit -q -m "not realdb"` 通过数与本任务开始前一致（允许
      因新增 fixture/docstring 测试而增加，但不得减少或出现新失败）。
- [ ] AC3 路径引用一致性：`grep -rn "run_chan_backtest.py\|run_formal_evaluation.py\|run_validation.py"`
      在 README.md 等活跃文档中的结果均指向 `scripts/` 前缀；
      `grep -rn "czsc_adapter.py\|czsc_multi_timeframe_strategy.py\|run_baostock_backtest.py\|run_akshare_backtest.py\|run_stock_backtest.py"`
      在 README.md 中的结果均指向 `legacy/` 前缀。
- [ ] AC4 命名去陷阱：`archive/one_shot_scripts/` 下不存在任何匹配 pytest 默认收集模式
      （`test_*.py`）的文件名；`pytest`（无路径参数，从 `examples/czsc_strategy` 目录下跑）
      不会尝试收集/报错在这两个已迁移文件上。
- [ ] AC5 新增文档真实可核：`docs/reference/chan_strategy_api.md` 覆盖 §2.1 列出的全部
      14 个 `chan_strategy/` 模块（含 `vendor/`），且明确写出
      `signals.py`/`sell_signals.py` 两个 `get_all_signals()` 的关系；`docs/design/README.md`
      索引条目数等于 `docs/design/*.md` 文件数。
- [ ] AC6 示例可运行或明确声明依赖：`docs/reference/quickstart_example.py` 要么在无额外
      数据依赖下可 `python docs/reference/quickstart_example.py` 直接跑通，要么在脚本顶部
      清楚写明所需数据库/环境依赖，Manual Verification 中必须贴出一次实际运行的输出
      （或明确记录因缺少历史数据库而无法在当前环境验证，附替代验证方式如语法/import 检查）。
- [ ] AC7 完成定义：VERSION bump + CHANGELOG 一条 + 本设计文档"阶段"字段更新为
      "dev implemented"，同一提交；`python tools/sync_check.py` 通过
      （注意：本任务不触碰 `chan_strategy/config.py` 的 `STRATEGY_CONFIG`/`BACKTEST_CONFIG`，
      `project_version_freshness` 门禁本次不会被触发，但仍需常规 VERSION/CHANGELOG bump
      满足 `changelog` 门禁）。

## 6. 非目标（Out of scope，本任务不做）

- **`diagnostics/` 目录重组**（§2.2 发现的约 400+ 个一次性研究产出）：体量大
  （480 个文件）、且存在脚本间 `import` 耦合（如 `platform_short_symbol_candidates.py`
  导入 `sc_short_weight_neighborhood.py` 等同目录模块），贸然批量迁移风险显著高于本任务
  其余整改项的收益。**建议作为独立后续任务（暂拟 A108）**，届时应先逐脚本做 import 依赖图
  再决定哪些可安全归档，而不是本任务顺带处理。
- 修改 `chan_strategy/` 任何模块的代码、公开 API、信号逻辑。
- 对 `vnpy/` 上游核心框架目录结构做任何调整（范围已在用户确认时排除）。
- 为 `tools/`、`skill_build/` 新增独立文档（`tools/` 已有 AGENTS.md 章节覆盖，
  `skill_build/` 已有自文档化的 `SKILL_DRAFT.md`；本任务只在 README 快速开始/docs 索引中
  各加一句指路文字，不新增专门文档文件，避免任务范围失控）。

## 7. Dev 实现记录

- 2026-07-30 (kimi-code, dev) - 按本设计文档完成 A107：
  - 全部 19 个根级散落脚本/notebook 用 `git mv` 归位：`scripts/`（3 个现役入口）、
    `legacy/`（7 个 A 股原型）、`archive/one_shot_scripts/`（8 个一次性脚本）、
    `archive/reports/`（3 份历史报告）。原根目录文件不再存在，无删除。
  - `archive/one_shot_scripts/` 中已无 `test_*.py` 文件名；`_debug_zs.py` → `debug_zs.py`，
    `_patch_backtest{1..4}.py` → `patch_backtest_1.py..patch_backtest_4.py`，
    `test_czsc_api.py`/`test_czsc_api2.py` → `czsc_api_probe_1.py`/`czsc_api_probe_2.py`。
  - 活跃文档路径引用同步：`README.md` 新增"快速开始"小节并修正目录树/路径；
    现役脚本 docstring 中的使用路径更新为 `scripts/`；legacy README 追加二次迁移说明；
    归档脚本内部硬编码路径更新为 `legacy/` 或仓库根定位，并追加迁移说明；
    `tests/unit/test_repo_hygiene.py` 的 one-shot 补丁脚本路径同步更新。
  - 新增 `docs/README.md`、`docs/design/README.md`、`docs/reference/chan_strategy_api.md`、
    `docs/reference/czsc_vendor_notes.md`、`docs/reference/quickstart_example.py`。
  - `tests/conftest.py` 仅新增模块级 docstring，未改动 fixture 逻辑。
  - `chan_strategy/**` 与 `diagnostics/**` 零改动；未触碰 `diagnostics/` 目录。
  - 版本治理：`VERSION` 0.2.64 → 0.2.65，`CHANGELOG.md` 新增 0.2.65 条目，本设计文档阶段字段更新为
    "dev implemented"，同一提交完成。
  - Manual Verification：not-realdb 单元测试 1009 passed/4 deselected/4 xfailed，与迁移前基线持平；
    `docs/reference/quickstart_example.py` 实跑输出已记录；
    `python tools/sync_check.py --root examples/czsc_strategy` PASS。

## 8. 决策记录

- 2026-07-29 (claude-code, design) - 用户在 4 个澄清问题中确认范围为 czsc_strategy
  子项目本身（非整个 vnpy 仓库）、"基础库"覆盖 chan_strategy 内部库 + czsc vendor 库 +
  vnpy 核心（三者均勾选），并确认走正式 sync-guardian design 交接流程。
- 2026-07-29 (claude-code, design) - 将 `diagnostics/` 重组排除出本任务范围（见 §6），
  理由：4 个并行审计子代理之一发现该目录脚本间存在真实 `import` 耦合，且体量
  （约 480 文件）远超本任务其余整改项，强行合并会显著放大单次 review 的核验难度，
  违反仓库"小步快跑"的既有协作惯例（见 `AGENTS.md` "Keep changes minimal"）。
- 2026-07-29 (claude-code, design) - 选择"只搬迁 + 补文档"而非同时精简/删除任何文件，
  理由：仓库既有惯例是给已废止代码打标签保留而非删除（`README.legacy.md`、各文件内
  "LEGACY"/"ONE-SHOT" 注释均为此惯例的证据），本任务延续该惯例，用目录归类替代
  "标注但仍摊在根目录"的现状，而不引入删除历史代码的新风险。
