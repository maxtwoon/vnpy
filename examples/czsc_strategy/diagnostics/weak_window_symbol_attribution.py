from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent

from portfolio_goal_evaluator import _json_safe, _scenario_params, _run_symbol  # noqa: E402
from chan_strategy.config import SQLITE_DB_PATH  # noqa: E402
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS  # noqa: E402


WEAK_WINDOWS = {
    "2023H1": ("2023-01-01", "2023-06-30"),
    "2022H1": ("2022-01-01", "2022-06-30"),
    "2026YTD": ("2026-01-01", "2026-04-24"),
}


def _sub_strategy_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, metrics in report.get("sub_strategies", {}).items():
        rows.append({
            "strategy": name,
            "trades": metrics.get("total_trades", 0),
            "win_rate": metrics.get("win_rate", 0.0),
            "profit_factor": metrics.get("profit_factor", 0.0),
            "avg_profit": metrics.get("avg_profit", 0.0),
            "avg_loss": metrics.get("avg_loss", 0.0),
        })
    return rows


def build_report(db_path: Path, symbols: list[str], scenario: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"scenario": scenario, "windows": {}}
    for window, (start, end) in WEAK_WINDOWS.items():
        symbol_rows = {}
        for symbol in symbols:
            row = _run_symbol(db_path, symbol, start, end, scenario)
            report = row["report"]
            symbol_rows[symbol] = {
                "return_pct": report.get("total_return_pct", 0.0),
                "max_drawdown_pct": report.get("max_drawdown_pct", 0.0),
                "sharpe": report.get("sharpe_ratio", 0.0),
                "trades": report.get("total_trades", 0),
                "win_rate": report.get("win_rate", 0.0),
                "profit_factor": report.get("profit_factor", 0.0),
                "sub_strategies": _sub_strategy_rows(report),
            }
        payload["windows"][window] = {
            "start": start,
            "end": end,
            "symbols": symbol_rows,
        }
    return payload


def _fmt_pct(value: float) -> str:
    return f"{value:.2f}%"


def _fmt_num(value: Any) -> str:
    if isinstance(value, str):
        return value
    return f"{float(value):.2f}"


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# Weak Window Symbol Attribution",
        "",
        f"- scenario: `{payload['scenario']}`",
        "- windows: 2023H1 / 2022H1 / 2026YTD",
        "",
    ]
    for window, data in payload["windows"].items():
        lines.extend([
            f"## {window} ({data['start']} ~ {data['end']})",
            "",
            "| symbol | return | drawdown | sharpe | trades | win_rate | PF |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for symbol, row in sorted(data["symbols"].items(), key=lambda kv: float(kv[1]["return_pct"])):
            lines.append(
                f"| {symbol} | {_fmt_pct(float(row['return_pct']))} | "
                f"{_fmt_pct(float(row['max_drawdown_pct']))} | {_fmt_num(row['sharpe'])} | "
                f"{row['trades']} | {_fmt_pct(float(row['win_rate']) * 100)} | {_fmt_num(row['profit_factor'])} |"
            )
        lines.extend([
            "",
            "### Sub-Strategies",
            "",
            "| symbol | strategy | trades | win_rate | PF | avg_profit | avg_loss |",
            "|---|---|---:|---:|---:|---:|---:|",
        ])
        for symbol, row in data["symbols"].items():
            for sub in row["sub_strategies"]:
                lines.append(
                    f"| {symbol} | {sub['strategy']} | {sub['trades']} | "
                    f"{_fmt_pct(float(sub['win_rate']) * 100)} | {_fmt_num(sub['profit_factor'])} | "
                    f"{_fmt_pct(float(sub['avg_profit']) * 100)} | {_fmt_pct(float(sub['avg_loss']) * 100)} |"
                )
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Attribute weak walk-forward windows by symbol and sub-strategy.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--scenario", default="expanded_short_sc_0847")
    parser.add_argument("--out-json", type=Path, default=HERE / "weak_window_symbol_attribution.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "weak_window_symbol_attribution.md")
    args = parser.parse_args()

    # Validate scenario early for a friendlier failure mode.
    _scenario_params(args.scenario, args.symbols[0])
    payload = build_report(args.db_path, args.symbols, args.scenario)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
