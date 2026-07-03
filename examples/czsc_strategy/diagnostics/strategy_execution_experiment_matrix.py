from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from datetime import datetime, timezone
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

SECOND_BUY_FILTERS = {
    "max_2buy_entry_vs_anchor_pct": 0.03,
    "enable_2buy_symbols": ["AP888", "A888", "ZN888"],
}
TRAILING_OVERRIDES = {
    "trailing_overrides": {
        "RB888": {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15},
        "SC888": {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15},
    }
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return value


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


def _scenario_params() -> dict[str, dict[str, Any]]:
    combined = copy.deepcopy(SECOND_BUY_FILTERS)
    combined.update(copy.deepcopy(TRAILING_OVERRIDES))
    return {
        "baseline": {},
        "second_buy_filters": copy.deepcopy(SECOND_BUY_FILTERS),
        "trailing_overrides": copy.deepcopy(TRAILING_OVERRIDES),
        "combined": combined,
    }


def _run_with_params(db_path: Path, symbol: str, start: str, end: str, params: dict[str, Any]) -> dict[str, Any]:
    original = copy.deepcopy(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG.update(copy.deepcopy(params))
        report = run_one(db_path, symbol, start, end, quiet=True)
        report["scenario_params"] = copy.deepcopy(params)
        return report
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def _combo(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in rows.values() if "error" not in r]
    n = len(valid) or 1
    return {
        "return_pct": sum(float(r.get("total_return_pct", 0)) for r in valid) / n,
        "max_drawdown_pct": sum(float(r.get("max_drawdown_pct", 0)) for r in valid) / n,
        "total_trades": sum(int(r.get("total_trades", 0)) for r in valid),
        "win_rate": sum(float(r.get("win_rate", 0)) for r in valid) / n,
        "max_gross_exposure": max((float(r.get("max_gross_exposure", 0)) for r in valid), default=0),
        "errors": len(rows) - len(valid),
    }


def build_matrix(db_path: Path, symbols: list[str]) -> dict[str, Any]:
    periods = {
        "full": (FULL_START, FULL_END),
        "out_sample": (OOS_START, OOS_END),
    }
    scenarios = _scenario_params()
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "periods": {},
        "scenarios": scenarios,
    }
    for period_name, (start, end) in periods.items():
        payload["periods"][period_name] = {"start": start, "end": end, "scenarios": {}}
        for scenario_name, params in scenarios.items():
            symbol_rows: dict[str, Any] = {}
            for symbol in symbols:
                try:
                    symbol_rows[symbol] = _run_with_params(db_path, symbol, start, end, params)
                except Exception as exc:  # pragma: no cover - diagnostic failure path
                    symbol_rows[symbol] = {"requested_symbol": symbol, "error": str(exc)}
            payload["periods"][period_name]["scenarios"][scenario_name] = {
                "symbols": symbol_rows,
                "combo": _combo(symbol_rows),
            }
    return payload


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Strategy Execution Experiment Matrix",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- db_path: `{payload['db_path']}`",
        "- scenarios: baseline / second_buy_filters / trailing_overrides / combined",
        "",
    ]
    for period_name, period in payload["periods"].items():
        lines.extend([
            f"## {period_name} ({period['start']} ~ {period['end']})",
            "",
            "| scenario | combo_return | combo_drawdown | combo_trades | combo_win_rate | max_gross_exposure | errors |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for scenario_name, scenario in period["scenarios"].items():
            combo = scenario["combo"]
            lines.append(
                f"| {scenario_name} | {_fmt_pct(combo['return_pct'])} | {_fmt_pct(combo['max_drawdown_pct'])} | "
                f"{_fmt_num(combo['total_trades'], 0)} | {_fmt_pct(combo['win_rate'] * 100)} | "
                f"{_fmt_pct(combo['max_gross_exposure'] * 100)} | {_fmt_num(combo['errors'], 0)} |"
            )
        lines.extend([
            "",
            "| scenario | symbol | return | drawdown | trades | win_rate | sharpe | gross |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ])
        for scenario_name, scenario in period["scenarios"].items():
            for symbol, report in scenario["symbols"].items():
                if "error" in report:
                    lines.append(f"| {scenario_name} | {symbol} | ERROR | - | - | - | - | {report['error']} |")
                    continue
                lines.append(
                    f"| {scenario_name} | {symbol} | {_fmt_pct(report.get('total_return_pct', 0))} | "
                    f"{_fmt_pct(report.get('max_drawdown_pct', 0))} | {_fmt_num(report.get('total_trades', 0), 0)} | "
                    f"{_fmt_pct(float(report.get('win_rate', 0)) * 100)} | {_fmt_num(report.get('sharpe_ratio', 0))} | "
                    f"{_fmt_pct(float(report.get('max_gross_exposure', 0)) * 100)} |"
                )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run true execution-path strategy experiments.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("strategy_execution_experiment_matrix.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("strategy_execution_experiment_matrix.md"))
    args = parser.parse_args()

    if not args.db_path.exists():
        raise SystemExit(f"DB not found: {args.db_path}")

    payload = build_matrix(args.db_path, args.symbols)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
