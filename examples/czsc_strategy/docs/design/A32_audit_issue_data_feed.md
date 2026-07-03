# A32 设计：审核问题数据接入 + A31 复核瑕疵修复

**任务号**：A32
**设计日期**：2026-07-03
**前置**：A31（audit_issue_diagnostics 只读诊断骨架，已交付并通过外部复核）
**输入依据**：A31 外部复核结论（2026-07-03）——骨架合格，但 H2/H3/M1 为 `unavailable`、H1/H4 为 `unknown`，且存在 3 个非阻塞瑕疵。

---

## 一、背景与目标

A31 建成了 H1/H2/H3/H4/M1 的只读诊断骨架，但当前报告全部处于"待喂数据"状态——**有秤，没称过东西**。
A32 的目标只有一句话：**把真实数据喂进去，让五个问题各自得到一个有数字、可判定的结论；同时修掉复核发现的 3 个瑕疵。**

**明确不做**（边界）：
- 不修复 H1-H4/M1 问题本身（那是拿到诊断数字之后的下一个任务）；
- 不改策略参数、买卖信号、风控与成交逻辑；
- 不发送任何委托、不调用任何交易接口、不连实盘；
- 不为了让报告"好看"筛选样本或调整诊断阈值；
- 不重构 A31 骨架（只做下述三处瑕疵修复 + 必要的数据接入层）。

---

## 二、方案

### W1. A31 复核瑕疵修复（3 处，先做）

| # | 瑕疵 | 修法 |
|---|------|------|
| W1a | H1 状态语义混淆：params 非空且干净时仍返回 `unknown`，与"未传参数"不可区分 | `detect_high_precision_weights`：params 为空 → `unknown`；params 非空且无可疑 → 新状态 `clean`；有可疑 → `detected`。同步更新既有测试断言 |
| W1b | H2 单位约定脆弱：`pnl_pct` 约定小数(-0.126)，误传百分数(-12.6)会被 ×100 放大且无告警 | `analyze_stop_loss_overshoot`：任一 `abs(pnl_pct) > 1.0` 时 raise `ValueError`，报错信息说明两种单位口径；新增测试锁定 |
| W1c | MD 报告未过敏感扫描：`write_markdown_report` 无 `contains_sensitive_data` 防护，直接调用时无保护 | 与 `write_json_report` 同规格：写盘前扫描，命中即 raise；新增测试锁定 |

### W2. 数据抽取层（新增 `diagnostics/extractors/`，全部只读）

新增独立抽取脚本，**只读现有产物、输出标准 JSON 到 `diagnostics/inputs/`**，不 import 策略运行时：

| 脚本 | 喂给 | 数据源（按优先级） | 输出 |
|------|------|-------------------|------|
| `extract_params.py` | H1 | ① `diagnostics/` 下 platform_optimization / sc_short_weight 系列产物中的当前生效权重 ② 策略文件中的组合权重常量（静态解析，不执行） | `inputs/params.json`：`[{name, value, source_file}]` |
| `extract_stop_pairs.py` | H2 | ① SimNow 观察日志/成交回报（A 系列已有产物）② 回测输出的 trade pairs | `inputs/stop_pairs.json`：`[{symbol, pnl_pct(小数), exit_reason, dt}]` |
| `extract_signal_history.py` | H3 | 回测/观察产生的信号记录（含"背驰""失效"字样的信号名） | `inputs/signal_history.json`：`[{dt, signal}]` |
| `extract_costs.py` | M1 | ① `BACKTEST_CONFIG`（run_*_backtest.py 静态解析）② vnpy engine 默认参数 ③ position/组合配置默认 | `inputs/costs.json`：`{config, engine_defaults, position_defaults}` |

约定：
- 每个 extractor 顶部声明数据源路径清单；源缺失时输出 `{"status": "source_missing", "tried": [...]}` 并以退出码 0 结束（诚实缺失，不伪造）；
- H2 的 `pnl_pct` 统一转为**小数**口径后落盘（对齐 W1b 校验）；
- H4 不需要 extractor：直接以 `--db-path` 指向实际行情 SQLite（`inspect_db.py` 已知路径），在运行剧本中给出。

### W3. 运行剧本与报告刷新

- 新增 `diagnostics/run_audit_diagnostics.ps1`（或 .py 包装）：依次跑 4 个 extractor → 以全部 inputs + `--db-path` 调 `audit_issue_diagnostics.py` → 生成当日 JSON/MD 报告。
- 更新 `NEXT_WORK.md`（A32 条目）、`WORK_LOG.md`（命令与结果原文）、`ACCEPTANCE.md`（若验收口径变化）。
- `CHANGELOG.md` 记一条，`VERSION` bump 至 0.2.0。

### W4. 接口/数据结构

- `inputs/*.json` 即上表 schema；诊断函数签名不变（H1 状态枚举新增 `clean`，属向后兼容扩展）。
- 报告新增顶层字段 `inputs_manifest`：记录每个 issue 的输入文件路径与记录数（0 也如实记），供审核对账。

---

## 三、边界与红线（继承 A 系列 + sync-guardian DoD）

1. 全部新增代码只读；静态检查"无交易调用"的既有测试必须继续覆盖 extractors（扩大扫描范围到 `diagnostics/extractors/*.py`）。
2. 敏感字段防护对 JSON 与 MD 两条写盘路径同规格生效（W1c）。
3. 诊断阈值（300bp 止损、高精度小数位判定等）不动。
4. 完成定义：代码 + VERSION bump + CHANGELOG 条目 + NEXT_WORK/WORK_LOG 更新同一提交；`python tools/sync_check.py` 通过后才能 `handoff.py next`。

---

## 四、验收标准（与 HANDOFF.md 同步，review 阶段照此逐条勾选）

见 `HANDOFF.md` "验收标准"节——两处内容一致，以 HANDOFF.md 为审核合同。

---

## 五、风险与备注

- **数据源可能真的不存在**（如止损成交对尚未积累）：extractor 以 `source_missing` 诚实落盘，对应 issue 保持 `unavailable` 不算失败——但必须在 WORK_LOG 记录 tried 路径，供人工确认"是真没有，不是没找对地方"。
- **H2 单位护栏是破坏性变更**：若历史调用方传百分数将开始报错——这是设计意图（宁可炸在开发期，不可静默放大 100 倍）。
- 本设计在无法执行 Python 的会话中产出，`sync_check.py` 门禁自验与 `handoff.py next` 交接由接棒方在本目录执行（见 HANDOFF"给下一棒的说明"第 0 条）。
