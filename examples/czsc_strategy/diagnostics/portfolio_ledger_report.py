"""A83 — Read-only portfolio margin/PnL ledger report (Phase 1).

Runs each symbol independently through its own :class:`BacktestEngine` with
``sizing_model="risk"`` (reusing the per-symbol execution pattern of
:class:`PortfolioEngine`), then aggregates the already-produced per-symbol
``total_open_margin`` and closed-trade ``pnl_currency`` into a portfolio-level
read-only ledger.

This is a measurement-only report. It does not gate trades, does not modify
:meth:`PortfolioCoordinator.run`, and does not remove the existing
``NotImplementedError`` for ``sizing_model="risk"`` + ``portfolio_risk="on"``.

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.config import BACKTEST_CONFIG, SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from chan_strategy.portfolio_engine import PortfolioEngine  # noqa: E402
from diagnostics.declassify_historical_reports import build_banner  # noqa: E402


DEFAULT_SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
DEFAULT_START = "2022-01-01"
DEFAULT_END = "2026-04-24"


def _json_safe(value: Any) -> Any:
    """Return a JSON-serializable copy of ``value``."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)
    return value


@contextmanager
def _risk_sizing_config() -> Any:
    """Temporarily set ``sizing_model="risk"`` and restore on exit."""
    saved = STRATEGY_CONFIG.get("sizing_model")
    STRATEGY_CONFIG["sizing_model"] = "risk"
    try:
        yield
    finally:
        if saved is None:
            STRATEGY_CONFIG.pop("sizing_model", None)
        else:
            STRATEGY_CONFIG["sizing_model"] = saved


def _symbol_clusters(
    corr_clusters: dict[str, list[str]], symbols: list[str]
) -> dict[str, list[str]]:
    """Map each symbol to the list of cluster names it belongs to."""
    key_to_clusters: dict[str, list[str]] = {}
    for name, members in corr_clusters.items():
        for member in members:
            key_to_clusters.setdefault(str(member).upper(), []).append(name)
    return {s: key_to_clusters.get(str(s).upper(), []) for s in symbols}


def _run_per_symbol_engines(
    symbols: list[str],
    freq: str = "1",
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float | None = None,
    commission_rate: float | None = None,
    slippage: float | None = None,
    db_path: str | None = None,
    table_names: dict[str, str] | None = None,
    enable_short: bool | None = None,
    quiet: bool = True,
) -> dict[str, dict[str, Any]]:
    """Run an independent risk-sized backtest for every symbol.

    Reuses :meth:`PortfolioEngine._run_per_symbol` but guarantees
    ``STRATEGY_CONFIG["sizing_model"] == "risk"`` for the duration of the run
    and restores the previous value afterwards.
    """
    engine = PortfolioEngine(
        symbols=symbols,
        freq=freq,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        slippage=slippage,
        db_path=db_path,
        table_names=table_names or {},
        enable_short=enable_short,
    )
    with _risk_sizing_config():
        if quiet:
            with contextlib.redirect_stdout(io.StringIO()):
                symbol_results = engine._run_per_symbol()
        else:
            symbol_results = engine._run_per_symbol()
    return symbol_results


def _build_ledger(
    symbol_results: dict[str, dict[str, Any]],
    initial_capital: float,
    corr_clusters: dict[str, list[str]],
) -> dict[str, Any]:
    """Aggregate independently-run per-symbol results into a portfolio ledger.

    The aggregation is read-only and timestamp-aligned using the union of all
    per-symbol equity-curve timestamps. Per-symbol margins are forward-filled
    within each symbol's own data range before summation so that open positions
    are not dropped at bars where another symbol happens to have a timestamp.
    """
    symbols = list(symbol_results.keys())
    cluster_map = _symbol_clusters(corr_clusters, symbols)

    per_symbol: dict[str, Any] = {}
    symbol_margin_series: dict[str, pd.Series] = {}
    symbol_realized_pnl: dict[str, float] = {}
    symbol_errors: dict[str, str] = {}

    for symbol, sr in symbol_results.items():
        report = sr.get("report", {})
        if "error" in report:
            symbol_errors[symbol] = str(report["error"])
            per_symbol[symbol] = {
                "error": str(report["error"]),
                "total_realized_pnl_currency": 0.0,
                "max_total_open_margin": 0.0,
                "final_total_open_margin": 0.0,
                "trade_count": 0,
            }
            continue

        engine = sr["engine"]
        curve = engine.equity_curve
        trades = engine.strategy.get_combined_trades()

        realized = sum(float(t.get("pnl_currency", 0.0)) for t in trades)
        symbol_realized_pnl[symbol] = realized

        if curve:
            index = [e["dt"] for e in curve]
            margins = [float(e.get("total_open_margin", 0.0)) for e in curve]
            series = pd.Series(margins, index=index, name=symbol)
            symbol_margin_series[symbol] = series
            max_margin = float(series.max()) if not series.empty else 0.0
            final_margin = float(series.iloc[-1]) if not series.empty else 0.0
        else:
            max_margin = 0.0
            final_margin = 0.0

        per_symbol[symbol] = {
            "total_realized_pnl_currency": realized,
            "max_total_open_margin": max_margin,
            "final_total_open_margin": final_margin,
            "trade_count": len(trades),
        }

    valid_symbols = [s for s in symbols if "error" not in per_symbol[s]]

    ledger_rows: list[dict[str, Any]] = []
    if symbol_margin_series:
        df = pd.concat(symbol_margin_series.values(), axis=1).sort_index()
        df = df.ffill().fillna(0.0)
        portfolio_margin = df.sum(axis=1)
        for dt, total_margin in portfolio_margin.items():
            margin_util = total_margin / initial_capital if initial_capital > 0 else 0.0
            ledger_rows.append(
                {
                    "dt": dt.isoformat(sep=" "),
                    "total_open_margin": float(total_margin),
                    "margin_utilization_pct": float(margin_util),
                }
            )
    else:
        portfolio_margin = pd.Series(dtype=float)

    total_realized_pnl = sum(symbol_realized_pnl.values())
    max_total_open_margin = (
        float(portfolio_margin.max()) if not portfolio_margin.empty else 0.0
    )
    final_total_open_margin = (
        float(portfolio_margin.iloc[-1]) if not portfolio_margin.empty else 0.0
    )
    max_margin_utilization_pct = (
        max_total_open_margin / initial_capital if initial_capital > 0 else 0.0
    )

    per_cluster: dict[str, Any] = {}
    for cluster_name, members in corr_clusters.items():
        member_symbols = [s for s in valid_symbols if s in members]
        if not member_symbols:
            per_cluster[cluster_name] = {
                "symbols": [],
                "max_total_open_margin": 0.0,
                "final_total_open_margin": 0.0,
            }
            continue
        if symbol_margin_series:
            cluster_df = df[member_symbols]
            cluster_margin = cluster_df.sum(axis=1)
            per_cluster[cluster_name] = {
                "symbols": member_symbols,
                "max_total_open_margin": float(cluster_margin.max()),
                "final_total_open_margin": float(cluster_margin.iloc[-1]),
            }
        else:
            per_cluster[cluster_name] = {
                "symbols": member_symbols,
                "max_total_open_margin": 0.0,
                "final_total_open_margin": 0.0,
            }

    uncategorized = [s for s in valid_symbols if not cluster_map.get(s)]
    if uncategorized:
        if symbol_margin_series:
            uncategorized_df = df[uncategorized]
            uncategorized_margin = uncategorized_df.sum(axis=1)
            per_cluster["_uncategorized"] = {
                "symbols": uncategorized,
                "max_total_open_margin": float(uncategorized_margin.max()),
                "final_total_open_margin": float(uncategorized_margin.iloc[-1]),
            }
        else:
            per_cluster["_uncategorized"] = {
                "symbols": uncategorized,
                "max_total_open_margin": 0.0,
                "final_total_open_margin": 0.0,
            }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": build_banner().strip(),
        "initial_capital": float(initial_capital),
        "symbols": symbols,
        "corr_clusters": {k: list(v) for k, v in corr_clusters.items()},
        "symbol_errors": symbol_errors,
        "portfolio_summary": {
            "total_realized_pnl_currency": total_realized_pnl,
            "max_total_open_margin": max_total_open_margin,
            "final_total_open_margin": final_total_open_margin,
            "max_margin_utilization_pct": max_margin_utilization_pct,
        },
        "per_symbol": per_symbol,
        "per_cluster": per_cluster,
        "ledger": ledger_rows,
        "methodology": {
            "sizing_model": "risk",
            "aggregation": "independent_per_symbol",
            "note": (
                "This report is a measurement-only aggregation of independently-run "
                "per-symbol backtests with sizing_model='risk'. It is NOT a true joint "
                "or coordinated portfolio replay; each symbol was run against the full "
                "initial capital in isolation. Phase 2 will build a shared-ledger "
                "coordinated replay."
            ),
        },
    }


def run_report(
    symbols: list[str],
    freq: str = "1",
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float | None = None,
    commission_rate: float | None = None,
    slippage: float | None = None,
    db_path: str | None = None,
    table_names: dict[str, str] | None = None,
    enable_short: bool | None = None,
    quiet: bool = True,
) -> dict[str, Any]:
    """Run the read-only portfolio ledger report for the given symbols."""
    symbol_results = _run_per_symbol_engines(
        symbols=symbols,
        freq=freq,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        slippage=slippage,
        db_path=db_path,
        table_names=table_names,
        enable_short=enable_short,
        quiet=quiet,
    )

    initial_capital = (
        initial_capital
        if initial_capital is not None
        else BACKTEST_CONFIG["initial_capital"]
    )
    corr_clusters = dict(STRATEGY_CONFIG.get("corr_clusters") or {})

    payload = _build_ledger(symbol_results, initial_capital, corr_clusters)
    payload["start_date"] = start_date or BACKTEST_CONFIG["start_date"]
    payload["end_date"] = end_date or BACKTEST_CONFIG["end_date"]
    payload["freq"] = freq
    return payload


def write_outputs(payload: dict[str, Any], out_dir: Path, stamp: str) -> tuple[Path, Path]:
    """Write JSON and Markdown evidence files."""
    json_path = out_dir / f"portfolio_ledger_report_{stamp}.json"
    md_path = out_dir / f"portfolio_ledger_report_{stamp}.md"

    json_path.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = payload["portfolio_summary"]
    lines: list[str] = [
        "# Portfolio Margin/PnL Ledger Report (Phase 1)",
        "",
        f"**Generated at:** {payload['generated_at']}",
        f"**Window:** {payload['start_date']} ~ {payload['end_date']}",
        f"**Symbols:** {', '.join(payload['symbols'])}",
        f"**Initial capital:** {payload['initial_capital']:,.2f}",
        "",
        f"> {payload['disclaimer']}",
        "",
        "## Methodology",
        "",
        "- Each symbol is run independently through its own ``BacktestEngine`` with "
        "``sizing_model='risk'``.",
        "- Portfolio-level figures are aggregated by timestamp across the per-symbol "
        "``equity_curve`` entries.",
        "- Realized currency PnL is the sum of closed-trade ``pnl_currency`` values "
        "from ``strategy.get_combined_trades()``.",
        "- Cluster breakdowns reuse ``STRATEGY_CONFIG['corr_clusters']``; no new "
        "clustering mechanism is introduced.",
        "- **This is a measurement-only aggregation of independent per-symbol runs, "
        "NOT a true joint/coordinated portfolio replay.**",
        "",
        "## Portfolio Summary",
        "",
        f"- **Total realized currency PnL:** {summary['total_realized_pnl_currency']:,.2f}",
        f"- **Max portfolio total open margin:** {summary['max_total_open_margin']:,.2f}",
        f"- **Final portfolio total open margin:** {summary['final_total_open_margin']:,.2f}",
        (
            "- **Max margin utilization:** "
            f"{summary['max_margin_utilization_pct'] * 100:.2f}%"
        ),
        "",
        "## Per-Symbol Breakdown",
        "",
        "| Symbol | Trades | Realized PnL | Max Margin | Final Margin |",
        "|--------|-------:|-------------:|-----------:|-------------:|",
    ]

    for symbol, data in payload["per_symbol"].items():
        if "error" in data:
            lines.append(
                f"| {symbol} | — | ERROR: {data['error']} | — | — |"
            )
        else:
            lines.append(
                f"| {symbol} | {data['trade_count']:,} | "
                f"{data['total_realized_pnl_currency']:,.2f} | "
                f"{data['max_total_open_margin']:,.2f} | "
                f"{data['final_total_open_margin']:,.2f} |"
            )
    lines.append("")

    lines.extend(
        [
            "## Per-Cluster Breakdown",
            "",
            "| Cluster | Symbols | Max Margin | Final Margin |",
            "|---------|---------|-----------:|-------------:|",
        ]
    )
    for cluster_name, data in payload["per_cluster"].items():
        symbols_str = ", ".join(data["symbols"]) if data["symbols"] else "—"
        lines.append(
            f"| {cluster_name} | {symbols_str} | "
            f"{data['max_total_open_margin']:,.2f} | "
            f"{data['final_total_open_margin']:,.2f} |"
        )
    lines.append("")

    lines.extend(
        [
            "## Ledger Sample",
            "",
            f"The full timestamp-level ledger contains {len(payload['ledger'])} rows. "
            "The first and last rows are shown below.",
            "",
            "| Timestamp | Total Open Margin | Margin Utilization |",
            "|-----------|------------------:|-------------------:|",
        ]
    )
    if payload["ledger"]:
        first = payload["ledger"][0]
        last = payload["ledger"][-1]
        lines.append(
            f"| {first['dt']} | {first['total_open_margin']:,.2f} | "
            f"{first['margin_utilization_pct'] * 100:.2f}% |"
        )
        lines.append(
            f"| {last['dt']} | {last['total_open_margin']:,.2f} | "
            f"{last['margin_utilization_pct'] * 100:.2f}% |"
        )
    else:
        lines.append("| — | — | — |")
    lines.append("")

    lines.extend(
        [
            "## Manual Verification",
            "",
            "Run the report natively and inspect the generated JSON/Markdown files:",
            "",
            "```bash",
            "python diagnostics/portfolio_ledger_report.py --verbose",
            "```",
            "",
            "Counts from a native run (to be filled after execution):",
            "",
            "- Symbols run: __",
            "- Portfolio ledger rows: __",
            "- Total realized currency PnL: __",
            "- Max margin utilization (%): __",
            "",
        ]
    )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main(
    symbols: tuple[str, ...] = tuple(DEFAULT_SYMBOLS),
    freq: str = "1",
    start_date: str = DEFAULT_START,
    end_date: str = DEFAULT_END,
    initial_capital: float | None = None,
    commission_rate: float | None = None,
    slippage: float | None = None,
    db_path: Path | None = None,
    out_dir: Path | None = None,
    stamp: str | None = None,
    quiet: bool = True,
) -> dict[str, Any]:
    """CLI entry point for the portfolio ledger report."""
    db_path = Path(db_path) if db_path else Path(SQLITE_DB_PATH)
    out_dir = Path(out_dir) if out_dir else Path(__file__).resolve().parent
    if stamp is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    payload = run_report(
        symbols=list(symbols),
        freq=freq,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        slippage=slippage,
        db_path=str(db_path),
        quiet=quiet,
    )
    write_outputs(payload, out_dir, stamp)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Portfolio margin/PnL ledger report (A83 Phase 1)."
    )
    parser.add_argument("--db-path", type=Path, default=None, help="Path to SQLite DB")
    parser.add_argument(
        "--symbols", nargs="+", default=DEFAULT_SYMBOLS, help="Symbols to include"
    )
    parser.add_argument("--freq", default="1", help="Bar frequency identifier")
    parser.add_argument("--start", default=DEFAULT_START, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=DEFAULT_END, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--initial-capital", type=float, default=None, help="Initial capital per symbol"
    )
    parser.add_argument(
        "--commission-rate", type=float, default=None, help="Commission rate"
    )
    parser.add_argument("--slippage", type=float, default=None, help="Slippage")
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory")
    parser.add_argument("--stamp", default=None, help="Output filename timestamp")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print backtest progress to stdout",
    )
    args = parser.parse_args()

    payload = main(
        symbols=tuple(args.symbols),
        freq=args.freq,
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.initial_capital,
        commission_rate=args.commission_rate,
        slippage=args.slippage,
        db_path=args.db_path,
        out_dir=args.out_dir,
        stamp=args.stamp,
        quiet=not args.verbose,
    )
    print(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2))
