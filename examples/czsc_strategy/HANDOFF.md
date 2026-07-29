---
task: "A102 five-min trade freq + filter level generalization"
stage: done
owner: claude-cowork
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

**A102 review 结论：通过（review → done）**。claude-cowork 已按设计文档 §5
AC1~AC7 逐条独立复核，全部达成；无阻断问题，4 条非阻断观察项记录在案。

| AC | 结论 | 复核方式 |
|----|------|---------|
| AC1 基线字节一致 | ✅ | reviewer 重跑 `a102_baseline_diff.py diff old new`，差异条数 0（非仅采信 dev 记录） |
| AC2 过滤层泛化生效 | ✅ | 单测断言 60分钟过滤键存在且日线键缺席；AC3 冒烟日志 `[30分钟趋势]`；engine diff 确认过滤层合成三分支 + 标签与数据同源 |
| AC3 目标组合端到端 | ✅ | `a102_ac3_summary_20260729.md`：5/5 品种跑通、三级键齐全、日线键按预期缺席、RESEARCH-ONLY 横幅齐全；5 份 JSON 落盘 |
| AC4 profile 有出处 | ✅ | 脚本比对 `config.py` 14 个键值与 `five_min_param_calibration_20260729.json` 全部一致（r=0.4361、×6 推导）；白名单 fail-closed 有单测 |
| AC5 时序纪律单测 | ✅ | `test_minute_filter_level_does_not_see_bar_before_it_closes` 镜像 4H no-lookahead 纪律；engine 增量更新 `dt <= bar.dt` 逐行确认 |
| AC6 测试门禁 | ✅ | reviewer 重跑 7 个关键测试文件 50 passed（含 a102 新增 9 条、a87、两个 no-lookahead）；全量 981 + realdb 4（260.5s）采信 dev 实跑记录 |
| AC7 同提交治理 | ✅ | `git show --stat HEAD`：VERSION 0.2.59 + CHANGELOG 条目 + 5 代码文件 + 4 测试文件 + 设计文档 + 16 份 diagnostics 全在同一提交；`sync_check.py` PASS |

**对 dev 两个复核提示的回应**：
1. `max_bi_num=50` 未放大 —— **认可**。已核实全部信号消费（zhongshu lookback=30、
   min_bi_count=5、risk_control recent）在 50 笔窗口内闭合，放大无行为收益；
2. positions.py 16 处 `get_strategy_param()` 切换 —— diff 逐处审查，默认值下与
   `STRATEGY_CONFIG[...]` 语义等价，且 AC1 字节一致实证兜底。

**非阻断观察项（不改代码，供后续任务参考）**：
1. 用户删除 base config 某键时，旧代码个别消费点有回退逻辑（timeout_1sell 回退
   1buy），新代码 `get_strategy_param` 会 KeyError——仅用户手改 config 的边缘场景；
2. `filter_freq` 非法值（错别字）被 `_freq_to_minutes` 静默当 30 分钟——pre-existing
   行为（trade_freq 同款），设计未要求校验；
3. 设计 §6 风险 2/3 建议的成本占比/降级统计未在 summary md 显式列出，但 5 份 JSON
   含 `round_trip_cost_pct_per_trade`，且 label_check 三级键齐全=无降级发生；
4. AC3 为 3 个月冒烟而非全窗口——dev 决策记录已载明，AC3 条文未指定窗口，可接受；
   **全窗口绩效评估留待后续任务**（本任务不产绩效结论）。

**任务终态**：目标组合「5分钟(交易) → 30分钟(过滤) → 4H(共振)」已可经
`STRATEGY_CONFIG` 三个键启用；默认配置（30分钟/日线）基线字节一致、测试全绿。
后续建议任务：全窗口 5 品种 5分钟组合绩效评估（RESEARCH-ONLY），重点观察
手续费占比与 max_bi_num 在长样本下的充分性。

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
- 2026-07-29 · review 通过 · 依据：AC1~AC7 逐条独立复核全达成（AC1 重跑 diff=0、
  AC4 脚本比对 14 键值一致、AC6 关键 50 条重跑全绿）；4 条非阻断观察项记录，
  全窗口绩效评估留作后续任务。

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-29 | 人 → claude-cowork | → design | A102 任务启动（依据当日 5分钟可行性探针与会话内多级别联立对比分析） |
| 2026-07-29 | claude-cowork → code-agent | design → dev | A102 design 落盘：过滤层泛化(D1)+参数profile(D2)+标签一致(D3)；施工清单H1~H7、红线、AC1~AC7 验收标准齐备 |
| 2026-07-29 | code-agent → claude-cowork | dev → review | A102 dev 完成：D1/D2/D3 全施工；AC1 RB888 diff=0；AC6 981+realdb4 全绿；AC3 五品种冒烟通过；profile 值有标定出处；偏离3项已记决策记录 |
| 2026-07-29 | claude-cowork → claude-cowork | review → done | A102 review 通过：AC1~AC7 全达成（AC1 重跑diff=0、AC4 键值比对一致、AC6 关键50条重跑全绿），4条非阻断观察项记录，全窗口绩效评估留后续任务 |
