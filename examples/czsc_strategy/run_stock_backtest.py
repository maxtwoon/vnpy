"""
缠论多时间周期策略 — tushare 小市值股票回测
========================================
使用tushare获取上证/深证/创业板各3只（共9只）小市值股票的历史数据，
运行CzscMultiTimeframeStrategy回测并对比绩效。

选股条件：
- 总市值 < 100亿
- 排除ST/退市股票
- 换手率 > 0.5%（保证流动性）
- 上市时间 <= 2020年（相对稳定）
- 各板块按市值从大到小选3只（在100亿以下选较大的，流动性更好）

数据说明：
- 优先尝试1分钟数据（需tushare高级权限，5000积分以上）
- 若1分钟不可用，回退至5分钟数据，并适配策略参数
- 最终回退至日线数据（策略效果受限，仅作参考）

使用方式：
    pip install tushare
    python run_stock_backtest.py
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

# 路径设置 — 确保能导入同目录下的策略模块
sys.path.insert(0, os.path.dirname(__file__))

import tushare as ts

from vnpy.trader.object import BarData, TradeData, OrderData
from vnpy.trader.constant import Exchange, Interval, Direction, Offset, Status, OrderType

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

TUSHARE_TOKEN = "da1f00839c22e497ddd81a46973751bc84315ba33d96472fd10547ca"

# 股票列表（上证/深证/创业板各3只小市值股票，市值<100亿）
# 选股日期: 2024-12-31，按市值从大到小排序（在100亿以下选较大的，流动性更好）
STOCKS = [
    # 上证主板（3只）
    {"ts_code": "600133.SH", "symbol": "600133", "exchange": Exchange.SSE, "name": "东湖高新", "board": "上证", "mv_yi": 99.7, "turnover": 2.27, "industry": "环境保护"},
    {"ts_code": "603220.SH", "symbol": "603220", "exchange": Exchange.SSE, "name": "中贝通信", "board": "上证", "mv_yi": 99.7, "turnover": 5.48, "industry": "通信设备"},
    {"ts_code": "600114.SH", "symbol": "600114", "exchange": Exchange.SSE, "name": "东睦股份", "board": "上证", "mv_yi": 99.7, "turnover": 3.37, "industry": "机械基件"},
    # 深证主板（3只）
    {"ts_code": "002036.SZ", "symbol": "002036", "exchange": Exchange.SZSE, "name": "联创电子", "board": "深证", "mv_yi": 99.6, "turnover": 3.07, "industry": "元器件"},
    {"ts_code": "002928.SZ", "symbol": "002928", "exchange": Exchange.SZSE, "name": "华夏航空", "board": "深证", "mv_yi": 99.2, "turnover": 0.73, "industry": "空运"},
    {"ts_code": "002158.SZ", "symbol": "002158", "exchange": Exchange.SZSE, "name": "汉钟精机", "board": "深证", "mv_yi": 99.0, "turnover": 1.18, "industry": "工程机械"},
    # 创业板（3只）
    {"ts_code": "300256.SZ", "symbol": "300256", "exchange": Exchange.SZSE, "name": "星星科技", "board": "创业板", "mv_yi": 99.4, "turnover": 6.42, "industry": "元器件"},
    {"ts_code": "300655.SZ", "symbol": "300655", "exchange": Exchange.SZSE, "name": "晶瑞电材", "board": "创业板", "mv_yi": 99.2, "turnover": 1.90, "industry": "半导体"},
    {"ts_code": "300634.SZ", "symbol": "300634", "exchange": Exchange.SZSE, "name": "彩讯股份", "board": "创业板", "mv_yi": 98.4, "turnover": 3.67, "industry": "软件服务"},
]

# 回测参数
START_DATE = "20230101"
END_DATE = "20241231"
CAPITAL = 1_000_000  # 初始资金100万

# ---------------------------------------------------------------------------
# 数据获取与转换
# ---------------------------------------------------------------------------


def download_stock_data(pro, stock: dict) -> tuple[list[BarData], str]:
    """从tushare下载股票分钟级数据并转换为BarData列表。

    按优先级尝试：
    1. 1分钟数据 (stk_mins / pro_bar)
    2. 5分钟数据 (stk_mins / pro_bar)
    3. 日线数据 (daily)

    Returns:
        (bars, freq_label): K线列表和周期标签（如"1min"/"5min"/"daily"）
    """
    ts_code = stock["ts_code"]
    symbol = stock["symbol"]
    exchange = stock["exchange"]

    # --- 尝试1分钟数据 ---
    bars, freq_label = _try_minute_data(pro, ts_code, symbol, exchange, freq="1min")
    if bars:
        return bars, freq_label

    # --- 尝试5分钟数据 ---
    bars, freq_label = _try_minute_data(pro, ts_code, symbol, exchange, freq="5min")
    if bars:
        return bars, freq_label

    # --- 回退到日线数据 ---
    print(f"  分钟数据不可用，回退至日线数据（策略效果将受限）")
    bars = _try_daily_data(pro, ts_code, symbol, exchange)
    if bars:
        return bars, "daily"

    return [], ""


def _try_minute_data(
    pro, ts_code: str, symbol: str, exchange: Exchange, freq: str
) -> tuple[list[BarData], str]:
    """尝试通过tushare获取分钟级数据。"""
    print(f"  尝试获取 {freq} 数据...")

    df = None

    # 方式1：stk_mins 接口
    try:
        ts_freq = "1min" if freq == "1min" else "5min"
        df = pro.stk_mins(
            ts_code=ts_code,
            start_date=START_DATE + " 09:00:00",
            end_date=END_DATE + " 15:00:00",
            freq=ts_freq,
        )
        if df is not None and len(df) > 0:
            print(f"  [stk_mins] 获取到 {len(df)} 条 {freq} 数据")
    except Exception as e:
        print(f"  [stk_mins] {freq} 接口调用失败: {e}")
        df = None

    # 方式2：ts.pro_bar 接口
    if df is None or len(df) == 0:
        try:
            bar_freq = "1min" if freq == "1min" else "5min"
            df = ts.pro_bar(
                ts_code=ts_code,
                freq=bar_freq,
                start_date=START_DATE,
                end_date=END_DATE,
            )
            if df is not None and len(df) > 0:
                print(f"  [pro_bar] 获取到 {len(df)} 条 {freq} 数据")
        except Exception as e:
            print(f"  [pro_bar] {freq} 接口调用失败: {e}")
            df = None

    if df is None or len(df) == 0:
        print(f"  {freq} 数据获取失败")
        return [], ""

    bars = _df_to_bars(df, symbol, exchange, freq)
    return bars, freq


def _try_daily_data(
    pro, ts_code: str, symbol: str, exchange: Exchange
) -> list[BarData]:
    """获取日线数据作为最终回退方案。"""
    print(f"  尝试获取日线数据...")
    try:
        df = pro.daily(
            ts_code=ts_code, start_date=START_DATE, end_date=END_DATE
        )
        if df is not None and len(df) > 0:
            print(f"  获取到 {len(df)} 条日线数据")
            return _df_to_bars(df, symbol, exchange, "daily")
    except Exception as e:
        print(f"  日线数据获取失败: {e}")
    return []


def _df_to_bars(
    df: pd.DataFrame, symbol: str, exchange: Exchange, freq: str
) -> list[BarData]:
    """将tushare DataFrame转换为vnpy BarData列表。"""
    bars = []

    # 确定时间列名
    if "trade_time" in df.columns:
        time_col = "trade_time"
    elif "trade_date" in df.columns:
        time_col = "trade_date"
    else:
        print(f"  [警告] DataFrame中未找到时间列，列名: {list(df.columns)}")
        return []

    # 确定周期
    if freq == "1min":
        interval = Interval.MINUTE
    elif freq == "5min":
        interval = Interval.MINUTE  # vnpy中5分钟也用MINUTE，由BarGenerator处理
    else:
        interval = Interval.DAILY

    # 按时间排序（tushare数据可能是倒序）
    df = df.sort_values(by=time_col).reset_index(drop=True)

    for _, row in df.iterrows():
        try:
            dt = pd.to_datetime(row[time_col])

            bar = BarData(
                symbol=symbol,
                exchange=exchange,
                datetime=dt,
                interval=interval,
                open_price=float(row["open"]),
                high_price=float(row["high"]),
                low_price=float(row["low"]),
                close_price=float(row["close"]),
                volume=float(row.get("vol", row.get("volume", 0))),
                turnover=float(row.get("amount", 0)),
                gateway_name="tushare",
            )
            bars.append(bar)
        except Exception as e:
            # 跳过有问题的行
            continue

    return bars


# ---------------------------------------------------------------------------
# Mock CTA 引擎
# ---------------------------------------------------------------------------


class MockCtaEngine:
    """模拟CTA引擎，用于独立回测。

    核心职责：
    - 模拟 send_order（立即成交）
    - 维护持仓和成交记录
    - 提供策略所需的基础接口
    """

    def __init__(self):
        self.trades: list[dict] = []
        self.order_counter: int = 0
        self.trade_counter: int = 0
        self.logs: list[str] = []

    def send_order(
        self,
        strategy,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
        stop: bool = False,
        lock: bool = False,
        net: bool = False,
    ) -> list[str]:
        """模拟发单 — 简化为立即成交。"""
        self.order_counter += 1
        orderid = f"MOCK.{self.order_counter:06d}"

        self.trade_counter += 1
        tradeid = f"MOCK.{self.trade_counter:06d}"

        # 记录成交
        # 从 vt_symbol 解析 symbol 和 exchange
        vt_sym = strategy.vt_symbol
        if "." in vt_sym:
            sym, exch = vt_sym.split(".", 1)
        else:
            sym, exch = vt_sym, ""
        trade = {
            "tradeid": tradeid,
            "orderid": orderid,
            "symbol": sym,
            "exchange": exch,
            "direction": direction,
            "offset": offset,
            "price": price,
            "volume": volume,
            "datetime": datetime.now(),
            "pnl": 0.0,
        }
        self.trades.append(trade)

        # 通知策略成交回调
        trade_data = TradeData(
            symbol=sym,
            exchange=strategy.exchange if hasattr(strategy, 'exchange') else Exchange.SSE,
            orderid=orderid,
            tradeid=tradeid,
            direction=direction,
            offset=offset,
            price=price,
            volume=volume,
            gateway_name="MOCK",
        )
        strategy.on_trade(trade_data)

        # 同步更新策略的 pos（新版 vnpy 不自动更新）
        # vnpy 常规：
        #   buy()   -> LONG  + OPEN   开多
        #   sell()  -> SHORT + CLOSE  平多
        #   short() -> SHORT + OPEN   开空
        #   cover() -> LONG  + CLOSE  平空
        if direction == Direction.LONG and offset in (Offset.OPEN, Offset.NONE):
            # buy() 开多
            strategy.pos += volume
        elif direction == Direction.SHORT and offset == Offset.CLOSE:
            # sell() 平多
            strategy.pos -= volume
        elif direction == Direction.SHORT and offset in (Offset.OPEN, Offset.NONE):
            # short() 开空
            strategy.pos -= volume
        elif direction == Direction.LONG and offset == Offset.CLOSE:
            # cover() 平空
            strategy.pos += volume

        return [orderid]

    def cancel_order(self, strategy, vt_orderid: str):
        """模拟撤单 — 简化为空操作。"""
        pass

    def cancel_all(self, strategy):
        """撤销策略所有未成交单。"""
        pass

    def write_log(self, msg: str, strategy=None):
        """记录日志。"""
        self.logs.append(msg)

    def load_bar(
        self, vt_symbol: str = None, days: int = 0, interval=Interval.MINUTE, callback=None, use_database=False
    ):
        """回测中不需要额外加载。"""
        return []

    def put_event(self, strategy):
        """通知UI更新 — 简化为空操作。"""
        pass

    def put_strategy_event(self, strategy):
        """通知策略状态更新 — 简化为空操作。"""
        pass

    def send_email(self, msg: str, strategy):
        """发送邮件 — 简化为空操作。"""
        pass

    def sync_strategy_data(self, strategy):
        """同步策略数据 — 简化为空操作。"""
        pass

    def load_tick(self, vt_symbol: str, days: int, callback):
        """加载Tick数据 — 简化为空操作。"""
        return []

    def get_pricetick(self, strategy) -> float:
        """获取最小价格变动。"""
        return 0.01

    def get_size(self, strategy) -> float:
        """获取合约乘数 — 股票为1。"""
        return 1

    def get_capital(self, strategy) -> float:
        """获取账户资金。"""
        return CAPITAL

    def get_engine_type(self):
        """获取引擎类型 — 返回回测类型。"""
        from vnpy_ctastrategy.base import EngineType
        return EngineType.BACKTESTING


# ---------------------------------------------------------------------------
# 简化回测器
# ---------------------------------------------------------------------------


@dataclass
class BacktestTrade:
    """回测成交记录。"""
    tradeid: str
    direction: Direction
    offset: Offset
    price: float
    volume: float
    datetime: datetime
    pnl: float = 0.0


class SimpleBacktester:
    """简化回测器 — 直接推送数据到策略。

    工作流程：
    1. 创建MockCtaEngine和策略实例
    2. 逐bar推送K线到策略的on_bar回调
    3. 跟踪持仓变化和成交记录
    4. 计算绩效指标
    """

    def __init__(
        self,
        strategy_class,
        setting: dict,
        symbol: str,
        exchange: Exchange,
        capital: float = CAPITAL,
    ):
        self.strategy_class = strategy_class
        self.setting = setting
        self.symbol = symbol
        self.exchange = exchange
        self.capital = capital

        # 回测结果
        self.trades: list[BacktestTrade] = []
        self.daily_pnl: list[float] = []
        self.net_values: list[float] = []
        self.position: float = 0  # 正=多头，负=空头
        self.avg_price: float = 0.0  # 持仓均价
        self.realized_pnl: float = 0.0  # 已实现盈亏
        self.commission_rate: float = 0.0003  # 手续费率（万三）
        self.stamp_tax_rate: float = 0.001  # 印花税（千一，仅卖出）

        # 策略实例和mock引擎
        self.engine: Optional[MockCtaEngine] = None
        self.strategy = None

    def run(self, bars: list[BarData], freq_label: str = "1min", disable_short: bool = False) -> dict:
        """运行回测。

        Args:
            bars: K线数据列表
            freq_label: 数据周期标签（"1min"/"5min"/"daily"）
            disable_short: 是否禁止开空（A股不支持双向交易时使用）

        Returns:
            绩效统计字典
        """
        if not bars:
            return {}

        # 创建mock引擎
        self.engine = MockCtaEngine()

        # 创建策略实例
        vt_symbol = f"{self.symbol}.{self.exchange.value}"
        self.strategy = self.strategy_class(
            cta_engine=self.engine,
            strategy_name="czsc_backtest",
            vt_symbol=vt_symbol,
            setting=self.setting,
        )

        # 适配5分钟数据：需要将策略的BarGenerator调整为直接接收5分钟K线
        # 原策略设计：on_bar接收1分钟 → bg_5m合成5分钟 → bg_30m合成30分钟 → bg_4h合成4小时
        # 如果数据本身是5分钟：需要跳过bg_5m，直接调用on_5min_bar
        if freq_label == "5min":
            self._patch_strategy_for_5min()

        # 初始化策略
        self.strategy.on_init()
        self.strategy.inited = True
        self.strategy.trading = True
        self.strategy.on_start()

        # 日线模式标记：禁止 on_30min_bar 内触发交易，避免同一日线 K 线内重复开关仓
        if freq_label == "daily":
            self.strategy._daily_mode = True
        else:
            self.strategy._daily_mode = False

        # 禁止开空模式：覆盖 _open_short 为空操作
        if disable_short:
            self.strategy._open_short = lambda price: None
            self.write_log_override = lambda msg: None  # 静默不输出

        # 注入自定义send_order以跟踪持仓
        original_send_order = self.strategy.buy

        # 逐bar推送
        prev_date = None
        daily_pnl = 0.0
        prev_realized_pnl = 0.0  # 用于计算每日新增已实现盈亏
        last_close = 0.0

        for i, bar in enumerate(bars):
            # 每日结算
            cur_date = bar.datetime.date() if hasattr(bar.datetime, 'date') else bar.datetime
            if prev_date is not None and cur_date != prev_date:
                self.daily_pnl.append(daily_pnl)
                daily_pnl = 0.0

            prev_date = cur_date
            last_close = bar.close_price

            # 推送K线到策略
            if freq_label == "5min":
                # 5分钟数据直接推送到5分钟回调
                self.strategy.on_5min_bar(bar)
            elif freq_label == "daily":
                # 日线模式：同一根K线依次更新三个周期
                # 关键：on_4hour_bar 和 on_30min_bar 只更新状态变量，不触发交易
                # 方法：调用前将 strategy.pos 设为 0（禁止开平仓），调用后恢复
                real_pos = self.strategy.pos

                # 1) 4小时：只更新 trend_4h（pos=0 时不会触发任何退出逻辑）
                self.strategy.pos = 0
                self.strategy.on_4hour_bar(bar)

                # 2) 30分钟：只更新 trend_30m/support_30m/resistance_30m/divergence_30m
                self.strategy.pos = 0
                self.strategy.on_30min_bar(bar)

                # 3) 恢复真实持仓，再执行 5 分钟交易逻辑
                self.strategy.pos = real_pos
                self.strategy.on_5min_bar(bar)

                # 4) 同步 backtester.position 与 strategy.pos（确保一致）
                self.position = self.strategy.pos
            else:
                # 1分钟数据 — 正常流程
                self.strategy.on_bar(bar)

            # 更新持仓盈亏
            if self.position != 0:
                unrealized = (bar.close_price - self.avg_price) * self.position
                # 扣除手续费
            else:
                unrealized = 0.0

            # 跟踪新增成交
            self._process_new_trades(bar.datetime)

            # 累积本日已实现盈亏（每日增量）
            daily_pnl += self.realized_pnl - prev_realized_pnl
            prev_realized_pnl = self.realized_pnl

        # 处理最后一日的盈亏
        self.daily_pnl.append(daily_pnl)

        # 计算绩效
        stats = self.calculate_statistics(bars)
        return stats

    def _patch_strategy_for_5min(self):
        """适配5分钟数据源：重写策略的BarGenerator结构。

        原策略：
          on_bar(1min) → bg_5m(5根1min) → on_5min_bar
                        bg_30m(30根1min) → on_30min_bar
                        bg_4h(4根1h=240根1min) → on_4hour_bar

        5分钟适配：
          每根5分钟K线直接触发on_5min_bar
          同时推送到bg_30m(6根5min→30min) 和 bg_4h(48根5min→4h)

        注意：BarGenerator的minute窗口合成逻辑基于1分钟K线的时间戳，
        5分钟数据需要自定义合成器。
        """
        from vnpy.trader.utility import BarGenerator

        # 替换bg_30m：从5分钟合成30分钟（6根5分钟）
        self.strategy.bg_30m = BarGenerator(
            lambda bar: None,  # 临时占位，稍后替换
            window=6,
            on_window_bar=self.strategy.on_30min_bar,
            interval=Interval.MINUTE,
        )

        # 替换bg_4h：从5分钟合成4小时（48根5分钟）
        # 但BarGenerator的HOUR模式是基于1分钟时间戳的，不适用于5分钟输入
        # 所以用MINUTE模式，window=48
        self.strategy.bg_4h = BarGenerator(
            lambda bar: None,
            window=48,
            on_window_bar=self.strategy.on_4hour_bar,
            interval=Interval.MINUTE,
        )

        # 保存原始on_5min_bar
        original_on_5min_bar = self.strategy.on_5min_bar

        # 创建新的on_5min_bar包装器，同时分发到30m和4h
        def on_5min_bar_wrapped(bar: BarData):
            # 先调用原始5分钟逻辑
            original_on_5min_bar(bar)
            # 分发到30分钟和4小时BarGenerator
            self.strategy.bg_30m.update_bar(bar)
            self.strategy.bg_4h.update_bar(bar)

        self.strategy.on_5min_bar = on_5min_bar_wrapped

    def _process_new_trades(self, bar_dt: datetime):
        """处理mock引擎中的新增成交，更新持仓和盈亏。"""
        if not self.engine:
            return

        # 获取新的成交（自上次处理以来的）
        start_idx = len(self.trades)
        for i in range(start_idx, len(self.engine.trades)):
            raw_trade = self.engine.trades[i]
            direction = raw_trade["direction"]
            offset = raw_trade["offset"]
            price = raw_trade["price"]
            volume = raw_trade["volume"]

            pnl = 0.0
            commission = 0.0

            # vnpy 常规：
            #   buy()   -> LONG  + OPEN   开多→ position+
            #   sell()  -> SHORT + CLOSE  平多→ position-
            #   short() -> SHORT + OPEN   开空→ position-
            #   cover() -> LONG  + CLOSE  平空→ position+
            if direction == Direction.LONG and offset in (Offset.OPEN, Offset.NONE):
                # buy() 开多
                old_pos = self.position
                old_avg = self.avg_price
                self.position += volume
                if self.position != 0:
                    self.avg_price = (
                        (old_pos * old_avg + volume * price) / self.position
                    )
                commission = price * volume * self.commission_rate
            elif direction == Direction.SHORT and offset == Offset.CLOSE:
                # sell() 平多
                pnl = (price - self.avg_price) * volume
                self.position -= volume
                commission = price * volume * self.commission_rate
                commission += price * volume * self.stamp_tax_rate  # 印花税
                if self.position <= 0:
                    self.position = 0
                    self.avg_price = 0.0
            elif direction == Direction.SHORT and offset in (Offset.OPEN, Offset.NONE):
                # short() 开空
                old_pos = abs(self.position)
                old_avg = self.avg_price
                self.position -= volume
                if self.position != 0:
                    self.avg_price = (
                        (old_pos * old_avg + volume * price) / abs(self.position)
                    )
                commission = price * volume * self.commission_rate
            elif direction == Direction.LONG and offset == Offset.CLOSE:
                # cover() 平空
                pnl = (self.avg_price - price) * volume
                self.position += volume
                commission = price * volume * self.commission_rate
                commission += price * volume * self.stamp_tax_rate
                if self.position >= 0:
                    self.position = 0
                    self.avg_price = 0.0

            net_pnl = pnl - commission
            self.realized_pnl += net_pnl

            bt_trade = BacktestTrade(
                tradeid=raw_trade["tradeid"],
                direction=direction,
                offset=offset,
                price=price,
                volume=volume,
                datetime=bar_dt,
                pnl=net_pnl,
            )
            self.trades.append(bt_trade)

    def calculate_statistics(self, bars: list[BarData]) -> dict:
        """计算绩效指标。"""
        if not bars:
            return {}

        total_pnl = self.realized_pnl

        # 未实现盈亏
        if self.position != 0 and self.avg_price != 0:
            last_price = bars[-1].close_price
            unrealized_pnl = (last_price - self.avg_price) * self.position
        else:
            unrealized_pnl = 0.0

        total_return = total_pnl / self.capital
        total_return_with_unrealized = (total_pnl + unrealized_pnl) / self.capital

        # 交易统计
        trade_count = len(self.trades)
        closed_trades = [t for t in self.trades if t.pnl != 0]
        win_trades = [t for t in closed_trades if t.pnl > 0]
        loss_trades = [t for t in closed_trades if t.pnl < 0]

        win_rate = len(win_trades) / len(closed_trades) if closed_trades else 0.0

        avg_profit = np.mean([t.pnl for t in win_trades]) if win_trades else 0.0
        avg_loss = np.mean([t.pnl for t in loss_trades]) if loss_trades else 0.0
        profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else float("inf")

        # 构建净值曲线（基于每日已实现盈亏）
        net_values = [self.capital]
        for pnl in self.daily_pnl:
            net_values.append(net_values[-1] + pnl)

        # 最大回撤
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        peak = net_values[0]
        for nv in net_values:
            if nv > peak:
                peak = nv
            dd = peak - nv
            dd_pct = dd / peak if peak > 0 else 0
            if dd_pct > max_drawdown_pct:
                max_drawdown = dd
                max_drawdown_pct = dd_pct

        # 夏普比率（基于日收益率）
        # 日线数据每天大多数交易为0，用非零收益日计算更合理
        if len(self.daily_pnl) > 1:
            daily_returns = np.array(self.daily_pnl) / self.capital
            nonzero_returns = daily_returns[daily_returns != 0]
            if len(nonzero_returns) > 1 and np.std(daily_returns) > 0:
                # 标准化到年化：乘以 sqrt(252)
                sharpe_ratio = (
                    np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
                )
            elif len(nonzero_returns) > 1:
                # 只用有交易的日期计算
                nonzero_mean = np.mean(nonzero_returns)
                nonzero_std = np.std(nonzero_returns)
                if nonzero_std > 0:
                    trade_freq = len(nonzero_returns) / len(daily_returns)
                    sharpe_ratio = nonzero_mean / nonzero_std * np.sqrt(252 * trade_freq)
                else:
                    sharpe_ratio = 1.0 if total_pnl > 0 else -1.0
            else:
                sharpe_ratio = 0.0
        else:
            sharpe_ratio = 0.0

        # 数据时间范围
        start_dt = bars[0].datetime
        end_dt = bars[-1].datetime
        trading_days = len(self.daily_pnl)

        stats = {
            "start_date": str(start_dt)[:10],
            "end_date": str(end_dt)[:10],
            "trading_days": trading_days,
            "total_bars": len(bars),
            "capital": self.capital,
            "total_pnl": total_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_return": total_return,
            "total_return_with_unrealized": total_return_with_unrealized,
            "trade_count": trade_count,
            "closed_trade_count": len(closed_trades),
            "win_count": len(win_trades),
            "loss_count": len(loss_trades),
            "win_rate": win_rate,
            "avg_profit": avg_profit,
            "avg_loss": avg_loss,
            "profit_loss_ratio": profit_loss_ratio,
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown_pct,
            "sharpe_ratio": sharpe_ratio,
            "final_position": self.position,
        }

        return stats


# ---------------------------------------------------------------------------
# 回测运行
# ---------------------------------------------------------------------------


def run_backtest(bars: list[BarData], stock: dict, freq_label: str) -> dict:
    """为单只股票运行回测。"""
    from czsc_multi_timeframe_strategy import CzscMultiTimeframeStrategy

    # 基础参数
    setting = {
        "fixed_size": 1,
        "max_pos": 3,
        "stop_loss_pct": 0.03,
        "take_profit_pct": 0.05,
        "trailing_stop_pct": 0.025,
        "min_bars_5m": 30,
        "min_bars_30m": 20,
        "min_bars_4h": 10,
        "support_tolerance_pct": 0.05,
    }

    # 根据数据周期调低K线数阀值
    if freq_label in ("5min", "daily"):
        setting["min_bars_5m"] = 20
        setting["min_bars_30m"] = 15
        setting["min_bars_4h"] = 8

    # 按股票特性差异化参数调整
    ts_code = stock.get("ts_code", "")
    industry = stock.get("industry", "")

    # 小市值股票波动性较大，统一适当放宽止损和止盈
    if industry in ("元器件", "半导体", "软件服务", "通信设备"):
        # 科技类股波动大，需要宽止损以容忍震荡
        setting["stop_loss_pct"] = 0.05        # 宽止损（容忍大震荡）
        setting["take_profit_pct"] = 0.10      # 大止盈（捕捉趋势行情）
        setting["trailing_stop_pct"] = 0.04    # 较紧的移动止损
        setting["support_tolerance_pct"] = 0.08  # 增加入场机会
    elif industry in ("环境保护", "机械基件", "工程机械", "空运"):
        # 传统行业波动中等
        setting["stop_loss_pct"] = 0.04
        setting["take_profit_pct"] = 0.08
        setting["trailing_stop_pct"] = 0.03
        setting["support_tolerance_pct"] = 0.06

    backtester = SimpleBacktester(
        strategy_class=CzscMultiTimeframeStrategy,
        setting=setting,
        symbol=stock["symbol"],
        exchange=stock["exchange"],
        capital=CAPITAL,
    )

    # A股不能做空，统一禁止开空
    stats = backtester.run(bars, freq_label=freq_label, disable_short=True)
    return stats


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------


def print_report(name: str, stats: dict):
    """打印单只股票的回测报告。"""
    if not stats:
        print(f"  {name}: 无回测结果")
        return

    print(f"\n  ┌─ 回测结果: {name} ─────────────────────────")
    print(f"  │ 回测区间:   {stats.get('start_date', 'N/A')} ~ {stats.get('end_date', 'N/A')}")
    print(f"  │ 交易天数:   {stats.get('trading_days', 0)}")
    print(f"  │ K线数量:    {stats.get('total_bars', 0)}")
    print(f"  │")
    print(f"  │ 初始资金:   {stats.get('capital', 0):>12,.2f}")
    print(f"  │ 已实现盈亏: {stats.get('total_pnl', 0):>12,.2f}")
    print(f"  │ 未实现盈亏: {stats.get('unrealized_pnl', 0):>12,.2f}")
    print(f"  │ 收益率:     {stats.get('total_return', 0):>11.2%}")
    print(f"  │ 含浮动收益率: {stats.get('total_return_with_unrealized', 0):>9.2%}")
    print(f"  │")
    print(f"  │ 总交易次数: {stats.get('trade_count', 0)}")
    print(f"  │ 平仓交易:   {stats.get('closed_trade_count', 0)}")
    print(f"  │ 盈利次数:   {stats.get('win_count', 0)}")
    print(f"  │ 亏损次数:   {stats.get('loss_count', 0)}")
    print(f"  │ 胜率:       {stats.get('win_rate', 0):>11.2%}")
    print(f"  │")
    print(f"  │ 平均盈利:   {stats.get('avg_profit', 0):>12,.2f}")
    print(f"  │ 平均亏损:   {stats.get('avg_loss', 0):>12,.2f}")
    print(f"  │ 盈亏比:     {stats.get('profit_loss_ratio', 0):>11.2f}")
    print(f"  │")
    print(f"  │ 最大回撤:   {stats.get('max_drawdown', 0):>12,.2f}")
    print(f"  │ 最大回撤率: {stats.get('max_drawdown_pct', 0):>10.2%}")
    print(f"  │ 夏普比率:   {stats.get('sharpe_ratio', 0):>11.2f}")
    print(f"  └{'─' * 42}")


def print_comparison(results: dict, stocks: list):
    """打印各股票回测对比汇总，包含板块信息。"""
    # 构建股票名称到板块的映射
    name_to_board = {s["name"]: s.get("board", "") for s in stocks}
    name_to_mv = {s["name"]: s.get("mv_yi", 0) for s in stocks}
    name_to_industry = {s["name"]: s.get("industry", "") for s in stocks}

    print(f"\n{'=' * 100}")
    print("缠论多时间周期策略 — 小市值股票回测对比报告")
    print(f"{'=' * 100}")

    # 选股信息表
    print("\n一、选股信息")
    print("-" * 100)
    print(
        f"{'股票':<10} {'板块':<8} {'市值(亿)':>10} {'换手率(%)':>10} {'行业':<10} {'选股理由'}"
    )
    print("-" * 100)
    for s in stocks:
        name = s["name"]
        board = s.get("board", "")
        mv = s.get("mv_yi", 0)
        tr = s.get("turnover", 0)
        ind = s.get("industry", "")
        reason = f"市值{mv}亿<100亿, 换手率{tr}%>0.5%, {board}板块流动性较好"
        print(f"{name:<10} {board:<8} {mv:>10.1f} {tr:>10.2f} {ind:<10} {reason}")

    # 回测绩效对比表
    print(f"\n二、回测绩效对比")
    print("-" * 100)
    print(
        f"{'股票':<10} {'板块':<8} {'收益率':>10} {'含浮动收益率':>12} "
        f"{'交易次数':>8} {'胜率':>8} {'最大回撤率':>10} {'夏普比率':>10}"
    )
    print("-" * 100)

    for s in stocks:
        name = s["name"]
        stats = results.get(name, {})
        board = name_to_board.get(name, "")

        if not stats:
            print(f"{name:<10} {board:<8} {'N/A':>10}")
            continue

        total_return = stats.get("total_return", 0)
        total_return_uf = stats.get("total_return_with_unrealized", 0)
        trade_count = stats.get("trade_count", 0)
        win_rate = stats.get("win_rate", 0)
        max_dd = stats.get("max_drawdown_pct", 0)
        sharpe = stats.get("sharpe_ratio", 0)

        print(
            f"{name:<10} {board:<8} {total_return:>9.2%} {total_return_uf:>11.2%} "
            f"{trade_count:>8} {win_rate:>7.2%} {max_dd:>9.2%} {sharpe:>10.2f}"
        )

    # 按板块汇总平均绩效
    print(f"\n三、按板块汇总平均绩效")
    print("-" * 100)
    print(
        f"{'板块':<10} {'股票数':>8} {'平均收益率':>12} {'平均含浮动收益率':>16} "
        f"{'平均胜率':>10} {'平均最大回撤率':>14} {'平均夏普比率':>12}"
    )
    print("-" * 100)

    board_stats = {}
    for s in stocks:
        name = s["name"]
        board = s.get("board", "")
        stats = results.get(name, {})
        if not stats:
            continue
        if board not in board_stats:
            board_stats[board] = []
        board_stats[board].append(stats)

    for board, stats_list in board_stats.items():
        n = len(stats_list)
        avg_return = np.mean([s.get("total_return", 0) for s in stats_list])
        avg_return_uf = np.mean([s.get("total_return_with_unrealized", 0) for s in stats_list])
        avg_win_rate = np.mean([s.get("win_rate", 0) for s in stats_list])
        avg_max_dd = np.mean([s.get("max_drawdown_pct", 0) for s in stats_list])
        avg_sharpe = np.mean([s.get("sharpe_ratio", 0) for s in stats_list])

        print(
            f"{board:<10} {n:>8} {avg_return:>11.2%} {avg_return_uf:>15.2%} "
            f"{avg_win_rate:>9.2%} {avg_max_dd:>13.2%} {avg_sharpe:>11.2f}"
        )

    # 全部汇总
    all_stats = [results.get(s["name"], {}) for s in stocks if results.get(s["name"], {})]
    if all_stats:
        n = len(all_stats)
        avg_return = np.mean([s.get("total_return", 0) for s in all_stats])
        avg_return_uf = np.mean([s.get("total_return_with_unrealized", 0) for s in all_stats])
        avg_win_rate = np.mean([s.get("win_rate", 0) for s in all_stats])
        avg_max_dd = np.mean([s.get("max_drawdown_pct", 0) for s in all_stats])
        avg_sharpe = np.mean([s.get("sharpe_ratio", 0) for s in all_stats])
        print(
            f"{'全部':<10} {n:>8} {avg_return:>11.2%} {avg_return_uf:>15.2%} "
            f"{avg_win_rate:>9.2%} {avg_max_dd:>13.2%} {avg_sharpe:>11.2f}"
        )

    print(f"{'=' * 100}")
    print()
    print("注意事项:")
    print("  1. 股票回测中做空受限（A股T+1且无融券），空头信号实际无法执行")
    print("  2. 未考虑涨跌停限制，实际交易可能无法以信号价成交")
    print("  3. 手续费按万三计算，印花税按千一（仅卖出）计算")
    print("  4. 若使用日线数据，策略的缠论分析精度将显著降低")
    print("  5. 本回测仅为策略逻辑验证，不构成投资建议")
    print("  6. 选股条件：市值<100亿、换手率>0.5%、上市<=2020年、排除ST")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def main():
    """主入口：获取数据 → 逐股回测 → 对比报告。"""
    print("=" * 60)
    print("缠论多时间周期策略 — tushare 股票回测")
    print("=" * 60)
    print(f"数据源: tushare")
    print(f"回测区间: {START_DATE} ~ {END_DATE}")
    print(f"初始资金: {CAPITAL:,.0f}")
    print()

    # 1. 初始化tushare
    try:
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
        print("tushare 初始化成功")
    except Exception as e:
        print(f"[错误] tushare 初始化失败: {e}")
        print("请确保已安装 tushare: pip install tushare")
        return

    # 2. 获取各股票数据并运行回测
    results = {}
    for stock in STOCKS:
        print(f"\n{'=' * 60}")
        print(f"开始处理: {stock['name']} ({stock['ts_code']})")
        print(f"{'=' * 60}")

        # 获取数据
        bars, freq_label = download_stock_data(pro, stock)
        if not bars:
            print(f"  [警告] {stock['name']} 数据获取失败，跳过")
            results[stock["name"]] = {}
            continue

        print(f"  获取到 {len(bars)} 根K线 (周期: {freq_label})")
        print(f"  时间范围: {bars[0].datetime} ~ {bars[-1].datetime}")

        # 运行回测
        try:
            stats = run_backtest(bars, stock, freq_label)
            results[stock["name"]] = stats
            print_report(stock["name"], stats)
        except Exception as e:
            print(f"  [错误] 回测执行失败: {e}")
            import traceback
            traceback.print_exc()
            results[stock["name"]] = {}

    # 3. 输出对比报告
    print_comparison(results, STOCKS)


if __name__ == "__main__":
    main()
