# chan_strategy API 参考

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

本文件按模块列出 `chan_strategy/` 的公开 API。每条描述均可在对应源文件的签名、docstring 或调用点中找到依据，未验证的行为不展开。

## 包级导出

`chan_strategy/__init__.py` 显式导出以下符号：

- `STRATEGY_CONFIG`、`BACKTEST_CONFIG`、`SIGNAL_VERSION`（来自 `config.py`）
- `get_all_signals`（来自 `sell_signals.py`，**注意不是 `signals.py` 版本**）
- `ChanTimingStrategy`、`create_first_buy_position`、`create_second_buy_position`、`create_third_buy_position`、`create_first_sell_position`、`create_second_sell_position`、`create_third_sell_position`（来自 `positions.py`）
- `resample_bars`（来自 `data_adapter.py`）

新代码应优先从 `chan_strategy` 包级导入，而不是直接依赖子模块的内部实现。

## 模块速查

| 模块 | 核心职责 | 是否有独立示例 |
|------|----------|----------------|
| `config.py` | 策略与回测配置（单一来源） | 否 |
| `data_adapter.py` | SQLite 数据读取、重采样、RawBar 转换 | 见 `quickstart_example.py` |
| `limit_config.py` | 期货品种涨跌停板配置与触板辅助函数 | 否 |
| `rollover_config.py` | 连续合约换月检测与排除窗口 | 否 |
| `zhongshu.py` | 由已确认笔构建笔中枢 | 见 `quickstart_example.py` |
| `signals.py` | 基础分类、买点、风控信号（含遗留 `get_all_signals`） | 否 |
| `sell_signals.py` | 在 `signals.py` 基础上补充卖点，包级导出的是本模块 `get_all_signals` | 否 |
| `positions.py` | Factor/Event/Position 子策略层、仓位工厂 | 见 `quickstart_example.py` |
| `backtest_engine.py` | 单品种回测引擎与正式评估入口 | 见 `scripts/run_chan_backtest.py` |
| `portfolio_engine.py` | 多品种组合回放与组合级风控协调器 | 否 |
| `portfolio_ledger.py` | 组合账本（共享资金、保证金、日损/回撤熔断） | 否 |
| `validation.py` | 信号/事件/稳健性/SimNow 准备度验证 | 见 `scripts/run_validation.py` |
| `html_report.py` | 可交互 HTML 回测报告生成 | 否 |
| `vendor/` | czsc 0.9.51 `kline_pro` 文件级 vendor | 见 `docs/reference/czsc_vendor_notes.md` |

## `config.py`

配置是**单一来源**：所有策略/回测参数、数据库路径、版本号均从此模块读取。

- `SQLITE_DB_PATH: str`
  - 默认 SQLite 数据库路径，可被环境变量 `CHAN_SQLITE_DB_PATH` 覆盖。
- `STRATEGY_CONFIG: dict[str, Any]`
  - 策略参数、风控开关、研究-only 开关的统一字典。引擎在运行期直接读取该字典。
- `BACKTEST_CONFIG: dict[str, Any]`
  - 回测参数（起止日期、初始资金、手续费、滑点等）。
- `SIGNAL_VERSION: str`
  - 当前生产信号版本（如 `"V260615"`），用于信号键后缀。
- `PROFILE_ALLOWED_KEYS: frozenset[str]`
  - `trade_freq_profiles` 允许覆盖的键白名单；信号逻辑、仓位、成本类键不可覆盖。
- `validate_trade_freq_profiles() -> None`
  - 校验 trade-freq profile 未越白名单；违规时 raise（fail-closed）。
- `get_strategy_param(key: str) -> Any`
  - 按当前 `trade_freq` 解析参数：profile 覆盖优先，否则返回 `STRATEGY_CONFIG[key]`；默认配置下与直接读字典字节一致。

> **陷阱**：`STRATEGY_CONFIG` 是模块级可变字典；`formal_evaluation_config()` 通过临时修改它实现正式评估模式，不要在多线程/多进程间共享运行期配置。

## `data_adapter.py`

数据适配层：从本地 SQLite 加载 1 分钟期货 K 线，并转换为 `czsc.RawBar`。

- `SqliteDataAdapter(db_path: str | Path)`
  - 连接 SQLite，提供 `get_tables()`、`get_symbols(table)`、`get_table_schema(table)`、`get_sample_data(table, limit)`、`load_bars(...)` 等方法。
- `resample_bars(bars, target_freq, target_minutes=None, daily_agg=None, night_session_start_hour=None) -> list[RawBar]`
  - 将 1 分钟 RawBar 重采样到更高周期；支持 `daily_agg="natural"` / `"trading_calendar"` 两种日线聚合口径。
- 内部辅助：`_trading_day_for_bar`、`_resample_daily_trading_calendar`、`_resample_daily_natural`、`_merge_bars`。

> **注意**：`BacktestEngine` 固定读取 1 分钟表（`freq="1"`），交易/过滤周期由 `resample_bars` 合成。

## `limit_config.py`

共享的涨跌停/停牌配置与辅助函数。

- `SYMBOL_LIMIT_CONFIG: dict[str, dict[str, Any]]`
  - 各品种稳态涨跌停幅度及来源说明；含临时扩板窗口（需人工确认）。
- `_bar_at_limit(bar, prev_close, limit_pct) -> bool | tuple[bool, bool]`
- `_limit_pct_for_date(symbol, dt) -> float | None`
- `_daily_prev_close_map(...) -> dict[date, float]`

这些函数主要被 `backtest_engine.py` / `positions.py` 在开仓/平仓门控时调用。

## `rollover_config.py`

连续合约换月检测。

- `ROLLOVER_SYMBOLS: tuple[str, ...]`
  - 默认监控的品种列表：`("AP888", "RB888", "SC888", "A888", "ZN888")`。
- `_detect_transitions(db_path, symbol, start_date, end_date) -> dict[str, Any]`
  - 从 `{symbol}_1M_raw` 表的 `real_symbol` 列检测换月日期。
- `_exclusion_dates(transitions) -> set[date]`
- `_pair_in_exclusion_window(pair_dt, exclusion_dates) -> bool`
- `_trading_dates_from_bars(bars) -> set[date]`

## `zhongshu.py`

笔中枢构建。

- `build_zhongshu_from_bis(bis: list) -> list[dict[str, Any]]`
  - 从已确认笔列表构建笔中枢，返回带 `start_idx` / `end_idx` / `zg` / `zd` / `gg` / `dd` 等字段的字典列表。
- `_make_zhongshu(bis, start_idx, max_bis)`（内部辅助）

> **口径**：本项目所有"中枢"均指笔中枢（由笔构成），不是线段中枢。详见 `docs/theory_code_crosscheck.md` §8 探针结论。

## `signals.py`

基础分类、买点、结构状态、风控信号。**本模块不是生产回测的信号入口**。

- `_get_confirmed_bi_list(c: CZSC) -> list`
  - 从 `finished_bis` 获取已确认笔，并做 `last_bi_extend` 防御性过滤；这是避免未来函数的关键辅助。
- `_get_confirming_bi(bi_list, base_idx, direction) -> Any | None`
- `signal_bi_direction(c, freq="30分钟") -> dict`
- `signal_zs_position(c, freq="30分钟") -> dict`
- `signal_trend_type(c, freq="30分钟") -> dict`（A106 新增只读分类）
- `signal_data_sufficiency(c, freq="30分钟", min_bi_count=5) -> dict`
- `signal_divergence_status(c, freq="30分钟") -> dict`
- `signal_zs_confirmation(c, freq="30分钟") -> dict`
- `signal_first_buy(c, freq="30分钟") -> dict`
- `signal_second_buy(c, freq="30分钟", buy1_anchor=None) -> dict`
- `signal_third_buy(c, freq="30分钟") -> dict`
- `signal_risk_control(c, freq="30分钟", stop_loss_pct=None) -> dict`
- `signal_risk_control_recent(c, freq="30分钟", stop_loss_pct=None) -> dict`
- `_select_zhongshu_for_departure_leg(bi_list, zhongshu_list) -> dict`
  - 选择一个后面有离开段的中枢，被 `signal_divergence_status` / `signal_first_buy` / `signal_first_sell` 等复用。
- `get_legacy_signals(c, freq="30分钟", buy1_anchor=None) -> dict`
  - 汇总本模块内的"遗留信号系统"，是**独立维护**的代码路径。
- `get_all_signals(c, freq="30分钟", buy1_anchor=None) -> dict` ⚠️
  - **已弃用兼容入口**，内部转发到 `get_legacy_signals` 并触发 `DeprecationWarning`。
- `class AtrStateTracker`
  - 增量 ATR 跟踪器，用于 `atr_chop_filter`（默认关闭）。

## `sell_signals.py`

**生产信号入口**。在 `signals.py` 基础上补充卖点与空头风控；`chan_strategy/__init__.py` 导出的 `get_all_signals` 即本模块的函数。

- `signal_second_buy(c, freq="30分钟", buy1_anchor=None) -> dict`
- `signal_third_buy(c, freq="30分钟") -> dict`
- `signal_first_sell(c, freq="30分钟") -> dict`
- `signal_second_sell(c, freq="30分钟", sell1_anchor=None) -> dict`
- `signal_third_sell(c, freq="30分钟") -> dict`
- `signal_short_risk_control(c, freq="30分钟", stop_loss_pct=None) -> dict`
- `signal_short_risk_control_recent(c, freq="30分钟", stop_loss_pct=None) -> dict`
- `get_all_signals(c, freq="30分钟", buy1_anchor=None, sell1_anchor=None) -> dict`
  - 返回包含买点、卖点、结构状态、风控的完整信号字典。

### `signals.py.get_all_signals()` 与 `sell_signals.py.get_all_signals()` 的关系

这是本仓库一个真实的认知陷阱，必须区分：

1. **`sell_signals.py` 的 `get_all_signals()` 是当前生产路径**：
   - 汇总 `signal_first_buy` / `signal_second_buy` / `signal_third_buy`（安全实现）
   - 额外包含 `signal_first_sell` / `signal_second_sell` / `signal_third_sell`（卖点）
   - 额外包含空头风控 `signal_short_risk_control` / `signal_short_risk_control_recent`
   - `chan_strategy/__init__.py` 导出的是这个版本。

2. **`signals.py` 的 `get_all_signals()` 是遗留兼容入口**：
   - 已标记 `DeprecationWarning`。
   - 转发到同模块的 `get_legacy_signals()`，后者组装的是本模块内**独立维护**的"遗留信号系统"（包括 `signals.py` 自己的 `signal_second_buy` / `signal_third_buy` 实现）。
   - 两套系统对同一输入**不保证结果一致**；`signals.py` 版本主要用于兼容部分历史脚本和 `tests/unit/test_remaining_coverage.py`。

**结论**：新代码、新文档、生产回测与测试统一使用 `chan_strategy.sell_signals.get_all_signals()`（或包级 `from chan_strategy import get_all_signals`），不要使用 `chan_strategy.signals.get_all_signals()`。

## `positions.py`

Factor/Event/Position 子策略层。

- `class Operate(Enum)`
  - 操作类型枚举（买/卖/开/平）。
- `class Signal`
  - 轻量信号对象；`is_match(other)` 只比较 key 与 v1/v2/v3，**score 段被忽略**。
- `class Factor`
  - 由多个 `Signal` 组成的复合条件。
- `class Event`
  - 开仓/平仓事件；内部用 `signals_all` / `signals_not` 描述触发条件。
- `class TradeRecord`
  - 单笔成交记录。
- `class Position`
  - 单个子策略仓位：处理开仓、止损、超时、移动止损、结构失效、每日过滤事件等。
- `class ChanTimingStrategy`
  - 策略主类：管理多个 `Position`，组合多空子策略信号，产出交易对（pairs）。
- `normalize_exit_reason(reason: str) -> str`
- `_research_symbol_key(symbol) -> str`
- `_research_contract_spec(symbol) -> dict`
- `_round_price_to_tick(symbol, price) -> float`
- `_research_trailing_params(symbol) -> tuple[int, float]`
- `create_first_buy_position(symbol, freq="30分钟", ...) -> Position`
- `create_second_buy_position(symbol, freq="30分钟", ...) -> Position`
- `create_third_buy_position(symbol, freq="30分钟", ...) -> Position`
- `create_first_sell_position(symbol, freq="30分钟", ...) -> Position`
- `create_second_sell_position(symbol, freq="30分钟", ...) -> Position`
- `create_third_sell_position(symbol, freq="30分钟", ...) -> Position`

> **陷阱**：`Signal.is_match` 不比较 score。任何"按 score 加权"的下游逻辑都不会生效；详情见 `tests/unit/test_signal_contract.py`。

## `backtest_engine.py`

单品种回测引擎。

- `class BacktestEngine`
  - 加载数据、驱动 `ChanTimingStrategy`、生成绩效报告。
  - 主要方法：`run()`、`generate_report()`、`print_report(report)`。
- `run_single_backtest(symbol, freq, start_date, end_date, table_name, ...) -> dict`
- `run_batch_backtest(configs, ...) -> list[dict]`
- `run_formal_evaluation(symbol, freq, start_date, end_date, table_name, ...) -> dict`
  - 启用 `sizing_model="risk"` + `limit_halt_model="enforce"` 的正式评估路径。
- `formal_evaluation_config() -> contextmanager`
  - 临时覆盖 `STRATEGY_CONFIG` 中正式评估相关键，退出时恢复。
- `_render_html_report_if_enabled(engine, report) -> str | None`
  - 当 `STRATEGY_CONFIG["html_report_enabled"]` 为真时渲染 HTML 报告。

> **正式评估是单品种**：`run_formal_evaluation.py` 不含组合级风控；组合级风控见 `portfolio_engine.py`。

## `portfolio_engine.py`

多品种组合回放。

- `class PortfolioCoordinator`
  - 基于权重（非保证金）的组合协调器；`portfolio_risk="on"` 且 `sizing_model!="risk"` 时使用。
- `class PortfolioEngine`
  - 多品种联合回放入口；方法 `run()` 根据 `sizing_model` 选择走 `PortfolioCoordinator` 还是 `PortfolioLedger`。
- `_sub_strategy_relative_weights() -> dict[str, float]`
- `_strategy_weight_fixed(strategy, symbol=None) -> float`
- `_position_sign(strategy) -> int`
- `_render_portfolio_html_report_if_enabled(...)`

## `portfolio_ledger.py`

组合账本（A87）。

- `class PortfolioLedger`
  - 跟踪共享资金、各品种保证金占用、簇敞口、日损限制、回撤熔断。
  - 主要方法：`pre_open_injection_for(symbol, dt, price, equity, total_open_margin) -> dict`。

> **双义键说明**：`max_margin_pct` / `cluster_gross_cap` / `daily_loss_limit_pct` 在 `PortfolioCoordinator` 与 `PortfolioLedger` 中有不同解释，但两者由 `sizing_model` 互斥分流，同一时刻只激活一种解释。

## `validation.py`

验证与诊断。

- `class SignalValidator`
- `class EventValidator`
- `class RobustnessValidator`
- `class SimNowReadinessChecker`
- `run_full_validation(symbol, freq, start_date, end_date, table_name, ...) -> dict`
  - 运行完整验证流程，返回信号/事件/稳健性/SimNow 准备度结果。
- `generate_optimization_suggestions(report, validation_results) -> List[str]`
- `_calc_max_drawdown(pnls, position_fraction=0.1) -> float`
- `_calc_max_drawdown_weighted(all_pairs, pos_weights) -> float`
- `_calc_sharpe(pnls, annual_factor=252) -> float`

## `html_report.py`

可交互 HTML 报告。

- `build_symbol_chart_payload(engine, report=None) -> dict[str, Any]`
  - 构建单个品种的图表/笔/中枢/买卖点/汇总数据 payload。
- `render_backtest_html_report(payloads, out_path=None, title=None) -> str`
  - 渲染多标签 HTML 报告；支持单品种或多品种 payload。
- `default_html_report_dir() -> Path`
  - 返回默认报告输出目录。

> **口径**：报告中的"中枢"均指笔中枢；K 线周期只是观察窗口，不是递归级别。详见 `docs/theory_code_crosscheck.md` §9 P0。

## `vendor/`

见 [`czsc_vendor_notes.md`](./czsc_vendor_notes.md)。

- `vendor/echarts_plot.py`：`kline_pro`、`SMA`、`EMA`、`MACD`
- `vendor/echarts.min.js`：内嵌 ECharts 运行时
- `vendor/__init__.py`：导出 `kline_pro`
