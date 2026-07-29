"""
5分钟交易级别参数标定（只读诊断，A102 D2 前置）
=================================================
设计依据：docs/design/A102_trade_freq_5min_filter_generalization.md §4.2
"止损 ≈ k × 笔幅度中位数，k 与 30 分钟基线一致"。

方法：
1. 读取 five_min_feasibility_probe_<date>.json 中 5 品种两个级别的笔幅度中位数；
2. 取跨品种中位数 med30 / med5，得比例系数 r = med5 / med30；
3. 价格类参数（止损BP、结构失效阈值、trailing启动BP）按 r 缩放
   —— 等价于保持 "参数 / 笔幅度中位数" 的 k 不变；
4. 时间类参数（timeout 按交易bar计数）按级别分钟数比 30/5 = 6 放大，
   保持实际持仓时间上限不变；
5. 比例类参数（trailing_drawback_pct）无尺度，保持不变。

输出：diagnostics/five_min_param_calibration_<date>.json / .md
铁律：只读；RESEARCH-ONLY；不作为盈利能力证明。
"""
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chan_strategy.config import STRATEGY_CONFIG  # noqa: E402

HERE = Path(__file__).parent

# 价格类：按笔幅度比例 r 缩放（k 不变）
PRICE_SCALED_KEYS = [
    "stop_loss_1buy", "stop_loss_2buy", "stop_loss_3buy",
    "stop_loss_1sell", "stop_loss_2sell", "stop_loss_3sell",
    "trailing_start_bp",
]
# 比例阈值类：按 r 缩放
PCT_SCALED_KEYS = ["structural_invalidation_pct"]
# 时间类：按级别分钟数比放大（保持实际时间不变）
TIME_STRETCH_KEYS = [
    "timeout_1buy", "timeout_2buy", "timeout_3buy",
    "timeout_1sell", "timeout_2sell", "timeout_3sell",
]
# 无尺度比例类：不变（需写明理由）
UNCHANGED_KEYS = {"trailing_drawback_pct": "比例回撤容忍，无价格尺度"}


def main() -> int:
    probe_files = sorted(HERE.glob("five_min_feasibility_probe_*.json"))
    if not probe_files:
        print("错误: 未找到 five_min_feasibility_probe_*.json，先跑可行性探针")
        return 1
    probe = json.loads(probe_files[-1].read_text(encoding="utf-8"))
    print(f"输入探针: {probe_files[-1].name} (窗口 {probe['window']})")

    med30, med5 = [], []
    per_symbol = {}
    for sym, entry in probe["symbols"].items():
        m30 = entry["30分钟基线"].get("bi_amp_pct_median")
        m5 = entry["5分钟"].get("bi_amp_pct_median")
        if m30 and m5:
            med30.append(m30)
            med5.append(m5)
            per_symbol[sym] = {"med30": m30, "med5": m5, "r": round(m5 / m30, 4)}
    if len(med30) < 3:
        print("错误: 有效品种不足3个，无法标定")
        return 1

    g30 = statistics.median(med30)
    g5 = statistics.median(med5)
    r = g5 / g30
    time_factor = 30 / 5  # timeout 按交易bar计数，保持实际时间不变

    profile, derivations = {}, []
    for key in PRICE_SCALED_KEYS:
        old = STRATEGY_CONFIG[key]
        k = (old / 100) / g30  # k = 参数(%) / 30分钟笔幅度中位数(%)
        new = round(k * g5 * 100)  # 回算 BP
        profile[key] = new
        derivations.append(
            f"| `{key}` | {old} BP | k={old/100:.2f}%/{g30:.2f}%={k:.2f} | "
            f"{k:.2f}×{g5:.2f}%×100 = **{new} BP** |"
        )
    for key in PCT_SCALED_KEYS:
        old = STRATEGY_CONFIG[key]
        k = old / g30
        new = round(k * g5, 4)
        profile[key] = new
        derivations.append(
            f"| `{key}` | {old} | k={old}/{g30:.2f}%={k:.4f} | "
            f"{k:.4f}×{g5:.2f}% = **{new}** |"
        )
    for key in TIME_STRETCH_KEYS:
        old = STRATEGY_CONFIG[key]
        new = int(round(old * time_factor))
        profile[key] = new
        derivations.append(
            f"| `{key}` | {old} 根 | 时间等价 ×{time_factor:.0f} | "
            f"{old}×{time_factor:.0f} = **{new} 根**（≈{new*5/60:.0f}小时） |"
        )

    report = {
        "calibration": "five_min_trade_freq_profile",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_probe": probe_files[-1].name,
        "read_only": True,
        "not_promotion_evidence": True,
        "global_medians": {"med30_pct": round(g30, 4), "med5_pct": round(g5, 4), "r": round(r, 4)},
        "per_symbol": per_symbol,
        "profile_5分钟": profile,
        "unchanged": UNCHANGED_KEYS,
    }

    out_json = HERE / f"five_min_param_calibration_{datetime.now():%Y%m%d}.json"
    out_md = out_json.with_suffix(".md")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 5分钟交易级别参数标定报告（A102 D2）",
        "",
        "<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->",
        "",
        "> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**",
        ">",
        "> 本报告是 5 分钟交易级别参数 profile 的标定推导记录，不含任何盈亏结论。",
        "",
        f"- 生成时间: {report['generated_at']}",
        f"- 输入探针: {probe_files[-1].name}（窗口 {probe['window']['start']} ~ {probe['window']['end']}）",
        "",
        "## 标定系数",
        "",
        f"- 30分钟跨品种笔幅度中位数 med30 = **{g30:.4f}%**（n={len(med30)}）",
        f"- 5分钟跨品种笔幅度中位数 med5 = **{g5:.4f}%**（n={len(med5)}）",
        f"- 价格缩放系数 r = med5/med30 = **{r:.4f}**",
        f"- 时间放大系数 = 30/5 = **{time_factor:.0f}**（timeout 按交易bar计数，保持实际持仓时间不变）",
        "",
        "## 分品种明细",
        "",
        "| 品种 | 30分钟笔幅度中位数% | 5分钟笔幅度中位数% | r |",
        "|------|--------------------:|-------------------:|--:|",
    ]
    for sym, d in per_symbol.items():
        lines.append(f"| {sym} | {d['med30']} | {d['med5']} | {d['r']} |")
    lines += [
        "",
        "## profile 推导（5分钟）",
        "",
        "| 参数 | 30分钟基线值 | k 推导 | 5分钟 profile 值 |",
        "|------|------------:|--------|----------------:|",
        *derivations,
        "",
        "## 不变参数及理由",
        "",
    ]
    for k, why in UNCHANGED_KEYS.items():
        lines.append(f"- `{k}` = {STRATEGY_CONFIG[k]}：{why}")
    lines += [
        "",
        "## 使用方法",
        "",
        "上表 profile 值填入 `STRATEGY_CONFIG[\"trade_freq_profiles\"][\"5分钟\"]`，",
        "引擎在 `trade_freq=\"5分钟\"` 时应用覆盖；未命中 profile 时行为与现状一致。",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"med30={g30:.4f}%  med5={g5:.4f}%  r={r:.4f}")
    print("5分钟 profile:", json.dumps(profile, ensure_ascii=False))
    print(f"\n输出: {out_json}")
    print(f"输出: {out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
