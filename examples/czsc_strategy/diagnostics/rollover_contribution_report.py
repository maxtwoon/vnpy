"""A73 — Rollover-window return contribution report.

Read-only diagnostic. Runs the default close-model backtest with
``rollover_stat_tagging="on"``, splits closed trades by the
``is_rollover_window`` flag A52 added to ``Position.pairs``, and reports the
separate return contribution, win rate, average P&L, and trade count for
rollover-window trades vs non-rollover-window trades per symbol.

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG  # noqa: E402
from diagnostics.backtest_matrix_report import _dominant_symbol  # noqa: E402
from diagnostics.declassify_historical_reports import build_banner  # noqa: E402


DEFAULT_SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
DEFAULT_START = "2022-01-01"
DEFAULT_END = "2026-04-24"


def _json_safe(value: Any) -> Any:
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


def _fmt_pct(value: float | int | str | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return f"{float(value):.2f}%"


def _fmt_num(value: float | int | str | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def _aggregate_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute total return, win rate, average P&L, and trade count.

    All return figures are expressed in percent points (``pnl_pct * 100``).
    """
    count = len(pairs)
    if count == 0:
        return {
            "trade_count": 0,
            "total_return_pct": 0.0,
            "win_rate": 0.0,
            "avg_pnl_pct": 0.0,
        }

    pnls = [float(p.get("pnl_pct", 0.0)) for p in pairs]
    wins = [p for p in pnls if p > 0]
    return {
        "trade_count": count,
        "total_return_pct": round(sum(pnls) * 100.0, 4),
        "win_rate": round(len(wins) / count, 4),
        "avg_pnl_pct": round(sum(pnls) / count * 100.0, 4),
    }


def _run_symbol(
    db_path: Path,
    symbol: str,
    start: str,
    end: str,
    quiet: bool = True,
) -> dict[str, Any]:
    """Run one symbol backtest with rollover tagging on and return pair groups."""
    table_name = f"{symbol.lower()}_1M_raw"
    try:
        data_symbol = _dominant_symbol(db_path, table_name, start, end)
    except (sqlite3.OperationalError, RuntimeError) as exc:
        return {
            "symbol": symbol,
            "data_symbol": None,
            "table_name": table_name,
            "start_date": start,
            "end_date": end,
            "error": f"dominant_symbol_resolution_failed: {exc}",
            "rollover": _aggregate_pairs([]),
            "non_rollover": _aggregate_pairs([]),
        }

    engine = BacktestEngine(
        symbol=data_symbol,
        db_path=str(db_path),
        table_name=table_name,
        start_date=start,
        end_date=end,
    )
    if quiet:
        with contextlib.redirect_stdout(io.StringIO()):
            report = engine.run()
    else:
        report = engine.run()

    if "error" in report:
        return {
            "symbol": symbol,
            "data_symbol": data_symbol,
            "table_name": table_name,
            "start_date": start,
            "end_date": end,
            "error": str(report["error"]),
            "rollover": _aggregate_pairs([]),
            "non_rollover": _aggregate_pairs([]),
        }

    pairs = engine.strategy.get_combined_trades()
    rollover_pairs = [p for p in pairs if p.get("is_rollover_window") is True]
    non_rollover_pairs = [p for p in pairs if p.get("is_rollover_window") is False]

    return {
        "symbol": symbol,
        "data_symbol": data_symbol,
        "table_name": table_name,
        "start_date": start,
        "end_date": end,
        "total_trades": len(pairs),
        "rollover": _aggregate_pairs(rollover_pairs),
        "non_rollover": _aggregate_pairs(non_rollover_pairs),
    }


def _require_rollover_tagging() -> None:
    """Refuse to run silently if rollover-window tagging is not enabled."""
    if STRATEGY_CONFIG.get("rollover_stat_tagging", "off") != "on":
        raise RuntimeError(
            "rollover_stat_tagging must be set to 'on' before running this report. "
            "Set STRATEGY_CONFIG['rollover_stat_tagging'] = 'on' (this report "
            "intentionally does not silently flip the config to avoid misleading output)."
        )


def run_report(
    db_path: Path,
    symbols: list[str],
    start: str,
    end: str,
    quiet: bool = True,
) -> dict[str, Any]:
    """Run the rollover-window contribution report for the given symbols."""
    _require_rollover_tagging()

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "disclaimer": build_banner().strip(),
        "symbols": {},
    }

    for symbol in symbols:
        payload["symbols"][symbol] = _run_symbol(db_path, symbol, start, end, quiet=quiet)

    return payload


def write_outputs(payload: dict[str, Any], out_dir: Path, stamp: str) -> tuple[Path, Path]:
    """Write JSON and Markdown evidence files."""
    json_path = out_dir / f"rollover_contribution_report_{stamp}.json"
    md_path = out_dir / f"rollover_contribution_report_{stamp}.md"

    json_path.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines: list[str] = [
        "# Rollover-Window Return Contribution Report",
        "",
        f"**Generated at:** {payload['generated_at']}",
        f"**Window:** {payload['start']} ~ {payload['end']}",
        f"**Database:** {payload['db_path']}",
        "",
        f"> {payload['disclaimer']}",
        "",
        "## Method",
        "",
        "- Backtests are run with ``rollover_stat_tagging='on'``.",
        "- Each closed trade in ``Position.pairs`` is split by ``is_rollover_window``.",
        "- Metrics are reported separately for rollover-window and non-rollover-window trades.",
        "- This is a measurement report: no pass/fail threshold is applied.",
        "",
        "## Results by Symbol",
        "",
    ]

    for symbol, data in payload["symbols"].items():
        lines.append(f"### {symbol}")
        lines.append("")
        if data.get("error"):
            lines.append(f"- **Error:** {data['error']}")
            lines.append("")
            continue

        lines.append(f"- **Data symbol:** {data['data_symbol']}")
        lines.append(f"- **Total closed trades:** {data['total_trades']}")
        lines.append("")

        rollover = data["rollover"]
        non_rollover = data["non_rollover"]
        diff_return = rollover["total_return_pct"] - non_rollover["total_return_pct"]

        lines.append("| Group | Trades | Total Return | Win Rate | Avg P&L |")
        lines.append("|-------|-------:|-------------:|---------:|--------:|")
        lines.append(
            f"| Rollover window | {_fmt_num(rollover['trade_count'], digits=0)} | "
            f"{_fmt_pct(rollover['total_return_pct'])} | "
            f"{_fmt_pct(rollover['win_rate'] * 100)} | "
            f"{_fmt_pct(rollover['avg_pnl_pct'])} |"
        )
        lines.append(
            f"| Non-rollover window | {_fmt_num(non_rollover['trade_count'], digits=0)} | "
            f"{_fmt_pct(non_rollover['total_return_pct'])} | "
            f"{_fmt_pct(non_rollover['win_rate'] * 100)} | "
            f"{_fmt_pct(non_rollover['avg_pnl_pct'])} |"
        )
        lines.append(
            f"| Difference | — | {_fmt_pct(diff_return)} | — | — |"
        )
        lines.append("")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main(
    db_path: Path | None = None,
    symbols: tuple[str, ...] = tuple(DEFAULT_SYMBOLS),
    start_date: str = DEFAULT_START,
    end_date: str = DEFAULT_END,
    out_dir: Path | None = None,
    stamp: str | None = None,
    quiet: bool = True,
) -> dict[str, Any]:
    """CLI entry point for the rollover-window contribution report."""
    _require_rollover_tagging()

    db_path = Path(db_path) if db_path else Path(SQLITE_DB_PATH)
    out_dir = Path(out_dir) if out_dir else Path(__file__).resolve().parent
    if stamp is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    payload = run_report(
        db_path=db_path,
        symbols=list(symbols),
        start=start_date,
        end=end_date,
        quiet=quiet,
    )
    write_outputs(payload, out_dir, stamp)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rollover-window return contribution report (A73)."
    )
    parser.add_argument("--db-path", type=Path, default=None, help="Path to SQLite DB")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help="Symbols to include",
    )
    parser.add_argument("--start", default=DEFAULT_START, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=DEFAULT_END, help="End date (YYYY-MM-DD)")
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory")
    parser.add_argument("--stamp", default=None, help="Output filename timestamp")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print backtest progress to stdout",
    )
    args = parser.parse_args()

    payload = main(
        db_path=args.db_path,
        symbols=tuple(args.symbols),
        start_date=args.start,
        end_date=args.end,
        out_dir=args.out_dir,
        stamp=args.stamp,
        quiet=not args.verbose,
    )
    print(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2))
