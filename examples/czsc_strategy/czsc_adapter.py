"""
CZSC 适配层 - 连接 vnpy BarData 与 czsc 缠论分析框架

将 vnpy 的 BarData 转换为 czsc 的 RawBar，封装 CZSC 分析对象，
提供走势判断、背驰检测、中枢分析等便捷接口，供策略层直接调用。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

try:
    from czsc import CZSC, Freq, RawBar
    from czsc.objects import Direction, Mark, ZS
except ImportError:
    raise ImportError(
        "无法导入 czsc 库，请先安装：pip install czsc  "
        "czsc 是缠论技术分析框架，提供 CZSC/RawBar/Freq 等核心类型。"
    )

from vnpy.trader.object import BarData


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def bardata_to_rawbar(bar: BarData, freq: Freq, idx: int = 0) -> RawBar:
    """将 vnpy 的 BarData 转换为 czsc 的 RawBar 格式。

    Args:
        bar: vnpy 的 BarData K线对象
        freq: czsc 的 Freq 枚举值
        idx: K线序号，默认为 0

    Returns:
        czsc RawBar 对象
    """
    return RawBar(
        symbol=bar.symbol,
        dt=bar.datetime,
        freq=freq,
        open=float(bar.open_price),
        close=float(bar.close_price),
        high=float(bar.high_price),
        low=float(bar.low_price),
        vol=float(bar.volume),
        amount=float(bar.turnover),
        id=idx,
    )


def get_czsc_freq(interval_minutes: int) -> Freq:
    """将分钟数转换为 czsc 的 Freq 枚举。

    Args:
        interval_minutes: K线周期对应的分钟数，如 5/15/30/60 等

    Returns:
        对应的 Freq 枚举值

    Raises:
        ValueError: 不支持的分钟数
    """
    _mapping: dict[int, Freq] = {
        1: Freq.F1,
        2: Freq.F2,
        3: Freq.F3,
        4: Freq.F4,
        5: Freq.F5,
        6: Freq.F6,
        10: Freq.F10,
        12: Freq.F12,
        15: Freq.F15,
        20: Freq.F20,
        30: Freq.F30,
        60: Freq.F60,
        120: Freq.F120,
        240: Freq.F120,   # czsc 0.9.x 已移除 F240，以 F120 代替
        360: Freq.F120,   # 同上
        1440: Freq.D,
    }
    freq = _mapping.get(interval_minutes)
    if freq is None:
        supported = sorted(_mapping.keys())
        raise ValueError(
            f"不支持的周期分钟数 {interval_minutes}，"
            f"支持的值: {supported}"
        )
    return freq


# ---------------------------------------------------------------------------
# 数据类型定义
# ---------------------------------------------------------------------------

class TrendType(Enum):
    """走势类型枚举"""
    UP = "up"
    DOWN = "down"
    CONSOLIDATION = "consolidation"


@dataclass
class DivergenceResult:
    """背驰检测结果"""
    has_divergence: bool
    direction: str          # "bull" 多头背驰 / "bear" 空头背驰 / "none"
    strength: float         # 背驰强度 (0-1)，基于笔的幅度比较
    description: str        # 描述信息


@dataclass
class ZSInfo:
    """中枢信息"""
    zg: float               # 中枢上沿
    zd: float               # 中枢下沿
    gg: float               # 中枢区间最高
    dd: float               # 中枢区间最低


# ---------------------------------------------------------------------------
# 核心分析器
# ---------------------------------------------------------------------------

class CzscAnalyzer:
    """封装单周期的 CZSC 缠论分析。

    将 vnpy BarData 增量输入，自动维护缠论分析状态，
    提供笔、分型、中枢、走势、背驰等高级查询接口。
    """

    def __init__(self, freq: int, max_count: int = 1000) -> None:
        """
        Args:
            freq: 周期（分钟数，如 5/30/60/240）
            max_count: 最多保留的K线数量
        """
        self.freq: int = freq
        self.czsc_freq: Freq = get_czsc_freq(freq)
        self.max_count: int = max_count
        self.raw_bars: list[RawBar] = []
        self.czsc: Optional[CZSC] = None
        self._bar_count: int = 0

    # ------------------------------------------------------------------
    # 数据更新
    # ------------------------------------------------------------------

    def update(self, bar: BarData) -> None:
        """增量更新一根K线，触发缠论分析更新。

        Args:
            bar: vnpy 的 BarData K线对象
        """
        raw_bar = bardata_to_rawbar(
            bar=bar,
            freq=self.czsc_freq,
            idx=self._bar_count,
        )
        self._bar_count += 1

        # 维护 raw_bars 列表（循环缓存）
        self.raw_bars.append(raw_bar)
        if len(self.raw_bars) > self.max_count:
            self.raw_bars = self.raw_bars[-self.max_count:]

        if self.czsc is None:
            # 首次初始化 CZSC 对象
            if len(self.raw_bars) >= 3:
                try:
                    self.czsc = CZSC(bars=self.raw_bars)
                except Exception:
                    # K线数据不足以构造 CZSC 时，静默等待更多数据
                    self.czsc = None
        else:
            # 增量更新
            try:
                self.czsc.update(raw_bar)
            except Exception:
                # 增量更新失败时，回退为全量重建
                try:
                    self.czsc = CZSC(bars=self.raw_bars)
                except Exception:
                    self.czsc = None

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def is_ready(self, min_bars: int = 50) -> bool:
        """是否已有足够K线数据用于分析。

        Args:
            min_bars: 最少需要的K线数量，默认 50

        Returns:
            数据是否充足
        """
        return self._bar_count >= min_bars and self.czsc is not None

    def get_bar_count(self) -> int:
        """返回已接收的K线数量。"""
        return self._bar_count

    # ------------------------------------------------------------------
    # 缠论基础数据
    # ------------------------------------------------------------------

    def get_bi_list(self) -> list:
        """获取笔列表，如未初始化返回空列表。"""
        if self.czsc is None:
            return []
        return self.czsc.bi_list

    def get_fx_list(self) -> list:
        """获取分型列表，如未初始化返回空列表。"""
        if self.czsc is None:
            return []
        return self.czsc.fx_list

    def get_zs_list(self) -> list:
        """获取中枢列表，如未初始化返回空列表。"""
        if self.czsc is None:
            return []
        # CZSC 对象没有直接的 zs_list 属性，需要通过笔列表来获取
        # 尝试访问 zs_list 属性（如果存在）
        if hasattr(self.czsc, "zs_list"):
            return self.czsc.zs_list
        # 否则从 bi_list 重建中枢
        return self._build_zs_from_bis()

    def _build_zs_from_bis(self) -> list:
        """从笔列表构建中枢列表。

        使用 czsc.objects.ZS 类从连续的笔中检测中枢。
        """
        bi_list = self.get_bi_list()
        if len(bi_list) < 3:
            return []

        zs_list: list = []
        # 滑动窗口：每3笔尝试构建中枢
        i = 0
        while i <= len(bi_list) - 3:
            window = bi_list[i: i + 3]
            try:
                zs = ZS(bis=window)
                if zs.is_valid:
                    zs_list.append(zs)
                    # 跳过已被中枢消耗的笔
                    i += 3
                else:
                    i += 1
            except Exception:
                i += 1

        return zs_list

    # ------------------------------------------------------------------
    # 高级分析
    # ------------------------------------------------------------------

    def get_trend_type(self) -> TrendType:
        """根据最近笔的方向判断走势类型。

        判断逻辑：
        - 最近3笔均向上（偶数笔向上，即 Direction.Up） → UP
        - 最近3笔均向下（偶数笔向下，即 Direction.Down） → DOWN
        - 其他（交替或笔数不足） → CONSOLIDATION

        注意：笔的 direction 属性表示该笔的走势方向，
        向上笔 Direction.Up 表示价格上涨，向下笔 Direction.Down 表示价格下跌。
        连续同向笔意味着走势延续，交替方向则为震荡。

        Returns:
            TrendType 枚举值
        """
        bi_list = self.get_bi_list()
        if len(bi_list) < 3:
            return TrendType.CONSOLIDATION

        recent_3 = bi_list[-3:]
        directions = [bi.direction for bi in recent_3]

        if all(d == Direction.Up for d in directions):
            return TrendType.UP
        if all(d == Direction.Down for d in directions):
            return TrendType.DOWN
        return TrendType.CONSOLIDATION

    def check_divergence(self) -> DivergenceResult:
        """检测背驰信号（基于笔的力度对比）。

        比较最近两笔同向笔的幅度（price_range = |high - low|）：
        - 如果最新笔幅度 < 前一笔同向笔幅度的 80%，视为背驰
        - bull 背驰：下跌走势中出现（最新同向笔为向下笔），提示可能反转向上
        - bear 背驰：上涨走势中出现（最新同向笔为向上笔），提示可能反转向下

        Returns:
            DivergenceResult 数据对象
        """
        bi_list = self.get_bi_list()
        if len(bi_list) < 4:
            return DivergenceResult(
                has_divergence=False,
                direction="none",
                strength=0.0,
                description="笔数量不足（至少需要4笔）",
            )

        # 分离向上笔和向下笔
        up_bis = [bi for bi in bi_list if bi.direction == Direction.Up]
        down_bis = [bi for bi in bi_list if bi.direction == Direction.Down]

        # 至少需要两笔同向笔才能比较
        last_bi = bi_list[-1]

        if last_bi.direction == Direction.Up:
            # 最后一笔向上 → 检测 bear 背驰（上涨力度减弱）
            if len(up_bis) < 2:
                return DivergenceResult(
                    has_divergence=False,
                    direction="none",
                    strength=0.0,
                    description="向上笔数量不足",
                )
            prev_range = abs(up_bis[-2].high - up_bis[-2].low)
            curr_range = abs(up_bis[-1].high - up_bis[-1].low)
            direction = "bear"
        else:
            # 最后一笔向下 → 检测 bull 背驰（下跌力度减弱）
            if len(down_bis) < 2:
                return DivergenceResult(
                    has_divergence=False,
                    direction="none",
                    strength=0.0,
                    description="向下笔数量不足",
                )
            prev_range = abs(down_bis[-2].high - down_bis[-2].low)
            curr_range = abs(down_bis[-1].high - down_bis[-1].low)
            direction = "bull"

        # 防止除零
        if prev_range == 0:
            return DivergenceResult(
                has_divergence=False,
                direction="none",
                strength=0.0,
                description="前一同向笔幅度为零",
            )

        ratio = curr_range / prev_range
        has_div = ratio < 0.8

        # strength: 幅度比值越小，背驰越强
        # ratio=0.8 → strength=0; ratio=0 → strength=1
        strength = max(0.0, min(1.0, 1.0 - ratio / 0.8)) if has_div else 0.0

        if has_div:
            if direction == "bull":
                desc = (
                    f"多头背驰：最新向下笔幅度 {curr_range:.4f} "
                    f"为前一笔 {prev_range:.4f} 的 {ratio:.1%}"
                )
            else:
                desc = (
                    f"空头背驰：最新向上笔幅度 {curr_range:.4f} "
                    f"为前一笔 {prev_range:.4f} 的 {ratio:.1%}"
                )
        else:
            desc = f"无背驰：同向笔幅度比 {ratio:.1%}"

        return DivergenceResult(
            has_divergence=has_div,
            direction=direction if has_div else "none",
            strength=strength,
            description=desc,
        )

    def get_last_zs(self) -> Optional[ZSInfo]:
        """获取最近一个中枢的信息，无中枢返回 None。

        Returns:
            ZSInfo 数据对象，或 None
        """
        zs_list = self.get_zs_list()
        if not zs_list:
            return None

        last_zs = zs_list[-1]
        return ZSInfo(
            zg=float(last_zs.zg),
            zd=float(last_zs.zd),
            gg=float(last_zs.gg),
            dd=float(last_zs.dd),
        )

    def get_last_bi_direction(self) -> Optional[str]:
        """获取最后一笔的方向。

        Returns:
            'up' / 'down' / None（无笔数据时）
        """
        bi_list = self.get_bi_list()
        if not bi_list:
            return None
        last_dir = bi_list[-1].direction
        if last_dir == Direction.Up:
            return "up"
        elif last_dir == Direction.Down:
            return "down"
        return None

    def get_last_fx(self):
        """获取最后一个已确认的分型。

        Returns:
            FX 对象，或 None（无分型数据时）
        """
        fx_list = self.get_fx_list()
        if not fx_list:
            return None
        return fx_list[-1]

    def is_near_support(self, price: float, tolerance_pct: float = 0.01) -> bool:
        """判断当前价格是否接近最近中枢下沿（支撑位）。

        Args:
            price: 当前价格
            tolerance_pct: 容差百分比，默认 1%

        Returns:
            是否接近支撑位。无中枢时返回 True（不限制）
        """
        zs_info = self.get_last_zs()
        if zs_info is None:
            return True  # 无中枢时不限制，允许任意价位入场
        support = zs_info.zd
        tolerance = support * tolerance_pct
        return abs(price - support) <= tolerance

    def is_near_resistance(self, price: float, tolerance_pct: float = 0.01) -> bool:
        """判断当前价格是否接近最近中枢上沿（阴力位）。
    
        Args:
            price: 当前价格
            tolerance_pct: 容差百分比，默认 1%
    
        Returns:
            是否接近阴力位。无中枢时返回 True（不限制）
        """
        zs_info = self.get_last_zs()
        if zs_info is None:
            return True  # 无中枢时不限制
        resistance = zs_info.zg
        tolerance = resistance * tolerance_pct
        return abs(price - resistance) <= tolerance

    def check_upper_break(self, price: float) -> bool:
        """检测价格是否突破中枢上沿（多空隧道上轨）"""
        zs = self.get_last_zs()
        if zs is None:
            return False
        return price > zs.zg

    def check_lower_break(self, price: float) -> bool:
        """检测价格是否跌破中枢下沿（多空隧道下轨）"""
        zs = self.get_last_zs()
        if zs is None:
            return False
        return price < zs.zd

    def get_distance_to_lower(self, price: float) -> float:
        """计算价格到下轨的距离百分比，返回值如 0.05 表示 5%"""
        zs = self.get_last_zs()
        if zs is None:
            return 999.0  # 无中枢时返回大值，表示不限制
        if zs.zd <= 0:
            return 999.0
        return (price - zs.zd) / zs.zd


# ---------------------------------------------------------------------------
# 简单测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("CzscAdapter module loaded successfully")
    analyzer = CzscAnalyzer(freq=5)
    print(f"CzscAnalyzer initialized: freq={analyzer.freq}")
