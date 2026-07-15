"""
多级别客观结构计算 (analyze_symbol)
====================================

skill 实际调用的工具：对指定标的输出多级别缠论客观结构 JSON，供解盘生成。
所有结构判断都来自此处，skill 文本不得编造。

数据来源（按可用性自动选择）：
  - 期货/已入库标的：读 chan_strategy 的 SQLite（1M → resample 多级别）。
  - 指数日线（如 sh000001）：读 fetch_sh_index_daily.py 产出的日线 CSV（仅日线级）。

输出（JSON）：
  {
    "symbol", "asof", "levels": {
        "日线": {方向, 中枢:{zg,zd,n_bis,位置}, 背驰, 一买/二买/三买, 一卖/二卖/三卖,
                 数据状态, 关键价位:[...], confirmation},
        "30分钟": {...}, "5分钟": {...}   # 数据可用时
    },
    "minute_available": bool,
    "notes": [...]
  }

用法：
  # 指数日线（CSV）
  python analyze_symbol.py --csv sh000001_daily.csv --symbol sh000001
  # 期货（SQLite，多级别）
  python analyze_symbol.py --symbol AP888 --table ap888_1M_raw
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# skill 安装后 scripts/ 在 skill 根下；优先使用环境变量，其次兼容本机仓库路径与开发期相对路径。
_CANDIDATE_ROOTS = [
    os.getenv("CHAN_STRATEGY_ROOT"),
    r"D:\repo\vnpy\examples\czsc_strategy",
    str(Path(__file__).resolve().parents[2]),
]
for _root in _CANDIDATE_ROOTS:
    if _root and Path(_root).exists():
        sys.path.insert(0, str(Path(_root)))
        break

from czsc import CZSC
from czsc.objects import RawBar, Freq, Direction

from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG
from chan_strategy.data_adapter import SqliteDataAdapter, resample_bars
from chan_strategy.signals import _get_confirmed_bi_list
from chan_strategy.zhongshu import build_zhongshu_from_bis

try:
    from chan_strategy.sell_signals import get_all_signals
except ImportError:  # pragma: no cover
    from chan_strategy.signals import get_legacy_signals as get_all_signals


# 我们对外汇报的状态维度：key 后缀 -> 输出字段名
_REPORT_DIMS = {
    "D1BI_方向V260615": "方向",
    "D1ZS_位置V260615": "中枢位置",
    "D1ZS_数据状态V260615": "数据状态",
    "D1BI_背驰V260615": "背驰",
    "D1ZS_结构状态V260615": "结构状态",
    "D1BSP_一买V260615": "一买",
    "D1BSP_二买V260615": "二买",
    "D1BSP_三买阶段V260615": "三买",
    "D1BSP_一卖V260615": "一卖",
    "D1BSP_二卖V260615": "二卖",
    "D1BSP_三卖阶段V260615": "三卖",
    "D1BSP_风控V260615": "多头风控",
    "D1BSP_空头风控V260615": "空头风控",
}


def _v1_by_dim(signals: dict, freq: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, val in signals.items():
        if not key.startswith(freq + "_"):
            continue
        for suf, name in _REPORT_DIMS.items():
            if key.endswith(suf):
                out[name] = val.split("_")[0]
    return out


def _latest_close(czsc: CZSC) -> Optional[float]:
    bars = getattr(czsc, "bars_raw", None) or []
    if not bars:
        return None
    return float(bars[-1].close)


def _confirmed_close(bis: list) -> Optional[float]:
    if not bis:
        return None
    last_bi = bis[-1]
    if getattr(last_bi, "raw_bars", None):
        return float(last_bi.raw_bars[-1].close)
    return float(last_bi.high if last_bi.direction == Direction.Up else last_bi.low)


def _safe_zhongshu_list(czsc: CZSC, bis: list) -> list:
    """Use the same local recent center selector as strategy buy/sell signals."""
    out = build_zhongshu_from_bis(bis, max_bis=9, lookback=30, mode="recent")
    for z in out:
        z.setdefault("source", "local_recent")
    return out


def _position_by_zs(close: Optional[float], zhongshu: Optional[dict]) -> str:
    if close is None or not zhongshu:
        return "无中枢"
    if close > zhongshu["zg"]:
        return "中枢上方"
    if close < zhongshu["zd"]:
        return "中枢下方"
    return "中枢内"


def _trend_direction(bis: list, zhongshu: Optional[dict], close: Optional[float]) -> str:
    """A coarse trend state, separated from the last confirmed BI direction."""
    if len(bis) < 5:
        return "不足"
    position = _position_by_zs(close, zhongshu)
    recent = bis[-5:]
    highs = [float(b.high) for b in recent]
    lows = [float(b.low) for b in recent]
    rising = highs[-1] > highs[0] and lows[-1] >= min(lows[:2])
    falling = lows[-1] < lows[0] and highs[-1] <= max(highs[:2])
    if position == "中枢上方" and rising:
        return "上行趋势"
    if position == "中枢下方" and falling:
        return "下行趋势"
    if position == "中枢内":
        return "震荡"
    return "偏强" if position == "中枢上方" else "偏弱"


def _provisional_context(czsc: CZSC, zhongshu: Optional[dict]) -> dict:
    """用最新收盘价描述相对已确认中枢的位置；不把未确认笔纳入买卖点判断。"""
    close = _latest_close(czsc)
    if close is None:
        return {"available": False, "reason": "缺少最新收盘价"}
    if not zhongshu:
        return {
            "available": False,
            "latest_close": round(close, 4),
            "reason": "无已确认中枢，不能给出相对中枢的预期态",
        }

    zg = float(zhongshu["zg"])
    zd = float(zhongshu["zd"])
    if close > zg:
        position = "中枢上方"
        nearest = "ZG"
        distance = (close - zg) / zg if zg else 0
        note = "最新收盘价位于已确认中枢上方，属于尝试离开或站稳上沿的预期态。"
    elif close < zd:
        position = "中枢下方"
        nearest = "ZD"
        distance = (close - zd) / zd if zd else 0
        note = "最新收盘价位于已确认中枢下方，属于尝试下离开或失守下沿的预期态。"
    else:
        position = "中枢内"
        nearest = "ZG" if abs(zg - close) <= abs(close - zd) else "ZD"
        boundary = zg if nearest == "ZG" else zd
        distance = (close - boundary) / boundary if boundary else 0
        note = "最新收盘价仍在已确认中枢内部，暂按中枢震荡与方向选择处理。"

    return {
        "available": True,
        "latest_close": round(close, 4),
        "relative_position": position,
        "nearest_boundary": nearest,
        "distance_pct": round(distance * 100, 3),
        "note": note,
        "warning": "该字段只描述最新价相对已确认中枢的位置，不参与已确认买卖点判定。",
    }


def _watch_points(snap: dict) -> dict:
    """给解盘层使用的观察点，不等同于确认买卖点。"""
    zhongshu = snap.get("中枢") or {}
    key_prices = snap.get("关键价位") or []
    up: List[str] = []
    down: List[str] = []
    structure: List[str] = []
    bsp: List[str] = []

    zg = zhongshu.get("zg")
    zd = zhongshu.get("zd")
    if zg is not None:
        up.append(f"站稳或重新突破中枢上沿 ZG={zg}")
    if zd is not None:
        down.append(f"跌破或不能收回中枢下沿 ZD={zd}")

    recent_high = snap.get("最近确认高点")
    recent_low = snap.get("最近确认低点")
    if recent_high is not None:
        up.append(f"突破最近确认笔高点 {recent_high}")
    if recent_low is not None:
        down.append(f"跌破最近确认笔低点 {recent_low}")

    direction = snap.get("方向")
    trend = snap.get("趋势方向")
    zs_position = snap.get("中枢位置")
    if zs_position == "中枢内":
        structure.append("当前处在中枢内部，优先观察上沿突破和下沿失守，未突破前按震荡处理")
    elif zs_position == "中枢上方":
        structure.append("当前位于中枢上方，观察是否能维持离开段，若跌回中枢则强度下降")
    elif zs_position == "中枢下方":
        structure.append("当前位于中枢下方，观察是否能收回中枢，不能收回则弱势延续")
    if direction == "向上":
        structure.append("确认笔方向向上，观察向上笔是否延续并突破最近确认高点")
    elif direction == "向下":
        structure.append("确认笔方向向下，观察向下笔是否延续并跌破最近确认低点")
    if trend in {"上行趋势", "偏强"} and zs_position in {"中枢内", "中枢上方"}:
        bsp.append("若后续向上离开中枢后回抽不跌回中枢，可进入潜在三买观察")
    if trend in {"下行趋势", "偏弱"} and zs_position in {"中枢内", "中枢下方"}:
        bsp.append("若后续向下离开中枢后反抽不回中枢，可进入潜在三卖观察")
    if direction == "向上" and zs_position == "中枢下方":
        bsp.append("弱修复阶段若回踩不破中枢下沿，可观察类二买结构")
    if direction == "向下" and zs_position == "中枢上方":
        bsp.append("高位回落阶段若反抽不过中枢上沿，可观察类二卖结构")
    if zhongshu and not bsp:
        structure.append("暂无确认买卖点时，以中枢边界和最近确认笔端点作为后续触发条件")

    third_buy = snap.get("三买")
    third_sell = snap.get("三卖")
    second_buy = snap.get("二买")
    second_sell = snap.get("二卖")
    first_buy = snap.get("一买")
    first_sell = snap.get("一卖")
    divergence = snap.get("背驰")

    if third_buy in {"离开中枢", "回抽不入中枢"}:
        bsp.append(f"三买处于{third_buy}阶段，观察回抽是否始终不进入原中枢并形成确认笔")
    if third_sell in {"离开中枢", "反抽不入中枢"}:
        bsp.append(f"三卖处于{third_sell}阶段，观察反抽是否始终不回到原中枢并形成确认笔")
    if second_buy and not str(second_buy).startswith("非"):
        bsp.append(f"二买处于{second_buy}阶段，观察是否能守住一买锚点区域")
    if second_sell and not str(second_sell).startswith("非"):
        bsp.append(f"二卖处于{second_sell}阶段，观察是否不能重新突破一卖锚点区域")
    if first_buy and not str(first_buy).startswith("非"):
        bsp.append(f"一买处于{first_buy}阶段，观察底背驰后的向上确认质量")
    if first_sell and not str(first_sell).startswith("非"):
        bsp.append(f"一卖处于{first_sell}阶段，观察顶背驰后的向下确认质量")
    if divergence == "疑似":
        bsp.append("背驰处于疑似状态，观察下一段力度是否衰减并完成确认")

    return {
        "向上观察": up,
        "向下观察": down,
        "结构观察": structure,
        "买卖点观察": bsp,
    }


def _zhongshu_and_levels(czsc: CZSC) -> dict:
    bis = _get_confirmed_bi_list(czsc)
    zs_list = _safe_zhongshu_list(czsc, bis)
    info = {"中枢": None, "关键价位": []}
    if zs_list:
        z = zs_list[-1]
        info["中枢"] = {"zg": round(z["zg"], 4), "zd": round(z["zd"], 4),
                        "n_bis": z["n_bis"], "source": z.get("source", "unknown")}
        info["关键价位"] += [round(z["zg"], 4), round(z["zd"], 4)]
    if bis:
        # 最近若干笔端点作为关键价位
        for b in bis[-3:]:
            info["关键价位"] += [round(b.high, 4), round(b.low, 4)]
        info["最近确认高点"] = round(max(float(b.high) for b in bis[-3:]), 4)
        info["最近确认低点"] = round(min(float(b.low) for b in bis[-3:]), 4)
    # 去重保序
    seen = []
    for v in info["关键价位"]:
        if v not in seen:
            seen.append(v)
    info["关键价位"] = seen
    close = _confirmed_close(bis)
    info["中枢位置"] = _position_by_zs(close, info["中枢"])
    info["趋势方向"] = _trend_direction(bis, info["中枢"], close)
    info["provisional_context"] = _provisional_context(czsc, info["中枢"])
    return info


def _level_snapshot(czsc: CZSC, freq: str) -> dict:
    signals = get_all_signals(czsc, freq)
    snap = _v1_by_dim(signals, freq)
    snap.update(_zhongshu_and_levels(czsc))
    snap["watch_points"] = _watch_points(snap)
    snap["confirmation"] = "基于已确认笔（末笔未延伸）"
    return snap


def _parse_asof(asof: Optional[str]) -> Optional[datetime]:
    """支持 'YYYY-MM-DD' 与 'YYYY-MM-DD HH:MM[:SS]'。
    纯日期视为当日收盘（含全天），带时间则精确截断。"""
    if not asof:
        return None
    asof = asof.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(asof, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue
    raise ValueError(f"无法解析 asof: {asof}（用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM）")


def _load_csv_daily(csv_path: Path, symbol: str) -> List[RawBar]:
    import pandas as pd
    df = pd.read_csv(csv_path)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)
    # OHLC 不变量校验（CSV 模式也不盲信）
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    bad = ((h < df[["open", "close", "low"]].max(axis=1))
           | (l > df[["open", "close", "high"]].min(axis=1))
           | (df[["open", "high", "low", "close"]] <= 0).any(axis=1))
    if bad.any():
        df = df[~bad].reset_index(drop=True)
    bars = []
    for i, r in df.iterrows():
        bars.append(RawBar(symbol=symbol, id=i, dt=r["datetime"].to_pydatetime(),
                           freq=Freq.D, open=float(r["open"]), close=float(r["close"]),
                           high=float(r["high"]), low=float(r["low"]),
                           vol=float(r.get("volume", 0) or 0),
                           amount=float(r.get("amount", 0) or 0)))
    return bars


def _load_csv_minute(csv_path: Path, symbol: str) -> List[RawBar]:
    import pandas as pd
    df = pd.read_csv(csv_path)
    dt_col = "datetime" if "datetime" in df.columns else "dt"
    df[dt_col] = pd.to_datetime(df[dt_col])
    df = df.sort_values(dt_col).drop_duplicates(dt_col).reset_index(drop=True)
    bad = (
        (df["high"] < df[["open", "close", "low"]].max(axis=1))
        | (df["low"] > df[["open", "close", "high"]].min(axis=1))
        | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    if bad.any():
        df = df[~bad].reset_index(drop=True)
    bars: List[RawBar] = []
    for i, r in df.iterrows():
        bars.append(RawBar(symbol=symbol, id=i, dt=r[dt_col].to_pydatetime(),
                           freq=Freq.F1, open=float(r["open"]), close=float(r["close"]),
                           high=float(r["high"]), low=float(r["low"]),
                           vol=float(r.get("volume", 0) or 0),
                           amount=float(r.get("amount", 0) or 0)))
    return bars


def analyze(symbol: str, csv: str = None, db_path: str = None, table: str = None,
            asof: str = None, minute_csv: str = None) -> dict:
    notes: List[str] = []
    levels: Dict[str, dict] = {}
    minute_available = False
    asof_dt = _parse_asof(asof)

    if csv:
        # 指数日线模式：只有日线
        bars = _load_csv_daily(Path(csv), symbol)
        if asof_dt:
            bars = [b for b in bars if b.dt <= asof_dt]
        if len(bars) < 35:
            return {"symbol": symbol, "error": f"日线数据不足: {len(bars)} 根"}
        levels["日线"] = _level_snapshot(CZSC(bars), "日线")
        if minute_csv:
            minute_bars = _load_csv_minute(Path(minute_csv), symbol)
            if asof_dt:
                minute_bars = [b for b in minute_bars if b.dt <= asof_dt]
            for name, fobj, minutes in [("5分钟", Freq.F5, 5), ("30分钟", Freq.F30, 30)]:
                rb = resample_bars(minute_bars, fobj, minutes)
                if len(rb) >= 35:
                    levels[name] = _level_snapshot(CZSC(rb), name)
            minute_available = "5分钟" in levels or "30分钟" in levels
            notes.append("数据源=日线CSV + 分钟CSV；次级别推演来自分钟CSV合成。")
        else:
            notes.append("数据源=日线CSV，仅日线级；次级别推演不可用。")
    else:
        # SQLite 多级别模式
        db_path = db_path or SQLITE_DB_PATH
        table = table or f"{symbol.lower()}_1M_raw"
        adapter = SqliteDataAdapter(db_path)
        try:
            bars = adapter.load_raw_bars(symbol=symbol, freq="1", table_name=table)
        finally:
            adapter.close()
        if asof_dt:
            bars = [b for b in bars if b.dt <= asof_dt]
        if len(bars) < 200:
            return {"symbol": symbol, "error": f"1M数据不足: {len(bars)} 根"}

        # 多级别：5分钟 / 30分钟 / 日线
        plans = [("5分钟", Freq.F5, 5), ("30分钟", Freq.F30, 30), ("日线", Freq.D, None)]
        for name, fobj, minutes in plans:
            rb = resample_bars(bars, fobj, minutes)
            if len(rb) >= 35:
                levels[name] = _level_snapshot(CZSC(rb), name)
        minute_available = "5分钟" in levels or "30分钟" in levels

    asof_dt = bars[-1].dt.strftime("%Y-%m-%d %H:%M") if bars else asof
    return {
        "symbol": symbol,
        "asof": asof_dt,
        "minute_available": minute_available,
        "levels": levels,
        "notes": notes,
    }


def main():
    ap = argparse.ArgumentParser(description="多级别客观结构计算")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--csv", default=None, help="日线CSV（指数模式）")
    ap.add_argument("--minute-csv", default=None, help="分钟CSV（指数模式可选；用于合成5分钟/30分钟）")
    ap.add_argument("--db", default=None, help="SQLite路径（期货模式）")
    ap.add_argument("--table", default=None)
    ap.add_argument("--asof", default=None,
                    help="截止时点 YYYY-MM-DD 或 YYYY-MM-DD HH:MM（纯日期=当日收盘）")
    args = ap.parse_args()
    res = analyze(args.symbol, csv=args.csv, db_path=args.db, table=args.table,
                  asof=args.asof, minute_csv=args.minute_csv)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
