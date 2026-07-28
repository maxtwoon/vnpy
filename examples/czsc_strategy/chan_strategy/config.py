"""缠论择时策略配置"""
import os

# 数据库路径
SQLITE_DB_PATH = os.getenv(
    "CHAN_SQLITE_DB_PATH",
    r"D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db"
)

# 策略参数
STRATEGY_CONFIG = {
    # 注：引擎固定从 1 分钟 K 线重采样（backtest_engine.py 硬编码 freq="1"）；
    # 曾存在的 base_freq/confirm_freq 键从未被任何代码消费（"次级别确认"未实现），
    # 已于 2026-07-26 审核后删除，避免用户误以为改这两项会生效。
    "trade_freq": "30分钟",    # 交易周期
    "filter_freq": "日线",     # 环境过滤周期

    # 仓位管理
    # 注：总资金实际来自 BACKTEST_CONFIG["initial_capital"]（见下）；
    # 曾存在的 total_capital 键无任何消费方，已于 2026-07-26 审核后删除。
    "pos_1buy": 0.10,          # 一买仓位10%（左侧试仓）
    "pos_2buy": 0.20,          # 二买仓位20%
    "pos_3buy": 0.30,          # 三买仓位30%
    "enable_short": False,     # 是否启用一卖/二卖/三卖空头子策略
    "regime_model": "independent",  # "independent" (default, each side self-gated) | "router" (daily regime selects allowed side)
    "enable_short_symbols": None,  # Research-only short enable list; None means all when enable_short=True.
    # long_short_overlap_policy = independent_long_short_substrategies:
    # when enable_short=True and regime_model="independent", long/short
    # sub-strategies may overlap on the same symbol; reports audit this via
    # both_long_short_bars.
    "symbol_position_overrides": {},  # Research-only per-symbol pos_* overrides.
    "pos_1sell": 0.10,         # 一卖仓位10%（左侧试仓）
    "pos_2sell": 0.20,         # 二卖仓位20%
    "pos_3sell": 0.30,         # 三卖仓位30%

    # 风控参数
    "stop_loss_1buy": 200,     # 一买止损200BP (2%)
    "stop_loss_2buy": 300,     # 二买止损300BP (3%)
    "stop_loss_3buy": 350,     # 三买止损350BP (3.5%)
    "stop_loss_1sell": 200,    # 一卖止损200BP (2%)
    "stop_loss_2sell": 300,    # 二卖止损300BP (3%)
    "stop_loss_3sell": 350,    # 三卖止损350BP (3.5%)

    # A53 structural-invalidation threshold (NOT the position stop-loss tiers above).
    # This is the "结构失效" margin past a center edge used by signal_risk_control
    # and the short-side mirror.  It is a fraction (e.g. 0.05 = 5%), not basis points.
    "structural_invalidation_pct": 0.05,
    # timeout 按交易周期 bar 计数；当前交易周期为 30 分钟
    "timeout_1buy": 600,       # 600根30分钟K线 = 300交易小时
    "timeout_2buy": 1000,      # 1000根30分钟K线 = 500交易小时
    "timeout_3buy": 1500,      # 1500根30分钟K线 = 750交易小时
    "timeout_1sell": 600,      # 600根30分钟K线 = 300交易小时
    "timeout_2sell": 1000,     # 1000根30分钟K线 = 500交易小时
    "timeout_3sell": 1500,     # 1500根30分钟K线 = 750交易小时
    "interval_1buy": 3600 * 24, # 一买开仓间隔24小时
    "interval_2buy": 3600 * 24, # 二买开仓间隔24小时
    "interval_3buy": 3600 * 24, # 三买开仓间隔24小时
    "interval_1sell": 3600 * 24, # 一卖开仓间隔24小时
    "interval_2sell": 3600 * 24, # 二卖开仓间隔24小时
    "interval_3sell": 3600 * 24, # 三卖开仓间隔24小时
    "T0": False,               # 不允许T0交易

    # 移动止损参数
    "trailing_start_bp": 300,      # 盈利超过300BP(3%)后启动移动止损
    "trailing_drawback_pct": 0.25, # 移动止损回撤容忍比例(从最高回撤25%平仓)

    # 止损执行模型（A38 Phase 1）。默认 "close" 与历史基线字节一致；
    # "intrabar" 用当根 bar 的 low/high 触价触发，避免收盘价检查下的隔夜跳空穿透。
    "stop_execution_model": "close",   # "close"（基线：逐bar收盘价触发/成交）| "intrabar"（bar内触价）
    "stop_penalty_bp": 0,              # intrabar 止损成交的额外不利滑点(BP)，默认0不惩罚

    # Research-only execution switches. None / empty keeps baseline behavior.
    "max_2buy_entry_vs_anchor_pct": None,
    "enable_2buy_symbols": None,
    # A53 first-buy research gates (None/False = legacy no-op behavior).
    "enable_1buy_symbols": None,       # restrict first-buy opens to this symbol list
    "block_1buy_daily_down": False,    # block first-buy open when daily direction is 向下
    "block_1buy_daily_not_up": False,  # block first-buy open when daily direction is not 向上
    "block_1buy_daily_below_zs": False,  # block first-buy open when daily position is 中枢下方
    "trailing_overrides": {},

    # A37 exit-event semantics switch (default legacy to keep baseline unchanged).
    "exit_event_semantics": "legacy",  # "legacy" | "restructured"

    # A39 daily aggregation switch (P2). "natural" is the legacy byte-identical path;
    # "trading_calendar" maps night-session bars past midnight to the next trading day.
    "daily_agg": "natural",               # "natural" | "trading_calendar"
    "night_session_start_hour": 20,       # bars with hour >= this are evening-session bars

    # A40 real position sizing (P3). "research" is the legacy byte-identical default;
    # "risk" sizes integer lots from equity, stop distance, contract multiplier and margin cap.
    "sizing_model": "research",           # "research" (legacy, default) | "risk"
    "risk_per_trade_pct": 0.005,          # NOMINAL risk budget per trade (0.5% of equity), sized off the
                                          # stop-loss distance; NOT a guaranteed max loss — actual loss can
                                          # exceed it via non-stop exits (structural failure, timeout,
                                          # gap-through the stop price). See Position._size_open docstring.
    "max_margin_pct": 0.50,               # cap on total open initial margin vs equity
    "max_symbol_margin_pct": 1.0,         # A87 joint replay only: per-symbol margin cap as a
                                          # fraction of shared portfolio equity (1.0 = no tighter
                                          # than legacy single-symbol behavior)
    "equity_mode": "fixed",               # "fixed" (running realized+unrealized off initial_capital)
                                          # | "compound" (documented, NOT implemented; raises NotImplementedError)

    # A43 MACD-area divergence (P4). "amplitude" is the legacy byte-identical default;
    # "macd" compares leaving vs entering segment MACD magnitude (|hist| area).
    "divergence_model": "amplitude",      # "amplitude" (legacy, default) | "macd"

    # P4 zhongshu selection fix. "legacy" keeps the naive zhongshu_list[-1] behavior
    # that made the P4 divergence signal structurally unreachable for shorts;
    # "departure_leg" selects the most recent zhongshu that actually has BIs after it,
    # matching signal_first_buy/signal_first_sell. Default "legacy" preserves all
    # existing default-config backtest results byte-for-byte.
    "divergence_status_zhongshu_mode": "legacy",  # "legacy" (default) | "departure_leg"
    "macd_fast": 12,                      # MACD fast EMA period (standard, NOT tuned)
    "macd_slow": 26,                      # MACD slow EMA period (standard, NOT tuned)
    "macd_signal": 9,                     # MACD signal EMA period (standard, NOT tuned)

    # A44 multi-level resonance entry filter (P5). "off" is the legacy byte-identical default;
    # "daily" requires strictly-positive daily structure (direction + position);
    # "daily_4h" additionally requires the 4H level to be constructive.
    "resonance_filter": "off",            # "off" (legacy, default) | "daily" | "daily_4h"
    "resonance_freq_4h": "240分钟",        # 4H CZSC level frequency label

    # A45 second-buy hard-gate + ATR chop filter (P6). "baseline" keeps the legacy behavior;
    # "gated" requires P4 MACD divergence, P5 resonance and ATR expansion;
    # "off" blocks all NEW second-buy opens while still allowing exits/risk-control.
    "second_buy_mode": "baseline",        # "baseline" (legacy, default) | "gated" | "off"
    "atr_chop_filter": "off",             # "off" (legacy, default) | "on"
    "atr_period": 14,                     # ATR lookback period for chop detection
    "atr_lookback": 100,                  # number of past ATR values used for percentile
    "atr_percentile_floor": 0.30,         # block opens when current ATR percentile is below this

    # A47 exit-model overhaul (P8a). "legacy" keeps the fixed-percentage-giveback trailing stop;
    # "structural_atr" uses ATR trailing + partial take-profit at directional targets.
    # IMPORTANT (A56, 2026-07-13): under "structural_atr" the ATR trailing stop is only evaluated
    # AFTER a partial take-profit event has fired. Positions that never reach a directional target
    # rely solely on the fixed stop-loss (above) and the timeout (below) for profit-side protection.
    "exit_model": "legacy",               # "legacy" (default, byte-identical) | "structural_atr"
    "atr_trail_mult": 3.0,                # ATR trailing-stop multiplier
    "partial_tp_frac": 0.5,               # fraction of position scaled out at the first directional target

    # A48 portfolio risk coordinator (P8b). "off" is the legacy byte-identical default;
    # "on" enables a backtest-only cross-symbol coordinator above per-symbol engines.
    "portfolio_risk": "off",              # "off" (legacy, default) | "on"

    # A51/A67 limit-up/down/halt fill behavior. "off" is the legacy byte-identical default;
    # "aware" adds ``is_entry_at_limit`` / ``is_exit_at_limit`` boolean fields to each
    # ``Position.pairs`` entry without changing fills, prices or trade counts;
    # "enforce" rejects fills that occur at an unexecutable limit/halt band for that side
    # (long entry at upper limit, long exit at lower limit, etc.) and records the rejection
    # via ``fill_rejected_at_limit``.  "enforce" is a research-only opt-in mode and does not
    # model exchange queue position or partial fills.
    # In rollover splice exclusion windows produced by rollover_open_gating="on",
    # BacktestEngine suppresses limit-halt tagging/rejection because the
    # continuous-contract splice jump is not an executable session limit lock;
    # generated reports count these bars as limit_halt_rollover_suppressed_bars.
    "limit_halt_model": "off",            # "off" (legacy, default) | "aware" | "enforce"

    # A52 rollover-window stat tagging (P10). "off" is the legacy byte-identical default;
    # "on" adds an ``is_rollover_window`` boolean field to each ``Position.pairs`` entry
    # without changing fills, prices or trade counts.
    "rollover_stat_tagging": "off",       # "off" (legacy, default) | "on"

    # A76 rollover-window open gating (P11). "off" is the legacy byte-identical default;
    # "on" blocks NEW long/short opens on bars whose trading date falls inside the
    # rollover exclusion window. Exits, stop-loss, timeout and risk-control for
    # already-open positions are unaffected. Enabled by formal_evaluation_config()
    # for formal-evaluation runs. The exclusion window is built from full-window
    # ex-post rollover transition detection and is protective open gating only,
    # so formal backtests may be slightly optimistic versus live point-in-time
    # rollover detection.
    "rollover_open_gating": "off",        # "off" (legacy, default) | "on"

    # Data-quality fail-closed threshold for rows skipped because datetime
    # parsing failed. Default None preserves legacy research behavior; formal
    # evaluation sets 0.001 so material timestamp corruption stops the run.
    "max_unparseable_row_rate": None,

    # Price tick rounding for recorded research fills. Default "off" preserves
    # legacy baseline snapshots; formal evaluation sets "on" so fills use the
    # exchange tick from contract_specs.
    "price_tick_rounding": "off",

    # risk_parity recomputes every bar and deliberately has no turnover/rebalance
    # control: reports expose risk_parity_rebalance_policy="every_bar",
    # risk_parity_turnover_control="none", max_symbol_weight_observed, and a
    # dropout/concentration caveat for missing active-symbol bars.
    "weighting": "fixed",                 # "fixed" (legacy 10/20/30 split) | "risk_parity"
    "corr_clusters": {                    # correlated symbol clusters for gross exposure cap
        "industrial_energy": ["RB888", "ZN888", "SC888"],
    },
    "cluster_gross_cap": 1.0,             # max summed gross weight within a cluster
    "daily_loss_limit_pct": 0.03,         # flatten + block new opens when day PnL <= -limit (resets every trading day)
    # 2026-07-26 审核后新增（研究用，默认禁用/None）：与 daily_loss_limit_pct 不同，
    # 本项是从组合权益历史峰值起算、跨交易日不重置的持久性回撤熔断——用于防止
    # daily_loss_limit_pct 挡不住的"每天各亏一点、累计慢性失血"场景。设为 0~1
    # 之间的小数（如 0.10）以启用：一旦当前权益相对历史峰值回撤达到该比例，
    # PortfolioCoordinator 的 weight-based replay 路径会记录触发、写入簿记型
    # flat_events 并阻断后续新开仓；sizing_model="risk" 且 portfolio_risk="on"
    # 的联合回放路径（PortfolioLedger）会执行真实 Position 强平并阻断新开仓。
    # 两条路径都不会随交易日切换自动解除。
    "max_drawdown_breaker_pct": None,
    "risk_parity_lookback": 60,           # trade-period bars used for per-symbol volatility estimate

    # HTML visual report toggle. Default False keeps existing report dicts byte-for-byte
    # identical for callers/tests that do not opt in.
    # html_report_dir="" means "use html_report.default_html_report_dir()"; kept as a
    # simple literal (not a computed Path expression) so the project_version_freshness
    # sync-check gate's restricted config-dict evaluator can fingerprint this file.
    "html_report_enabled": False,
    "html_report_dir": "",

    "contract_specs": {
        # Multiplier (合约乘数), tick (最小变动价位), margin_rate (交易所最低交易保证金率).
        # These are EXCHANGE-MINIMUM margin rates for research only, not production/broker rates.
        # Risk reports expose margin_model_caveat: exchange-minimum margin rates
        # are used for research bookkeeping only; maintenance margin, broker
        # add-ons, margin calls, and broker forced liquidation are not modeled.
        # Sourced 2026-07-11 from the exchanges' own published contract rules.
        "AP888": {"multiplier": 10,   "tick": 1.0, "margin_rate": 0.07},
        # source: CZCE 苹果期货合约规则 (czce.com.cn/cn/rootfiles/2021/09/09/1605597612939463-1605597612959828.pdf)
        "RB888": {"multiplier": 10,   "tick": 1.0, "margin_rate": 0.05},
        # source: SHFE 螺纹钢期货合约(修订版) (shfe.com.cn/products/futures/metal/ferrousandpreciousmetal/rb_f/standard_rb_f/202312/t20231205_327324.html)
        "SC888": {"multiplier": 1000, "tick": 0.1, "margin_rate": 0.05},
        # source: INE/SHFE 原油期货标准合约(SC) (ine.com.cn/products/futures/energyandchemical/sc_f/standard_sc_f/202312/t20231205_802540.html)
        "A888":  {"multiplier": 10,   "tick": 1.0, "margin_rate": 0.05},
        # source: DCE 黄大豆1号(A)期货合约及交割要素 (dce.com.cn ... 附件3:各品种合约)
        "ZN888": {"multiplier": 5,    "tick": 5.0, "margin_rate": 0.05},
        # source: SHFE 锌期货合约(修订版) (shfe.com.cn/products/futures/metal/nonferrousmetal/zn_f/standard_zn_f/202312/t20231205_309038.html)
    },
}

# 回测参数
BACKTEST_CONFIG = {
    "start_date": "2023-01-01",
    "end_date": "2025-12-31",
    "initial_capital": 1000000,
    "commission_rate": 0.0001,   # 万一手续费（期货实际成本）
    "slippage": 0.0005,          # 0.05%滑点
}

# Cost model disclosure for formal reports:
# transaction_cost_model = round_trip_commission_plus_single_side_slippage
# slippage_application = single-side per round-trip
# round_trip_cost_formula = 2 * commission_rate + slippage

# 信号版本
SIGNAL_VERSION = "V260615"
