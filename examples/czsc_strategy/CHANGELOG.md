# Changelog — czsc_strategy 诊断工作流

版本单一真相：`VERSION` 文件。每个对外可见改动 = 代码 + 版本 bump + 本文件一条 + 相关文档，同一提交完成。

## 0.2.13 — 2026-07-16

- A78 正式评估默认改为 intrabar 止损执行模型，并新增 RESEARCH_BASELINE 消费护栏函数。
  - `chan_strategy/backtest_engine.py` 的 `formal_evaluation_config()` 在正式评估期间额外临时覆盖
    `STRATEGY_CONFIG["stop_execution_model"] = "intrabar"`，运行结束后（含异常路径）无条件恢复原始值；
    与已有的 `sizing_model="risk"`、`limit_halt_model="enforce"`、`rollover_open_gating="on"` 共同构成
    正式评估四覆盖。
  - 新增可复用护栏函数 `assert_not_research_baseline(report: dict)`：当 `report.get("mode_label") ==
    "RESEARCH_BASELINE"` 时抛出 `ValueError`，供未来任何晋级/acceptance 逻辑在消费报告前调用；本任务
    不改造现有 SimNow 晋级判定脚本。
  - 新增/扩展单测 `tests/unit/test_formal_evaluation.py`：验证 `stop_execution_model` 覆盖生效、成功/异常
    后恢复、非默认原始值保留、入口函数 `run_formal_evaluation()` 内报告字段为 `"intrabar"`，并覆盖护栏
    函数对 `"RESEARCH_BASELINE"` 抛出、对其他标签/空 dict 不抛出的行为；不依赖真实历史数据库。
  - 未修改 `chan_strategy/config.py` 默认字典，未改动非正式评估默认路径的任何既有测试断言。

## 0.2.12 — 2026-07-16

- A77 修复文档漂移：README `limit_halt_model` 与 verdict 层 docstring 说明。
  - `README.md` 中 `limit_halt_model` 取值列表更新为 `"off" | "aware" | "enforce"`，与
    `chan_strategy/config.py` 实际支持值保持一致。
  - `README.md` 在研究-only 开关章节补充说明：正式评估路径（`sizing_model="risk"`、
    `limit_halt_model="enforce"`、换月窗口开仓门控）请使用 `run_formal_evaluation.py` 入口。
  - `diagnostics/cost_sensitivity_report.py` 的 `run_cost_sensitivity()`、
    `diagnostics/risk_param_sensitivity_report.py` 的 `evaluate_perturbation_gate()`、
    `diagnostics/backtest_matrix_report.py` 的 `evaluate_oos_gate()` 三个测量函数 docstring
    增加指向各自 companion verdict 函数（`cost_sensitivity_gate_verdict()`、
    `perturbation_gate_verdict()`、`oos_gate_verdict()`）的说明，避免读者将“本函数不设定阈值”
    过度推广到整个文件；保留原函数“不发明任意 pass/fail 阈值”的准确描述不变。
  - 纯文档/docstring 改动，未修改任何函数逻辑、返回值结构或既有测试断言。

## 0.2.11 — 2026-07-15

- A76 新增正式评估模式下换月窗口开仓门控（解决第四轮审核唯一 🔴 高严重度问题）。
  - 新增 `STRATEGY_CONFIG["rollover_open_gating"] = "off" | "on"`，默认 `"off"`，保持默认路径字节级不变。
  - `formal_evaluation_config()` 将 `rollover_open_gating` 临时覆盖为 `"on"`，与 `sizing_model="risk"`、
    `limit_halt_model="enforce"` 一起构成正式评估三覆盖；运行结束后无条件恢复原始值（含异常路径）。
  - 门控仅阻止换月排除窗口内的新开仓（多头/空头），不影响窗口内已持仓位的止损、超时、移动止损、信号平仓等
    风控逻辑；不调整连续合约拼接价格本身。
  - 复用 A52 的 `rollover_config.py` / `_rollover_excluded_dates()` 计算排除日期，元数据缺失/检测失败时
    优雅降级为不门控，并在报告/日志中显式标识 `"rollover_open_gating_unavailable"`，避免与"生效但无排除日期"
    静默不可区分。
  - 正式评估报告的 `mode_label` 扩展为
    `PARTIAL_PRODUCTION_FEATURES(sizing_model=risk,limit_halt_model=enforce,rollover_open_gating=on)`。
  - 新增单测 `tests/unit/test_rollover_open_gating.py`，覆盖：默认 off、正式评估启用、窗口内开仓被拦、默认路径
    正常开仓、已持仓正常平仓、元数据缺失降级可识别、mode_label 包含新维度；不依赖真实历史数据库。
  - 不改动任何 SimNow 下单/撤单路径，不涉及阈值调优，不对连续合约价格做任何前复权/后复权/价差平滑。

## 0.2.10 — 2026-07-15

- A75 新增废弃信号路径导入护栏测试 `tests/unit/test_signal_path_hygiene.py`。
  - 静态扫描 `chan_strategy/`（除 `signals.py` 自身）、`diagnostics/`、`skill_build/`、
    `run_chan_backtest.py` 等生产/执行路径文件，断言不存在直接从 `chan_strategy.signals`
    import `get_all_signals`（不带 `get_legacy_signals` 后缀别名）的写法。
  - 使用 AST 级检测，正确区分：生产路径 `from chan_strategy.sell_signals import get_all_signals`
    （允许）、A72 已接受的 `from chan_strategy.signals import get_legacy_signals as get_all_signals`
    回退别名（允许）、以及真正的违规直接旧名导入（失败）。
  - 新增反向自测，构造临时违规源码样例验证检测器本身确实能捕获被禁模式，未往生产代码中插入任何
    违规导入。
  - 不改动 `chan_strategy/signals.py`、`sell_signals.py` 或任何信号计算逻辑；不改动 SimNow
    下单/撤单路径；不依赖真实历史数据库。

## 0.2.9 — 2026-07-15

- A74 新增正式评估回测入口，默认启用 `sizing_model="risk"` + `limit_halt_model="enforce"`。
  - 不改动 `chan_strategy/config.py` 中 `STRATEGY_CONFIG`/`BACKTEST_CONFIG` 的默认字典值；既有默认路径
    （`run_chan_backtest.py`、直接构造 `BacktestEngine`、既有 `diagnostics/*.py`）行为完全不变。
  - 在 `chan_strategy/backtest_engine.py` 新增 `formal_evaluation_config()` 上下文管理器，临时覆盖
    `sizing_model` 与 `limit_halt_model`，并在 `finally` 中无条件恢复原始值（即使运行期间抛异常）。
  - 新增 `run_formal_evaluation()` 便捷函数与 `run_formal_evaluation.py` 独立脚本，作为显式正式评估入口。
  - 报告沿用 A70 的 `mode_label` 机制；正式评估路径下 `mode_label` 为
    `PARTIAL_PRODUCTION_FEATURES(sizing_model=risk,limit_halt_model=enforce)`，明确标识非研究基线。
  - 新增单测 `tests/unit/test_formal_evaluation.py`，覆盖：覆盖生效、成功/异常后配置恢复、保留既有非默认值、
    入口函数行为、`mode_label` 非基线；不依赖真实历史数据库。
  - 不改动任何 SimNow 下单/撤单路径，不涉及阈值调优。

## 0.2.8 — 2026-07-15

- A73 新增 `diagnostics/rollover_contribution_report.py` 换月窗口收益贡献单列报告。
  - 复用 `BacktestEngine` 与 `Position.pairs` 机制，在 `rollover_stat_tagging="on"` 下运行回测，
    按 A52 标记的 `is_rollover_window` 将已平仓交易分为换月窗口内/外两组。
  - 每品种输出两组交易的总收益贡献、胜率、平均盈亏、交易笔数对比，以及两者总收益贡献的差值。
  - 报告为纯测量型输出，不设置任何 pass/fail 阈值，不改动 `backtest_engine.py` 的 A52 标记逻辑、
    既有测试或任何 SimNow 下单/撤单路径。
  - 报告顶部包含 RESEARCH-ONLY / NOT PROMOTION EVIDENCE 横幅，符合 A54 约定。
  - 若 `rollover_stat_tagging` 不是 `"on"`，报告明确抛出 `RuntimeError`，避免静默产出误导性全 0/空输出。
  - 新增单测 `tests/unit/test_rollover_contribution_report.py`，使用构造的 `Position.pairs` fixture
    验证分组与聚合逻辑，不依赖真实历史数据库。

## 0.2.7 — 2026-07-15

- A72 弃用 `chan_strategy/signals.py` 中的旧 `get_all_signals()` 入口。
  - 将原函数重命名为 `get_legacy_signals()`，函数体与信号计算逻辑保持不变；
     docstring 增加说明，指出其已被 `chan_strategy.sell_signals.get_all_signals`
    取代。
  - 在原 `get_all_signals` 名称保留薄包装，调用时触发 `DeprecationWarning`
    （`stacklevel=2`）并转发到 `get_legacy_signals()`，避免破坏潜在隐藏调用方。
  - 更新 `skill_build/build_mapping.py` 与
    `skill_build/scripts/analyze_symbol.py` 的 `except ImportError` 回退分支，
    改为显式导入 `get_legacy_signals`，避免在死代码回退路径触发弃用告警。
  - 将故意测试遗留实现本身的 `tests/unit/test_remaining_coverage.py` 与
    `test_second_buy_real_path.py` 改为调用 `get_legacy_signals()`，消除正常测试
    运行中的告警噪音。
  - 新增单测 `test_base_get_all_signals_emits_deprecation_warning`：断言旧入口
    仍返回与 `get_legacy_signals()` 一致的结果，并触发 `DeprecationWarning`。
  - 不改动 `chan_strategy/sell_signals.py`、任何 SimNow 下单/撤单路径，也不改动
    任何信号计算逻辑；所有既有数值/结构断言保持字节级不变。

## 0.2.6 — 2026-07-15

- A71 将 A69 三项测量型门禁升级为机器可判定晋级门禁。
  - 在 `diagnostics/backtest_matrix_report.py` 新增 `oos_gate_verdict()`：IS/OOS 收益符号翻转为
    `fail`；OOS 最大回撤相对 IS 最大回撤超过 3 倍（且 IS 回撤非零）为 `warn`；否则 `pass`。
  - 在 `diagnostics/risk_param_sensitivity_report.py` 新增 `perturbation_gate_verdict()`：任一参数变体
    相对 baseline 收益符号翻转为 `fail`；否则 `pass`。不设 `warn`  tier，因为符号翻转本身是无需校准的
    定性判据；不引入 epsilon 豁免，避免任意阈值掩盖真实脆弱性。
  - 在 `diagnostics/cost_sensitivity_report.py` 新增 `cost_sensitivity_gate_verdict()`：2.0x 成本下
    `total_return_pct` 符号翻转为 `fail`；2.0x 成本相对 1.0x 基线的收益相对跌幅超过 90%（仅当基线收益为正）
    为 `warn`；否则 `pass`。
  - 三个 verdict 函数均返回 `symbols` 层 verdict、`overall_status` 与人类可读 `reasons`；不改变底层
    A69 测量函数的返回结构与既有测试。
  - 阈值选取为极端、自证安全的保护性上限，未依据 `diagnostics/` 任何历史报告观测值反推；理由记录在
    `HANDOFF.md` Decision Log。
  - 新增单测覆盖 `pass`/`warn`/`fail`（或 `pass`/`fail`）各态，使用构造 fixture，不依赖真实历史数据库。
  - 不改动 `chan_strategy/*.py` 交易逻辑、SimNow 下单/撤单路径，不涉及参数调优。

## 0.2.5 — 2026-07-15

- A70 默认回测报告强制标注 research/off 模式标签。
  - `chan_strategy/backtest_engine.py` 的 `generate_report()` 新增 `mode_label` 与 `limit_halt_model` 字段；
    `mode_label` 在纯默认配置（`sizing_model="research"`、`limit_halt_model="off"`、`portfolio_risk="off"`）下为
    `"RESEARCH_BASELINE"`，任一维度偏离时显式命名该维度及当前值（如
    `PARTIAL_PRODUCTION_FEATURES(sizing_model=risk)`）。
  - `print_report()` 在报告最顶部打印 `mode_label`；当为 `"RESEARCH_BASELINE"` 时额外打印醒目免责提示：
    "本报告为 RESEARCH_BASELINE（研究基线），不构成生产/可交易证据"。
  - 新增单测覆盖全默认、各维度单独偏离及多维度组合偏离情形，断言 `generate_report()` 返回字典与
    `print_report()` 的 stdout 输出。
  - 不改动任何既有回测数值输出（`total_return_pct`、`sharpe_ratio` 等），不影响 SimNow 下单/撤单路径，
    不涉及参数调优。

## 0.2.4 — 2026-07-15

- A67 新增 `limit_halt_model="enforce"`（涨跌停/停牌不可成交回测模式）。
  - 新增第三个可选值 `"enforce"`：当某笔开仓/平仓在方向性不利的涨跌停带内时，本 bar 拒绝该次成交（`self.pos` 不变），并在最终成交的 `Position.pairs` 记录上追加 `fill_rejected_at_limit` 审计字段。
  - 覆盖全部开平仓入口：信号开仓/平仓、`exit_model="legacy"` 的移动止损/固定止损/超时、`exit_model="structural_atr"` 的固定止损/超时/ATR 移动止损（共 7 处平仓判定点 + 2 处开仓判定点），统一通过 `Position._reject_fill_at_limit()` 辅助方法拦截，避免重复逻辑。
  - 设计决策（记录于 HANDOFF Decision Log）：采用"本 bar 拒绝"而非"跨 bar 排队递延"模型——`_get_operate()` 每根 bar 都会重新评估缠论结构分类，因此被拒绝的信号在结构未变化时会在下一 bar 自然重试，无需引入跨 bar 状态机。
  - `limit_halt_model="off"` / `"aware"` 的行为、字段与既有等价性测试完全字节级不变；`"enforce"` 是新增的纯 opt-in 研究模式。
  - 新增 `diagnostics/limit_halt_enforce_report.py`，对比 `off`/`aware`/`enforce` 三种模式在同一 post-2026-04-24 窗口下的成交笔数与收益差异（RESEARCH-ONLY，诚实测量，不作为任何模式更优的证据）。
  - 不改动任何 SimNow 下单/撤单路径，不涉及参数调优。

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
