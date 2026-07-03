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
from diagnostics.strategy_execution_experiment_matrix import (
    FULL_END,
    FULL_START,
    OOS_END,
    OOS_START,
    SECOND_BUY_FILTERS,
    TRAILING_OVERRIDES,
)


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


def _combined_params() -> dict[str, Any]:
    params = copy.deepcopy(SECOND_BUY_FILTERS)
    params.update(copy.deepcopy(TRAILING_OVERRIDES))
    return params


def _params_for_symbol(base: dict[str, Any], symbol: str, exempt_symbols: set[str]) -> dict[str, Any]:
    params = copy.deepcopy(base)
    if symbol in exempt_symbols:
        params["max_2buy_entry_vs_anchor_pct"] = None
    return params


def _run(db_path: Path, symbol: str, start: str, end: str, params: dict[str, Any]) -> dict[str, Any]:
    original = copy.deepcopy(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG.update(copy.deepcopy(params))
        return run_one(db_path, symbol, start, end, quiet=True)
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def _combo(rows: dict[str, Any]) -> dict[str, Any]:
    valid = [r for r in rows.values() if "error" not in r]
    n = len(valid) or 1
    return {
        "return_pct": sum(float(r.get("total_return_pct", 0)) for r in valid) / n,
        "max_drawdown_pct": sum(float(r.get("max_drawdown_pct", 0)) for r in valid) / n,
        "total_trades": sum(int(r.get("total_trades", 0)) for r in valid),
        "win_rate": sum(float(r.get("win_rate", 0)) for r in valid) / n,
    }


def build_matrix(db_path: Path, symbols: list[str]) -> dict[str, Any]:
    periods = {
        "full": (FULL_START, FULL_END),
        "out_sample": (OOS_START, OOS_END),
    }
    scenarios = {
        "combined": set(),
        "exempt_AP888": {"AP888"},
        "exempt_A888": {"A888"},
        "exempt_AP888_A888": {"AP888", "A888"},
    }
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "periods": {},
        "base_params": _combined_params(),
    }
    for period_name, (start, end) in periods.items():
        payload["periods"][period_name] = {"start": start, "end": end, "scenarios": {}}
        for scenario, exempt_symbols in scenarios.items():
            rows = {}
            for symbol in symbols:
                try:
                    rows[symbol] = _run(db_path, symbol, start, end, _params_for_symbol(_combined_params(), symbol, exempt_symbols))
                except Exception as exc:  # pragma: no cover - diagnostic failure path
                    rows[symbol] = {"requested_symbol": symbol, "error": str(exc)}
            payload["periods"][period_name]["scenarios"][scenario] = {
                "exempt_symbols": sorted(exempt_symbols),
                "symbols": rows,
                "combo": _combo(rows),
            }
    return payload


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# Second-Buy Exemption Matrix",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        "- baseline here means current `combined` candidate.",
        "- exemption means disabling only `max_2buy_entry_vs_anchor_pct` for that symbol; trailing overrides stay unchanged.",
        "",
    ]
    for period_name, period in payload["periods"].items():
        base = period["scenarios"]["combined"]["combo"]
        lines.extend([
            f"## {period_name} ({period['start']} ~ {period['end']})",
            "",
            "| scenario | return | drawdown | trades | win_rate | return_delta | drawdown_delta | trade_delta |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for scenario, item in period["scenarios"].items():
            combo = item["combo"]
            lines.append(
                f"| {scenario} | {_fmt_pct(combo['return_pct'])} | {_fmt_pct(combo['max_drawdown_pct'])} | "
                f"{_fmt_num(combo['total_trades'], 0)} | {_fmt_pct(combo['win_rate'] * 100)} | "
                f"{_fmt_pct(combo['return_pct'] - base['return_pct'])} | "
                f"{_fmt_pct(combo['max_drawdown_pct'] - base['max_drawdown_pct'])} | "
                f"{_fmt_num(combo['total_trades'] - base['total_trades'], 0)} |"
            )
        lines.extend([
            "",
            "| scenario | symbol | return | drawdown | trades | win_rate |",
            "|---|---|---:|---:|---:|---:|",
        ])
        for scenario, item in period["scenarios"].items():
            for symbol, report in item["symbols"].items():
                if "error" in report:
                    lines.append(f"| {scenario} | {symbol} | ERROR | - | - | {report['error']} |")
                else:
                    lines.append(
                        f"| {scenario} | {symbol} | {_fmt_pct(report.get('total_return_pct', 0))} | "
                        f"{_fmt_pct(report.get('max_drawdown_pct', 0))} | {_fmt_num(report.get('total_trades', 0), 0)} | "
                        f"{_fmt_pct(float(report.get('win_rate', 0)) * 100)} |"
                    )
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test AP888/A888 exemption from second-buy chase filter.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("second_buy_exemption_matrix.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("second_buy_exemption_matrix.md"))
    args = parser.parse_args()

    payload = build_matrix(args.db_path, args.symbols)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
