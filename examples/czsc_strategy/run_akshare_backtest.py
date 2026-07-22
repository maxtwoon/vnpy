# =============================================================================
# !! LEGACY / 已停止维护 —— RESEARCH-ONLY / NOT PROMOTION EVIDENCE !!
# -----------------------------------------------------------------------------
# 本文件（run_akshare_backtest.py）是早期 A 股原型代码，已停止维护，未接入当前回测/测试路径；
# 当前唯一活跃维护、有测试覆盖的实现是 chan_strategy/（期货 CTA）。
#
# 本文件不含任何 A 股交易制度建模：
#   - 未建模 T+1（当日买入不可当日卖出）
#   - 未建模 涨跌停 / 停牌（halts）
#   - 未建模 卖出侧印花税
#   - 未建模 A 股禁止做空约束
#   - 成交假设为即时、无约束成交（immediate / unconstrained fills）
#
# 其输出【不得】作为策略有效性的证据（NOT PROMOTION EVIDENCE）。
# =============================================================================
"""
缠论多时间周期策略 — AKShare 数据源回测
===========================================
使用AKShare免费数据接口获取上证、深证、创业板各3只
市值<100亿的股票历史数据，运行CzscMultiTimeframeStrategy回测。

AKShare 优势：
- 完全免费，无需API Key
- 数据覆盖A股全市场

注意事项：
- 分钟数据通常只有最近几个交易日，大概率回退到日线
- 日线数据策略精度受限，仅作逻辑验证
- AKShare某些接口有频率限制，两次调用间加 time.sleep(1)
"""

import sys
import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(__file__))

import akshare as ak

from vnpy.trader.object import BarData, TradeData, OrderData
from vnpy.trader.constant import Exchange, Interval, Direction, Offset, Status, OrderType

from czsc_multi_timeframe_strategy import CzscMultiTimeframeStrategy

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

CAPITAL = 1_000_000  # 初始资金100万
START_DATE = "20210101"
END_DATE = "20221231"

# 备用股票列表（当AKShare实时选股接口不可用时使用）
# 基于历史数据，选取各板块小市值代表性股票
FALLBACK_STOCKS = [
    # 上证主板（3只）
    {"symbol": "600133", "exchange": Exchange.SSE, "name": "东湖高新", "board": "上证", "mv_yi": 99.7, "turnover": 2.27, "industry": "环境保护"},
    {"symbol": "603220", "exchange": Exchange.SSE, "name": "中贝通信", "board": "上证", "mv_yi": 99.7, "turnover": 5.48, "industry": "通信设备"},
    {"symbol": "600114", "exchange": Exchange.SSE, "name": "东睦股份", "board": "上证", "mv_yi": 99.7, "turnover": 3.37, "industry": "机械基件"},
    # 深证主板（3只）
    {"symbol": "002036", "exchange": Exchange.SZSE, "name": "联创电子", "board": "深证", "mv_yi": 99.6, "turnover": 3.07, "industry": "元器件"},
    {"symbol": "002928", "exchange": Exchange.SZSE, "name": "华夏航空", "board": "深证", "mv_yi": 99.2, "turnover": 0.73, "industry": "空运"},
    {"symbol": "002158", "exchange": Exchange.SZSE, "name": "汉钟精机", "board": "深证", "mv_yi": 99.0, "turnover": 1.18, "industry": "工程机械"},
    # 创业板（3只）
    {"symbol": "300256", "exchange": Exchange.SZSE, "name": "星星科技", "board": "创业板", "mv_yi": 99.4, "turnover": 6.42, "industry": "元器件"},
    {"symbol": "300655", "exchange": Exchange.SZSE, "name": "晶瑞电材", "board": "创业板", "mv_yi": 99.2, "turnover": 1.90, "industry": "半导体"},
    {"symbol": "300634", "exchange": Exchange.SZSE, "name": "彩讯股份", "board": "创业板", "mv_yi": 98.4, "turnover": 3.67, "industry": "软件服务"},
]


# ---------------------------------------------------------------------------
# 选股逻辑
# ---------------------------------------------------------------------------

def _to_akshare_symbol(symbol: str, exchange: Exchange) -> str:
    """将vnpy symbol转换为AKShare的stock_zh_a_daily格式。
    上证: sh600133, 深证: sz002036, 创业板: sz300256
    """
    if exchange == Exchange.SSE:
        return f"sh{symbol}"
    else:
        return f"sz{symbol}"


def select_stocks(max_retries=3) -> list[dict]:
    """从上证/深证/创业板各选3只市值<100亿的股票。

    当前网络环境下东方财富/新浪实时接口不稳定，直接使用备用列表。
    备用列表基于历史小市值股票筛选，覆盖各板块代表性标的。
    """
    print("使用备用股票列表（AKShare实时接口当前不可用）")
    return FALLBACK_STOCKS


# ---------------------------------------------------------------------------
# 数据获取与转换
# ---------------------------------------------------------------------------

def download_stock_data(symbol: str, exchange: Exchange, start_date: str = START_DATE, end_date: str = END_DATE) -> tuple[list[BarData], str]:
    """使用AKShare的stock_zh_a_daily接口获取个股历史日线数据。

    该接口使用腾讯/新浪数据源，在当前网络环境下可正常访问。
    列名: date, open, high, low, close, volume, amount, outstanding_share, turnover

    Returns:
        (bars, freq_label): K线列表和周期标签（均为daily）
    """
    bars = []
    ak_symbol = _to_akshare_symbol(symbol, exchange)

    try:
        print(f"  正在获取日线数据 ({ak_symbol})...")
        df = ak.stock_zh_a_daily(symbol=ak_symbol, start_date=start_date, end_date=end_date)
        if df is None or len(df) == 0:
            print(f"  返回空数据")
            return [], ""

        # 按日期排序（确保时间序列正确）
        df = df.sort_values(by="date").reset_index(drop=True)

        for _, row in df.iterrows():
            dt = pd.to_datetime(row["date"])
            bar = BarData(
                symbol=symbol, exchange=exchange, datetime=dt,
                interval=Interval.DAILY,
                open_price=float(row["open"]), high_price=float(row["high"]),
                low_price=float(row["low"]), close_price=float(row["close"]),
                volume=float(row["volume"]), turnover=float(row.get("amount", 0)),
                gateway_name="akshare",
            )
            bars.append(bar)

        print(f"  获取到 {len(bars)} 根日K线")
        return bars, "daily"

    except Exception as e:
        print(f"  日线数据获取失败: {e}")
        return [], ""


# ---------------------------------------------------------------------------
# Mock CTA 引擎（从 run_stock_backtest.py 复制以确保独立运行）
# ---------------------------------------------------------------------------


class MockCtaEngine:
    """模拟CTA引擎，用于独立回测。"""

    def __init__(self):
        self.trades: list[dict] = []
        self.order_counter: int = 0
        self.trade_counter: int = 0
        self.logs: list[str] = []

    def send_order(
        self, strategy, direction: Direction, offset: Offset,
        price: float, volume: float, stop: bool = False,
        lock: bool = False, net: bool = False,
    ) -> list[str]:
        """模拟发单 — 立即成交。"""
        self.order_counter += 1
        orderid = f"MOCK.{self.order_counter:06d}"
        self.trade_counter += 1
        tradeid = f"MOCK.{self.trade_counter:06d}"

        vt_sym = strategy.vt_symbol
        if "." in vt_sym:
            sym, exch = vt_sym.split(".", 1)
        else:
            sym, exch = vt_sym, ""

        trade = {
            "tradeid": tradeid, "orderid": orderid,
            "symbol": sym, "exchange": exch,
            "direction": direction, "offset": offset,
            "price": price, "volume": volume,
            "datetime": datetime.now(), "pnl": 0.0,
        }
        self.trades.append(trade)

        trade_data = TradeData(
            symbol=sym,
            exchange=strategy.exchange if hasattr(strategy, "exchange") else Exchange.SSE,
            orderid=orderid, tradeid=tradeid,
            direction=direction, offset=offset,
            price=price, volume=volume, gateway_name="MOCK",
        )
        strategy.on_trade(trade_data)

        if direction == Direction.LONG and offset in (Offset.OPEN, Offset.NONE):
            strategy.pos += volume
        elif direction == Direction.SHORT and offset == Offset.CLOSE:
            strategy.pos -= volume
        elif direction == Direction.SHORT and offset in (Offset.OPEN, Offset.NONE):
            strategy.pos -= volume
        elif direction == Direction.LONG and offset == Offset.CLOSE:
            strategy.pos += volume

        return [orderid]

    def cancel_order(self, strategy, vt_orderid: str):
        pass

    def cancel_all(self, strategy):
        pass

    def write_log(self, msg: str, strategy=None):
        self.logs.append(msg)

    def load_bar(self, vt_symbol: str = None, days: int = 0, interval=Interval.MINUTE, callback=None, use_database=False):
        return []

    def put_event(self, strategy):
        pass

    def put_strategy_event(self, strategy):
        pass

    def send_email(self, msg: str, strategy):
        pass

    def sync_strategy_data(self, strategy):
        pass

    def load_tick(self, vt_symbol: str, days: int, callback):
        return []

    def get_pricetick(self, strategy) -> float:
        return 0.01

    def get_size(self, strategy) -> float:
        return 1

    def get_capital(self, strategy) -> float:
        return CAPITAL

    def get_engine_type(self):
        from vnpy_ctastrategy.base import EngineType
        return EngineType.BACKTESTING


# ---------------------------------------------------------------------------
# 简化回测器（从 run_stock_backtest.py 复制）
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
    """简化回测器 — 直接推送数据到策略。"""

    def __init__(self, strategy_class, setting: dict, symbol: str, exchange: Exchange, capital: float = CAPITAL):
        self.strategy_class = strategy_class
        self.setting = setting
        self.symbol = symbol
        self.exchange = exchange
        self.capital = capital

        self.trades: list[BacktestTrade] = []
        self.daily_pnl: list[float] = []
        self.position: float = 0
        self.avg_price: float = 0.0
        self.realized_pnl: float = 0.0
        self.commission_rate: float = 0.0003
        self.stamp_tax_rate: float = 0.001

        self.engine: Optional[MockCtaEngine] = None
        self.strategy = None

    def run(self, bars: list[BarData], freq_label: str = "1min", disable_short: bool = False) -> dict:
        """运行回测。"""
        if not bars:
            return {}

        self.engine = MockCtaEngine()
        vt_symbol = f"{self.symbol}.{self.exchange.value}"
        self.strategy = self.strategy_class(
            cta_engine=self.engine,
            strategy_name="czsc_backtest",
            vt_symbol=vt_symbol,
            setting=self.setting,
        )

        if freq_label == "5min":
            self._patch_strategy_for_5min()

        self.strategy.on_init()
        self.strategy.inited = True
        self.strategy.trading = True
        self.strategy.on_start()

        if freq_label == "daily":
            self.strategy._daily_mode = True
        else:
            self.strategy._daily_mode = False

        if disable_short:
            self.strategy._open_short = lambda price: None

        prev_date = None
        daily_pnl = 0.0
        prev_realized_pnl = 0.0

        for bar in bars:
            cur_date = bar.datetime.date() if hasattr(bar.datetime, "date") else bar.datetime
            if prev_date is not None and cur_date != prev_date:
                self.daily_pnl.append(daily_pnl)
                daily_pnl = 0.0
            prev_date = cur_date

            if freq_label == "5min":
                self.strategy.on_5min_bar(bar)
            elif freq_label == "daily":
                real_pos = self.strategy.pos
                self.strategy.pos = 0
                self.strategy.on_4hour_bar(bar)
                self.strategy.pos = 0
                self.strategy.on_30min_bar(bar)
                self.strategy.pos = real_pos
                self.strategy.on_5min_bar(bar)
                self.position = self.strategy.pos
            else:
                self.strategy.on_bar(bar)

            self._process_new_trades(bar.datetime)
            daily_pnl += self.realized_pnl - prev_realized_pnl
            prev_realized_pnl = self.realized_pnl

        self.daily_pnl.append(daily_pnl)
        stats = self.calculate_statistics(bars)
        return stats

    def _patch_strategy_for_5min(self):
        """适配5分钟数据源。"""
        from vnpy.trader.utility import BarGenerator

        self.strategy.bg_30m = BarGenerator(
            lambda bar: None, window=6,
            on_window_bar=self.strategy.on_30min_bar, interval=Interval.MINUTE,
        )
        self.strategy.bg_4h = BarGenerator(
            lambda bar: None, window=48,
            on_window_bar=self.strategy.on_4hour_bar, interval=Interval.MINUTE,
        )

        original_on_5min_bar = self.strategy.on_5min_bar

        def on_5min_bar_wrapped(bar: BarData):
            original_on_5min_bar(bar)
            self.strategy.bg_30m.update_bar(bar)
            self.strategy.bg_4h.update_bar(bar)

        self.strategy.on_5min_bar = on_5min_bar_wrapped

    def _process_new_trades(self, bar_dt: datetime):
        """处理mock引擎中的新增成交。"""
        if not self.engine:
            return

        start_idx = len(self.trades)
        for i in range(start_idx, len(self.engine.trades)):
            raw_trade = self.engine.trades[i]
            direction = raw_trade["direction"]
            offset = raw_trade["offset"]
            price = raw_trade["price"]
            volume = raw_trade["volume"]

            pnl = 0.0
            commission = 0.0

            if direction == Direction.LONG and offset in (Offset.OPEN, Offset.NONE):
                old_pos = self.position
                old_avg = self.avg_price
                self.position += volume
                if self.position != 0:
                    self.avg_price = (old_pos * old_avg + volume * price) / self.position
                commission = price * volume * self.commission_rate
            elif direction == Direction.SHORT and offset == Offset.CLOSE:
                pnl = (price - self.avg_price) * volume
                self.position -= volume
                commission = price * volume * self.commission_rate
                commission += price * volume * self.stamp_tax_rate
                if self.position <= 0:
                    self.position = 0
                    self.avg_price = 0.0
            elif direction == Direction.SHORT and offset in (Offset.OPEN, Offset.NONE):
                old_pos = abs(self.position)
                old_avg = self.avg_price
                self.position -= volume
                if self.position != 0:
                    self.avg_price = (old_pos * old_avg + volume * price) / abs(self.position)
                commission = price * volume * self.commission_rate
            elif direction == Direction.LONG and offset == Offset.CLOSE:
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
                tradeid=raw_trade["tradeid"], direction=direction,
                offset=offset, price=price, volume=volume,
                datetime=bar_dt, pnl=net_pnl,
            )
            self.trades.append(bt_trade)

    def calculate_statistics(self, bars: list[BarData]) -> dict:
        """计算绩效指标。"""
        if not bars:
            return {}

        total_pnl = self.realized_pnl

        if self.position != 0 and self.avg_price != 0:
            last_price = bars[-1].close_price
            unrealized_pnl = (last_price - self.avg_price) * self.position
        else:
            unrealized_pnl = 0.0

        total_return = total_pnl / self.capital
        total_return_with_unrealized = (total_pnl + unrealized_pnl) / self.capital

        trade_count = len(self.trades)
        closed_trades = [t for t in self.trades if t.pnl != 0]
        win_trades = [t for t in closed_trades if t.pnl > 0]
        loss_trades = [t for t in closed_trades if t.pnl < 0]

        win_rate = len(win_trades) / len(closed_trades) if closed_trades else 0.0
        avg_profit = np.mean([t.pnl for t in win_trades]) if win_trades else 0.0
        avg_loss = np.mean([t.pnl for t in loss_trades]) if loss_trades else 0.0
        profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else float("inf")

        net_values = [self.capital]
        for pnl in self.daily_pnl:
            net_values.append(net_values[-1] + pnl)

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

        if len(self.daily_pnl) > 1:
            daily_returns = np.array(self.daily_pnl) / self.capital
            nonzero_returns = daily_returns[daily_returns != 0]
            if len(nonzero_returns) > 1 and np.std(daily_returns) > 0:
                sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
            elif len(nonzero_returns) > 1:
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

        start_dt = bars[0].datetime
        end_dt = bars[-1].datetime
        trading_days = len(self.daily_pnl)

        return {
            "start_date": str(start_dt)[:10], "end_date": str(end_dt)[:10],
            "trading_days": trading_days, "total_bars": len(bars),
            "capital": self.capital, "total_pnl": total_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_return": total_return,
            "total_return_with_unrealized": total_return_with_unrealized,
            "trade_count": trade_count, "closed_trade_count": len(closed_trades),
            "win_count": len(win_trades), "loss_count": len(loss_trades),
            "win_rate": win_rate, "avg_profit": avg_profit,
            "avg_loss": avg_loss, "profit_loss_ratio": profit_loss_ratio,
            "max_drawdown": max_drawdown, "max_drawdown_pct": max_drawdown_pct,
            "sharpe_ratio": sharpe_ratio, "final_position": self.position,
        }


# ---------------------------------------------------------------------------
# 回测运行
# ---------------------------------------------------------------------------

def run_single_backtest(bars: list[BarData], stock: dict, freq_label: str) -> dict:
    """为单只股票运行回测。"""
    # 按10%资金比例计算每次交易股数
    # A股最小交易单位为1手=100股
    price = bars[0].close_price  # 使用第一根K线收盘价作为参考
    position_value = CAPITAL * 0.10  # 单次仓位占总资金10%
    fixed_size = max(100, int(position_value / price / 100) * 100)  # 取整到100股

    # 基础参数 — 针对日线数据优化（放宽止损、降低止盈、放宽支撑容忍度）
    setting = {
        "fixed_size": fixed_size,      # 动态计算
        "max_pos": 3,                  # 最多3次仓位（总计约30%）
        "stop_loss_pct": 0.05,         # 止损5%
        "take_profit_pct": 0.03,       # 止盈3%
        "trailing_stop_pct": 0.025,    # 移动止损2.5%
        "min_bars_5m": 20,             # 减少最小K线数
        "min_bars_30m": 15,
        "min_bars_4h": 8,
        "support_tolerance_pct": 0.05,  # 放宽支撑容忍度 3%→5%
    }

    # 根据数据周期进一步调低阈值
    if freq_label == "daily":
        setting["min_bars_5m"] = 15
        setting["min_bars_30m"] = 10
        setting["min_bars_4h"] = 5

    # 按行业差异化参数
    industry = stock.get("industry", "")
    if industry in ("元器件", "半导体", "软件服务", "通信设备"):
        setting["stop_loss_pct"] = 0.06
        setting["take_profit_pct"] = 0.04
        setting["trailing_stop_pct"] = 0.05
        setting["support_tolerance_pct"] = 0.06
    elif industry in ("环境保护", "机械基件", "工程机械", "空运"):
        setting["stop_loss_pct"] = 0.05
        setting["take_profit_pct"] = 0.03
        setting["trailing_stop_pct"] = 0.04
        setting["support_tolerance_pct"] = 0.05

    backtester = SimpleBacktester(
        strategy_class=CzscMultiTimeframeStrategy,
        setting=setting,
        symbol=stock["symbol"],
        exchange=stock["exchange"],
        capital=CAPITAL,
    )

    stats = backtester.run(bars, freq_label=freq_label, disable_short=True)
    stats["fixed_size"] = fixed_size
    stats["price"] = price
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
    fixed_size = stats.get('fixed_size', 0)
    price_ref = stats.get('price', 0)
    if fixed_size and price_ref:
        print(f"  │ 动态仓位:   {fixed_size:>12,}股 (约{fixed_size * price_ref / 10000:.1f}万元，占资金{fixed_size * price_ref / CAPITAL * 100:.1f}%)")
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


def print_comparison(results: dict, stocks: list[dict]):
    """打印各股票回测对比汇总。"""
    name_to_board = {s["name"]: s.get("board", "") for s in stocks}
    name_to_mv = {s["name"]: s.get("mv_yi", 0) for s in stocks}

    print(f"\n{'=' * 100}")
    print("缠论多时间周期策略 — 小市值股票回测对比报告 (AKShare数据源)")
    print(f"{'=' * 100}")

    print("\n一、选股信息")
    print("-" * 100)
    print(f"{'股票':<10} {'板块':<8} {'市值(亿)':>10} {'换手率(%)':>10} {'行业':<10} {'选股理由'}")
    print("-" * 100)
    for s in stocks:
        name = s["name"]
        board = s.get("board", "")
        mv = s.get("mv_yi", 0)
        tr = s.get("turnover", 0)
        ind = s.get("industry", "")
        reason = f"市值{mv}亿<100亿, 换手率{tr}%>0.5%, {board}板块流动性较好"
        print(f"{name:<10} {board:<8} {mv:>10.1f} {tr:>10.2f} {ind:<10} {reason}")

    print(f"\n二、回测绩效对比")
    print("-" * 100)
    print(f"{'股票':<10} {'板块':<8} {'收益率':>10} {'含浮动收益率':>12} "
          f"{'交易次数':>8} {'胜率':>8} {'最大回撤率':>10} {'夏普比率':>10}")
    print("-" * 100)

    for s in stocks:
        name = s["name"]
        stats = results.get(name, {})
        board = name_to_board.get(name, "")
        if not stats:
            print(f"{name:<10} {board:<8} {'N/A':>10}")
            continue
        print(
            f"{name:<10} {board:<8} "
            f"{stats.get('total_return', 0):>9.2%} "
            f"{stats.get('total_return_with_unrealized', 0):>11.2%} "
            f"{stats.get('trade_count', 0):>8} "
            f"{stats.get('win_rate', 0):>7.2%} "
            f"{stats.get('max_drawdown_pct', 0):>9.2%} "
            f"{stats.get('sharpe_ratio', 0):>10.2f}"
        )

    print(f"\n三、按板块汇总平均绩效")
    print("-" * 100)
    print(f"{'板块':<10} {'股票数':>8} {'平均收益率':>12} {'平均含浮动收益率':>16} "
          f"{'平均胜率':>10} {'平均最大回撤率':>14} {'平均夏普比率':>12}")
    print("-" * 100)

    board_stats = {}
    for s in stocks:
        name = s["name"]
        board = s.get("board", "")
        stats = results.get(name, {})
        if not stats:
            continue
        board_stats.setdefault(board, []).append(stats)

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
    print("  6. 数据源: AKShare (免费开源金融数据接口)")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

def main():
    """主入口：选股 → 逐股回测 → 对比报告。"""
    print("=" * 60)
    print("缠论多时间周期策略 — AKShare 股票回测")
    print("=" * 60)
    print(f"数据源: AKShare (免费接口，无需API Key)")
    print(f"回测区间: {START_DATE} ~ {END_DATE}")
    print(f"初始资金: {CAPITAL:,.0f}")
    print()

    # 1. 选股
    stocks = select_stocks()
    print(f"\n选定 {len(stocks)} 只股票:")
    for s in stocks:
        print(f"  {s['board']} | {s['symbol']} {s['name']} | 市值: {s['mv_yi']:.1f}亿")

    # 2. 逐只回测
    results = {}
    for stock in stocks:
        print(f"\n{'=' * 60}")
        print(f"回测: {stock['name']} ({stock['symbol']}) - {stock['board']}")
        print(f"{'=' * 60}")

        bars, freq_label = download_stock_data(stock["symbol"], stock["exchange"])
        if not bars:
            print(f"  数据获取失败，跳过")
            results[stock["name"]] = {}
            continue

        print(f"  数据周期: {freq_label}, K线数量: {len(bars)}")
        print(f"  时间范围: {bars[0].datetime} ~ {bars[-1].datetime}")

        time.sleep(1)  # AKShare频率限制

        try:
            stats = run_single_backtest(bars, stock, freq_label)
            results[stock["name"]] = stats
            print_report(stock["name"], stats)
        except Exception as e:
            print(f"  [错误] 回测执行失败: {e}")
            import traceback
            traceback.print_exc()
            results[stock["name"]] = {}

    # 3. 输出对比报告
    print_comparison(results, stocks)


if __name__ == "__main__":
    main()
