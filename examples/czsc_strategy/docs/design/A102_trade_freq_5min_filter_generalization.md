# A102 — 5分钟交易级别 + 过滤层泛化（30分钟替换日线）设计

- 任务：A102
- 阶段：design（claude-cowork）
- 日期：2026-07-29
- 前置证据：`diagnostics/five_min_feasibility_probe_20260729.md` / `.json`（只读探针，RESEARCH-ONLY）
- 关联分析：本会话对 `czsc_multi_timeframe_strategy.py`（legacy）与 `chan_strategy/` 的多级别联立对比

---

## 1. 背景与目标

当前 `chan_strategy/` 的三级架构为：交易级别 `trade_freq="30分钟"`（主分析）、过滤层
`filter_freq="日线"`（趋势门禁）、共振层 `resonance_freq_4h="240分钟"`（A44，默认 off）。

目标级别组合改为：**5分钟（交易）→ 30分钟（过滤）→ 4小时（共振）**。5分钟→30分钟
间距 ×6、30分钟→4H 间距 ×8，层级关系比现状更整齐（现状日线与 4H 的父子关系随
`daily_agg` 模式变化，且跨夜盘聚合）。

探针结论（2026-07-29，5 品种 × 16 个月）：

- 数据覆盖充足：5分钟 bar 1.4万~3.4万根/品种，315 个交易日；
- 结构生成正常：947~2190 笔（3~7 笔/日）、151~372 个中枢（segment 口径）；
- **参数失配是主要风险**：5分钟笔幅度中位数 0.52%~0.90%，现有止损/超时/结构失效
  阈值按 30 分钟（笔幅度 1.4%~2.8%）校准，直接改配置会导致止损相对结构尺寸偏宽
  2.2~6.8 倍、timeout 覆盖时间缩至 1/6。

## 2. 范围

**做：**

1. **D1 过滤层泛化**：解除过滤层对日线的硬编码，使 `filter_freq` 真正生效
   （"日线" / "30分钟" 等分钟级别均可），默认 "日线" 保持基线字节一致；
2. **D2 5分钟级别参数 profile**：建立按交易级别分组的参数覆盖机制，并给出
   5分钟 profile 的标定值（标定依据须落盘为诊断报告）；
3. **D3 级别标签一致性**：过滤层信号标签、门控、日志全部跟随 `filter_freq`，
   消除"数据是日线、标签是30分钟"类错位。

**不做（明确非目标）：**

- 三级分仓、跨级别风控（破高级别下轨强平）——属后续独立任务；
- `resonance_freq_4h` 机制本身（保持 A44 现状，仅验证其在 5分钟交易级别下可用）；
- 日线 CZSC 的移除——日线信号生成路径保留（`regime_model="router"` 等消费方仍在）；
- 任何盈利能力结论。本任务只交付"可运行 + 基线兼容 + 参数有依据"。

## 3. 现状硬编码点（dev 的施工清单）

| # | 位置 | 现状 | 改造 |
|---|------|------|------|
| H1 | `backtest_engine.py` L503 | 过滤层 bar 合成写死 `Freq.D`（含 `daily_agg` 分支） | 按 `filter_freq` 走 `_freq_name_to_czsc_freq` / `_freq_to_minutes`；日线时保留 `daily_agg`/`night_session_start_hour` 逻辑 |
| H2 | `backtest_engine.py` L533–535 | `enable_daily_filter = filter_freq == "日线"` | 改为"过滤层 CZSC 可用即启用"（与日级别解耦），预热不足自动降级的行为保留 |
| H3 | `backtest_engine.py` L554–555, L698–708 | 日线 CZSC 增量更新变量名 `daily_bar_idx` 等 | 语义不变，命名可泛化；时序纪律 `dt <= bar.dt` 必须原样保留 |
| H4 | `backtest_engine.py` L721–723 | 过滤层 CZSC 固定按日线合成，信号却用 `filter_freq_name` 打标签 | 数据与标签同源：过滤层 bar 由 `filter_freq` 合成，标签即 `filter_freq` |
| H5 | `positions.py` L74–161 | `_daily_trend_filter_signals` / `_higher_level_filter_signals` / `_resonance_holds` 字面量 `"日线"` | 级别标签参数化为 `filter_freq`；"off" 默认值路径字节一致 |
| H6 | `positions.py` L1780–1782, L1821–1838 | `enable_daily_filter` 门控与 `_log_daily_trend` 写死 `"日线"` 键 | 跟随 `filter_freq`；`regime_model="router"` 的日线 regime 语义需明确（见 5.3 开放问题） |
| H7 | `config.py` L48–54 等 | timeout/止损/结构失效阈值按 30 分钟校准 | D2 profile 机制覆盖 |

## 4. 设计

### 4.1 D1 过滤层泛化

- `filter_freq` 语义升级为"环境过滤级别"，取值 `"日线"`（默认）或任意
  `_freq_to_minutes` 支持的分钟级别（"5分钟"/"15分钟"/"30分钟"/"60分钟"/"120分钟"/"240分钟"）；
- 引擎启动时：日线 → 走现有 `Freq.D` + `daily_agg` 合成路径；分钟级别 → 走
  `resample_bars(bars, freq_obj, minutes)`（与交易级别/4H 同款）；
- 过滤层 CZSC 的初始化、预热对齐（`dt <= warmup_dt`）、主循环增量更新
  （`dt <= bar.dt`，防未来函数）三个环节对所有级别共用同一套逻辑；
- 信号标签 = `filter_freq`（`get_all_signals(czsc_filter, filter_freq_name)`），
  消费端 `positions.py` 所有 `"日线"` 字面量改为读 `STRATEGY_CONFIG["filter_freq"]`；
- **不变式**：`filter_freq="日线"` 且其余配置默认时，回测输出与基线字节一致。

### 4.2 D2 参数 profile 机制

- 新增配置键 `"trade_freq_profiles": { "<trade_freq>": { ...覆盖键... } }`，
  引擎在 `trade_freq` 命中 profile 时应用覆盖；未命中或键缺失 = 现状值；
- 可覆盖键限定为：`timeout_*`、`stop_loss_*`、`structural_invalidation_pct`、
  `trailing_start_bp`、`trailing_drawback_pct`。**不允许** profile 覆盖信号逻辑、
  成本、仓位比例（避免 profile 成为第二配置中心）；
- 5分钟 profile 的具体数值不在本设计中写死：dev 阶段先跑一个**标定探针**
  （基于 `five_min_feasibility_probe` 的笔幅度分布，按"止损 ≈ k × 笔幅度中位数，
  k 与 30 分钟基线一致"的原则推导，k 值与推导过程写入
  `diagnostics/five_min_param_calibration_<date>.md`），再把推导出的值填入 profile；
- 禁止"凭感觉调参"：profile 每个值必须能在标定报告中找到出处。

### 4.3 D3 标签一致性

- 全仓 grep 验收：`chan_strategy/` 内不再存在与过滤层相关的 `"日线"` 字面量
  （保留的例外：`regime` 路由的日线语义、`daily_agg` 日线合成、注释）；
- `_log_daily_trend` 改名/泛化为按 `filter_freq` 记录，日志键与信号键同源。

### 4.4 时序与兼容性约束（红线）

1. 高级别 CZSC 只吃 `dt <= 当前交易bar.dt` 的已完结 bar（防未来函数）——现有
   L698–708 模式原样保留到新级别；
2. 信号当根产生、下一根开盘价成交的"延迟一根 bar"纪律不变；
3. 默认配置（`trade_freq="30分钟"`, `filter_freq="日线"`）输出与基线**字节一致**；
4. czsc `max_bi_num=50` 截断在 5 分钟下语义变化（50笔≈1~2 个交易日 vs 30分钟的
   ~1 个月）：dev 须确认所有消费 `bi_list` 的信号在 5 分钟下不因回看窗口缩短而
   失效或行为异常，结论写入 dev 自测记录；
5. 诊断/报告新增产物遵守 RESEARCH-ONLY 横幅门禁（`tools/sync_check.py`）。

## 5. 验收标准（review 阶段的合同，逐条可判定）

- [ ] **AC1 基线兼容**：默认配置下对 ≥1 个品种（建议 RB888）跑基线回测，
  输出与基线字节一致（沿用 `diagnostics/baseline_20260621_vs_current_diff_*` 的
  diff 方法），diff 结果落盘；
- [ ] **AC2 过滤层泛化生效**：`filter_freq="30分钟"` 时，引擎日志出现
  "K线合成: N根1分钟 → M根30分钟"（过滤层），信号字典含 `30分钟_D1BI_方向V260615_*`
  键，且不存在过滤层数据与标签错位；
- [ ] **AC3 目标组合端到端**：`trade_freq="5分钟"` + `filter_freq="30分钟"` +
  `resonance_filter="daily_4h"` 在 5 品种（AP/RB/SC/A/ZN 888）上完整跑通不报错，
  报告落盘（RESEARCH-ONLY 横幅齐全）；
- [ ] **AC4 参数 profile 有据**：`trade_freq_profiles` 中 5分钟 profile 的每个值
  在 `diagnostics/five_min_param_calibration_<date>.md` 中有推导出处；
  未命中 profile 的级别行为与现状一致；
- [ ] **AC5 时序纪律**：新增/修改的单测覆盖"过滤层 bar 未完结不进入 CZSC"
  （`dt <= bar.dt`），测试落盘并通过；
- [ ] **AC6 测试门禁**：`pytest tests/unit -q -m "not realdb"` 全绿；且因本任务
  触及 `chan_strategy/positions.py`，必须附 `python -m pytest tests/unit -m realdb -q`
  的实跑输出（AGENTS.md realdb 守则）；
- [ ] **AC7 治理**：代码 + VERSION bump + CHANGELOG 条目 + 本设计文档状态更新在
  同一提交；`python tools/sync_check.py` 通过。

## 6. 风险与开放问题

1. **`regime_model="router"` 的日线语义**：router 用日线 regime 选边。过滤层泛化后
   router 应继续用日线（独立合成）还是跟随 `filter_freq`？设计倾向：**保持日线
   独立**（日线合成路径保留），dev 若发现耦合过深可在决策记录中说明后跟随
   `filter_freq`，但必须在 HANDOFF 决策记录中写明；
2. **5分钟噪声 vs 成本**：笔幅度 0.5%~0.9% 级别上，往返成本（2×手续费+滑点）占比
   显著高于 30 分钟。本任务不评估盈利性，但 AC3 报告中应附成本占比统计供后续
   决策；
3. **warmup 语义**：`warmup_bars` 以交易 bar 计，5 分钟下同样根数只覆盖 1/6 时间，
   过滤层/共振层预热不足自动降级的触发频率会上升——AC3 报告中须统计降级发生次数；
4. **max_bi_num 截断**（红线4）若发现实质影响，优先放大 `max_bi_num` 而非改信号
   逻辑，偏离须记入决策记录。

## 7. 交接

design 完成后 `python tools/handoff.py next --summary "A102 设计文档落盘"` 推进至
dev（owner: code-agent）。review 打回路径：设计问题 → design；实现偏离 → dev。
