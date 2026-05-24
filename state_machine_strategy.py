"""
专享策略26：基于"状态机"的多因子策略
============================================
策略核心思路：
    1. 用多个技术因子（趋势/动量/成交量/MACD）共同判断当前市场"状态"
    2. 状态机将市场分为：多头状态(BULL) / 空头状态(BEAR) / 中性状态(NEUTRAL)
    3. 根据当前状态决定开仓/平仓方向，避免单因子噪声干扰

状态划分规则（因子投票制）：
    - BULL:    3个及以上因子看多 → 开多
    - BEAR:    3个及以上因子看空 → 开空（期货）/ 平多（A股）
    - NEUTRAL: 因子分歧 → 平仓或空仓

四大因子：
    Factor 1 - 趋势因子：MA_fast > MA_slow  (5/20日均线)
    Factor 2 - 动量因子：RSI > 50
    Factor 3 - 成交量因子：当前量 > 量均线 * 阈值
    Factor 4 - MACD因子：MACD Histogram > 0

风控：
    - ATR止损（入场价 ± atr_multi * ATR）
    - 固定仓位（每次fixed_size手/股）

用法（作为vnpy CTA策略使用）：
    from state_machine_strategy import StateMachineStrategy
"""

from typing import Optional, Deque
from collections import deque
import math


# ──────────────────────────────────────────────
# 状态常量
# ──────────────────────────────────────────────
STATE_NEUTRAL = 0   # 中性/无信号
STATE_BULL = 1      # 多头状态
STATE_BEAR = -1     # 空头状态


# ──────────────────────────────────────────────
# 轻量级技术指标计算（无外部依赖）
# ──────────────────────────────────────────────

class _EMACalc:
    """EMA 增量计算器"""
    def __init__(self, period: int):
        self.period = period
        self.k = 2.0 / (period + 1)
        self.value: Optional[float] = None
        self._count = 0

    def update(self, price: float) -> Optional[float]:
        self._count += 1
        if self._count <= self.period:
            # 前 period 根用 SMA 初始化
            self.value = (
                price if self.value is None
                else (self.value * (self._count - 1) + price) / self._count
            )
            if self._count == self.period:
                return self.value
            return None
        else:
            self.value = price * self.k + self.value * (1 - self.k)
            return self.value


class _SMACalc:
    """SMA 增量计算器（滚动窗口）"""
    def __init__(self, period: int):
        self.period = period
        self._buf: Deque[float] = deque(maxlen=period)
        self.value: Optional[float] = None

    def update(self, price: float) -> Optional[float]:
        self._buf.append(price)
        if len(self._buf) == self.period:
            self.value = sum(self._buf) / self.period
            return self.value
        return None


class _ATRCalc:
    """ATR 增量计算器（Wilder平滑）"""
    def __init__(self, period: int):
        self.period = period
        self._prev_close: Optional[float] = None
        self._count = 0
        self.value: Optional[float] = None

    def update(self, high: float, low: float, close: float) -> Optional[float]:
        if self._prev_close is not None:
            tr = max(
                high - low,
                abs(high - self._prev_close),
                abs(low - self._prev_close),
            )
        else:
            tr = high - low
        self._prev_close = close

        self._count += 1
        if self._count <= self.period:
            self.value = (
                tr if self.value is None
                else (self.value * (self._count - 1) + tr) / self._count
            )
            if self._count == self.period:
                return self.value
            return None
        else:
            self.value = (self.value * (self.period - 1) + tr) / self.period
            return self.value


class _RSICalc:
    """RSI 增量计算器（Wilder平滑）"""
    def __init__(self, period: int = 14):
        self.period = period
        self._prev_close: Optional[float] = None
        self._count = 0
        self._avg_gain = 0.0
        self._avg_loss = 0.0
        self.value: Optional[float] = None

    def update(self, close: float) -> Optional[float]:
        if self._prev_close is None:
            self._prev_close = close
            return None
        change = close - self._prev_close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        self._prev_close = close
        self._count += 1

        if self._count <= self.period:
            self._avg_gain += gain / self.period
            self._avg_loss += loss / self.period
            if self._count == self.period:
                rs = self._avg_gain / self._avg_loss if self._avg_loss != 0 else 1e9
                self.value = 100 - 100 / (1 + rs)
                return self.value
            return None
        else:
            self._avg_gain = (self._avg_gain * (self.period - 1) + gain) / self.period
            self._avg_loss = (self._avg_loss * (self.period - 1) + loss) / self.period
            rs = self._avg_gain / self._avg_loss if self._avg_loss != 0 else 1e9
            self.value = 100 - 100 / (1 + rs)
            return self.value


class _MACDCalc:
    """MACD 增量计算器"""
    def __init__(self, fast=12, slow=26, signal=9):
        self._ema_fast = _EMACalc(fast)
        self._ema_slow = _EMACalc(slow)
        self._ema_signal = _EMACalc(signal)
        self.macd: Optional[float] = None
        self.signal_line: Optional[float] = None
        self.histogram: Optional[float] = None

    def update(self, close: float):
        ef = self._ema_fast.update(close)
        es = self._ema_slow.update(close)
        if ef is not None and es is not None:
            self.macd = ef - es
            sig = self._ema_signal.update(self.macd)
            if sig is not None:
                self.signal_line = sig
                self.histogram = self.macd - sig


# ──────────────────────────────────────────────
# 状态机多因子策略类
# ──────────────────────────────────────────────

class StateMachineStrategy:
    """
    基于"状态机"的多因子量化策略
    ──────────────────────────────
    参数说明：
        ma_fast      (int)   快速均线周期，默认 5
        ma_slow      (int)   慢速均线周期，默认 20
        rsi_period   (int)   RSI 周期，默认 14
        rsi_bull     (float) RSI 多头阈值，默认 55
        rsi_bear     (float) RSI 空头阈值，默认 45
        vol_period   (int)   成交量均线周期，默认 20
        vol_multi    (float) 量能放大倍数阈值，默认 1.2
        atr_period   (int)   ATR 周期，默认 14
        atr_multi    (float) ATR 止损倍数，默认 2.0
        bull_threshold (int) 触发多头所需因子数，默认 3
        bear_threshold (int) 触发空头所需因子数，默认 3
        fixed_size   (int)   每次交易手数/股数，默认 1
        enable_short (bool)  是否允许做空，默认 False（A股）
    """

    # 策略元信息（vnpy 规范）
    author = "StateMachineStrategy"
    parameters = [
        "ma_fast", "ma_slow",
        "rsi_period", "rsi_bull", "rsi_bear",
        "vol_period", "vol_multi",
        "atr_period", "atr_multi",
        "bull_threshold", "bear_threshold",
        "fixed_size", "enable_short",
    ]
    variables = ["pos", "state", "bull_count", "bear_count", "stop_price"]

    def __init__(
        self,
        cta_engine,
        strategy_name: str,
        vt_symbol: str,
        setting: dict,
    ):
        self.cta_engine = cta_engine
        self.strategy_name = strategy_name
        self.vt_symbol = vt_symbol

        # ── 策略参数（从setting读取，带默认值）──
        self.ma_fast: int = int(setting.get("ma_fast", 5))
        self.ma_slow: int = int(setting.get("ma_slow", 20))
        self.rsi_period: int = int(setting.get("rsi_period", 14))
        self.rsi_bull: float = float(setting.get("rsi_bull", 55.0))
        self.rsi_bear: float = float(setting.get("rsi_bear", 45.0))
        self.vol_period: int = int(setting.get("vol_period", 20))
        self.vol_multi: float = float(setting.get("vol_multi", 1.2))
        self.atr_period: int = int(setting.get("atr_period", 14))
        self.atr_multi: float = float(setting.get("atr_multi", 2.0))
        self.bull_threshold: int = int(setting.get("bull_threshold", 3))
        self.bear_threshold: int = int(setting.get("bear_threshold", 3))
        self.fixed_size: int = int(setting.get("fixed_size", 1))
        self.enable_short: bool = bool(setting.get("enable_short", False))

        # ── 策略变量 ──
        self.pos: int = 0               # 当前持仓（正=多，负=空）
        self.state: int = STATE_NEUTRAL  # 当前市场状态
        self.bull_count: int = 0         # 本次bar看多因子数
        self.bear_count: int = 0         # 本次bar看空因子数
        self.stop_price: float = 0.0     # 止损价

        # ── vnpy 标准状态 ──
        self.inited: bool = False
        self.trading: bool = False

        # ── 指标计算器 ──
        self._sma_fast = _SMACalc(self.ma_fast)
        self._sma_slow = _SMACalc(self.ma_slow)
        self._rsi = _RSICalc(self.rsi_period)
        self._vol_ma = _SMACalc(self.vol_period)
        self._atr = _ATRCalc(self.atr_period)
        self._macd = _MACDCalc(12, 26, 9)

        # ── 状态缓存 ──
        self._prev_state: int = STATE_NEUTRAL
        self._bar_count: int = 0
        self._warmup: int = max(self.ma_slow, 26 + 9, self.rsi_period, self.vol_period, self.atr_period) + 5

    # ──────────────── vnpy 生命周期 ────────────────

    def on_init(self):
        self.write_log(f"策略初始化: {self.strategy_name}")
        self.write_log(f"参数: MA({self.ma_fast}/{self.ma_slow}), RSI({self.rsi_period}), "
                       f"Vol倍数({self.vol_multi}), ATR倍数({self.atr_multi}), "
                       f"Bull阈值({self.bull_threshold}), Bear阈值({self.bear_threshold})")

    def on_start(self):
        self.write_log("策略启动")

    def on_stop(self):
        self.write_log("策略停止")

    # ──────────────── 核心K线处理 ────────────────

    def on_bar(self, bar):
        """每根K线到来时调用（主入口）"""
        self._bar_count += 1

        close = bar.close_price
        high = bar.high_price
        low = bar.low_price
        volume = bar.volume

        # 1. 更新所有指标
        sma_fast = self._sma_fast.update(close)
        sma_slow = self._sma_slow.update(close)
        rsi = self._rsi.update(close)
        vol_ma = self._vol_ma.update(volume)
        atr = self._atr.update(high, low, close)
        self._macd.update(close)

        # 2. 预热期不交易
        if self._bar_count < self._warmup:
            return
        if not self.trading:
            return

        # 3. 判断各因子状态
        self.bull_count = 0
        self.bear_count = 0

        # 因子1：趋势因子（MA金叉/死叉）
        if sma_fast is not None and sma_slow is not None:
            if sma_fast > sma_slow:
                self.bull_count += 1
            elif sma_fast < sma_slow:
                self.bear_count += 1

        # 因子2：动量因子（RSI）
        if rsi is not None:
            if rsi > self.rsi_bull:
                self.bull_count += 1
            elif rsi < self.rsi_bear:
                self.bear_count += 1

        # 因子3：量能因子（成交量放大）
        if vol_ma is not None and vol_ma > 0:
            if volume > vol_ma * self.vol_multi:
                # 放量配合方向
                if sma_fast is not None and sma_slow is not None:
                    if sma_fast > sma_slow:
                        self.bull_count += 1
                    else:
                        self.bear_count += 1
                else:
                    # 无均线方向时中性
                    pass
            elif volume < vol_ma / self.vol_multi:
                # 缩量，反向加分
                pass  # 缩量信号较弱，不单独计分

        # 因子4：MACD因子
        if self._macd.histogram is not None:
            if self._macd.histogram > 0:
                self.bull_count += 1
            elif self._macd.histogram < 0:
                self.bear_count += 1

        # 4. 状态机转换
        self._prev_state = self.state
        if self.bull_count >= self.bull_threshold:
            self.state = STATE_BULL
        elif self.bear_count >= self.bear_threshold:
            self.state = STATE_BEAR
        else:
            self.state = STATE_NEUTRAL

        # 5. 止损检查（优先于状态信号）
        if self.pos > 0 and self.stop_price > 0:
            if close <= self.stop_price:
                self._close_long(bar, close, "止损平多")
                return
        elif self.pos < 0 and self.stop_price > 0:
            if close >= self.stop_price:
                self._close_short(bar, close, "止损平空")
                return

        # 6. 根据状态执行交易
        atr_val = atr if atr is not None else close * 0.01

        if self.state == STATE_BULL:
            if self.pos == 0:
                self._open_long(bar, close, atr_val)
            elif self.pos < 0 and self.enable_short:
                self._close_short(bar, close, "翻多平空")
                self._open_long(bar, close, atr_val)

        elif self.state == STATE_BEAR:
            if self.pos > 0:
                self._close_long(bar, close, "空头信号平多")
            if self.pos == 0 and self.enable_short:
                self._open_short(bar, close, atr_val)

        else:  # NEUTRAL
            if self.pos > 0:
                self._close_long(bar, close, "中性信号平多")
            elif self.pos < 0:
                self._close_short(bar, close, "中性信号平空")

    # ──────────────── 交易辅助方法 ────────────────

    def _open_long(self, bar, price: float, atr: float):
        """开多仓"""
        self.buy(price, self.fixed_size)
        self.stop_price = price - self.atr_multi * atr
        self.write_log(
            f"开多 | 价格={price:.3f} 止损={self.stop_price:.3f} "
            f"多因子={self.bull_count} 空因子={self.bear_count} 状态=BULL"
        )

    def _close_long(self, bar, price: float, reason: str):
        """平多仓"""
        self.sell(price, abs(self.pos))
        self.stop_price = 0.0
        self.write_log(f"平多 [{reason}] | 价格={price:.3f}")

    def _open_short(self, bar, price: float, atr: float):
        """开空仓（仅期货模式）"""
        if not self.enable_short:
            return
        self.short(price, self.fixed_size)
        self.stop_price = price + self.atr_multi * atr
        self.write_log(
            f"开空 | 价格={price:.3f} 止损={self.stop_price:.3f} "
            f"多因子={self.bull_count} 空因子={self.bear_count} 状态=BEAR"
        )

    def _close_short(self, bar, price: float, reason: str):
        """平空仓"""
        self.cover(price, abs(self.pos))
        self.stop_price = 0.0
        self.write_log(f"平空 [{reason}] | 价格={price:.3f}")

    # ──────────────── vnpy 标准交易接口 ────────────────

    def buy(self, price: float, volume: float, stop: bool = False, lock: bool = False):
        from vnpy.trader.constant import Direction, Offset
        return self.cta_engine.send_order(self, Direction.LONG, Offset.OPEN, price, volume, stop, lock)

    def sell(self, price: float, volume: float, stop: bool = False, lock: bool = False):
        from vnpy.trader.constant import Direction, Offset
        return self.cta_engine.send_order(self, Direction.SHORT, Offset.CLOSE, price, volume, stop, lock)

    def short(self, price: float, volume: float, stop: bool = False, lock: bool = False):
        from vnpy.trader.constant import Direction, Offset
        return self.cta_engine.send_order(self, Direction.SHORT, Offset.OPEN, price, volume, stop, lock)

    def cover(self, price: float, volume: float, stop: bool = False, lock: bool = False):
        from vnpy.trader.constant import Direction, Offset
        return self.cta_engine.send_order(self, Direction.LONG, Offset.CLOSE, price, volume, stop, lock)

    # ──────────────── 回调（简单实现）────────────────

    def on_trade(self, trade):
        pass

    def on_order(self, order):
        pass

    def on_stop_order(self, stop_order):
        pass

    # ──────────────── 工具 ────────────────

    def write_log(self, msg: str):
        if hasattr(self.cta_engine, "write_log"):
            self.cta_engine.write_log(msg, self)

    def put_event(self):
        if hasattr(self.cta_engine, "put_event"):
            self.cta_engine.put_event(self)

    def get_engine_type(self):
        if hasattr(self.cta_engine, "get_engine_type"):
            return self.cta_engine.get_engine_type()
        return None
