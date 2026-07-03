from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS, run_one
from diagnostics.second_buy_anchor_audit import collect_audit
from diagnostics.second_buy_entry_position_audit import enrich


FULL_START = "2022-01-01"
FULL_END = "2026-04-24"
OOS_START = "2025-01-01"
OOS_END = "2026-04-24"
DEFAULT_MAX_ENTRY_VS_ANCHOR = 0.03
DEFAULT_ENABLE_2BUY_SYMBOLS = ["AP888", "A888", "ZN888"]


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _fmt_trade_pct(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def _fmt_num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"trades": 0, "pnl_sum": 0.0, "win_rate": 0.0, "profit_factor": 0.0, "max_loss": 0.0}
    pnls = [float(x["pnl_pct"]) for x in rows]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x <= 0]
    loss_sum = abs(sum(losses))
    return {
        "trades": len(rows),
        "pnl_sum": sum(pnls),
        "win_rate": len(wins) / len(rows),
        "avg_pnl": sum(pnls) / len(rows),
        "profit_factor": sum(wins) / loss_sum if loss_sum else float("inf"),
        "max_loss": min(pnls),
    }


def _baseline_reports(db_path: Path, start: str, end: str, symbols: list[str]) -> dict[str, Any]:
    return {symbol: run_one(db_path, symbol, start, end, quiet=True) for symbol in symbols}


def _adjust_return(report: dict[str, Any], excluded_pairs: list[dict[str, Any]]) -> float:
    pos_2buy = STRATEGY_CONFIG.get("pos_2buy", 0.20)
    removed = sum(float(x["pnl_pct"]) for x in excluded_pairs) * pos_2buy * 100
    return float(report.get("total_return_pct", 0)) - removed


def _scenario(rows: list[dict[str, Any]], mode: str, enabled_symbols: set[str], max_entry: float) -> tuple[list[dict], list[dict]]:
    if mode == "entry_filter":
        kept = [r for r in rows if r.get("entry_vs_anchor_pct") is not None and r["entry_vs_anchor_pct"] <= max_entry]
    elif mode == "symbol_filter":
        kept = [r for r in rows if r["symbol"] in enabled_symbols]
    elif mode == "combined":
        kept = [
            r for r in rows
            if r["symbol"] in enabled_symbols
            and r.get("entry_vs_anchor_pct") is not None
            and r["entry_vs_anchor_pct"] <= max_entry
        ]
    else:
        kept = list(rows)
    kept_ids = {id(r) for r in kept}
    excluded = [r for r in rows if id(r) not in kept_ids]
    return kept, excluded


def run_period(db_path: Path, name: str, start: str, end: str, symbols: list[str], max_entry: float, enabled_symbols: set[str]) -> dict[str, Any]:
    audit = enrich(collect_audit(db_path, symbols, start, end))
    reports = _baseline_reports(db_path, start, end, symbols)
    rows = audit["trades"]
    scenarios = {}
    for mode in ["baseline", "entry_filter", "symbol_filter", "combined"]:
        kept, excluded = _scenario(rows, mode, enabled_symbols, max_entry)
        by_symbol = {}
        for symbol in symbols:
            symbol_excluded = [r for r in excluded if r["symbol"] == symbol]
            symbol_kept = [r for r in kept if r["symbol"] == symbol]
            by_symbol[symbol] = {
                "kept": _summarize(symbol_kept),
                "excluded": _summarize(symbol_excluded),
                "baseline_return_pct": reports[symbol].get("total_return_pct", 0),
                "adjusted_return_pct": _adjust_return(reports[symbol], symbol_excluded),
            }
        scenarios[mode] = {
            "kept": _summarize(kept),
            "excluded": _summarize(excluded),
            "by_symbol": by_symbol,
        }
    return {"name": name, "start": start, "end": end, "scenarios": scenarios}


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# 二买追高过滤与分品种启用研究",
        "",
        f"- max_entry_vs_anchor：{payload['max_entry_vs_anchor'] * 100:.2f}%",
        f"- enable_2buy_symbols：{' / '.join(payload['enable_2buy_symbols'])}",
        "- 口径：不改正式策略；按已发生二买交易做研究性剔除，并估算剔除后的最终收益。",
        "",
    ]
    for period in payload["periods"]:
        lines.extend([
            f"## {period['name']} ({period['start']} ~ {period['end']})",
            "",
            "| 场景 | 保留二买 | 保留二买收益 | 保留胜率 | 排除二买 | 排除二买收益 |",
            "|---|---:|---:|---:|---:|---:|",
        ])
        for mode, data in period["scenarios"].items():
            kept = data["kept"]
            excluded = data["excluded"]
            lines.append(
                f"| {mode} | {_fmt_num(kept['trades'], 0)} | {_fmt_trade_pct(kept['pnl_sum'])} | "
                f"{_fmt_trade_pct(kept['win_rate'])} | {_fmt_num(excluded['trades'], 0)} | {_fmt_trade_pct(excluded['pnl_sum'])} |"
            )
        lines.extend([
            "",
            "### 按品种 adjusted_return_pct",
            "",
            "| 场景 | 品种 | baseline收益 | adjusted收益 | 差值 | 保留二买 | 排除二买 |",
            "|---|---|---:|---:|---:|---:|---:|",
        ])
        for mode, data in period["scenarios"].items():
            for symbol, row in data["by_symbol"].items():
                delta = row["adjusted_return_pct"] - row["baseline_return_pct"]
                lines.append(
                    f"| {mode} | {symbol} | {_fmt_pct(row['baseline_return_pct'])} | "
                    f"{_fmt_pct(row['adjusted_return_pct'])} | {_fmt_pct(delta)} | "
                    f"{_fmt_num(row['kept']['trades'], 0)} | {_fmt_num(row['excluded']['trades'], 0)} |"
                )
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Research second-buy chase filter and per-symbol enable list.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--max-entry-vs-anchor", type=float, default=DEFAULT_MAX_ENTRY_VS_ANCHOR)
    parser.add_argument("--enable-2buy-symbols", nargs="+", default=DEFAULT_ENABLE_2BUY_SYMBOLS)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("second_buy_research_filters.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("second_buy_research_filters.md"))
    args = parser.parse_args()

    enabled = set(args.enable_2buy_symbols)
    payload = {
        "max_entry_vs_anchor": args.max_entry_vs_anchor,
        "enable_2buy_symbols": args.enable_2buy_symbols,
        "periods": [
            run_period(args.db_path, "full", FULL_START, FULL_END, args.symbols, args.max_entry_vs_anchor, enabled),
            run_period(args.db_path, "out_sample", OOS_START, OOS_END, args.symbols, args.max_entry_vs_anchor, enabled),
        ],
    }
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
