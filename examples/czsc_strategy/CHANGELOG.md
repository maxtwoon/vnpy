# Changelog — czsc_strategy 诊断工作流

版本单一真相：`VERSION` 文件。每个对外可见改动 = 代码 + 版本 bump + 本文件一条 + 相关文档，同一提交完成。

## 0.2.55（2026-07-29）- 方案 C：集中度指标改滚动 60 日窗口 + 样本不足 informational

- **根因**：`symbol_top1_abs_share` / `strategy_top1_abs_share` 此前按全回放历史累计，
  指标随窗口延伸漂移——07-27→07-28 零新交易但 strategy_top1 从 0.5550 升到 0.5925，
  越过 warning 线 0.5904，使 `valid_observation_reason = thresholds_not_pass` 成为
  绑定否决项。固定线重校准（方案 B）无法消除该类漂移，被否。
- **快照侧（`export_simnow_replay_snapshot.py`）**：新增
  `_filter_trades_for_concentration`（按 `close_dt` 落在 `[day-59, day]` 的滚动 60
  个日历日窗口过滤；`window_days<=0` 回退全历史）；`_risk_for_day` 返回新增
  `concentration_sample`（`window_days`/`min_trades`/`trade_count`/`insufficient_sample`，
  最少 5 笔）；`build_snapshot` meta 记录 `concentration_window_days` /
  `concentration_min_trades`；CLI 新增 `--concentration-window-days` 与
  `--concentration-min-trades`。
- **监控侧（`simnow_daily_monitor.py`）**：`evaluate_thresholds` 新增 `informational`
  参数——集合内指标行 `level="informational"` 且带 `"informational": True`，不参与
  status 汇总；`make_record` 在选中的 risk payload 读到
  `concentration_sample.insufficient_sample=True` 时，把两个集中度指标降级为
  informational，不再否决 `valid_observation`。样本充足时 veto 行为不变。
  阈值基线 json 不动；07-28 及更早的历史记录不重算。
- **测试**：快照侧 +3（窗口边界过滤、窗口化集中度与样本元信息、样本充足标志），
  监控侧 +3（informational 不参与 status、样本不足不否决、样本充足仍 veto）；
  全量单测 972 passed, 23 skipped；realdb 4 passed；裸 PATH Preflight 324 passed。

## 0.2.54（2026-07-28）- 新增缠论书摘 ⇄ 代码对照核查表（纯文档）

- 新增 `docs/theory_code_crosscheck.md`：将带页码锚点的缠论书摘
  （源笔记存档于 `docs/reference/chan_theory_book_notes.txt`）逐条对照项目现有实现，
  按 ✅一致 / ⚠️部分 / ❌缺口 / ❓待验证 标注，区分信号计算层与报告/叙事层两套适用条款；
  汇总缺口优先级（P0 报告层措辞整改 / P1 区间套与走势类型识别 / P2 多义性披露与 MACD 面积通道），
  并列出对 `czsc==1.0.0rc8` 行为断言（ZS 默认笔中枢、倒1/倒2 信号键名）的待验证清单。
- 纯文档改动：不涉及任何代码、参数、信号或回测行为；诊断边界不变。

## 0.2.53（2026-07-28）- risk-halt 决策门禁仅限 halt 日 + 解释器探测依赖补全

- **门禁对齐（修复⑤）**：`run_next_work.ps1` 此前每次 LiveCapture 后无条件生成
  risk-halt review pack 与 pending 决策记录，与 ACCEPTANCE.md "仅 automation_status=halt
  时生成"的设计不符；非 halt 日（如 no_actionable_events_on_either_side）留下的 pending
  记录会被 A38 拦截，20 日观察无法自动推进。现改为从 run summary 读取
  `automation_status`，仅 `halt` 时生成 review/decision，其他状态打印 Skip 说明。
  已删除 07-28（非 halt 日）误生成的 pending 决策记录，review pack 保留作审计。
- **探测依赖补全**：0.2.50 的解释器探测仅校验 `import pytest`，实测某沙箱运行时
  装有 pytest 但无 czsc，导致选中后 conftest 收集失败（exit 4）。探测升级为
  `import pytest, pandas, czsc`，报错文案同步更新。
- **测试**：新增 `test_risk_halt_review_and_decision_generation_gated_on_halt_status` 与
  `test_python_probe_requires_full_project_deps`；包装套件 107 passed；
  全量单测 965 passed；裸 PATH Preflight 自动选对 C:\Python314 并通过。
## 0.2.53（2026-07-28）- 修复 P4 背驰信号中枢选择缺陷（空头开仓几乎永远无法触发）

- **根因**：`chan_strategy/signals.py::signal_divergence_status()` 原来直接取
  `zhongshu_list[-1]`；在默认 `mode="recent"` 下该中枢几乎必然没有后续笔，导致
  `{freq}_D1BI_背驰V260615` 几乎永远输出 `"无"`，进而使 `_research_short_open_allowed()`
  的 P4 门控对空头几乎永远通不过（A888/SC888 全年实证：99.99% 以上调用返回 `"无"`）。
- **修复方案**：新增 `STRATEGY_CONFIG["divergence_status_zhongshu_mode"]` 配置开关：
  - `"legacy"`（默认）：保留原 `zhongshu_list[-1]` 行为，默认配置回测结果字节不变；
  - `"departure_leg"`：与同文件的 `signal_first_buy` / `sell_signals.py` 的
    `signal_first_sell` 保持一致，向后搜索最近一个后面确实存在离开段的中枢。
- **实现**：提取纯函数 `_select_zhongshu_for_departure_leg(bi_list, zhongshu_list)`，
  `signal_divergence_status()`、`signal_first_buy()`、`signal_first_sell()` 统一复用，
  避免同一逻辑三处复制； helper 不耦合 `STRATEGY_CONFIG`，由调用方决定是否启用。
  （review 修正：`signal_first_sell()` 在 0.2.53 后续提交中才实际接入 helper；`signal_third_buy()`
  也复用了 helper，行为与原先内联表达式完全一致。）
- **验证**：新增 8 个单元测试，证明同一 fixture 下 `legacy` 返回 `"无"`、
  `departure_leg` 返回 `"疑似"`；全量 not-realdb 单测 986 passed（+8），realdb 4 passed，
  SimNow `-Preflight` 338 passed；手动回测验证见 `HANDOFF.md` 的 `## Manual Verification`。
- **默认行为不变**：`formal_evaluation_config()` 未设置该新键；默认 `"legacy"` 路径
  与修复前字节一致，不扰动任何现有基线或晋升决策证据。

## 0.2.52（2026-07-28）- czsc 1.0.0rc8 升级 review 修复：基准位移披露机制与文档指向

- **修复 `_baseline_displacement()` 静默失败缺陷**：
  `diagnostics/czsc_upgrade_diff_report.py` 原实现从 `git show HEAD:snapshot` 读取旧基准、
  用相对 CWD 的路径读取新基准，外覆两个裸 `except`，导致从 `examples/czsc_strategy/` 目录
  重新生成报告时"research-mode 基准位移"章节被静默丢弃；且 snapshot 刷新提交后
  `git show HEAD` 会取到新值，可能输出"位移为零"的错误结论。现改为读取落盘的固定
  golden fixture（`tests/unit/test_position_sizing_research_equivalence.snapshot.pre_czsc10.json`），
  缺失 fixture 或 snapshot 时直接抛错（fail-loud），章节不再可能静默丢失。
- **补全行为差异报告**：`diagnostics/czsc_upgrade_behavior_diff_report.md` 现在真正包含
  "research-mode 基准位移"章节，列出 SC888/RB888 Bucket-B 指标（SC888 total_return_pct
  3.794%→0.646%、sharpe 0.809→0.242、三买多头 4 笔→1 笔等）。
- **修正文档指向**：`diagnostics/czsc_upgrade_failure_attribution.md`、CHANGELOG.md 0.2.48
  与 HANDOFF.md 验收标准第 4 条对不存在章节的引用，现已与报告实际内容一致。
- **N1 处理**：`diagnostics/czsc_upgrade_fixtures/`（约 20MB）与
  `diagnostics/czsc_upgrade_sample_report.html`（约 5MB）为可再生生成产物，本次不加入
  版本跟踪；报告内保留重新生成命令，review 可独立复跑验证。

## 0.2.51（2026-07-28）- 执行 07-27 风险停机决策：签署、观察窗重置与 loader 绑定修复

- **决策执行**：`simnow_risk_halt_decision_2026-07-27.json/.md` 由 hanabeatrisa 签署
  （`reset_observation_window_after_strategy_change`，rationale 引用 0.2.49 根因修复），
  `--validate` 通过；`simnow_observation_window.json` 的 `observation_start_date`
  移至 2026-07-28，07-27 台账行保留为审计历史、不计入新 20 日窗口。
- **缺陷修复**：`build_snapshot` 此前调用 `_resolve_risk_start` 未显式传 `loader`，
  默认参数在 def 时绑定模块函数，monkeypatch 及运行期配置变更不生效；
  现显式传 `loader=load_observation_start_date`（调用期查找模块全局）。
- **测试**：`test_simnow_ledger_summary.py::test_cli_writes_summary_json` 夹具日期
  随观察窗前移至 2026-07-28（该用例经 CLI 回退读取真实窗口配置）。
- **验证**：全量单测 `955 passed, 23 skipped, 4 xfailed`（`PYTHONUTF8=1`）；
  决策记录校验 `valid: true`；sync_check PASS。
## 0.2.50（2026-07-28）- run_next_work.ps1 固定 Python 解释器探测

- **环境隐患修复**：wrapper 此前全程调用裸 `python`，在 PATH 解析到无项目依赖的
  解释器（如沙箱运行时、空 venv）时，Preflight 会在 import 阶段失败（实测：
  `No module named pytest`），LiveCapture 则可能在 `import vnpy` / `import vnpy_ctp`
  处崩溃。
- **实现**：新增 `-PythonExe` 参数与 `SIMNOW_PYTHON` 环境变量覆盖；默认按
  `python` → `C:\Python314\python.exe` 顺序探测首个可 `import pytest` 的解释器，
  运行日志首行打印 `Using Python interpreter: ...`；`-LiveCapture` 前置校验
  `vnpy_ctp` 可导入，失败即时报出可操作原因。探测用 `Test-PythonImports` 辅助函数，
  局部降级 `ErrorActionPreference`，规避 Windows PowerShell 5.1 下 EAP=Stop 把
  原生 stderr 变成 NativeCommandError 的坑。全部 16 个 python 调用点改用解析结果 `$Py`。
- **验证**：裸 PATH（`python` 指向无 pytest 的解释器）下 Preflight 自动选对
  `C:\Python314` 并通过（`315 passed, 23 skipped`，skip 为包装测试在 Git Bash
  上下文探测不到 PowerShell 的既有环境行为；PowerShell 可见时 `105 passed`）；
  显式指定坏解释器立即报 `not runnable or cannot import pytest`；`-LiveCapture`
  在窗口外仍按原设计拒绝，且拒绝发生在解释器解析与 vnpy_ctp 校验之后，链路顺序正确。
- **文档**：`diagnostics/AUTOMATION_PROMPT.md` 预检步骤补充解释器解析说明。
## 0.2.49（2026-07-28）- SimNow 回放风险指标限定在观察窗内（打断 halt 再生循环）

- **根因修复**：`diagnostics/export_simnow_replay_snapshot.py` 的 `_risk_for_day` 此前用
  `upto = daily.loc[:day]` 对全回放历史做累计扫描，max drawdown / max consecutive loss
  永远命中 2023-06-19~06-28 固定历史亏损段，导致每个观察日重复触发 warning/halt 并再生成
  pending 风险停机决策记录（07-24、07-27 两次同源），A38 拦截使 20 日有效观察无法累积。
- **方案 A 实现**：新增 `_resolve_risk_start`（优先级：显式 `--risk-start` 参数 >
  `simnow_observation_window.json` 的 `observation_start_date` > 全历史）与 `--full-history-risk`
  开关；`build_snapshot` 新增 `risk_start` / `full_history_risk` 参数并在 meta 记录
  `risk_window_start` / `risk_window_source`；`risk_start` 晚于观察日时回退为单日测量，
  避免配置错误被伪装成"零风险"。回放本身仍从 `--start` 跑全量历史（信号 warmup 需要），
  仅风险指标计算被窗口化。
- **验证**：新增 10 个单测（窗口化/全历史/回退/参数解析/meta 记录）；全量单测
  `954 passed`（`test_handoff_tool.py::test_handoff_status_uses_authoritative_sync_check_engine`
  在 GBK locale 下的既有编码环境问题，`PYTHONUTF8=1` 即通过，与本次改动无关）；
  realdb 门禁 `4 passed`；真实 DB 冒烟（`--start 2026-06-01 --date 2026-07-27`）确认
  meta 记录 `risk_window_start=2026-07-27 / source=observation_window_config`，
  drawdown/consecutive_loss 不再包含 2023-06 陈旧段。
- **文档**：`diagnostics/ACCEPTANCE.md` 风险门禁一节补充指标测量口径说明。
## 0.2.48（2026-07-28）- czsc 1.0.0rc8 升级 review 修复与补充披露

- **行为差异报告强化**：
  - 重新生成 `diagnostics/czsc_upgrade_fixtures/`，设置 `CZSC_MAX_BI_NUM=10000`，
    确认本次真实数据集上的笔数未触顶；报告新增"`max_bi_num` 截断披露"章节。
  - 信号对比从终端快照改为**逐 bar 回放**，输出每个信号键的转态次数与时间点差异。
  - 补充 ZN888 分型数量 4.8 倍差异的根因说明：1.0.0rc8 的 `fx_list` 暴露大量候选分型，
    按笔端点确认的口径统计后各品种差异不大；ZN888 的高波动产生了更多被否决的候选。
- **research-mode 基准位移披露（生成机制存在缺陷，实际正确落地见 0.2.52）**：
  计划在 `diagnostics/czsc_upgrade_behavior_diff_report.md` 中显式列出
  `test_position_sizing_research_equivalence.snapshot.json` 刷新前后的 SC888/RB888
  Bucket-B 指标（SC888 total_return_pct 3.794%→0.646%、sharpe 0.809→0.242、
  三买多头 4 笔→1 笔等），并新增 `diagnostics/czsc_upgrade_failure_attribution.md`
  逐条说明被修改测试夹具的归因（笔算法差异 vs 其他）。
- **HTML 报告两项附加功能补录决策记录**：
  - B/S 买卖点序号标注（`_build_bs_payload` 的 `label` 字段 + `_bs_label_series`）
    与 echarts.min.js 内联去 CDN 化（`chan_strategy/vendor/echarts.min.js`）并非 czsc
    升级原设计范围；本次选择保留并补录 HANDOFF.md 决策记录与 CHANGELOG 条目，
    理由是两者直接提升报告可读性与离线可用性，且已有配套单测与样例报告。
  - 评估内联 1.1MB JS 对 `diagnostics/` 目录的膨胀影响：当前 `diagnostics/` 已包含
    大量历史报告与 fixture，单份 HTML +1MB 在可接受范围内，但后续批量归档时应考虑
    将大体积 sample report 移入 `diagnostics/archive/` 并保留最新一份。
- **Phase 4 依赖环境记录**：`czsc==1.0.0rc8` 新增运行时依赖 `polars`、`scipy`、
  `statsmodels`、`wbt>=0.2.1`、`typer` 经验证均可正常导入（`python -m pip check` 干净），
  其中 `wbt` 为 PyPI 包 `wbt`（weighted-biv-explorer）0.6.0；与本仓库既有依赖无冲突。

## 0.2.47（2026-07-28）- czsc 库升级至 1.0.0rc8（Rust 重写）

- **依赖升级**：`requirements.txt` 中 `czsc` 从 `0.9.51` 精确 pin 到 `1.0.0rc8`。
- **导入路径迁移**：`czsc.objects` / `czsc.enum` / `czsc.utils.echarts_plot` /
  `czsc.utils.bar_generator` 等已删除路径全部改为从顶层 `czsc` 导入或本地 vendored 实现；
  `CZSC(bars=...)` 关键字调用改为 `CZSC(bars_raw=...)`。
- **kline_pro 本地 vendoring**：由于 `czsc.utils.echarts_plot` 在 1.0 中被删除，
  将原 `kline_pro` 图表函数与所需 `SMA`/`MACD` 辅助函数 vendored 到
  `chan_strategy/vendor/echarts_plot.py`，保证 HTML 回测报告渲染行为不变。
- **240 分钟周期映射**：`backtest_engine.py` / `data_adapter.py` / `czsc_adapter.py`
  的周期映射表在 czsc 1.0（提供 `Freq.F240`）时映射到真实 `F240`，在 0.9.x 回退到 `F120`，
  保持与旧版本兼容。
- **行为差异披露**：新增 `diagnostics/czsc_upgrade_bi_diff.py` 与
  `diagnostics/czsc_upgrade_diff_report.py`，在 5 个期货连续合约真实历史数据上量化
  0.9.51 与 1.0.0rc8 的笔/中枢/买卖点信号差异；完整报告见
  `diagnostics/czsc_upgrade_behavior_diff_report.md`（RESEARCH-ONLY）。
- **测试适配**：针对 1.0 中 `RawBar`/`FakeBI` 变为 Rust 不可变对象、
  `FX` 行为语义变化等情况，调整相关单元测试夹具，避免原地属性修改或实例化原生类型。
- **纪律重申**：本次升级会改变同一历史数据上的笔边界与部分信号输出；在通过正式 SimNow
  前瞻观察之前，不应视为"已验证可用"。
- **回滚路径**：`requirements.txt` 中 `czsc==1.0.0rc8` 为单行独立改动，可单独 revert；
  若需回退到 `0.9.51`，同时恢复 `chan_strategy/vendor/` 的使用（即改回
  `from czsc.utils.echarts_plot import kline_pro`）即可。

## 0.2.46（2026-07-27）- 风险/成本/数据质量披露强化与配置漂移防护

- **数据质量 fail-closed 门禁**：`BacktestEngine.run()` 计算 `unparseable_row_rate`，
  当超过 `STRATEGY_CONFIG["max_unparseable_row_rate"]` 时中止运行（默认 `None` 保持历史行为，
  `formal_evaluation_config()` 设为 `0.001`）。
- **成交价格 tick 取整**：新增 `price_tick_rounding` 配置开关与
  `Position._round_price_to_tick`，正式评估模式下记录成交价按交易所最小变动价位取整。
- **PortfolioCoordinator 回撤熔断**：weight-based 联合回放路径现在具备与
  `PortfolioLedger`（`sizing_model="risk"`）同等的持久性、跨交易日回撤熔断语义。
- **配置键单一真值硬化**：核心风控/配置键从 `STRATEGY_CONFIG.get(key, 字面量默认值)` 改为
  `STRATEGY_CONFIG[key]` 硬索引（`test_a53_config_signal_cleanup.py` 新增 AST 级回归防止再引入
  字面量 fallback）；删除两个从未被消费的历史配置键（`base_freq`/`confirm_freq`、`total_capital`）。
- **报告披露扩展**：生成的报告新增 `margin_model_caveat`、`limit_halt_rule_caveat`、
  `slippage_model_caveat` 等字段，把研究性假设内联披露给下游报告消费方。
- **仓库卫生**：`_patch_backtest*.py` 一次性补丁脚本与根目录 `test_backtest_idempotent.py`
  按仓库既有约定重新标注/迁移；新增 `tests/unit/test_repo_hygiene.py` 覆盖上述及
  data_cache 清理、`IN_FLIGHT_CHANGES.md` 清单的卫生检查。

不涉及任何交易/信号逻辑变更；均为成本/风险/数据质量记账、披露与配置单一真值强化。

## 0.2.45（2026-07-27）- A105 可复用 HTML 可视化回测报告模板

- **新增 HTML 可视化回测报告**：新增 `chan_strategy/html_report.py`，为每次回测自动生成一份
  交互式 HTML 报告（默认关闭， opt-in）。报告基于 `pyecharts` 的 `Tab()` 多标签页，每品种一页，
  包含 K 线图、成交量、MACD、笔（bi）、中枢（zhongshu）markArea  overlay、多空买卖点标记、
  成交订单清单 HTML 表格及单品种摘要统计卡。
- **引擎集成**：`BacktestEngine.generate_report()` 在 `html_report_enabled=True` 时生成单品种
  HTML 报告并写入 `report["html_report_path"]`；`PortfolioEngine.run()` 在组合模式下生成多标签
  组合 HTML 报告。默认 `html_report_enabled=False` 时报告字典与改动前字节一致。
- **数据结构扩展（纯附加）**：
  - `BacktestEngine.run()` 额外保留 `self.czsc_trade`（交易周期 CZSC 对象），供报告模块读取笔/中枢。
  - `Position._close_long` / `_close_short` 生成的 pair 字典增加 `"direction": "long"/"short"`，
    用于买卖点标记区分多空；未删除/重命名任何已有字段。
- **配置扩展**：`STRATEGY_CONFIG` 新增 `html_report_enabled`（默认 `False`）与 `html_report_dir`
  （默认 `examples/czsc_strategy/diagnostics/`）。
- **依赖声明**：`examples/czsc_strategy/requirements.txt` 新增 `pyecharts==2.1.0`。
- **新增单测**：`tests/unit/test_html_report.py` 覆盖 payload 形状、bi/zs/bs 字段、HTML 渲染冒烟、
  toggle 开关兼容性、pair 方向字段、组合报告集成；不依赖网络/SimNow/真实数据库。

## 0.2.44（2026-07-26）- Codex 独立复核 follow-up（关键风控单一真值与 handoff wrapper）

- **关键风控参数单一真值补漏**：Codex review 复核 0.2.43 后发现
  `positions.py` / `portfolio_engine.py` / `portfolio_ledger.py` 仍有部分核心风控键使用
  `STRATEGY_CONFIG.get(key, 字面量默认值)`，与 0.2.43 "fallback 字面量硬化"声明不完全一致。
  现已将 `sizing_model` / `risk_per_trade_pct` / `max_margin_pct` / `limit_halt_model` /
  `portfolio_risk` / `weighting` / `daily_loss_limit_pct` / `max_symbol_margin_pct` /
  `cluster_gross_cap` / `daily_agg` / `night_session_start_hour` 等关键键改为单一真值读取；
  `PortfolioCoordinator` / `PortfolioLedger` 的局部测试配置先叠加到 `STRATEGY_CONFIG` 基线，
  再硬索引，避免测试夹具必须复制全量配置。
- **新增配置漂移回归测试**：`tests/unit/test_a53_config_signal_cleanup.py` 新增 AST 级检查，
  锁定上述核心风控键不得重新引入带字面量默认值的 `.get()`。
- **handoff wrapper 修复**：A104 将 `tools/sync_check.py` 改为根级 sync_guardian 的 thin wrapper 后，
  `tools/handoff.py status` 仍从本地 wrapper 导入 `_load_config` 等内部函数，导致 ImportError。
  现已改为直接导入根级 `tools/sync_guardian/sync_check.py` 权威引擎，并新增
  `tests/unit/test_handoff_tool.py` 子进程回归。
- **xfail 披露修正**：`tests/unit/test_second_buy_real_path.py` 与本条 changelog 明确区分：
  前 3 个 xfail 是已废弃 `get_legacy_signals` 路径；第 4 个验证器用例走生产
  `sell_signals.get_all_signals()`，但当前失败原因是历史夹具未覆盖出二买状态，不是生产路径在
  已覆盖结构下输出错误二买信号。
- **测试环境耦合修正**：`test_run_per_symbol_engines_sets_risk_sizing` 显式传入不存在的
  unit-test DB 路径，避免测试 sizing override 时误探测本机默认 SQLite 路径并因权限/缺库失败。

## 0.2.43（2026-07-26）- AI_REVIEW_REPORT_2026-07-26 中高问题修复（术语、死配置、凭据卫生、组合回撤熔断）

针对 `AI_REVIEW_REPORT_2026-07-26.md` 列出的 14 条 🟠 中危问题逐项核实并修复：

- **凭据卫生**：`diagnostics/simnow_connection_config.example.json` 用户名/密码改占位符；
  `skill_build/llm_eval_config.json` 清空硬编码 DeepSeek key，改走 `DEEPSEEK_API_KEY` 环境变量
  （两文件均未被 git 跟踪，非公开泄露，属本地卫生修复）。
- **死配置清理**：`STRATEGY_CONFIG` 删除从未被消费的 `base_freq`/`confirm_freq`/`total_capital`
  三个键（引擎固定从 1 分钟重采样，"次级别确认"从未实现）；README 周期映射表同步更新。
- **术语澄清（"确认"三义）**：README 新增专节区分买卖点确认笔/中枢结构确认/已删除的次级别确认；
  `signals.py` 相关 docstring 同步修正不实表述（`signal_divergence_status` 不再声称支持"确认"档位）。
- **score 死字段**：`signals.py` 模块 docstring 明确 score 段为装饰性字段，不参与
  `Signal.is_match` 匹配/仲裁/仓位计算（契约见 `test_signal_contract.py`，行为未变）。
- **zhongshu.py 标准差异声明**：模块 docstring 补充与缠论标准/czsc 库 ZS 对象的已知偏离
  （`max_bis` 封顶、`lookback` 截断、入场 `mode="recent"` 与风控 `mode="segment"` 的口径差异）。
- **参数沿革 + 适用前提**：README 新增风控参数沿革说明（源自 A 股原型经验值，未按期货重新优化）
  与"适用前提与失效环境"节；`regime_model`/`atr_chop_filter` 补入开关清单。
- **根目录残留治理**：`test_second_buy_bug.py`/`test_second_buy_real_path.py` 两个真实回归测试
  迁入 `tests/unit/`（迁移后发现 4 个用例失败：前 3 个位于已废弃 `get_legacy_signals`
  路径，第 4 个验证器用例走生产 `sell_signals.get_all_signals()` 聚合入口但失败原因为历史夹具
  在真实 CZSC 笔识别下未覆盖出二买状态；均已标注 `xfail` 并分别记录原因，不掩盖、不误使门禁变红，
  留作独立任务）；`_debug_zs.py`/`test_czsc_api.py`/
  `test_czsc_api2.py` 补 ONE-SHOT/LEGACY 横幅；`inspect_db.py` 硬编码路径改为
  `CHAN_SQLITE_DB_PATH` 环境变量覆盖（与 `config.py` 同一模式）；`backtesting_demo.ipynb` 补
  LEGACY/DEMO 说明单元格。
- **positions.py fallback 字面量硬化**：≥10 处 `STRATEGY_CONFIG.get(key, 字面量默认)` 改为
  `STRATEGY_CONFIG[key]` 硬索引（键均已在 `config.py` 中定义，字面量默认为纯重复、无实际防御
  作用）；`_sell` 键回退 `_buy` 键的设计保留，但回退目标同样改为硬索引。
- **组合回撤熔断（新能力，默认禁用）**：`PortfolioLedger` 新增 `max_drawdown_breaker_pct`
  （默认 `None`）——从组合权益历史峰值起算、跨交易日不重置的持久性回撤熔断，区别于每日重置的
  `daily_loss_limit_pct`；触发后走 A90 同款强平+阻断新开仓路径（`portfolio_engine.py`
  `_build_joint_report`）。仅在 `sizing_model="risk"` + `portfolio_risk="on"` 的联合回放路径生效，
  默认关闭不影响任何现有行为（868 条既有单测全量通过）；新增 3 条专项单测。
  `run_formal_evaluation.py`（单品种）补充明确的组合级风控范围外声明，并指向
  `PortfolioEngine(portfolio_risk="on")` 作为组合级风控约束下的评估路径。

不涉及信号生成/买卖点判定/回测撮合等核心逻辑变更（`_get_confirming_bi`/`build_zhongshu_from_bis`/
`signal_first_buy` 等函数体本身未改，仅 docstring 与死配置/死字段被处理）。

## 0.2.42（2026-07-22）- A104 遗留 A 股脚本卫生治理（硬编码 token、过期 sync 门禁、合规披露缺失、选股前视披露）
  （用户新一轮全项目 4-subagent 只读审计的 4 个 examples 范围发现，纯披露/卫生修复，
  不触碰 chan_strategy/ 与任何生产风控/信号/回测逻辑）：
  - **发现1（硬编码 Tushare token）**：`debug_pos.py` 不再含 token 字面量，改为
    `os.environ["TUSHARE_TOKEN"]` 读取，未设置时以带可操作提示的 `RuntimeError`
    fail-closed（无任何默认/回退 token）；模块 docstring 增加环境变量要求说明。
    设计范围外的同源问题：`run_stock_backtest.py` 的 `TUSHARE_TOKEN` 常量含同一字面量，
    已按完全相同的 fail-closed 模式一并修复（小偏离，已记入 HANDOFF.md 决策记录）。
    该 token 已存在于 git 历史（commit adac8808），轮换/吊销属仓库外操作，用户已被单独告知。
  - **发现2（过期重复的 sync_check 副本）**：`tools/sync_check.py` 由 314 行独立旧副本
    替换为薄 wrapper（`runpy.run_path()` 委托仓库根 `tools/sync_guardian/sync_check.py`
    共享引擎，经 `__file__` 相对定位 `parents[3]` 到仓库根），自动继承
    `deliverables_policy` 等后续新增门禁；本子项目治理配置 `.synccheck.yml` 保持不变
    （去重的是引擎代码，不是治理规则）。已验证在本目录运行 `python tools/sync_check.py`
    对本地配置 exit 0。
  - **发现3（遗留 A 股脚本可运行但无合规建模、执行点无警示）**：六个遗留脚本
    （`debug_pos.py`/`run_stock_backtest.py`/`run_akshare_backtest.py`/
    `run_baostock_backtest.py`/`czsc_adapter.py`/`czsc_multi_timeframe_strategy.py`）
    文件顶部统一添加同款警示横幅：声明其为已停维护的 A 股原型、当前活跃实现是
    `chan_strategy/`（期货 CTA）、未建模 T+1/涨跌停/停牌/卖出侧印花税/禁止做空、
    成交为即时无约束、输出不得作为策略有效性证据
    （RESEARCH-ONLY / NOT PROMOTION EVIDENCE）。
  - **发现4（run_stock_backtest.py 选股前视/幸存者偏差）**：其股票池按回测窗口结束日
    （2024-12-31）静态选取，构成幸存者偏差/前视；按设计仅在该文件横幅中显式披露该机制，
    不改写选股逻辑（该脚本本批次即被标记为 legacy；point-in-time 选股的真正修复留待其
    重新纳入维护时再做）。
  - 单测通过 780 → 780（not-realdb，**数量不变**——纯注释/banner/token 读取/wrapper
    修复，未增删测试）；`-m realdb` 等价门禁不变通过；双侧 sync_check、Preflight、
    ruff 均通过（见 HANDOFF.md Manual Verification）。RESEARCH-ONLY，不构成交易建议。
## 0.2.41（2026-07-22）- A103 修复同义反复测试断言 + 删除死代码 utils.py
  （第四次全面 re-audit L-NEW-9、L-NEW-10，两处小而独立的修复）：
  - **L-NEW-9（测试断言修复）**：`tests/unit/test_more_coverage.py`
    `test_data_adapter_default_paths_and_errors` 中的
    `X if False else (_ for _ in ()).throw(ValueError(...))` 构造是同义反复断言——
    `if False` 前的 `load_kline_data` 调用永不执行，异常由自身合成抛出，测试恒过、
    从未真实触发「无数据表」错误路径。现已替换为：在同一测试内新建真正零表的
    空数据库（`empty_for_l9.db`，仅 `sqlite3.connect(path).close()`，无任何建表），
    对其真实调用 `SqliteDataAdapter(...).load_kline_data("T", table_name=None)`，
    仍在 `pytest.raises(ValueError, match="没有找到")` 内——断言特异性不变，但现在真实
    触发了 `data_adapter.py` 的「数据库中没有找到数据表」raise；新 adapter 按本文件既有
    `try/finally: adapter.close()` 模式关闭。
  - **L-NEW-10（死代码删除）**：`chan_strategy/utils.py` 整文件删除。其三个函数
    `parse_signal`/`signal_key`/`signal_value` 在删除前经全仓库 grep 复核确认零引用——
    其余同名命中均为 czsc 自有 `Signal.signal_value` 属性、diagnostics 脚本局部变量、
    或测试内独立定义的同名辅助函数（如 `test_exit_model.py` 的 `_signal_key`/`_signal_value`），
    无一 import 自 `chan_strategy.utils`；真实信号解析走 czsc 的 `Signal` 类（`.key`/
    `.signal_value` 属性）。
  - 其余一律未动：未触碰两文件中任何其他测试、未触碰 `test_branch_completion.py`、
    未触碰 `backtest_engine.py`/`positions.py`/`signals.py` 等生产代码。
  - 单测通过：779 → 779（not-realdb，**数量不变**——本系列罕见的「同数量」验收情形，
    只是把一条既有测试的断言变真，未增删测试）；`-m realdb` 等价门禁不变通过；
    双侧 sync_check、Preflight、ruff 均通过（见根 HANDOFF.md Manual Verification）。
    RESEARCH-ONLY，不构成交易建议。

## 0.2.40（2026-07-22）- A102 新增两份 20 日 SimNow 晋升准备度实现的平价回归测试
  （第三次全面 re-audit M-NEW-3；**纯测试新增，明确不是对底层重复实现的修复**）：
  - 背景：`diagnostics/simnow_daily_monitor.py::build_20d_report` 与
    `diagnostics/simnow_promotion_decision.py::decide_promotion` 独立维护同一「20 日晋升准备度」
    判定，子计数已真实分化（前者 `halt_days` 还检查 `order_safety.status=="halt"`、
    `consistency_matched_days` 要求 `matched AND verified`；后者只看 `thresholds.status=="halt"`、
    接受任意真值 `matched`）。当前最终 verdict 仍一致，仅因两者都先经共享且更严格的
    `is_valid_observation()` 门禁（`valid_observation_days >= min_days`）兜底——属「真实但当前惰性」
    的分化，非现行 bug。
  - **范围决定：本次只加回归测试，不合并/不修改任一实现**——两个文件属于正在并发运行的
    SimNow 20 日晋升决策工作流，删除或改动其实现的风险大于关闭一个已被独立确认非现行的分化；
    是否合并留给能直接看到该并发工作流状态的人类维护者作为独立任务决定。
  - 新增 `tests/unit/test_simnow_promotion_parity.py`（全新文件，不扩展既有
    `test_simnow_daily_monitor.py`，避免与并发工作流产生合并冲突），3 条测试：
    (a) 全干净 20 日窗口，两实现 `ready_to_expand` 一致为 True；
    (b) 直接构造分化日（`order_safety` halt 但 `thresholds` 非 halt；`matched=True` 但
    `verified=False`），断言最终 verdict 仍一致为 False，同时显式钉住两实现
    `halt_days`（1 vs 0）与 `consistency_matched_days`（19 vs 20）子计数确实不同——
    这是核心回归钉：未来任何让子计数分化传导到 `ready_to_expand` 分歧的改动会立即 fail；
    (c) 有效观察日不足 `min_days` 的窗口，两实现以同一原因
    （`valid_observation_days < min_days`）一致判定 not ready。
  - 零生产代码变化：`diagnostics/`、`chan_strategy/` 下文件逐字节未动；
    单测通过：776 → 779（not-realdb，净 +3 条新测试）；`-m realdb` 等价门禁不变通过；
    双侧 sync_check、Preflight、ruff 均通过（见根 HANDOFF.md Manual Verification）。
    RESEARCH-ONLY，不构成交易建议。

## 0.2.39（2026-07-22）
- A101 SimNow 准备度门禁 docstring 与实际判定逻辑对齐 + 未检测硬门槛 fail-closed 修复
  （第二次全面 re-audit H-NEW-2，两处相互独立的变化）：
  - **(a) 纯文档澄清（无行为变化，与 A95 M1/A96 M3/A99 保守先例一致）**：
    `chan_strategy/validation.py` `SimNowReadinessChecker.check_readiness` docstring 的
    「条件:」清单此前以 10 项并列 [OK]/[NG] 呈现，读起来像 10 项都是强制门槛；实际代码中
    只有条件 1-4（增量一致性/无重绘/冻结快照确定性/交易样本>=100）是逐项否决 ready 的硬门槛，
    条件 5-10（胜率/盈亏比/回撤/夏普/样本外/参数稳定性）只计入 `passed_count >= 7` 的软配额。
    docstring 现已明确区分两类并写明判定规则（硬门槛全部显式通过 + 10 项中显式通过不少于 7 项）。
    **未触碰 `passed_count >= 7`、未增删任何 checks{} 条目、未触碰 `:993-998` 已准确的硬门槛内联注释**；
  - **(b) 真实的、收窄范围的行为变化（fail-closed，与 A97 `rollover_open_gating` 先例一致）**：
    `signal_stable` 三项与 `enough_trades` 的比较由 `passed is not False` 改为 `passed is True`——
    此前未提供稳定性检查输入（`passed=None`，「未检测」）时硬门槛被静默视为通过，
    现在「尚未证明安全」正确阻断 ready 而非默认放行。已核实唯一生产调用点
    `run_full_validation`（`validation.py:1233-1239`）始终为四项硬门槛提供具体非 None 字典，
    两种写法在该路径行为完全一致，本次收紧只影响省略稳定性参数的直接调用路径；
    未触碰 `passed_count`/配额逻辑，本文件唯一逻辑变化即这四处比较符；
  - 扩展 `tests/unit/test_simnow_readiness_sharpe.py`（A99 文件）新增 3 条回归测试：
    软配额语义钉住（win_rate=0.40 失败但其余全过时 ready 仍为 True、passed_count=8，
    证明这是文档化后的有意设计而非 bug）；fail-closed 回归（省略 signal_freeze 且其余全过时
    ready=False，修复前为 True）；正向用例（四项硬门槛显式通过 + 配额满足时 ready=True、
    passed_count=9）。A99 既有 4 条测试（从不读 ready）原样通过；
  - 单测通过数 773 → 776（not-realdb，净增 3 条新测试）；`-m realdb` 等价门禁不变，
    双侧 sync_check、Preflight、ruff 均通过（见 HANDOFF.md Manual Verification）。
    RESEARCH-ONLY，不构成交易建议。

## 0.2.38（2026-07-22）
- A100 文档化背驰力度比较「进入段/离开段方向可能不一致」为已接受行为（re-audit M-NEW-2；
  **纯 docstring/注释 + 回归测试，无任何信号生成逻辑变化**——本次是对已存在、已测试行为的
  文档澄清，不是行为修改，与 A95 M1、A96 M3 的保守先例一致）：
  - `chan_strategy/signals.py` `signal_divergence_status` docstring 新增「方向约束」段，
    明确三点：(a) 进入段 `enter_bi` 仅按位置选取（中枢前一笔；中枢前无笔时回退为中枢自身
    第一笔），其方向与离开段 `leave_bi` **不保证、也不要求一致**；(b) `_divergence_power`/
    `_bi_power`/`_macd_power_for_segment` 只做纯幅度比较，与方向无关，反向笔对不会被过滤
    或报错；(c) 该行为已被既有测试 `test_signal_first_buy_differs_between_models`（fixture 中
    `zs_start_idx == 0`，enter_bi 与 leave_bi 方向相反）作为合法输入对待——声明这是对现状的
    描述而非缠论权威论断，若未来经领域评审确认需强制方向匹配，应作为独立任务单独评估回归影响；
  - 三处 `enter_bi`/`enter_idx` 选取点（`signals.py` `signal_divergence_status` 与
    `signal_first_buy`；`sell_signals.py` `signal_first_sell`）各加一两行内联注释，指向
    docstring 的完整说明，未重复展开；
  - **零逻辑变化**：未触碰 `_divergence_power`/`_bi_power`/`_macd_power_for_segment`、未触碰任何
    `enter_bi`/`leave_bi` 选取代码、未触碰任何方向过滤代码（diff 仅含 docstring/注释行）；
    审核报告自带的修复建议 (b)（向前搜索最近同向笔）是真实的信号生成行为变化，影响全部
    背驰/一买/一卖分类与历史回测结果，且需缠论领域权威确认，明确不属于本任务范围；
  - 新增回归测试 `tests/unit/test_divergence_macd.py::`
    `test_divergence_power_ignores_leg_direction_mismatch`：直接构造方向相反的 enter/leave
    笔对，断言 `_divergence_power` 在 amplitude 与 macd 两种模式下均正常运行、返回纯幅度比较
    结果、不按方向过滤——把既有测试只是顺带覆盖的行为显式钉住；
  - 单测通过数 772 → 773（not-realdb，净增 1 条新测试）；`-m realdb` 等价门禁不变，
    双侧 sync_check、Preflight、ruff 均通过（见 HANDOFF.md Manual Verification）。
    RESEARCH-ONLY，不构成交易建议。

## 0.2.37（2026-07-22）
- A99 SimNow 准备度门禁夏普比率口径统一为已强制执行的 0.3（re-audit M-NEW-1；**纯文档/提示文案对齐，
  未改动强制门禁本身**——`checks["夏普比率>=0.3"]` 的键名与 0.3 阈值逐字节不变，强制门槛仍是 0.3，
  本次改动不是门禁收紧）：
  - `chan_strategy/validation.py` `SimNowReadinessChecker.check_readiness` docstring 条件 8 由
    「夏普比率 >= 0.5」改为「夏普比率 >= 0.3」，与实际强制检查一致；
  - 同文件 `generate_optimization_suggestions` 的夏普提示阈值由 `sharpe < 0.5` 改为 `sharpe < 0.3`，
    提示文案由 `(...<0.5)` 改为 `(...<0.3)`，与该函数内其余指标（胜率/盈亏比/回撤）
    「提示阈值与门禁阈值一致」的既有模式对齐——修复了同一报告中 `0.3 <= sharpe < 0.5` 时
    准备度区段打印 `[OK]` 而优化建议区段同时警告「夏普比率偏低」的自相矛盾输出；
  - 为何向 0.3 对齐而非 0.5：强制检查是已在生产使用的真实行为，收紧到 0.5 是无设计依据的
    追溯性行为变更（高风险），而对齐两处描述性引用是零行为变化的文档修复（与 A95 M1、A96 M3
    的保守先例一致）；若日后确认 0.5 才是本意，收紧门禁是有意的单行后续改动；
  - 新增 `tests/unit/test_simnow_readiness_sharpe.py`（这两个函数的首个测试覆盖）：
    `sharpe_ratio=0.3` 恰好通过门禁、`0.29` 不通过、建议函数在 0.3 不产生夏普提示、
    在 0.29 产生文案含 `<0.3`（非 `<0.5`）的提示，共 4 条；
  - 单测通过数 768 → 772（not-realdb，净增 4 条新测试）；`-m realdb` 等价门禁不变通过，
    双侧 sync_check、Preflight、ruff 均通过（见 HANDOFF.md Manual Verification）。
    RESEARCH-ONLY，不构成交易建议。

## 0.2.36（2026-07-22）
- A98 `exit_model="structural_atr"` 部分止盈退出纳入 `limit_halt_model="enforce"` 门控
  （re-audit H-NEW-1 + L-NEW-1；真实行为变化）：
  - `chan_strategy/positions.py` `Position.update` 的 structural_atr 部分止盈分支
    （此前是全文件唯一未经 `_reject_fill_at_limit(...)` 守卫的退出路径）现在与其他所有退出分支
    一样先经守卫：当退出方向触及不可成交涨跌停带（如多头退出遇跌停）时，该 bar 的部分止盈
    成交被拒绝——不成交、`_partial_tp_done` 保持 `False`、`_pending_fill_rejected_at_limit`
    置 `True`，下一 bar 重试（与既有的信号平仓/固定止损/超时/ATR 移动止损被拒行为完全一致）；
  - `limit_halt_model` 为 `"off"`/`"aware"` 时行为逐字节不变（`_reject_fill_at_limit` 在非
    enforce 模式下恒返回 `False`）；structural_atr 其余退出分支与全部 legacy 分支未触碰；
  - L-NEW-1（部分止盈 pair 上 `fill_rejected_at_limit` 携带陈旧值）作为同一修复的副作用
    自然解决——`_scale_out` 现在仅在 `_reject_fill_at_limit` 针对本次成交尝试运行之后才会
    被执行，pair 上的审计字段反映真实状态，无需额外代码改动；
  - 新增回归测试 `tests/unit/test_limit_halt_enforce.py::
    test_enforce_rejects_structural_atr_partial_tp_at_lower_limit`（被拒场景：仓位不变、
    无新 pair、`_partial_tp_done` 仍为 `False`、拒成交审计标记置 `True`）与
    `test_enforce_allows_structural_atr_partial_tp_when_not_at_limit`（正向场景：enforce 下
    非涨跌停 bar 部分止盈正常成交，`pair["fill_rejected_at_limit"] is False`）；
  - 单测通过数 766 → 768（not-realdb，净增 2 条新测试）；`-m realdb` 等价门禁通过；
    双侧 sync_check、Preflight、ruff 均通过（见 HANDOFF.md Manual Verification）。
    RESEARCH-ONLY，不构成交易建议。

## 0.2.35（2026-07-22）
- A97 `rollover_open_gating="on"` 检测失败改为 fail-closed（audit M2 + H2 缓解；真实行为变化）：
  - `chan_strategy/backtest_engine.py` 回测主循环前的 rollover 检测失败分支（原打印警告并静默禁用门控、
    降级为无保护运行）改为 `raise ValueError(...)`，对齐 `limit_halt_model` 既有的 fail-closed 模式：
    报错信息含失败原因（`transitions["unavailable"]` 或捕获的检测异常）与显式退出路径
    （修复元数据/检测问题，或显式设 `rollover_open_gating="off"` 放弃该保护）；
    触发条件为配置值本身 `"on"`，不限于 `formal_evaluation_config()` 路径；
  - 「检测成功但窗口内无排除日期」分支（合法非错误结果）完全未动；`rollover_open_gating="off"`
    默认路径字节级不变；`rollover_stat_tagging` 使用独立的 `_rollover_excluded_dates()` best-effort
    路径，与本改动无关、未触碰；
  - `tests/unit/test_rollover_open_gating.py::test_gating_reports_unavailable_when_metadata_missing`
    断言方向翻转：同一非存在 DB 构造下断言抛出 `ValueError` 而非优雅降级（修复测试所编码的 bug，
    非删除覆盖）；该文件其余测试与 `test_formal_evaluation.py` 全部不变通过；
  - 真实数据冒烟：`formal_evaluation_config()` + `rollover_open_gating="on"` 对真实历史库
    （AP888/RB888）检测成功、回测正常完成不抛新异常（见 HANDOFF.md Manual Verification）。
    RESEARCH-ONLY，不构成交易建议。

## 0.2.34（2026-07-21）
- A96 文档化 `signals.py` 遗留信号系统为独立维护系统而非冗余副本（audit M3；纯 docstring，无行为变化）：
  - `chan_strategy/signals.py` `signal_second_buy`/`signal_third_buy` 的 `.. deprecated::` 块扩写，
    明确四点：(a) 属于 `get_legacy_signals()` 自包含的「遗留信号系统」，(b) 与 `sell_signals`
    同名实现为独立维护的代码路径、已分叉且不保证同输入同结果，(c) 拥有专属单测覆盖
    （`tests/unit/test_remaining_coverage.py`，具名 `test_base_second_buy_edge_branches`/
    `test_base_third_buy_edge_branches`），转发会静默使 monkeypatch 失效，(d) 新代码应使用
    `sell_signals` 的实现；
  - `get_legacy_signals()` 的 `.. note::` 与废弃的 `get_all_signals()` 包装器的 `.. deprecated::`
    块以同样的「独立维护、非冗余副本」框架强化说明；
  - 未改任何函数逻辑/签名/返回值，未触碰 `sell_signals.py`、未触碰任何测试；单测通过数不变
    （761 not-realdb），`-m realdb` 等价门禁逐字节一致，双侧 sync_check、Preflight、ruff 均通过。
    RESEARCH-ONLY，不构成交易建议。
## 0.2.33（2026-07-21）
- A95 文档化 `risk_per_trade_pct` 为名义风险预算而非硬亏损上限（audit M1；纯注释/docstring，无行为变化）：
  - `chan_strategy/config.py:87` 内联注释改为明确说明该参数是**名义**单笔风险预算（权益的 0.5%），
    按止损距离反推手数，**不是**保证的最大亏损——实际亏损可经非止损退出路径（结构破坏退出、
    超时退出、跳空穿越止损价）超过该预算；
  - `chan_strategy/positions.py` `_size_open()` docstring 新增说明段：预算仅在「固定止损恰好
    在止损价成交」时精确实现，并具名列出三条可超预算的退出路径（structural failure、timeout、
    gap-through，含 `stop_execution_model="intrabar"` 仅以 `min(trigger, close)` 部分建模跳空
    的说明）；
  - grep 确认 `risk_per_trade_pct` 生产代码仅两处（`config.py:87`、`positions.py:1030`），
    无其他暗示硬上限的注释；冻结验收文档 `diagnostics/joint_replay_acceptance_2026-07-17.md`
    按任务范围未触碰；未改任何逻辑、默认值或测试断言；单测通过数不变（761 not-realdb），
    `-m realdb` 等价门禁逐字节一致，双侧 sync_check、Preflight、ruff 均通过。
    RESEARCH-ONLY，不构成交易建议。

## 0.2.32（2026-07-21）
- A94 文档化背驰门禁中恒假的「确认」分支（audit M4；纯注释，无行为变化）：
  `chan_strategy/positions.py` 两处消费点（`_research_second_buy_allowed` 与
  `_research_short_open_allowed` 的 P4 背驰检查）在 `if not (div_val.startswith("疑似") or div_val.startswith("确认")):`
  上方各加一段注释，明确说明 `signal_divergence_status()`（`signals.py`）当前只会产生
  「疑似」、永远不会产生「确认」，因此该 `or` 的「确认」半边当前为死代码，但出于前向兼容
  （未来背驰分级增强若新增真正的「确认」档）保留，且运行时零成本、请勿删除。
  未改动 `if` 条件本身，未触碰 `signals.py`，未新增背驰档位；未加 `# pragma: no branch`
  标记（coverage 分支分析不会把 `or` 的两半拆成独立分支，该标记在此处无意义——与
  `signals.py:340` 已有的互补方向 `pragma` 场景不同）。单测通过数不变（761 not-realdb），
  `-m realdb` 等价门禁逐字节一致，双侧 sync_check、Preflight、ruff 均通过。RESEARCH-ONLY，不构成交易建议。

## 0.2.31（2026-07-21）
- A93 review 打回修复（codex 拒绝项闭环，无行为变化）：
  - `chan_strategy/positions.py` 签名行 `trailing_start` 注释删除过时的 `1.5%` 字面量
    （该参数现为 `None` 哨兵、运行时取 `STRATEGY_CONFIG`，字面百分比只会再次漂移），改为配置中性表述。
  - `positions.py` 与 `tests/unit/test_positions.py` 的 30 条 ruff 存量告警清零：28 条
    `UP006`/`UP035`/`UP045`/`F401` 由 `ruff check --fix` 机械修复（`typing.List/Dict/Tuple/Optional`
    → 内置泛型 / `X | None`，删除未使用的 `typing.Dict` 与 `pytest` 导入）；1 条 `B905`
    （`Signal` 值匹配的 `zip(...)`）按审查指引显式加 `strict=False`——两侧均已 `[:3]` 截断，
    最短者胜的既有语义保持不变，不用 `strict=True` 避免短分段信号崩溃。
    `ruff check` 对两个触及文件现在 0 告警。纯类型标注现代化 + 注释修正，无任何运行时行为变化；
    全部单元测试（761 not-realdb + 4 realdb 等价门禁）通过数不变。

## 0.2.30（2026-07-21）
- A93 消除 `Position()` 孤儿移动止损默认值（audit M5）：`Position.__init__` 的
  `trailing_start`/`trailing_drawback_pct` 默认参数从硬编码 `150`/`0.4`（与
  `STRATEGY_CONFIG` 的 `trailing_start_bp=300`/`trailing_drawback_pct=0.25` 漂移）
  改为 `None` 哨兵，并在 `__init__` 内按既有 `commission_rate`/`slippage` 同一模式回退到
  `STRATEGY_CONFIG.get("trailing_start_bp", 300)` / `STRATEGY_CONFIG.get("trailing_drawback_pct", 0.25)`
  ——不经 `create_*` 工厂直接构造 `Position(...)` 的调用方（测试/诊断脚本/外部调用）不再静默拿到
  与单一真相配置不一致的旧默认值；显式传参仍原样覆盖。未触碰 `_research_trailing_params()` 与任何
  `create_*` 工厂（它们始终显式传值，行为不变）；未改 `config.py` 任何默认值，无既有回测输出变化。
  新增 `tests/unit/test_positions.py::test_position_direct_construction_uses_config_trailing_defaults`
  证明直接构造（省略或显式 `None`）时取配置值、显式覆盖仍生效。RESEARCH-ONLY，不构成交易建议。

## 0.2.29（2026-07-21）
- A92 熔断强平真实数据验证 + 报告熔断警示（audit H3；未改 `portfolio_ledger.py`、未改
  `_build_joint_report()` 强平驱动逻辑、未改 `config.py` 默认值）：
  - Part 1 真实数据证明：新增 `diagnostics/joint_replay_flatten_stress_check.py`——同一
    5 品种/同一窗口（AP888/RB888/SC888/A888/ZN888，2022-01-01~2026-04-24）以**运行时临时收紧**
    的 `daily_loss_limit_pct=0.005`（上下文管理器覆盖后还原，非配置默认值变更）重跑联合回放：
    49 次触发、101 笔 `flat_events`（ZN888:31/AP888:30/RB888:22/A888:18；68 笔即时 + 33 笔滞后），
    逐笔对照独立重载的 bar 数据验证全部 101 笔 `flat_price` 等于**该品种自身 tick 的 `bar.close`**；
    跨品种滞后强平价不变量以真实时间偏斜证实——2022-04-22 21:59 触发 tick A888 以自身收盘 6115.0
    即时强平，滞后的 AP888 于 3570 分钟后（跨周末）2022-04-25 09:29 以**自身**收盘 8561.0 强平
    （绝非触发 tick 价格）；无任一笔平仓早于开仓。阈值搜索全程记录（影子回放一次映射日 PnL 轨迹：
    0.025~0.0075 首触发均为 2022-03-30 空仓已知案例，0.005 首触发 2022-01-14 ZN888 一买多头实仓）；
    同 bar 先开后平边界案例（ZN888 2024-09-05 13:59，开盘 23030→收盘 22900，因果有序非 bug）
    已记录于 `diagnostics/joint_replay_flatten_stress_2026-07-21.md`（含 RESEARCH-ONLY 横幅）；
  - Part 2 诚实警示：`backtest_engine.py generate_report()` 新增 `circuit_breaker_caveat`
    （单品种口径声明无组合级熔断保护）；`portfolio_engine.py` `_build_off_report()`/
    `_build_on_report()` 新增同名字段（off 路径无保护；权重口径 `PortfolioCoordinator` 的
    flat_events 仅为内部权重簿记、非真实平仓）；`_build_joint_report()` 新增 `flatten_status`
    （`_flatten_status_note()`），区分「本运行未触发」「触发但无仓可平（A90 已记录的 2022-03-30
    情形）」「触发且实际强平 N 笔」三种状态，消除空 `flat_events` 的歧义；
  - `tests/unit/test_position_sizing_research_equivalence.py`：Bucket-A 形状契约补
    `circuit_breaker_caveat: str` 并在模块 docstring 分类中登记（纯新增键，不触碰既有基线值比较）；
  - 单测 760 通过（`-m "not realdb"`）；`-m realdb` 实跑（AGENTS.md 守则要求）发现**既有**失败——
    `test_research_mode_equivalence_to_baseline` 的 SC888 `sharpe_ratio` 与基线差 1 ULP
    （baseline=0.8091974663759458 actual=0.809197466375945）；已用 pristine HEAD（stash 全部 A92
    改动后复跑）证明该失败与本任务无关（A92 不触碰夏普计算），按升级规则记录于根 HANDOFF.md
    决策记录而非顺手修复（等价性门禁的浮点严格性问题属另一任务）；双侧 sync_check 通过。
    RESEARCH-ONLY，不构成交易建议。

## 0.2.28（2026-07-21）

- A91 等价性门禁补强（codex review 打回项 1：`sub_strategies` 分类为 Bucket-B 却未快照/比较）：
  - `tests/unit/test_position_sizing_research_equivalence.py`：`_run_symbol()` 不再剔除
    `sub_strategies`，快照含完整 `report`；等价性测试新增独立的嵌套字典全等断言
    （`sub_strategies` 为 `{pos_name: {stat: value}}` 结构，不进 `EQUIVALENCE_REPORT_FIELDS`
    扁平标量白名单，模块 docstring 已说明原因）——消除“聚合计指标相同但子策略级交易分布
    漂移”这一静默回归盲区；
  - 正向证明：scratch edit 篡改 `Position.evaluate()` 的 `win_rate`（+0.01）后
    `test_research_mode_equivalence_to_baseline` 按预期失败（报 sub_strategies 差异），
    随后已回退，`chan_strategy/` 零改动；
  - 基线快照重新生成（现含 `sub_strategies`）；`-m realdb` 与 `-m "not realdb"` 全量测试、
    双侧 sync_check、Preflight 均通过。

## 0.2.27（2026-07-21）

- A91 恢复 research 模式等价性门禁效力（audit H1；`generate_report()` 新增 8 个报告字段后
  全字典 `==` 比较必然失败，而 `-m "not realdb"` 默认验收静默跳过该测试）：
  - `tests/unit/test_position_sizing_research_equivalence.py`：改为白名单比较——`pairs` /
    `equity_curve` 全等 + `report` 仅比较 Bucket-B 计算字段（`EQUIVALENCE_REPORT_FIELDS`）；
    Bucket-A 配置回显字段不做基线值比较，但断言其存在性与类型（防形状回归）；模块 docstring
    内记录 `generate_report()` 全部 key 的 Bucket A/B 分类（对照 backtest_engine.py 现行实现）；
  - 同文件 `test_research_mode_additive_fields_take_default_values` 扩展：断言 research 模式下
    `mode_label == "RESEARCH_BASELINE"` 及其余 Bucket-A 字段默认值、`sizing_caveat` 非空；
  - 基线快照重新生成前独立复核：两品种 `pairs`/`equity_curve` 与旧基线逐字节一致、
    Bucket-B 共有 key 零值差异（仅 `unparseable_rows_skipped` 为旧基线缺失的新增计算字段，
    值=0，已随新基线固定）；快照已按当前代码重生成；
  - 正向/反向证明：临时新增配置回显 key 测试仍通过、篡改 Bucket-B 字段测试必失败
    （scratch edit 均已回退，`chan_strategy/` 零改动）；
  - `AGENTS.md` 新增“测试验证守则（realdb 提醒）”：触及 `positions.py` / 报告生成 /
    research 仓位逻辑的改动，验收必须实跑 `-m realdb`。

## 0.2.26（2026-07-20）

- A90 熔断强平实现（按 `docs/design/a89-forced-liquidation-design.md` 逐条落地，daily loss limit
  触发后强制平仓；未改 `positions.py` / `backtest_engine.py`）：
  - `chan_strategy/portfolio_engine.py` `_build_joint_report()`：
    - 检测 `ledger.daily_loss_limit_active` 的 False→True 跳变（在调用
      `check_daily_loss_limit()` 前捕获前值）：触发品种 X 立即以该 tick 自身 `bar.close`
      （`post_item[2]`）调用既有原语 `ChanTimingStrategy.flatten_all_positions(price, dt,
      "daily_loss_limit_flatten")`（`positions.py:2122`，本任务未改动）；
    - 驱动器新增 `flatten_pending: set[symbol]` 循环态（不放在 `PortfolioLedger` 上）：触发时
      把其余全部成功品种加入；主循环在处理某品种 `"pre_open"` yield 之前检查，若 pending 则
      用**该品种自己当前 tick 的 `bar.close`**（经 `engines[symbol].trade_bars` + bisect 查找，
      绝不用触发 tick 的价格——对滞后品种那是未来函数）先强平再走正常 pre_open/gating 流程；
    - 新增 `flat_events` 诊断列表，形状对齐 `PortfolioCoordinator.flat_events`（
      `portfolio_engine.py:291-299`）减去权重簿记专用 `weight` 字段、加 `reason` 字段：
      `dt`/`symbol`/`strategy`/`open_dt`/`open_price`/`flat_price`/`reason`；强平前先捕获
      该品种 `strategy.positions` 中 `pos.pos != 0` 的持仓快照，只为实际被平的仓位记账；
    - 报告字段：`"flat_events": flat_events` 新增；`"flatten_on_breach"` 由
      `"not_implemented_see_A89"` 改为 `"implemented_see_A90"`（A87 的诚实标注已过时）；
    - 新开仓拦截的起止语义不变（`daily_loss_limit_active` 当日拦截、次日
      `update_trading_day()` 重置，均沿用 A87）；单品种/cluster 保证金上限仍只拒开不强平；
  - `chan_strategy/portfolio_ledger.py`：仅更新两处过期文档字符串（A87 “仅拦截不开仓”范围说明
    改为指向 A90 驱动器侧强平），零行为变化；
  - `tests/unit/test_a87_joint_replay.py`（16 → 17 项）：
    - `test_daily_loss_limit_does_not_force_close_positions` 按新设计语义重写为
      `test_daily_loss_limit_flattens_open_positions`（同 fixture 反转预期：触发品种在触发
      tick 立即强平、同 tick 已处理品种在下一 pre_open 以自身 close 强平、`flat_events`
      逐字段精确断言、只强平一次）；
    - 新增 `test_daily_loss_limit_lagging_symbol_flattens_at_own_price`：构造 BBB 在触发 tick
      无 bar 的滞后场景，验证 BBB 在自己下一 pre_open 以**自身** 95.0 收盘强平而非触发价 91.0；
    - `test_daily_loss_limit_blocks_rest_of_day_then_clears`：BBB 在触发 tick 被强平先于自身
      止损执行（同价 89.5，经济结果一致），其 pair reason 由 "止损" 变为
      "daily_loss_limit_flatten" —— 本任务唯一改动的既有行为断言；拦截/次日解除断言不变；
    - 两个 cap 测试补充 `flat_events == []` 断言，锁定“margin-cap 触发不强平”排除项；
    - 无信号冒烟测试的 `flatten_on_breach` 标记断言同步更新；
  - 真实数据冒烟检查：`diagnostics/joint_replay_acceptance_check.py` 新增第 6 项
    `flat_events` 连贯性检查（品种合法、reason 正确、窗口内、open_dt<=dt）并纳入
    `overall_accepted`；触发日覆盖仅作信息性记录（触发时刻组合已空仓时为空属正常），
    改为门禁 `flat_events_non_empty_or_explained`：空 flat_events 仅当每个触发都能由
    “触发 tick 上有策略自身平仓”（`flat_events_trigger_explanations`，检查 pairs 中
    close_dt 恰等于触发 tick 的平仓）解释时才可通过。
    对同一 5 品种/窗口（AP888/RB888/SC888/A888/ZN888，2022-01-01~2026-04-24）重跑：
    已知 2022-03-30 09:29 触发（-3.004%）时刻唯一仍持有的 AP888 一买多头在**同一 tick**
    被策略自身止损平仓（9887→8401，margin 13841.8→0.0），触发检测发生在其后，组合已空仓，
    故 `flat_events` 在真实数据上**为空属设计内行为**而非接线故障——探针（截断窗口前缀复跑
    + 插桩 `flatten_all_positions` 调用记录 + 触发前后 margin/pairs 证据）确认强平机制
    被正确触发且无仓可平；联合回放交易序列/总已实现 PnL 与 A88 已提交基线逐位一致
    （-57,473.587），证明 A90 接线对无仓触发零副作用。强平路径本身由新增单测（含滞后品种
    用自身价格强平的构造场景）覆盖。结果写入 `diagnostics/joint_replay_acceptance_check.json`
    并在 `diagnostics/joint_replay_acceptance_2026-07-17.md` 追加 A90 补遗（详见该文档）；
  - 单测总数 751 → 755（含并行工作流既有的 +3）。RESEARCH-ONLY，不构成交易建议。

## 0.2.25（2026-07-17）

- A89 熔断强平设计文档核验与定稿（纯文档变更，未改任何 `chan_strategy/` / `diagnostics/`
  生产代码、未改任何既有测试断言）：
  - 对 `docs/design/a89-forced-liquidation-design.md` 的全部代码引用逐一核对当前代码库：
    `positions.py:2122` `ChanTimingStrategy.flatten_all_positions()` 存在且全库零调用点（grep 确认）、
    `portfolio_ledger.py:141` `check_daily_loss_limit()` / `:111` `update_trading_day()` 准确；
    修正两处行号漂移——`PortfolioCoordinator.flat_events` 为 `portfolio_engine.py:125`（原写 :124）、
    `PortfolioCoordinator._flatten_all()` 为 `portfolio_engine.py:283`（原写 :282），并补充
    `flat_events` 追加逻辑位于 `portfolio_engine.py:291-299`、协调器版本字段另含 `weight`。
  - 收紧"用哪个价格强平"一节表述：固定止损实际走 `_close_long(stop_fill, dt, "止损")`，
    其中 `_stop_fill()`（`positions.py:893`）在默认 `stop_execution_model="close"` 下返回值即当根
    bar 收盘价——明确该结论成立的前提，消除实现者误读空间。
  - 四个设计决策区（平仓原语形态、强平价格、跨品种时序、重新触发机制）均已含明确决策+理由，
    无开放式问句遗留；`docs/design/` 下无既有 `AGENTS.md` 需同步。

## 0.2.24（2026-07-17）

- A88 联合时钟回放真实数据验收 / sanity-check（沿 A83→A84 模式，对 A87 联合回放做真实数据
  验收，纯只读诊断，未改任何 `chan_strategy/` 生产代码）：
  - 新增 `diagnostics/joint_replay_acceptance_check.py`：以 `sizing_model="risk"` +
    `portfolio_risk="on"` 在真实历史 SQLite 数据库上运行 `PortfolioEngine` 联合时钟回放
    （AP888/RB888/SC888/A888/ZN888，2022-01-01~2026-04-24，与 A83/A84 完全相同的品种与窗口），
    并按 A84 同法独立重跑各品种单引擎进行交叉比对。
  - 全部 sanity 检查通过：5 品种零数据错误；联合权益曲线 19,470 行（与 A83 台账行数一致）
    权益始终为正、保证金非负、最大保证金利用率 6.21%（A83 为 6.49%）、利用率最大跳动 3.44pp
    无异常跳变；cluster 成员大小写不敏感成立，`margin_by_cluster` 实测将 RB888/SC888/ZN888
    归入 industrial_energy。
  - `blocked_opens` 非空且连贯：58 条全部为 `daily_loss_limit`，集中在 2022-03-30——当日
    09:29 组合日 PnL 触及 -3.004%（阈值 -3%）后当日全部品种新开仓被拦截，次日自动解除；
    未出现任何 margin-cap 类拦截（与 A84 实测峰值利用率仅 ~6.5% 一致，上限从未接近）。
  - 与 A83/A84 独立聚合台账比对：4 个品种（AP888/RB888/SC888/A888）交易时序完全一致（部分
    交易手数因联合回放按共享权益做 risk sizing 而不同，属设计内行为）；ZN888 如设计预期自
    首个被拦截开仓处发散（独立运行 2022-03-30 22:59 的开仓被日亏限制拦截，联合回放于次日
    2022-03-31 00:29 按后续信号重新入场）。联合总已实现 PnL -57,473.59 对比独立汇总
    -65,463.57（相对差 12.2%，在验收容差内），差异来源已在验收文档中逐条解释。
  - 验收报告 `diagnostics/joint_replay_acceptance_2026-07-17.md` 与结果 JSON 已按惯例
    `git add -f` 纳入版本控制。明确范围边界：仅拦截新开仓、无强平（A89 未建）、
    不构成交易建议，不宣称生产就绪。

## 0.2.23（2026-07-17）

- A87 联合时钟组合回放 + `PortfolioLedger` + 开仓 gating（范围：仅拦截新开仓，不强平）：
  - 新增 `chan_strategy/portfolio_ledger.py`：`PortfolioLedger` 在联合回放循环内维护共享的
    货币量纲组合状态——`equity = initial_capital + Σ各品种PnL贡献`（本金只计一次，各品种引擎
    与组合共用同一 `initial_capital`，沿用 A83/A84 已验证方法）、`margin_by_symbol`/
    `margin_total`/`margin_by_cluster`（cluster 成员复用 A83 `_symbol_clusters()` 大小写不敏感
    匹配）、`trading_day`/`day_start_equity`/`daily_loss_limit_active` 日切簿记（复用
    `_trading_day()` 与既有 `daily_agg` 配置）。`pre_open_injection_for()` 无违约时返回真实
    共享 `(equity, margin_total)`；触发日亏上限/单品种上限/cluster 上限（按此优先级，首个命中
    为准）时返回饱和保证金 `(equity, equity*max_margin_pct, reason)`，迫使
    `Position._size_open()` 既有公式拒开——gating 完全经由既有 sizing 公式的两个既有输入完成，
    未改 `positions.py`。类文档中显式说明 `max_margin_pct`/`cluster_gross_cap`/
    `daily_loss_limit_pct` 在权重版（`PortfolioCoordinator`）与货币版（本类）两条互斥路径下的
    双重含义。
  - `chan_strategy/portfolio_engine.py`：新增 `_build_joint_report()` 联合时钟驱动——每品种一个
    `BacktestEngine.bar_generator()`（默认 warmup_bars=100，与 `run()` 一致），按时间戳并集推进、
    同 tick 按 `sorted(symbol)` 确定性处理；`pre_open` 注入共享/饱和值，`post_bar` 回写共享
    `(equity, margin_total)` 使各引擎自身记录的权益曲线反映组合视图；品种数据结束后其保证金
    贡献按 A83 语义不再结转（下一 tick 起清零）、PnL 贡献冻结于最后已知值；数据加载失败品种
    记入 `symbol_errors` 并排除出联合循环。抽出 `_make_symbol_engine()` 供 `_run_per_symbol()`
    与联合驱动共用（纯抽取，行为不变）；`run()` 中 `sizing_model="risk" + portfolio_risk="on"`
    的 `NotImplementedError` 分支按设计替换为 `_build_joint_report()`，其余两个分支完全不变。
  - 联合报告字段：`portfolio_risk="on"`/`sizing_model="risk"`/`symbol_reports`/`symbol_errors`/
    联合 `equity_curve`（每唯一 tick 一条）/`pairs`/`blocked_opens`/`loss_limit_triggers`；
    不含 `flat_events`，以 `flatten_on_breach="not_implemented_see_A89"` 显式标注本任务不强平
    （2026-07-17 用户决策：A87 仅拦截新开仓，强平留待后续任务，暂定 A89）。
  - `chan_strategy/config.py`：`STRATEGY_CONFIG` 新增 `max_symbol_margin_pct`（默认 1.0，即
    不严于单品种既有行为，遵循新约束默认最宽松纪律）。
  - 新增 `tests/unit/test_a87_joint_replay.py` 16 项：账本聚合/日切重置/触发记录/注入优先级；
    真实 `bar_generator()` 驱动下——总保证金上限使第二品种开仓被既有公式缩减（250→150 手）、
    单品种上限在总保证金有余量时拦截其新开仓、cluster 上限大小写不敏感拦截同 cluster 品种、
    日亏限制当日对全部品种拦截新开仓且次日解除（触发的唯一平仓来自策略自身止损）、触发时
    不强平任何持仓、品种结束保证金不越界（A83 语义在联合驱动上的复验）、数据错误品种排除、
    无信号冒烟、`run()` 四种配置组合路由。
  - 更新 `tests/unit/test_portfolio_risk.py`：原 `test_run_rejects_risk_sizing_with_portfolio_risk_on`
    断言的 `NotImplementedError` 被本任务按设计移除，该测试改为
    `test_run_routes_risk_sizing_with_portfolio_risk_on_to_joint_replay`（断言新路由）；这是本任务
    唯一改动的既有测试断言，已在 HANDOFF 决策记录中说明理由。
  - 未改动 `positions.py`、`backtest_engine.py`；`sizing_model="risk"+portfolio_risk="off"` 与
    `sizing_model!="risk"+portfolio_risk="on"` 两条既有路径行为不变（既有快照/回归测试通过）。
    单测总数 735 → 751。

## 0.2.22（2026-07-17）

- A86 `BacktestEngine` 逐 bar 生成器抽取（外部权益/保证金注入点，A87 联合时钟前置，按
  `docs/design/a85-joint-replay-design.md` 的 A86 范围执行）：
  - `chan_strategy/backtest_engine.py`：原 `run()` 主循环改为嵌套在新方法
    `bar_generator()` 内的 `_bar_loop()` 生成器，通过闭包捕获原有全部局部变量
    （`nonlocal pending_signals, daily_bar_idx, h4_bar_idx, excluded_dates`），不新增方法参数、
    不改动任何局部变量名与既有分支；在两个既有 `_compute_equity_and_margin()` 调用点
    （`if risk_mode:` 内的 bar.open 开盘前 / bar.close 信号后）各插入一个 yield
    （`"pre_open"` / `"post_bar"`，载荷 `(kind, dt, price, computed_equity, computed_margin)`），
    外部驱动可 `.send((equity, total_open_margin))` 注入覆盖值，`.send(None)` 表示不覆盖、
    沿用引擎自身计算值。生成器耗尽时经 `StopIteration.value` 返回回测报告。
  - `run()` 变为 `bar_generator()` 的默认耗尽包装（全程 `send(None)`）；数据加载失败/
    数据不足等早退路径仍返回同样的错误字典。真实数据（AP888，2024-01-01~2024-06-30，
    `ap888_1M_raw`，783 根交易 bar、9 笔交易）在 research 与 risk 两种模式下
    `equity_curve`/`signal_history`/report 重构前后逐字节一致（json 全精度浮点比较）。
  - 新增 `tests/unit/test_a86_bar_generator.py` 5 项：research/risk 默认耗尽结果与
    `run()` 完全一致、两个 yield 点严格交替且载荷形状固定、pre_open 注入 4x equity 精确改变
    `Position._size_open()` 手数（按 sizing 公式断言，证明注入点真正到达开仓 sizing）、
    错误字典早退路径与 `run()` 一致。单测总数 730 → 735，无既有测试结果改变。
  - 未改动 `positions.py`、`portfolio_engine.py` 或任何既有测试断言；未触碰
    `sizing_model="risk" + portfolio_risk="on"` 互斥 `NotImplementedError` 门控；未实现
    A87 联合时钟驱动与 `PortfolioLedger`。

## 0.2.21 — 2026-07-16

- A85 联合回放 + 共享 PortfolioLedger 算法边界设计文档定稿（设计-only，无生产代码）。
  - 在 `docs/design/a85-joint-replay-design.md` 中明确回答用户指定的 5 个设计问题：
    联合时钟模型（自然分钟 outer-join，逐 bar 前向填充估值、不前向填充信号）、
    共享账本状态（`PortfolioLedger` 字段与每个 tick 的 6 步更新顺序）、
    开仓 gating 语义（总保证金/单品种/cluster cap 硬性拒绝 + daily loss limit 强平）、
    信号执行顺序（`(symbol, strategy)` 字典序确定性强排）、
    测试矩阵（10 项覆盖用户列出的 7 类场景）。
  - 所有决策均追溯到现有代码（`PortfolioEngine._run_per_symbol()`、`_build_on_report()`、
    `PortfolioCoordinator.allow_open()`/`on_bar()`/`_flatten_all()`、`_trading_day()`、
    `Position._size_open()`）或现有测试行为，不臆造未经验证的新机制。
  - 明确排除阶段三熔断动作决策与外部数据依赖问题；保留 `PortfolioEngine.run()` 的
    `sizing_model="risk" + portfolio_risk="on"` 互斥 `NotImplementedError` 门控不变。
  - 未改动 `chan_strategy/`、`diagnostics/` 任何生产代码，未改动任何既有测试断言。

## 0.2.20 — 2026-07-16

- A84 组合账本真实数据验收 / sanity-check。
  - 修复 `diagnostics/portfolio_ledger_report.py` 在多表数据库（同时存在 `*_1M_raw` 与
    `*_5M_raw`）下因 `_find_table()` 精确匹配歧义而失败的问题：新增 `_infer_table_names()`
    根据运行频率 `freq` 自动选择 `{symbol}_1m_raw` / `{symbol}_5m_raw`，并允许用户通过
    `table_names` 显式覆盖；保持默认参数不变。
  - 对 `AP888`/`RB888`/`SC888`/`A888`/`ZN888`、窗口 `2022-01-01~2026-04-24`、
    `sizing_model="risk"` 真实历史 SQLite 数据库完成 ledger 运行。
  - 独立复算脚本 `diagnostics/portfolio_ledger_acceptance_check.py` 验证：组合总保证金与
    单品种按时间戳对齐求和一致（行级最大差异 < 1e-6）；组合已实现货币 PnL 等于各品种 PnL
    之和；最大保证金使用率时刻可追溯至具体品种；品种数据范围外保证金贡献为 0；cluster 成员
    大小写不敏感；单品种关键指标（PnL / 最大保证金 / 最终保证金 / 交易次数）与 ledger 内部
    复算一致。
  - 将验收报告 `portfolio_ledger_report_20260716_094919.{json,md}` 与
    `portfolio_ledger_acceptance_2026-07-16.md` 作为诊断证据 `git add -f` 跟踪。
  - 未改动 `PortfolioCoordinator.run()` 的 `NotImplementedError` 门控、`_run_per_symbol()`、
    `_build_on_report()`、`_build_off_report()` 或任何既有测试断言；未触碰 SimNow
    下单/撤单路径；未新增任何 gating/threshold 逻辑。

## 0.2.19 — 2026-07-16

- A83 修复组合账本聚合两处正确性问题（codex review 打回项）。
  - `diagnostics/portfolio_ledger_report.py` 的 `_build_ledger()` 在按时间戳对齐各品种保证金序列后，
    先对每根 bar 前向填充（ffill），再用每品种自身 `[first_dt, last_dt]` 的布尔掩码把范围外
    的值置为 `0.0`，避免某一品种最后一根 bar 的保证金被延续到后续品种仍有数据的时间段，
    导致组合总保证金、最大保证金使用率及 cluster 保证金被高估。
  - cluster 分组时复用 `_symbol_clusters()` 建立的 case-insensitive 映射，确保请求符号大小写
    与 `STRATEGY_CONFIG["corr_clusters"]` 配置不一致（如 `rb888` 对应配置中的 `RB888`）时仍能被
    正确归入对应 cluster，而不是被错误排除或划入 `_uncategorized`。
  - 新增单测覆盖：品种提前结束后不再继续贡献保证金、`_build_ledger()` 内部 cluster 成员判断
    大小写不敏感。
  - 未改动 `PortfolioCoordinator.run()` 的 `NotImplementedError` 门控、`_run_per_symbol()`、
    `_build_on_report()`、`_build_off_report()` 或任何既有测试断言；未触碰 SimNow 下单/撤单路径。

## 0.2.18 — 2026-07-16

- A83 新增组合级真实保证金/PnL 只读账本报告（Phase 1）。
  - 新增 `diagnostics/portfolio_ledger_report.py`：对给定品种列表与日期范围，以
    `sizing_model="risk"` 独立运行每个品种自己的 `BacktestEngine`（复用
    `PortfolioEngine._run_per_symbol`），然后按时间戳聚合各品种 `equity_curve` 中的
    `total_open_margin` 与各品种已平仓 `pnl_currency`，产出组合级：总保证金占用序列、
    已实现货币 PnL、最大保证金使用率、单品种占用/PnL 明细、按 `STRATEGY_CONFIG["corr_clusters"]`
    分组的 cluster 占用明细。
  - 报告为纯测量型输出，明确声明自己是“独立单品种回测的聚合”，不是真正的联合/协调组合
    回放（Phase 2 工作）。不设置任何 pass/fail 阈值，不参与开仓拦截。
  - 未改动 `PortfolioCoordinator.run()` 现有的 `sizing_model="risk"` +
    `portfolio_risk="on"` 互斥 `NotImplementedError` 门控；未改动 `_run_per_symbol()`、
    `_build_on_report()`、`_build_off_report()` 或任何既有测试断言；未触碰任何 SimNow
    下单/撤单/发送路径。
  - 新增单测 `tests/unit/test_portfolio_ledger_report.py`：使用构造 fixture 验证保证金求和、
    PnL 求和、cluster 分组、错误品种处理、配置覆盖与恢复等逻辑；不依赖真实历史数据库。
  - 报告顶部包含 RESEARCH-ONLY / NOT PROMOTION EVIDENCE 横幅，并在 Markdown 输出中包含
    `## Manual Verification` 章节。

## 0.2.17 — 2026-07-16

- A82 将 `assert_not_research_baseline()` 从 blocklist 改为 fail-closed allow-list（第六轮审核致命项修复）。
  - `chan_strategy/backtest_engine.py` 的 `assert_not_research_baseline()` 改为：仅当
    `report["mode_label"]` 为字符串且以 `"PARTIAL_PRODUCTION_FEATURES("` 开头（即 `_compute_mode_label()`
    实际产生的非研究基线格式）时放行；缺失键、`None`、空字符串、`"RESEARCH_BASELINE"`、
    任何未被识别的字符串一律抛出 `ValueError`。错误信息包含实际 `mode_label` 值以便审计追溯。
  - `unified_acceptance_gate()` 继续复用 `assert_not_research_baseline()`，因此对上述所有不确定/未知
    输入返回顶层 `"fail"`；函数注释同步更新为 allow-list 语义。
  - 修正 `tests/unit/test_formal_evaluation.py`：将原先断言 `{}`/`{"mode_label": ""}`/`FORMAL_EVALUATION`
    通过的测试改为断言它们现在被拒绝；保留并扩展对 `"PARTIAL_PRODUCTION_FEATURES(...)"` 的放行断言。
  - 修正 `tests/unit/test_a81_acceptance_gate.py`：将 `test_empty_mode_label_does_not_fail` 改为
    `test_empty_mode_label_fails`，并新增 `test_missing_mode_label_fails`、`test_none_mode_label_fails`；
    修正 `test_warn_propagates_when_no_fail` 中使用的非安全标签，避免与 allow-list 冲突。
  - 未改动 `_compute_mode_label()` 本身的计算逻辑或格式，未改动任何回测数值输出、SimNow 下单/撤单路径、
    或诊断脚本。

## 0.2.16 — 2026-07-16

- A81 新增统一晋级门禁函数与研究基线入口警告。
  - `chan_strategy/backtest_engine.py` 新增 `unified_acceptance_gate()`：组合 A71 三项 verdict
    函数的 `overall_status`（OOS、参数扰动、成本敏感）与报告 `mode_label`，返回单一顶层
    `"pass"|"warn"|"fail"` 判据：任一输入 `"fail"` → `"fail"`；`mode_label == "RESEARCH_BASELINE"` →
    `"fail"`；无 `"fail"` 但任一 `"warn"` → `"warn"`；否则 `"pass"`。RESEARCH_BASELINE 检查复用
    `assert_not_research_baseline()`，不重复字符串比较；不修改任何 verdict 阈值。
  - `run_chan_backtest.py` 的 `main()` 在首次执行前打印醒目警告：说明本入口为研究基线入口，
    不构成生产/可交易证据，并指向 `run_formal_evaluation.py`。
  - 新增单测 `tests/unit/test_a81_acceptance_gate.py`：覆盖全 `"pass"` + 非基线 → `"pass"`、
    任一 verdict `"fail"` → `"fail"`、RESEARCH_BASELINE → `"fail"`、warn 传播、fail 覆盖 warn、
    缺失 `overall_status` 默认按 `"pass"` 处理；不依赖真实历史数据库。
  - 未改动任何既有回测数值输出、SimNow 下单/撤单路径、或现有测试断言；未将新函数接入任何
    SimNow 晋级判定脚本。

## 0.2.15 — 2026-07-16

- A80 数据适配器无法解析行计数与上报。
  - `chan_strategy/data_adapter.py` 的 `SqliteDataAdapter.load_raw_bars()` 新增可选参数
    `unparseable_count`，对因 `datetime` 无法解析而被跳过的行进行计数；跳过行为本身不变，
    仅增加计数。
  - `chan_strategy/backtest_engine.py` 的 `load_data()` 在加载数据时收集该计数并保存为
    `self.unparseable_rows_skipped`；`generate_report()` 始终将其加入输出字典
    (`unparseable_rows_skipped`)，包括默认研究路径与正式评估路径；`print_report()` 同步打印。
  - 新增单测 `tests/unit/test_a80_unparseable_rows.py`：验证可解析数据集计数为 0、含无法解析
    时间戳的数据集计数准确、以及默认路径和正式评估路径的报告字段均正确；不依赖真实历史数据库。
  - 未引入基于跳过行数的任何失败/阻塞/阈值逻辑，未改动信号计算、SimNow 下单/撤单路径或既有
    数值断言。

## 0.2.14 — 2026-07-16

- A79 正式评估默认改为 trading_calendar 日线聚合。
  - `chan_strategy/backtest_engine.py` 的 `formal_evaluation_config()` 在正式评估期间额外临时覆盖
    `STRATEGY_CONFIG["daily_agg"] = "trading_calendar"`，运行结束后（含异常路径）无条件恢复原始值；
    与已有的 `sizing_model="risk"`、`limit_halt_model="enforce"`、
    `rollover_open_gating="on"`、`stop_execution_model="intrabar"` 共同构成正式评估五覆盖。
  - 未修改 `chan_strategy/config.py` 默认字典（`daily_agg="natural"` 保持默认路径字节级不变），
    未改动 `_resample_daily_trading_calendar()` 本身或任何信号计算逻辑。
  - 新增/扩展单测 `tests/unit/test_formal_evaluation.py`：验证 `daily_agg` 覆盖生效、成功/异常后恢复、
    非默认原始值保留、入口函数 `run_formal_evaluation()` 内 `daily_agg` 实际取值为 `"trading_calendar"`；
    不依赖真实历史数据库。

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
