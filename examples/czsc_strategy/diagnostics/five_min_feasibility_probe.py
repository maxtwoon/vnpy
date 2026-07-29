"""
5分钟交易级别可行性探针（只读诊断）
=====================================
目的：评估把 trade_freq 从 "30分钟" 改为 "5分钟" 的可行性（第一步验证，纯配置侧）。

回答三个问题：
1. 数据覆盖：现有1分钟数据合成5分钟后，bar数/交易日覆盖是否充足？
2. 结构质量：5分钟级别上 CZSC 笔/中枢能否正常生成？密度和幅度如何（对比30分钟基线）？
3. 参数失配风险：5分钟笔幅度与现有止损梯度（200/300/350BP）、结构失效阈值（5%）是否匹配？

实现说明：
- 数据库每品种一张表（{symbol}_1M_raw），必须显式传 table_name；
- czsc 1.0 的 CZSC 默认 max_bi_num=50 只保留最近50笔，本探针统计全窗口结构，
  故显式 max_bi_num=len(bars)；回测引擎的增量用法不受此影响；
- 中枢计数用项目自己的 chan_strategy.zhongshu.build_zhongshu_from_bis
  （segment 模式，非重叠分段），而非 czsc 库的中枢对象。

铁律：只读——不发送委托、不调交易接口、不改策略参数与买卖信号；
输出不含 password/auth_code/api_key/account_id 等敏感字段；
结果不得作为盈利能力证明（结构质量探针，非回测）。

输出：diagnostics/five_min_feasibility_probe_<date>.json / .md
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# 允许从仓库根/子项目目录直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from czsc import CZSC, Freq  # noqa: E402

from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from chan_strategy.data_adapter import SqliteDataAdapter, resample_bars  # noqa: E402
from chan_strategy.zhongshu import build_zhongshu_from_bis  # noqa: E402

SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
# 探针窗口：与近期诊断报告同一批数据末端对齐（数据库快照至 2026-04-24）
WINDOW_START = "2025-01-01"
WINDOW_END = "2026-04-24"

# 现有参数（用于失配分析，仅读取不修改）
STOP_TIERS_BP = [
    STRATEGY_CONFIG["stop_loss_1buy"],
    STRATEGY_CONFIG["stop_loss_2buy"],
    STRATEGY_CONFIG["stop_loss_3buy"],
]
STRUCT_INVALID_PCT = STRATEGY_CONFIG["structural_invalidation_pct"]
TIMEOUT_BARS = [
    STRATEGY_CONFIG["timeout_1buy"],
    STRATEGY_CONFIG["timeout_2buy"],
    STRATEGY_CONFIG["timeout_3buy"],
]


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return round(s[k], 4)


def _analyze_level(bars_1m: list, freq_obj: Freq, minutes: int) -> dict:
    """合成指定级别并跑一遍 CZSC（全窗口笔保留），返回结构质量统计。"""
    bars = resample_bars(bars_1m, freq_obj, minutes)
    if len(bars) < 20:
        return {"bar_count": len(bars), "error": "bar数量不足"}

    days = sorted({b.dt.date() for b in bars})
    # czsc 1.0 默认 max_bi_num=50 只留最近50笔；探针需要全窗口结构统计
    c = CZSC(bars, max_bi_num=len(bars))

    bi_list = list(c.bi_list)
    # 项目自研中枢构建（segment 模式：非重叠分段，每个笔区间一个规范中枢）
    zs_list = build_zhongshu_from_bis(bi_list, mode="segment", lookback=None)

    # 笔幅度（相对当笔中点价格的百分比）
    bi_amp_pct = []
    for bi in bi_list:
        hi, lo = getattr(bi, "high", None), getattr(bi, "low", None)
        if hi and lo and (hi + lo) > 0:
            bi_amp_pct.append((hi - lo) / ((hi + lo) / 2) * 100)

    n_days = len(days)
    return {
        "bar_count": len(bars),
        "trading_days": n_days,
        "bars_per_day": round(len(bars) / n_days, 1) if n_days else None,
        "first_dt": str(bars[0].dt),
        "last_dt": str(bars[-1].dt),
        "bi_count": len(bi_list),
        "bi_per_day": round(len(bi_list) / n_days, 2) if n_days else None,
        "bi_amp_pct_p25": _pct(bi_amp_pct, 0.25),
        "bi_amp_pct_median": _pct(bi_amp_pct, 0.50),
        "bi_amp_pct_p75": _pct(bi_amp_pct, 0.75),
        "zs_count_segment": len(zs_list),
        "bi_count_ge_5": len(bi_list) >= 5,
    }


def _mismatch_notes(five: dict) -> list[str]:
    """根据5分钟笔幅度分布，评估现有参数失配风险。"""
    notes = []
    med = five.get("bi_amp_pct_median")
    if med is None:
        return ["5分钟笔幅度无法统计"]
    for bp in STOP_TIERS_BP:
        ratio = (bp / 100) / med  # BP→% 后与笔幅度中位数比较
        notes.append(
            f"止损 {bp}BP({bp/100:.1f}%) / 5分钟笔幅度中位数({med:.2f}%) = {ratio:.1f}x"
        )
    notes.append(
        f"结构失效阈值 {STRUCT_INVALID_PCT*100:.0f}% / 5分钟笔幅度中位数 = "
        f"{STRUCT_INVALID_PCT*100/med:.1f}x"
    )
    # timeout 按交易bar计数：5分钟下同样根数覆盖时间 = 30分钟的 1/6
    for t in TIMEOUT_BARS:
        notes.append(f"timeout {t}根: 30分钟下≈{t*30/60:.0f}小时 → 5分钟下≈{t*5/60:.1f}小时")
    return notes


def main() -> int:
    adapter = SqliteDataAdapter(SQLITE_DB_PATH)
    report = {
        "probe": "five_min_trade_freq_feasibility",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window": {"start": WINDOW_START, "end": WINDOW_END},
        "read_only": True,
        "not_promotion_evidence": True,
        "symbols": {},
        "errors": {},
    }

    try:
        tables = {t.lower(): t for t in adapter.get_tables()}
        for symbol in SYMBOLS:
            table = tables.get(f"{symbol.lower()}_1m_raw")
            if table is None:
                report["errors"][symbol] = f"table_not_found: {symbol.lower()}_1m_raw"
                print(f"[probe] {symbol}: 找不到表 {symbol.lower()}_1m_raw")
                continue

            print(f"[probe] {symbol}: 加载1分钟数据 {WINDOW_START}~{WINDOW_END} (表 {table}) ...")
            try:
                bars_1m = adapter.load_raw_bars(
                    symbol, freq="1", start_date=WINDOW_START, end_date=WINDOW_END,
                    table_name=table,
                )
            except Exception as e:  # noqa: BLE001 - 诊断脚本记录后继续
                report["errors"][symbol] = f"load_failed: {e}"
                print(f"  !! 加载失败: {e}")
                continue
            if not bars_1m:
                report["errors"][symbol] = "no_1m_data_in_window"
                print("  !! 窗口内无1分钟数据")
                continue

            print(f"  1分钟bar: {len(bars_1m)}根 ({bars_1m[0].dt} ~ {bars_1m[-1].dt})")
            five = _analyze_level(bars_1m, Freq.F5, 5)
            thirty = _analyze_level(bars_1m, Freq.F30, 30)
            entry = {
                "bars_1m": len(bars_1m),
                "5分钟": five,
                "30分钟基线": thirty,
            }
            if "error" not in five:
                entry["param_mismatch"] = _mismatch_notes(five)
            report["symbols"][symbol] = entry
            print(
                f"  5分钟: {five.get('bar_count')}bar / {five.get('bi_count')}笔 / "
                f"{five.get('zs_count_segment')}中枢(segment); "
                f"笔幅度中位数 {five.get('bi_amp_pct_median')}%"
            )
            print(
                f"  30分钟: {thirty.get('bar_count')}bar / {thirty.get('bi_count')}笔 / "
                f"{thirty.get('zs_count_segment')}中枢(segment); "
                f"笔幅度中位数 {thirty.get('bi_amp_pct_median')}%"
            )
    finally:
        adapter.close()

    out_json = Path(__file__).parent / f"five_min_feasibility_probe_{datetime.now():%Y%m%d}.json"
    out_md = out_json.with_suffix(".md")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 5分钟交易级别可行性探针（只读诊断）",
        "",
        "<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->",
        "",
        "> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**",
        ">",
        "> 本报告是 5 分钟交易级别的结构质量探针（笔/中枢生成与数据覆盖统计），",
        "> 不是回测，不包含任何盈亏结论，不得作为策略有效性或盈利能力的证据。",
        "",
        f"- 生成时间: {report['generated_at']}",
        f"- 窗口: {WINDOW_START} ~ {WINDOW_END}",
        "- 性质: 结构质量探针，非回测，**不得作为盈利能力证明**",
        "- 中枢口径: `chan_strategy.zhongshu.build_zhongshu_from_bis` segment 模式（非重叠分段）",
        "",
        "| 品种 | 级别 | bar数 | 交易日 | bar/日 | 笔数 | 笔/日 | 笔幅度中位数% | 笔幅度P25/P75% | 中枢数 |",
        "|------|------|------:|-------:|-------:|-----:|------:|--------------:|---------------:|-------:|",
    ]
    for sym, entry in report["symbols"].items():
        for level in ("5分钟", "30分钟基线"):
            d = entry[level]
            lines.append(
                f"| {sym} | {level} | {d.get('bar_count')} | {d.get('trading_days')} | "
                f"{d.get('bars_per_day')} | {d.get('bi_count')} | {d.get('bi_per_day')} | "
                f"{d.get('bi_amp_pct_median')} | "
                f"{d.get('bi_amp_pct_p25')}/{d.get('bi_amp_pct_p75')} | "
                f"{d.get('zs_count_segment')} |"
            )
    lines += ["", "## 参数失配分析（5分钟 vs 现有30分钟校准参数）", ""]
    for sym, entry in report["symbols"].items():
        if "param_mismatch" in entry:
            lines.append(f"### {sym}")
            for n in entry["param_mismatch"]:
                lines.append(f"- {n}")
            lines.append("")
    if report["errors"]:
        lines += ["## 错误", ""]
        for sym, err in report["errors"].items():
            lines.append(f"- {sym}: {err}")
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n输出: {out_json}")
    print(f"输出: {out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
