# 审核报告：缠论（CZSC）量化交易策略 examples/czsc_strategy

**审核对象**：`D:\repo\vnpy\examples\czsc_strategy`（含 `chan_strategy/` 核心包、`diagnostics/`、`tests/`、遗留股票策略 `czsc_multi_timeframe_strategy.py`）
**审核人**：AI股交易专家审核 Agent（ai-stock-trading-reviewer）
**审核日期**：2026-07-03
**版本/快照**：SIGNAL_VERSION = V260615（config.py:72）；工作区当前文件状态

---

## 〇、审核对象说明

目录内实际并存**两套独立策略**：

1. **遗留策略**（README.md 唯一记载）：A股 5m/30m/4h 三级分仓波段战法，`czsc_multi_timeframe_strategy.py` + `czsc_adapter.py`，Baostock 数据。
2. **现行策略**（无 README 记载）：期货 30 分钟缠论择时（一/二/三买卖点），`chan_strategy/` 包 + `run_chan_backtest.py`，SQLite 1 分钟数据（AP/RB/SC/A/ZN 888 连续合约），配套 `tests/`（100% 分支覆盖门禁）与 60+ 份 `diagnostics/` 报告。

本报告以现行策略为主，遗留策略问题单列。

---

## 一、总体结论

- 综合评分：**56/100（C，及格）**
- 一句话结论：**工程与验证纪律明显高于同类业余项目（防未来函数、延迟成交、100%覆盖、walk-forward、2x成本压力测试、诚实记录失败门禁），但存在"用样本外数据反向调参到千分位"的严重回测方法论缺陷、一处永不触发的死亡出场分支、连续合约/夜盘数据假设未处理，且 README 与现行代码完全脱节。当前状态不建议实盘，SimNow 仿真可做但对"GOAL PASSED"结论应打折。**
- 致命项（单维 ≤2 分）：无。但 D4、D5 均为 4 分（重大问题），修复前不应将回测结论用于任何资金决策。

## 二、各维度评分表

| 维度 | 得分 | 评级 | 一句话依据 |
|------|------|------|-----------|
| D1 信号与择时逻辑自洽性 | 6/10 | 及格偏上 | 确认笔纪律与状态机严谨，但"背驰失效"分支在真实数据下永不可达，且二买/三买存在两套并行实现 |
| D2 风控完整性与一致性 | 5/10 | 及格 | 止损/超时/移动止损齐全且优先级明确，但收盘价检查止损导致实际亏损可达标称止损的 4 倍（-12.60% vs 3%），超时与 T0 参数事实失效 |
| D3 参数/阈值跨载体一致性 | 5/10 | 及格 | 手续费/滑点存在三个互相矛盾的"真值"；base_freq/confirm_freq 为死配置；文档注释算术错误 |
| D4 回测/评估严谨性 | 4/10 | 重大问题 | 执行时序与防前视做得好，但 OOS 窗口被反复用于参数选择，SC 空头权重被调到 0.847 恰好使门禁翻绿 |
| D5 数据假设处理 | 4/10 | 重大问题 | 888 连续合约换月/复权完全未声明处理；日线按自然日聚合切断期货夜盘；end_date 字符串比较丢失末日数据 |
| D6 指标定义与术语统一 | 6/10 | 及格偏上 | 信号命名规范统一且有穷尽性验证，但"背驰=确认"分类永不产出、Factor 名与实现不符、存在乱码 |
| D7 市场环境适配与声明 | 6/10 | 及格偏上 | 日线趋势过滤显式建模、strict/loose 有理由，walk-forward 暴露 2023H1 失效但无失效保护机制 |
| D8 可追溯性与单一真值源 | 5/10 | 及格 | config 集中、信号带版本号，但旧版含缺陷信号仍可导入，_patch_backtest1-4 等死代码残留，README 记载的是已废弃策略 |
| D9 透明度与可审计性 | 8/10 | 良好 | 全部源码可读、无黑盒、变异测试已接线、负面结果如实留档；扣分点：用结构上不可能的假数据"喂饱"覆盖率 |
| D10 合规与风险提示充分性 | 7/10 | 良好 | 无自动实盘下单、研究模式免责声明随报告打印；现行策略缺独立 README 与免责声明 |
| **合计** | **56/100** | **C** | |

---

## 三、问题清单（按严重程度排序）

### 🔴 高

**H1. 样本外窗口被用于参数选择——"GOAL PASSED"是门禁拟合的产物，不是策略能力**
- 定位：`diagnostics/sc_short_weight_neighborhood.md:5-10`、`diagnostics/portfolio_goal_expanded_short_sc_0847.md:20,26`、`diagnostics/platform_optimization_round1~9`、`diagnostics/portfolio_goal_expanded_short_sc_085.md` 等系列文件
- 证据：SC 空头权重邻域扫描中，multiplier=0.75/0.8/0.85/0.9/1.0 全部 `pass=False`，唯独 **0.847** `pass=True`（0.8 时 calmar 1.31 < 基准 1.35 差之毫厘；0.85 时 walk-forward 从 6/9 掉到 5/9）。最终存在以 `expanded_short_sc_0847` 命名的"通过"场景。而同一配置**全样本 PF 仅 0.98、收益 0.13%**（portfolio_goal_expanded_short_sc_0847.md:26），基线场景 `portfolio_goal_evaluation.md` 明确 `GOAL PASSED: False`。
- 影响：OOS（2025-01-01~2026-04-24）被 9 轮以上 platform_optimization、trailing_overrides、enable_2buy_symbols、二买 3% 追高过滤等实验反复读取并据此选择参数后，它已不再是样本外。权重精确到小数点后三位（0.847）且相邻值全部失败，是教科书级的门禁过拟合特征。walk-forward 6/9 vs 5/9 因 0.003 的权重变化而翻转，本身说明该"通过"极度脆弱。
- 建议：(1) 冻结当前全部参数，划出**从未参与任何决策的新时段**（2026-04-24 之后的增量数据 + SimNow 实时数据）作为真正的验收集；(2) 禁止任何精度超过一位小数的权重类参数；(3) 把"参数曾读取过哪些时段数据"写入每份 diagnostics 报告头部；(4) 对 0.847 类参数直接回退为 1.0 或删除。

**H2. 固定止损按 30 分钟收盘价检查，跳空/夜盘间隔下实际亏损可达标称止损 4 倍，且未建模涨跌停/流动性**
- 定位：`chan_strategy/positions.py:354-358, 427-437`（`_check_stop_loss` 以 close 比较、以 close 成交）；证据数据 `diagnostics/second_buy_anchor_audit_20220101_20260424.md:29`
- 证据：二买止损配置为 300BP=3%（config.py:32），但真实回测中出现 `SC888 2026-04-07 开仓 → 2026-04-08 stop_loss 平仓，单笔 -12.60%`；-4.77%、-4.63% 等超损案例多条。原因：止损仅在 bar 收盘时检查并以收盘价成交，跨夜盘跳空直接穿透；期货涨跌停板、无对手价的极端情形完全未建模。
- 影响：风控账面预算（权重 × 止损BP）系统性低估真实尾部风险；组合最大回撤等指标同步失真。
- 建议：(1) 止损检查改为 bar 内 low/high 触价，成交价取 `min(触发价, bar.close)` 或触发价加惩罚滑点；(2) 增加隔夜跳空压力测试（以开盘价强制出场重算全部 pairs）；(3) 文档中显式声明"未建模涨跌停与流动性"并纳入 SimNow 验收对照项。

**H3. "背驰失效"分支在真实 CZSC 数据下永不可达——二买/二卖的一条出场路径是死代码，覆盖率用不可能的结构喂饱**
- 定位：`chan_strategy/signals.py:270-280`；消费方 `positions.py:685-694`（二买出场 Factor"方向反转且在中枢内"要求 `背驰V260615_失效`）、`positions.py:945-954`（二卖同）；测试 `tests/unit/test_coverage_closure.py:271-275, 286-299`
- 证据：失效判定要求 `after_zs_bis[-2]` 与 `after_zs_bis[-1]` **两根相邻笔同为 Down**（signals.py:273-274）。CZSC 已确认笔严格方向交替，相邻同向笔在真实数据中不存在。测试通过 `bi_factory` 手工构造连续两根 Down 笔（test_coverage_closure.py:291-292）达成覆盖，掩盖了死代码事实。
- 影响：(1) `背驰=失效` 永不输出，依赖它的二买/二卖"方向反转且在中枢内"出场因子永不触发——实际出场只剩结构失效、止损、移动止损、超时，与设计文档语义不符；(2) 100% 分支覆盖门禁的可信度被削弱。
- 建议：改为比较 `after_zs_bis[-3]` 与 `after_zs_bis[-1]`（跨过中间反向笔的同向比较）；为测试夹具增加"笔方向必须交替"的领域不变量断言；用真实历史数据回放验证该分类至少出现过一次。

**H4. 连续合约（888）换月与复权处理完全未声明——缠论结构信号对价格连续性极其敏感**
- 定位：`chan_strategy/config.py:6-9`（数据源）、`chan_strategy/data_adapter.py` 全文（无任何换月/复权逻辑）、`tests/TEST_REPORT.md` §7、全部 diagnostics 报告（均未提及）
- 证据：全部回测基于 `{symbol}888_1M_raw` 连续合约表，但整个代码库与文档没有一处说明该连续序列是否做过后复权/价差平滑。若为未平滑的主力连续，换月跳空会被笔/分型/中枢当作真实行情：制造假突破（触发三买/结构失效）、假跳空止损、假背驰。
- 影响：所有回测结论（含 walk-forward、OOS）的地基不牢；SC888（换月价差大的品种）恰好是亏损最重、参数最敏感的品种（full -10.87%，backtest_matrix:20），与换月污染的猜想一致，需排除。
- 建议：(1) 向数据供应商确认 888 合成规则并写入 config/README；(2) 若未平滑，改用后复权连续或在换月日禁止开仓并强制以移仓价差修正持仓成本；(3) 对比"剔除换月日 ±1 天信号"前后的绩效差异作为专项诊断。

### 🟠 中

**M1. 手续费/滑点存在三个互相矛盾的"真值"**
- 定位：`config.py:67-68`（0.0001/0.0005，注释称"期货实际成本"）；`backtest_engine.py:69-70`（引擎默认 0.0003/0.001）；`positions.py:287-288` 及六个 create_* 函数默认（0.0001/0.0005）；`diagnostics/platform_optimization_round9.md:51`（"historical engine baseline 0.0003/0.001"）
- 影响：同一策略经 `run_single_backtest`（用引擎默认 0.0003/0.001）与直接按 BACKTEST_CONFIG 跑，成本相差 2 倍多；diagnostics 结论实际基于引擎默认而非 config，config 注释"实际成本"具误导性。
- 建议：引擎构造参数默认改为 `BACKTEST_CONFIG` 取值，删除函数签名里的魔法数字；在报告头打印实际使用的成本参数。

**M2. 二买/三买存在两套并行实现，语义有差异**
- 定位：`signals.py:427-561, 564-665`（旧实现，docstring 自述有"None 分支和 Direction 比较缺陷"由 `sell_signals.py:27` 指出）；`sell_signals.py:26-109`（覆盖实现）；`signals.py:740-752`（旧 `get_all_signals` 仍可导入且不含卖点）
- 证据：两版差异非纯修复——旧版 `buy1_idx + 1 >= len(bi_list)` vs 新版 `buy1_idx + 2 >= len(bi_list)`（sell_signals.py:46）；旧版三买取 `zhongshu_list[-1]`，新版取"其后已有离开段的最近中枢"（sell_signals.py:80）。
- 影响：直接 `from chan_strategy.signals import get_all_signals` 的下游（含未来维护者）会拿到已知缺陷版本；同名函数双真值违反单一真值源。
- 建议：删除或显式弃用旧实现（改名 `_deprecated_*` 并 raise DeprecationWarning），`signals.py.get_all_signals` 直接转发 sell_signals 版本。

**M3. 入场与风控使用不同口径的中枢——开仓锚定的结构和"结构失效"判断的结构可能不是同一个**
- 定位：`zhongshu.py:44-92`（recent 重叠窗口 vs segment 分段两种模式）；入场类信号用 recent（signals.py:136,222,304,357）；`signal_risk_control`/`signal_short_risk_control` 用 segment（signals.py:696，sell_signals.py:237）
- 影响：注释解释了动机（震荡超限需分段计数），但"结构失效=跌破中枢下沿 5%"引用的 zd 可能属于与开仓中枢不同的结构，导致止损位与建仓逻辑脱节——已知设计取舍，但缺乏专项验证。
- 建议：diagnostics 增加"开仓时刻中枢 vs 触发结构失效时刻中枢是否同一"的一致率审计；或结构失效改用与开仓同口径的 recent 中枢，仅震荡超限保留 segment。

**M4. README 与现行代码完全脱节；TEST_REPORT 覆盖清单过期**
- 定位：`README.md:67-78`（文件结构不含 chan_strategy/tests/diagnostics/skill_build）；README 全文只描述已废弃的股票策略；`tests/TEST_REPORT.md:18-27`（覆盖源仅 5 文件）vs `.coveragerc:3-10`（现为整个 chan_strategy 包，含 sell_signals.py/zhongshu.py）
- 建议：为 chan_strategy 撰写独立 README（含数据假设、成本口径、研究模式声明、免责声明）；TEST_REPORT 增加生成日期与自动同步。

**M5. 超时与 T0 风控参数事实失效**
- 定位：`config.py:38-43`（timeout 600/1000/1500 根 30 分钟K线）；`diagnostics/risk_param_sensitivity_20240101_20241231.md:13-14,20-21`（timeout_short/timeout_long 与 baseline 绩效逐位相同）；`positions.py:300`（`self.T0` 赋值后无任何读取）
- 影响：timeout 松到从不约束（600 根 ≈ 数十个交易日，移动止损/止损总在其前触发）；"不允许T0交易"只是注释，无强制逻辑。声明的风控与实际生效的风控不一致。
- 建议：要么把 timeout 收紧到有约束力的量级并重新敏感性测试，要么在文档标注"名义参数"；T0 删除或实现（如禁止同一交易日内平仓后再开仓）。

**M6. 日线按自然日聚合切断期货夜盘；end_date 字符串比较丢失最后一天盘中数据**
- 定位：`data_adapter.py:61-83`（按 `bar.dt.date()` 分组）；`data_adapter.py:221-226`（`datetime <= '2025-12-31'` 文本比较排除 `2025-12-31 09:00:00` 等）
- 影响：国内期货夜盘（21:00 起，SC 至次日 2:30）属于下一交易日，自然日切分把一个交易日拆成两根"日线"，日线趋势过滤消费的是与交易所口径不符的结构；末日数据静默缺失使区间边界结果不可复现。
- 建议：按交易日历（夜盘归属规则）聚合日线；end_date 统一补 `' 23:59:59'` 或改用 `< date+1day`。

**M7. 二买锚点匹配用"低点最接近"启发式，Factor 命名与实现不符**
- 定位：`sell_signals.py:37-45`（全笔列表中找 `abs(bi.low - anchor_low)` 最小者）；`positions.py:678-684`（Factor 名"跌破一买低点"，实际条件是 `方向向下 + 中枢下方`，与一买锚点低点无关）
- 影响：锚点匹配在相似低点并存时可能绑错笔（有 `edt <= anchor_dt` 约束缓解）；出场因子名称让审计者误以为存在真实的锚点破位检查。
- 建议：锚点匹配改为按 `bi.edt == anchor_dt` 精确匹配、失败即返回非二买；Factor 更名为"趋势反转出场"或真正实现对 anchor_low 的破位比较。

**M8. "背驰=确认"分类与 confirm_freq/base_freq 配置从未实现**
- 定位：`signals.py:204-215`（docstring："确认需要次级别协同——在多级别协同中处理"）；`validation.py:44`（穷尽性验证把"确认"列为合法值）；`config.py:13,15`（base_freq="5分钟"、confirm_freq="5分钟" 全库无消费方；引擎实际加载 1 分钟数据，backtest_engine.py:13）
- 影响：文档承诺的次级别确认机制不存在，单级别"疑似"背驰即参与一买判定；config 中两个频率键是误导性死配置。
- 建议：删除死配置或实现 5 分钟次级别确认；validation 的期望值集合与可产出值集合对齐。

**M9. 遗留股票策略"以损定量"实现破坏了 README 承诺的 10% 最大亏损上限**
- 定位：`czsc_multi_timeframe_strategy.py:404-409`（总比例=Σ min(1,10/H_i)·ratio_i）与 `415-422`（层内再按固定 20/30/50 分配 + `max(100,…)` 强制底仓）；`README.md:57-59`（"确保即使所有下轨被打穿，最大亏损也控制在10%以内"）
- 证据：数值反例——H_5m=H_30m=10%、H_4h=30% 时 total_ratio=0.667，最坏亏损 = 0.667×(0.2×10%+0.3×10%+0.5×30%) = **13.3% > 10%**。原公式的每层风险帽在二次分配中丢失；`max(100,…)` 还会在计算股数为 0 时强制买入。
- 建议：直接按 `alloc_i = min(1,10/H_i)·ratio_i` 独立计算各层股数；去掉 100 股强制下限（不足则该层放弃）。若该策略已废弃，在 README 顶部声明废弃状态。

### 🟢 低

**L1. 乱码残留**：`positions.py:169-176` REASON_CODE_MAP 含 GBK 乱码键（"绉诲姩姝㈡崯"等，作为容错可留但应注明）、`positions.py:183` "淇″彿骞仓" 前缀判断；`skill_build/reports/CURRENT_WORK_STATUS.md:57-96` 大段"????"乱码。统一 UTF-8 并修复历史文档。

**L2. 注释算术矛盾**：`config.py:38` "600根30分钟K线 = 300交易小时" 与 `positions.py:296` "600 根 30 分钟 K 线 ≈ 12.5 个交易日" 冲突（按期货每日约 6-8 交易小时，300 小时 ≈ 40-50 个交易日）。

**L3. Position 类默认值与 config 不一致**：`positions.py:284-285`（trailing 150/0.4）vs `config.py:53-54`（300/0.25）。当前创建函数总是传 config 值，无实际影响，但裸 `Position(...)` 会静默使用另一套参数。建议默认值取自 config 或设为必填。

**L4. README 出场过滤描述与代码不符（遗留策略）**：`README.md:44-46` 称"5m破下轨但距30m下轨≤5% → 不卖"为无条件规则；`czsc_multi_timeframe_strategy.py:304-308` 实际仅在**亏损时**应用过滤，盈利时直接卖出。

**L5. `_patch_backtest.py` ~ `_patch_backtest4.py`、`_debug_zs.py`、`debug_pos.py`、`test_czsc_api*.py` 等调试残留**堆积在包顶层，与正式 tests/ 并存，增加误用风险。建议移入 `archive/` 或删除。

**L6. 信号历史仅每 100 根抽样记录**（backtest_engine.py:311），validation 的穷尽性检查因此只验证了 1% 的时点。可改为全量记录 v1 分类（内存占用极小）。

---

## 四、亮点（值得保留的好设计）

1. **防未来函数纪律**：`_get_confirmed_bi_list` 对 `finished_bis + last_bi_extend` 的防御性过滤，并在注释中明令禁止回退到 `bi_list`（signals.py:27-51）；信号一律用已确认结构的收盘价而非 `bars_raw[-1]`。
2. **延迟成交语义**：信号当根生成、下一根开盘价成交，风控当根收盘立即执行，且有 `test_execution_timing.py` 专项守护（backtest_engine.py:263-319）。
3. **日线过滤无前视**：日线 bar 时间戳取当日最后一根 1 分钟（data_adapter.py:91），主循环按 `dt <=` 推进，配 `test_daily_no_lookahead.py`。
4. **验证工程完备**：100% 分支覆盖门禁 + 变异测试接线（且如实承认"覆盖率必要不充分"、32 个变异体存活，TEST_REPORT §9）、幂等 run()、状态回放一致性测试。
5. **诚实的负面记录**：`portfolio_goal_evaluation.md` 基线 `GOAL PASSED: False`、TEST_REPORT 如实写明 2024Q1 近零交易、CURRENT_WORK_STATUS 明确"统一紧移动止损不适合全局默认"——研究留痕文化好。
6. **research-only 开关显式隔离**：`enable_2buy_symbols`、`trailing_overrides` 等注明 Research-only 且默认 None/空，基线行为不受污染（config.py:56-59）。
7. **敞口审计入报表**：max_long/short/gross_exposure 与多空同持 bar 数直接进回测报告（backtest_engine.py:422-425）。

## 五、修复优先级建议（Top 6）

1. **重建可信样本外**（H1）：冻结参数，用 2026-04-24 之后新数据 + SimNow 实时做唯一验收集；废弃 0.847 类三位小数参数。
2. **止损触价化 + 跳空压力测试**（H2）：bar 内 low/high 触发，重算全部历史 pairs，更新所有 diagnostics 结论。
3. **修复"背驰失效"死分支**（H3）：改为跨笔同向比较，并给测试夹具加"笔方向交替"不变量。
4. **澄清 888 连续合约合成规则**（H4）：写入文档；做换月日剔除对照实验，重点复核 SC888。
5. **统一成本单一真值**（M1）：引擎默认读 BACKTEST_CONFIG，报告头打印实际成本。
6. **清理双实现与死配置**（M2/M8/M5）：弃用 signals.py 旧二买/三买，删除或实现 confirm_freq/base_freq/T0/timeout。

---

> 免责声明：本报告为策略工程质量审核，非投资建议；不对被审策略的实盘收益做任何承诺。
