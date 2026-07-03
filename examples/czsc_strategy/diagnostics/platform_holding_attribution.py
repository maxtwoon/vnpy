from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from diagnostics.backtest_matrix_report import _dominant_symbol  # noqa: E402
from symbol_set_stability_scan import SYMBOL_SETS  # noqa: E402


BASE_CONFIG = {
    "block_1buy_daily_down": True,
    "max_2buy_entry_vs_anchor_pct": 0.03,
    "enable_2buy_symbols": ["AP888", "A888", "ZN888"],
    "trailing_overrides": {
        "RB888": {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15},
        "SC888": {"trailing_start_bp": 150, "trailing_drawback_pct": 0.15},
    },
    "enable_short": True,
    "enable_short_symbols": ["SC888"],
    "pos_1sell": 0.075,
    "pos_3sell": 0.225,
}


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


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"trades": 0, "pnl_sum": 0.0, "win_rate": 0.0, "avg_bars": 0.0, "profit_factor": 0.0}
    pnls = [float(row["pnl_pct"]) for row in rows]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    loss_sum = abs(sum(losses))
    return {
        "trades": len(rows),
        "pnl_sum": sum(pnls),
        "win_rate": len(wins) / len(rows),
        "avg_pnl": sum(pnls) / len(rows),
        "avg_bars": sum(int(row.get("bars_held", 0)) for row in rows) / len(rows),
        "profit_factor": sum(wins) / loss_sum if loss_sum else float("inf"),
    }


def _run_symbol(db_path: Path, symbol: str, start: str, end: str) -> dict[str, Any]:
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
    trades = []
    for pos in engine.strategy.positions:
        for pair in pos.pairs:
            row = dict(pair)
            row["symbol"] = symbol
            row["strategy"] = pos.name
            trades.append(row)
    return {"report": report, "trades": trades}


def build_report(db_path: Path, set_name: str, start: str, end: str, config: dict[str, Any]) -> dict[str, Any]:
    original = copy.deepcopy(STRATEGY_CONFIG)
    symbols = SYMBOL_SETS[set_name]
    try:
        STRATEGY_CONFIG.update(copy.deepcopy(config))
        all_trades = []
        symbol_reports = {}
        for symbol in symbols:
            row = _run_symbol(db_path, symbol, start, end)
            symbol_reports[symbol] = row["report"]
            all_trades.extend(row["trades"])
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)

    groups = {
        "by_symbol": defaultdict(list),
        "by_strategy": defaultdict(list),
        "by_reason": defaultdict(list),
        "by_duration": defaultdict(list),
        "by_stale_loss": defaultdict(list),
    }
    for trade in all_trades:
        groups["by_symbol"][trade["symbol"]].append(trade)
        groups["by_strategy"][trade["strategy"]].append(trade)
        groups["by_reason"][str(trade.get("reason_code") or trade.get("reason") or "unknown")].append(trade)
        bars = int(trade.get("bars_held", 0))
        groups["by_duration"][_bucket(bars)].append(trade)
        if bars > 120 and float(trade.get("pnl_pct", 0.0)) <= 0:
            groups["by_stale_loss"]["bars_gt_120_loss"].append(trade)
        elif bars > 120:
            groups["by_stale_loss"]["bars_gt_120_win"].append(trade)
        else:
            groups["by_stale_loss"]["bars_le_120"].append(trade)

    return {
        "set": set_name,
        "symbols": symbols,
        "start": start,
        "end": end,
        "config": config,
        "symbol_reports": symbol_reports,
        "summary": _summarize(all_trades),
        "groups": {
            group: {name: _summarize(rows) for name, rows in sorted(items.items())}
            for group, items in groups.items()
        },
        "worst_long_holds": sorted(
            [x for x in all_trades if int(x.get("bars_held", 0)) > 120],
            key=lambda row: float(row.get("pnl_pct", 0.0)),
        )[:20],
    }


def _fmt_pct(value: float | int | str | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return f"{float(value) * 100:.2f}%"


def _fmt_num(value: float | int | str | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def _row(name: str, stats: dict[str, Any]) -> str:
    return (
        f"| {name} | {_fmt_num(stats.get('trades'), 0)} | {_fmt_pct(stats.get('pnl_sum'))} | "
        f"{_fmt_pct(stats.get('win_rate'))} | {_fmt_pct(stats.get('avg_pnl'))} | "
        f"{_fmt_num(stats.get('profit_factor'))} | {_fmt_num(stats.get('avg_bars'))} |"
    )


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# Platform Holding Attribution",
        "",
        f"- set: `{payload['set']}`",
        f"- symbols: `{', '.join(payload['symbols'])}`",
        f"- period: `{payload['start']} ~ {payload['end']}`",
        "",
        "## Summary",
        "",
        "| group | trades | pnl_sum | win_rate | avg_pnl | PF | avg_bars |",
        "|---|---:|---:|---:|---:|---:|---:|",
        _row("all", payload["summary"]),
        "",
    ]
    for group_name in ["by_symbol", "by_strategy", "by_reason", "by_duration", "by_stale_loss"]:
        lines.extend([
            f"## {group_name}",
            "",
            "| group | trades | pnl_sum | win_rate | avg_pnl | PF | avg_bars |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for name, stats in payload["groups"][group_name].items():
            lines.append(_row(name, stats))
        lines.append("")

    lines.extend([
        "## Worst Long Holds",
        "",
        "| symbol | strategy | open_dt | close_dt | pnl | bars | reason |",
        "|---|---|---|---|---:|---:|---|",
    ])
    for trade in payload["worst_long_holds"]:
        lines.append(
            f"| {trade['symbol']} | {trade['strategy']} | {trade['open_dt']} | {trade['close_dt']} | "
            f"{_fmt_pct(trade['pnl_pct'])} | {_fmt_num(trade.get('bars_held'), 0)} | {trade.get('reason', '')} |"
        )
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze holding duration and exit reasons for a platform symbol set.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--set", dest="set_name", default="core_AP_A_ZN", choices=sorted(SYMBOL_SETS))
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-04-24")
    parser.add_argument("--out-json", type=Path, default=HERE / "platform_holding_attribution.json")
    parser.add_argument("--out-md", type=Path, default=HERE / "platform_holding_attribution.md")
    args = parser.parse_args()

    payload = build_report(args.db_path, args.set_name, args.start, args.end, BASE_CONFIG)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
