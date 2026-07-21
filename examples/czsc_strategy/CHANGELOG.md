# Changelog — czsc_strategy 诊断工作流

版本单一真相：`VERSION` 文件。每个对外可见改动 = 代码 + 版本 bump + 本文件一条 + 相关文档，同一提交完成。

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
