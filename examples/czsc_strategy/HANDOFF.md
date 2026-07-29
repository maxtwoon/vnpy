---
task: "A102 five-min trade freq + filter level generalization"
stage: dev
owner: code-agent
updated: 2026-07-29
deliverables:
  - docs/design/A102_trade_freq_5min_filter_generalization.md
  - diagnostics/five_min_feasibility_probe_20260729.md
  - diagnostics/five_min_param_calibration_20260729.md
  - diagnostics/a102_baseline_diff_rb888_20260729.md
  - diagnostics/a102_ac3_summary_20260729.md
  - tests/unit/test_a102_filter_level_generalization.py
blockers: []
---

## 背景与目标

将 `chan_strategy/` 的三级架构从「30分钟(交易) → 日线(过滤) → 4H(共振)」迁移为
「**5分钟(交易) → 30分钟(过滤) → 4H(共振)**」。级别间距 ×6/×8，层级关系更整齐。

前置探针（2026-07-29，5品种×16个月，RESEARCH-ONLY）已确认：数据覆盖充足、
5分钟笔/中枢生成正常（3~7笔/日，151~372中枢/品种）；主要风险是参数失配——
现有止损/timeout/结构失效阈值按30分钟（笔幅度1.4%~2.8%）校准，5分钟笔幅度中位数
仅0.52%~0.90%，直接改配置会导致止损偏宽2.2~6.8倍、timeout覆盖时间缩至1/6。

## 验收标准

以设计文档 §5 为准（AC1 基线字节一致 / AC2 过滤层泛化生效 / AC3 目标组合5品种
端到端 / AC4 参数profile有标定出处 / AC5 时序纪律单测 / AC6 含 realdb 实跑的
测试门禁 / AC7 同提交治理）。

## 给下一棒的说明

**下一棒：claude-cowork（review 阶段）**。dev 已完成 D1/D2/D3 全部施工，
请按设计文档 §5 逐条验收，每条结论引用下列证据：

| AC | 结论所需证据 |
|----|-------------|
| AC1 基线字节一致 | `diagnostics/a102_baseline_diff_rb888_20260729.md`（RB888 默认配置 diff=0，方法：`a102_baseline_diff.py`，old=stash 旧代码 / new=工作区） |
| AC2 过滤层泛化生效 | `tests/unit/test_a102_filter_level_generalization.py::test_backtest_engine_runs_with_minute_filter_freq`（60分钟过滤键存在且日线键缺席）；AC3 冒烟中 `[30分钟趋势]` 日志 |
| AC3 目标组合端到端 | `diagnostics/a102_ac3_summary_20260729.md`（5品种全跑通，5分钟/30分钟/240分钟键齐全，日线键按预期缺席）+ 5 份 `a102_ac3_<symbol>_20260729.json` |
| AC4 profile 有出处 | `diagnostics/five_min_param_calibration_20260729.md`（r=0.4361、×6 推导全记录）；`config.py::trade_freq_profiles` 注释引用该文件 |
| AC5 时序纪律单测 | `test_minute_filter_level_does_not_see_bar_before_it_closes`（镜像 4H no-lookahead 测试） |
| AC6 测试门禁 | `pytest tests/unit -q -m "not realdb"` 981 passed / 0 failed；`python -m pytest tests/unit -m realdb -q` 4 passed（260.5s 实跑） |
| AC7 同提交治理 | VERSION 0.2.59 + CHANGELOG 0.2.59 条目 + 本文件，同一提交 |

**偏离决策（dev 记录，详见决策记录）**：
1. AC3 窗口 3 个月冒烟（2025-01-01~2025-03-31）而非全窗口——算力约束；设计 §5 AC3
   未指定窗口，冒烟定位是"管线跑通 + 标签正确"，非绩效评估；
2. 新增 `filter_freq="off"` 显式关闭途径——两个既有测试（a87/more_coverage）依赖
   旧"非日线值=禁用"hack，H2 解耦后该 hack 失效，提供合法替代而非回退设计；
3. `ChanTimingStrategy` 的 `enable_daily_filter` 参数名保留（validation.py 等既有
   调用方），语义泛化为 filter_freq 级别，docstring 已注明。

**review 特别提示**：
- `max_bi_num=50` 红线（设计 §4.4-4）：dev 未放大该值——所有信号消费
  （zhongshu lookback=30bi、min_bi_count=5）均在 50 笔窗口内，5分钟下 50 笔≈1~2
  交易日仍满足；请复核此判断；
- 改动横跨 engine/positions/signals/sell_signals/config 5 文件，建议重点 diff
  `positions.py` 的 16 处参数消费点切换（语义等价性已由 AC1+AC6 双重验证）。

## 决策记录

- 2026-07-29 · A102 启动，design 落盘 · 依据：5分钟可行性探针通过（数据/结构可行，
  参数失配为主要风险）；设计采用「过滤层泛化 + 参数profile」两轨，而非简单改配置。
- 2026-07-29 · 日线合成路径保留不移除 · 理由：`regime_model="router"` 等消费方仍用
  日线 regime；过滤层泛化是"级别可配"，不是"去日线"。
- 2026-07-29 · AC3 改用 3 个月窗口冒烟 · 理由：单次会话算力约束（5分钟 bar 数为
  30分钟的 6 倍）；设计 AC3 未指定窗口，冒烟验证管线与标签，绩效评估留待后续任务。
- 2026-07-29 · 新增 filter_freq="off" · 理由：H2 门控解耦使 a87/more_coverage 两个
  既有测试依赖的"非日线值=禁用"hack 失效；显式 off 是合法的过滤器关闭语义，
  两处测试已迁移（行为等价：均无过滤层信号）。
- 2026-07-29 · `enable_daily_filter` 参数名保留 · 理由：validation.py 等 3+ 处既有
  调用方按名传参；改名是纯装饰性变动且扩大 diff，语义已在 docstring 注明泛化。
- 2026-07-29 · `max_bi_num=50` 未放大 · 理由：全部信号消费（zhongshu lookback=30、
  min_bi_count=5）均在 50 笔窗口内闭合；放大只会拖慢引擎，无行为收益。

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-29 | 人 → claude-cowork | → design | A102 任务启动（依据当日 5分钟可行性探针与会话内多级别联立对比分析） |
| 2026-07-29 | claude-cowork → code-agent | design → dev | A102 design 落盘：过滤层泛化(D1)+参数profile(D2)+标签一致(D3)；施工清单H1~H7、红线、AC1~AC7 验收标准齐备 |
