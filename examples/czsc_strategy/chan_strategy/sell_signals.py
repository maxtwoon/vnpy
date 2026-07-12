"""卖点扩展信号。

这个模块复用 signals.py 的基础分类与买点信号，并补充一卖、二卖、三卖
以及空头结构风控。内部回测与验证统一从这里导入 get_all_signals。
"""
from czsc import CZSC
from czsc.objects import Direction

from chan_strategy.zhongshu import build_zhongshu_from_bis
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.signals import (
    _divergence_power,
    _get_confirmed_bi_list,
    _get_confirming_bi,
    signal_bi_direction,
    signal_data_sufficiency,
    signal_divergence_status,
    signal_first_buy,
    signal_risk_control,
    signal_risk_control_recent,
    signal_zs_confirmation,
    signal_zs_position,
)


def signal_second_buy(c: CZSC, freq: str = "30分钟", buy1_anchor: dict = None) -> dict:
    """安全二买实现：规避旧 signals.py 中 None 分支和 Direction 比较缺陷。"""
    key = f"{freq}_D1BSP_二买V260615"
    if buy1_anchor is None or buy1_anchor.get("price") is None or buy1_anchor.get("zs_zg") is None:
        return {key: "非二买_任意_任意_0"}
    bi_list = _get_confirmed_bi_list(c)
    if not bi_list or len(bi_list) < 5:
        return {key: "非二买_任意_任意_0"}

    anchor_low = buy1_anchor["price"]
    anchor_dt = buy1_anchor.get("dt")
    buy1_idx, best_diff = None, float("inf")
    for i, bi in enumerate(bi_list):
        if bi.direction != Direction.Down:
            continue
        if anchor_dt is not None and bi.edt > anchor_dt:
            continue
        diff = abs(bi.low - anchor_low)
        if diff < best_diff:
            buy1_idx, best_diff = i, diff
    if buy1_idx is None or buy1_idx + 2 >= len(bi_list):
        return {key: "非二买_任意_任意_0"}

    rebound_idx = buy1_idx + 1
    rebound_bi = bi_list[rebound_idx]
    if rebound_bi.direction != Direction.Up:
        return {key: "非二买_任意_任意_0"}
    if anchor_dt is not None and rebound_bi.sdt < anchor_dt:
        return {key: "非二买_任意_任意_0"}

    retracement_idx = rebound_idx + 1
    retracement_bi = bi_list[retracement_idx]
    if retracement_bi.direction != Direction.Down or retracement_bi.low <= anchor_low:
        return {key: "非二买_任意_任意_0"}

    confirm_bi = _get_confirming_bi(bi_list, retracement_idx, Direction.Up)
    if confirm_bi is not None:
        if confirm_bi.low <= anchor_low:
            return {key: "非二买_任意_任意_0"}
        return {key: "二买确认_任意_任意_75"}
    if retracement_idx == len(bi_list) - 1:
        return {key: "二买候选_任意_任意_55"}
    return {key: "非二买_任意_任意_0"}


def signal_third_buy(c: CZSC, freq: str = "30分钟") -> dict:
    """安全三买实现：向上离开中枢，回抽不入中枢，再向上确认。"""
    k1, k2, k3 = freq, "D1BSP", "三买阶段V260615"
    bi_list = _get_confirmed_bi_list(c)
    zhongshu_list = build_zhongshu_from_bis(bi_list)
    v1, score = "非三买", 0
    if not zhongshu_list or len(bi_list) < 5:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}

    last_zs = next((zs for zs in reversed(zhongshu_list) if bi_list[zs["end_idx"] + 1:]), zhongshu_list[-1])
    zg = last_zs["zg"]
    after_zs_bis = bi_list[last_zs["end_idx"] + 1:]
    leave_idx, retrace_idx = None, None
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
                    return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}
            continue
        break
    if leave_idx is None:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}
    if retrace_idx is None:
        v1, score = "离开中枢", 40
    else:
        global_retrace_idx = last_zs["end_idx"] + 1 + retrace_idx
        if _get_confirming_bi(bi_list, global_retrace_idx, Direction.Up) is not None:
            v1, score = "三买确认", 90
        elif any(bi.direction == Direction.Down and bi.low < zg for bi in after_zs_bis[retrace_idx + 1:]):
            v1, score = "非三买", 0
        else:
            v1, score = "回抽不入中枢", 65
    return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}


def signal_first_sell(c: CZSC, freq: str = "30分钟") -> dict:
    """一卖信号：向上离开中枢后的顶背驰确认。"""
    k1, k2, k3 = freq, "D1BSP", "一卖V260615"
    bi_list = _get_confirmed_bi_list(c)
    zhongshu_list = build_zhongshu_from_bis(bi_list)
    v1, score = "非一卖", 0
    if not zhongshu_list or len(bi_list) < 5:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}

    last_zs = next((zs for zs in reversed(zhongshu_list) if bi_list[zs["end_idx"] + 1:]), zhongshu_list[-1])
    up_leave_bis = [
        bi for bi in bi_list[last_zs["end_idx"] + 1:]
        if bi.direction == Direction.Up
    ]
    if not up_leave_bis:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}

    leave_bi = up_leave_bis[-1]
    if leave_bi.high <= last_zs["zg"]:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}

    enter_idx = last_zs["start_idx"] - 1 if last_zs["start_idx"] > 0 else last_zs["start_idx"]
    enter_bi = bi_list[enter_idx]
    enter_power, leave_power = _divergence_power(enter_bi, leave_bi, c)
    if leave_power < enter_power:
        if _get_confirming_bi(bi_list, bi_list.index(leave_bi), Direction.Down) is not None:
            v1, score = "一卖确认", 80
        else:
            v1, score = "一卖候选", 60
    return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}


def signal_second_sell(c: CZSC, freq: str = "30分钟", sell1_anchor: dict = None) -> dict:
    """二卖信号：一卖后回落、反抽不创新高、再向下确认。"""
    k1, k2, k3 = freq, "D1BSP", "二卖V260615"
    bi_list = _get_confirmed_bi_list(c)
    v1, score = "非二卖", 0
    if not bi_list or len(bi_list) < 5:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}
    if sell1_anchor is None or sell1_anchor.get("price") is None or sell1_anchor.get("zs_zd") is None:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}

    anchor_high = sell1_anchor["price"]
    anchor_dt = sell1_anchor.get("dt")
    sell1_idx, best_diff = None, float("inf")
    for i, bi in enumerate(bi_list):
        if bi.direction != Direction.Up:
            continue
        if anchor_dt is not None and bi.edt > anchor_dt:
            continue
        diff = abs(bi.high - anchor_high)
        if diff < best_diff:
            sell1_idx, best_diff = i, diff
    if sell1_idx is None or sell1_idx + 2 >= len(bi_list):
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}

    decline_idx = sell1_idx + 1
    decline_bi = bi_list[decline_idx]
    if decline_bi.direction != Direction.Down:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}
    if anchor_dt is not None and decline_bi.sdt < anchor_dt:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}

    rebound_idx = decline_idx + 1
    rebound_bi = bi_list[rebound_idx]
    if rebound_bi.direction != Direction.Up or rebound_bi.high >= anchor_high:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}

    confirm_bi = _get_confirming_bi(bi_list, rebound_idx, Direction.Down)
    if confirm_bi is not None:
        if confirm_bi.high >= anchor_high:
            return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}
        v1, score = "二卖确认", 75
    elif rebound_idx == len(bi_list) - 1:
        v1, score = "二卖候选", 55
    else:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}
    return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}


def signal_third_sell(c: CZSC, freq: str = "30分钟") -> dict:
    """三卖信号：向下离开中枢，反抽不入中枢，再向下确认。"""
    k1, k2, k3 = freq, "D1BSP", "三卖阶段V260615"
    bi_list = _get_confirmed_bi_list(c)
    zhongshu_list = build_zhongshu_from_bis(bi_list)
    v1, score = "非三卖", 0
    if not zhongshu_list or len(bi_list) < 5:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}

    last_zs = next((zs for zs in reversed(zhongshu_list) if bi_list[zs["end_idx"] + 1:]), zhongshu_list[-1])
    zd = last_zs["zd"]
    after_zs_bis = bi_list[last_zs["end_idx"] + 1:]
    leave_idx, rebound_idx = None, None
    for idx, bi in enumerate(after_zs_bis):
        if leave_idx is None:
            if bi.direction == Direction.Down and bi.low < zd:
                leave_idx = idx
            continue
        if rebound_idx is None:
            if bi.direction == Direction.Up:
                if bi.high <= zd:
                    rebound_idx = idx
                else:
                    return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}
            continue
        break
    if leave_idx is None:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}
    if rebound_idx is None:
        v1, score = "离开中枢", 40
    else:
        global_rebound_idx = last_zs["end_idx"] + 1 + rebound_idx
        if _get_confirming_bi(bi_list, global_rebound_idx, Direction.Down) is not None:
            v1, score = "三卖确认", 90
        elif any(bi.direction == Direction.Up and bi.high > zd for bi in after_zs_bis[rebound_idx + 1:]):
            v1, score = "非三卖", 0
        else:
            v1, score = "反抽不入中枢", 65
    return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}


def signal_short_risk_control(c: CZSC, freq: str = "30分钟", stop_loss_pct: float | None = None) -> dict:
    """空头结构失效信号：价格向上突破最后一个中枢上沿。"""
    k1, k2, k3 = freq, "D1BSP", "空头风控V260615"
    bi_list = _get_confirmed_bi_list(c)
    # Same as long-side risk: the timeout branch is about accumulated BIs in
    # one segmented center, not the nearest local display center.
    zhongshu_list = build_zhongshu_from_bis(bi_list, mode="segment")
    v1, score = "结构完好", 0
    if not zhongshu_list or not bi_list:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}

    last_zs = zhongshu_list[-1]
    last_bi = bi_list[-1]
    if last_bi.raw_bars:
        current_price = last_bi.raw_bars[-1].close
    elif last_bi.direction == Direction.Up:
        current_price = last_bi.high
    else:
        current_price = last_bi.low
    pct = stop_loss_pct if stop_loss_pct is not None else STRATEGY_CONFIG["structural_invalidation_pct"]
    if current_price > last_zs["zg"] * (1 + pct):
        v1, score = "结构失效", 95
    elif last_zs["n_bis"] >= 9:
        v1, score = "震荡超限", 70
    return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}


def signal_short_risk_control_recent(c: CZSC, freq: str = "30分钟", stop_loss_pct: float | None = None) -> dict:
    """Recent-mode short structural failure signal for restructured exits.

    信号名: {freq}_D1BSP_空头风控RV260615
    分类: 结构完好 / 结构失效

    Uses mode="recent" so the structural-exit center aligns with the center
    used by position/direction factors. The threshold is read from
    ``STRATEGY_CONFIG["structural_invalidation_pct"]``.
    """
    k1, k2, k3 = freq, "D1BSP", "空头风控RV260615"
    bi_list = _get_confirmed_bi_list(c)
    zhongshu_list = build_zhongshu_from_bis(bi_list, mode="recent")
    v1, score = "结构完好", 0
    if not zhongshu_list or not bi_list:
        return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}

    last_zs = zhongshu_list[-1]
    last_bi = bi_list[-1]
    if last_bi.raw_bars:
        current_price = last_bi.raw_bars[-1].close
    elif last_bi.direction == Direction.Up:
        current_price = last_bi.high
    else:
        current_price = last_bi.low
    pct = stop_loss_pct if stop_loss_pct is not None else STRATEGY_CONFIG["structural_invalidation_pct"]
    if current_price > last_zs["zg"] * (1 + pct):
        v1, score = "结构失效", 95
    return {f"{k1}_{k2}_{k3}": f"{v1}_任意_任意_{score}"}


def get_all_signals(c: CZSC, freq: str = "30分钟",
                    buy1_anchor: dict = None,
                    sell1_anchor: dict = None) -> dict:
    """获取包含买点与卖点的完整信号字典。"""
    signals = {}
    signals.update(signal_bi_direction(c, freq))
    signals.update(signal_zs_position(c, freq))
    signals.update(signal_data_sufficiency(c, freq))
    signals.update(signal_divergence_status(c, freq))
    signals.update(signal_zs_confirmation(c, freq))
    signals.update(signal_first_buy(c, freq))
    signals.update(signal_second_buy(c, freq, buy1_anchor=buy1_anchor))
    signals.update(signal_third_buy(c, freq))
    signals.update(signal_first_sell(c, freq))
    signals.update(signal_second_sell(c, freq, sell1_anchor=sell1_anchor))
    signals.update(signal_third_sell(c, freq))
    signals.update(signal_risk_control(c, freq))
    signals.update(signal_short_risk_control(c, freq))
    if STRATEGY_CONFIG.get("exit_event_semantics") == "restructured":
        signals.update(signal_risk_control_recent(c, freq))
        signals.update(signal_short_risk_control_recent(c, freq))
    return signals
