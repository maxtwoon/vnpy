from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG
from diagnostics.backtest_matrix_report import DEFAULT_SYMBOLS, _dominant_symbol
from diagnostics.strategy_execution_experiment_matrix import (
    FULL_END,
    FULL_START,
    OOS_END,
    OOS_START,
    _scenario_params,
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return value


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


def _strategy_weight(strategy: str) -> float:
    if "一买" in strategy:
        return float(STRATEGY_CONFIG.get("pos_1buy", 0.10))
    if "二买" in strategy:
        return float(STRATEGY_CONFIG.get("pos_2buy", 0.20))
    if "三买" in strategy:
        return float(STRATEGY_CONFIG.get("pos_3buy", 0.30))
    if "一卖" in strategy:
        return float(STRATEGY_CONFIG.get("pos_1sell", 0.10))
    if "二卖" in strategy:
        return float(STRATEGY_CONFIG.get("pos_2sell", 0.20))
    if "三卖" in strategy:
        return float(STRATEGY_CONFIG.get("pos_3sell", 0.30))
    return 0.10


def _trade_key(trade: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(trade["strategy"]),
        trade["open_dt"].isoformat(sep=" "),
        f"{float(trade['open_price']):.8f}",
    )


def _weighted_pct(trade: dict[str, Any]) -> float:
    return float(trade["pnl_pct"]) * _strategy_weight(str(trade["strategy"])) * 100


def _max_losing_streak(trades: list[dict[str, Any]]) -> int:
    streak = 0
    max_streak = 0
    for trade in sorted(trades, key=lambda x: x["close_dt"]):
        if float(trade["pnl_pct"]) <= 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _trade_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {
            "trades": 0,
            "avg_pnl_pct": 0.0,
            "median_pnl_pct": 0.0,
            "max_loss_pct": 0.0,
            "max_profit_pct": 0.0,
            "weighted_sum_pct": 0.0,
            "max_losing_streak": 0,
            "by_reason": {},
            "by_strategy": {},
        }
    pnls = [float(t["pnl_pct"]) for t in trades]
    weighted = [_weighted_pct(t) for t in trades]
    by_reason: dict[str, dict[str, Any]] = {}
    by_strategy: dict[str, dict[str, Any]] = {}
    for field, target in [("reason_code", by_reason), ("strategy", by_strategy)]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for trade in trades:
            grouped[str(trade.get(field, ""))].append(trade)
        for key, rows in grouped.items():
            target[key] = {
                "trades": len(rows),
                "raw_pnl_sum_pct": sum(float(x["pnl_pct"]) for x in rows) * 100,
                "weighted_pnl_sum_pct": sum(_weighted_pct(x) for x in rows),
            }
    return {
        "trades": len(trades),
        "avg_pnl_pct": sum(pnls) / len(pnls) * 100,
        "median_pnl_pct": median(pnls) * 100,
        "max_loss_pct": min(pnls) * 100,
        "max_profit_pct": max(pnls) * 100,
        "weighted_sum_pct": sum(weighted),
        "max_losing_streak": _max_losing_streak(trades),
        "by_reason": dict(sorted(by_reason.items())),
        "by_strategy": dict(sorted(by_strategy.items())),
    }


def _run_trades(db_path: Path, symbol: str, start: str, end: str, params: dict[str, Any]) -> dict[str, Any]:
    original = copy.deepcopy(STRATEGY_CONFIG)
    table_name = f"{symbol.lower()}_1M_raw"
    data_symbol = _dominant_symbol(db_path, table_name, start, end)
    try:
        STRATEGY_CONFIG.update(copy.deepcopy(params))
        engine = BacktestEngine(
            symbol=data_symbol,
            db_path=str(db_path),
            table_name=table_name,
            start_date=start,
            end_date=end,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            report = engine.run()
        trades = engine.strategy.get_combined_trades()
        for trade in trades:
            trade["requested_symbol"] = symbol
            trade["data_symbol"] = data_symbol
            trade["weighted_pnl_pct"] = _weighted_pct(trade)
        return {"report": report, "trades": trades}
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)


def _diff_trades(baseline: list[dict[str, Any]], combined: list[dict[str, Any]]) -> dict[str, Any]:
    base_map = {_trade_key(t): t for t in baseline}
    combo_map = {_trade_key(t): t for t in combined}
    base_keys = set(base_map)
    combo_keys = set(combo_map)
    removed = [base_map[k] for k in sorted(base_keys - combo_keys)]
    added = [combo_map[k] for k in sorted(combo_keys - base_keys)]
    changed = []
    unchanged = []
    for key in sorted(base_keys & combo_keys):
        b = base_map[key]
        c = combo_map[key]
        item = {
            "key": key,
            "baseline": b,
            "combined": c,
            "weighted_delta_pct": _weighted_pct(c) - _weighted_pct(b),
            "raw_delta_pct": (float(c["pnl_pct"]) - float(b["pnl_pct"])) * 100,
            "close_dt_changed": b["close_dt"] != c["close_dt"],
            "reason_changed": b.get("reason_code") != c.get("reason_code"),
        }
        if item["close_dt_changed"] or item["reason_changed"] or abs(item["raw_delta_pct"]) > 1e-12:
            changed.append(item)
        else:
            unchanged.append(item)
    return {
        "removed": removed,
        "added": added,
        "changed": changed,
        "unchanged_count": len(unchanged),
        "summary": {
            "removed_count": len(removed),
            "added_count": len(added),
            "changed_count": len(changed),
            "unchanged_count": len(unchanged),
            "removed_weighted_pnl_pct": sum(_weighted_pct(t) for t in removed),
            "added_weighted_pnl_pct": sum(_weighted_pct(t) for t in added),
            "changed_weighted_delta_pct": sum(float(t["weighted_delta_pct"]) for t in changed),
        },
    }


def build_report(db_path: Path, symbols: list[str]) -> dict[str, Any]:
    params = _scenario_params()
    periods = {
        "full": (FULL_START, FULL_END),
        "out_sample": (OOS_START, OOS_END),
    }
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "symbols": symbols,
        "periods": {},
    }
    for period_name, (start, end) in periods.items():
        period_rows = {}
        all_base: list[dict[str, Any]] = []
        all_combo: list[dict[str, Any]] = []
        for symbol in symbols:
            base = _run_trades(db_path, symbol, start, end, params["baseline"])
            combo = _run_trades(db_path, symbol, start, end, params["combined"])
            all_base.extend(base["trades"])
            all_combo.extend(combo["trades"])
            period_rows[symbol] = {
                "baseline_report": base["report"],
                "combined_report": combo["report"],
                "baseline_stats": _trade_stats(base["trades"]),
                "combined_stats": _trade_stats(combo["trades"]),
                "diff": _diff_trades(base["trades"], combo["trades"]),
            }
        period_rows["_portfolio"] = {
            "baseline_stats": _trade_stats(all_base),
            "combined_stats": _trade_stats(all_combo),
            "diff": _diff_trades(all_base, all_combo),
        }
        payload["periods"][period_name] = {"start": start, "end": end, "symbols": period_rows}
    return payload


def _top_bottom(diff: dict[str, Any], n: int = 10) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = []
    for t in diff["removed"]:
        rows.append({"type": "removed", "trade": t, "impact_pct": -_weighted_pct(t)})
    for t in diff["added"]:
        rows.append({"type": "added", "trade": t, "impact_pct": _weighted_pct(t)})
    for t in diff["changed"]:
        rows.append({"type": "changed", "trade": t["combined"], "baseline": t["baseline"], "impact_pct": t["weighted_delta_pct"]})
    rows = sorted(rows, key=lambda x: float(x["impact_pct"]), reverse=True)
    return rows[:n], list(reversed(rows[-n:]))


def write_markdown(payload: dict[str, Any], out: Path) -> None:
    lines = [
        "# Baseline vs Combined Trade Difference Attribution",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- db_path: `{payload['db_path']}`",
        "- diff key: `(strategy, open_dt, open_price)`",
        "",
    ]
    for period_name, period in payload["periods"].items():
        port = period["symbols"]["_portfolio"]
        bstats = port["baseline_stats"]
        cstats = port["combined_stats"]
        diff = port["diff"]
        s = diff["summary"]
        lines.extend([
            f"## {period_name} ({period['start']} ~ {period['end']})",
            "",
            "| scope | trades | avg_pnl | median_pnl | max_loss | max_profit | weighted_sum | losing_streak |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
            f"| baseline | {_fmt_num(bstats['trades'], 0)} | {_fmt_pct(bstats['avg_pnl_pct'])} | {_fmt_pct(bstats['median_pnl_pct'])} | {_fmt_pct(bstats['max_loss_pct'])} | {_fmt_pct(bstats['max_profit_pct'])} | {_fmt_pct(bstats['weighted_sum_pct'])} | {_fmt_num(bstats['max_losing_streak'], 0)} |",
            f"| combined | {_fmt_num(cstats['trades'], 0)} | {_fmt_pct(cstats['avg_pnl_pct'])} | {_fmt_pct(cstats['median_pnl_pct'])} | {_fmt_pct(cstats['max_loss_pct'])} | {_fmt_pct(cstats['max_profit_pct'])} | {_fmt_pct(cstats['weighted_sum_pct'])} | {_fmt_num(cstats['max_losing_streak'], 0)} |",
            "",
            "| removed | added | changed | unchanged | removed_weighted | added_weighted | changed_delta | total_impact |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
            f"| {s['removed_count']} | {s['added_count']} | {s['changed_count']} | {s['unchanged_count']} | {_fmt_pct(s['removed_weighted_pnl_pct'])} | {_fmt_pct(s['added_weighted_pnl_pct'])} | {_fmt_pct(s['changed_weighted_delta_pct'])} | {_fmt_pct(-s['removed_weighted_pnl_pct'] + s['added_weighted_pnl_pct'] + s['changed_weighted_delta_pct'])} |",
            "",
            "### By Symbol",
            "",
            "| symbol | base_trades | combo_trades | removed | added | changed | total_impact | base_weighted | combo_weighted |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for symbol, row in period["symbols"].items():
            if symbol == "_portfolio":
                continue
            rs = row["diff"]["summary"]
            total = -rs["removed_weighted_pnl_pct"] + rs["added_weighted_pnl_pct"] + rs["changed_weighted_delta_pct"]
            lines.append(
                f"| {symbol} | {_fmt_num(row['baseline_stats']['trades'], 0)} | {_fmt_num(row['combined_stats']['trades'], 0)} | "
                f"{rs['removed_count']} | {rs['added_count']} | {rs['changed_count']} | {_fmt_pct(total)} | "
                f"{_fmt_pct(row['baseline_stats']['weighted_sum_pct'])} | {_fmt_pct(row['combined_stats']['weighted_sum_pct'])} |"
            )
        lines.extend(["", "### Exit Reason Weighted PnL", "", "| scope | reason | trades | weighted_pnl |", "|---|---|---:|---:|"])
        for scope, stats in [("baseline", bstats), ("combined", cstats)]:
            for reason, item in stats["by_reason"].items():
                lines.append(f"| {scope} | {reason} | {_fmt_num(item['trades'], 0)} | {_fmt_pct(item['weighted_pnl_sum_pct'])} |")

        top, bottom = _top_bottom(diff)
        lines.extend(["", "### Top Positive Impacts", "", "| type | symbol | strategy | open_dt | close_dt | reason | impact | pnl |", "|---|---|---|---|---|---|---:|---:|"])
        for item in top:
            t = item["trade"]
            lines.append(
                f"| {item['type']} | {t.get('requested_symbol')} | {t.get('strategy')} | {t.get('open_dt')} | {t.get('close_dt')} | "
                f"{t.get('reason_code')} | {_fmt_pct(item['impact_pct'])} | {_fmt_trade_pct(t.get('pnl_pct'))} |"
            )
        lines.extend(["", "### Top Negative Impacts", "", "| type | symbol | strategy | open_dt | close_dt | reason | impact | pnl |", "|---|---|---|---|---|---|---:|---:|"])
        for item in bottom:
            t = item["trade"]
            lines.append(
                f"| {item['type']} | {t.get('requested_symbol')} | {t.get('strategy')} | {t.get('open_dt')} | {t.get('close_dt')} | "
                f"{t.get('reason_code')} | {_fmt_pct(item['impact_pct'])} | {_fmt_trade_pct(t.get('pnl_pct'))} |"
            )
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Attribute trade-level differences between baseline and combined.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out-json", type=Path, default=Path(__file__).with_name("trade_difference_attribution.json"))
    parser.add_argument("--out-md", type=Path, default=Path(__file__).with_name("trade_difference_attribution.md"))
    args = parser.parse_args()

    payload = build_report(args.db_path, args.symbols)
    args.out_json.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
