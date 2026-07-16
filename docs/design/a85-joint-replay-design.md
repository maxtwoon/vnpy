# A85 — Joint Replay + Shared PortfolioLedger 设计（算法设计任务，不含实现代码）

## 状态与定位

本文档是 [portfolio-risk-fusion-design.md](portfolio-risk-fusion-design.md) 阶段二的**算法边界设计**，
不是实现任务。产出物就是本文档本身；验收标准是"后续实现者不需要对任何一处语义猜测"，而不是任何代码
变更。[A83](../../examples/czsc_strategy/diagnostics/portfolio_ledger_report.py)/[A84](../../examples/czsc_strategy/diagnostics/portfolio_ledger_acceptance_2026-07-16.md)
证明的是"独立单品种结果按时间对齐汇总是可信的"，**不是**"联合回放、共享保证金池、实时开仓拦截、
cluster/portfolio gating 是正确的"——这两者是完全不同的算法问题，A85 只回答后者。

Phase 1（A83/A84，只读账本）与本设计的关系：Phase 1 的 `_build_ledger()` 是"回放后拿已经跑完的
per-symbol equity_curve，事后求和"；本设计要解决的是"回放**过程中**，每根 bar 每个品种要不要开仓，
取决于当时其他品种已经占用了多少共享保证金"——这是一个**在线（online）、有状态、跨品种耦合**的问题，
Phase 1 的事后聚合完全不涉及这个耦合。

## 现状代码基线（本设计的落点）

- `PortfolioEngine._run_per_symbol()`（`portfolio_engine.py:338`）：当前对每个品种独立跑一遍
  `BacktestEngine.run()`，互不知晓，不共享任何状态。
- `PortfolioEngine._build_on_report()`（`portfolio_engine.py:433`）：把独立跑完的逐品种 `pairs`/
  `equity_curve` 按时间戳合并重放，用 `PortfolioCoordinator.allow_open()`（`portfolio_engine.py:240`）
  做**事后（post-hoc）**门控——它读的是已经用 100% 自有资金跑出来的信号序列，不是"这笔单子如果被拒，
  该品种真实回测路径会不同"的真实联合回放。
- `PortfolioCoordinator`（`portfolio_engine.py:84`）已有：`cluster_gross_cap` 拦截
  （`allow_open`）、`daily_loss_limit_pct` 熔断+全平（`on_bar`→`_flatten_all`）、`_trading_day()`
  日切/夜盘映射（`portfolio_engine.py:32`，已支持 `daily_agg="trading_calendar"`）。这些机制的
  **触发时机和动作**可以复用，需要换的是**判定用的量纲**（权重占比 → 真实保证金/真实货币）以及
  **门控是否真实影响后续回放路径**（当前不影响，因为是事后重放；联合回放必须影响）。
- `sizing_model="risk"` 侧：`Position._open_long()`/`_open_short()`（`positions.py`）按
  `equity`/`total_open_margin`/`price*multiplier*margin_rate` 算整数手，是单品种独立状态机，
  没有"跨品种共享资金池"概念。

## 1. 联合时钟模型

**决策：以自然分钟时间戳为唯一联合时钟，`outer join` 对齐，逐 bar 前向填充估值、不前向填充信号。**

- **多品种 bar 对齐**：用所有品种 `equity_curve`/K线的 `dt` 做时间戳并集（`outer join`），按时间戳
  升序驱动整个联合回放循环——这与 A83 `_build_ledger()`（`portfolio_ledger_report.py`）已经验证过的
  对齐方式一致，不重新发明。每个联合回放的"tick"对应并集里的一个时间戳。
- **某品种缺 bar 时**：
  - **估值（保证金占用/浮动盈亏）**：在该品种自己的 `[first_dt, last_dt]` 范围内，前向填充（沿用
    A83 修复过的"不越界"规则——range 外一律置零，不做任何填充）。这保证组合总保证金占用在缺 bar 的
    分钟里不会凭空消失或凭空产生。
  - **信号/开仓判定**：**不**前向填充信号——一个品种在当前联合时钟 tick 没有自己的 bar，就没有
    机会产生新信号，也不需要为它做开仓判定。这与"该品种这一分钟根本没有新数据"的物理现实一致，
    不应该用邻近 bar 的价格伪造一个信号决策。
  - 已开仓头寸的止损/移动止损/超时等**品种自身**的风险动作（这些当前由 `BacktestEngine`/`Position`
    内部逐 bar 驱动，不属于组合层）在缺 bar 的分钟里同样跳过——沿用现有单品种引擎"没有新 bar 就不
    评估"的既有语义，联合回放不改变这一点，只改变"组合层是否读取到这个品种在这一刻的估值"。
- **日切/夜盘/跨交易日**：直接复用现有 `_trading_day(dt, daily_agg, night_session_start_hour)`
  （`portfolio_engine.py:32`），已支持 `daily_agg="trading_calendar"`（夜盘 ≥20:00 归入次日交易日）
  与 `daily_agg="natural"`（自然日）两种口径，与 A79 引入的单品种 `daily_agg` 语义保持一致，不新增
  第三种口径。`daily_loss_limit_pct` 的"当日"边界沿用这个函数的返回值，不做特殊处理。
- **为什么不选"严格要求所有品种 bar 完全对齐才推进联合时钟"**：品种停牌、上市时间不同、结算时间
  不同（如 `SC888` 夜盘到 23:59，`AP888` 只到 14:59，A84 验收数据已经证实这一真实差异）是期货组合
  的常态，要求严格对齐会导致联合时钟频繁停滞或丢弃大量真实数据，不可行。

## 2. 共享账本状态（`PortfolioLedger`）

**决策：`PortfolioLedger` 是一个在联合回放循环内部维护的可变对象，每个联合时钟 tick 更新一次，字段如下。**

```
PortfolioLedger（每个 tick 后的快照）:
  dt: datetime                              # 当前联合时钟时间戳
  cash: float                                # 可用现金 = initial_capital + 累计已实现PnL − 累计手续费
  realized_pnl_cum: float                    # 累计已实现 PnL（货币）
  unrealized_pnl: float                      # 当前所有持仓的浮动盈亏之和（货币）
  equity: float                              # cash + unrealized_pnl
  margin_occupied_total: float               # 所有持仓保证金占用之和（货币）
  margin_available: float                    # equity − margin_occupied_total
  margin_by_symbol: dict[symbol, float]      # 逐品种保证金占用（品种自身 range 外恒为 0，同 A83 语义）
  margin_by_cluster: dict[cluster, float]    # 逐 cluster 保证金占用（复用 STRATEGY_CONFIG["corr_clusters"]）
  open_positions: dict[(symbol, strategy), Position]  # 当前持仓明细
  trading_day: date                          # 当前交易日（_trading_day() 返回值）
  day_start_equity: float                    # 当日（trading_day 切换时）起始 equity，daily_loss_limit 基准
  daily_loss_limit_active: bool              # 当日是否已触发熔断
```

- **更新顺序（每个 tick 内，严格按此顺序，避免同一 tick 内状态竞争）**：
  1. 若 `trading_day` 变化 → 结算：`day_start_equity = equity`（用上一个 tick 收盘时的 equity），
     `daily_loss_limit_active = False`。
  2. 对每个在本 tick 有 bar 的品种，用其最新价格重算该品种所有持仓的 `unrealized_pnl` 与
     `margin_occupied`（沿用 `positions.py` 现有单品种逐 bar 估值公式，不改变公式本身，只改变
     "谁的 equity/margin 参与门控判定"这一层）。
  3. 汇总 `unrealized_pnl`/`margin_occupied_total`/`margin_by_symbol`/`margin_by_cluster`。
  4. 计算 `equity`/`margin_available`。
  5. 检查 `daily_loss_limit_pct`（见第 3 节）——若触发，本 tick 内先执行强平，再重算一次
     `margin_occupied_total`/`equity`（强平后应归零对应持仓的保证金占用）。
  6. 处理本 tick 到达的信号：先平仓信号，再开仓信号（同一 tick 内，平仓释放的保证金必须先入账，
     开仓判定才能看到这笔释放的额度——这是"先平后开"顺序的唯一理由，不是任意选择）。
- **数据区间外的品种**：`margin_by_symbol[symbol]` 在该品种 `[first_dt, last_dt]` 之外恒为 `0.0`，
  `open_positions` 里不应残留该品种任何超出其 range 的持仓（沿用 A83 已验证的"不越界"规则；如果
  某品种在 `last_dt` 时仍有未平仓头寸，视为该品种数据在回测窗口末尾被截断，其未平仓头寸在 `last_dt`
  后按"标记为该品种数据结束、保证金立即释放、不计入组合浮动盈亏"处理——这与单品种 `BacktestEngine`
  现有的"回测结束时强制以最后收盘价平仓并计入已实现 PnL"逻辑保持一致，不发明新语义，只是把这个既有
  单品种规则应用到"品种自己的 range 结束"而不是"整个回测窗口结束"）。

## 3. 开仓 gating 语义

**决策：所有上限判定发生在"先平后开"顺序里的开仓阶段，全部是硬性拒绝（不排队、不部分成交），
`daily_loss_limit` 触发时是"禁止新仓 + 立即强平"（延续 `PortfolioCoordinator._flatten_all()`
现有语义，不改为"只禁新仓不强平"）。**

- **总保证金上限**：`margin_occupied_total + 本次拟开仓所需保证金 > equity * max_total_margin_pct`
  时拒绝。`max_total_margin_pct` 是新增配置项，默认值需要用户/后续任务明确给出（本设计不臆造数值，
  建议默认设为 `1.0`，即"不超过当前组合权益"，与单品种 `risk` sizing 已有的"不能开出超过自己权益
  能承受的保证金"的既有保守假设一致；这是"为什么这个数字是安全的"而不是"拟合了历史数据"的默认值，
  符合项目一贯的默认值纪律）。
- **单品种上限**：`margin_by_symbol[symbol] + 本次拟开仓保证金 > equity * max_symbol_margin_pct`
  时拒绝。同样建议默认值参考单品种 `risk` sizing 现有行为——单品种回测本身没有"品种自身上限"这个
  概念（它天然假设 100% 权益可用），所以联合回放引入这一层是**新增的组合层约束**，不是对现有单品种
  行为的还原；默认值应设为一个明显宽松的值（如 `1.0`，即单品种也可用满全部权益），把"是否要更严格
  地限制单品种敞口"留给后续产品决策，而不是本设计臆造一个收紧的数字。
- **cluster cap**：复用 `cluster_gross_cap`（`portfolio_engine.py:104`）现有配置项和判定时机
  （`allow_open()` 里的门控），但判定量纲从"权重占比"换成`margin_by_cluster[cluster] / equity`。
  `cluster_gross_cap` 的既有默认值（`1.0`）延续，不重新定义。
- **daily loss limit 触发后的动作**：**禁止新仓 + 立即强平全部持仓**（沿用
  `PortfolioCoordinator.on_bar()`→`_flatten_all()` 现有权重版本的语义，只换算基准为真实货币 PnL：
  `day_pnl_pct = (equity - day_start_equity) / day_start_equity <= -daily_loss_limit_pct`）。
  **不采用"只禁新仓、保留已有持仓"的备选方案**，理由：现有代码已经实现并测试了"强平"这一支路径
  （`portfolio_engine.py:282` `_flatten_all`），若阶段二改为"只禁新仓"，等于推翻已有既定行为，
  这属于阶段三（熔断动作决策）明确留白的范围——用户在 portfolio-risk-fusion-design.md 里已经把
  "熔断后禁新仓 vs 强平"列为独立的阶段三产品决策；本设计在阶段二**保持现状（强平）**，因为这是
  当前代码唯一实现过的路径，阶段三如果决定改为"只禁新仓"，是对现有行为的显式变更，需要单独任务，
  不应该在联合回放算法设计阶段顺带做出这个决定。
- **不采用"排队等待保证金"或"部分成交"**：这两者都需要引入订单簿/成交排队的新状态机，超出
  "联合回放 + 门控"的既有架构假设（单品种 `Position` 本身是"整手要么全开要么不开"，没有部分成交
  概念），保持与现有单品种语义一致，硬性拒绝即可。

## 4. 信号执行顺序

**决策：同一联合时钟 tick 内的多个开仓信号，按 `(symbol, strategy)` 的固定字典序排序执行，
不做资金争抢的"优先级"设计；资金不足时按此固定顺序，先到先得，后续的直接被拒。**

- **排序键**：`sorted(signals_this_tick, key=lambda s: (s.symbol, s.strategy))`。选择字典序而非
  "按信号强度/历史胜率/组合权重"等业务优先级，理由：
  1. **确定性优先于"最优性"**——引入任何业务优先级都需要一个新的打分/排序规则，这本身是一个需要
     独立验证的产品决策（等价于又一次"以谁为准"的选择），不应该在联合时钟机制设计里顺带臆造。
  2. 字典序是**与输入数据完全无关**的确定性排序，保证同一份历史数据无论重跑多少次，结果完全一致
     （可复现性是回测评估的底线要求，项目一贯的"diagnostic-first / 不臆造未经验证的规则"纪律）。
  3. 若未来需要按业务优先级排序，只需替换排序 key，不影响联合时钟/账本/门控的其余设计——这是一个
     局部可替换的决策点，不是架构性约束。
- **"资金不足时谁先拿到保证金"**：严格按上面排好的顺序逐个尝试 `allow_open()`；一旦某个信号被拒绝
  （无论因为总保证金/单品种/cluster cap 中的哪一条），**跳过它，继续尝试队列中的下一个**（不是
  "整批同时失败"）。这与单品种 `risk` sizing 现有的"逐笔独立判定"语义一致。
- **是否需要 deterministic tie-breaker**：字典序本身对 `(symbol, strategy)` 组合是全序的（不存在
  两个信号 `symbol` 和 `strategy` 都相同却是两个不同信号的情况，因为 `open_positions` 的 key 本身
  就是 `(symbol, strategy)`），不需要额外的 tie-breaker。若未来同一 `(symbol, strategy)` 在同一
  tick 内出现多个信号（当前策略架构下不会发生，`positions.py` 里每个 `(symbol, strategy)` 同一时刻
  只有一个持仓状态），按到达顺序（信号生成时的原始顺序）作为次级排序键。

## 5. 测试矩阵

以下每一项都必须有对应单元测试（沿用 A83 `tests/unit/test_portfolio_ledger_report.py` 的测试风格：
用 `FakeEngine`/构造好的 `equity_curve`/`trades`，不依赖真实数据库）：

1. **forward-fill 不越界**：品种在 `[first_dt, last_dt]` 外，`margin_by_symbol[symbol]` 与
   `unrealized_pnl` 贡献恒为 `0`（复用/扩展 A83 已有的 `test_margin_not_carried_past_symbol_end`）。
2. **cluster 大小写一致**：`margin_by_cluster` 的品种归类对大小写不敏感（复用 A83 已有的
   `test_cluster_grouping_is_case_insensitive_in_build_ledger` 思路，应用到联合回放场景）。
3. **同时开仓资金竞争**：构造两个品种在同一 tick 都产生开仓信号、且总保证金上限只够满足其中一个，
   断言字典序在前的品种成交、在后的被拒且记录在 `blocked_opens`。
4. **保证金不足拒单**：单笔开仓所需保证金本身就超过 `margin_available`，断言拒绝且 `equity`/
   `margin_occupied_total` 不变。
5. **cluster cap 拒单**：某 cluster 已占用接近上限，新开仓会突破 `cluster_gross_cap`，断言拒绝，
   与现有 `PortfolioCoordinator.allow_open()` 的 `cluster_gross_cap` 分支行为一致。
6. **daily loss limit 行为**：构造当日亏损超过 `daily_loss_limit_pct` 的场景，断言
   `daily_loss_limit_active=True`、全部持仓被强平、当日剩余 tick 内新开仓全部被拒、次日
   `daily_loss_limit_active` 重置为 `False`。
7. **缺 bar 处理**：某品种在联合时钟的某个 tick 没有自己的 bar，断言该 tick 内：(a) 该品种的
   `margin_by_symbol` 沿用其最近一次已知值（在其 range 内），(b) 该品种没有任何新开仓/平仓判定
   被触发，(c) 其他品种的判定不受影响。
8. **数据末端截断品种的强制平仓**：品种在 `last_dt` 时仍有未平仓头寸，断言在其 range 结束时被
   按最后已知价格强制平仓、计入已实现 PnL、释放保证金，且不影响其他品种。
9. **先平后开顺序**：同一 tick 内某品种既有平仓信号又有另一品种的开仓信号，且开仓所需保证金恰好
   等于平仓释放的保证金量，断言开仓成功（验证平仓的保证金释放先于开仓判定生效）。
10. **`portfolio_risk="off"`/`sizing_model!="risk"` 时行为不变**：联合回放机制必须是新增的门控
    分支，默认关闭时现有 `_build_off_report()`/`_build_on_report()`（权重版）路径必须保持字节级
    不变（沿用项目一贯的"新开关默认关闭、行为不变"纪律）。

## 明确排除在 A85 范围外的问题

- 熔断触发后"禁新仓 vs 强平"的产品决策（阶段三，已在 portfolio-risk-fusion-design.md 里留白，
  本设计第 3 节延续现状——强平——作为阶段二的默认动作，不代表阶段三已经决定）。
- 连续合约复权/结算价涨跌停带（外部数据依赖，portfolio-risk-fusion-design.md 已记录为独立限制）。
- 实现本身（如何改写 `PortfolioEngine`/新增 `PortfolioLedger` 类的具体代码结构）——留给 Phase 2
  实现任务的 dev 阶段，本设计只约束语义，不约束代码组织方式。

## Acceptance Criteria（本设计文档自身的验收标准）

- [ ] 本文档覆盖用户列出的全部 5 个设计问题，每一项都给出明确决策 + 理由，不留"选 A 还是选 B"
      的开放式问句。
- [ ] 每一项决策都能追溯到现有代码的具体位置或现有测试的具体行为（不凭空发明与现状无关的新机制）。
- [ ] 测试矩阵覆盖用户列出的全部 7 类场景（forward-fill、cluster 大小写、资金竞争、保证金不足、
      cluster cap、daily loss limit、缺 bar/数据末端）。
- [ ] 明确排除阶段三（熔断动作）与外部数据依赖问题，不越界展开。
- [ ] `python tools/sync_check.py` 与 `python tools/sync_check.py --root examples/czsc_strategy` 通过
      （纯文档新增，不改变任何代码/测试，两个 gate 预期直接通过）。
