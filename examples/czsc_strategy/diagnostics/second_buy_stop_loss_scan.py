from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG
from diagnostics.backtest_matrix_report import DEFAULT_END, DEFAULT_START, DEFAULT_SYMBOLS, _dominant_symbol


STOP_VALUES = [200, 250, 300, 350, 400]


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def _fmt_report_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def _summarize_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    if not pairs:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "pnl_sum": 0.0,
            "avg_pnl": 0.0,
            "profit_factor": 0.0,
            "stop_loss_rate": 0.0,
            "max_loss_pct": 0.0,
        }
    pnls = [float(p["pnl_pct"]) for p in pairs]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    loss_sum = abs(sum(losses))
    stop_count = sum(1 for p in pairs if p.get("reason_code") == "stop_loss")
    return {
        "total_trades": len(pairs),
        "win_rate": len(wins) / len(pairs),
        "pnl_sum": sum(pnls),
        "avg_pnl": sum(pnls) / len(pnls),
        "profit_factor": sum(wins) / loss_sum if loss_sum else float("inf"),
        "stop_loss_count": stop_count,
        "stop_loss_rate": stop_count / len(pairs),
        "max_loss_pct": min(pnls),
        "avg_bars_held": sum(int(p.get("bars_held", 0)) for p in pairs) / len(pairs),
    }


def _run(db_path: Path, symbol: str, start: str, end: str, stop_loss_2buy: int) -> dict[str, Any]:
    original = copy.deepcopy(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG.update({"stop_loss_2buy": stop_loss_2buy})
        table_name = f"{symbol.lower()}_1M_raw"
        data_symbol = _dominant_symbol(db_path, table_name, start, end)
        engine = BacktestEngine(symbol=data_symbol, db_path=str(db_path), table_name=table_name, start_date=start, end_date=end)
        with contextlib.redirect_stdout(io.StringIO()):
            report = engine.run()
        if "error" in report:
            return {"error": report["error"], "stop_loss_2buy": stop_loss_2buy}
        buy2 = engine.strategy.positions[1]
        summary = _summarize_pairs(list(buy2.pairs))
        summary["stop_loss_2buy"] = stop_loss_2buy
        summary["symbol_return_pct"] = report.get("total_return_pct", 0)
        summary["symbol_max_drawdown_pct"] = report.get("max_drawdown_pct", 0)
        return summary
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def run_scan(db_path: Path, symbols: list[str], start: str, end: str) -> dict[str, Any]:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "stop_values": STOP_VALUES,
        "symbols": {},
    }
    for symbol in symbols:
        payload["symbols"][symbol] = [_run(db_path, symbol, start, end, stop) for stop in STOP_VALUES]
    return payload


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# 二买止损扫描",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 区间：{payload['start']} ~ {payload['end']}",
        f"- 品种：{' / '.join(payload['symbols'].keys())}",
        f"- stop_loss_2buy：{' / '.join(map(str, payload['stop_values']))}",
        "",
        "| 品种 | stop_loss_2buy | 二买交易 | 二买累计收益 | 二买胜率 | 二买盈亏比 | 止损率 | 最大单笔亏损 | 全策略收益 | 全策略回撤 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for symbol, rows in payload["symbols"].items():
        for row in rows:
            if "error" in row:
                lines.append(f"| {symbol} | {row['stop_loss_2buy']} | - | - | - | - | - | - | - | error: {row['error']} |")
                continue
            pf = row.get("profit_factor")
            pf_text = "inf" if pf == float("inf") or pf == "inf" else _fmt_num(pf)
            lines.append(
                "| {symbol} | {stop} | {trades} | {pnl} | {win} | {pf} | {stop_rate} | {max_loss} | {ret} | {dd} |".format(
                    symbol=symbol,
                    stop=row["stop_loss_2buy"],
                    trades=_fmt_num(row.get("total_trades"), 0),
                    pnl=_fmt_pct(row.get("pnl_sum", 0)),
                    win=_fmt_pct(row.get("win_rate", 0)),
                    pf=pf_text,
                    stop_rate=_fmt_pct(row.get("stop_loss_rate", 0)),
                    max_loss=_fmt_pct(row.get("max_loss_pct", 0)),
                    ret=_fmt_report_pct(row.get("symbol_return_pct", 0)),
                    dd=_fmt_report_pct(row.get("symbol_max_drawdown_pct", 0)),
                )
            )
    lines.extend(
        [
            "",
            "## 判读",
            "",
            "- 若放宽止损只扩大最大亏损且不改善盈亏比，问题更可能在二买确认位置。",
            "- 若某个止损档同时改善二买盈亏比与全策略收益，可进入样本外复核。",
            "",
        ]
    )
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan stop_loss_2buy values and report second-buy quality.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("second_buy_stop_loss_scan_20220101_20260424.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("second_buy_stop_loss_scan_20220101_20260424.md"))
    args = parser.parse_args()

    payload = run_scan(args.db_path, args.symbols, args.start, args.end)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
