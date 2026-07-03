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
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS, run_one


DEFAULT_START = "2025-01-01"
DEFAULT_END = "2026-04-24"
TUNED = {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15}


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


def _run(db_path: Path, symbol: str, start: str, end: str, params: dict[str, Any]) -> dict[str, Any]:
    original = copy.deepcopy(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG.update(params)
        report = run_one(db_path, symbol, start, end, quiet=True)
        report["params"] = dict(params)
        return report
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def run_validation(db_path: Path, symbols: list[str], start: str, end: str) -> dict[str, Any]:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "tuned": TUNED,
        "symbols": {},
    }
    for symbol in symbols:
        payload["symbols"][symbol] = {
            "baseline": _run(db_path, symbol, start, end, {}),
            "tuned": _run(db_path, symbol, start, end, TUNED),
        }
    return payload


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    improved = 0
    dd_not_worse = 0
    lines = [
        "# 五品种移动止损样本外验证",
        "",
        f"- 区间：{payload['start']} ~ {payload['end']}",
        "- baseline：默认 `300 / 0.25`",
        f"- tuned：`{payload['tuned']['trailing_start_bp']} / {payload['tuned']['trailing_drawback_pct']}`",
        "",
        "| 品种 | baseline收益 | tuned收益 | 收益差 | baseline回撤 | tuned回撤 | 回撤差 | baseline交易 | tuned交易 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for symbol, reports in payload["symbols"].items():
        b = reports["baseline"]
        t = reports["tuned"]
        delta = float(t.get("total_return_pct", 0)) - float(b.get("total_return_pct", 0))
        dd_delta = float(t.get("max_drawdown_pct", 0)) - float(b.get("max_drawdown_pct", 0))
        improved += int(delta > 0)
        dd_not_worse += int(dd_delta <= 0)
        lines.append(
            "| {symbol} | {bret} | {tret} | {delta} | {bdd} | {tdd} | {dd_delta} | {bt} | {tt} |".format(
                symbol=symbol,
                bret=_fmt_pct(b.get("total_return_pct", 0)),
                tret=_fmt_pct(t.get("total_return_pct", 0)),
                delta=_fmt_pct(delta),
                bdd=_fmt_pct(b.get("max_drawdown_pct", 0)),
                tdd=_fmt_pct(t.get("max_drawdown_pct", 0)),
                dd_delta=_fmt_pct(dd_delta),
                bt=_fmt_num(b.get("total_trades", 0), 0),
                tt=_fmt_num(t.get("total_trades", 0), 0),
            )
        )
    lines.extend([
        "",
        "## 结论",
        "",
        f"- 收益改善品种数：{improved} / {len(payload['symbols'])}",
        f"- 回撤不恶化品种数：{dd_not_worse} / {len(payload['symbols'])}",
        "- 若收益改善少于 3 个品种或回撤普遍恶化，不建议设为全局默认。",
        "",
    ])
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate tight trailing stop on all symbols out of sample.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("trailing_oos_all_symbols_20250101_20260424.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("trailing_oos_all_symbols_20250101_20260424.md"))
    args = parser.parse_args()

    payload = run_validation(args.db_path, args.symbols, args.start, args.end)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
