<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

# Codex 独立审核报告：czsc_strategy 0.2.44

**审核对象**：`D:\repo\vnpy\examples\czsc_strategy`  
**审核日期**：2026-07-26  
**审核范围**：`AI_REVIEW_REPORT_2026-07-26.md`、`CHANGELOG.md` 0.2.43/0.2.44、`chan_strategy/`、`README.md`、`VERSION`、`run_formal_evaluation.py`、`tests/unit/`、`tools/handoff.py`、关键诊断配置文件。  
**结论**：0.2.43 对原 14 条中危问题的修复总体真实，但存在 3 个 follow-up 缺口；本次已修复并 bump 到 0.2.44。当前未发现仍需立即修复的 🟠 中危或 🔴 高危问题。  
**最终评分**：82/100（B，良好）。本报告为工程质量审核，不构成交易建议，也不构成策略盈利能力证明。

## 十维度评分

| 维度 | 分数 | 结论 |
|---|---:|---|
| D1 信号构建与择时逻辑自洽 | 8 | 生产入口统一为 `sell_signals.get_all_signals()`；次级别确认死语义已删除/澄清。 |
| D2 组合构建、风险预算与风控一致性 | 8 | 新增持久性 `max_drawdown_breaker_pct`，接入联合回放强平和阻断；默认禁用且文档说明范围。 |
| D3 参数/阈值跨载体一致性 | 8 | 原 0.2.43 仍遗留关键 fallback，本次在 `positions.py`/`portfolio_engine.py`/`portfolio_ledger.py` 补齐硬索引并加 AST 回归。 |
| D4 回测/评估严谨性 | 7 | 成本/样本污染披露和 formal 单品种范围说明较清楚；仍无干净 OOS 通过证据。 |
| D5 数据假设处理 | 8 | 期货换月、涨跌停、夜盘等有较完整建模/披露；真实库抽样未在本次复跑。 |
| D6 指标定义与术语统一 | 8 | “确认”三义、score 装饰字段、zhongshu 与标准差异已披露；二买 xfail 原因本次进一步修正。 |
| D7 市场环境适配与声明 | 8 | README 新增适用前提/失效环境，regime/ATR chop 默认关闭原因可见。 |
| D8 可追溯性与单一真值源 | 8 | VERSION/CHANGELOG 已到 0.2.44；handoff wrapper 断裂已修复并加回归。 |
| D9 透明度与可审计性 | 8 | 无黑箱；凭据样例已占位；本次报告记录未通过完整测试的环境原因。 |
| D10 合规与风险提示充分性 | 9 | RESEARCH-ONLY 横幅、只读门禁、敏感字段扫描机制保留。 |
| **合计** | **82/100** | **未发现剩余中高危项** |

## 本次独立发现并修复

1. **🟠 D3：关键风控 fallback 补漏**
   - 证据：0.2.43 后 `chan_strategy/positions.py` 仍对 `sizing_model`、`risk_per_trade_pct`、`max_margin_pct`、`limit_halt_model` 使用 `.get(key, 默认值)`；`portfolio_engine.py`/`portfolio_ledger.py` 也存在组合风控默认值 fallback。
   - 修复：`chan_strategy/positions.py:665`、`:938`、`:977`、`:993`、`:1040`、`:1041`、`:1092`、`:1120`、`:1162`、`:1956` 改为单一真值硬索引；`chan_strategy/portfolio_engine.py:135`、`:136`、`:137`、`:138`、`:908`、`:909` 等同类修复；`chan_strategy/portfolio_ledger.py:76` 先合并基线配置再硬索引。
   - 回归：`tests/unit/test_a53_config_signal_cleanup.py:44` 新增 AST 扫描。

2. **🟠 D8：handoff wrapper 被 sync_check thin wrapper 破坏**
   - 证据：`python tools/handoff.py status` 原报 `ImportError: cannot import name '_load_config' from 'sync_check'`。
   - 修复：`tools/handoff.py:24` 改为直接导入根级 `tools/sync_guardian/sync_check.py` 权威引擎。
   - 回归：`tests/unit/test_handoff_tool.py:9` 子进程验证 `handoff.py status`。

3. **🟡 D6/D9：4 个 xfail 的原因披露不够精确**
   - 证据：`tests/unit/test_second_buy_real_path.py` 中第 4 个 xfail 走 `SignalValidator`，内部使用生产 `sell_signals.get_all_signals()`，不能简单归为 legacy 路径。
   - 修复：`tests/unit/test_second_buy_real_path.py:30` 区分前 3 个 legacy xfail 与第 4 个生产聚合入口但“夹具未覆盖二买状态”的 xfail；`CHANGELOG.md:21` 同步澄清。
   - 复核：`python -m pytest tests/unit/test_second_buy_real_path.py -q --runxfail` 显示失败原因是锚点价格/未覆盖二买确认/验证器报“样本未覆盖二买路径”，未发现生产路径在已覆盖结构下错误输出二买。

4. **🟡 测试环境耦合**
   - 证据：`tests/unit/test_portfolio_ledger_report.py::test_run_per_symbol_engines_sets_risk_sizing` 会误探测本机默认 SQLite 路径并因权限失败。
   - 修复：`tests/unit/test_portfolio_ledger_report.py:224` 显式传入不存在的 unit-test DB 路径，测试只验证 sizing override。

## 原 14 条 🟠 问题逐条核实

| # | 结论 | 核实依据 |
|---:|---|---|
| 1 次级别确认死配置 | 真正解决 | `base_freq`/`confirm_freq` 已从 `STRATEGY_CONFIG` 删除；README `:30` 明确固定 1m 重采样且无次级别确认实现。 |
| 2 组合回撤熔断缺失 | 真正解决 | `portfolio_ledger.py:184` 实现持久回撤熔断；`portfolio_engine.py:842` 接入强平；`test_a87_joint_replay.py` 覆盖默认禁用、触发、持久化、优先级。 |
| 3 默认/正式评估无组合层约束 | 真正解决（披露+路径指引） | `README.md:178`、`run_formal_evaluation.py:53` 明确单品种入口不含组合风控，并指向 `PortfolioEngine(..., portfolio_risk="on")`。 |
| 4 positions.py fallback 重复默认值 | 部分解决后本次补齐 | 0.2.43 已修 stop/timeout/仓位键；本次补齐核心风控键并加 `test_core_risk_config_keys_do_not_use_literal_get_fallbacks`。 |
| 5 无干净 OOS 通过证据 | 真正解决（诚实披露，不伪造） | README/diagnostics 继续声明 SimNow 20 有效日未完成；未把污染窗口包装为晋级证据。 |
| 6 “确认”术语三义冲突 | 真正解决 | `README.md:51` 明确三义；`signals.py:312` 说明次级别确认从未实现。 |
| 7 zhongshu 标准差异未声明 | 真正解决 | `chan_strategy/zhongshu.py:15` 声明非 textbook/czsc.ZS，披露 `max_bis`/`lookback`/mode 差异。 |
| 8 score 死字段误导 | 真正解决 | `chan_strategy/signals.py:11` 声明 score 装饰性且不参与匹配/仓位；契约测试保留。 |
| 9 适用前提与失效环境零声明 | 真正解决 | `README.md:180` 新增适用前提与失效环境。 |
| 10 regime/ATR chop 默认关闭无文档 | 真正解决 | `README.md:171` 将 `regime_model`、`atr_chop_filter` 纳入开关清单并说明默认。 |
| 11 风控阈值无沿革 | 真正解决（披露，不追认有效性） | `README.md:83` 说明源自早期 A 股原型，未按期货重新优化。 |
| 12 根目录残留无治理 | 基本解决 | 测试迁入 `tests/unit/`，legacy/one-shot 横幅补齐；4 个 xfail 保持可见，本次修正原因披露。 |
| 13 凭据卫生 | 真正解决 | `diagnostics/simnow_connection_config.example.json` 用户/密码为占位符；`skill_build/llm_eval_config.json` 的 `api_key` 为空。 |
| 14 research/risk 单笔风险口径差异无说明 | 真正解决（披露） | README/正式评估说明区分 research 与 risk/组合路径；未把两者混为同一风险预算。 |

## 验证记录

- `python -m pytest tests/unit/test_a53_config_signal_cleanup.py::test_core_risk_config_keys_do_not_use_literal_get_fallbacks -q`：1 passed。
- `python -m pytest tests/unit/test_handoff_tool.py -q`：1 passed。
- `python tools/handoff.py status`：exit 0，输出 stage/owner/deliverables。
- `python -m pytest tests/unit/test_a53_config_signal_cleanup.py tests/unit/test_a87_joint_replay.py tests/unit/test_handoff_tool.py tests/unit/test_second_buy_real_path.py tests/unit/test_signal_path_hygiene.py -q -m "not realdb"`：43 passed, 4 xfailed。
- `python -m pytest tests/unit/test_portfolio_ledger_report.py::test_run_per_symbol_engines_sets_risk_sizing -q`：1 passed。
- `python tools/sync_check.py`：PASS，版本单一真相 `0.2.44`。
- `python -m pytest tests/unit -q -m "not realdb"`：当前沙箱未能完成。第一次因 `C:\Users\Admin\.vntrader\log\vt_20260726.log` 无写权限在收集阶段失败；创建本地 `.vntrader/log` 后继续运行，但大量 `tmp_path` 测试因 `C:\Users\Admin\AppData\Local\Temp\pytest-of-Admin` / 本地 `--basetemp` 目录枚举权限失败，属于测试临时目录环境限制。本次受影响路径的聚焦测试已通过。

## 剩余低危/观察项

- 4 个二买真实 CZSC 夹具测试仍 xfail；当前证据支持其为“历史夹具未覆盖二买状态/legacy 可见债”，不是已确认的生产信号缺陷。建议后续单独重建能稳定产生一买→二买结构的真实 CZSC fixture。
- 干净 OOS/SimNow 20 有效日仍未完成；这限制策略有效性证明，但不构成本次工程一致性中高危缺陷。

> 免责声明：本报告为策略工程质量审核，非投资建议；不对被审策略的实盘收益做任何承诺。
