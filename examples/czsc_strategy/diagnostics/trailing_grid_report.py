from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG
from diagnostics.backtest_matrix_report import run_one


DEFAULT_SYMBOLS = ["RB888", "SC888"]
DEFAULT_START = "2024-01-01"
DEFAULT_END = "2024-12-31"
START_VALUES = [150, 200, 250, 300]
DRAWBACK_VALUES = [0.15, 0.20, 0.25, 0.30]


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def _run_with_params(db_path: Path, symbol: str, start: str, end: str, trailing_start: int, drawback: float) -> dict[str, Any]:
    original = copy.deepcopy(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG.update({"trailing_start_bp": trailing_start, "trailing_drawback_pct": drawback})
        report = run_one(db_path, symbol, start, end, quiet=True)
        report["trailing_start_bp"] = trailing_start
        report["trailing_drawback_pct"] = drawback
        return report
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def run_grid(db_path: Path, symbols: list[str], start: str, end: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "symbols": {},
    }
    for symbol in symbols:
        rows = []
        for trailing_start in START_VALUES:
            for drawback in DRAWBACK_VALUES:
                rows.append(_run_with_params(db_path, symbol, start, end, trailing_start, drawback))
        payload["symbols"][symbol] = rows
    return payload


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# 移动止损二层细网格",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 区间：{payload['start']} ~ {payload['end']}",
        f"- 品种：{' / '.join(payload['symbols'].keys())}",
        f"- trailing_start_bp：{' / '.join(map(str, START_VALUES))}",
        f"- trailing_drawback_pct：{' / '.join(map(str, DRAWBACK_VALUES))}",
        "",
    ]
    for symbol, rows in payload["symbols"].items():
        best = max(rows, key=lambda r: r.get("total_return_pct", -999))
        lines.extend([
            f"## {symbol}",
            "",
            f"- 收益最优：start={best['trailing_start_bp']}，drawback={best['trailing_drawback_pct']}，收益={best.get('total_return_pct', 0):.2f}%，回撤={best.get('max_drawdown_pct', 0):.2f}%",
            "",
            "| start_bp | drawback | 交易数 | 收益率 | 最大回撤 | 胜率 | 盈亏比 |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for row in sorted(rows, key=lambda r: (r["trailing_start_bp"], r["trailing_drawback_pct"])):
            pf = row.get("profit_factor")
            pf_text = "inf" if pf == float("inf") or pf == "inf" else _fmt_num(pf)
            lines.append(
                "| {start} | {drawback:.2f} | {trades} | {ret} | {dd} | {win} | {pf} |".format(
                    start=row["trailing_start_bp"],
                    drawback=row["trailing_drawback_pct"],
                    trades=_fmt_num(row.get("total_trades"), 0),
                    ret=_fmt_pct(row.get("total_return_pct", 0)),
                    dd=_fmt_pct(row.get("max_drawdown_pct", 0)),
                    win=_fmt_pct(float(row.get("win_rate", 0)) * 100),
                    pf=pf_text,
                )
            )
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run second-level trailing stop grid.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("trailing_grid_20240101_20241231.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("trailing_grid_20240101_20241231.md"))
    args = parser.parse_args()

    payload = run_grid(args.db_path, args.symbols, args.start, args.end)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
