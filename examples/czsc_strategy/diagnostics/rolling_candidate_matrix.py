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
from diagnostics.strategy_execution_experiment_matrix import SECOND_BUY_FILTERS, TRAILING_OVERRIDES


WINDOWS = {
    "2022H1": ("2022-01-01", "2022-06-30"),
    "2022H2": ("2022-07-01", "2022-12-31"),
    "2023H1": ("2023-01-01", "2023-06-30"),
    "2023H2": ("2023-07-01", "2023-12-31"),
    "2024H1": ("2024-01-01", "2024-06-30"),
    "2024H2": ("2024-07-01", "2024-12-31"),
    "2025H1": ("2025-01-01", "2025-06-30"),
    "2025H2": ("2025-07-01", "2025-12-31"),
    "2026YTD": ("2026-01-01", "2026-04-24"),
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


def _combined_params() -> dict[str, Any]:
    params = copy.deepcopy(SECOND_BUY_FILTERS)
    params.update(copy.deepcopy(TRAILING_OVERRIDES))
    return params


def _expanded_params(symbol: str) -> dict[str, Any]:
    params = _combined_params()
    if symbol in {"AP888", "A888"}:
        params["max_2buy_entry_vs_anchor_pct"] = None
    return params


def _scenario_params(scenario: str, symbol: str) -> dict[str, Any]:
    if scenario == "baseline":
        return {}
    if scenario == "combined":
        return _combined_params()
    if scenario == "expanded":
        return _expanded_params(symbol)
    raise ValueError(f"unsupported scenario: {scenario}")


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
        "errors": len(rows) - len(valid),
    }


def build_matrix(db_path: Path, symbols: list[str]) -> dict[str, Any]:
    scenarios = ["baseline", "combined", "expanded"]
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "scenarios": {
            "baseline": {},
            "combined": _combined_params(),
            "expanded": {
                "description": "combined plus AP888/A888 exemption from max_2buy_entry_vs_anchor_pct",
                "base": _combined_params(),
                "exempt_2buy_chase_symbols": ["AP888", "A888"],
            },
        },
        "windows": {},
    }
    for window_name, (start, end) in WINDOWS.items():
        payload["windows"][window_name] = {"start": start, "end": end, "scenarios": {}}
        for scenario in scenarios:
            rows = {}
            for symbol in symbols:
                try:
                    rows[symbol] = _run(db_path, symbol, start, end, _scenario_params(scenario, symbol))
                except Exception as exc:  # pragma: no cover - diagnostic failure path
                    rows[symbol] = {"requested_symbol": symbol, "error": str(exc)}
            payload["windows"][window_name]["scenarios"][scenario] = {"symbols": rows, "combo": _combo(rows)}
    return payload


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# Rolling Candidate Matrix",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        "- windows: half-year windows plus 2026YTD.",
        "- expanded: combined plus AP888/A888 exemption from the 3% second-buy chase filter.",
        "",
        "| window | scenario | return | drawdown | trades | win_rate | return_delta | drawdown_delta | trade_delta | errors |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for window_name, window in payload["windows"].items():
        base = window["scenarios"]["baseline"]["combo"]
        for scenario, row in window["scenarios"].items():
            combo = row["combo"]
            lines.append(
                f"| {window_name} | {scenario} | {_fmt_pct(combo['return_pct'])} | {_fmt_pct(combo['max_drawdown_pct'])} | "
                f"{_fmt_num(combo['total_trades'], 0)} | {_fmt_pct(combo['win_rate'] * 100)} | "
                f"{_fmt_pct(combo['return_pct'] - base['return_pct'])} | "
                f"{_fmt_pct(combo['max_drawdown_pct'] - base['max_drawdown_pct'])} | "
                f"{_fmt_num(combo['total_trades'] - base['total_trades'], 0)} | {_fmt_num(combo['errors'], 0)} |"
            )
    lines.extend(["", "## Symbol Detail", ""])
    for window_name, window in payload["windows"].items():
        lines.extend([
            f"### {window_name} ({window['start']} ~ {window['end']})",
            "",
            "| scenario | symbol | return | drawdown | trades | win_rate |",
            "|---|---|---:|---:|---:|---:|",
        ])
        for scenario, row in window["scenarios"].items():
            for symbol, report in row["symbols"].items():
                if "error" in report:
                    lines.append(f"| {scenario} | {symbol} | ERROR | - | - | {report['error']} |")
                    continue
                lines.append(
                    f"| {scenario} | {symbol} | {_fmt_pct(report.get('total_return_pct', 0))} | "
                    f"{_fmt_pct(report.get('max_drawdown_pct', 0))} | {_fmt_num(report.get('total_trades', 0), 0)} | "
                    f"{_fmt_pct(float(report.get('win_rate', 0)) * 100)} |"
                )
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run rolling-window baseline/combined/expanded candidate matrix.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("rolling_candidate_matrix.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("rolling_candidate_matrix.md"))
    args = parser.parse_args()

    payload = build_matrix(args.db_path, args.symbols)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
