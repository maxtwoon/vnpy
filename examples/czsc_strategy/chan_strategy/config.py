"""缠论择时策略配置"""
import os
from pathlib import Path

# 数据库路径
SQLITE_DB_PATH = os.getenv(
    "CHAN_SQLITE_DB_PATH",
    r"D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db"
)

# 策略参数
STRATEGY_CONFIG = {
    "base_freq": "5分钟",      # 基础周期
    "trade_freq": "30分钟",    # 交易周期
    "confirm_freq": "5分钟",   # 次级别确认周期
    "filter_freq": "日线",     # 环境过滤周期

    # 仓位管理
    "total_capital": 1000000,
    "pos_1buy": 0.10,          # 一买仓位10%（左侧试仓）
    "pos_2buy": 0.20,          # 二买仓位20%
    "pos_3buy": 0.30,          # 三买仓位30%
    "enable_short": False,     # 是否启用一卖/二卖/三卖空头子策略
    "enable_short_symbols": None,  # Research-only short enable list; None means all when enable_short=True.
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

    # Research-only execution switches. None / empty keeps baseline behavior.
    "max_2buy_entry_vs_anchor_pct": None,
    "enable_2buy_symbols": None,
    "trailing_overrides": {},
}

# 回测参数
BACKTEST_CONFIG = {
    "start_date": "2023-01-01",
    "end_date": "2025-12-31",
    "initial_capital": 1000000,
    "commission_rate": 0.0001,   # 万一手续费（期货实际成本）
    "slippage": 0.0005,          # 0.05%滑点
}

# 信号版本
SIGNAL_VERSION = "V260615"
