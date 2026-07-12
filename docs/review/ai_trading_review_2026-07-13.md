# 审核报告：czsc_strategy（缠论期货策略）— 修复后复审

**审核对象**：`D:\repo\vnpy\examples\czsc_strategy\`
**审核人**：AI股交易专家审核 Agent（ai-stock-trading-reviewer）
**审核日期**：2026-07-13
**版本/快照**：`32c5f1946a625fe36dce2c207e85a95156c74de3`（`A54 (report-disclaimer hygiene + sync_check gate) review accepted; handoff review->done`）
**上次审核**：docs/review/ai_trading_review_2026-07-12.md（56/100，C）

**实测基线**（本次复审现场执行，非转述）：
- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` → **562 passed, 4 deselected**（31.3s，全绿）
- `python tools/sync_check.py` → **PASS**（版本单一真相 4.4.0 一致；仅 archive_dir 不存在的非阻断 WARN）
- `diagnostics/` 下 132 份 `.md`（含 archive/）中 **123 份携带 RESEARCH-ONLY banner**，9 份未携带（6 份为 `.synccheck.yml` 声明的流程文档豁免 + 2 份 `audit_issue_diagnostics_*` 硬编码豁免 + 1 份 archive/ 未纳入扫描）

---

## 一、总体结论

- 综合评分：**68/100（C，上限区间，接近 B）**（上次 56/100）
- 一句话结论：上次 13 项发现中 10 项经代码级复核确认已真实修复或合理搁置（含两个 🔴 高危项），修复质量普遍是"带等价性快照测试 + 门禁"的工程级修复而非补丁式糊墙；但修复本身引入的新代码（A47 部分止盈、A48 组合重放、A51 涨跌停标记）中存在**部分止盈交易成本被双重缩放（系统性少计约一半）、structural_atr 模式在部分止盈前完全没有盈利侧保护、涨跌停标记对小写品种代码静默失效**等 3 个中危新问题，以及 A52-A54 再次出现 VERSION/CHANGELOG 记账滞后的旧病复发，距离"可信到可以推进仿真验证"仍差一轮针对新增代码的收口。
- 致命项：**无**（十个维度均 >2 分；最低分 D5=5）。

---

## 二、上次发现的 13 项问题复核表

| # | 上次发现 | 修复任务 | 复核结论 | 证据 |
|---|---------|---------|------|------|
| 🔴1 | `_scale_out` 手数取整跳过时不置位 `_partial_tp_done`，永久阻塞 ATR 移动止损 | A49 | **已修复** | `chan_strategy/positions.py:851-858`：lot-floor 跳过分支显式 `self._partial_tp_done = True` 并附注释解释可达性；回归测试 `tests/unit/test_exit_model.py:268-315` 精确覆盖 `sizing_model="risk"` + 1手 + `floor(0.5)==0` 场景并断言 `p._partial_tp_done is True` |
| 🔴2 | 涨跌停/停牌完全未处理 | A50+A51 | **部分修复（诊断+标记已落地，成交约束合理搁置但证据薄）** | A50 只读诊断 `diagnostics/limit_halt_exposure_report.py` 与 2026-07-13 报告存在；A51 `limit_halt_model="aware"` 仅打 `is_entry_at_limit`/`is_exit_at_limit` 标记，不改成交（`positions.py:888-890,991-993`，含 off 模式全引擎快照等价测试）。搁置成交约束的决策在 roadmap 中有事先声明的决策路径（`docs/design/a49-audit-remediation-roadmap.md:213-215,243-249`），程序上成立；但 A50 干净窗口（2026-04-24~07-09）**总共只有 2 笔交易、0 笔触板**，且 RB888/A888 两个品种因数据不足直接报错——以这样的样本量断言"敞口可忽略"证据力接近于零，全历史窗口的触板敞口至今未在未污染口径下量化 |
| 🟠3 | `sizing_model="research"` 警示仅控制台 print | A54 | **已修复** | `backtest_engine.py:647-654`：`sizing_caveat` 作为标准字段写入报告 dict；`portfolio_engine.py:413-418,580-585` 两种组合报告均透传该字段 |
| 🟠4 | 换月排除仅存在于只读诊断脚本 | A52 | **已修复（按"统计标注不默认屏蔽"的原建议口径）** | `rollover_stat_tagging="on"` 时回测循环后对每笔 pair 打 `is_rollover_window`（`backtest_engine.py:514-518`）；检测逻辑单一真相化到 `chan_strategy/rollover_config.py`（transition±1 实际相邻交易日，缺邻日时标注 unavailable 而非乱配，`rollover_config.py:149-202`）；off 等价快照测试 `test_rollover_off_equivalence.py` 存在 |
| 🟠5 | 888 连续合约复权方式未声明未校验 | A52 | **已修复** | `data_adapter.py:361-368`：引用 `diagnostics/contract_adjustment_verification.py` 2026-07-13 实测结论的声明注释（raw 未复权拼接、有 `real_symbol` 列、换月日存在价格跳变、与 A34 H4 found_spliced 一致）；验证脚本与 JSON 证据文件均在 |
| 🟠6 | `enable_1buy_symbols`/`block_1buy_daily_*` 等孤儿配置键 | A53 | **已修复** | `config.py:70-73` 四键齐备且默认 no-op（None/False）；`test_a53_orphan_keys_equivalence.py` + 快照验证默认行为不变 |
| 🟠7 | `stop_loss_pct=0.05` 四处硬编码 | A53 | **已修复** | 四个调用点（`signals.py:787,842`；`sell_signals.py:252,285`）全部改为 `STRATEGY_CONFIG["structural_invalidation_pct"]` 直接索引（键被删会 KeyError 而非静默回退）；`config.py:38-41` 注释明确区分"结构失效阈值"与"分买点止损 BP"两个概念（A53 review 曾打回残留 `.get(...,0.05)`，`480ea8f0` 补齐，reject-and-fix 轨迹可查） |
| 🟠8 | `signals.py` 中被取代的二买/三买旧实现无警示 | A53 | **已修复（有小残留）** | `signals.py:489-494,630-635` 加 `.. deprecated::` 标注并指向 `sell_signals` 权威实现；生产链路（backtest/validation）均从 `sell_signals` 导入。残留：`signals.get_all_signals`（`signals.py:857-871`）本身无弃用标注、仍装配旧实现，且被 `skill_build/build_mapping.py:47`、`skill_build/scripts/analyze_symbol.py:61` 两个活脚本消费 |
| 🟠9 | ~90/130 报告缺 RESEARCH-ONLY 声明 | A54 | **已修复（有小残留）** | 实测 123/132 份带 banner；`.synccheck.yml` 新增 `diagnostics_banner_check` 门禁且 `tools/sync_guardian/sync_check.py:594-630` 有实现、当前 PASS。残留：`audit_issue_diagnostics_*` 前缀豁免硬编码在检查器（`sync_check.py:626`）而非配置声明；`diagnostics/archive/` 不在扫描 glob 内，其中 1 份归档 HANDOFF 无 banner |
| 🟢10 | `equity_mode` 纯装饰死配置 | A53 | **已修复** | `positions.py:932-936`：`equity_mode="compound"` 显式 `raise NotImplementedError`，按原建议"明确表达尚未实现而非静默忽略" |
| 🟢11 | VERSION/CHANGELOG 自 A33 起 15 任务未更新 | （顺带解决） | **部分修复——且已开始复发** | `VERSION`=0.2.0、CHANGELOG 有 0.2.0/A51 条目；但其后完成的 A52（新增 `rollover_stat_tagging` 键）、A53（新增 4+1 配置键）、A54（新增门禁）均为外部可见变更，`git show --stat`（`55d69b08`/`480ea8f0` 等）确认未再动 VERSION/CHANGELOG——同一漂移模式在修复后一天内重现（根因：根仓库 sync_check 只守 `vnpy/__init__.py::4.4.0`，项目级 VERSION 无门禁牙齿） |
| 🟢12 | HANDOFF.md 陈旧 Review Reject Notes | （不排期） | **已解决** | 当前 `HANDOFF.md` grep "Reject" 零命中，A48/A53 的 reject 记录均已随交接清理 |
| 🟢13 | 全品种统一 0.05% 滑点 | （不排期） | **合理搁置** | `config.py:165` 未变；`a49-audit-remediation-roadmap.md:80` 明确列为 backlog 研究任务，与"非阻断"原判一致 |

**小结**：13 项中已修复 8（#1,3,4,5,6,7,10,12）、部分修复/带残留 3（#2,8,9）、部分修复且复发 1（#11）、合理搁置 1（#13）。没有一项属于"宣称修复但实际未修复"。

---

## 三、各维度评分表

| 维度 | 本次 | 上次 | 评级 | 一句话依据 |
|------|------|------|------|-----------|
| D1 信号与择时逻辑自洽性 | 7 | 6 | 良好 | 旧二买/三买实现已弃用标注、中枢口径（segment/recent）在各调用点显式声明理由（`signals.py:762-764`、`sell_signals.py:237-239`）；扣分：`_research_short_open_allowed` 对三卖也强制要求背驰信号（`positions.py:414-444`），三卖本是趋势延续点而非背驰点，空头闸门语义过严且未见文档解释；`signals.get_all_signals` 仍向 skill_build 输送弃用实现 |
| D2 风控完整性与一致性 | 6 | 4 | 及格但有短板 | 🔴#1 已修复且有精确回归测试、孤儿风控键补齐；扣分：structural_atr 模式在部分止盈触发前**没有任何盈利侧保护**（新发现 🟠2），部分止盈成本少计（🟠1），组合止损强平交易零成本入账（🟠5） |
| D3 参数/阈值跨载体一致性 | 7 | 5 | 良好 | `structural_invalidation_pct`/`SYMBOL_LIMIT_CONFIG`/`rollover_config` 均单一真相化且带来源引用；扣分：A52-A54 的 CHANGELOG 记账缺失（🟢8）、banner 豁免名单一半在 YAML 一半硬编码（🟢9） |
| D4 回测/评估严谨性 | 6 | 6 | 及格但有短板 | 延迟成交、无未来函数纪律保持（4H/日线增量更新均 `dt <= bar.dt`，`backtest_engine.py:367-375`），研究口径警示进入报告正文，等价性快照测试体系扩大；扣分：部分止盈成本双重缩放系统性美化 structural_atr 的 A/B 对比（🟠1），组合重放是"事后过滤已成交序列"的反事实近似（被屏蔽开仓不会改变后续信号路径），且 `sizing_model="risk"`+`portfolio_risk="on"` 组合账目口径互斥无守卫（🟠4） |
| D5 数据假设处理 | 5 | 3 | 及格但有短板 | 复权方式已声明+实测校验、换月窗口可标注、涨跌停可标记——三大空白全部从"零"进到"可观测"；扣分：涨跌停"前收盘"用自然日最后一根 bar 收盘价，夜盘品种（RB/SC 21:00 后）的夜盘收盘会污染前收基准，与交易所"前一日结算价"口径的偏差只声明了一半（🟠6）；AP/RB 在测量窗口内曾被临时扩板的事实在代码/报告中均无记载；品种代码小写时限价配置静默失效（🟠3）；成交约束仍未建模 |
| D6 指标定义与术语统一 | 7 | 5 | 良好 | "结构失效阈值 vs 仓位止损"概念区分成文（`config.py:38-41`）、`normalize_exit_reason` 统一退出原因枚举、弃用实现有指向性标注；扣分：`REASON_CODE_MAP` 里保留 GBK 乱码键（"绉诲姩姝㈡崯"）说明历史数据存在编码污染且被就地容错而非治理（`positions.py:276-284`） |
| D7 市场环境适配与声明 | 6 | 6 | 及格但有短板 | regime router、共振过滤、ATR 震荡过滤等环境闸门齐备且默认关闭可审计；仍无独立的"何种行情应回避"策略文档章节，本次修复也未涉及 |
| D8 可追溯性与单一真值源 | 7 | 6 | 良好 | 任务号-代码-测试-HANDOFF 四方对应关系保持，A53 reject-and-fix 有 commit 轨迹，`equity_mode` 死配置消除；扣分：项目级 VERSION/CHANGELOG 漂移复发（A52-A54 零记账），banner 硬编码豁免绕开配置声明 |
| D9 透明度与可审计性 | 9 | 9 | 优秀 | 全部纯 Python 可读源码，无黑盒；诊断/验证脚本只读；新增 A50/A52 验证脚本自带证据 JSON |
| D10 合规与风险提示充分性 | 8 | 6 | 良好 | RESEARCH-ONLY banner 覆盖 123/132 且有 CI 门禁防回流，`sizing_caveat` 进报告正文，README 明示"仅供学习研究不构成投资建议"，无任何自动下单路径；扣分：archive 目录游离于门禁外，豁免名单不完全透明 |
| **合计** | **68/100** | **56/100** | **C（接近 B）** | |

---

## 四、新发现问题清单（按严重程度排序）

### 🔴 高

（无。本次未发现直接资本损失级或造假级问题。）

### 🟠 中

1. **部分止盈交易成本被双重缩放，系统性少计约一半，美化 `structural_atr` 退出模型的对比结果**
   - 定位：`chan_strategy/positions.py:865-872`（`_scale_out`），对照 `positions.py:970-977`（`_close_long` 全额成本）
   - 证据：
     ```python
     scale_fraction = scale_volume / self.volume
     full_transaction_cost = 2 * self.commission_rate + self.slippage
     transaction_cost = full_transaction_cost * scale_fraction     # <-- 按比例打折
     ...
     pnl_currency = (
         gross_pnl * self.cost * scale_volume * self.contract_multiplier
         - transaction_cost * self.cost * scale_volume * self.contract_multiplier  # <-- 又乘了 scale_volume
     )
     ```
   - 分析：`full_transaction_cost`（开+平双边手续费+滑点）本就是**每手**的比例成本；货币成本公式中已经乘了 `scale_volume`，再对费率乘 `scale_fraction` 即是二次缩放。以研究模式默认参数（volume=1、`partial_tp_frac=0.5`、f=0.07%）验算：部分止盈支付 `0.5f×0.5手=0.25f`，剩余平仓支付 `f×0.5手=0.5f`，全生命周期合计 0.75f；而同等交易量走 legacy 单次全平应付约 1.0f（拆成两次平仓实际成本只会更高不会更低）。每个部分止盈生命周期少计约 25% 的交易成本（约 1.75BP/笔）。注释自称"Transaction costs are scaled by the same fraction so total costs remain consistent"，与算术事实不符。
   - 影响：`diagnostics/exit_model_report_2026-07-12.md` 等 legacy vs structural_atr 的 A/B 对比被单向偏置——凡走部分止盈路径的交易成本被低估，会把"新退出模型更优"的结论掺水。
   - 建议：部分止盈 pair 的费率应为 `full_transaction_cost`（不乘 `scale_fraction`），或至少按"开仓成本分摊+本次平仓全额"的口径写清楚并修正注释；补一条"部分止盈+剩余平仓总成本 ≥ 单次全平成本"的守恒断言测试。

2. **`structural_atr` 模式下，部分止盈触发之前不存在任何盈利侧保护；若方向性目标事件从未触发，ATR 移动止损终身不可达**
   - 定位：`chan_strategy/positions.py:691-699`（`Position.update` 的 A47 elif 链）
   - 证据：
     ```python
     elif not self._partial_tp_done:
         partial_event = self._get_partial_tp_event(signals_dict)
         if partial_event:
             self._scale_out(...)
     elif self._check_atr_trailing_stop(price, atr):
         ...
     ```
     ATR 移动止损分支只有在 `_partial_tp_done is True` 后才会被求值（A49 修复的是 lot-floor 跳过这一种置位缺口，而不是这个结构本身）。而 `_partial_tp_done` 只能由部分止盈事件（方向性因子）触发置位。
   - 影响：与 legacy 模式对比，legacy 的百分比移动止损从盈利 300BP 起全程在线；structural_atr 模式下，一笔从未到达方向性目标的持仓，其盈利侧唯一的退出手段只剩信号平仓/固定止损/超时——浮盈可以完整回吐到固定止损位。同时在部分止盈触发的当根 bar，ATR 检查也因 elif 短路被跳过一根。若这是"ATR trailing 只保护剩余仓位"的有意设计，`config.py:114-118` 的注释（"ATR trailing + partial take-profit"）与 A47 设计文档均未把"部分止盈前无 trailing"这一关键行为差异讲明。
   - 建议：要么让 ATR trailing 从开仓起独立于 `_partial_tp_done` 生效（与部分止盈并行），要么在 config 注释与 A47 文档中显式声明该保护空窗，并在 exit_model 对比报告中标注这一结构性差异。

3. **`limit_halt_model="aware"` 的品种限价查找区分大小写，小写品种代码（数据层明确支持）会导致标记静默失效、全部记为"未触板"**
   - 定位：`chan_strategy/backtest_engine.py:314`
   - 证据：`limit_pct = SYMBOL_LIMIT_CONFIG.get(self.symbol, {}).get("limit_pct")`；而 `SYMBOL_LIMIT_CONFIG` 键全为大写（`limit_config.py:19-55`）。数据层查询显式 `COLLATE NOCASE` 兼容"历史大写与近期小写记录"（`data_adapter.py:317`），`run_chan_backtest.py` 的品种代码直接取自数据库 symbol 列；仓位/权重层则统一走 `_research_symbol_key()` 大写归一（`positions.py:302-304`）。唯独限价查找不归一。
   - 影响：`BacktestEngine(symbol="sc888")` + `limit_halt_model="aware"` 时 `limit_pct=None`，每笔 pair 照样写入 `is_entry_at_limit=False`/`is_exit_at_limit=False`——读者拿到的是"看起来跑过检查、实际根本没查表"的假阴性标记，无任何 warning。属于 fail-open。
   - 建议：查找前 `_research_symbol_key(self.symbol)` 归一；`limit_pct is None` 且 aware 模式时打印警告或将标记写为 `None` 而非 `False`。

4. **`sizing_model="risk"` 与 `portfolio_risk="on"` 组合的账目口径互斥且无守卫**
   - 定位：`chan_strategy/portfolio_engine.py:516-527`
   - 证据：组合重放的权益账本固定使用 `pnl_pct * abs(weight) * initial_capital`（比例权重口径），完全不消费 risk 模式产出的 `pnl_currency`/整数手/保证金信息；`portfolio_engine.py` 全文无一处引用 `sizing_model`。
   - 影响：两个闸门同时打开时，单品种报告是货币口径、组合报告是权重比例口径，`daily_loss_limit_pct` 触发判断基于与真实手数无关的合成权益——数字上能跑通，含义上不可比。新增闸门堆叠（`exit_model`×`sizing_model`×`portfolio_risk`×`weighting` 等 10 个开关）没有任何组合合法性校验矩阵。
   - 建议：在 `PortfolioEngine.run()` 入口对不支持的组合显式 raise 或 warning；在设计文档补一张"闸门组合支持矩阵"。

5. **组合每日止损强平的交易按毛收益入账（零手续费零滑点），单向美化 `portfolio_risk="on"` 的结果**
   - 定位：`chan_strategy/portfolio_engine.py:547`
   - 证据：`gross_pnl = sign * (flat_price - pos["open_price"]) / pos["open_price"]` 直接作为 `pnl_pct` 写入 coordinated_pairs，无 `2*commission+slippage` 扣减；而正常 pair 的 `pnl_pct` 来自 `Position` 层，是净额。同一张 pairs 表混用毛/净两种口径。
   - 建议：强平 pair 同样扣减双边成本（强平场景滑点只会更大，不应更小）。

6. **涨跌停带基准的三重简化只声明了一重：夜盘污染"前收盘"、结算价口径、临时扩板窗口均影响标记准确性**
   - 定位：`chan_strategy/limit_config.py:66-86`（`_daily_prev_close_map` 按自然日取最后一根 bar 收盘）、`backtest_engine.py:313,323-326`
   - 证据与分析：
     - (a) **夜盘污染**：`_bar_date` 用自然日。RB/SC 等有夜盘品种 21:00-23:00 的 bar 按交易所口径属于**下一交易日**，但被归入当日，"前一日收盘"实际是前一日夜盘 23:00 的价——该价本身属于被计算日的交易时段，前收基准发生自引用偏移。A50 报告 Methodology 只声明了"previous trading day's last close observed in the loaded window"，未提示夜盘归属问题（而项目在 A39 里明明已经为日线聚合修过同一个问题，`daily_agg="trading_calendar"` 的逻辑没有复用到这里）。
     - (b) **结算价口径**：五个品种的 source 引用全部写明"前一交易日**结算价**±x%"，实现却用收盘价。Methodology 声明了用收盘价这一事实，但未评估两口径偏差方向。
     - (c) **临时扩板**：`limit_config.py:16-18` 仅泛泛写"exchanges reserve the right to widen limits"；AP、RB 在测量窗口内被交易所临时扩板的具体时段，在已交付的代码与报告中均无任何记载——用 steady-state 3%/5% 去套扩板时段会产生假阳性触板标记。
     - 另：`backtest_engine.py:325-326` 对同一 bar 以完全相同的参数计算两次得到必然相等的 `entry_at_limit`/`exit_at_limit`，且 `_bar_at_limit` 不区分涨停/跌停方向、不区分开仓在 bar.open 成交而标记看全 bar 高低——标记语义偏粗，做多在跌停 bar 开仓（真正不可成交场景是涨停买入）与做多在涨停 bar 开仓被打同一个标。
   - 影响：A51 标记目前只能回答"这根 bar 摸过板"，回答不了"这笔成交在这一侧是否真的不可执行"。若未来 A51 标记被用作成交约束的依据，这些偏差会直接传导。
   - 建议：前收改按交易日历口径（复用 A39 逻辑）；`_bar_at_limit` 返回 (touched_upper, touched_lower) 二元组并按开/平方向消费；在 `SYMBOL_LIMIT_CONFIG` 中登记已知的临时扩板时段或至少在报告中列出。

### 🟢 低

7. **平仓 TradeRecord 的 volume 恒为 1（先重置后记录）**：`positions.py:995-1006`（多头）与 `1058-1069`（空头）中 `self.volume = 1` 在 `self.trades.append(TradeRecord(..., volume=self.volume, ...))` 之前执行，risk 模式下交易流水的平仓手数永远记 1（`pairs` 不受影响，`_scale_out` 记录正确）。审计交易流水时会与 pairs 对不上。
8. **VERSION/CHANGELOG 漂移复发**：A52（新增 `rollover_stat_tagging`）、A53（新增 5 个配置键）、A54（新增门禁）皆为外部可见变更，但 `VERSION` 停在 0.2.0、CHANGELOG 最后一条是 A51。根因是项目级 VERSION 无门禁（根 `.synccheck.yml` 只守 `vnpy/__init__.py`）。建议把 `examples/czsc_strategy/VERSION` 纳入某个 sync_check 规则，否则上次 #11 的"15 个任务 0 条日志"迟早重演。
9. **banner 门禁豁免名单半透明**：`audit_issue_diagnostics_*` 前缀豁免硬编码在 `tools/sync_guardian/sync_check.py:626` 而非 `.synccheck.yml` 的 `skip` 列表；`diagnostics/archive/` 不在扫描范围（glob 非递归），其中 1 份归档 HANDOFF 无 banner。豁免应全部声明在配置里。
10. **`weighting="risk_parity"` + `portfolio_risk="off"` 静默无效但被回显**：`_build_off_report` 是无条件等权平均（`portfolio_engine.py:361-369`），但报告仍写 `"weighting": STRATEGY_CONFIG.get("weighting")`（`portfolio_engine.py:422`），读者会误以为风险平价已生效。
11. **`REASON_CODE_MAP` 容错 GBK 乱码键**：`positions.py:279-284` 将"绉诲姩姝㈡崯"（"移动止损"的 UTF-8 字节被 GBK 误解码产物）等乱码字符串映射回正常 code——说明某处历史链路产生过编码污染，被就地打补丁而非根治，存在其他中文 reason 仍以乱码落入 `"other"` 桶的风险。
12. **`signals.get_all_signals` 仍向 skill_build 输送弃用实现**：`skill_build/build_mapping.py:47`、`skill_build/scripts/analyze_symbol.py:61` 从 `chan_strategy.signals` 导入 `get_all_signals`，其内部装配的是已被标记 deprecated 的二买/三买实现；`signals.get_all_signals` 本身无弃用标注。
13. **空头开仓闸门对三卖也要求背驰**：`_research_short_open_allowed`（`positions.py:414-444`）把 `{freq}_D1BI_背驰V260615 ∈ {疑似,确认}` 作为一/二/三卖统一前置条件；三卖是中枢破位后的趋势延续点，缠论语义上不要求背驰。闸门本身默认生效于 `enable_short=True` 路径，语义过严会系统性压低三卖样本量，且该不对称未见文档说明。

---

## 五、亮点（值得保留的好设计）

- **修复不是"改到测试变绿"而是"改到有等价性证明"**：每个新闸门（A51/A52/A53）都附带 off 模式的全引擎字典级快照等价测试（`test_limit_halt_off_equivalence.py`、`test_rollover_off_equivalence.py`、`test_a53_orphan_keys_equivalence.py`），确保默认路径字节不变——这是本次复审能快速确认"没修坏别的"的关键基础设施。
- **A53 的 review 打回记录是真实对抗性审核的证据**：`92f5ead1` 打回"`.get(..., 0.05)` 残留第二真值源"、`480ea8f0` 改为直接索引（键被删即 KeyError），这个细节说明 review 阶段真的在读代码而不是走流程。
- **单一真相模块化模式成型**：`limit_config.py` / `rollover_config.py` 把"诊断脚本先用、生产标记后用"的逻辑抽成共享模块并附交易所一手来源引用，避免了诊断与生产两套实现漂移——这是对上次 #4/#7 类问题的结构性免疫。
- **A50→A51 的"先量化再决策"纪律**：roadmap 事先写明"A50 数字出来前不定 A51 语义，敞口可忽略则可以决定不做 enforcement"（`a49-audit-remediation-roadmap.md:213-215`）——决策路径本身是对的，问题只在样本量（见 🔴2 复核栏）。
- **banner 门禁有牙齿**：`diagnostics_banner_check` 进入 `.synccheck.yml` 并在 sync_check 中强制执行，新报告漏声明会直接 FAIL，堵住了上次 #9 "补完存量、增量继续漏"的复发通道。
- **前视纪律在新代码中延续**：4H 共振的增量更新严格 `h4_bars[idx].dt <= bar.dt`（`backtest_engine.py:372-375`），`AtrStateTracker` 百分位显式剔除当根（`signals.py:929-940` "excluding the current bar, to avoid lookahead"），A40 权益计算用 `bar.open` 与延迟成交同价（`backtest_engine.py:328-333`）。

---

## 六、修复优先级建议（Top 6）

1. **【中·必修】修正 `_scale_out` 交易成本双重缩放**（`positions.py:867`）：费率不乘 `scale_fraction`，并对 exit_model 历史对比报告重跑，确认 structural_atr 结论方向不被翻转；补总成本守恒断言测试。
2. **【中·必修】决断 structural_atr 的盈利侧保护空窗**：要么让 ATR trailing 自开仓起生效，要么在 config/A47 文档/对比报告三处显式声明"部分止盈前无 trailing"，消除与 legacy 对比时的隐性语义差。
3. **【中】`SYMBOL_LIMIT_CONFIG` 查找大小写归一 + `limit_pct` 缺失时 fail-loud**（`backtest_engine.py:314`），消除 aware 模式的假阴性标记。
4. **【中】给闸门组合上守卫**：至少 `sizing_model="risk"`+`portfolio_risk="on"` 应 raise/warn；组合强平 pair 补扣双边成本（`portfolio_engine.py:547`）。
5. **【中】把 A50 诊断在全历史窗口（含污染窗口，注明性质）重跑一次**：2 笔交易的敞口结论撑不起"enforcement 可缓做"的决策；同时修正前收盘的夜盘归属（复用 A39 交易日历逻辑）并登记 AP/RB 临时扩板时段。
6. **【低】项目级 VERSION/CHANGELOG 纳入门禁**：为 `examples/czsc_strategy/VERSION` 增加 sync_check 规则并补记 A52-A54；banner 豁免全部移入 `.synccheck.yml` 声明。

> 免责声明：本报告为策略工程质量审核，非投资建议；不对被审策略的实盘收益做任何承诺。
