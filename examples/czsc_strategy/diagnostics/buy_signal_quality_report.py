from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_MATRIX = Path(__file__).with_name("backtest_matrix_20220101_20260424.json")
DEFAULT_FUNNEL = Path(__file__).with_name("signal_funnel_summary_20220101_20260424.md")
DEFAULT_OUT = Path(__file__).with_name("buy_signal_quality_20220101_20260424.md")


def _fmt_pct(value: float | int | str | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return f"{float(value):.2f}%"


def _fmt_num(value: float | int | str | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def _parse_pair(text: str) -> tuple[int, int]:
    left, right = text.split("/")
    return int(left.replace(",", "").strip()), int(right.replace(",", "").strip())


def parse_funnel_summary(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        r"^\|\s*(?P<symbol>[A-Z0-9]+)\s*\|\s*(?P<bars>[\d,]+)\s*\|\s*"
        r"(?P<buy1>[\d,]+\s*/\s*[\d,]+)\s*\|\s*"
        r"(?P<buy2>[\d,]+\s*/\s*[\d,]+)\s*\|\s*"
        r"(?P<buy3>[\d,]+\s*/\s*[\d,]+)\s*\|"
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line.strip())
        if not m:
            continue
        symbol = m.group("symbol")
        buy1_pass, buy1_open = _parse_pair(m.group("buy1"))
        buy2_pass, buy2_open = _parse_pair(m.group("buy2"))
        buy3_pass, buy3_open = _parse_pair(m.group("buy3"))
        rows[symbol] = {
            "bars": int(m.group("bars").replace(",", "")),
            "buy1_pass": buy1_pass,
            "buy1_open": buy1_open,
            "buy2_pass": buy2_pass,
            "buy2_open": buy2_open,
            "buy3_pass": buy3_pass,
            "buy3_open": buy3_open,
        }
    return rows


def _find_sub_strategy(report: dict[str, Any], keyword: str) -> dict[str, Any]:
    for name, stats in report.get("sub_strategies", {}).items():
        if keyword in name:
            return stats
    return {}


def write_report(matrix: dict[str, Any], funnel: dict[str, dict[str, Any]], out: Path) -> None:
    lines = [
        "# 一买 / 二买质量漏斗报告",
        "",
        f"- 回测矩阵：`{DEFAULT_MATRIX.name}`",
        f"- 信号漏斗：`{DEFAULT_FUNNEL.name}`",
        "- 目标：确认一买、二买不再是全零信号，并用真实回测交易质量判断它们是“高质量低频”还是仍需继续放宽。",
        "",
        "## 漏斗通过数与开仓数",
        "",
        "| 品种 | 评估bar | 一买通过 | 一买开仓 | 一买开仓率 | 二买通过 | 二买开仓 | 二买开仓率 | 二买/一买开仓比 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for symbol in matrix.get("symbols", {}):
        row = funnel.get(symbol, {})
        buy1_pass = row.get("buy1_pass", 0)
        buy1_open = row.get("buy1_open", 0)
        buy2_pass = row.get("buy2_pass", 0)
        buy2_open = row.get("buy2_open", 0)
        lines.append(
            "| {symbol} | {bars} | {b1p} | {b1o} | {b1r} | {b2p} | {b2o} | {b2r} | {ratio} |".format(
                symbol=symbol,
                bars=_fmt_num(row.get("bars", 0), 0),
                b1p=_fmt_num(buy1_pass, 0),
                b1o=_fmt_num(buy1_open, 0),
                b1r=_fmt_pct((buy1_open / buy1_pass * 100) if buy1_pass else 0),
                b2p=_fmt_num(buy2_pass, 0),
                b2o=_fmt_num(buy2_open, 0),
                b2r=_fmt_pct((buy2_open / buy2_pass * 100) if buy2_pass else 0),
                ratio=_fmt_pct((buy2_open / buy1_open * 100) if buy1_open else 0),
            )
        )

    lines.extend(
        [
            "",
            "## 全样本交易质量",
            "",
            "| 品种 | 子策略 | 交易数 | 胜率 | 盈亏比 | 平均盈利 | 平均亏损 | 平均持仓bar |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for symbol, reports in matrix.get("symbols", {}).items():
        full = reports.get("full", {})
        for label in ("一买", "二买"):
            stats = _find_sub_strategy(full, label)
            lines.append(
                "| {symbol} | {label} | {trades} | {win_rate} | {pf} | {avg_profit} | {avg_loss} | {avg_bars} |".format(
                    symbol=symbol,
                    label=label,
                    trades=_fmt_num(stats.get("total_trades", 0), 0),
                    win_rate=_fmt_pct(float(stats.get("win_rate", 0)) * 100),
                    pf=_fmt_num(stats.get("profit_factor", 0)),
                    avg_profit=_fmt_pct(float(stats.get("avg_profit", 0)) * 100),
                    avg_loss=_fmt_pct(float(stats.get("avg_loss", 0)) * 100),
                    avg_bars=_fmt_num(stats.get("avg_bars_held", 0), 1),
                )
            )

    warnings: list[str] = []
    for symbol in matrix.get("symbols", {}):
        row = funnel.get(symbol, {})
        if row.get("buy1_open", 0) == 0:
            warnings.append(f"{symbol}: 一买开仓为 0")
        if row.get("buy2_open", 0) == 0:
            warnings.append(f"{symbol}: 二买开仓为 0")
        full = matrix["symbols"][symbol].get("full", {})
        buy2_stats = _find_sub_strategy(full, "二买")
        if buy2_stats and buy2_stats.get("total_trades", 0) == 0:
            warnings.append(f"{symbol}: 二买真实回测交易为 0")

    lines.extend(["", "## 结论", ""])
    if warnings:
        lines.append("- 告警：" + "；".join(warnings))
    else:
        lines.append("- 一买、二买在五个主连上均已恢复开仓，当前首要问题从“信号全零”转为“交易质量与频率是否符合预期”。")
    lines.append("- 二买显著低频是正常现象还是过严，需要结合盈亏比、胜率和样本外结果继续观察；本报告只固化当前事实。")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Write buy1/buy2 signal quality report from matrix and funnel outputs.")
    parser.add_argument("--matrix-json", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--funnel-summary", type=Path, default=DEFAULT_FUNNEL)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.matrix_json.exists():
        raise SystemExit(f"matrix JSON not found: {args.matrix_json}")

    matrix = json.loads(args.matrix_json.read_text(encoding="utf-8"))
    funnel = parse_funnel_summary(args.funnel_summary)
    write_report(matrix, funnel, args.out_md)
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
