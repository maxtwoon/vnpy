"""A46 P7 — Short-enable diagnostic report.

Read-only report comparing long-only (enable_short=False) with long+short
(enable_short=True) on the honest post-P1 baseline. Per-symbol short-side
expectancy and combined long+short metrics are reported for research review.

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


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE
BANNER = "RESEARCH-ONLY — Diagnostic only, not a trading recommendation."
SYMBOLS = ["RB888", "SC888"]
WINDOW_START = "2026-04-24"
WINDOW_END = "2026-07-09"


def _run_backtest(
    symbol: str,
    enable_short: bool,
    regime_model: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run a single-symbol backtest under the requested short/regime config."""
    original_enable_short = STRATEGY_CONFIG.get("enable_short")
    original_regime_model = STRATEGY_CONFIG.get("regime_model")
    try:
        STRATEGY_CONFIG["enable_short"] = enable_short
        STRATEGY_CONFIG["regime_model"] = regime_model
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
        if original_enable_short is None:
            STRATEGY_CONFIG.pop("enable_short", None)
        else:
            STRATEGY_CONFIG["enable_short"] = original_enable_short
        if original_regime_model is None:
            STRATEGY_CONFIG.pop("regime_model", None)
        else:
            STRATEGY_CONFIG["regime_model"] = original_regime_model


def _serialize_pair(pair: dict[str, Any]) -> dict[str, Any]:
    """Make a trade pair JSON-serializable (datetime -> iso string)."""
    out = {}
    for k, v in pair.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _short_pairs(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only trades produced by short sub-strategies."""
    return [p for p in pairs if "空头" in (p.get("strategy") or "")]


def _long_pairs(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only trades produced by long sub-strategies."""
    return [p for p in pairs if "多头" in (p.get("strategy") or "")]


def _expectancy(pairs: list[dict[str, Any]]) -> float:
    """Average PnL% per trade (expectancy)."""
    if not pairs:
        return 0.0
    return sum(p.get("pnl_pct", 0.0) for p in pairs) / len(pairs)


def _overall_metrics(
    report: dict[str, Any],
    combined_pairs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract overall strategy metrics and short-side expectancy."""
    pairs = [_serialize_pair(p) for p in combined_pairs]
    longs = _long_pairs(pairs)
    shorts = _short_pairs(pairs)

    return {
        "trade_count": report.get("total_trades", 0),
        "win_count": sum(1 for p in pairs if p.get("pnl_pct", 0) > 0),
        "loss_count": sum(1 for p in pairs if p.get("pnl_pct", 0) <= 0),
        "win_rate": report.get("win_rate", 0.0),
        "profit_factor": report.get("profit_factor", 0.0),
        "total_return_pct": report.get("total_return_pct", 0.0),
        "max_drawdown_pct": report.get("max_drawdown_pct", 0.0),
        "sharpe_ratio": report.get("sharpe_ratio", 0.0),
        "both_long_short_bars": report.get("both_long_short_bars", 0),
        "long_trade_count": len(longs),
        "long_win_rate": (
            sum(1 for p in longs if p.get("pnl_pct", 0) > 0) / len(longs)
            if longs else 0.0
        ),
        "long_expectancy": _expectancy(longs),
        "short_trade_count": len(shorts),
        "short_win_rate": (
            sum(1 for p in shorts if p.get("pnl_pct", 0) > 0) / len(shorts)
            if shorts else 0.0
        ),
        "short_expectancy": _expectancy(shorts),
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
        "both_long_short_bars": 0,
        "long_trade_count": 0,
        "long_win_rate": 0.0,
        "long_expectancy": 0.0,
        "short_trade_count": 0,
        "short_win_rate": 0.0,
        "short_expectancy": 0.0,
        "pairs": [],
    }


def _run_symbol(
    symbol: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Run long-only and long+short variants for one symbol."""
    result: dict[str, Any] = {
        "symbol": symbol,
        "long_only": None,
        "independent": None,
        "router": None,
        "error": None,
    }

    if not db_path.exists():
        result["error"] = "database_not_found"
        for mode in ("long_only", "independent", "router"):
            result[mode] = _empty_metrics()
        return result

    try:
        long_report, long_pairs = _run_backtest(
            symbol, False, "independent", db_path, start_date, end_date
        )
        independent_report, independent_pairs = _run_backtest(
            symbol, True, "independent", db_path, start_date, end_date
        )
        router_report, router_pairs = _run_backtest(
            symbol, True, "router", db_path, start_date, end_date
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        result["error"] = f"backtest_failed: {exc}"
        for mode in ("long_only", "independent", "router"):
            result[mode] = _empty_metrics()
        return result

    for mode, report, pairs in (
        ("long_only", long_report, long_pairs),
        ("independent", independent_report, independent_pairs),
        ("router", router_report, router_pairs),
    ):
        if "error" in report:
            result["error"] = f"{mode}_error: {report['error']}"
            result[mode] = _empty_metrics()
        else:
            result[mode] = _overall_metrics(report, pairs)

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
    for mode in ("long_only", "independent", "router"):
        totals[mode] = {
            "trade_count": sum(
                s[mode].get("trade_count", 0) for s in per_symbol if s.get(mode)
            ),
            "short_trade_count": sum(
                s[mode].get("short_trade_count", 0) for s in per_symbol if s.get(mode)
            ),
            "both_long_short_bars": sum(
                s[mode].get("both_long_short_bars", 0) for s in per_symbol if s.get(mode)
            ),
        }

    payload = {
        "disclaimer": BANNER,
        "generated_at": datetime.now().isoformat(),
        "regime_model": "long_only vs independent vs router",
        "note": (
            "This report is evidence only and is not used to select or tune parameters. "
            "No threshold tuning is performed from this report in-task. "
            "Window chosen as the most recent continuous 4-month period available for both RB888 and SC888."
        ),
        "window": {"start_date": start_date, "end_date": end_date},
        "total_symbols": len(symbols),
        "symbols_attempted": list(symbols),
        "totals": totals,
        "per_symbol": per_symbol,
    }
    return payload


def _format_md(payload: dict[str, Any]) -> str:
    """Render payload as Markdown for human review."""
    lines = [
        "# A46 P7 — Short-Enable Diagnostic",
        "",
        f"**{payload['disclaimer']}**",
        "",
        f"Generated: {payload['generated_at']}",
        f"Window: {payload['window']['start_date']} ~ {payload['window']['end_date']}",
        "",
        "## Totals",
        "",
        "| Mode | Total trades | Short trades | Both-long-short bars |",
        "|------|-------------:|-------------:|---------------------:|",
    ]
    for mode, t in payload["totals"].items():
        lines.append(
            f"| {mode} | {t['trade_count']} | {t['short_trade_count']} | "
            f"{t['both_long_short_bars']} |"
        )

    lines.extend(["", "## Per-symbol summary", ""])
    lines.append(
        "| Symbol | Mode | Trades | Long WR | Long Exp | Short WR | Short Exp | Return | Max DD | Both-L-S |"
    )
    lines.append(
        "|--------|------|-------:|--------:|---------:|---------:|----------:|-------:|-------:|---------:|"
    )

    for symbol_data in payload["per_symbol"]:
        symbol = symbol_data["symbol"]
        error = symbol_data.get("error")
        if error:
            lines.append(f"| {symbol} | - | - | - | - | - | - | error: {error} | - | - |")
            continue
        for mode in ("long_only", "independent", "router"):
            m = symbol_data[mode]
            lines.append(
                f"| {symbol} | {mode} | {m['trade_count']} | "
                f"{m['long_win_rate']*100:.1f}% | {m['long_expectancy']*100:.2f}% | "
                f"{m['short_win_rate']*100:.1f}% | {m['short_expectancy']*100:.2f}% | "
                f"{m['total_return_pct']:.2f}% | {m['max_drawdown_pct']:.2f}% | "
                f"{m['both_long_short_bars']} |"
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
    """Generate the short-enable diagnostic report."""
    db_path = db_path or Path(SQLITE_DB_PATH)
    stamp = stamp or datetime.now().strftime("%Y-%m-%d")
    payload = _build_payload(db_path, symbols, start_date, end_date, stamp)

    json_path = out_dir / f"short_enable_report_{stamp}.json"
    md_path = out_dir / f"short_enable_report_{stamp}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_format_md(payload))

    print("Short-enable diagnostic report written to:")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate A46 P7 short-enable diagnostic report."
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
