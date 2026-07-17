# A89 — 熔断强平（daily loss limit 触发后的强制平仓）设计（算法设计任务，不含实现代码）

## 状态与定位

本文档回答用户在 A87 前置提问中明确搁置的问题："daily loss limit 触发后，是只禁新仓，还是同时强平"——
A87 已实现"只禁新仓"（`chan_strategy/portfolio_ledger.py` 的 `daily_loss_limit_active` 门控），本设计补上
"强平"这一半，作为独立的 A89 实现任务的前置设计。产出物是本文档本身，不是代码。

## 关键发现：强平原语已经存在，且从未被调用

`ChanTimingStrategy.flatten_all_positions(price, dt, reason)`（`positions.py:2122`）：

```python
def flatten_all_positions(self, price: float, dt: datetime, reason: str = "flatten") -> None:
    """Close all open positions immediately (used by portfolio daily loss limit)."""
    for pos in self.positions:
        if pos.pos > 0:
            pos._close_long(price, dt, reason)
        elif pos.pos < 0:
            pos._close_short(price, dt, reason)
```

这个方法**已经存在**（复用现有 `_close_long`/`_close_short`，与既有平仓、PnL 记账、`trades`/`pairs` 记录逻辑
完全一致，不需要发明任何新的平仓/记账算法），但代码库里**没有任何调用点**（`grep` 确认为零）——推测是
更早的任务（P8b/A48 权重版 `PortfolioCoordinator` 时期）预先写好，但当时的 `PortfolioCoordinator._flatten_all()`
（`portfolio_engine.py:282`）操作的是协调器自己的权重敞口簿记，从未真正调用到 engine 层，所以这个方法
被遗忘了。

**这意味着 A89 不需要新建平仓原语**——需要设计的只是：联合驱动器在什么时刻、对哪些品种、用什么价格
调用 `engine.strategy.flatten_all_positions(price, dt, reason)`。这把 A89 的实现复杂度从"新增引擎能力"
降低为"正确的驱动器时序控制"，与 A87 本身的复杂度量级接近，不是一个新的大类问题。

## 需要回答的四个设计问题

### 1. 强平原语的形态

**决策：直接复用 `ChanTimingStrategy.flatten_all_positions()`，不新增任何 `BacktestEngine`/`Position`
层的新方法。** 联合驱动器（`PortfolioEngine._build_joint_report()`）在检测到 `daily_loss_limit_active`
从 `False` 变为 `True` 的那一刻，对触发品种调用 `engines[symbol].strategy.flatten_all_positions(...)`；
对其余品种的处理见问题 3（时序问题）。

### 2. 用哪个价格强平

**决策：用触发时刻该品种自己当前 bar 的收盘价（`bar.close`），与止损/超时平仓已有的"当根 bar 立即
按 `close` 价平仓，不delay到下一根 bar"惯例完全一致**（对照 `positions.py:733-750` 止损/超时平仓都是
`_close_long(price, dt, "止损")`，这里的 `price` 就是 `update()` 收到的当根 bar 收盘价，不是下一根开盘
价）。强平是风险动作，不是新开仓，理应遵循与止损/超时相同的"立即执行"惯例，不应该采用新开仓
"延迟一根 bar 成交"的惯例。

### 3. 强平的作用范围与跨品种时序（本设计的核心难点）

**背景矛盾**：daily loss limit 是在某个品种 X 处理到时间戳 T 时，由共享 `PortfolioLedger` 检测到的
（`portfolio_ledger.py:141` `check_daily_loss_limit()`）。但联合驱动器是逐品种、逐 tick 推进的
（`portfolio_engine.py` 的 `_build_joint_report()` 按 `sorted(symbol)` 顺序处理同一时间戳的品种）——
在 T 这一刻，可能只有品种 X 自己的生成器已经推进到 T，其余品种 Y/Z 的生成器可能仍停留在 T 之前的某个
时间戳（例如 Y 在这一分钟没有自己的 bar）。

**决策：强平不是"瞬间对所有品种生效"，而是"每个品种在自己的生成器到达触发时刻或之后最近一次
`pre_open` yield 时，才对该品种执行强平"**——具体机制：

- 驱动器维护一个 `flatten_pending: set[symbol]` 集合。当 `ledger.check_daily_loss_limit()` 在处理品种
  X 的 tick 时首次触发（`daily_loss_limit_active` 从 False 变 True），立即：
  1. 对 X 自己调用 `flatten_all_positions(bar.close, current_dt, "daily_loss_limit_flatten")`（X 已经
     在这个时间点，可以立即执行，不需要等待）。
  2. 把其余所有品种（包括尚未开始处理这一 tick 的品种）加入 `flatten_pending`。
- 驱动器主循环每次处理某个品种 Y 的下一个 `"pre_open"` yield 时，先检查 `Y in flatten_pending`：如果是，
  在处理这个 `"pre_open"` 之前，先用 **Y 自己这个 tick 的 `bar.close`** 强平 Y 的持仓（不是回溯去用
  X 触发时刻的价格——那是"未来函数"对 Y 而言，Y 自己在那个时间戳可能根本没有 bar），然后把 Y 从
  `flatten_pending` 移除。
- **为什么不"瞬间强平所有品种"**：这会要求在品种 Y 自己的生成器还没推进到触发时间戳之前，从外部修改
  Y 的 `Position` 状态——这违反了整个项目一贯遵守的"无未来函数"原则（每个品种的回测决策只能基于该
  品种自己已知的、到当前 bar 为止的信息）。用"品种自己下一次到达时才强平"的方案，代价是同一个组合层
  事件在不同品种身上生效的物理时刻略有先后（毫秒级 tick 粒度下通常就是下一根 bar），但这正是"联合
  回放但保留每个品种自己的数据节奏"这一架构本身的题中之义，不是缺陷。
- **是否需要在 `blocked_opens` 之外，新增一个 `flat_events` 诊断列表**：是，参照
  `PortfolioCoordinator.flat_events`（`portfolio_engine.py:124`）的既有字段命名和形状
  （`dt`/`symbol`/`strategy`/`open_dt`/`open_price`/`flat_price`），联合版本的 `flat_events` 记录每一笔
  被强平仓位的品种、strategy 名、开仓价、强平价、强平原因。

### 4. 重新触发/解除机制

**决策：复用 A87 已经实现的 `daily_loss_limit_active` 每日重置逻辑，不新增额外的重新触发规则。**
`ledger.update_trading_day()`（`portfolio_ledger.py:111`）已经在交易日切换时把 `daily_loss_limit_active`
重置为 `False`——这个重置本身不变。A89 只在"触发的那一刻"追加"强平"这一个动作，不改变"何时解除禁止
新仓"的既有语义。也不需要为强平本身设计单独的"每天只强平一次"逻辑——因为强平只在
`daily_loss_limit_active` **从 False 变为 True 的那一个瞬间**触发一次（不是每个 tick 都检查是否要强
平），触发之后该状态保持 `True` 直到次日重置，其间不会重复强平已经空仓的品种。

## 明确排除在 A89 范围外的问题

- 单品种/cluster 保证金上限触发时是否也要强平：**不**——A85/A87 已经明确"熔断"（circuit breaker）
  概念专指 daily loss limit 这一回撤类风控，单品种/cluster 保证金上限只是开仓前的准入约束，不是回撤
  熔断，触发后只是"拒绝新开仓"（A87 已实现），不涉及强平，本设计不改变这一点。
- 强平后是否允许当日剩余时间"重新开仓"（例如权益回升后解除熔断）：不在本设计讨论范围，沿用 A87
  已有的"当日剩余时间禁止新仓，次日重置"语义，不发明日内提前解除规则。
- 实现本身（`_build_joint_report()` 里具体怎么改代码、`flatten_pending` 集合的具体数据结构选择）——
  留给 A89 实现任务的 dev 阶段，本设计只约束语义。

## Acceptance Criteria（本设计文档自身的验收标准）

- [ ] 覆盖用户提出的 4 个设计问题，每项都有明确决策 + 理由，不留开放式问句。
- [ ] 明确记录 `ChanTimingStrategy.flatten_all_positions()` 已存在且无调用点这一发现，及其对实现复杂度
      的影响。
- [ ] 强平时序方案明确解决"品种间进度不同步"的无未来函数问题，不采用"瞬间强平所有品种"的简化方案。
- [ ] 明确排除单品种/cluster cap 触发强平、日内提前解除熔断这两项，避免范围蔓延。
- [ ] `python tools/sync_check.py` 与 `python tools/sync_check.py --root examples/czsc_strategy` 通过
      （纯文档新增，预期直接通过）。
