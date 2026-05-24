"""
缠论多时间周期CTA交易策略（波段战法版）
=======================================
基于缠论中枢通道突破的多级分仓策略：
- 4小时：大趋势判断 + 无条件止损基准
- 30分钟：趋势确认 + 分仓持仓
- 5分钟：精确入场/出场信号 + 利润锁定

核心规则：
1. 破上轨买入，破下轨卖出
2. 亏损时信号过滤（距更高级别下轨<=5%不卖）
3. 破4H下轨 → 全仓无条件清（终极止损）
4. 总盈利>=20% + 破5m下轨 → 全清；总盈利>=30% → 全清
5. 以损定量：根据价格到各级别下轨的距离计算仓位
6. 主观止损安全网：总亏损超过10%无条件清仓
"""

import sys
import os

# 将当前目录加入路径，确保能导入同目录下的 czsc_adapter
sys.path.insert(0, os.path.dirname(__file__))

from czsc_adapter import CzscAnalyzer, TrendType, DivergenceResult, ZSInfo

from vnpy_ctastrategy import CtaTemplate, StopOrder
from vnpy.trader.object import TickData, BarData, TradeData, OrderData
from vnpy.trader.constant import Direction, Offset, Interval
from vnpy.trader.utility import BarGenerator, ArrayManager


class CzscMultiTimeframeStrategy(CtaTemplate):
    """缠论多时间周期CTA策略 —— 波段战法版

    多级分仓 + 通道突破 + 信号过滤：
    - 5分钟 = 1F级别 → 20%仓位
    - 30分钟 = 5F级别 → 30%仓位
    - 4小时 = 30F级别 → 50%仓位
    """

    author = "CZSC Strategy"

    # ---------------------------------------------------------------
    # 策略参数
    # ---------------------------------------------------------------

    total_capital: float = 1000000    # 总资金（用于计算仓位）
    max_distance_pct: float = 0.30    # 建仓范围：距4H下轨最大距离（30%）
    filter_distance_pct: float = 0.05  # 信号过滤阈值（5%）- 小亏时保护出场
    profit_lock_pct_1: float = 0.20   # 第一档利润锁定（20%）
    profit_lock_pct_2: float = 0.30   # 第二档利润锁定（30%）
    subjective_stop_pct: float = 0.10  # 主观止损安全网（10%）
    min_bi_range_pct: float = 0.005   # 入场笔最小幅度（0.5%价格）
    risk_factor: int = 10             # 以损定量系数
    ratio_5m: float = 0.20            # 5m仓位比例
    ratio_30m: float = 0.30           # 30m仓位比例
    ratio_4h: float = 0.50            # 4h仓位比例
    min_bars_5m: int = 100            # 5m预热K线数
    min_bars_30m: int = 30            # 30m预热K线数
    min_bars_4h: int = 12             # 4h预热K线数

    parameters = [
        "total_capital",
        "max_distance_pct",
        "filter_distance_pct",
        "profit_lock_pct_1",
        "profit_lock_pct_2",
        "subjective_stop_pct",
        "min_bi_range_pct",
        "risk_factor",
        "ratio_5m",
        "ratio_30m",
        "ratio_4h",
        "min_bars_5m",
        "min_bars_30m",
        "min_bars_4h",
    ]

    # ---------------------------------------------------------------
    # 状态变量
    # ---------------------------------------------------------------

    pos_5m: int = 0                   # 5分钟级别持仓股数
    pos_30m: int = 0                  # 30分钟级别持仓股数
    pos_4h: int = 0                   # 4小时级别持仓股数
    entry_price_5m: float = 0.0       # 5m入场均价
    entry_price_30m: float = 0.0      # 30m入场均价
    entry_price_4h: float = 0.0       # 4h入场均价
    total_profit_pct: float = 0.0     # 当前总浮动盈利百分比

    variables = [
        "pos_5m",
        "pos_30m",
        "pos_4h",
        "entry_price_5m",
        "entry_price_30m",
        "entry_price_4h",
        "total_profit_pct",
    ]

    # ---------------------------------------------------------------
    # 初始化
    # ---------------------------------------------------------------

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        # 多周期 BarGenerator
        # bg_5m/bg_30m 从 on_bar(1分钟) 合成
        # bg_4h 从 on_bar(1分钟) 合成为4小时（window=4, interval=Interval.HOUR）
        self.bg_5m = BarGenerator(self.on_bar, 5, self.on_5min_bar)
        self.bg_30m = BarGenerator(self.on_bar, 30, self.on_30min_bar)
        self.bg_4h = BarGenerator(
            self.on_bar, 4, self.on_4hour_bar, interval=Interval.HOUR
        )

        # CZSC 分析器（各周期独立实例）
        self.czsc_5m = CzscAnalyzer(freq=5, max_count=500)
        self.czsc_30m = CzscAnalyzer(freq=30, max_count=300)
        self.czsc_4h = CzscAnalyzer(freq=240, max_count=200)

    # ---------------------------------------------------------------
    # 生命周期回调
    # ---------------------------------------------------------------

    def on_init(self):
        """策略初始化"""
        self.write_log("策略初始化")
        self.load_bar(20)  # 加载20天历史数据预热

    def on_start(self):
        """策略启动"""
        self.write_log("策略启动")

    def on_stop(self):
        """策略停止"""
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        """Tick数据更新"""
        self.bg_5m.update_tick(tick)

    def on_bar(self, bar: BarData):
        """1分钟基础K线回调 - 分发给各周期BarGenerator"""
        self.bg_5m.update_bar(bar)
        self.bg_30m.update_bar(bar)
        self.bg_4h.update_bar(bar)

    # ---------------------------------------------------------------
    # 多周期K线回调
    # ---------------------------------------------------------------

    def on_4hour_bar(self, bar: BarData):
        """4小时K线回调 - 更新大趋势判断和无条件止损位"""
        try:
            self.czsc_4h.update(bar)
        except Exception as e:
            self.write_log(f"4小时CZSC更新异常: {e}")
            return

        # 4H级别只负责提供大趋势参考和无条件止损位
        # 不主动触发交易（由5m回调统一处理）

    def on_30min_bar(self, bar: BarData):
        """30分钟K线回调"""
        try:
            self.czsc_30m.update(bar)
        except Exception as e:
            self.write_log(f"30分钟CZSC更新异常: {e}")
            return

        if not self.czsc_30m.is_ready(self.min_bars_30m):
            return

        # 30分钟级别出场检查
        self._check_30m_exit(bar)

        # 30分钟级别重新进场
        self._check_30m_reentry(bar)

    def on_5min_bar(self, bar: BarData):
        """5分钟K线回调 - 所有交易决策在此执行"""
        try:
            self.czsc_5m.update(bar)
        except Exception as e:
            self.write_log(f"5分钟CZSC更新异常: {e}")
            return

        if not self.czsc_5m.is_ready(self.min_bars_5m):
            return

        # 更新浮动盈亏
        self._update_total_profit(bar.close_price)

        # 检查优先级（从高到低）：
        # 1. 主观止损安全网（10%）
        if self._check_subjective_stop(bar):
            self.put_event()
            return

        # 2. 无条件结构止损（破4H下轨）
        if self._check_unconditional_stop(bar):
            self.put_event()
            return

        # 3. 利润锁定
        if self._check_profit_lock(bar):
            self.put_event()
            return

        # 4. 5m级别出场（破5m下轨 + 信号过滤）
        self._check_5m_exit(bar)

        # 5. 入场/加仓检查
        self._check_entry(bar)
        self._check_5m_reentry(bar)

        self.put_event()

    # ---------------------------------------------------------------
    # 入场逻辑
    # ---------------------------------------------------------------

    def _check_entry(self, bar: BarData):
        """建仓信号：5m突破上轨 + 距4H下轨<=30% + 多级确认条件
        
        确认条件（提高胜率）：
        1. 30m趋势不能为DOWN（避免逆势入场）
        2. 5m最后一笔方向向上（确保突破有笔结构支撑）
        3. 30m无空头背驰信号（避免在顶部入场）
        4. 4H无中枢时回退到30m判断（方向4）
        """
        # 必须完全无持仓才建新仓（防止仓位无限叠加）
        if self.pos != 0 or self.pos_5m > 0 or self.pos_30m > 0 or self.pos_4h > 0:
            return

        # 确认条件1：30m趋势过滤 — 若30m处于下跌趋势则不入场
        if self.czsc_30m.is_ready(self.min_bars_30m):
            trend_30m = self.czsc_30m.get_trend_type()
            if trend_30m == TrendType.DOWN:
                return

        # 确认条件2：5m最后一笔方向向上（确保突破有笔结构支撑，非假突破）
        if self.czsc_5m.is_ready(self.min_bars_5m):
            last_bi_dir = self.czsc_5m.get_last_bi_direction()
            if last_bi_dir != "up":
                return  # 5m笔还向下，突破信号未确认

            # 附加：5m最后笔幅度需>=1%价格（过滤微弱假突破）
            bi_list = self.czsc_5m.get_bi_list()
            if bi_list:
                last_bi = bi_list[-1]
                bi_range = abs(last_bi.high - last_bi.low)
                if bi_range < bar.close_price * self.min_bi_range_pct:
                    return  # 笔幅度太小，可能是噪音而非真实突破

        # 确认条件3：30m无空头背驰信号（避免在上涨末期入场）
        if self.czsc_30m.is_ready(self.min_bars_30m):
            div_30m = self.czsc_30m.check_divergence()
            if div_30m.has_divergence and div_30m.direction == "bear":
                return  # 30m出现空头背驰，上涨可能即将结束

        # 前置条件：4H中枢存在，价格在建仓范围内
        dist_4h = self.czsc_4h.get_distance_to_lower(bar.close_price)
        if dist_4h == 999.0:
            # 方向4：4H无中枢时回退到30m中枢判断（放宽到15%）
            if self.czsc_30m.is_ready(self.min_bars_30m):
                dist_30m = self.czsc_30m.get_distance_to_lower(bar.close_price)
                if dist_30m == 999.0 or dist_30m > 0.15:
                    return  # 30m也无中枢或距离太远，不入场
            else:
                return  # 30m数据不足，不入场
        elif dist_4h > self.max_distance_pct:
            return

        # 5m突破上轨
        if not self.czsc_5m.check_upper_break(bar.close_price):
            return

        # 计算以损定量仓位
        total_ratio = self._calculate_position_ratio(bar.close_price)

        # 一次性三级建仓
        self._open_all_levels(bar.close_price, total_ratio)

    # ---------------------------------------------------------------
    # 5m/30m出场逻辑
    # ---------------------------------------------------------------

    def _check_5m_exit(self, bar: BarData):
        """5分钟级别出场：破5m下轨 + 信号过滤
        
        核心规则：破上轨买入，破下轨卖出
        - 盈利时：破5m下轨直接卖出
        - 亏损时：破5m下轨 + 信号过滤（距30m下轨<=5%不卖，给恢复机会）
        """
        if self.pos_5m <= 0:
            return

        # 检查是否破5m下轨
        if not self.czsc_5m.check_lower_break(bar.close_price):
            return

        # 亏损时：应用信号过滤，距30m下轨<=5%则不卖
        if bar.close_price < self.entry_price_5m:
            dist_30m = self.czsc_30m.get_distance_to_lower(bar.close_price)
            if dist_30m <= self.filter_distance_pct:
                return  # 距30m下轨太近，过滤不卖

        # 破下轨卖出5m仓位
        self._sell_level_5m(bar.close_price)

    def _check_30m_exit(self, bar: BarData):
        """30分钟级别出场：破30m下轨 + 信号过滤
        
        核心规则：破上轨买入，破下轨卖出
        - 盈利时：破30m下轨直接卖出
        - 亏损时：破30m下轨 + 信号过滤（距4H下轨<=5%不卖，给恢复机会）
        """
        if self.pos_30m <= 0:
            return

        if not self.czsc_30m.check_lower_break(bar.close_price):
            return

        # 亏损时：应用信号过滤，距4H下轨<=5%则不卖
        if bar.close_price < self.entry_price_30m:
            dist_4h = self.czsc_4h.get_distance_to_lower(bar.close_price)
            if dist_4h <= self.filter_distance_pct:
                return  # 距4H下轨太近，过滤不卖

        # 破下轨卖出30m仓位
        self._sell_level_30m(bar.close_price)

    # ---------------------------------------------------------------
    # 主观止损安全网
    # ---------------------------------------------------------------

    def _check_subjective_stop(self, bar: BarData) -> bool:
        """主观止损安全网：总亏损超过10%无条件出场
        
        非结构性止损，仅在异常情况（中枢消失、数据异常等）下触发，
        作为保命安全网。正常情况下不应触发此止损。
        """
        if self.pos == 0:
            return False
        if self.total_profit_pct < -self.subjective_stop_pct:
            self.write_log(f"[主观止损] 总亏损{self.total_profit_pct*100:.1f}%超过{self.subjective_stop_pct*100:.0f}%，全清")
            self._clear_all(bar.close_price)
            return True
        return False

    # ---------------------------------------------------------------
    # 无条件止损
    # ---------------------------------------------------------------

    def _check_unconditional_stop(self, bar: BarData) -> bool:
        """破4H下轨 → 无条件全仓清（终极止损）"""
        if self.pos == 0:
            return False
        if self.czsc_4h.check_lower_break(bar.close_price):
            self.write_log(f"[终极止损] 破4H下轨，全仓清")
            self._clear_all(bar.close_price)
            return True
        return False

    # ---------------------------------------------------------------
    # 利润锁定
    # ---------------------------------------------------------------

    def _check_profit_lock(self, bar: BarData) -> bool:
        """利润锁定清仓"""
        if self.pos == 0:
            return False

        # 第二档：>=30%直接清
        if self.total_profit_pct >= self.profit_lock_pct_2:
            self._clear_all(bar.close_price)
            return True

        # 第一档：>=20% + 破5m下轨
        if self.total_profit_pct >= self.profit_lock_pct_1:
            if self.czsc_5m.check_lower_break(bar.close_price):
                self._clear_all(bar.close_price)
                return True

        return False

    # ---------------------------------------------------------------
    # 以损定量计算
    # ---------------------------------------------------------------

    def _calculate_position_ratio(self, price: float) -> float:
        """以损定量公式: (risk_factor/H_level) * ratio_level"""
        h_5m = self.czsc_5m.get_distance_to_lower(price) * 100  # 转为百分比数字
        h_30m = self.czsc_30m.get_distance_to_lower(price) * 100
        h_4h = self.czsc_4h.get_distance_to_lower(price) * 100

        # 防除零
        h_5m = max(h_5m, 1.0)
        h_30m = max(h_30m, 1.0)
        h_4h = max(h_4h, 1.0)

        total_ratio = (
            min(1.0, self.risk_factor / h_5m) * self.ratio_5m +
            min(1.0, self.risk_factor / h_30m) * self.ratio_30m +
            min(1.0, self.risk_factor / h_4h) * self.ratio_4h
        )
        return min(1.0, total_ratio)

    # ---------------------------------------------------------------
    # 开仓/平仓辅助方法
    # ---------------------------------------------------------------

    def _open_all_levels(self, price: float, total_ratio: float):
        """三级建仓"""
        total_value = self.total_capital * total_ratio

        # 计算各级别股数（A股100股整数倍）
        size_5m = max(100, int(total_value * self.ratio_5m / price / 100) * 100)
        size_30m = max(100, int(total_value * self.ratio_30m / price / 100) * 100)
        size_4h = max(100, int(total_value * self.ratio_4h / price / 100) * 100)

        self.pos_5m = size_5m
        self.pos_30m = size_30m
        self.pos_4h = size_4h
        self.entry_price_5m = price
        self.entry_price_30m = price
        self.entry_price_4h = price

        total_size = size_5m + size_30m + size_4h
        self.buy(price, total_size)
        self.write_log(
            f"三级建仓: 价格={price:.2f}, 总股数={total_size}, "
            f"5m={size_5m}, 30m={size_30m}, 4h={size_4h}"
        )

    def _sell_level_5m(self, price: float):
        """卖出5m级别仓位"""
        if self.pos_5m > 0:
            self.sell(price, self.pos_5m)
            self.write_log(f"卖出5m级别: 价格={price:.2f}, 股数={self.pos_5m}")
            self.pos_5m = 0

    def _sell_level_30m(self, price: float):
        """卖出30m级别仓位"""
        if self.pos_30m > 0:
            self.sell(price, self.pos_30m)
            self.write_log(f"卖出30m级别: 价格={price:.2f}, 股数={self.pos_30m}")
            self.pos_30m = 0

    def _sell_level_4h(self, price: float):
        """卖出4h级别仓位"""
        if self.pos_4h > 0:
            self.sell(price, self.pos_4h)
            self.write_log(f"卖出4h级别: 价格={price:.2f}, 股数={self.pos_4h}")
            self.pos_4h = 0

    def _clear_all(self, price: float):
        """全仓清"""
        # 优先卖出实际持仓（self.pos），而非仅依赖分级仓位之和
        actual_pos = self.pos
        level_total = self.pos_5m + self.pos_30m + self.pos_4h
        sell_size = max(actual_pos, level_total)
        if sell_size > 0:
            self.sell(price, sell_size)
            self.write_log(f"全仓清仓: 价格={price:.2f}, 实际持仓={actual_pos}, 分级总计={level_total}")
        self.pos_5m = 0
        self.pos_30m = 0
        self.pos_4h = 0
        self.entry_price_5m = 0.0
        self.entry_price_30m = 0.0
        self.entry_price_4h = 0.0
        self.total_profit_pct = 0.0

    def _update_total_profit(self, price: float):
        """计算总浮动盈利百分比"""
        total_cost = (
            self.pos_5m * self.entry_price_5m +
            self.pos_30m * self.entry_price_30m +
            self.pos_4h * self.entry_price_4h
        )
        if total_cost <= 0:
            self.total_profit_pct = 0.0
            return
        total_value = (self.pos_5m + self.pos_30m + self.pos_4h) * price
        self.total_profit_pct = (total_value - total_cost) / total_cost

    # ---------------------------------------------------------------
    # 5m/30m重新进场
    # ---------------------------------------------------------------

    def _check_5m_reentry(self, bar: BarData):
        """5m重新进场（有大级别底仓时） - 已禁用，避免小额买单过多"""
        # 为避免分仓回测中产生大量小额订单，暂时禁用reentry
        return

    def _check_30m_reentry(self, bar: BarData):
        """30m重新进场（有4H底仓时） - 已禁用，避免小额买单过多"""
        # 为避免分仓回测中产生大量小额订单，暂时禁用reentry
        return

    # ---------------------------------------------------------------
    # 订单与成交回调
    # ---------------------------------------------------------------

    def on_order(self, order: OrderData):
        """订单状态更新回调"""
        pass

    def on_trade(self, trade: TradeData):
        """成交回调"""
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """停止单回调"""
        pass
