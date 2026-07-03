from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.config import SQLITE_DB_PATH
from diagnostics.backtest_matrix_report import DEFAULT_END, DEFAULT_START, DEFAULT_SYMBOLS, run_one


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def _fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def _dt_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _year(value: Any) -> str:
    if isinstance(value, datetime):
        return str(value.year)
    return str(value)[:4]


def _bucket(bars: int) -> str:
    if bars <= 20:
        return "00-20"
    if bars <= 60:
        return "21-60"
    if bars <= 120:
        return "061-120"
    if bars <= 300:
        return "121-300"
    return "300+"


def _summarize(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    if not pairs:
        return {"trades": 0, "pnl_sum": 0.0, "win_rate": 0.0, "avg_pnl": 0.0, "profit_factor": 0.0}
    pnls = [float(p["pnl_pct"]) for p in pairs]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    profit = sum(wins)
    loss = abs(sum(losses))
    return {
        "trades": len(pairs),
        "pnl_sum": sum(pnls),
        "win_rate": len(wins) / len(pnls),
        "avg_pnl": sum(pnls) / len(pnls),
        "profit_factor": profit / loss if loss else float("inf"),
        "avg_bars": sum(int(p.get("bars_held", 0)) for p in pairs) / len(pairs),
    }


def collect_trades(db_path: Path, symbols: list[str], start: str, end: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "symbols": {},
        "trades": [],
    }
    for symbol in symbols:
        # run_one returns report only; rerun through it first for symbol resolution, then keep engine quiet by
        # reusing its imported BacktestEngine path would duplicate code. The private stdout capture keeps this
        # diagnostic readable when called from CI.
        from diagnostics.backtest_matrix_report import _dominant_symbol
        from chan_strategy.backtest_engine import BacktestEngine

        table_name = f"{symbol.lower()}_1M_raw"
        data_symbol = _dominant_symbol(db_path, table_name, start, end)
        engine = BacktestEngine(
            symbol=data_symbol,
            db_path=str(db_path),
            table_name=table_name,
            start_date=start,
            end_date=end,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            report = engine.run()
        symbol_trades = []
        if "error" not in report:
            for pos in engine.strategy.positions:
                for pair in pos.pairs:
                    row = dict(pair)
                    row["symbol"] = symbol
                    row["strategy"] = pos.name
                    symbol_trades.append(row)
                    result["trades"].append(row)
        result["symbols"][symbol] = {
            "report": report,
            "trade_summary": _summarize(symbol_trades),
        }
    return result


def build_attribution(data: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, dict[str, list[dict[str, Any]]]] = {
        "by_symbol": defaultdict(list),
        "by_strategy": defaultdict(list),
        "by_year": defaultdict(list),
        "by_duration": defaultdict(list),
        "by_reason": defaultdict(list),
    }
    for trade in data["trades"]:
        groups["by_symbol"][trade["symbol"]].append(trade)
        groups["by_strategy"][trade["strategy"]].append(trade)
        groups["by_year"][_year(trade["open_dt"])].append(trade)
        groups["by_duration"][_bucket(int(trade.get("bars_held", 0)))].append(trade)
        groups["by_reason"][str(trade.get("reason_code") or trade.get("reason") or "unknown")].append(trade)

    out = {}
    for group_name, rows in groups.items():
        out[group_name] = {key: _summarize(value) for key, value in sorted(rows.items())}
    out["worst_trades"] = sorted(data["trades"], key=lambda x: float(x["pnl_pct"]))[:20]
    return out


def _summary_row(name: str, stats: dict[str, Any]) -> str:
    pf = stats.get("profit_factor")
    pf_text = "inf" if pf == float("inf") else _fmt_num(pf)
    return (
        f"| {name} | {_fmt_num(stats.get('trades'), 0)} | {_fmt_pct(stats.get('pnl_sum'))} | "
        f"{_fmt_pct(stats.get('win_rate'))} | {_fmt_pct(stats.get('avg_pnl'))} | {pf_text} | "
        f"{_fmt_num(stats.get('avg_bars'))} |"
    )


def write_markdown(data: dict[str, Any], attr: dict[str, Any], path: Path) -> None:
    lines = [
        "# 收益归因报告",
        "",
        f"- 生成时间：{data['generated_at']}",
        f"- 区间：{data['start']} ~ {data['end']}",
        f"- 品种：{' / '.join(data['symbols'].keys())}",
        "- 说明：收益为未按资金权重加权的单笔 `pnl_pct` 汇总，用于定位亏损来源；资金曲线仍以回测矩阵为准。",
        "",
    ]
    for section, title in [
        ("by_symbol", "按品种"),
        ("by_strategy", "按子策略"),
        ("by_year", "按年份"),
        ("by_duration", "按持仓时长"),
        ("by_reason", "按出场原因"),
    ]:
        lines.extend([
            f"## {title}",
            "",
            "| 分组 | 交易数 | 累计收益 | 胜率 | 平均单笔 | 盈亏比 | 平均持仓bar |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for name, stats in attr[section].items():
            lines.append(_summary_row(name, stats))
        lines.append("")

    lines.extend([
        "## 最大亏损交易 Top20",
        "",
        "| 品种 | 子策略 | 开仓时间 | 平仓时间 | 开仓价 | 平仓价 | 盈亏 | 持仓bar | 原因 |",
        "|---|---|---|---|---:|---:|---:|---:|---|",
    ])
    for trade in attr["worst_trades"]:
        lines.append(
            "| {symbol} | {strategy} | {open_dt} | {close_dt} | {open_price} | {close_price} | {pnl} | {bars} | {reason} |".format(
                symbol=trade["symbol"],
                strategy=trade["strategy"],
                open_dt=_dt_text(trade["open_dt"]),
                close_dt=_dt_text(trade["close_dt"]),
                open_price=_fmt_num(trade.get("open_price")),
                close_price=_fmt_num(trade.get("close_price")),
                pnl=_fmt_pct(trade.get("pnl_pct")),
                bars=_fmt_num(trade.get("bars_held"), 0),
                reason=trade.get("reason", ""),
            )
        )
    lines.extend([
        "",
        "## 结论口径",
        "",
        "- 若亏损集中在少数年份或少数出场原因，优先审那一段行情和风控触发。",
        "- 若亏损集中在某个子策略，先做信号漏斗和入场形态复核，再考虑参数。",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Write PnL attribution report from real backtests.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("pnl_attribution_20220101_20260424.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("pnl_attribution_20220101_20260424.md"))
    args = parser.parse_args()

    data = collect_trades(args.db_path, args.symbols, args.start, args.end)
    attr = build_attribution(data)
    payload = {"data": data, "attribution": attr}
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_markdown(data, attr, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
