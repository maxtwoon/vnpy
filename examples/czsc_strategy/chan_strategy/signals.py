"""
缠论标准信号函数模块

所有信号统一使用格式: k1_k2_k3_v1_v2_v3_score
- k1: 周期，如 30分钟、5分钟、日线
- k2: 观察对象与参数，如 D1BI、D1ZS、D1BSP
- k3: 信号名称及版本，如 方向V260615
- v1/v2/v3: 分类结果；未使用位置填 "任意"
- score: 0-100打分

关键约束:
- 只使用已确认结构生成交易信号
- 数据不足时输出明确的降级分类
- 单级别背驰只能输出"疑似"
- 完全分类信号必须穷尽、互斥
"""
from typing import Any

import numpy as np
import pandas as pd

from czsc import CZSC
from czsc.objects import Direction
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.zhongshu import build_zhongshu_from_bis


# ============================================================
# 辅助函数
# ============================================================

def _get_confirmed_bi_list(c: CZSC) -> list:
    """
    获取已确认笔列表

    CZSC 的 ``finished_bis`` 属性用于获取已完成的笔，但当当前未确认笔
    （bars_ubi）仍在延伸并破坏末笔高低点时，``finished_bis`` 的最后一笔
    可能仍在延伸，并非真正"已确认"。

    因此，本函数在 ``finished_bis`` 基础上再做一次防御性过滤：
    - 若 ``last_bi_extend`` 为 True（末笔正在延伸），则剔除最后一笔；
    - 若当前 czsc 版本没有 ``finished_bis``，直接返回空列表。

    交易信号必须基于过滤后的列表，绝对不允许回退到 ``c.bi_list``，否则
    可能使用未确认末笔造成未来函数。
    """
    if not hasattr(c, "finished_bis") or c.finished_bis is None:
        return []

    bis = list(c.finished_bis)

    # 防御性过滤：若最后一笔仍在延伸，则它还不是真正已确认的结构
    if bis and hasattr(c, "last_bi_extend") and c.last_bi_extend:
        bis = bis[:-1]

    return bis


def _bi_power(bi) -> float:
    """计算笔的力度 (价格幅度)"""
    return abs(bi.high - bi.low)


def _macd(closes: np.ndarray, fast: int, slow: int, signal: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute MACD (DIF, DEA, hist) on a close-price series.

    Uses the standard EMA definition: DIF = EMA(fast) - EMA(slow),
    DEA = EMA(DIF, signal), hist = 2 * (DIF - DEA).  Only bars up to the
    current one are consumed, preserving the no-lookahead discipline.
    """
    if len(closes) == 0:
        return np.array([]), np.array([]), np.array([])
    s = pd.Series(closes, dtype=float)
    ema_fast = s.ewm(span=fast, adjust=False).mean().to_numpy()
    ema_slow = s.ewm(span=slow, adjust=False).mean().to_numpy()
    dif = ema_fast - ema_slow
    dea = pd.Series(dif).ewm(span=signal, adjust=False).mean().to_numpy()
    hist = 2.0 * (dif - dea)
    return dif, dea, hist


def _macd_power_for_segment(segment_bars: list, all_bars: list,
                            fast: int, slow: int, signal: int) -> float:
    """Return summed |hist| MACD area for ``segment_bars``.

    MACD is computed over ``all_bars`` (up to the current bar) so the EMA
    state is consistent; the segment magnitude is the sum of |hist| over the
    bars whose dt belongs to ``segment_bars``.  If the segment has no bars or
    no bars are available, returns 0.0.

    There is no amplitude fallback: under ``divergence_model="macd"`` the
    comparison is always MACD-based, even when the available confirmed-bar
    history is shorter than the conventional MACD warm-up period.
    """
    if not segment_bars or not all_bars:
        return 0.0

    closes = np.array([b.close for b in all_bars], dtype=float)
    _, _, hist = _macd(closes, fast, slow, signal)

    segment_dts = {b.dt for b in segment_bars}
    total = 0.0
    for i, bar in enumerate(all_bars):
        if bar.dt in segment_dts:
            total += abs(float(hist[i]))
    return total


def _macd_divergence_power(enter_bi, leave_bi, czsc_obj) -> tuple[float, float]:
    """Return (enter_power, leave_power) using MACD |hist| area.

    Reads only confirmed bars available on ``czsc_obj.bars_raw``.
    """
    fast = STRATEGY_CONFIG.get("macd_fast", 12)
    slow = STRATEGY_CONFIG.get("macd_slow", 26)
    signal = STRATEGY_CONFIG.get("macd_signal", 9)
    all_bars = list(getattr(czsc_obj, "bars_raw", []) or [])

    enter_power = _macd_power_for_segment(
        list(getattr(enter_bi, "raw_bars", []) or []), all_bars, fast, slow, signal
    )
    leave_power = _macd_power_for_segment(
        list(getattr(leave_bi, "raw_bars", []) or []), all_bars, fast, slow, signal
    )
    return enter_power, leave_power


def _divergence_power(enter_bi, leave_bi, czsc_obj) -> tuple[float, float]:
    """Return (enter_power, leave_power) according to the active divergence_model."""
    model = STRATEGY_CONFIG.get("divergence_model", "amplitude")
    if model == "macd":
        return _macd_divergence_power(enter_bi, leave_bi, czsc_obj)
    return _bi_power(enter_bi), _bi_power(leave_bi)


def _get_confirming_bi(bi_list: list, base_idx: int, direction: Direction) -> Any | None:
    """获取 base_idx 之后紧跟着的确认笔。

    约束：
    - 不会返回 base_idx 本身；
    - base_idx 之后必须存在下一根已确认笔；
    - 下一根已确认笔的方向必须与 ``direction`` 一致；
    - 该确认笔必须是当前已确认笔列表的最后一根（确保确认形态是当前末端）。

    当上述任一条件不满足时返回 None，避免在仅有一笔或形态不完整时
    把末笔误当成确认笔。
    """
    if not bi_list or base_idx < 0 or base_idx + 1 >= len(bi_list):
        return None
    confirm_bi = bi_list[base_idx + 1]
    if confirm_bi.direction != direction:
        return None
    if confirm_bi is not bi_list[-1]:
        return None
    return confirm_bi


# ============================================================
# 一、完全分类信号
# ============================================================

def signal_bi_direction(c: CZSC, freq: str = "30分钟") -> dict:
    """
    笔方向信号

    信号名: {freq}_D1BI_方向V260615
    完全分类: 向上 / 向下 / 无有效笔

    判定逻辑:
    - 获取最后一笔的方向
    - 笔列表为空或不足时返回"无有效笔"
    """
    k1 = freq
    k2 = "D1BI"
    k3 = "方向V260615"

    bi_list = _get_confirmed_bi_list(c)

    if not bi_list or len(bi_list) < 1:
        v1 = "无有效笔"
        score = 0
    else:
        last_bi = bi_list[-1]
        if last_bi.direction == Direction.Up:
            v1 = "向上"
            score = 50
        else:
            v1 = "向下"
            score = 50

    key = f"{k1}_{k2}_{k3}"
    value = f"{v1}_任意_任意_{score}"
    return {key: value}


def signal_zs_position(c: CZSC, freq: str = "30分钟") -> dict:
    """
    中枢位置信号

    信号名: {freq}_D1ZS_位置V260615
    完全分类: 中枢上方 / 中枢内 / 中枢下方 / 无中枢

    判定逻辑:
    - 获取最后一个中枢的 zd(下沿) 和 zg(上沿)
    - 用最后一根K线的收盘价判定位置
    - 中枢列表为空时返回"无中枢"
    """
    k1 = freq
    k2 = "D1ZS"
    k3 = "位置V260615"

    bi_list = _get_confirmed_bi_list(c)
    zhongshu_list = build_zhongshu_from_bis(bi_list)

    if not zhongshu_list:
        v1 = "无中枢"
        score = 0
    else:
        last_zs = zhongshu_list[-1]
        zd = last_zs["zd"]
        zg = last_zs["zg"]

        # 获取最后一根已确认K线的收盘价
        # 必须使用已确认结构的价格，避免使用包含未确认末笔的 bars_raw[-1]
        last_bi = bi_list[-1]
        if last_bi.raw_bars:
            last_close = last_bi.raw_bars[-1].close
        elif last_bi.direction == Direction.Up:
            last_close = last_bi.high
        else:
            last_close = last_bi.low

        if last_close > zg:
            v1 = "中枢上方"
            score = 70
        elif last_close < zd:
            v1 = "中枢下方"
            score = 30
        else:
            v1 = "中枢内"
            score = 50

    key = f"{k1}_{k2}_{k3}"
    value = f"{v1}_任意_任意_{score}"
    return {key: value}


def signal_data_sufficiency(c: CZSC, freq: str = "30分钟", min_bi_count: int = 5) -> dict:
    """
    数据充分度信号

    信号名: {freq}_D1ZS_数据状态V260615
    完全分类: 充分 / 不足

    判定逻辑:
    - 笔的数量 >= min_bi_count 时为"充分"
    - 否则为"不足"
    """
    k1 = freq
    k2 = "D1ZS"
    k3 = "数据状态V260615"

    bi_count = len(_get_confirmed_bi_list(c))

    if bi_count >= min_bi_count:
        v1 = "充分"
        score = 100
    else:
        v1 = "不足"
        score = 0

    key = f"{k1}_{k2}_{k3}"
    value = f"{v1}_任意_任意_{score}"
    return {key: value}


def signal_divergence_status(c: CZSC, freq: str = "30分钟") -> dict:
    """
    背驰状态信号

    信号名: {freq}_D1BI_背驰V260615
    完全分类: 无 / 疑似 / 确认

    判定逻辑:
    - 无中枢或笔不足: "无"
    - 最后一笔离开中枢且力度弱于进入: "疑似"（单级别只能疑似）
    - 需要次级别确认才能变为"确认"（在多级别协同中处理）

    力度计算: 由 ``divergence_model`` 配置决定（amplitude: abs(high-low);
    macd: summed |hist| area on confirmed trade-frequency closes）。

    注意: 单级别信号中不会输出"确认"，确认需要次级别协同
    """
    k1 = freq
    k2 = "D1BI"
    k3 = "背驰V260615"

    bi_list = _get_confirmed_bi_list(c)
    zhongshu_list = build_zhongshu_from_bis(bi_list)

    # 默认无背驰
    v1 = "无"
    score = 0

    if not zhongshu_list or len(bi_list) < 5:
        # 数据不足，无法判定
        v1 = "无"
        score = 0
    else:
        last_zs = zhongshu_list[-1]
        zd = last_zs["zd"]
        zg = last_zs["zg"]
        zs_end_idx = last_zs["end_idx"]

        # 中枢之后的笔（离开段）
        after_zs_bis = bi_list[zs_end_idx + 1:]

        if len(after_zs_bis) >= 1:
            # 有离开段
            leave_bi = after_zs_bis[-1]  # 最后的离开笔

            # 寻找进入段: 中枢之前的最后一笔（或中枢第一笔之前的笔）
            zs_start_idx = last_zs["start_idx"]
            if zs_start_idx > 0:
                enter_bi = bi_list[zs_start_idx - 1]
            else:
                # 没有进入段，使用中枢第一笔
                enter_bi = bi_list[zs_start_idx]

            enter_power, leave_power = _divergence_power(enter_bi, leave_bi, c)

            # 判定背驰: 离开段力度弱于进入段
            if leave_power < enter_power:
                # 检查是否离开了中枢
                if leave_bi.direction == Direction.Down and leave_bi.low < zd:
                    # 向下离开中枢且力度减弱 -> 底背驰疑似
                    v1 = "疑似"
                    score = 60
                elif leave_bi.direction == Direction.Up and leave_bi.high > zg:  # pragma: no branch - complementary divergence direction
                    # 向上离开中枢且力度减弱 -> 顶背驰疑似
                    v1 = "疑似"
                    score = 60

    key = f"{k1}_{k2}_{k3}"
    value = f"{v1}_任意_任意_{score}"
    return {key: value}


def signal_zs_confirmation(c: CZSC, freq: str = "30分钟") -> dict:
    """
    中枢结构确认状态信号

    信号名: {freq}_D1ZS_结构状态V260615
    完全分类: 已确认 / 未确认 / 无中枢

    判定逻辑:
    - 中枢至少由3笔构成才为"已确认"
    - 中枢正在构建中（不足3笔重叠）为"未确认"
    - 无中枢时返回"无中枢"
    """
    k1 = freq
    k2 = "D1ZS"
    k3 = "结构状态V260615"

    bi_list = _get_confirmed_bi_list(c)
    zhongshu_list = build_zhongshu_from_bis(bi_list)

    if not zhongshu_list:
        # 检查是否正在构建中枢（有笔但尚不满足3笔重叠）
        if bi_list and len(bi_list) >= 2:
            v1 = "未确认"
            score = 30
        else:
            v1 = "无中枢"
            score = 0
    else:
        last_zs = zhongshu_list[-1]
        n_bis = last_zs["n_bis"]

        if n_bis >= 3:
            v1 = "已确认"
            score = 80
        else:
            v1 = "未确认"
            score = 40

    key = f"{k1}_{k2}_{k3}"
    value = f"{v1}_任意_任意_{score}"
    return {key: value}


# ============================================================
# 二、仓位调整信号（买卖点候选与确认）
# ============================================================

def signal_first_buy(c: CZSC, freq: str = "30分钟") -> dict:
    """
    一买信号

    信号名: {freq}_D1BSP_一买V260615
    分类: 非一买 / 一买候选 / 一买确认

    一买候选条件:
    - 当前级别向下离开中枢并创新低
    - 离开段力度弱于进入段（疑似底背驰）

    一买确认条件:
    - 候选条件满足
    - 基于已确认笔列表，最后向下笔已经结束并出现新的向上笔

    注意: 本函数仅使用 CZSC 的已确认笔（finished_bis），避免使用未确认末笔
    造成未来函数。单级别背驰只能到"候选"或"确认"，完全确认仍建议结合次级别。
    """
    k1 = freq
    k2 = "D1BSP"
    k3 = "一买V260615"

    bi_list = _get_confirmed_bi_list(c)
    zhongshu_list = build_zhongshu_from_bis(bi_list)

    v1 = "非一买"
    score = 0

    if not zhongshu_list or len(bi_list) < 5:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    # recent 模式会返回重叠候选窗口；取最近一个后面已有离开段的中枢，
    # 与一卖/三买/三卖保持同一口径，避免选到尾部无后续笔的展示中枢。
    last_zs = next((zs for zs in reversed(zhongshu_list) if bi_list[zs["end_idx"] + 1:]), zhongshu_list[-1])
    zd = last_zs["zd"]
    zs_end_idx = last_zs["end_idx"]
    zs_start_idx = last_zs["start_idx"]

    # 中枢之后的笔
    after_zs_bis = bi_list[zs_end_idx + 1:]

    if not after_zs_bis:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    # 寻找向下离开中枢的笔
    down_leave_bis = [bi for bi in after_zs_bis if bi.direction == Direction.Down]

    if not down_leave_bis:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    # 取最后一笔向下笔作为离开段
    leave_bi = down_leave_bis[-1]

    # 检查是否向下离开中枢（创新低于中枢下沿）
    if leave_bi.low >= zd:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    # 计算进入段力度
    if zs_start_idx > 0:
        enter_bi = bi_list[zs_start_idx - 1]
    else:
        enter_bi = bi_list[zs_start_idx]
    enter_power, leave_power = _divergence_power(enter_bi, leave_bi, c)

    # 判定背驰: 离开段力度弱于进入段
    if leave_power < enter_power:
        # 检查确认状态: 向下离开笔之后必须紧跟着一根向上的已确认笔，
        # 且该向上笔是当前最后一根已确认笔，才构成一买确认。
        leave_idx = bi_list.index(leave_bi)
        confirm_bi = _get_confirming_bi(bi_list, leave_idx, Direction.Up)
        if confirm_bi is not None:
            v1 = "一买确认"
            score = 80
        else:
            # 向下离开笔仍是最后一笔，或确认形态不完整 -> 候选
            v1 = "一买候选"
            score = 60

    key = f"{k1}_{k2}_{k3}"
    value = f"{v1}_任意_任意_{score}"
    return {key: value}


def signal_second_buy(c: CZSC, freq: str = "30分钟", buy1_anchor: dict = None) -> dict:
    """
    二买信号

    信号名: {freq}_D1BSP_二买V260615
    分类: 非二买 / 二买候选 / 二买确认

    严格绑定一买后的完整结构:
    - 必须存在有效一买锚点（含 anchor_low, anchor_zs_zg）
    - 在已确认笔列表中找到与锚点对应的一买向下笔
    - 一买后必须出现向上反弹笔
    - 回抽笔低点必须高于一买低点（anchor_low），即回抽不创新低
    - 确认形态要求回抽后再出现新的向上笔

    注意:
    二买的核心语义是"一买后反弹再回抽不创新低"，回抽可以进入中枢。
    若回抽不进入中枢（low > anchor_zs_zg），则属于较强的二买/类三买；
    具体是否开仓由 Position 层根据位置信号（中枢上方/中枢内/中枢下方）过滤。

    参数:
    - buy1_anchor: 一买锚点信息 dict，必须包含 {
        "dt": datetime,      # 一买时间（应为对应向下笔的结束时间，即结构时间）
        "price": float,      # 一买价格（低点）
        "zs_zd": float,     # 所属中枢下沿
        "zs_zg": float,     # 所属中枢上沿
    }
      如果为 None 或缺少关键字段，直接返回"非二买"。
    """
    k1 = freq
    k2 = "D1BSP"
    k3 = "二买V260615"

    bi_list = _get_confirmed_bi_list(c)

    v1 = "非二买"
    score = 0

    # 至少需要5笔才能判定二买
    if not bi_list or len(bi_list) < 5:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    # 二买必须严格绑定一买锚点；无锚点或关键字段缺失时不产生任何二买信号
    if (buy1_anchor is None or
            buy1_anchor.get("price") is None or
            buy1_anchor.get("zs_zg") is None):
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    anchor_low = buy1_anchor["price"]
    anchor_dt = buy1_anchor.get("dt")

    # 在已确认笔列表中找到与一买锚点对应的向下笔
    # 优先匹配低点最接近 anchor_low 且结束时间不晚于 anchor_dt 的向下笔
    buy1_idx = None
    best_diff = float('inf')
    for i, bi in enumerate(bi_list):
        if bi.direction != Direction.Down:
            continue
        if anchor_dt is not None and bi.edt > anchor_dt:
            continue
        diff = abs(bi.low - anchor_low)
        if diff < best_diff:
            best_diff = diff
            buy1_idx = i

    if buy1_idx is None or buy1_idx + 1 >= len(bi_list):
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    # 一买后必须紧跟向上反弹笔
    rebound_idx = buy1_idx + 1
    rebound_bi = bi_list[rebound_idx]
    if rebound_bi.direction != Direction.Up:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    # 二买结构必须发生在一买锚点之后，即反弹笔开始时间不早于锚点时间。
    # positions.py 已把 anchor_dt 修正为一买向下笔的结束时间（结构时间），
    # 因此这里恢复使用 anchor_dt 进行过滤。
    if anchor_dt is not None and rebound_bi.sdt < anchor_dt:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    # 检查后续是否有向下回抽笔
    if rebound_idx + 1 >= len(bi_list):
        # 有反弹但尚无回抽，不属于二买
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    retracement_idx = rebound_idx + 1
    retracement_bi = bi_list[retracement_idx]
    if retracement_bi.direction != Direction.Down:
        # 反弹后直接继续向上，没有形成回抽
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    # 二买核心：回抽低点必须高于一买低点（不创新低）。
    # 允许回抽进入中枢，不强求 low > anchor_zs_zg，否则语义将滑向三买。
    if retracement_bi.low <= anchor_low:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    # 只有结构末端才产生有效二买信号，避免 stale 锚点被后续无关形态触发。
    # 使用 _get_confirming_bi 保证：回抽后紧跟着的向上笔是当前最后一根已确认笔。
    confirm_bi = _get_confirming_bi(bi_list, retracement_idx, Direction.Up)
    if confirm_bi is not None:
        # 确认向上笔起点应高于一买低点（由回抽低点已保证）
        if confirm_bi.low <= anchor_low:
            key = f"{k1}_{k2}_{k3}"
            value = f"{v1}_任意_任意_{score}"
            return {key: value}
        v1 = "二买确认"
        score = 75
    elif retracement_idx == len(bi_list) - 1:
        v1 = "二买候选"
        score = 55
    else:
        # 回抽后没有紧跟当前末端的确认向上笔，不属于有效二买
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    key = f"{k1}_{k2}_{k3}"
    value = f"{v1}_任意_任意_{score}"
    return {key: value}


def signal_third_buy(c: CZSC, freq: str = "30分钟") -> dict:
    """
    三买信号

    信号名: {freq}_D1BSP_三买阶段V260615
    分类: 非三买 / 离开中枢 / 回抽不入中枢 / 三买确认

    三买三阶段:
    1. 离开: 向上有效离开中枢（向上笔的高点突破中枢ZG）
    2. 回抽: 次级别回抽，低点不进入中枢ZG
    3. 确认: 再次向上确认（出现新的向上笔）

    判定逻辑:
    - 获取最后一个中枢
    - 检查中枢之后的笔序列
    - 识别当前处于三买的哪个阶段
    """
    k1 = freq
    k2 = "D1BSP"
    k3 = "三买阶段V260615"

    bi_list = _get_confirmed_bi_list(c)
    zhongshu_list = build_zhongshu_from_bis(bi_list)

    v1 = "非三买"
    score = 0

    if not zhongshu_list or len(bi_list) < 5:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    last_zs = zhongshu_list[-1]
    zg = last_zs["zg"]
    zs_end_idx = last_zs["end_idx"]

    # 中枢之后的笔
    after_zs_bis = bi_list[zs_end_idx + 1:]

    if not after_zs_bis:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    # 显式三买状态机:
    # 1. 离开: 第一根向上笔高点突破中枢上沿 (bi.high > zg)
    # 2. 回抽: 离开后的第一根向下笔低点不进入中枢 (bi.low >= zg)
    # 3. 确认: 回抽后紧跟的当前末笔为向上笔
    #
    # 注意: 确认向上笔通常也会再次突破 zg，不能把它重新识别为新的离开笔。
    leave_idx = None
    retrace_idx = None

    for idx, bi in enumerate(after_zs_bis):
        if leave_idx is None:
            if bi.direction == Direction.Up and bi.high > zg:
                leave_idx = idx
            continue

        if retrace_idx is None:
            if bi.direction == Direction.Down:
                if bi.low >= zg:
                    retrace_idx = idx
                else:
                    # 离开后的首次回抽跌入中枢，三买失效
                    v1 = "非三买"
                    score = 0
                    key = f"{k1}_{k2}_{k3}"
                    value = f"{v1}_任意_任意_{score}"
                    return {key: value}
            continue

        # 已经完成“离开 + 有效回抽”，后续阶段由当前末笔确认。
        break

    if leave_idx is None:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    if retrace_idx is None:
        v1 = "离开中枢"
        score = 40
    else:
        global_retrace_idx = zs_end_idx + 1 + retrace_idx
        if _get_confirming_bi(bi_list, global_retrace_idx, Direction.Up) is not None:
            v1 = "三买确认"
            score = 90
        elif any(
            bi.direction == Direction.Down and bi.low < zg
            for bi in after_zs_bis[retrace_idx + 1:]
        ):
            v1 = "非三买"
            score = 0
        else:
            v1 = "回抽不入中枢"
            score = 65

    key = f"{k1}_{k2}_{k3}"
    value = f"{v1}_任意_任意_{score}"
    return {key: value}


def signal_risk_control(c: CZSC, freq: str = "30分钟", stop_loss_pct: float = 0.05) -> dict:
    """
    结构失效信号（原名"风控信号"）

    信号名: {freq}_D1BSP_风控V260615
    分类: 结构完好 / 结构失效 / 震荡超限

    语义说明:
    - 结构完好: 技术结构正常，无需干预
    - 结构失效: 价格跌破中枢下沿（技术面平仓理由，来自市场结构）
    - 震荡超限: 中枢内笔数过多，无明确方向（结构性超时）

    与Position.stop_loss的关系:
    - 本信号 = 技术面结构平仓理由（来自市场结构分析）
    - Position.stop_loss = 风控底线（来自资金管理）
    - 两者并存，先触发者执行，这是合理的设计

    判定逻辑:
    - 结构失效: 价格跌破最后一个中枢下沿的 stop_loss_pct 比例
    - 震荡超限: 中枢之后没有明确方向（笔在中枢内振荡超过一定数量）
    """
    k1 = freq
    k2 = "D1BSP"
    k3 = "风控V260615"

    bi_list = _get_confirmed_bi_list(c)
    # "震荡超限" measures how many BIs one center has accumulated, so keep
    # segmentation semantics here instead of the nearest-local display center.
    zhongshu_list = build_zhongshu_from_bis(bi_list, mode="segment")

    v1 = "结构完好"
    score = 0

    if not zhongshu_list or not bi_list:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    last_zs = zhongshu_list[-1]
    zd = last_zs["zd"]

    # 获取当前价格（必须使用已确认结构的终点价格）
    last_bi = bi_list[-1]
    if last_bi.raw_bars:
        current_price = last_bi.raw_bars[-1].close
    elif last_bi.direction == Direction.Up:
        current_price = last_bi.high
    else:
        current_price = last_bi.low

    # 结构失效检测: 价格跌破中枢下沿的 (1 - stop_loss_pct) 位置
    stop_level = zd * (1 - stop_loss_pct)
    if current_price < stop_level:
        v1 = "结构失效"
        score = 95
    else:
        # 震荡超限检测: 中枢内笔数过多（超过9笔在中枢内振荡）
        zs_n_bis = last_zs["n_bis"]
        if zs_n_bis >= 9:
            v1 = "震荡超限"
            score = 70

    key = f"{k1}_{k2}_{k3}"
    value = f"{v1}_任意_任意_{score}"
    return {key: value}


def signal_risk_control_recent(c: CZSC, freq: str = "30分钟", stop_loss_pct: float = 0.05) -> dict:
    """
    Recent-mode structural failure signal for restructured exit semantics.

    信号名: {freq}_D1BSP_风控RV260615
    分类: 结构完好 / 结构失效

    Uses the nearest local center (mode="recent") so that structural failure
    refers to the same center as position/direction factors. The 0.05 threshold
    is copied verbatim from ``signal_risk_control``; it is not tuned here.
    """
    k1 = freq
    k2 = "D1BSP"
    k3 = "风控RV260615"

    bi_list = _get_confirmed_bi_list(c)
    zhongshu_list = build_zhongshu_from_bis(bi_list, mode="recent")

    v1 = "结构完好"
    score = 0

    if not zhongshu_list or not bi_list:
        key = f"{k1}_{k2}_{k3}"
        value = f"{v1}_任意_任意_{score}"
        return {key: value}

    last_zs = zhongshu_list[-1]
    zd = last_zs["zd"]

    last_bi = bi_list[-1]
    if last_bi.raw_bars:
        current_price = last_bi.raw_bars[-1].close
    elif last_bi.direction == Direction.Up:
        current_price = last_bi.high
    else:
        current_price = last_bi.low

    stop_level = zd * (1 - stop_loss_pct)
    if current_price < stop_level:
        v1 = "结构失效"
        score = 95

    key = f"{k1}_{k2}_{k3}"
    value = f"{v1}_任意_任意_{score}"
    return {key: value}


# ============================================================
# 汇总函数
# ============================================================

def get_all_signals(c: CZSC, freq: str = "30分钟", buy1_anchor: dict = None) -> dict:
    """获取所有信号的汇总字典"""
    signals = {}
    signals.update(signal_bi_direction(c, freq))
    signals.update(signal_zs_position(c, freq))
    signals.update(signal_data_sufficiency(c, freq))
    signals.update(signal_divergence_status(c, freq))
    signals.update(signal_zs_confirmation(c, freq))
    signals.update(signal_first_buy(c, freq))
    signals.update(signal_second_buy(c, freq, buy1_anchor=buy1_anchor))
    signals.update(signal_third_buy(c, freq))
    signals.update(signal_risk_control(c, freq))
    if STRATEGY_CONFIG.get("exit_event_semantics") == "restructured":
        signals.update(signal_risk_control_recent(c, freq))
    return signals
