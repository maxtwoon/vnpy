# 审核报告：czsc_strategy（缠论期货策略）

**审核对象**：`D:\repo\vnpy\examples\czsc_strategy\`
**审核人**：AI股交易专家审核 Agent（ai-stock-trading-reviewer）
**审核日期**：2026-07-12
**版本/快照**：`7f30081159939b700aa0f2ed8b0094d816dd2d6c`（`A48 review accepted after replay fixes`）

---

## 一、总体结论

- 综合评分：**56/100（C，及格但有明显短板）**
- 一句话结论：工程治理与前视偏差纪律做得扎实（无未来函数、fill 延迟正确、SimNow 工具全部只读），但**期货核心风控存在真实的静默失效路径（部分止盈永久 no-op 导致 ATR 移动止损被阻塞）、涨跌停/停牌完全未处理、复权方式未声明**，不建议在修复 D2/D5 高优先级问题前用于实盘或半自动信号推送。
- 致命项：**无**（十个维度均未评到 ≤2 分；但 D5 数据假设处理评分接近临界，属于"重大问题"级别，需要优先修复）。

---

## 二、各维度评分表

| 维度 | 得分 | 评级 | 一句话依据 |
|------|------|------|-----------|
| D1 信号与择时逻辑自洽性 | 6/10 | 及格但有短板 | 中枢取值口径不统一（`zhongshu_list[-1]` vs. 跳过尾部无后续笔的中枢），`signals.py` 中被自己声明为"有缺陷"的买卖点信号仍留在生产可导入路径上 |
| D2 风控完整性与一致性 | 4/10 | 重大问题 | `_scale_out` 在 `sizing_model="risk"` 且缩量后手数为0时静默 no-op、且**永不置位** `_partial_tp_done`，导致 `exit_model="structural_atr"` 下的 ATR 移动止损分支被永久跳过；另有指向不存在配置键的孤儿风控开关 |
| D3 参数/阈值跨载体一致性 | 5/10 | 及格但有短板 | `stop_loss_pct=0.05` 在 4 处函数签名硬编码、不经 `config.py`，与 `config.py` 实际的分买点止损 200-350BP 概念不同却同名易混淆；`enable_1buy_symbols`/`block_1buy_daily_*` 等键在 `config.py` 中根本不存在 |
| D4 回测/评估严谨性 | 6/10 | 及格但有短板 | 核心回测循环无未来函数、成交价延迟到下一根开盘，纪律良好；但默认 `sizing_model="research"` 产出的 Sharpe/PF 并非可交易盈亏且未在多数报告中加注说明；存在 9 轮以上参数搜索与 4 位小数权重（`0.0847`）等过拟合信号，团队已自建检测工具但未做代码级硬阻断 |
| D5 数据假设处理 | 3/10 | 重大问题 | 全链路（`data_adapter.py`/`backtest_engine.py`/`positions.py`）未见任何涨跌停/停牌处理；888连续合约复权方式未声明未校验；换月污染仅在只读诊断脚本中排除，默认回测路径不排除；默认 `daily_agg="natural"` 会把夜盘K线错配到错误交易日 |
| D6 指标定义与术语统一 | 5/10 | 及格但有短板 | `signals.py` 与 `sell_signals.py` 中存在同名信号（二买/三买）两套不同实现，后者显式声称是对前者缺陷的修正，但前者仍存在于 `get_all_signals` 可达路径附近，构成未来误用的隐患 |
| D7 市场环境适配与声明 | 6/10 | 及格但有短板 | 设计文档声明了一买胜率 26-37%、二买 PF 常 <1 等适用性证据并驱动了 P4-P6 各项闸门，具备一定程度的环境适配意识，但策略文档本身未见明确的"何种行情应回避"独立章节 |
| D8 可追溯性与单一真值源 | 6/10 | 及格但有短板 | 任务ID注释与代码分支高度对应、无矛盾；但 `equity_mode` 配置项声明"compound 未实现"却连"fixed"分支本身也从未被读取分支判断，是纯装饰性配置；`VERSION`/`CHANGELOG` 自 A33 起 15 个任务未更新 |
| D9 透明度与可审计性 | 9/10 | 优秀 | 全部为可读 Python 源码，未发现任何加密/编译黑盒；SimNow 相关脚本亦全部只读、无下单 API 调用 |
| D10 合规与风险提示充分性 | 6/10 | 及格但有短板 | 铁律与最新阶段交付报告均正确携带 RESEARCH-ONLY 声明，SimNow 工具无自动下单；但 `diagnostics/` 130 份报告中约 90 份缺少免责声明，尽管项目已自建 `declassify_historical_reports.py` 补丁脚本，未对存量报告完整重跑 |
| **合计** | **56/100** | **C** | |

---

## 三、问题清单（按严重程度排序）

### 🔴 高

1. **ATR 移动止损可被静默永久阻塞（部分止盈 no-op 未复位标志位）**
   - 定位：`chan_strategy/positions.py:832-846`（`_scale_out`）与 `chan_strategy/positions.py:680-688`（`_check_position` 主循环）
   - 证据：
     ```python
     # positions.py:839-845
     scale_volume = self.volume * partial_tp_frac
     if STRATEGY_CONFIG.get("sizing_model", "research") == "risk":
         scale_volume = int(floor(scale_volume))
         if scale_volume < 1:
             return                      # <-- 提前返回，_partial_tp_done 从未置 True
         if scale_volume >= self.volume:
             return
     ```
     ```python
     # positions.py:680-688
     elif not self._partial_tp_done:
         partial_event = self._get_partial_tp_event(signals_dict)
         if partial_event:
             self._scale_out(price, dt, f"部分止盈-{partial_event.name}")
     elif self._check_atr_trailing_stop(price, atr):   # 只要 780 分支被命中就永远走不到这里
         ...
     ```
     `_partial_tp_done` 仅在 `_scale_out` 成功执行时于 `positions.py:878` 被置为 `True`；`positions.py:600` 初始化为 `False`。
   - 影响：`sizing_model="risk"`（真实整数手仓位模型）叠加 `exit_model="structural_atr"`（P8a 引入的结构化 ATR 移动止损，是该模式下唯一的"盈利侧"风控手段）时，只要按 `partial_tp_frac` 缩出的手数不足 1 手（小账户、低乘数标的、或本就只有 1 手仓位的常见情形），`_scale_out` 直接 `return`、**永不**把 `_partial_tp_done` 置 `True`。由于 `elif` 链的短路特性，第 680 行分支会在此后每根 bar 都被命中（即使没有部分止盈事件也仍然进入该 `elif` 分支体，只是内部 `if partial_event` 为假、什么都不做），第 684 行的 ATR 移动止损检查因此**永远不会被求值**。这意味着该持仓在固定止损和超时之外，唯一的"给利润设保护"的机制被静默关闭，且没有任何日志/报告字段能反映这一状态——诊断报告只会看到该笔交易走了固定止损或超时退出，无法区分"ATR移动止损从未触发"与"ATR移动止损从未被允许触发"。
   - 建议：在 `_scale_out` 提前返回前，先判断"该笔仓位本就不足以拆分"的情形（`scale_volume < 1`）应等价于"视为已完成部分止盈"，即在 return 前把 `self._partial_tp_done = True`（同时可记录 `reason="部分止盈-手数不足跳过"`），使后续 ATR 移动止损分支可达；并为该分支补充一条单元测试，覆盖 `sizing_model="risk"` + 单手仓位 + `exit_model="structural_atr"` 的组合。

2. **期货主链路（`data_adapter.py`/`backtest_engine.py`/`positions.py`）完全没有涨跌停/停牌处理**
   - 定位：全仓库 grep `涨停|跌停|limit|halt|停牌` 在 `chan_strategy/data_adapter.py`、`chan_strategy/backtest_engine.py`、`chan_strategy/positions.py` 中零命中
   - 证据：入场按下一根 bar 的开盘价成交（`backtest_engine.py:308-312`，`execution_price=bar.open`），止损按当前 bar 收盘/高低价成交（`positions.py` 的 `_stop_fill`），全程未检查该 bar 是否处于涨跌停封板或停牌状态。
   - 影响：标的池中的 `AP888`（苹果，历史上多次涨跌停）、`RB888`（螺纹钢）均为存在每日涨跌停幅度限制的商品期货品种。回测在涨跌停封板/无成交量的 bar 上照常按开盘价开仓、按收盘价/高低价止损平仓，等同于假设了在涨跌停期间存在实际不存在的流动性，会系统性高估策略的可执行性与收益、低估滑点与尾部风险，直接影响 D4 的回测真实性结论。
   - 建议：在 `data_adapter.py` 加载原始 K 线时增加涨跌停判定字段（结合合约每日涨跌停比例与前收盘价计算），在 `backtest_engine.py`/`positions.py` 的成交环节对触及涨跌停且无法反向成交的 bar 做"不可成交/顺延"处理，并新增一份诊断报告统计现有历史回测中有多少笔交易实际落在涨跌停 bar 上，量化当前结果的乐观偏差。

### 🟠 中

3. **默认 `sizing_model="research"` 产出的绩效指标并非可交易盈亏，但绝大多数诊断报告未加注说明**
   - 定位：`chan_strategy/config.py:76`（`"sizing_model": "research"`，默认值），`chan_strategy/backtest_engine.py:716-722`（仅在控制台 print 中做了提示）
   - 证据：
     ```python
     # backtest_engine.py:721-722
     print("注: 当前为信号研究模式（方向型仓位+事后加权），")
     print("    未建模合约乘数/资金上限/复利，仅评估信号有效性。")
     ```
     该提示只打印到控制台，未写入 `diagnostics/*.md`/`*.json` 报告正文。
   - 影响：`run_batch_backtest`/`run_single_backtest` 及绝大多数 `diagnostics/*.md` 报告默认使用 `research` 模式，其 Sharpe/PF/年化收益是"方向型仓位+固定权重"下的合成指标，不含合约乘数、保证金上限、复利效应，不代表真实可交易盈亏。脱离控制台单独阅读某份报告的读者容易将其误读为实盘可实现的业绩。
   - 建议：把该提示文本作为标准字段写入所有报告 JSON/MD 的 header（而不仅是 print），并在报告模板层面强制要求。

4. **换月污染在默认回测路径中不被排除，仅存在于只读诊断脚本**
   - 定位：`diagnostics/rollover_exclusion_report.py:1-9`（docstring 确认 `real_symbol` 列存在换月事件），`chan_strategy/data_adapter.py`/`chan_strategy/backtest_engine.py` 无任何排除逻辑
   - 证据：`rollover_exclusion_report.py` docstring："Detects 888 continuous-contract rollover dates from the raw table's `real_symbol` column, runs the close-model baseline backtest, and reports the before/after impact of excluding trades whose open or close falls within `transition_date ± 1 trading day`."
   - 影响：说明该项目自己已确认换月会污染回测结果，但排除逻辑只存在于一个独立诊断脚本里，`BacktestEngine`/`PortfolioEngine` 的默认生产路径不做任何换月窗口标记或排除，所有默认跑出来的回测/诊断报告（包括本身用于验收的报告）都可能包含被换月污染的交易而未被剔除。
   - 建议：将换月识别下沉为 `data_adapter.py` 提供的一个可选字段（例如 `is_rollover_window`），供 `backtest_engine.py` 在统计层面标注（不要求默认启用交易屏蔽，但至少让报告能够区分"含换月"与"不含换月"两组指标）。

5. **复权方式未声明未校验（期货连续合约）**
   - 定位：`chan_strategy/config.py:4-8`、`chan_strategy/data_adapter.py` 全文
   - 证据：`config.py` 仅声明数据库路径，`data_adapter.py` 将每行视为原始 OHLCV，无复权元数据消费；对照 `run_baostock_backtest.py:242` 股票脚本显式声明 `adjustflag="2"  # 前复权`。
   - 影响：`AP888/RB888/SC888/A888/ZN888` 是否为前复权/后复权/不复权拼接的连续合约，直接影响止损百分比、ATR、笔/中枢结构识别的历史价格水平是否可信，但代码层面完全未声明或校验这一假设。
   - 建议：在 `data_adapter.py` 或 `config.py` 中显式声明并断言拼接方法（若数据库已固定为某种方式，至少加注释和一次性校验脚本核实）。

6. **`enable_1buy_symbols`/`block_1buy_daily_*` 等风控开关读取不存在的配置键，永久 no-op**
   - 定位：`chan_strategy/positions.py:396,405,407,409`
   - 证据：
     ```python
     # positions.py:396
     enabled = STRATEGY_CONFIG.get("enable_1buy_symbols")
     # positions.py:405,407,409
     if STRATEGY_CONFIG.get("block_1buy_daily_down") and daily_direction.startswith("向下"): ...
     if STRATEGY_CONFIG.get("block_1buy_daily_not_up") and not daily_direction.startswith("向上"): ...
     if STRATEGY_CONFIG.get("block_1buy_daily_below_zs") and daily_position.startswith("中枢下方"): ...
     ```
     `chan_strategy/config.py` 中未见 `enable_1buy_symbols`/`block_1buy_daily_down`/`block_1buy_daily_not_up`/`block_1buy_daily_below_zs` 任一键。
   - 影响：这些是"一买"信号的日线方向/中枢位置过滤闸门，代码逻辑本身是完整的，但由于 `.get()` 永远返回 `None`（falsy），条件永不成立，闸门在任何配置下都不会生效——即使用户在 `config.py` 里手动添加这些键并赋值 `True`，只要键名与代码里读取的不一致（需逐一核实），该风控意图也无法落地。这是一处单一真值源缺口：代码"看起来"支持这些风控开关，但实际上无法通过任何配置路径打开。
   - 建议：要么在 `config.py` 中补齐这些键（默认 `False`/`None` 以保持行为不变），要么删除 `positions.py` 中的死读取代码，避免未来维护者误以为这些风控已经生效。

7. **`stop_loss_pct=0.05` 在 4 处函数签名中硬编码，脱离 `config.py`，且与配置中同名概念（分买点止损）数值不同**
   - 定位：`chan_strategy/signals.py:726,793`，`chan_strategy/sell_signals.py:235,261`；对照 `chan_strategy/config.py:31-36`
   - 证据：`signals.py:726` `def signal_risk_control(c: CZSC, freq: str = "30分钟", stop_loss_pct: float = 0.05) -> dict:`；`sell_signals.py:268` 注释自认 "The 0.05 threshold is copied verbatim."；而 `config.py:31-36` 中 `stop_loss_1buy=200`(2%)、`stop_loss_2buy=300`(3%)、`stop_loss_3buy=350`(3.5%) 才是仓位实际使用的止损阈值。
   - 影响：`signal_risk_control`/`signal_short_risk_control` 系列函数计算的是"结构失效"信号（价格跌破中枢边沿 5% 视为结构失效），与仓位止损（`positions.py` 按买点分层的 2%-3.5% 止损）是两个不同的风控概念，但共用 `stop_loss_pct` 这一参数名且默认值互不相同、互不引用，容易让后续维护者误以为二者是同一个阈值的两处实现，产生"改了一处以为全改了"的隐患；同时 0.05 这个数值在 4 处物理拷贝，属于经典的第二真值源问题。
   - 建议：把结构失效阈值也纳入 `STRATEGY_CONFIG`（例如 `structural_invalidation_pct`），4 处函数默认值改为从配置读取，并在注释中明确其与仓位止损阈值的区别。

8. **同名信号在 `signals.py` 与 `sell_signals.py` 中存在两套不同实现，前者已知有缺陷但仍留在可达路径附近**
   - 定位：`chan_strategy/sell_signals.py`（对 `signal_second_buy`/`signal_third_buy` 的修正版）vs. `chan_strategy/signals.py`（原始版本，仍存在于 `get_all_signals`）
   - 证据：子代理审查确认 `sell_signals.py` 中的实现显式声明是在修补 `signals.py` 原生实现的缺陷，但 `signals.py` 自身的 `get_all_signals` 仍导出旧实现；当前生产管线通过 `sell_signals.py` 导入，因此运行时不受影响，但 `signals.py` 中的旧实现构成一个"看起来能用、实际有缺陷"的陷阱，供未来任何直接从 `signals.py` 导入信号的新代码误用。
   - 建议：在 `signals.py` 对应函数处加注释明确指向 `sell_signals.py` 的修正版本为唯一权威实现，或直接删除/标记 deprecated。

9. **诊断报告免责声明覆盖不完整：约 90/130 份历史报告缺少 RESEARCH-ONLY 声明**
   - 定位：`diagnostics/*.md`（130 份中约 90 份），对照 `diagnostics/declassify_historical_reports.py` docstring
   - 证据：`exit_model_report_2026-07-12.md:3`、`portfolio_heat_report_2026-07-12.md:3` 等最新阶段交付报告均正确携带 `**RESEARCH-ONLY — Diagnostic only, not a trading recommendation.**`；但 `platform_short_symbol_candidates_sc025_final_full.md`、`key_trade_behavior_review.md`、`platform_optimization_round3~9.md`、多份 `simnow_daily_brief_*.md`/`simnow_report_*.md` 等文件全文未见该声明或任何等价措辞。`declassify_historical_reports.py` 的 docstring 明确说明其存在目的正是"给带有 `GOAL PASSED` 或 `0.847` 通过行的历史报告打上 `<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->` 标记"，说明团队已知晓这一缺口但该脚本显然未对当前全部报告文件完整重跑。
   - 影响：单独阅读这些缺失声明的历史报告（尤其是带有候选/通过表格的报告）的读者，无法从文件本身判断其"仅供研究、非推荡证据"的性质，存在被误当作可信业绩证明二次传播的风险。
   - 建议：对 `diagnostics/*.md` 全量重跑 `declassify_historical_reports.py`，并在 CI/`sync_check.py` 中加入"新增报告必须包含声明"的门禁检查，防止该缺口在未来继续扩大。

10. **`equity_mode` 配置项是纯装饰性的死配置**
    - 定位：`chan_strategy/config.py:79-80`
    - 证据：
      ```python
      "equity_mode": "fixed",  # "fixed" (running realized+unrealized off initial_capital)
                                # | "compound" (documented, NOT implemented in A40)
      ```
      全仓库检索确认该键仅在 `tests/unit/test_position_sizing.py:24,55` 被断言等于 `"fixed"`（重言式，不会因实际行为不同而失败），`positions.py`/`backtest_engine.py`/`portfolio_engine.py` 均未读取该键做任何分支判断。
    - 影响：配置文件"看起来"提供了资金核算模式的可切换项，实际上无论设为何值都不影响任何行为，容易误导后续读者认为存在一个已实现但未启用的复利模式。
    - 建议：要么删除该键，要么补齐读取分支（哪怕只是在 `"compound"` 时抛出 `NotImplementedError`，明确表达"尚未实现"而非"静默忽略"）。

### 🟢 低

11. **`VERSION`/`CHANGELOG.md` 自 A33（2026-07-03）起 15 个任务（A34-A48）未再更新**
    - 定位：`examples/czsc_strategy/VERSION`（`0.1.0`）、`examples/czsc_strategy/CHANGELOG.md`（仅一条 `0.1.0 — 2026-07-03` 记录）
    - 证据：`docs/design/A32_audit_issue_data_feed.md:54` 曾计划"VERSION 升至 0.2.0"，但当前 `VERSION` 文件仍为 `0.1.0`。
    - 影响：按 `AGENTS.md` 的治理约定，"默认关闭、行为不变"的新增开关（A34-A48 绝大多数任务）不强制要求版本号变动，因此这可能是合规的，但对于像 A43 删除 `signals.py` 中失效死分支这类"外部可见变化"的任务，是否也应触发版本号变动，值得团队用 `tools/sync_check.py` 的实际判定规则再核实一次，避免版本号与实际功能积累脱节太久造成外部误判。
    - 建议：核实 `sync_check.py` 的版本触发规则是否覆盖"默认行为不变但新增可选开关"的情况；若规则本就不要求，建议在 `CHANGELOG.md` 中至少以"未发布变更"章节的形式滚动记录，避免出现 15 个任务、0 条变更日志的观感落差。

12. **HANDOFF.md 中"Review Reject Notes"段落长期滞留，未随最终修复移除，易造成信息过期误读**
    - 定位：`D:\repo\vnpy\HANDOFF.md`（A48 Review Reject Notes 章节，约行 229-266）
    - 证据：该章节完整描述了 A48 早期版本中的 4 个真实缺陷（组合协调器每日止损未落表、空头符号错误、`table_name`/`table_names` 参数不匹配、`coordinator=` 死接线），但这些缺陷已在 `6904af92`/`7f300811` 中修复并通过对应回归测试（`tests/unit/test_portfolio_risk.py::test_portfolio_engine_daily_loss_flatten_replay` 等）验证，当前代码不再存在这些问题。
    - 影响：只看 Reject Notes 而不核对 git log/Decision Log 的审阅者，容易把已修复的历史缺陷当作当前存在的缺陷重复上报（本审计在初稿阶段也一度将其列入候选清单，经代码核实后排除）。
    - 建议：在最终 `done` 状态的 HANDOFF.md 中，为已解决的 Reject Notes 段落显式加上"已于 commit X 修复"标注，或移至归档文件，减少信息过期的认知负担。

13. **futures 回测统一使用 0.05% 平仓滑点，未按合约流动性差异分品种校准**
    - 定位：`chan_strategy/config.py:144`（`"slippage": 0.0005`），对照 `config.py:121-135` 的合约乘数差异（5-1000 不等）
    - 影响：苹果期货（AP，流动性较薄）与原油（SC，流动性较好）共用同一滑点假设，可能低估薄流动性合约的实际冲击成本。
    - 建议：为流动性差异较大的品种引入按品种校准的滑点参数（非阻断性，可作为后续研究任务）。

---

## 四、亮点（值得保留的好设计）

- **前视偏差纪律扎实**：`backtest_engine.py` 主循环严格采用"当根 bar 生成信号→存入 `pending_signals`→下一根 bar 开盘价成交"的延迟执行模式（`backtest_engine.py:298-369`），未发现任何跨 bar 的未来函数泄漏；`portfolio_engine.py` 组合协调器同样明确声明且经代码验证"从不读取未来 bar"。
- **治理流程有真实的纠错记录，而非自我宣称**：A38-A48 的每一阶段都在 design/dev/review 三方之间留下了可核查的 reject-and-fix 轨迹（如 A40 报告未追踪、A44 从"信号级单测"补强为"全引擎黄金快照"验收标准、A45 二买闸门语义 bug、A46 设计阶段自相矛盾验收标准、A48 组合协调器 4 个真实缺陷），且经独立复核确认这些问题在当前代码中确已修复，说明其"design→dev→review→done"流程不是形式主义。
- **过拟合自我识别工具已经落地**：`diagnostics/symbol_set_stability_scan.py` 主动对已调优的高精度权重场景（如 `pos_1sell=0.0847`）做符号池敏感性压力测试，并在自身报告中标注"RESEARCH ONLY — NOT PROMOTION EVIDENCE"，这是同类项目中少见的诚实自我审查实践。
- **SimNow 相关脚本严格只读**：全仓库检索未发现任何 `send_order`/`place_order`/`cancel_order` 调用，`simnow_connection_probe.py`/`simnow_daily_capture.py` 等工具仅做行情订阅和事件采集，不具备自动下单能力，符合"决策支持而非自动代客理财"定位。
- **等价性回归测试机制严格**：抽查的 `test_enable_short_false_equivalence.py`、`test_second_buy_and_atr_off_equivalence.py`、`test_portfolio_risk_off_equivalence.py` 均对完整 `BacktestEngine`/`PortfolioEngine` 输出做精确字典相等断言（无容差、无 `pytest.approx`），是真正意义上的字节级等价性校验，而非弱化版的近似比对。

---

## 五、修复优先级建议（Top N）

1. **【高】修复 `_scale_out` 的 `_partial_tp_done` 复位缺口**（`positions.py:832-846`），恢复 `sizing_model="risk"` + `exit_model="structural_atr"` 组合下 ATR 移动止损的可达性，并补充回归测试覆盖该组合。
2. **【高】为期货主链路引入涨跌停/停牌识别与成交约束**，至少先做"统计现有回测中命中涨跌停 bar 的交易占比"的量化诊断，评估当前收益/风险指标的乐观偏差幅度。
3. **【中】声明并校验 888 连续合约复权方式**，把该假设从"隐含"变成"显式代码断言"。
4. **【中】把换月排除逻辑从只读诊断脚本下沉为 `data_adapter.py` 的可选统计字段**，让默认生产报告至少能区分含/不含换月污染的两组指标。
5. **【中】补齐或删除 `enable_1buy_symbols`/`block_1buy_daily_*` 等孤儿配置键**，消除"代码存在但配置路径打不开"的单一真值源缺口。
6. **【中】把 `sizing_model="research"` 的"非可交易盈亏"提示从控制台 print 提升为报告正文字段**，并对全部 `diagnostics/*.md` 历史报告重跑 `declassify_historical_reports.py` 补齐研究声明。
7. **【低】统一结构失效阈值 `stop_loss_pct=0.05` 到 `STRATEGY_CONFIG`**，避免与仓位止损阈值同名不同值造成混淆；清理 `signals.py` 中已被 `sell_signals.py` 取代的旧信号实现或加注明确指向。

> 免责声明：本报告为策略工程质量审核，非投资建议；不对被审策略的实盘收益做任何承诺。
