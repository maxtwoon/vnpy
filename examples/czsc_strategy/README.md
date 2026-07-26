# 缠论期货 CTA 策略（当前实现）

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> 本项目是一个**研究用途**的量化策略工作区，不是可上线的交易推荐。所有历史回测结果仅为代码行为的记录，不代表未来表现；任何涉及真实资金的决策都需要独立的风控、合规与实盘验证。
>
> - `is_promotion_evidence`: False
> - `research_only`: True
> - `note`: 请勿将本仓库中的回测数字、参数默认值或诊断报告作为投资建议使用。

## 策略概述

本目录是 VeighNa（vnpy）框架上的一个**期货 CTA 研究策略**，基于缠论（CZSC）结构分析，以"一买 / 二买 / 三买"及其镜像卖点作为核心信号，对选定的商品期货连续合约进行多周期择时。

与仓库中仍保留的早期 A 股原型（`czsc_adapter.py` / `czsc_multi_timeframe_strategy.py` / `run_baostock_backtest.py`）不同，当前 actively-tested 的实现完全位于 `chan_strategy/` 目录下，信号版本为 `V260615`。

> **历史归档**：旧版 README 内容已移至 [`README.legacy.md`](./README.legacy.md)，其中描述的 2021-2022 年 A 股波段战法原型已不再接入当前回测与测试路径。

## 核心设计

### 周期映射

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `trade_freq` | `30分钟` | 交易决策周期 |
| `filter_freq` | `日线` | 环境过滤周期 |

以上默认值来自 `chan_strategy/config.py` 的 `STRATEGY_CONFIG`，是该策略生产回测路径的真实配置。引擎固定从 1 分钟 K 线重采样出 `trade_freq`/`filter_freq`（`backtest_engine.py` 硬编码 `freq="1"` 读取底层数据）；曾经存在的 `base_freq`（基础周期）与 `confirm_freq`（次级别确认周期）两个配置键从未被任何代码消费，"次级别确认"信号语义在当前版本中并未实现（详见下方"信号语义"一节的澄清），已随本次审核一并删除，避免用户误以为修改它们会影响信号行为。

### 信号体系（生产路径）

生产信号由 `chan_strategy/sell_signals.py` 中的 `get_all_signals()` 统一输出，包括：

- **多头买点**：一买、二买、三买
- **空头卖点**：一卖、二卖、三卖
- **结构状态**：笔方向、中枢位置、中枢结构确认、数据充分度、背驰状态
- **风控信号**：多头结构失效 / 空头结构失效 / 震荡超限

> **注意**：`chan_strategy/signals.py` 内部也保留了一个 `get_all_signals()` 汇总函数，用于兼容部分历史脚本；该函数会调用 `signals.py` 中已废弃的二买 / 三买实现，**不是**当前回测引擎实际使用的路径。新代码与文档描述应以 `sell_signals.get_all_signals()` 为准。

### 信号语义（简述）

- **一买**：向下离开中枢后，离开段力度弱于进入段（疑似底背驰），并在其后出现新的向上确认笔。
- **二买**：一买低点之后反弹、回抽不创新低，再出现向上确认笔。
- **三买**：向上有效离开中枢，回抽不进入中枢上沿，再出现向上确认笔。
- **一卖 / 二卖 / 三卖**：分别为上述结构的镜像，仅在 `enable_short=True` 时启用；默认配置中空头子策略关闭。

所有信号仅使用 CZSC 的已确认笔（`finished_bis` 并做防御性过滤），不允许使用未确认末笔，以避免未来函数。

> **"确认"一词的三种含义（术语澄清，2026-07-26 审核后补充）**：本项目中"确认"在三处场景下语义不同，务必区分：
> 1. **买卖点确认笔**（如上文"一买确认"）：指候选条件满足后，紧跟出现的同级别反向笔（`signals.py` 内 `_get_confirming_bi`），与"次级别"无关。
> 2. **中枢结构状态"已确认"**：指中枢已由 ≥3 笔重叠构成（`signal_zs_confirmation`），与买卖点确认是两回事。
> 3. **"次级别确认"**：曾在 `confirm_freq` 配置项与部分函数 docstring 中提及，但从未被任何代码实际消费——不存在跨级别协同确认的实现。相关死配置已删除（见上文"周期映射"）。

### 仓位管理

默认采用固定分层仓位（`sizing_model="research"` 为基线）：

| 子策略 | 默认仓位比例 | 说明 |
|--------|-------------|------|
| 一买 / 一卖 | 10% | 左侧试仓 |
| 二买 / 二卖 | 20% | 趋势确认加仓 |
| 三买 / 三卖 | 30% | 强势 breakout 加仓 |

> 默认 `enable_short=False`，因此一卖 / 二卖 / 三卖不会实际开仓。所有仓位阈值均可在 `chan_strategy/config.py` 中调整。

### 风控参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `stop_loss_1buy` / `stop_loss_1sell` | 200 BP | 一买 / 一卖固定止损（2%） |
| `stop_loss_2buy` / `stop_loss_2sell` | 300 BP | 二买 / 二卖固定止损（3%） |
| `stop_loss_3buy` / `stop_loss_3sell` | 350 BP | 三买 / 三卖固定止损（3.5%） |
| `timeout_1buy` / `timeout_1sell` | 600 根 30 分钟 K 线 | 一买 / 一卖超时平仓 |
| `timeout_2buy` / `timeout_2sell` | 1000 根 30 分钟 K 线 | 二买 / 二卖超时平仓 |
| `timeout_3buy` / `timeout_3sell` | 1500 根 30 分钟 K 线 | 三买 / 三卖超时平仓 |
| `trailing_start_bp` | 300 BP | 盈利超过 3% 后启动移动止损 |
| `trailing_drawback_pct` | 0.25 | 从最高盈利回撤 25% 时平仓 |
| `structural_invalidation_pct` | 0.05 | 价格突破中枢边缘 5% 视为结构失效 |

> **参数沿革（2026-07-26 审核后补充）**：上表止损/超时/移动止损数值源自项目早期 A 股波段战法原型（`README.legacy.md`）的经验设定，迁移到期货 CTA 场景时未针对期货合约的波动率/保证金特性重新优化或做参数敏感性扫描；`diagnostics/` 下的稳健性扫描（成本敏感性、品种邻域扫描）验证的是这组既定数值的稳健性，不等于验证了数值本身的最优性。修改前建议先看 `diagnostics/platform_optimization_round*.md` 系列既有扫描结果。

### 默认交易标的

`chan_strategy/config.py` 中 `contract_specs` 定义的默认期货连续合约：

| 合约 | 合约乘数 | 最小变动价位 | 交易所最低保证金率（研究用） |
|------|---------:|------------:|----------------------------|
| AP888（苹果） | 10 | 1.0 | 7% |
| RB888（螺纹钢） | 10 | 1.0 | 5% |
| SC888（原油） | 1000 | 0.1 | 5% |
| A888（黄大豆1号） | 10 | 1.0 | 5% |
| ZN888（锌） | 5 | 5.0 | 5% |

> 上述保证金率为交易所公布的最低标准，仅用于研究回测，不是实际券商/期货公司保证金。

### 回测配置

`chan_strategy/config.py` 中 `BACKTEST_CONFIG` 的默认值：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `start_date` | `2023-01-01` | 回测开始日期 |
| `end_date` | `2025-12-31` | 回测结束日期 |
| `initial_capital` | 1,000,000 | 初始资金 |
| `commission_rate` | 0.0001 | 手续费（万一） |
| `slippage` | 0.0005 | 滑点（0.05%） |

回测数据源为 SQLite 期货 1 分钟 K 线数据库（路径由 `SQLITE_DB_PATH` 指定，可通过环境变量 `CHAN_SQLITE_DB_PATH` 覆盖）。

## 文件结构

```
examples/czsc_strategy/
├── chan_strategy/                     # 当前策略核心实现
│   ├── backtest_engine.py             # 回测引擎
│   ├── config.py                      # 策略与回测配置（单一来源）
│   ├── data_adapter.py                # SQLite 数据适配层
│   ├── limit_config.py                # 涨跌停/停牌配置
│   ├── portfolio_engine.py            # 组合风险协调器
│   ├── positions.py                   # 持仓与仓位管理
│   ├── rollover_config.py             # 连续合约 rollover 配置
│   ├── sell_signals.py                # 生产卖点/买点信号（当前回测使用）
│   ├── signals.py                     # 基础分类与买点信号（含兼容实现）
│   ├── utils.py                       # 工具函数
│   ├── validation.py                  # 验证工具
│   └── zhongshu.py                    # 中枢构建
├── diagnostics/                       # 诊断报告与研究输出
├── tests/                             # 单元/集成/性能测试
├── run_chan_backtest.py               # 当前期货策略回测入口
├── run_validation.py                  # 验证脚本
├── README.md                          # 本文档（当前策略）
├── README.legacy.md                   # 旧版 A 股原型归档
├── VERSION                            # 子项目版本
└── CHANGELOG.md                       # 子项目变更日志
```

> 旧版文件 `czsc_adapter.py`、`czsc_multi_timeframe_strategy.py`、`run_baostock_backtest.py` 等仍保留在目录中，但属于**已废止的早期 A 股原型**，当前测试与生产回测路径不再引用。

## 使用方法

### 运行回测

```bash
cd examples/czsc_strategy
python run_chan_backtest.py
```

首次运行前请确认 `chan_strategy/config.py` 中的 `SQLITE_DB_PATH` 指向有效的期货 1 分钟 K 线 SQLite 数据库。数据库表名格式通常为 `{symbol}_1M_raw`（如 `sc888_1M_raw`）。

### 运行测试

```bash
# 运行 czsc_strategy 单元测试（跳过需要本地历史数据库的测试）
python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
```

### 查看研究-only 开关

`chan_strategy/config.py` 的 `STRATEGY_CONFIG` 中叠加了大量研究-only 的可选开关（默认均为与历史基线字节一致的值），例如：

- `exit_model`: `"legacy" | "structural_atr"`
- `limit_halt_model`: `"off" | "aware" | "enforce"`
- `sizing_model`: `"research" | "risk"`
- `divergence_model`: `"amplitude" | "macd"`
- `resonance_filter`: `"off" | "daily" | "daily_4h"`
- `second_buy_mode`: `"baseline" | "gated" | "off"`
- `portfolio_risk`: `"off" | "on"`
- `weighting`: `"fixed" | "risk_parity"`
- `regime_model`: `"independent"（默认）| "router"`（"router" 时由日线市况路由器统一选择当日允许开仓的多空方向；默认 `"independent"` 为多空各自独立按自身信号门控，不做市况路由）
- `atr_chop_filter`: `"off"（默认，legacy 行为）| "on"`（基于 ATR 的震荡市过滤器；开启后在低波动/无趋势环境下会 gate 掉新开仓；实现见 `positions.py`）
- `max_drawdown_breaker_pct`: `None`（默认，禁用）| `0~1` 之间的小数（2026-07-26 审核后新增）——组合权益相对历史峰值的持久性回撤熔断，跨交易日不重置（区别于每日重置的 `daily_loss_limit_pct`）；仅在 `sizing_model="risk"` 且 `portfolio_risk="on"` 的联合回放路径（`PortfolioLedger`）生效，触发后强平并阻断新开仓，直到该次回放结束

完整列表与默认值请以 `chan_strategy/config.py` 为准，README 不再逐一复制，以避免再次出现文档漂移。

如需运行默认配置以上的正式评估路径（`sizing_model="risk"`、`limit_halt_model="enforce"`、换月窗口开仓门控等），请使用独立入口 `run_formal_evaluation.py`，而不是默认的 `run_chan_backtest.py`。**该入口是单品种评估，不包含任何组合级风控**（`max_margin_pct` / `daily_loss_limit_pct` / `max_drawdown_breaker_pct` 均只存在于多品种联合回放路径）；如需组合级风控约束下的报告，请改用 `PortfolioEngine(symbols, ...).run()` 并设置 `portfolio_risk="on"` + `sizing_model="risk"`（见 `chan_strategy/portfolio_engine.py` / `portfolio_ledger.py`）。

### 适用前提与失效环境（2026-07-26 审核后补充）

本策略是"一买（左侧抄底）+ 三买（突破跟随）"的混合体系，对趋势/波动环境存在结构性依赖，但当前 README 与代码内**没有任何正式声明**指明策略的有效前提或已知失效环境。以下为已知情况，供使用者参考，**不构成有效性证明**：

- **一买（左侧抄底）**在持续单边下跌（无有效底背驰反转）的环境中天然容易受损——这正是结构失效退出（`structural_invalidation_pct`）存在的原因，但该退出是止损性质的被动保护，不是主动的环境识别。
- `diagnostics/first_buy_environment_candidates_*` 系列报告探索过针对一买信号叠加"日线趋势向下时屏蔽"（`block_daily_down`）等环境过滤候选，results 显示可降低弱势窗口下的一买损伤，但**这些报告使用的窗口 `2022-01-01~2026-04-24` 属于反复用于参数选择的受污染证据**，报告自身已标注为负面/受污染证据，不能作为"该过滤器有效"的证明，仅供了解研究方向。
- 三买（突破跟随）在无趋势/震荡行情中容易被反复打止损；`atr_chop_filter`（震荡市过滤，默认关闭）与 `regime_model="router"`（市况路由，默认关闭）是项目中现有的、未默认启用的缓解机制（见上文"查看研究-only 开关"）。
- 在干净样本外证据出现之前（见"重要说明"第 3 条与 `diagnostics/simnow_20d_promotion_decision.md`），本策略不应被视为对任何特定市场环境已验证有效或无效。

## 重要说明

1. **研究用途**：本策略及其所有参数、回测结果、诊断报告仅供研究，不构成投资建议。
2. **默认 sizing_model="research"**：该模式使用固定 1 手 / 1 倍乘数的百分比收益曲线，不是真实资金 P&L 曲线；若需模拟真实资金，请切换到 `sizing_model="risk"` 并理解其假设。
3. **历史数据不代表未来**：默认回测窗口 2023-01-01 ~ 2025-12-31 内的任何结果都不能保证未来表现。
4. **未考虑所有实盘摩擦**：默认成本模型仅包含手续费与滑点，未覆盖交易所规则变化、流动性冲击、保证金追缴、断网等真实交易风险。
5. **空头默认关闭**：`enable_short=False`，因此默认仅运行多头子策略；启用空头需要在配置中显式打开并独立评估风险。
6. **信号路径**：生产回测与测试统一使用 `chan_strategy/sell_signals.py` 中的 `get_all_signals()`，不要使用 `signals.py` 内部的同名汇总函数。

## 历史诊断报告

`examples/czsc_strategy/diagnostics/` 目录下保存了带有 `RESEARCH-ONLY / NOT PROMOTION EVIDENCE` 横幅的研究报告。如需了解历史回测表现，请直接阅读这些文件，而不是从本 README 中获取被截断或重新表述的数字。

例如：

- `diagnostics/backtest_matrix_20220101_20260424.md` —— 全样本回测矩阵（覆盖 AP888 / RB888 / SC888 / A888 / ZN888），但该报告使用的窗口 `2022-01-01~2026-04-24` 属于反复用于参数选择的历史数据，报告自身已明确标注为受污染/负面证据，不能作为推广依据。
- `diagnostics/trailing_oos_validation_20250101_20260424.md` —— 移动止损的样本外验证（2025-01-01 ~ 2026-04-24）。

> 任何历史绩效数字都必须以原始横幅报告为准；本 README 不生成、不重复、不更新此类数字。
