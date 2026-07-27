<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

# 审核报告：缠论期货 CTA 策略（czsc_strategy）—— 0.2.44 复审

**审核对象**：D:\repo\vnpy\examples\czsc_strategy
**审核人**：AI股交易专家审核 Agent（ai-stock-trading-reviewer）
**审核标准版本**：2.4.0
**审核日期**：2026-07-26
**版本/快照**：VERSION 0.2.44（信号版本 V260615；HEAD=b7589b66f"fix all 14 medium findings from AI_REVIEW_REPORT_2026-07-26"；审核时工作区有 36 个未提交 simnow 相关在途改动）
**证据定位规则**：定位使用 `D:\repo\vnpy\examples\czsc_strategy\<相对路径>:<行号>`；全库检索证据已在对应条目记录搜索根与结果。
**材料索取记录**：状态：不适用；说明：被审对象全部材料明文可读；SQLite 实库在本机可用并已直接抽查（见 D5）。
**与前次审核的关系**：本报告是对同日 `AI_REVIEW_REPORT_2026-07-26.md`（0.2.42 基线，68/100）之后修复轮（0.2.43/0.2.44）的**独立复审**：全部维度重新取证，前次 14 条 🟠 逐条复核修复真实性，不以前次报告或 `diagnostics/codex_review_2026-07-26.md` 的结论为证据（codex 报告仅作背景）。

---

## 一、总体结论

- 综合评分：**82/100（B 良好）**（可评维度 10/10；结构性 N/A：无；证据不足/未验证：见"二、审核范围与局限"）
- 一句话结论：**前次审核的 14 条中危问题修复经逐条独立复核基本真实（仅少量降级为残留 🟢），工程质量在同类研究代码中保持上乘；唯一结构性短板不变——所有历史"样本外"窗口均被反复用于参数选择，当前不存在任何干净的样本外有效性通过证据，晋级完全依赖尚未完成的 SimNow 前瞻观察（0/20 有效日）。作为研究工程良好，作为策略有效性证据仍不成立。**
- 高危项/实盘前置警示：**无 🔴 项**。
- 致命项：**无**（无维度 ≤2 分，🔴 0 条）。
- 一致性提示：本复审总分（82）与 codex 复核报告（82）独立收敛；两者证据路径不同（本复审实跑了测试套件、realdb 门禁并直接抽查了 SQLite 实库），收敛增强可信度但不构成相互证明。

---

## 二、审核范围与局限

- **审核方式**：静态审阅（chan_strategy 全部 12 个模块逐行通读，约 8100 行）+ 运行验证。运行验证明细：
  1. `pytest tests/unit -q -m "not realdb"`（解释器 C:\Python314\python.exe，项目实际开发环境）：**852 passed, 21 failed, 4 deselected, 4 xfailed**。21 个失败全部定位于审核环境限制而非代码回归——20 个在 `tests/unit/test_run_next_work_wrapper.py`，需要将 PowerShell 函数注入 `pwsh` 子进程执行，而本机无 pwsh；1 个在 `tests/unit/test_handoff_tool.py::test_handoff_status_uses_authoritative_sync_check_engine`，为子进程输出的 GBK 解码失败（本机中文 Windows 默认编码）。开发方在 0.2.44 提交信息中声明其环境 873 passed。**未验证：这 21 条在开发环境下的通过状态。**
  2. `pytest tests/unit -m realdb -q`（AGENTS.md 要求的实库门禁）：**4 passed**（108.98s）。
  3. `python tools/sync_check.py`：**PASS**（版本单一真相 0.2.44）。
  4. SQLite 实库直接抽查（`D:\BaiduNetdiskDownload\...\kline_data.db`）：144 张表（888/777 各一），`ap888_1M_raw` 244,481 行，NULL 价格 0 行、非正/倒置价格 0 行、范围 2022-01-04~2026-07-21、`real_symbol` 分段 14 段（AP205→AP610），换月检测数据基础属实。
  5. 阈值对账：`python -c` 直读 `STRATEGY_CONFIG`/`BACKTEST_CONFIG` 生效值与 README 表逐项比对，全部一致。
  6. 凭据复查：`diagnostics/simnow_connection_config.example.json` 已改占位符；`skill_build/llm_eval_config.json` 的 api_key 已清空。
- **材料范围**：chan_strategy/ 全部源码、入口脚本、README/README.legacy/AGENTS/HANDOFF/CHANGELOG/VERSION/.synccheck.yml、tools/、tests/（存在性核查+实跑）、diagnostics/ 关键报告、docs/design/、根目录残留脚本、skill_build/ 参考文档。
- **方法论材料缺失**：无。
- **未验证项**（逐条）：
  1. 21 个环境耦合测试在开发环境的通过状态（见上）。
  2. czsc 第三方库内部是否存在后视修正：依赖项目自建 `validate_no_repaint` 间接背书，未独立复现；该检查自身声明不能证明底层库无修正（`chan_strategy/validation.py` validate_no_repaint docstring）。
  3. 实库抽查仅覆盖 ap888 一表；其余 143 表的 NULL/异常价格未逐表检查（有 contract_adjustment_verification 事证支撑换月拼接结论）。
  4. 涨跌停幅度与临时扩板窗口按其引用的交易所规则文本采信，未联网复核（两处扩板窗口配置自带"未经独立核实，待人工确认"标注，`chan_strategy/limit_config.py:32-36,51-55`）。
- **市场语境适配**：被审对象为**商品期货 CTA**，按适配矩阵执行：剔除 A 股 T+1、印花税、复权、退市项；替换/强化为合约连续化与换月、合约乘数与保证金、夜盘归属、涨跌停板建模、滑点。D4 基本面 point-in-time 子项结构性剔除（纯价格型策略）；D4 容量子项剔除（5 个主力连续合约、低换手、流动性好）。

---

## 三、各维度评分表

| 维度 | 得分 | 评级 | 一句话依据（含"未验证"标注） |
|------|------|------|-----------|
| D1 信号构建与择时逻辑自洽性 | 8/10 | 良好 | 生产信号路径统一（sell_signals.get_all_signals）；"次级别确认"死语义已删除并三义澄清；多空信号互斥天然成立；残留：无预期换手/稳定性设计假设说明（🟢） |
| D2 组合构建、风险预算与风控一致性 | 8/10 | 良好 | 单笔层（止损/超时/移动止损/结构失效）+组合层（保证金/品种/簇/日亏/持久回撤熔断）+极端行情 toolkit 齐全且可复算；缺换手/再平衡约束（🟢），回撤熔断默认禁用且未接入权重口径路径（🟢） |
| D3 参数/阈值跨载体一致性 | 8/10 | 良好 | 关键阈值全链对账零不符（本次实跑直读验证）；核心风控键已有 AST 防漂移守卫；残留：backtest_engine pos 权重 6 处 + portfolio_engine 1 处字面量 fallback 未入守卫（🟢） |
| D4 回测/评估严谨性 | 7/10 | 良好 | 无前视设计（信号 T→成交 T+1 开盘、高周期时间戳因果）有测试锁定；成本模型+敏感性门禁+walk-forward 齐全；🟠 无干净 OOS 通过证据封顶 7 |
| D5 数据假设处理 | 9/10 | 优秀 | splice/换月/涨跌停/夜盘"声明→代码→测试→报告"证据链完整；本次直接抽查实库（0 异常价格行）+ realdb 门禁 4/4 通过；残留：涨跌停基准用前收盘价而非前结算价（🟢）、bar 空洞无缺失率 fail-closed（🟢） |
| D6 指标定义与术语统一 | 8/10 | 良好 | "确认"三义已在 README+docstring 显式区分；zhongshu 补教科书级偏离声明；score 声明为装饰性；残留：缠论核心术语无唯一定义出处（🟢）、结构状态"未确认"分支不可达（🟢） |
| D7 市场环境适配与声明 | 8/10 | 良好 | README 新增"适用前提与失效环境"节；regime router/ATR chop 有量化判据（ATR 分位数地板）并补入开关清单；两者默认关闭的原因已声明 |
| D8 可追溯性与单一真值源 | 8/10 | 良好 | 参数沿革已补；VERSION+CHANGELOG+sync_check 门禁实跑通过；残留脚本大多补横幅；残留：_patch_backtest1-4 无横幅、test_backtest_idempotent.py 在 tests 门外、data_cache 9 个废止 CSV 仍被 git 跟踪（🟢） |
| D9 透明度与可审计性 | 9/10 | 优秀 | 全明文无黑盒；凭据卫生缺口已消除（example 占位符、LLM key 清空）；本次独立复算可行且已实跑验证；残留：20+1 个测试存在环境耦合（pwsh/GBK）（🟢） |
| D10 合规与风险提示充分性 | 9/10 | 优秀 | RESEARCH-ONLY 横幅门禁强制；无任何下单路径（回测-only）；零收益承诺措辞；mode_label+fail-closed 守卫防止研究基线被当作生产证据 |
| **合计（归一化）** | **82/100** | **B** | Σ=82，可评 10 维，等权归一 |

> 复核自检记录：① 唯一 🟠（D4 无干净 OOS）按强制映射封顶 D4=7，已核对其余维度无 🟠 归属、得分 ≥8 不与映射冲突；② 无 🔴 项，反驳测试不适用（无高危结论需防守）；③ 报告中全部数值（852/21/4、4 passed、0.0001/0.0005、200/300/350BP、600/1000/1500、0.10/0.20/0.30、0.05、0/20、244,481 行、14 段 real_symbol）已与原文/实跑输出逐一核对。

---

## 四、问题清单（按严重程度排序）

### 🔴 高

无。

### 🟠 中（1 条）

**1.【D4】最终候选无真正未触碰的样本外通过证据；全部历史 OOS 窗口被反复用于参数选择（结构性，诚实披露但问题本体仍在）**
- 定位：`diagnostics\backtest_matrix_20220101_20260424.md:7`（自述窗口"repeatedly used for parameter selection…retained as negative / contaminated evidence only"）；`diagnostics\simnow_20d_promotion_decision.md`（本次复审时工作区最新值：`observed_days: 8/20`、`valid_observation_days: 0/20`、`ready_to_expand: False`，blockers 含 `need_20_more_valid_observation_days, consistency_not_fully_matched, halt_threshold_breached`）
- 影响：九轮同窗口迭代优化（platform_optimization_round1~9）+ 大量候选扫描使全部历史"样本外"实为受污染证据；当前不存在任何干净 OOS 通过记录；策略有效性既未被证明也未被证伪。
- 说明：此条与前次审核 🟠5 为同一条。修复轮的处理方式是"诚实披露+门禁不放松"（README:185-187 明确标注受污染；SimNow 晋级门禁未放行）——这是该问题唯一正确的工程应对，但按评分锚点"验证样本与训练/筛选样本混用"的封顶判据，D4 仍不得高于 7，直到前瞻观察产生首个干净通过记录。
- 建议：维持现有"污染证据自我降级+前瞻窗口门禁"治理；SimNow 20 有效日完成前，任何文档不得把历史窗口数字表述为有效性证据（目前执行良好）。

### 🟢 低（按维度归组，均已定位取证）

**信号与术语（D1/D6）**

2. 【D1】信号层无预期换手与稳定性设计假设说明——全库检索（根 `D:\repo\vnpy\examples\czsc_strategy`，Grep `预期换手|稳定性假设`）仅命中遗留 A 股脚本。
3. 【D1】`signals.py` 与 `sell_signals.py` 双 `get_all_signals` 并存：治理充分（DeprecationWarning + AST 门禁 + README 双处声明 + 模块 docstring 明确两套系统独立维护且结果不保证一致，`signals.py:920-973`），属受控的活歧义，记录项。
4. 【D6】缠论核心术语（笔/中枢/背驰/一买二买三买）无唯一定义出处；`skill_build\reference\缠论术语表.md` 是话术映射文档且 chan_strategy/ 无任何引用。
5. 【D6】`signal_zs_confirmation` 的"未确认"（score=40）分支不可达：`signals.py:406-411`，`_make_zhongshu` 要求首 3 笔重叠才返回中枢，故存在中枢时 n_bis 恒 ≥3。
6. 【D1】`enable_short=True` 且 `regime_model="independent"` 时，同一标的多头子策略与空头子策略可同时持仓（研究与风险口径均允许）；回测报告有 `both_long_short_bars` 指标如实披露（`backtest_engine.py:714,943`），属已声明的建模简化，非隐藏缺陷。

**组合与风控（D2）**

7. 【D2】`max_drawdown_breaker_pct` 默认 None（禁用），且仅接入 `sizing_model="risk"`+`portfolio_risk="on"` 的 PortfolioLedger 联合回放路径；权重口径 PortfolioCoordinator 路径无回撤熔断（`portfolio_ledger.py:85-92` 注释已声明范围）。
8. 【D2】risk_parity 权重每 bar 重算，无换手/再平衡约束；标的掉线时等权归一化可推高集中度（前次审核实例：AP888 权重 87.93%）。
9. 【D2】期货强平/维持保证金未建模，保证金率取交易所最低值（`config.py:174-186` 已声明 research-only 并附交易所出处）。

**回测（D4）**

10. 【D4】滑点只按单边计入：往返成本 = 2×佣金 + 1×滑点（`positions.py:1073,1143,952`），每往返少计约 5bp；x2 成本敏感性门禁（`diagnostics/cost_sensitivity_report.py`）已包络该口径，影响温和。
11. 【D4】换月开仓门控使用全窗口事后检测的换月日期（`backtest_engine.py:528-554` 在回测开始前对 `[start_date, end_date]` 全窗口运行 `_detect_transitions`）；换月日现实中可提前感知，偏差方向为保护性，但 formal 结果仍轻微偏乐观，报告未显式声明其事后性质。
12. 【D4】"信号 T→成交 T+1 开盘"协议无命名直接的回归测试（`test_execution_timing.py` 仅含幂等性与数据不足两条）；存在间接覆盖（`test_limit_halt_enforce.py:144` 拒单后下一 bar 成交、`test_resonance_filter_off_equivalence.py:39` 注明下一 bar 执行）。

**数据（D5，期货适配后）**

13. 【D5】涨跌停带宽基准价用"前一交易日收盘价"（`limit_config.py:106-138`），而其引用的交易所规则文本均为"前一交易日结算价"；formal 窗口实测 0 笔拒单，当前无实证影响。
14. 【D5】enforce 触发为 bar 区间"触板即拒"（`limit_config.py:180-181`，high≥上限 或 low≤下限），方向保守；与报告 methodology 措辞存在口径差。
15. 【D5】时间序列 bar 空洞无缺失率阈值 fail-closed；不可解析行只跳过计数（`data_adapter.py:411-412`），由诊断层监控兜底。
16. 【D5】`contract_specs` 的 `tick` 字段生产代码零引用（全库 Grep 仅 config 定义处与注释），成交价未按最小变动价位取整。
17. 【D5】换月拼接边界处涨跌停带宽失去意义（splice 跳空可能远超带宽），持仓跨换月日平仓可能被误拒顺延一根 bar。

**参数/治理/透明度（D3/D8/D9）**

18. 【D3】残留未入 AST 守卫的字面量 fallback：`backtest_engine.py:722-727`（pos_1buy~pos_3sell 六处，字面量 0.10/0.20/0.30 与 config 当前一致）、`portfolio_engine.py:78`（`.get(config_key, 0.10)`）；AST 守卫（`tests/unit/test_a53_config_signal_cleanup.py:44-80`）仅覆盖 3 个文件 11 个核心风控键。当前数值全一致，纯漂移风险。
19. 【D3】大量开关型键仍以字符串字面量 fallback 分散读取（如 `STRATEGY_CONFIG.get("exit_model", "legacy")`、`get("resonance_filter", "off")`、`get("regime_model", "independent")` 等，遍布 positions.py/backtest_engine.py），默认字符串在 ≥2 处重复定义。
20. 【D8】`_patch_backtest.py`~`_patch_backtest4.py` 四个一次性补丁脚本仍无 ONE-SHOT/LEGACY 横幅（同目录 `_debug_zs.py`/`test_czsc_api.py`/`inspect_db.py` 等已补）；`test_backtest_idempotent.py` 是真实回归测试但仍在仓库根、tests/unit 门禁之外且被 git 跟踪。
21. 【D8】`data_cache/` 9 个已废止 A 股 CSV 仍在 git 跟踪中（`git ls-files` 实证）。
22. 【D9】测试环境耦合：20 条 `test_run_next_work_wrapper.py` 依赖本机 pwsh，1 条 `test_handoff_tool.py` 依赖控制台编码——在本次审核环境失败（详见"二、审核范围与局限"）；对"测试套件可独立复核"构成轻微折扣。
23. 【D8】工作区长期存在 36 个未提交 simnow 在途改动（与前次审核时数量相同）；VERSION/CHANGELOG 门禁只覆盖已提交内容，在途改动的治理状态依赖人工纪律。

---

## 五、亮点（值得保留的好设计）

1. **防未来函数的信号输入纪律严格且成文**：`_get_confirmed_bi_list`（`signals.py:37-61`）在 finished_bis 之上做 last_bi_extend 防御性剔除，明确"绝对不允许回退到 c.bi_list"。
2. **无前视的聚合时间戳设计**：合成 bar 时间戳=最后一根构成 bar（`data_adapter.py:190`），日线/4H 仅当 `dt <= 当前 bar` 才注入（`backtest_engine.py:635,641`），有 test_daily_no_lookahead / test_4h_no_lookahead 锁定。
3. **成交时点模型真实做到信号 T、成交 T+1 开盘**：pending_signals 机制 + execution_price=bar.open 全链路（`backtest_engine.py:602-628`），走读未发现前视路径。
4. **模式标签 + fail-closed 守卫**：`_compute_mode_label`/`assert_not_research_baseline`/`unified_acceptance_gate`（`backtest_engine.py:120-241`）从制度上阻止 RESEARCH_BASELINE 被当作生产证据；research 模式报告强制 sizing_caveat 与 circuit_breaker_caveat。
5. **污染证据自我降级标注体系**：受污染产物统一 RESEARCH-ONLY 横幅 + `is_promotion_evidence: False`；README 主动声明哪些窗口是"负面/受污染证据"。
6. **新增持久回撤熔断的工程质量**：`PortfolioLedger.check_drawdown_breaker`（`portfolio_ledger.py:184-210`）跨交易日不重置、与 A90 强平同链路接线、联合回放驱动有不变量断言（`portfolio_engine.py:784,812`），并有单测覆盖默认禁用/触发/持久化/优先级。
7. **组合强平无前视处理严谨**：lagging symbol 用自有 tick 的 bar.close 强平（`portfolio_engine.py:788-799`），注释明确避免 lookahead。
8. **极端行情 toolkit 完整且溯源**：涨跌停三档 + 逐品种交易所规则出处；换月检测失败 fail-closed raise（`backtest_engine.py:536-549`）；临时扩板窗口自带"未经独立核实"标注。
9. **多空隔离与信号互斥天然成立**：enable_short=False 时空头 Position 不创建；一买/一卖确认对末笔方向要求互斥，同刻不可能双向确认。
10. **门禁文化真实运转且本次复审实证**：sync_check PASS、realdb 等价性门禁 4/4、852 条非实库单测通过、AST 级防漂移/防下单守卫多份。
11. **修复轮本身的诚实性**：前次 14 条 🟠 的修复逐条复核未发现"假修复"（表面上改、实际未生效）案例；xfail 的 4 条失败均以 reason 显式登记而非隐藏。

---

## 六、修复优先级建议（Top 5）

1. **【D4】守住前瞻观察纪律**（不变，仍是第一优先级）：SimNow 20 有效日完成前，任何文档不得把历史窗口数字表述为有效性证据；这是项目唯一通往"干净 OOS"的路径。
2. **【D3】把残留字面量 fallback 纳入守卫**：将 `pos_*` 权重键与 backtest_engine.py 纳入 `test_core_risk_config_keys_do_not_use_literal_get_fallbacks` 的文件/键集合；开关型字符串默认值建议集中为模块级常量。
3. **【D8】残留清理收尾**：`_patch_backtest1-4` 补 ONE-SHOT 横幅或删除；`test_backtest_idempotent.py` 迁入 tests/unit；`data_cache/` 9 个废止 CSV 移出 git 跟踪；36 个在途 simnow 改动尽快提交或 stash 归档。
4. **【D2】回撤熔断补全接入面**：权重口径 PortfolioCoordinator 路径接入 `max_drawdown_breaker_pct`，或在 coordinator 报告中显式声明"本口径无回撤熔断"（目前只在 ledger docstring 声明）。
5. **【D5】涨跌停基准价对齐前结算价**：若数据库有结算价列则切换基准，否则在 `limit_config.py` docstring 显式声明"用前收盘价近似前结算价"的口径偏差及方向。

---

> 免责声明：本报告为策略工程质量审核，非投资建议；不对被审策略的实盘收益做任何承诺。本报告本身亦为研究产物，不构成对该项目盈利能力的证明。
