"""A44 P5 — Multi-level resonance entry filter comparison diagnostic.

Read-only report comparing ``resonance_filter`` modes (``off``, ``daily``,
``daily_4h``) on the honest post-P1 baseline.

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
SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
WINDOW_START = "2026-04-24"
WINDOW_END = "2026-07-09"


def _run_backtest_for_filter(
    symbol: str,
    resonance_filter: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run a single-symbol backtest under the requested resonance_filter."""
    original_filter = STRATEGY_CONFIG.get("resonance_filter")
    original_freq = STRATEGY_CONFIG.get("resonance_freq_4h")
    try:
        STRATEGY_CONFIG["resonance_filter"] = resonance_filter
        STRATEGY_CONFIG["resonance_freq_4h"] = "240分钟"
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
        if original_filter is None:
            STRATEGY_CONFIG.pop("resonance_filter", None)
        else:
            STRATEGY_CONFIG["resonance_filter"] = original_filter
        if original_freq is None:
            STRATEGY_CONFIG.pop("resonance_freq_4h", None)
        else:
            STRATEGY_CONFIG["resonance_freq_4h"] = original_freq


def _serialize_pair(pair: dict[str, Any]) -> dict[str, Any]:
    """Make a trade pair JSON-serializable (datetime -> iso string)."""
    out = {}
    for k, v in pair.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _overall_metrics(report: dict[str, Any], combined_pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract overall strategy metrics from a backtest report."""
    pairs = [_serialize_pair(p) for p in combined_pairs]
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
        "pairs": [],
    }


def _run_symbol(
    symbol: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Run all resonance modes for one symbol and compare performance."""
    result: dict[str, Any] = {
        "symbol": symbol,
        "off": None,
        "daily": None,
        "daily_4h": None,
        "error": None,
    }

    if not db_path.exists():
        result["error"] = "database_not_found"
        for mode in ("off", "daily", "daily_4h"):
            result[mode] = _empty_metrics()
        return result

    try:
        off_report, off_pairs = _run_backtest_for_filter(
            symbol, "off", db_path, start_date, end_date
        )
        daily_report, daily_pairs = _run_backtest_for_filter(
            symbol, "daily", db_path, start_date, end_date
        )
        daily_4h_report, daily_4h_pairs = _run_backtest_for_filter(
            symbol, "daily_4h", db_path, start_date, end_date
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        result["error"] = f"backtest_failed: {exc}"
        for mode in ("off", "daily", "daily_4h"):
            result[mode] = _empty_metrics()
        return result

    for mode, report, pairs in (
        ("off", off_report, off_pairs),
        ("daily", daily_report, daily_pairs),
        ("daily_4h", daily_4h_report, daily_4h_pairs),
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
    for mode in ("off", "daily", "daily_4h"):
        totals[mode] = sum(
            s[mode]["trade_count"] for s in per_symbol if s.get(mode)
        )

    payload = {
        "disclaimer": BANNER,
        "generated_at": datetime.now().isoformat(),
        "resonance_filter": "off vs daily vs daily_4h",
        "note": (
            "This report is evidence only and is not used to select or tune parameters. "
            "No numeric thresholds were introduced; 'constructive' reuses existing categorical signals."
        ),
        "window": {"start_date": start_date, "end_date": end_date},
        "total_symbols": len(symbols),
        "symbols_attempted": list(symbols),
        "total_trades_by_mode": totals,
        "per_symbol": per_symbol,
    }
    return payload


def _format_md(payload: dict[str, Any]) -> str:
    """Render payload as Markdown for human review."""
    lines = [
        "# A44 P5 — Multi-Level Resonance Entry Filter Comparison",
        "",
        f"**{payload['disclaimer']}**",
        "",
        f"Generated: {payload['generated_at']}",
        f"Window: {payload['window']['start_date']} ~ {payload['window']['end_date']}",
        "",
        "## Aggregate trade counts",
        "",
        "| Mode | Total trades |",
        "|------|-------------:|",
    ]
    for mode, count in payload["total_trades_by_mode"].items():
        lines.append(f"| {mode} | {count} |")

    lines.extend(["", "## Per-symbol summary", ""])
    lines.append("| Symbol | Mode | Trades | Win rate | PF | Return | Max DD |")
    lines.append("|--------|------|--------|----------|----|--------|--------|")

    for symbol_data in payload["per_symbol"]:
        symbol = symbol_data["symbol"]
        error = symbol_data.get("error")
        if error:
            lines.append(f"| {symbol} | - | - | - | - | error: {error} | - |")
            continue
        for mode in ("off", "daily", "daily_4h"):
            m = symbol_data[mode]
            lines.append(
                f"| {symbol} | {mode} | {m['trade_count']} | "
                f"{m['win_rate']*100:.1f}% | {m['profit_factor']:.2f} | "
                f"{m['total_return_pct']:.2f}% | {m['max_drawdown_pct']:.2f}% |"
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
    """Generate the resonance-filter comparison report."""
    db_path = db_path or Path(SQLITE_DB_PATH)
    stamp = stamp or datetime.now().strftime("%Y-%m-%d")
    payload = _build_payload(db_path, symbols, start_date, end_date, stamp)

    json_path = out_dir / f"resonance_filter_comparison_report_{stamp}.json"
    md_path = out_dir / f"resonance_filter_comparison_report_{stamp}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_format_md(payload))

    print("Resonance filter comparison report written to:")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate A44 P5 resonance filter comparison report."
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
        help="Symbols to include in the comparison.",
    )
    args = parser.parse_args()
    main(
        db_path=args.db_path,
        out_dir=args.out_dir,
        symbols=tuple(args.symbols),
        start_date=args.start_date,
        end_date=args.end_date,
    )
