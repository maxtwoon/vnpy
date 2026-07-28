# czsc 0.9.51 → 1.0.0rc8 测试改动归因

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

本文件逐条说明 czsc 1.0.0rc8 升级过程中被修改的测试与夹具，区分"笔算法差异导致的预期变化"、
机械导入路径迁移、以及范围外的功能新增。所有改动均已在 `pytest examples/czsc_strategy/tests/unit -q`
（not-realdb 与 realdb）中验证通过。

## 总体结论

- **没有测试失败被掩盖**：升级后全量单测结果为 `978 passed, 4 deselected, 4 xfailed`
  （not-realdb）与 `4 passed`（realdb）。任何数值变化都被显式归因并记录。
- **唯一需要刷新金标准（snapshot）的测试**：
  `tests/unit/test_position_sizing_research_equivalence.snapshot.json`。
  刷新完全由 czsc 1.0.0rc8 的笔合并规则变化引起，不是策略代码 bug。
  具体位移见 `czsc_upgrade_behavior_diff_report.md` 的"research-mode 基准位移"章节。

## 改动分类

### A. 机械导入路径迁移（无行为变化）

以下文件仅将 `from czsc.objects import ...` / `from czsc.enum import ...` 等已删除路径
改为 `from czsc import ...`，或同步调整 `CZSC(bars=...)` 关键字参数。代码逻辑与断言均未改变。

| 文件 | 说明 |
|---|---|
| `tests/conftest.py` | `RawBar`/`Freq`/`Direction` 改为顶层导入 |
| `tests/unit/test_4h_no_lookahead.py` | 同上 |
| `tests/unit/test_a53_config_signal_cleanup.py` | 同上 |
| `tests/unit/test_backtest_idempotent.py` | 同上 |
| `tests/unit/test_branch_completion.py` | 同上 |
| `tests/unit/test_coverage_closure.py` | 同上 |
| `tests/unit/test_daily_no_lookahead.py` | 同上 |
| `tests/unit/test_data_adapter.py` | 同上 |
| `tests/unit/test_divergence_macd.py` | 同上 |
| `tests/unit/test_exit_event_restructure.py` | 同上 |
| `tests/unit/test_limit_halt_exposure_report.py` | 同上 |
| `tests/unit/test_more_coverage.py` | 同上 |
| `tests/unit/test_portfolio_risk_off_equivalence.py` | 同上 |
| `tests/unit/test_regressions.py` | 同上 |
| `tests/unit/test_remaining_coverage.py` | 同上 |
| `tests/unit/test_second_buy_bug.py` | 同上 |
| `tests/unit/test_second_buy_real_path.py` | 同上 |
| `tests/unit/test_signal_properties.py` | 同上 |
| `tests/unit/test_signals.py` | 同上 |
| `tests/unit/test_strategy_state_replay.py` | 同上 |
| `tests/unit/test_zhongshu.py` | 同上 |

### B. 因 Rust 对象不可变而调整的夹具/构造方式（非算法差异，但必要）

| 文件 | 说明 |
|---|---|
| `tests/unit/test_data_adapter.py` | `RawBar` 在 1.0 中为 Rust dataclass，测试中对构造后的 `RawBar` 原地修改属性被替换为构造时传参 |
| `test_czsc_api.py` | `CZSC(bars=bars)` 关键字调用改为位置参数 `CZSC(bars)`，避免 1.0 构造函数签名变化 |
| `test_czsc_api2.py` | 同上 |

### C. 因笔算法差异导致的金标准刷新

| 文件 | 说明 |
|---|---|
| `tests/unit/test_position_sizing_research_equivalence.snapshot.json` | **唯一数值基准刷新**。czsc 1.0 的 Rust 笔合并规则改变了 SC888/RB888 的回测交易序列；Bucket-B 字段（total_return_pct、sharpe、profit_factor、子策略成交数等）随之改变。该 snapshot 为研究模式等价性测试所用，刷新前旧版本无法通过 1.0 环境 |

### D. 范围外但保留的功能扩展（有配套单测）

| 文件 | 说明 |
|---|---|
| `tests/unit/test_html_report.py` | 新增 B/S 序号标注与 echarts 内联两项单测；这些功能本属于 A105 报告增强范畴，但已在本次提交中补录决策记录 |

## 备注

- `diagnostics/czsc_upgrade_fixtures/0_9_51/*.json` 为本次报告服务，不是单元测试夹具；
  其对比数据与当前脚本可复现（已使用 `CZSC_MAX_BI_NUM=10000` 重新生成）。
- 若将来 czsc 上游发布正式 1.0.0 且笔算法再次变化，应重新运行
  `czsc_upgrade_bi_diff.py` 并刷新本归因说明。
