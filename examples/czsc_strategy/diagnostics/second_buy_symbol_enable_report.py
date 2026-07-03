from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_SCAN = Path(__file__).with_name("second_buy_stop_loss_scan_20220101_20260424.json")
DEFAULT_OUT = Path(__file__).with_name("second_buy_symbol_enable_report.md")


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def _decision(best: dict) -> str:
    trades = best.get("total_trades", 0)
    pnl = best.get("pnl_sum", 0)
    pf = best.get("profit_factor", 0)
    if trades < 5:
        return "观察：样本少"
    if pnl > 0 and pf >= 1:
        return "可启用"
    if pnl > -0.05 and pf >= 0.8:
        return "谨慎启用"
    return "禁用候选"


def main() -> None:
    parser = argparse.ArgumentParser(description="Suggest per-symbol second-buy enable/disable decisions.")
    parser.add_argument("--scan-json", type=Path, default=DEFAULT_SCAN)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    data = json.loads(args.scan_json.read_text(encoding="utf-8"))
    lines = [
        "# 二买分品种启用建议",
        "",
        f"- 来源：`{args.scan_json.name}`",
        "- 口径：取每个品种在 stop_loss_2buy 扫描中的二买累计收益最优档，再给出启用建议。",
        "",
        "| 品种 | 最优 stop_loss_2buy | 二买交易 | 二买累计收益 | 胜率 | 盈亏比 | 止损率 | 建议 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for symbol, rows in data["symbols"].items():
        best = max(rows, key=lambda r: r.get("pnl_sum", -999))
        pf = best.get("profit_factor")
        pf_text = "inf" if pf == float("inf") or pf == "inf" else f"{pf:.2f}"
        lines.append(
            "| {symbol} | {stop} | {trades} | {pnl} | {win} | {pf} | {stop_rate} | {decision} |".format(
                symbol=symbol,
                stop=best.get("stop_loss_2buy"),
                trades=best.get("total_trades"),
                pnl=_fmt_pct(best.get("pnl_sum", 0)),
                win=_fmt_pct(best.get("win_rate", 0)),
                pf=pf_text,
                stop_rate=_fmt_pct(best.get("stop_loss_rate", 0)),
                decision=_decision(best),
            )
        )
    lines.extend([
        "",
        "## 说明",
        "",
        "- 本报告只给研究建议，不自动修改策略配置。",
        "- `禁用候选` 表示下一步应审二买确认形态；不是立即删除代码。",
        "",
    ])
    args.out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
