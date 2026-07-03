from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS, run_one


FULL_START = "2022-01-01"
FULL_END = "2026-04-24"
OOS_START = "2025-01-01"
OOS_END = "2026-04-24"
TRAILING_OVERRIDES = {
    "RB888": {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15},
    "SC888": {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15},
}


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


def _period(db_path: Path, name: str, start: str, end: str, symbols: list[str]) -> dict[str, Any]:
    rows = {}
    for symbol in symbols:
        baseline = _run(db_path, symbol, start, end, {})
        params = {"trailing_overrides": {symbol: TRAILING_OVERRIDES[symbol]}} if symbol in TRAILING_OVERRIDES else {}
        tuned = _run(db_path, symbol, start, end, params)
        rows[symbol] = {"baseline": baseline, "override": tuned}
    return {"name": name, "start": start, "end": end, "symbols": rows}


def _weighted_combo(rows: dict[str, Any], key: str) -> dict[str, float]:
    n = len(rows) or 1
    return {
        "return_pct": sum(v[key].get("total_return_pct", 0) for v in rows.values()) / n,
        "max_drawdown_pct": sum(v[key].get("max_drawdown_pct", 0) for v in rows.values()) / n,
        "total_trades": sum(v[key].get("total_trades", 0) for v in rows.values()),
    }


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# 移动止损分品种候选研究",
        "",
        "- overrides：RB888 / SC888 使用 `150 / 0.15`，其他品种保持默认。",
        "- 口径：逐品种独立回测，组合行使用五品种简单平均收益/回撤与交易数求和。",
        "",
    ]
    for period in payload["periods"]:
        base_combo = _weighted_combo(period["symbols"], "baseline")
        tuned_combo = _weighted_combo(period["symbols"], "override")
        lines.extend([
            f"## {period['name']} ({period['start']} ~ {period['end']})",
            "",
            "| 品种 | 参数 | baseline收益 | override收益 | 收益差 | baseline回撤 | override回撤 | 回撤差 | baseline交易 | override交易 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for symbol, reports in period["symbols"].items():
            b = reports["baseline"]
            t = reports["override"]
            params = t.get("params") or {"default": True}
            lines.append(
                "| {symbol} | {params} | {bret} | {tret} | {delta} | {bdd} | {tdd} | {dd_delta} | {bt} | {tt} |".format(
                    symbol=symbol,
                    params=json.dumps(params, ensure_ascii=False),
                    bret=_fmt_pct(b.get("total_return_pct", 0)),
                    tret=_fmt_pct(t.get("total_return_pct", 0)),
                    delta=_fmt_pct(t.get("total_return_pct", 0) - b.get("total_return_pct", 0)),
                    bdd=_fmt_pct(b.get("max_drawdown_pct", 0)),
                    tdd=_fmt_pct(t.get("max_drawdown_pct", 0)),
                    dd_delta=_fmt_pct(t.get("max_drawdown_pct", 0) - b.get("max_drawdown_pct", 0)),
                    bt=_fmt_num(b.get("total_trades", 0), 0),
                    tt=_fmt_num(t.get("total_trades", 0), 0),
                )
            )
        lines.extend([
            f"| 组合均值 | - | {_fmt_pct(base_combo['return_pct'])} | {_fmt_pct(tuned_combo['return_pct'])} | "
            f"{_fmt_pct(tuned_combo['return_pct'] - base_combo['return_pct'])} | "
            f"{_fmt_pct(base_combo['max_drawdown_pct'])} | {_fmt_pct(tuned_combo['max_drawdown_pct'])} | "
            f"{_fmt_pct(tuned_combo['max_drawdown_pct'] - base_combo['max_drawdown_pct'])} | "
            f"{_fmt_num(base_combo['total_trades'], 0)} | {_fmt_num(tuned_combo['total_trades'], 0)} |",
            "",
        ])
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Research per-symbol trailing stop overrides.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("trailing_symbol_overrides_report.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("trailing_symbol_overrides_report.md"))
    args = parser.parse_args()

    payload = {
        "overrides": TRAILING_OVERRIDES,
        "periods": [
            _period(args.db_path, "full", FULL_START, FULL_END, args.symbols),
            _period(args.db_path, "out_sample", OOS_START, OOS_END, args.symbols),
        ],
    }
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
