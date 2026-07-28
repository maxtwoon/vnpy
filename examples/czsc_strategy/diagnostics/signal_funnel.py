"""
信号漏斗诊断 (Signal Funnel Diagnostic)
========================================

目的：定位"策略几乎不交易"的根因——到底是信号层没产出，还是事件层
（数据/结构闸门、日线过滤、买点确认、二买锚点前置）把信号过滤光了。

做法：完全复刻 BacktestEngine.run() 的信号生成管线（30分钟交易级 + 日线
过滤级、已确认结构、buy1_anchor 回放），但在每根 bar 处对三个子策略的
开仓 Event 做"逐级闸门存活计数"，最后输出：

  1) 信号层分布：每个信号 key 的各分类出现次数（看 一买确认/二买确认/
     三买确认 在信号层到底触发了多少次——这是"信号 vs 事件"的分水岭）。
  2) 每个子策略的开仓漏斗：按 Event 的真实条件顺序，统计累计存活数，
     一眼看出是哪一级闸门把人砍光的。
  3) 二买锚点可用性：单独统计有多少 bar 具备 buy1_anchor，区分"二买被
     自身条件挡住"还是"被锚点前置挡住"。

关键点：闸门判定直接复用真实的 Position/Event/Factor/Signal 对象，不复制
策略逻辑，保证与回测同源、不漂移。

用法：
    python -m diagnostics.signal_funnel AP888
    python diagnostics/signal_funnel.py AP888 --start 2022-01-01 --end 2026-04-24
    python diagnostics/signal_funnel.py AP888 --table ap888_1M_raw
    # 多品种：
    python diagnostics/signal_funnel.py AP888 RB888 SC888 A888 ZN888

注意：本脚本需要真实数据库可用；默认读取 config.SQLITE_DB_PATH
（可用环境变量 CHAN_SQLITE_DB_PATH 覆盖）。
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, OrderedDict
from pathlib import Path

# 允许从同级 examples/czsc_strategy 导入 chan_strategy
sys.path.insert(0, str(Path(__file__).parent.parent))

from czsc import CZSC
from czsc import Freq

from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG, BACKTEST_CONFIG
from chan_strategy.data_adapter import SqliteDataAdapter, resample_bars
from chan_strategy.sell_signals import get_all_signals
from chan_strategy.positions import ChanTimingStrategy, Operate
from chan_strategy.backtest_engine import BacktestEngine


# 我们关注的、用于"信号层 vs 事件层"判断的信号 key 后缀
_INTERESTING_SUFFIXES = [
    "D1BI_方向V260615",
    "D1ZS_位置V260615",
    "D1ZS_数据状态V260615",
    "D1BI_背驰V260615",
    "D1ZS_结构状态V260615",
    "D1BSP_一买V260615",
    "D1BSP_二买V260615",
    "D1BSP_三买阶段V260615",
    "D1BSP_一卖V260615",
    "D1BSP_二卖V260615",
    "D1BSP_三卖阶段V260615",
    "D1BSP_风控V260615",
    "D1BSP_空头风控V260615",
]

_SAFE_TABLE_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _v1(signal_obj) -> str:
    """取 Signal 期望值的 v1（第一段分类），仅用于打标签。"""
    return signal_obj.signal_value.split("_")[0]


def _signal_label(signal_obj, signals_dict: dict) -> str:
    """生成带缺失标记的信号标签，避免把信号缺失误读为条件不满足。"""
    suffix = "" if signal_obj.key in signals_dict else " [MISSING]"
    return f"{signal_obj.key}={_v1(signal_obj)}{suffix}"


def _event_stages(event, signals_dict: dict) -> list[tuple[str, bool]]:
    """把一个开仓 Event 拆成有序的闸门列表 [(label, passed), ...]。

    顺序与 Event.is_match 的语义一致：
      signals_all（逐条拆开，便于定位是哪一条 all 条件挂的）
      → signals_any（整体一项）
      → signals_not（整体一项）
      → factors（任一 factor 满足）
    判定全部复用真实 Signal/Factor 的 is_match，不复制逻辑。
    """
    stages: list[tuple[str, bool]] = []

    for _idx, s in enumerate(event.signals_all):
        stages.append((f"ALL {_signal_label(s, signals_dict)}", s.is_match(signals_dict)))

    if event.signals_any:
        keys = ", ".join(_signal_label(s, signals_dict) for s in event.signals_any)
        passed = any(s.is_match(signals_dict) for s in event.signals_any)
        stages.append((f"ANY({keys})", passed))

    if event.signals_not:
        keys = ", ".join(_signal_label(s, signals_dict) for s in event.signals_not)
        passed = not any(s.is_match(signals_dict) for s in event.signals_not)
        stages.append((f"NOT({keys})", passed))

    if event.factors:
        passed = any(f.is_match(signals_dict) for f in event.factors)
        names = " | ".join(f.name for f in event.factors)
        stages.append((f"FACTOR任一满足({names})", passed))

    return stages


def _factor_signal_breakdown(event, signals_dict: dict) -> list[tuple[str, bool]]:
    """把各 factor 内部的 signals_all/any/not 拆出来做边际统计，
    用于看清"买点确认"这一类核心信号到底有没有在事件层被引用到。
    """
    out: list[tuple[str, bool]] = []
    for f in event.factors:
        for s in f.signals_all:
            out.append((f"[{f.name}] ALL {_signal_label(s, signals_dict)}", s.is_match(signals_dict)))
        for s in f.signals_any:
            out.append((f"[{f.name}] ANY {_signal_label(s, signals_dict)}", s.is_match(signals_dict)))
        for s in f.signals_not:
            out.append((f"[{f.name}] NOT {_signal_label(s, signals_dict)}", not s.is_match(signals_dict)))
    return out


def _validate_table_name(db_path: str, table: str) -> str:
    """校验表名存在且只包含安全字符；SQLite 标识符不能用参数绑定。"""
    if not _SAFE_TABLE_RE.fullmatch(table):
        raise ValueError(f"非法表名: {table!r}；仅允许字母、数字、下划线")

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "select name from sqlite_master where type='table' and name=?",
            (table,),
        ).fetchone()
    if row is None:
        raise ValueError(f"数据库中不存在表: {table}")
    return table


def _select_symbol_value(db_path: str, table: str, start: str, end: str) -> str:
    """处理真实库中的 symbol 大小写漂移（如 ap888 表里同时存 AP888 与 ap888）。
    选定区间内出现次数最多的 symbol 值。
    """
    table = _validate_table_name(db_path, table)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            f"""
            select symbol, count(*) as n from "{table}"
            where datetime >= ? and datetime <= ?
            group by symbol order by n desc limit 1
            """,
            (start, end),
        ).fetchone()
    if row is None:
        raise ValueError(f"{table} 在 {start}~{end} 无数据")
    return row[0]


def run_funnel(
    symbol: str,
    start: str = None,
    end: str = None,
    db_path: str = None,
    table_name: str = None,
    warmup: int = 100,
    enable_short: bool = False,
) -> dict:
    """对单个品种跑信号漏斗诊断，返回结果字典并打印报告。"""
    db_path = db_path or SQLITE_DB_PATH
    start = start or BACKTEST_CONFIG["start_date"]
    end = end or BACKTEST_CONFIG["end_date"]
    table = table_name or f"{symbol.lower()}_1M_raw"
    table = _validate_table_name(db_path, table)

    # 处理大小写漂移，拿到真实 symbol 值
    real_symbol = _select_symbol_value(db_path, table, start, end)

    # ---- 加载 1M 原始数据 ----
    adapter = SqliteDataAdapter(db_path)
    try:
        bars = adapter.load_raw_bars(
            symbol=real_symbol, freq="1",
            start_date=start, end_date=end, table_name=table,
        )
    finally:
        adapter.close()

    if len(bars) < warmup + 10:
        return {"symbol": symbol, "error": f"数据不足: {len(bars)} 根 1M"}

    # ---- 复刻引擎的多级别合成（与 BacktestEngine.run 完全一致）----
    trade_freq_name = STRATEGY_CONFIG.get("trade_freq", "30分钟")
    filter_freq_name = STRATEGY_CONFIG.get("filter_freq", "日线")
    trade_minutes = BacktestEngine._freq_to_minutes(trade_freq_name)
    trade_freq_obj = BacktestEngine._freq_name_to_czsc_freq(trade_freq_name)

    trade_bars = resample_bars(bars, trade_freq_obj, trade_minutes)
    daily_bars = resample_bars(bars, Freq.D, target_minutes=None)

    if len(trade_bars) < warmup + 10:
        return {"symbol": symbol, "error": f"交易周期数据不足: {len(trade_bars)} 根 {trade_freq_name}"}

    czsc_trade = CZSC(trade_bars[:warmup])
    warmup_dt = trade_bars[warmup - 1].dt
    daily_warmup_bars = [b for b in daily_bars if b.dt <= warmup_dt]
    czsc_daily = CZSC(daily_warmup_bars) if len(daily_warmup_bars) >= 3 else None
    daily_filter_configured = filter_freq_name == "日线"
    daily_czsc_initialized = czsc_daily is not None
    daily_filter_passed_to_strategy = daily_filter_configured and daily_czsc_initialized

    strategy = ChanTimingStrategy(
        symbol=real_symbol, freq=trade_freq_name,
        enable_daily_filter=daily_filter_passed_to_strategy,
        enable_short=enable_short,
    )
    positions = strategy.positions  # 真实子策略 Position 对象；enable_short=True 时包含三组空头
    sub_names = [p.name for p in positions]

    daily_bar_idx = len(daily_warmup_bars)

    # ---- 统计容器 ----
    n_eval = 0  # 参与漏斗评估的 bar 数
    daily_available_count = 0
    anchor_available_count = 0

    # 信号层分布: key -> Counter(v1)
    signal_dist: dict[str, Counter] = {}

    # 每个子策略: 有序 stage -> 累计存活 / 边际通过
    cum_survive: dict[str, OrderedDict[str,int]] = {n: OrderedDict() for n in sub_names}
    marg_pass: dict[str, OrderedDict[str,int]] = {n: OrderedDict() for n in sub_names}
    final_open_ok: dict[str, int] = {n: 0 for n in sub_names}
    actual_open_count: dict[str, int] = {n: 0 for n in sub_names}
    # factor 内部信号边际统计
    factor_marg: dict[str, OrderedDict[str,int]] = {n: OrderedDict() for n in sub_names}

    pending_signals = None

    for i in range(warmup, len(trade_bars)):
        bar = trade_bars[i]

        # 1) 先驱动策略状态（维持 buy1_anchor / 持仓），与引擎同序
        prev_trade_counts = {p.name: len(p.trades) for p in positions}
        if pending_signals is not None:
            strategy.update(pending_signals, bar.close, bar.dt,
                            execution_price=bar.open, czsc_obj=czsc_trade)
        else:
            strategy.update({}, bar.close, bar.dt, czsc_obj=czsc_trade)
        for pos in positions:
            new_trades = pos.trades[prev_trade_counts[pos.name]:]
            actual_open_count[pos.name] += sum(
                1 for trade in new_trades if trade.operate in {Operate.LO, Operate.SO}
            )

        # 2) 更新交易级 CZSC
        czsc_trade.update(bar)

        # 3) 增量更新日线 CZSC
        if czsc_daily is not None:
            while daily_bar_idx < len(daily_bars) and daily_bars[daily_bar_idx].dt <= bar.dt:
                czsc_daily.update(daily_bars[daily_bar_idx])
                daily_bar_idx += 1

        # 4) 生成信号（与引擎一致：交易级 + 日线 merge + buy1_anchor）
        buy1_anchor = strategy.get_last_buy1_anchor()
        sell1_anchor = strategy.get_last_sell1_anchor()
        signals = get_all_signals(
            czsc_trade, trade_freq_name,
            buy1_anchor=buy1_anchor,
            sell1_anchor=sell1_anchor,
        )
        daily_present = czsc_daily is not None and bool(czsc_daily.bi_list)
        if daily_present:
            signals.update(get_all_signals(czsc_daily, filter_freq_name))

        # ===== 漏斗打点 =====
        n_eval += 1
        if daily_present:
            daily_available_count += 1
        if buy1_anchor is not None:
            anchor_available_count += 1

        # 信号层分布
        for key, val in signals.items():
            v1 = val.split("_")[0]
            signal_dist.setdefault(key, Counter())[v1] += 1

        # 每个子策略的开仓漏斗（评估真实 open Event，忽略持仓/间隔，
        # 这样测的是"信号+过滤层"的纯事件可触发性；真实开仓数另行统计）
        for pos in positions:
            name = pos.name
            any_open_event_passed = False
            for event_idx, event in enumerate(pos.opens):
                prefix = f"E{event_idx + 1}:{event.name} "
                stages = _event_stages(event, signals)
                survived = True
                for idx, (label, passed) in enumerate(stages):
                    skey = f"{prefix}{idx}. {label}"
                    marg_pass[name].setdefault(skey, 0)
                    cum_survive[name].setdefault(skey, 0)
                    if passed:
                        marg_pass[name][skey] += 1
                    survived = survived and passed
                    if survived:
                        cum_survive[name][skey] += 1
                any_open_event_passed = any_open_event_passed or survived

                # factor 内部信号边际
                for label, passed in _factor_signal_breakdown(event, signals):
                    flabel = f"E{event_idx + 1}:{event.name} {label}"
                    factor_marg[name].setdefault(flabel, 0)
                    if passed:
                        factor_marg[name][flabel] += 1
            if any_open_event_passed:
                final_open_ok[name] += 1

        pending_signals = signals

    result = {
        "symbol": symbol,
        "real_symbol": real_symbol,
        "period": f"{start} ~ {end}",
        "table": table,
        "n_1m_bars": len(bars),
        "n_trade_bars": len(trade_bars),
        "n_eval": n_eval,
        "daily_filter_configured": daily_filter_configured,
        "daily_czsc_initialized": daily_czsc_initialized,
        "daily_filter_passed_to_strategy": daily_filter_passed_to_strategy,
        "daily_available_count": daily_available_count,
        "anchor_available_count": anchor_available_count,
        "signal_dist": {k: dict(v) for k, v in signal_dist.items()},
        "cum_survive": {k: dict(v) for k, v in cum_survive.items()},
        "marg_pass": {k: dict(v) for k, v in marg_pass.items()},
        "factor_marg": {k: dict(v) for k, v in factor_marg.items()},
        "final_open_ok": final_open_ok,
        "actual_open_count": actual_open_count,
        "sub_names": sub_names,
    }
    _print_report(result)
    return result


def _print_report(r: dict) -> None:
    if "error" in r:
        print(f"\n[{r['symbol']}] 错误: {r['error']}")
        return

    print("\n" + "=" * 78)
    print(f"信号漏斗诊断: {r['symbol']} (真实symbol={r['real_symbol']})")
    print(f"区间: {r['period']}  表: {r['table']}")
    print(f"1M K线: {r['n_1m_bars']}  →  交易周期K线: {r['n_trade_bars']}  →  评估bar: {r['n_eval']}")
    print(f"日线过滤配置: {r['daily_filter_configured']}  "
          f"日线CZSC初始化: {r['daily_czsc_initialized']}  "
          f"日线过滤传入策略: {r['daily_filter_passed_to_strategy']}  "
          f"日线信号可用bar: {r['daily_available_count']}/{r['n_eval']}  "
          f"buy1锚点可用bar: {r['anchor_available_count']}/{r['n_eval']}")
    print("=" * 78)

    # ---- 信号层分布（只打我们关心的 key）----
    print("\n[信号层分布] 各信号分类出现次数（事件层之前的纯信号产出）")
    print("-" * 78)
    for suffix in _INTERESTING_SUFFIXES:
        for key in sorted(r["signal_dist"]):
            if key.endswith(suffix):
                dist = r["signal_dist"][key]
                dist_str = ", ".join(f"{v}:{c}" for v, c in sorted(dist.items(), key=lambda x: -x[1]))
                print(f"  {key}: {dist_str}")

    # ---- 每个子策略的漏斗 ----
    for name in r["sub_names"]:
        print("\n" + "-" * 78)
        print(
            f"[开仓漏斗] {name}    事件条件通过bar数: {r['final_open_ok'][name]} / {r['n_eval']}  "
            f"真实开仓次数: {r['actual_open_count'][name]}"
        )
        print("-" * 78)
        cum = r["cum_survive"][name]
        marg = r["marg_pass"][name]
        prev = r["n_eval"]
        print(f"  {'起点(全部评估bar)':<52} 存活={prev}")
        for skey in cum:  # OrderedDict 保序
            surv = cum[skey]
            m = marg.get(skey, 0)
            drop = prev - surv
            flag = "  <== 砍光" if surv == 0 and prev > 0 else ("  <== 主要瓶颈" if drop > prev * 0.5 and prev > 0 else "")
            print(f"  {skey:<52} 存活={surv:<6} (本级边际通过={m}, 较上一级-{drop}){flag}")
            prev = surv

        # factor 内部信号边际（买点确认这类核心信号到底触发了多少次）
        fm = r["factor_marg"][name]
        if fm:
            print("  -- factor内部信号边际通过次数（与顺序无关）--")
            for label, c in fm.items():
                print(f"     {label}: {c}")


def main():
    ap = argparse.ArgumentParser(description="缠论策略信号漏斗诊断")
    ap.add_argument("symbols", nargs="+", help="品种代码，如 AP888 RB888")
    ap.add_argument("--start", default=None, help="开始日期 YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="结束日期 YYYY-MM-DD")
    ap.add_argument("--db", default=None, help="数据库路径，默认用 config")
    ap.add_argument("--table", default=None, help="指定数据表；默认 <symbol小写>_1M_raw")
    ap.add_argument("--warmup", type=int, default=100, help="预热交易周期K线数")
    ap.add_argument("--enable-short", action="store_true", help="同时诊断一卖/二卖/三卖空头子策略")
    ap.add_argument("--keep-going", action="store_true", help="批量诊断时即使某个品种失败也继续，最后仍返回非零")
    ap.add_argument("--config-json", default=None, help="JSON object merged into STRATEGY_CONFIG for diagnostics")
    ap.add_argument("--config-file", default=None, help="JSON file merged into STRATEGY_CONFIG for diagnostics")
    args = ap.parse_args()

    if args.config_json:
        STRATEGY_CONFIG.update(json.loads(args.config_json))
    if args.config_file:
        STRATEGY_CONFIG.update(json.loads(Path(args.config_file).read_text(encoding="utf-8")))

    summary = []
    failures = []
    for sym in args.symbols:
        try:
            r = run_funnel(sym, start=args.start, end=args.end,
                           db_path=args.db, table_name=args.table, warmup=args.warmup,
                           enable_short=args.enable_short)
            if "error" not in r:
                summary.append((sym, r["n_eval"], r["final_open_ok"], r["actual_open_count"]))
            else:
                failures.append((sym, r["error"]))
        except Exception as e:  # noqa: BLE001
            failures.append((sym, str(e)))
            print(f"\n[{sym}] 诊断失败: {e}")
            import traceback
            traceback.print_exc()
            if not args.keep_going:
                raise SystemExit(1) from e

    # 汇总
    if summary:
        print("\n" + "=" * 78)
        print("汇总: 各品种事件条件通过bar数 / 真实开仓次数")
        print("=" * 78)
        for sym, n_eval, fok, aoc in summary:
            parts = ", ".join(f"{k}={fok[k]}/{aoc.get(k, 0)}" for k in fok)
            print(f"  {sym} (评估{n_eval}bar): {parts}")

    if failures:
        print("\n诊断失败品种:")
        for sym, err in failures:
            print(f"  {sym}: {err}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
