# Portfolio-Risk / Risk-Sizing 统一账户模型设计

## 状态：设计已通过，Q2 已决策，进入分阶段实现

**2026-07-16 用户决策**：Q2（"以谁为准"）选定 **手数/真实保证金为准**。`risk_parity`/
`cluster_gross_cap` 保留，但降级为"开仓前的预算/上限/排序约束"，不再作为账户会计基础——
共享 `PortfolioLedger`（真实保证金占用 + 真实货币 PnL）才是账户真值。理由：项目目标是生产级期货
组合评估路径，不是组合研究打分器；期货实盘的最终约束是可用资金、保证金占用、合约乘数、整数手、
手续费/滑点/浮盈浮亏，不是权重。选"权重为准"虽然实现成本更低，但会把 A40 已经建立的手数/保证金
可信度倒退为"组合分配名义敞口再推导手数"的研究框架，不符合目标。

**用户确认的分阶段路线**（本设计文档记录路线，具体任务在 HANDOFF 中逐阶段推进）：

1. **阶段一（只读账本，不参与拦截）**：组合回放后生成组合级真实保证金占用、真实货币 PnL、
   最大保证金使用率、单品种占用、cluster 占用报告——纯测量，不改变任何开仓判定。
2. **阶段二（接入开仓判定）**：开仓前读取共享 `PortfolioLedger`，拒绝超过总保证金上限、单品种上限、
   cluster cap、daily loss limit 的新仓。
3. **阶段三（熔断动作决策）**：组合回撤熔断后是"禁止新开仓"还是"强制平仓"，需要单独产品决策，
   不在阶段一/二范围内。
4. **SimNow 继续保持只读事实源**，不与回测账本共用代码，只用于校验模型偏差。

本文档以下章节是决策前的分析记录，保留作为背景依据；"需要回答的设计问题"章节里 Q2 已有明确结论，
其余问题（Q1/Q3/Q4）的答案将在阶段一实现时按需具体化，不需要在本文档里预先精确定义所有数值细节。

## 背景

`sizing_model="risk"`（A40）与 `portfolio_risk="on"`（A48/P8b）目前在
`chan_strategy/portfolio_engine.py:606-615` 被显式互斥：

```python
if sizing_model == "risk" and portfolio_risk == "on":
    raise NotImplementedError(
        "sizing_model='risk' with portfolio_risk='on' is not supported yet: "
        "the coordinated portfolio replay uses weight-based accounting, which is "
        "incompatible with the currency-based lots/margin accounting of risk sizing."
    )
```

这是本项目自 A53 起就已知且如实记录的限制，不是本次新发现。第三、四、五轮第三方审核都把它列为
"组合级风控与真实手数风控不能同时验证"的核心短板——单笔风险侧（止损、超时、移动止损、涨跌停拒单、
换月门控、intrabar 止损、真实手数/保证金约束）已经相对完整，但组合层面的真实资金风险闭环缺失。

## 现状证据（两套独立的会计模型）

### `sizing_model="risk"`（单品种，手数/保证金记账）

- `Position._open_long()`/`_open_short()`（`positions.py:979-1130` 附近）按 `equity`、
  `total_open_margin`、`price * multiplier * margin_rate` 计算可开手数（整数手），逐笔记录
  `pnl_currency`。
- `BacktestEngine._compute_equity_and_margin()`（`backtest_engine.py:771-786`）为**单个品种自己的
  `equity`**，逐 bar 累加该品种自己持仓的 `total_open_margin`，与其他品种完全隔离。
- `max_total_open_margin`/`max_margin_utilization_pct`（`backtest_engine.py:884-890`）都是单品种
  报告字段，天然没有跨品种视角。

### `portfolio_risk="on"`（组合，权重/百分比记账）

- `PortfolioCoordinator`（`portfolio_engine.py:84` 起）先让每个品种**各自独立**跑一遍
  `BacktestEngine`（`_run_per_symbol`，`portfolio_engine.py:338`），拿到each品种自己的百分比
  `equity_curve` 和已平仓 `pairs`。
- `_build_on_report()`（`portfolio_engine.py:433`）把这些**已经算好的、彼此独立的**逐品种
  equity/trade 事件按时间戳合并重放，用 `risk_parity` 权重、`cluster_gross_cap`、
  `daily_loss_limit_pct` 对开仓做门控——但它消费的是每个品种已经用**自己的资金 100% 假设**跑出来
  的收益率，不是一个共享的、真实分配了资金的组合账户。

**核心矛盾**：`risk` sizing 的整数手/保证金约束，天然要求知道"当前组合还剩多少可用保证金"；而
`portfolio_risk="on"` 目前的实现方式（先独立跑单品种，再重放合并）从架构上就没有"共享保证金池"这个
概念——每个品种在自己的独立回测里，都认为自己拥有全部 `initial_capital`。

## 需要回答的设计问题（供用户/后续设计迭代讨论，非结论）

### 1. 组合账户权益如何计算：静态本金、逐日权益、逐笔权益？

现状：`risk` sizing 是逐 bar 更新的单品种 `equity`（`_compute_equity_and_margin` 每根 bar 都用
`bar.close`/`bar.open` 重算）；`portfolio_risk` 的 `daily_loss_limit_pct`
（`portfolio_engine.py:230`）是逐日结算式的组合层 PnL。统一账户至少要在这两种粒度里选一个作为
"真实持仓保证金占用"判定的基准时点——是每根 bar 都重新计算组合可用保证金（更精确，但需要所有品种的
bar 严格对齐），还是只在日切时点重算（更简单，但日内新增持仓无法即时感知组合保证金占用）？

### 2. `risk` sizing 产出的是手数，`portfolio_risk` 目前偏权重——以谁为准？

这是最核心的选择。两个方向都可行，但含义完全不同：
- **手数为准**：组合层不再用"权重/risk_parity"分配名义敞口，而是直接消费每个品种真实开出的手数和
  保证金占用，组合层的"cluster cap"、"daily loss limit"都改成基于真实保证金/真实货币 PnL 的判定。
  好处是与真实期货账户完全一致；代价是 `risk_parity` 权重这套现有机制需要重新设计或废弃。
- **权重为准**：`risk` sizing 让位于组合层的权重分配，单品种的"整数手"计算变成组合权重分配后的
  派生结果，而不是独立决策。好处是保留现有 `risk_parity`/`cluster_gross_cap` 机制；代价是
  单品种视角的手数/保证金测试（A40 已有的等价性测试）可能需要重新审视其"单品种独立可信"的前提。

本文档不预设答案——这需要用户结合"这个策略未来是打算按品种独立分配资金实盘，还是打算做真正的
组合层资金调度"来判断，属于产品/业务决策，不是纯技术判断。

### 3. 保证金占用、合约乘数、手续费、滑点、浮盈浮亏如何统一入账？

现状这四项在单品种 `risk` sizing 里都已经有明确实现（`positions.py` 的 `pnl_currency` 计算、
`total_open_margin` 累加），缺的是"多个品种共享同一个资金池"时如何汇总——例如品种 A 已用去 60% 保证金
后，品种 B 的开仓判断需要读取"当前组合总保证金占用"而不是"品种 B 自己的保证金占用"。这需要
`PortfolioCoordinator` 在开仓判定时刻拥有一个跨品种共享的可变状态（当前架构里
`_run_per_symbol` 是完全独立、互不知晓的循环，做不到这一点）。

### 4. 多品种同向暴露、单品种上限、总保证金上限、组合回撤熔断如何定义？

`cluster_gross_cap`（`portfolio_engine.py:104`）和 `daily_loss_limit_pct`（`portfolio_engine.py:105`）
已经是权重口径下的组合级风控，概念上是对的，只是数值基准需要从"权重敞口占比"换成"真实保证金占比/
真实货币回撤"。这部分改造相对直接——一旦第 2 条的"以谁为准"决定了，这两个已有机制大概率可以复用其
判定时机（逐 bar/逐日）和触发后动作（拒绝新开仓/强制平仓），只需换算基准量纲。

### 5. 回测、正式评估、SimNow 观察三条路径是否使用同一套账户模型？

现状：
- 单品种回测/正式评估（`run_formal_evaluation.py`）走 `BacktestEngine`，`sizing_model="risk"` 时
  是手数/保证金记账。
- 组合回测走 `PortfolioEngine`/`PortfolioCoordinator`，是独立品种重放+权重门控。
- SimNow 观察工作流（`diagnostics/simnow_daily_monitor.py` 等）是只读观测生产环境的真实账户状态
  （`account_contamination`/`external_active_positions` 等字段），本身不做回测记账，是第三套独立
  的"读真实账户"路径。

**这三者目前没有必要、也不应该被强行统一成同一套代码**——SimNow 路径读的是真实券商/期货公司返回的
账户状态，这是"事实来源"，不需要模拟；回测和正式评估如果统一了账户模型，理应让 SimNow 观察结果成为
未来校验回测账户模型准确性的对照基准，而不是反过来让回测模型的抽象绑架真实账户读取逻辑。

## 已确认的下一步（阶段一，将作为独立 HANDOFF 任务推进）

**claude-code 确认的具体技术落点**：`PortfolioCoordinator.run()`（`portfolio_engine.py:606-615`）
里的 `NotImplementedError` 只在 `sizing_model == "risk" and portfolio_risk == "on"` 时、且在调用
`_run_per_symbol()` **之前**触发；而 `_run_per_symbol()`（`portfolio_engine.py:338`）本身只是对每个
品种独立跑一遍 `BacktestEngine.run()`，不涉及权重协调逻辑，也不会触发这个拦截。这意味着阶段一的只读
账本**不需要修改 `PortfolioCoordinator.run()` 或移除现有拦截**——只需要一个新的诊断脚本，直接以
`sizing_model="risk"` 循环调用每个品种自己的 `BacktestEngine.run()`（可以直接复用
`_run_per_symbol()` 这个方法，或者在诊断脚本里写一个等价的独立循环，dev 决定），读取每个品种
`equity_curve` 里已有的 `total_open_margin`（`backtest_engine.py:876` 附近的
`generate_report()` 输出字段）和 `strategy.get_combined_trades()` 里已有的 `pnl_currency`，按时间戳
汇总成组合级视角：

- 组合总保证金占用（各品种 `total_open_margin` 按同一时间戳求和）。
- 组合真实货币 PnL（各品种已平仓 `pnl_currency` 累加 + 浮动持仓的估算浮盈浮亏）。
- 最大保证金使用率、各品种占用、各 `corr_clusters` 占用（复用 `STRATEGY_CONFIG["corr_clusters"]`
  已有的品种分组，不新建分组机制）。

这是纯新增的只读度量报告，不修改 `PortfolioCoordinator`/`BacktestEngine` 的任何现有执行路径或既有
测试断言，`sizing_model="risk"` + `portfolio_risk="on"` 的现有 `NotImplementedError` 原样保留
（阶段二才考虑是否/如何替换为真实联合回测与拦截）。

阶段二（联合回测替代独立重放 + 真实拦截）与阶段三（熔断动作）留待阶段一验证账本准确性后再展开，
不在当前任务范围内预先设计细节。

## 外部数据依赖问题（不在本设计讨论范围，仅记录，供后续单独跟踪）

以下与"账户模型统一"是两个独立问题，本文档不展开，按用户建议原样保留为生产化前置限制：

- 连续合约复权/换月价差处理（`RISK_NOTE_888_SPLICE.md` 已记录，需要真实交易所主力合约切换规则或
  行情商复权数据源）。
- 结算价涨跌停带建模（当前 `limit_config.py` 用前收盘价近似，真实结算价数据源未接入）。

这两项继续保持当前的保守近似（`limit_halt_model="enforce"` + 换月门控），不在没有真实数据源的情况下
强行实现，等数据源确定后再作为独立任务处理。
