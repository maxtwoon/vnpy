"""A45 P6 — Second-buy hard-gate + ATR chop filter diagnostic.

Read-only report comparing ``second_buy_mode`` modes (``baseline``, ``gated``,
``off``) on the honest post-P1 baseline, plus entry win-rate bucketed by ATR
percentile at the open bar.

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Make the czsc_strategy package importable from this diagnostics script
_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from chan_strategy.signals import AtrStateTracker  # noqa: E402


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE
BANNER = "RESEARCH-ONLY — Diagnostic only, not a trading recommendation."
SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
WINDOW_START = "2026-04-24"
WINDOW_END = "2026-07-09"


def _run_backtest_for_mode(
    symbol: str,
    second_buy_mode: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[Any]]:
    """Run a single-symbol backtest under the requested second_buy_mode."""
    original_mode = STRATEGY_CONFIG.get("second_buy_mode")
    original_atr_filter = STRATEGY_CONFIG.get("atr_chop_filter")
    try:
        STRATEGY_CONFIG["second_buy_mode"] = second_buy_mode
        # Keep ATR chop filter off so this report isolates the second-buy gate effect.
        STRATEGY_CONFIG["atr_chop_filter"] = "off"
        engine = BacktestEngine(
            symbol=symbol,
            freq="1",
            start_date=start_date,
            end_date=end_date,
            db_path=str(db_path),
            table_name=f"{symbol.lower()}_1M_raw",
        )
        report = engine.run()
        combined_pairs = engine.strategy.get_combined_trades() if engine.strategy else []
        trade_bars = getattr(engine, "trade_bars", [])
        return report, combined_pairs, trade_bars
    finally:
        if original_mode is None:
            STRATEGY_CONFIG.pop("second_buy_mode", None)
        else:
            STRATEGY_CONFIG["second_buy_mode"] = original_mode
        if original_atr_filter is None:
            STRATEGY_CONFIG.pop("atr_chop_filter", None)
        else:
            STRATEGY_CONFIG["atr_chop_filter"] = original_atr_filter


def _serialize_pair(pair: dict[str, Any]) -> dict[str, Any]:
    """Make a trade pair JSON-serializable (datetime -> iso string)."""
    out = {}
    for k, v in pair.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _compute_atr_percentile_series(trade_bars: list[Any]) -> dict[datetime, float | None]:
    """Map each trade-bar dt to the ATR percentile at that bar.

    Uses the same AtrStateTracker parameters as the strategy so the diagnostic
    is consistent with the live gate.  Bars with insufficient history return
    ``None``.
    """
    tracker = AtrStateTracker(
        period=STRATEGY_CONFIG.get("atr_period", 14),
        lookback=STRATEGY_CONFIG.get("atr_lookback", 100),
        floor=STRATEGY_CONFIG.get("atr_percentile_floor", 0.30),
    )
    mapping: dict[datetime, float | None] = {}
    for bar in trade_bars:
        state = tracker.update(
            high=getattr(bar, "high", bar.close),
            low=getattr(bar, "low", bar.close),
            close=getattr(bar, "close", bar.close),
        )
        mapping[bar.dt] = state["percentile"]
    return mapping


def _bucket_atr_percentile(percentile: float | None) -> str:
    if percentile is None:
        return "insufficient_history"
    if percentile < 0.30:
        return "<p30"
    if percentile < 0.50:
        return "p30_50"
    if percentile < 0.70:
        return "p50_70"
    return ">=p70"


def _second_buy_pairs(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only trades produced by the second-buy sub-strategy."""
    return [p for p in pairs if "二买" in (p.get("strategy") or "")]


def _overall_metrics(
    report: dict[str, Any],
    combined_pairs: list[dict[str, Any]],
    trade_bars: list[Any],
) -> dict[str, Any]:
    """Extract overall strategy metrics and ATR-bucketed entry win-rate."""
    pairs = [_serialize_pair(p) for p in combined_pairs]
    second_buy = _second_buy_pairs(pairs)
    atr_map = _compute_atr_percentile_series(trade_bars)

    buckets: dict[str, dict[str, Any]] = {}
    for p in pairs:
        open_dt = p.get("open_dt")
        if open_dt is None:
            continue
        if isinstance(open_dt, str):
            open_dt = datetime.fromisoformat(open_dt)
        pct = atr_map.get(open_dt)
        bucket = _bucket_atr_percentile(pct)
        buckets.setdefault(bucket, {"count": 0, "wins": 0})
        buckets[bucket]["count"] += 1
        if p.get("pnl_pct", 0) > 0:
            buckets[bucket]["wins"] += 1

    for b in buckets.values():
        b["win_rate"] = b["wins"] / b["count"] if b["count"] else 0.0

    return {
        "trade_count": report.get("total_trades", 0),
        "win_count": sum(1 for p in pairs if p.get("pnl_pct", 0) > 0),
        "loss_count": sum(1 for p in pairs if p.get("pnl_pct", 0) <= 0),
        "win_rate": report.get("win_rate", 0.0),
        "profit_factor": report.get("profit_factor", 0.0),
        "total_return_pct": report.get("total_return_pct", 0.0),
        "max_drawdown_pct": report.get("max_drawdown_pct", 0.0),
        "sharpe_ratio": report.get("sharpe_ratio", 0.0),
        "second_buy_trade_count": len(second_buy),
        "second_buy_win_rate": (
            sum(1 for p in second_buy if p.get("pnl_pct", 0) > 0) / len(second_buy)
            if second_buy else 0.0
        ),
        "atr_percentile_buckets": buckets,
        "pairs": pairs,
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "total_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "second_buy_trade_count": 0,
        "second_buy_win_rate": 0.0,
        "atr_percentile_buckets": {},
        "pairs": [],
    }


def _run_symbol(
    symbol: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Run all second-buy modes for one symbol and compare performance."""
    result: dict[str, Any] = {
        "symbol": symbol,
        "baseline": None,
        "gated": None,
        "off": None,
        "error": None,
    }

    if not db_path.exists():
        result["error"] = "database_not_found"
        for mode in ("baseline", "gated", "off"):
            result[mode] = _empty_metrics()
        return result

    try:
        baseline_report, baseline_pairs, baseline_bars = _run_backtest_for_mode(
            symbol, "baseline", db_path, start_date, end_date
        )
        gated_report, gated_pairs, gated_bars = _run_backtest_for_mode(
            symbol, "gated", db_path, start_date, end_date
        )
        off_report, off_pairs, off_bars = _run_backtest_for_mode(
            symbol, "off", db_path, start_date, end_date
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        result["error"] = f"backtest_failed: {exc}"
        for mode in ("baseline", "gated", "off"):
            result[mode] = _empty_metrics()
        return result

    for mode, report, pairs, bars in (
        ("baseline", baseline_report, baseline_pairs, baseline_bars),
        ("gated", gated_report, gated_pairs, gated_bars),
        ("off", off_report, off_pairs, off_bars),
    ):
        if "error" in report:
            result["error"] = f"{mode}_error: {report['error']}"
            result[mode] = _empty_metrics()
        else:
            result[mode] = _overall_metrics(report, pairs, bars)

    return result


def _build_payload(
    db_path: Path,
    symbols: tuple[str, ...],
    start_date: str,
    end_date: str,
    stamp: str,
) -> dict[str, Any]:
    """Build the full report payload."""
    per_symbol = []
    for symbol in symbols:
        per_symbol.append(_run_symbol(symbol, db_path, start_date, end_date))

    totals = {}
    for mode in ("baseline", "gated", "off"):
        totals[mode] = sum(
            s[mode]["second_buy_trade_count"] for s in per_symbol if s.get(mode)
        )

    payload = {
        "disclaimer": BANNER,
        "generated_at": datetime.now().isoformat(),
        "second_buy_mode": "baseline vs gated vs off",
        "note": (
            "This report is evidence only and is not used to select or tune parameters. "
            "atr_percentile_floor is NOT adjusted based on this report in-task."
        ),
        "window": {"start_date": start_date, "end_date": end_date},
        "atr_config": {
            "atr_period": STRATEGY_CONFIG.get("atr_period", 14),
            "atr_lookback": STRATEGY_CONFIG.get("atr_lookback", 100),
            "atr_percentile_floor": STRATEGY_CONFIG.get("atr_percentile_floor", 0.30),
        },
        "total_symbols": len(symbols),
        "symbols_attempted": list(symbols),
        "second_buy_trades_by_mode": totals,
        "per_symbol": per_symbol,
    }
    return payload


def _format_md(payload: dict[str, Any]) -> str:
    """Render payload as Markdown for human review."""
    lines = [
        "# A45 P6 — Second-Buy Hard-Gate + ATR Chop Filter Diagnostic",
        "",
        f"**{payload['disclaimer']}**",
        "",
        f"Generated: {payload['generated_at']}",
        f"Window: {payload['window']['start_date']} ~ {payload['window']['end_date']}",
        "",
        "## ATR configuration",
        "",
        f"- period: {payload['atr_config']['atr_period']}",
        f"- lookback: {payload['atr_config']['atr_lookback']}",
        f"- percentile floor: {payload['atr_config']['atr_percentile_floor']}",
        "",
        "## Second-buy trades by mode",
        "",
        "| Mode | Second-buy trades |",
        "|------|------------------:|",
    ]
    for mode, count in payload["second_buy_trades_by_mode"].items():
        lines.append(f"| {mode} | {count} |")

    lines.extend(["", "## Per-symbol summary", ""])
    lines.append("| Symbol | Mode | Total trades | 2nd-buy trades | 2nd-buy WR | Return | Max DD |")
    lines.append("|--------|------|-------------:|---------------:|-----------:|-------:|-------:|")

    for symbol_data in payload["per_symbol"]:
        symbol = symbol_data["symbol"]
        error = symbol_data.get("error")
        if error:
            lines.append(f"| {symbol} | - | - | - | - | error: {error} | - |")
            continue
        for mode in ("baseline", "gated", "off"):
            m = symbol_data[mode]
            lines.append(
                f"| {symbol} | {mode} | {m['trade_count']} | "
                f"{m['second_buy_trade_count']} | "
                f"{m['second_buy_win_rate']*100:.1f}% | "
                f"{m['total_return_pct']:.2f}% | {m['max_drawdown_pct']:.2f}% |"
            )

    lines.extend(["", "## Entry win-rate by ATR percentile (baseline mode)", ""])
    lines.append("| Symbol | Bucket | Count | Wins | Win rate |")
    lines.append("|--------|--------|------:|-----:|---------:|")
    for symbol_data in payload["per_symbol"]:
        symbol = symbol_data["symbol"]
        if symbol_data.get("error"):
            continue
        buckets = symbol_data["baseline"].get("atr_percentile_buckets", {})
        if not buckets:
            lines.append(f"| {symbol} | - | - | - | - |")
        for bucket, b in sorted(buckets.items()):
            lines.append(
                f"| {symbol} | {bucket} | {b['count']} | {b['wins']} | "
                f"{b['win_rate']*100:.1f}% |"
            )

    lines.extend(["", "## Note", "", payload["note"], ""])
    return "\n".join(lines)


def main(
    db_path: Path | None = None,
    out_dir: Path = DEFAULT_OUT_DIR,
    symbols: tuple[str, ...] = tuple(SYMBOLS),
    start_date: str = WINDOW_START,
    end_date: str = WINDOW_END,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Generate the second-buy + ATR diagnostic report."""
    db_path = db_path or Path(SQLITE_DB_PATH)
    stamp = stamp or datetime.now().strftime("%Y-%m-%d")
    payload = _build_payload(db_path, symbols, start_date, end_date, stamp)

    json_path = out_dir / f"second_buy_and_atr_report_{stamp}.json"
    md_path = out_dir / f"second_buy_and_atr_report_{stamp}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_format_md(payload))

    print("Second-buy + ATR diagnostic report written to:")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate A45 P6 second-buy + ATR chop filter diagnostic report."
    )
    parser.add_argument(
        "--db-path", type=Path, default=None,
        help="Path to the SQLite kline database.",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=DEFAULT_OUT_DIR,
        help="Directory to write the report files.",
    )
    parser.add_argument(
        "--start-date", type=str, default=WINDOW_START,
        help="Backtest window start (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date", type=str, default=WINDOW_END,
        help="Backtest window end (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--symbols", nargs="+", default=list(SYMBOLS),
        help="Symbols to include in the report.",
    )
    args = parser.parse_args()
    main(
        db_path=args.db_path,
        out_dir=args.out_dir,
        symbols=tuple(args.symbols),
        start_date=args.start_date,
        end_date=args.end_date,
    )
