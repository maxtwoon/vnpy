# =============================================================================
# !! LEGACY / 已停止维护 —— RESEARCH-ONLY / NOT PROMOTION EVIDENCE !!
# -----------------------------------------------------------------------------
# 本文件（run_baostock_backtest.py）是早期 A 股原型代码，已停止维护，未接入当前回测/测试路径；
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
缠论多时间周期策略 — Baostock 5分钟数据源回测
================================================
使用Baostock免费接口获取2021-2022年5分钟K线历史数据，
实现真正的多周期K线合成回测：5分钟 → 30分钟 → 4小时。

Baostock 优势：
- 完全免费，无需API Key
- 支持2006年至今的5/15/30/60分钟历史数据
- 前复权/后复权可选

回测逻辑：
- 5分钟K线直接驱动 on_5min_bar
- 每6根5分钟自动合成1根30分钟K线 → on_30min_bar
- 每48根5分钟自动合成1根4小时K线 → on_4hour_bar

注意事项：
- A股每天交易时段: 9:30-11:30, 13:00-15:00 共48根5分钟K线
- 2年约480交易日 × 48根 ≈ 23,000根/股
- Baostock time字段格式: 20210104093500000 (17位，精确到毫秒)
"""

import sys
import os
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(__file__))

from vnpy.trader.object import BarData, TradeData, OrderData
from vnpy.trader.constant import Exchange, Interval, Direction, Offset, Status, OrderType
from vnpy.trader.utility import BarGenerator

from czsc_multi_timeframe_strategy import CzscMultiTimeframeStrategy


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

CAPITAL = 1_000_000  # 初始资金100万
START_DATE = "2021-01-01"
END_DATE = "2022-12-31"

# 9只股票列表（上证3只、深证3只、创业板3只）
STOCKS = [
    # 上证主板（3只）
    {"bs_code": "sh.600133", "symbol": "600133", "exchange": Exchange.SSE, "name": "东湖高新", "board": "上证"},
    {"bs_code": "sh.603220", "symbol": "603220", "exchange": Exchange.SSE, "name": "中贝通信", "board": "上证"},
    {"bs_code": "sh.600114", "symbol": "600114", "exchange": Exchange.SSE, "name": "东睦股份", "board": "上证"},
    # 深证主板（3只）
    {"bs_code": "sz.002036", "symbol": "002036", "exchange": Exchange.SZSE, "name": "联创电子", "board": "深证"},
    {"bs_code": "sz.002928", "symbol": "002928", "exchange": Exchange.SZSE, "name": "华夏航空", "board": "深证"},
    {"bs_code": "sz.002158", "symbol": "002158", "exchange": Exchange.SZSE, "name": "汉钟精机", "board": "深证"},
    # 创业板（3只）
    {"bs_code": "sz.300256", "symbol": "300256", "exchange": Exchange.SZSE, "name": "星星科技", "board": "创业板"},
    {"bs_code": "sz.300655", "symbol": "300655", "exchange": Exchange.SZSE, "name": "晶瑞电材", "board": "创业板"},
    {"bs_code": "sz.300634", "symbol": "300634", "exchange": Exchange.SZSE, "name": "彩讯股份", "board": "创业板"},
]

# 策略参数 v12（波段战法分仓版 — 最终版）
# 核心改进：分层出场策略
#   盈利时：笔方向确认（保守，让盈利跑完）
#   大亏>3%时：直接卖出（快止损）
#   小亏<3%时：信号过滤保护（给恢复机会）
STRATEGY_SETTING = {
    "total_capital": CAPITAL,
    "max_distance_pct": 0.30,
    "filter_distance_pct": 0.05,   # 5%信号过滤（小亏出场保护）
    "profit_lock_pct_1": 0.20,     # 20%利润锁定
    "profit_lock_pct_2": 0.30,     # 30%全清
    "max_loss_pct": 0.03,          # 3%大亏阈值（超过直接止损）
    "trailing_start_pct": 1.00,    # 禁用移动止盈
    "trailing_floor_pct": 0.00,    # 禁用
    "min_bi_range_pct": 0.005,     # 0.5%笔最小幅度
    "risk_factor": 10,
    "ratio_5m": 0.20,
    "ratio_30m": 0.30,
    "ratio_4h": 0.50,
    "min_bars_5m": 100,
    "min_bars_30m": 30,
    "min_bars_4h": 12,
}


# ---------------------------------------------------------------------------
# Baostock 数据获取（带CSV缓存）
# ---------------------------------------------------------------------------

DATA_CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")


def _bars_to_df(bars: list) -> "pd.DataFrame":
    """BarData列表转为DataFrame保存缓存。"""
    import pandas as pd
    rows = []
    for b in bars:
        rows.append({
            "datetime": b.datetime.strftime("%Y%m%d%H%M%S"),
            "open": b.open_price,
            "high": b.high_price,
            "low": b.low_price,
            "close": b.close_price,
            "volume": b.volume,
            "turnover": b.turnover,
        })
    return pd.DataFrame(rows)


def _df_to_bars(df: "pd.DataFrame", symbol: str, exchange: Exchange) -> list:
    """DataFrame转为BarData列表。"""
    import pandas as pd
    bars = []
    for _, row in df.iterrows():
        dt = datetime.strptime(str(row["datetime"]), "%Y%m%d%H%M%S")
        bar = BarData(
            symbol=symbol,
            exchange=exchange,
            datetime=dt,
            interval=Interval.MINUTE,
            open_price=float(row["open"]),
            high_price=float(row["high"]),
            low_price=float(row["low"]),
            close_price=float(row["close"]),
            volume=float(row["volume"]),
            turnover=float(row["turnover"]),
            gateway_name="baostock",
        )
        bars.append(bar)
    return bars


def download_5min_data_cached(
    bs_code: str,
    symbol: str,
    exchange: Exchange,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
) -> list:
    """带CSV缓存的5分钟数据下载。

    第一次运行时下载并保存到CSV，后续运行直接从缓存加载。
    """
    import pandas as pd
    os.makedirs(DATA_CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(
        DATA_CACHE_DIR,
        f"{symbol}_{start_date}_{end_date}.csv"
    )

    if os.path.exists(cache_file):
        print(f"  [缓存] 从本地加载: {os.path.basename(cache_file)}")
        df = pd.read_csv(cache_file, dtype={"datetime": str})
        bars = _df_to_bars(df, symbol, exchange)
        print(f"  缓存加载完成，共 {len(bars):,} 根K线")
        return bars

    print(f"  [下载] 未找到缓存，开始从 Baostock 下载...")
    bars = download_5min_data(bs_code, symbol, exchange, start_date, end_date)

    if bars:
        df = _bars_to_df(bars)
        df.to_csv(cache_file, index=False)
        print(f"  [缓存] 已保存至 {os.path.basename(cache_file)}")

    return bars

def download_5min_data(
    bs_code: str,
    symbol: str,
    exchange: Exchange,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
) -> list[BarData]:
    """使用Baostock获取5分钟K线历史数据（前复权）。

    Baostock单次查询最多返回约25,000条记录，使用按季度分段下载确保获取2年完整数据。

    Args:
        bs_code: Baostock格式代码，如 sh.600133 / sz.002036
        symbol: vnpy格式代码，如 600133
        exchange: 交易所枚举
        start_date: 开始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD

    Returns:
        BarData列表，按时间升序排列
    """
    import baostock as bs

    # 按季度分段下载（避免Baostock单次返回最多约25,000条的限制）
    # 每个季度约49个交易日 × 48根 = 约2,352根，远小于限制
    from datetime import date

    def quarter_ranges(s: str, e: str) -> list[tuple[str, str]]:
        """将日期范围按季度切割，返回 [(seg_start, seg_end), ...] 列表。"""
        start = date.fromisoformat(s)
        end = date.fromisoformat(e)
        ranges = []
        y = start.year
        q = (start.month - 1) // 3
        while True:
            qs = date(y, q * 3 + 1, 1)
            qm = q * 3 + 3
            qe_day = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][qm - 1]
            if qm == 2 and ((y % 4 == 0 and y % 100 != 0) or y % 400 == 0):
                qe_day = 29
            qe = date(y, qm, qe_day)
            seg_start = max(qs, start)
            seg_end = min(qe, end)
            if seg_start <= seg_end:
                ranges.append((str(seg_start), str(seg_end)))
            if qe >= end:
                break
            q += 1
            if q >= 4:
                q = 0
                y += 1
        return ranges

    segments = quarter_ranges(start_date, end_date)
    all_bars: list[BarData] = []
    seen_dts: set = set()

    try:
        lg = bs.login()
        if lg.error_code != "0":
            print(f"  [错误] Baostock登录失败: {lg.error_msg}")
            return []

        for seg_start, seg_end in segments:
            rs = bs.query_history_k_data_plus(
                code=bs_code,
                fields="date,time,open,high,low,close,volume,amount",
                start_date=seg_start,
                end_date=seg_end,
                frequency="5",   # 5分钟
                adjustflag="2",  # 前复权
            )

            if rs.error_code != "0":
                print(f"  [警告] 分段 {seg_start}~{seg_end} 查询失败: {rs.error_msg}")
                continue

            field_names = ["date", "time", "open", "high", "low", "close", "volume", "amount"]
            seg_rows = []
            while rs.next():
                seg_rows.append(dict(zip(field_names, rs.get_row_data())))

            for row in seg_rows:
                time_str = str(row["time"])[:14]
                try:
                    dt = datetime.strptime(time_str, "%Y%m%d%H%M%S")
                except ValueError:
                    continue

                if dt in seen_dts:
                    continue
                seen_dts.add(dt)

                try:
                    open_p = float(row["open"])
                    high_p = float(row["high"])
                    low_p = float(row["low"])
                    close_p = float(row["close"])
                    vol = float(row["volume"] or 0)
                    amount = float(row["amount"] or 0)
                except (ValueError, TypeError):
                    continue

                if open_p <= 0 or close_p <= 0:
                    continue

                bar = BarData(
                    symbol=symbol,
                    exchange=exchange,
                    datetime=dt,
                    interval=Interval.MINUTE,
                    open_price=open_p,
                    high_price=high_p,
                    low_price=low_p,
                    close_price=close_p,
                    volume=vol,
                    turnover=amount,
                    gateway_name="baostock",
                )
                all_bars.append(bar)

        bs.logout()

        # 按时间升序排列
        all_bars.sort(key=lambda b: b.datetime)
        return all_bars

    except Exception as e:
        print(f"  [错误] 数据获取异常: {e}")
        import traceback
        traceback.print_exc()
        try:
            bs.logout()
        except Exception:
            pass
        return []


# ---------------------------------------------------------------------------
# Mock CTA 引擎
# ---------------------------------------------------------------------------


class MockCtaEngine:
    """模拟CTA引擎，用于独立回测。"""

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

        trade_data = TradeData(
            symbol=sym,
            exchange=strategy.exchange if hasattr(strategy, "exchange") else Exchange.SSE,
            orderid=orderid,
            tradeid=tradeid,
            direction=direction,
            offset=offset,
            price=price,
            volume=volume,
            gateway_name="MOCK",
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

    def load_bar(
        self,
        vt_symbol: str = None,
        days: int = 0,
        interval=Interval.MINUTE,
        callback=None,
        use_database=False,
    ):
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
# 基于计数的K线合成器（替代BarGenerator的分钟边界触发方式）
# ---------------------------------------------------------------------------

class CountBarMerger:
    """基于计数的K线合成器 - 每N根输入K线合成1根输出K线。

    不依赖BarGenerator的分钟边界触发，适用于5分钟数据合成30分钟/4小时。
    """

    def __init__(self, window: int, on_bar_callback):
        self.window = window
        self.on_bar_callback = on_bar_callback
        self._count = 0
        self._merged: BarData | None = None

    def update_bar(self, bar: BarData) -> None:
        """接收一根K线，累计window根后回调合成K线。"""
        if self._merged is None:
            # 第一根：初始化合成K线
            self._merged = BarData(
                symbol=bar.symbol,
                exchange=bar.exchange,
                datetime=bar.datetime,
                interval=bar.interval,
                gateway_name=bar.gateway_name,
                open_price=bar.open_price,
                high_price=bar.high_price,
                low_price=bar.low_price,
                close_price=bar.close_price,
                volume=bar.volume,
                turnover=bar.turnover,
            )
        else:
            # 后续根：更新high/low/close/volume/turnover
            self._merged.high_price = max(self._merged.high_price, bar.high_price)
            self._merged.low_price = min(self._merged.low_price, bar.low_price)
            self._merged.close_price = bar.close_price
            self._merged.volume += bar.volume
            self._merged.turnover += bar.turnover

        self._count += 1
        if self._count >= self.window:
            # 触发回调
            if self.on_bar_callback:
                self.on_bar_callback(self._merged)
            # 重置
            self._merged = None
            self._count = 0


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
    """简化回测器 — 直接推送5分钟数据到策略，内部合成30分钟和4小时K线。"""

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

        self.trades: list[BacktestTrade] = []
        self.daily_pnl: list[float] = []
        self.position: float = 0
        self.avg_price: float = 0.0
        self.realized_pnl: float = 0.0
        self.commission_rate: float = 0.0003   # 手续费万三
        self.stamp_tax_rate: float = 0.001     # 印花税千一（仅卖出）

        self.engine: Optional[MockCtaEngine] = None
        self.strategy = None

    def run(self, bars_5min: list[BarData], disable_short: bool = True) -> dict:
        """运行真正的多周期回测。

        核心流程：
        1. 初始化策略
        2. 修改策略内部BarGenerator，使其从5分钟合成30分钟（×6）和4小时（×48）
        3. 逐根5分钟K线推送到 on_5min_bar，触发BG合成更高周期
        """
        if not bars_5min:
            return {}

        self.engine = MockCtaEngine()
        vt_symbol = f"{self.symbol}.{self.exchange.value}"
        self.strategy = self.strategy_class(
            cta_engine=self.engine,
            strategy_name="czsc_baostock_backtest",
            vt_symbol=vt_symbol,
            setting=self.setting,
        )

        # ---------------------------------------------------------------
        # 关键：使用CountBarMerger替代BarGenerator，基于精确计数合成
        # merger_30m: 每6根5分钟 → 1根30分钟
        # merger_4h : 每48根5分钟 → 1根4小时
        # ---------------------------------------------------------------
        merger_30m = CountBarMerger(
            window=6,
            on_bar_callback=self.strategy.on_30min_bar,
        )
        merger_4h = CountBarMerger(
            window=48,
            on_bar_callback=self.strategy.on_4hour_bar,
        )

        # 将 on_5min_bar 包装：原逻辑 + 触发计数合成 + 冷却期控制
        original_on_5min_bar = self.strategy.on_5min_bar
        _bar_idx = [0]
        _last_close_idx = [-48]  # 初始假设已超过冷却期
        _prev_pos = [0]
        COOLDOWN = 48   # 第10次迭代：回归1个交易日冷却期

        def on_5min_bar_wrapped(bar: BarData):
            strategy = self.strategy
            idx = _bar_idx[0]
            _bar_idx[0] += 1

            # 先合成更高周期（确保本根5m K线处理前，高周期已更新）
            merger_30m.update_bar(bar)
            merger_4h.update_bar(bar)

            # 冷却期内且无持仓：仅更新CZSC分析器，跳过开仓逻辑
            in_cooldown = (idx - _last_close_idx[0]) < COOLDOWN
            if in_cooldown and strategy.pos == 0:
                # 手动更新czsc_5m，跳过交易决策
                try:
                    strategy.czsc_5m.update(bar)
                except Exception:
                    pass
                strategy.put_event()
                return

            # 执行原策略逻辑（5m信号检测）
            prev_pos = _prev_pos[0]
            original_on_5min_bar(bar)

            # 检测完全平仓事件，记录冷却起始
            if prev_pos != 0 and strategy.pos == 0:
                _last_close_idx[0] = idx
            _prev_pos[0] = strategy.pos

        self.strategy.on_5min_bar = on_5min_bar_wrapped

        # 禁止做空（A股T+1限制）
        if disable_short:
            self.strategy._open_short = lambda price: None

        self.strategy.on_init()
        self.strategy.inited = True
        self.strategy.trading = True
        self.strategy.on_start()

        # ---------------------------------------------------------------
        # 逐根5分钟K线推送
        # ---------------------------------------------------------------
        prev_date = None
        daily_pnl = 0.0
        prev_realized_pnl = 0.0
        total_bars = len(bars_5min)

        for i, bar in enumerate(bars_5min):
            # 进度提示（每2000根）
            if i > 0 and i % 2000 == 0:
                pct = i / total_bars * 100
                print(f"    进度: {i}/{total_bars} ({pct:.1f}%) ...")

            cur_date = bar.datetime.date()
            if prev_date is not None and cur_date != prev_date:
                self.daily_pnl.append(daily_pnl)
                daily_pnl = 0.0
            prev_date = cur_date

            # 推送5分钟K线（内部会触发BG合成30分钟/4小时）
            self.strategy.on_5min_bar(bar)

            self._process_new_trades(bar.datetime)
            daily_pnl += self.realized_pnl - prev_realized_pnl
            prev_realized_pnl = self.realized_pnl

        # 最后一天
        self.daily_pnl.append(daily_pnl)

        stats = self.calculate_statistics(bars_5min)
        return stats

    def _process_new_trades(self, bar_dt: datetime):
        """处理mock引擎中的新增成交。"""
        if not self.engine:
            return

        start_idx = len(self.trades)
        for i in range(start_idx, len(self.engine.trades)):
            raw = self.engine.trades[i]
            direction = raw["direction"]
            offset = raw["offset"]
            price = raw["price"]
            volume = raw["volume"]

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
                commission = price * volume * (self.commission_rate + self.stamp_tax_rate)
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
                commission = price * volume * (self.commission_rate + self.stamp_tax_rate)
                if self.position >= 0:
                    self.position = 0
                    self.avg_price = 0.0

            net_pnl = pnl - commission
            self.realized_pnl += net_pnl

            bt_trade = BacktestTrade(
                tradeid=raw["tradeid"],
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
            if np.std(daily_returns) > 0:
                sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
            else:
                nonzero = daily_returns[daily_returns != 0]
                if len(nonzero) > 1 and np.std(nonzero) > 0:
                    trade_freq = len(nonzero) / len(daily_returns)
                    sharpe_ratio = np.mean(nonzero) / np.std(nonzero) * np.sqrt(252 * trade_freq)
                else:
                    sharpe_ratio = 1.0 if total_pnl > 0 else (-1.0 if total_pnl < 0 else 0.0)
        else:
            sharpe_ratio = 0.0

        start_dt = bars[0].datetime
        end_dt = bars[-1].datetime
        trading_days = len(self.daily_pnl)

        return {
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


# ---------------------------------------------------------------------------
# 回测运行
# ---------------------------------------------------------------------------


def run_single_backtest(bars_5min: list[BarData], stock: dict) -> dict:
    """为单只股票运行5分钟真实多周期回测。"""
    # 新策略通过total_capital参数自行计算仓位，直接使用STRATEGY_SETTING
    setting = dict(STRATEGY_SETTING)

    backtester = SimpleBacktester(
        strategy_class=CzscMultiTimeframeStrategy,
        setting=setting,
        symbol=stock["symbol"],
        exchange=stock["exchange"],
        capital=CAPITAL,
    )

    stats = backtester.run(bars_5min, disable_short=True)
    return stats


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------


def print_report(name: str, stats: dict):
    """打印单只股票回测报告。"""
    if not stats:
        print(f"  {name}: 无回测结果")
        return

    print(f"\n  ┌─ 回测结果: {name} ─────────────────────────")
    print(f"  │ 回测区间:   {stats.get('start_date', 'N/A')} ~ {stats.get('end_date', 'N/A')}")
    print(f"  │ 交易天数:   {stats.get('trading_days', 0)}")
    print(f"  │ 5分钟K线:   {stats.get('total_bars', 0)} 根")
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


def print_final_report(results: dict, stocks: list[dict], data_info: dict):
    """打印综合对比报告。"""
    print(f"\n{'=' * 110}")
    print("缠论多时间周期策略 — Baostock 5分钟真实多周期回测对比报告")
    print(f"{'=' * 110}")

    # 数据获取概览
    print("\n一、数据获取情况（Baostock 5分钟 前复权数据）")
    print("-" * 110)
    print(f"{'股票':<10} {'板块':<8} {'5分钟K线数':>12} {'合成30分钟K线':>14} {'合成4小时K线':>12} "
          f"{'时间范围':<32}")
    print("-" * 110)
    for s in stocks:
        name = s["name"]
        info = data_info.get(name, {})
        n5m = info.get("bars_5m", 0)
        n30m = n5m // 6
        n4h = n5m // 48
        time_range = info.get("time_range", "N/A")
        board = s.get("board", "")
        print(f"{name:<10} {board:<8} {n5m:>12,} {n30m:>14,} {n4h:>12,} {time_range:<32}")

    # 绩效对比
    print(f"\n二、各股绩效对比（多周期真实回测）")
    print("-" * 110)
    print(f"{'股票':<10} {'板块':<8} {'收益率':>10} {'含浮动':>10} "
          f"{'交易次数':>8} {'胜率':>8} {'最大回撤率':>10} {'夏普比率':>10}")
    print("-" * 110)

    for s in stocks:
        name = s["name"]
        stats = results.get(name, {})
        board = s.get("board", "")
        if not stats:
            print(f"{name:<10} {board:<8} {'N/A':>10}")
            continue
        print(
            f"{name:<10} {board:<8} "
            f"{stats.get('total_return', 0):>9.2%} "
            f"{stats.get('total_return_with_unrealized', 0):>9.2%} "
            f"{stats.get('trade_count', 0):>8} "
            f"{stats.get('win_rate', 0):>7.2%} "
            f"{stats.get('max_drawdown_pct', 0):>9.2%} "
            f"{stats.get('sharpe_ratio', 0):>10.2f}"
        )

    # 板块汇总
    print(f"\n三、按板块汇总平均绩效")
    print("-" * 110)
    print(f"{'板块':<10} {'股票数':>8} {'平均收益率':>12} {'平均胜率':>10} "
          f"{'平均最大回撤率':>14} {'平均夏普比率':>12}")
    print("-" * 110)

    board_stats: dict[str, list[dict]] = {}
    for s in stocks:
        name = s["name"]
        board = s.get("board", "")
        stats = results.get(name, {})
        if stats:
            board_stats.setdefault(board, []).append(stats)

    for board, stats_list in board_stats.items():
        n = len(stats_list)
        avg_return = np.mean([s.get("total_return", 0) for s in stats_list])
        avg_win_rate = np.mean([s.get("win_rate", 0) for s in stats_list])
        avg_max_dd = np.mean([s.get("max_drawdown_pct", 0) for s in stats_list])
        avg_sharpe = np.mean([s.get("sharpe_ratio", 0) for s in stats_list])
        print(
            f"{board:<10} {n:>8} {avg_return:>11.2%} {avg_win_rate:>9.2%} "
            f"{avg_max_dd:>13.2%} {avg_sharpe:>11.2f}"
        )

    all_stats = [results.get(s["name"], {}) for s in stocks if results.get(s["name"], {})]
    if all_stats:
        n = len(all_stats)
        avg_return = np.mean([s.get("total_return", 0) for s in all_stats])
        avg_win_rate = np.mean([s.get("win_rate", 0) for s in all_stats])
        avg_max_dd = np.mean([s.get("max_drawdown_pct", 0) for s in all_stats])
        avg_sharpe = np.mean([s.get("sharpe_ratio", 0) for s in all_stats])
        print(
            f"{'全部':<10} {n:>8} {avg_return:>11.2%} {avg_win_rate:>9.2%} "
            f"{avg_max_dd:>13.2%} {avg_sharpe:>11.2f}"
        )

    print(f"{'=' * 110}")

    print()
    print("四、与AKShare日线回测的对比说明")
    print("-" * 110)
    print("  数据精度对比:")
    print(f"    AKShare 日线:     每天1根K线，2年约480根，仅能做日线级别分析")
    print(f"    Baostock 5分钟:  每天48根K线，2年约23,040根，真正三级联立回测")
    print()
    print("  多周期合成方式:")
    print(f"    AKShare模式: 同一根日K线被模拟分发给5m/30m/4h三个分析器（伪多周期）")
    print(f"    Baostock模式: 5分钟→30分钟（6根合1）→4小时（48根合1）真实合成")
    print()
    print("  策略精度提升:")
    print(f"    - 5分钟分型信号更精确（真实5分钟K线结构，而非模拟）")
    print(f"    - 30分钟趋势确认有真实的中期结构支撑")
    print(f"    - 4小时大趋势判断不再是日线的伪4小时")
    print(f"    - 入场时机更精准，止损/止盈触发更符合实际")
    print()
    print("  注意事项:")
    print("  1. A股禁止做空（T+1限制），空头信号已屏蔽")
    print("  2. 未考虑涨跌停限制，实际交易可能无法以信号价成交")
    print("  3. 手续费: 万三 + 印花税千一（仅卖出）")
    print("  4. 数据源: Baostock (免费, 2006年至今, 支持分钟级历史数据)")
    print("  5. 本回测仅为策略逻辑验证，不构成投资建议")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def main():
    """主入口：下载数据 → 逐股回测 → 综合报告。"""
    print("=" * 70)
    print("缠论多时间周期策略 — Baostock 5分钟真实多周期回测 [波段战法分仓版]")
    print("=" * 70)
    print(f"数据源: Baostock (5分钟K线, 前复权)")
    print(f"回测区间: {START_DATE} ~ {END_DATE}")
    print(f"初始资金: {CAPITAL:,.0f}")
    print(f"多周期合成: 5min → 30min(×6) → 4hour(×48)")
    print(f"策略参数: max_dist={STRATEGY_SETTING['max_distance_pct']:.0%}, "
          f"filter={STRATEGY_SETTING['filter_distance_pct']:.0%}, "
          f"profit_lock1={STRATEGY_SETTING['profit_lock_pct_1']:.0%}, "
          f"profit_lock2={STRATEGY_SETTING['profit_lock_pct_2']:.0%}, "
          f"risk_factor={STRATEGY_SETTING['risk_factor']}")
    print(f"入场条件: 5m突破中枢上沿 + 距4H下轨<={STRATEGY_SETTING['max_distance_pct']:.0%}")
    print(f"止损规则: 破4H下轨全清（无条件止损）")
    print()

    results: dict[str, dict] = {}
    data_info: dict[str, dict] = {}

    for stock in STOCKS:
        name = stock["name"]
        symbol = stock["symbol"]
        board = stock["board"]
        bs_code = stock["bs_code"]

        print(f"\n{'=' * 70}")
        print(f"[{board}] {name} ({symbol})  bs_code={bs_code}")
        print(f"{'=' * 70}")

        # 1. 下载5分钟数据（优先从缓存加载）
        t0 = time.time()
        print(f"  正在加载5分钟K线数据 ...")
        bars_5min = download_5min_data_cached(
            bs_code=bs_code,
            symbol=symbol,
            exchange=stock["exchange"],
            start_date=START_DATE,
            end_date=END_DATE,
        )
        elapsed = time.time() - t0

        if not bars_5min:
            print(f"  [跳过] 数据获取失败")
            results[name] = {}
            data_info[name] = {"bars_5m": 0, "time_range": "N/A"}
            time.sleep(2)
            continue

        n5m = len(bars_5min)
        time_range = f"{bars_5min[0].datetime} ~ {bars_5min[-1].datetime}"
        print(f"  获取到 {n5m:,} 根5分钟K线 (耗时 {elapsed:.1f}s)")
        print(f"  时间范围: {time_range}")
        print(f"  预计合成: {n5m // 6:,} 根30分钟, {n5m // 48:,} 根4小时")

        data_info[name] = {"bars_5m": n5m, "time_range": time_range}

        # Baostock限流保护
        time.sleep(0.5)

        # 2. 运行回测
        try:
            t1 = time.time()
            print(f"  开始回测 (共 {n5m:,} 根K线) ...")
            stats = run_single_backtest(bars_5min, stock)
            elapsed2 = time.time() - t1
            results[name] = stats
            print(f"  回测完成 (耗时 {elapsed2:.1f}s)")
            print_report(name, stats)
        except Exception as e:
            print(f"  [错误] 回测异常: {e}")
            import traceback
            traceback.print_exc()
            results[name] = {}

    # 3. 综合报告
    print_final_report(results, STOCKS, data_info)


if __name__ == "__main__":
    main()
