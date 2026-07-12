"""A43 P4 — MACD-area divergence comparison diagnostic.

Read-only report comparing ``divergence_model="amplitude"`` (legacy) and
``"macd"`` (12/26/9 standard parameters) on the honest post-P1 baseline.

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

# Make the czsc_strategy package importable from this diagnostics script
_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import BACKTEST_CONFIG, SQLITE_DB_PATH, STRATEGY_CONFIG


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE
BANNER = "RESEARCH-ONLY — Diagnostic only, not a trading recommendation."
SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
WINDOW_START = "2026-04-24"
WINDOW_END = "2026-07-09"


def _run_backtest_for_model(
    symbol: str,
    model: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run a single-symbol backtest under the requested divergence_model."""
    original_model = STRATEGY_CONFIG.get("divergence_model")
    try:
        STRATEGY_CONFIG["divergence_model"] = model
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
        return report, combined_pairs
    finally:
        if original_model is None:
            STRATEGY_CONFIG.pop("divergence_model", None)
        else:
            STRATEGY_CONFIG["divergence_model"] = original_model


def _serialize_pair(pair: dict[str, Any]) -> dict[str, Any]:
    """Make a trade pair JSON-serializable (datetime -> iso string)."""
    out = {}
    for k, v in pair.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _first_buy_metrics(report: dict[str, Any], combined_pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract first-buy sub-strategy metrics from a backtest report."""
    sub = report.get("sub_strategies", {}).get("一买多头", {})
    pairs = [
        _serialize_pair(p) for p in combined_pairs
        if p.get("strategy") == "一买多头"
    ]
    return {
        "trade_count": sub.get("total_trades", 0),
        "win_count": sub.get("win_count", 0),
        "loss_count": sub.get("loss_count", 0),
        "win_rate": sub.get("win_rate", 0.0),
        "profit_factor": sub.get("profit_factor", 0.0),
        "avg_profit_pct": sub.get("avg_profit", 0.0) * 100,
        "avg_loss_pct": sub.get("avg_loss", 0.0) * 100,
        "total_return_pct": report.get("total_return_pct", 0.0),
        "max_drawdown_pct": report.get("max_drawdown_pct", 0.0),
        "first_buy_pairs": pairs,
    }


def _run_symbol(
    symbol: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Run both models for one symbol and compare first-buy performance."""
    result: dict[str, Any] = {
        "symbol": symbol,
        "amplitude": None,
        "macd": None,
        "error": None,
    }

    if not db_path.exists():
        result["error"] = "database_not_found"
        result["amplitude"] = _empty_metrics()
        result["macd"] = _empty_metrics()
        return result

    try:
        amplitude_report, amplitude_pairs = _run_backtest_for_model(
            symbol, "amplitude", db_path, start_date, end_date
        )
        macd_report, macd_pairs = _run_backtest_for_model(
            symbol, "macd", db_path, start_date, end_date
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        result["error"] = f"backtest_failed: {exc}"
        result["amplitude"] = _empty_metrics()
        result["macd"] = _empty_metrics()
        return result

    if "error" in amplitude_report:
        result["error"] = f"amplitude_error: {amplitude_report['error']}"
        result["amplitude"] = _empty_metrics()
    else:
        result["amplitude"] = _first_buy_metrics(amplitude_report, amplitude_pairs)

    if "error" in macd_report:
        result["error"] = f"macd_error: {macd_report['error']}"
        result["macd"] = _empty_metrics()
    else:
        result["macd"] = _first_buy_metrics(macd_report, macd_pairs)

    return result


def _empty_metrics() -> dict[str, Any]:
    return {
        "trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "avg_profit_pct": 0.0,
        "avg_loss_pct": 0.0,
        "total_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "first_buy_pairs": [],
    }


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

    total_amplitude_trades = sum(
        s["amplitude"]["trade_count"] for s in per_symbol if s["amplitude"]
    )
    total_macd_trades = sum(
        s["macd"]["trade_count"] for s in per_symbol if s["macd"]
    )

    payload = {
        "disclaimer": BANNER,
        "generated_at": datetime.now().isoformat(),
        "divergence_model": "amplitude vs macd",
        "macd_params": {
            "fast": STRATEGY_CONFIG.get("macd_fast", 12),
            "slow": STRATEGY_CONFIG.get("macd_slow", 26),
            "signal": STRATEGY_CONFIG.get("macd_signal", 9),
        },
        "note": (
            "MACD parameters are fixed at the 12/26/9 standard values. "
            "This report is evidence only and is not used to select or tune parameters."
        ),
        "window": {"start_date": start_date, "end_date": end_date},
        "total_symbols": len(symbols),
        "symbols_attempted": list(symbols),
        "total_amplitude_first_buy_trades": total_amplitude_trades,
        "total_macd_first_buy_trades": total_macd_trades,
        "per_symbol": per_symbol,
    }
    return payload


def _format_md(payload: dict[str, Any]) -> str:
    """Render the report payload as Markdown."""
    lines = [
        "# A43 P4 — MACD-Area Divergence Comparison Report",
        "",
        f"> {payload['disclaimer']}",
        "",
        f"Generated: {payload['generated_at']}",
        f"Window: {payload['window']['start_date']} ~ {payload['window']['end_date']}",
        "",
        "## Parameters",
        "",
        f"- Divergence models: {payload['divergence_model']}",
        f"- MACD fast: {payload['macd_params']['fast']}",
        f"- MACD slow: {payload['macd_params']['slow']}",
        f"- MACD signal: {payload['macd_params']['signal']}",
        "",
        f"> {payload['note']}",
        "",
        "## Summary",
        "",
        f"- Amplitude first-buy trades: {payload['total_amplitude_first_buy_trades']}",
        f"- MACD first-buy trades: {payload['total_macd_first_buy_trades']}",
        "",
        "## Per-Symbol First-Buy Metrics",
        "",
        "| Symbol | Model | Trades | Win Rate | PF | Avg Profit | Avg Loss | Return | Max DD |",
        "|--------|-------|--------|----------|----|------------|----------|--------|--------|",
    ]

    for item in payload["per_symbol"]:
        symbol = item["symbol"]
        if item.get("error"):
            lines.append(f"| {symbol} | — | — | — | — | — | — | — | {item['error']} |")
            continue
        for model in ("amplitude", "macd"):
            m = item[model]
            lines.append(
                f"| {symbol} | {model} | "
                f"{m['trade_count']} | "
                f"{m['win_rate']*100:.1f}% | "
                f"{m['profit_factor']:.2f} | "
                f"{m['avg_profit_pct']:.2f}% | "
                f"{m['avg_loss_pct']:.2f}% | "
                f"{m['total_return_pct']:.2f}% | "
                f"{m['max_drawdown_pct']:.2f}% |"
            )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "This report compares the legacy amplitude proxy for 背驰 against a standard "
        "MACD area measure on the post-P1 baseline.  It is read-only evidence; any "
        "decision to switch the default divergence model belongs to a future "
        "holdout-validated promotion step.",
        "",
    ])
    return "\n".join(lines)


def main(
    db_path: Path | None = None,
    symbols: tuple[str, ...] = (),
    start_date: str = WINDOW_START,
    end_date: str = WINDOW_END,
    out_dir: Path = DEFAULT_OUT_DIR,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Generate the amplitude-vs-MACD divergence comparison report."""
    db_path = db_path or Path(SQLITE_DB_PATH)
    symbols = symbols or tuple(SYMBOLS)
    stamp = stamp or datetime.now().strftime("%Y-%m-%d")

    payload = _build_payload(db_path, symbols, start_date, end_date, stamp)

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"divergence_model_comparison_report_{stamp}.json"
    md_path = out_dir / f"divergence_model_comparison_report_{stamp}.md"

    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_format_md(payload), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"{BANNER}")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A43 P4 divergence-model comparison report")
    parser.add_argument("--db-path", type=Path, default=None, help="Path to SQLite kline database")
    parser.add_argument("--symbols", nargs="+", default=None, help="Symbols to evaluate")
    parser.add_argument("--start-date", default=WINDOW_START, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=WINDOW_END, help="End date (YYYY-MM-DD)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory")
    parser.add_argument("--stamp", default=None, help="Report filename stamp")
    args = parser.parse_args()

    main(
        db_path=args.db_path,
        symbols=tuple(args.symbols) if args.symbols else (),
        start_date=args.start_date,
        end_date=args.end_date,
        out_dir=args.out_dir,
        stamp=args.stamp,
    )
