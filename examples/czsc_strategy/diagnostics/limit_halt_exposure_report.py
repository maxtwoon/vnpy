"""A50 — Limit-Up/Down/Halt Impact Diagnostic (Read-Only).

Read-only report measuring how many baseline replay trades have their
entry-fill bar or exit-fill bar at or beyond each symbol's daily
price-limit band.  The report reuses ``BacktestEngine``'s existing
combined-trades output and does not change any fill logic in
``backtest_engine.py``, ``positions.py`` or ``data_adapter.py``.

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Make the czsc_strategy package importable from this diagnostics script
_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from chan_strategy.config import SQLITE_DB_PATH  # noqa: E402
from chan_strategy.limit_config import (  # noqa: E402
    SYMBOL_LIMIT_CONFIG,
    _bar_at_limit,
    _bar_date,
    _daily_prev_close_map,
)


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE
BANNER = "RESEARCH-ONLY — Diagnostic only, not a trading recommendation."
SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
WINDOW_START = "2026-04-24"
WINDOW_END = "2026-07-09"



@dataclass
class TradeLimitDiag:
    """Per-trade limit/halt diagnostic record."""

    open_dt: str
    close_dt: str
    direction: str
    entry_date: str
    exit_date: str
    entry_at_limit: bool
    exit_at_limit: bool
    entry_band_available: bool
    exit_band_available: bool
    entry_upper_limit: float | None
    entry_lower_limit: float | None
    exit_upper_limit: float | None
    exit_lower_limit: float | None
    entry_prev_close: float | None
    exit_prev_close: float | None
    zero_volume_near_entry: bool | str
    zero_volume_near_exit: bool | str


def _direction_from_strategy(strategy: str) -> str:
    return "short" if "空头" in strategy else "long"


def _index_for_dt(trade_bars: list[Any], dt: Any) -> int | None:
    """Find the trade bar index whose timestamp exactly matches ``dt``."""
    for i, bar in enumerate(trade_bars):
        if bar.dt == dt:
            return i
    return None


def _zero_volume_near(trade_bars: list[Any], idx: int | None) -> bool | str:
    """Best-effort flag: is any adjacent bar (including idx) zero-volume?

    Returns ``True``/``False`` when a volume column exists, otherwise
    ``"unavailable"``.
    """
    if idx is None or not trade_bars or idx < 0 or idx >= len(trade_bars):
        return False

    if not hasattr(trade_bars[idx], "vol"):
        return "unavailable"

    for j in (idx - 1, idx, idx + 1):
        if 0 <= j < len(trade_bars):
            vol = getattr(trade_bars[j], "vol", None)
            if vol is None:
                return "unavailable"
            if float(vol) == 0.0:
                return True
    return False


def _format_dt(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def _compute_trade_diagnostics(
    pairs: list[dict[str, Any]],
    trade_bars: list[Any],
    raw_bars: list[Any],
    limit_pct: float,
) -> list[TradeLimitDiag]:
    """Compute daily-limit and zero-volume diagnostics for every closed pair."""
    diagnostics: list[TradeLimitDiag] = []
    if not trade_bars or not raw_bars:
        return diagnostics

    prev_close_map = _daily_prev_close_map(raw_bars)

    for pair in pairs:
        open_dt = pair.get("open_dt")
        close_dt = pair.get("close_dt")
        if open_dt is None or close_dt is None:
            continue

        entry_idx = _index_for_dt(trade_bars, open_dt)
        exit_idx = _index_for_dt(trade_bars, close_dt)
        entry_bar = trade_bars[entry_idx] if entry_idx is not None else None
        exit_bar = trade_bars[exit_idx] if exit_idx is not None else None

        entry_date = _bar_date(entry_bar) if entry_bar else _bar_date(trade_bars[0])
        exit_date = _bar_date(exit_bar) if exit_bar else entry_date

        entry_prev_close, _ = prev_close_map.get(entry_date, (None, None))
        exit_prev_close, _ = prev_close_map.get(exit_date, (None, None))

        entry_at_limit, entry_upper, entry_lower = (
            _bar_at_limit(entry_bar, entry_prev_close, limit_pct)
            if entry_bar
            else (False, None, None)
        )
        exit_at_limit, exit_upper, exit_lower = (
            _bar_at_limit(exit_bar, exit_prev_close, limit_pct)
            if exit_bar
            else (False, None, None)
        )

        zero_vol_entry = _zero_volume_near(trade_bars, entry_idx)
        zero_vol_exit = _zero_volume_near(trade_bars, exit_idx)

        diagnostics.append(
            TradeLimitDiag(
                open_dt=_format_dt(open_dt),
                close_dt=_format_dt(close_dt),
                direction=_direction_from_strategy(pair.get("strategy", "")),
                entry_date=str(entry_date),
                exit_date=str(exit_date),
                entry_at_limit=entry_at_limit,
                exit_at_limit=exit_at_limit,
                entry_band_available=entry_prev_close is not None,
                exit_band_available=exit_prev_close is not None,
                entry_upper_limit=entry_upper,
                entry_lower_limit=entry_lower,
                exit_upper_limit=exit_upper,
                exit_lower_limit=exit_lower,
                entry_prev_close=entry_prev_close,
                exit_prev_close=exit_prev_close,
                zero_volume_near_entry=zero_vol_entry,
                zero_volume_near_exit=zero_vol_exit,
            )
        )

    return diagnostics


def _empty_metrics() -> dict[str, Any]:
    return {
        "trade_count": 0,
        "entry_at_limit_count": 0,
        "entry_not_at_limit_count": 0,
        "exit_at_limit_count": 0,
        "exit_not_at_limit_count": 0,
        "entry_at_limit_pct": 0.0,
        "exit_at_limit_pct": 0.0,
        "limit_band_unavailable_count": 0,
        "zero_volume_proxy_available": False,
        "trades_with_zero_volume_near_entry": 0,
        "trades_with_zero_volume_near_exit": 0,
        "trades": [],
    }


def _overall_metrics(
    report: dict[str, Any],
    pairs: list[dict[str, Any]],
    trade_bars: list[Any],
    raw_bars: list[Any],
    limit_pct: float,
) -> dict[str, Any]:
    """Extract per-symbol metrics and per-trade diagnostics."""
    diagnostics = _compute_trade_diagnostics(pairs, trade_bars, raw_bars, limit_pct)

    trade_count = report.get("total_trades", len(pairs))
    entry_at = sum(1 for d in diagnostics if d.entry_at_limit)
    exit_at = sum(1 for d in diagnostics if d.exit_at_limit)
    unavailable = sum(
        1 for d in diagnostics if not d.entry_band_available or not d.exit_band_available
    )

    zero_vol_available = any(isinstance(d.zero_volume_near_entry, bool) for d in diagnostics)
    zero_vol_entry = sum(
        1 for d in diagnostics if d.zero_volume_near_entry is True
    )
    zero_vol_exit = sum(
        1 for d in diagnostics if d.zero_volume_near_exit is True
    )

    return {
        "trade_count": trade_count,
        "entry_at_limit_count": entry_at,
        "entry_not_at_limit_count": trade_count - entry_at,
        "exit_at_limit_count": exit_at,
        "exit_not_at_limit_count": trade_count - exit_at,
        "entry_at_limit_pct": entry_at / trade_count if trade_count else 0.0,
        "exit_at_limit_pct": exit_at / trade_count if trade_count else 0.0,
        "limit_band_unavailable_count": unavailable,
        "zero_volume_proxy_available": zero_vol_available,
        "trades_with_zero_volume_near_entry": zero_vol_entry,
        "trades_with_zero_volume_near_exit": zero_vol_exit,
        "trades": [d.__dict__ for d in diagnostics],
    }


def _run_backtest(
    symbol: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[Any], list[Any]]:
    """Run a single-symbol baseline replay and return report + raw artifacts."""
    engine = BacktestEngine(
        symbol=symbol,
        freq="1",
        start_date=start_date,
        end_date=end_date,
        db_path=str(db_path),
        table_name=f"{symbol.lower()}_1M_raw",
    )
    report = engine.run()
    pairs = engine.strategy.get_combined_trades() if engine.strategy else []
    return report, pairs, getattr(engine, "trade_bars", []), getattr(engine, "bars", [])


def _run_symbol(
    symbol: str,
    db_path: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Compute limit-exposure metrics for one symbol on the baseline replay."""
    limit_cfg = SYMBOL_LIMIT_CONFIG.get(symbol, {})
    result: dict[str, Any] = {
        "symbol": symbol,
        "limit_pct": limit_cfg.get("limit_pct"),
        "limit_source": limit_cfg.get("source"),
        "limit_note": (
            "First-cut steady-state contract percentage. "
            "Exchange notices may temporarily widen limits for specific contracts or after limit-hit days; "
            "those exceptions are not applied here."
        ),
        "error": None,
        "metrics": None,
    }

    if not db_path.exists():
        result["error"] = "database_not_found"
        result["metrics"] = _empty_metrics()
        return result

    try:
        report, pairs, trade_bars, raw_bars = _run_backtest(
            symbol, db_path, start_date, end_date
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        result["error"] = f"backtest_failed: {exc}"
        result["metrics"] = _empty_metrics()
        return result

    if "error" in report:
        result["error"] = report["error"]
        result["metrics"] = _empty_metrics()
        return result

    limit_pct = limit_cfg.get("limit_pct")
    if limit_pct is None:
        result["error"] = "limit_percentage_unavailable"
        result["metrics"] = _empty_metrics()
        return result

    result["metrics"] = _overall_metrics(
        report, pairs, trade_bars, raw_bars, limit_pct
    )
    return result


def _build_payload(
    db_path: Path,
    symbols: tuple[str, ...],
    start_date: str,
    end_date: str,
    stamp: str,
) -> dict[str, Any]:
    """Build the full report payload."""
    per_symbol = [_run_symbol(symbol, db_path, start_date, end_date) for symbol in symbols]

    totals = {
        "trade_count": 0,
        "entry_at_limit_count": 0,
        "entry_not_at_limit_count": 0,
        "exit_at_limit_count": 0,
        "exit_not_at_limit_count": 0,
        "trades_with_zero_volume_near_entry": 0,
        "trades_with_zero_volume_near_exit": 0,
    }
    for item in per_symbol:
        m = item.get("metrics")
        if not m:
            continue
        totals["trade_count"] += m.get("trade_count", 0)
        totals["entry_at_limit_count"] += m.get("entry_at_limit_count", 0)
        totals["entry_not_at_limit_count"] += m.get("entry_not_at_limit_count", 0)
        totals["exit_at_limit_count"] += m.get("exit_at_limit_count", 0)
        totals["exit_not_at_limit_count"] += m.get("exit_not_at_limit_count", 0)
        totals["trades_with_zero_volume_near_entry"] += m.get(
            "trades_with_zero_volume_near_entry", 0
        )
        totals["trades_with_zero_volume_near_exit"] += m.get(
            "trades_with_zero_volume_near_exit", 0
        )

    payload = {
        "disclaimer": BANNER,
        "generated_at": datetime.now().isoformat(),
        "window": {"start_date": start_date, "end_date": end_date},
        "total_symbols": len(symbols),
        "symbols_attempted": list(symbols),
        "note": (
            "This report is read-only evidence.  It uses the exchange-published "
            "steady-state daily price-limit percentage per symbol and the previous "
            "trading day's last close observed in the loaded window.  It does not "
            "change BacktestEngine/PortfolioEngine fill logic, does not enforce any "
            "limit/halt constraint, and is not used to tune parameters.  "
            "For per-trade tagging, set ``limit_halt_model='aware'`` in "
            "``chan_strategy.config.STRATEGY_CONFIG``; trades will still open/close "
            "at unchanged prices and only gain ``is_entry_at_limit``/"
            "``is_exit_at_limit`` boolean fields."
        ),
        "totals": totals,
        "per_symbol": per_symbol,
    }
    return payload


def _format_md(payload: dict[str, Any]) -> str:
    """Render the payload as Markdown for human review."""
    lines = [
        "# A50 — Limit-Up/Down/Halt Impact Diagnostic",
        "",
        f"> {payload['disclaimer']}",
        "",
        f"Generated: {payload['generated_at']}",
        f"Window: {payload['window']['start_date']} ~ {payload['window']['end_date']}",
        "",
        "## Totals",
        "",
        "| Metric | Count |",
        "|--------|------:|",
        f"| Total trades | {payload['totals']['trade_count']} |",
        f"| Entry-fill at/beyond limit | {payload['totals']['entry_at_limit_count']} |",
        f"| Entry-fill not at limit | {payload['totals']['entry_not_at_limit_count']} |",
        f"| Exit-fill at/beyond limit | {payload['totals']['exit_at_limit_count']} |",
        f"| Exit-fill not at limit | {payload['totals']['exit_not_at_limit_count']} |",
        f"| Zero-volume near entry | {payload['totals']['trades_with_zero_volume_near_entry']} |",
        f"| Zero-volume near exit | {payload['totals']['trades_with_zero_volume_near_exit']} |",
        "",
        "## Per-Symbol Summary",
        "",
        "| Symbol | Limit % | Trades | Entry @ limit | Exit @ limit | Z-Vol near entry | Z-Vol near exit | Error |",
        "|--------|--------:|-------:|--------------:|-------------:|-----------------:|----------------:|-------|",
    ]

    for item in payload["per_symbol"]:
        symbol = item["symbol"]
        limit_pct = item.get("limit_pct")
        limit_pct_str = f"{limit_pct*100:.1f}%" if limit_pct is not None else "n/a"
        error = item.get("error") or "-"
        m = item.get("metrics")
        if m:
            lines.append(
                f"| {symbol} | {limit_pct_str} | "
                f"{m['trade_count']} | "
                f"{m['entry_at_limit_count']} ({m['entry_at_limit_pct']*100:.1f}%) | "
                f"{m['exit_at_limit_count']} ({m['exit_at_limit_pct']*100:.1f}%) | "
                f"{m['trades_with_zero_volume_near_entry']} | "
                f"{m['trades_with_zero_volume_near_exit']} | {error} |"
            )
        else:
            lines.append(
                f"| {symbol} | {limit_pct_str} | - | - | - | - | - | {error} |"
            )

    lines.extend(["", "## Sources", ""])
    for item in payload["per_symbol"]:
        symbol = item["symbol"]
        source = item.get("limit_source") or "unavailable"
        lines.append(f"- **{symbol}**: {source}")

    lines.extend([
        "",
        "## Methodology",
        "",
        payload["note"],
        "",
        "A trade is flagged 'at limit' on the entry/exit side when the fill bar's "
        "high or low touches or exceeds the computed daily price-limit band. "
        "The band is derived from the previous trading day's last close observed "
        "in the loaded window and the symbol's steady-state exchange limit percentage. "
        "Zero-volume bars within one bar of the fill bar are reported as a secondary "
        "halted/no-liquidity proxy when the raw table exposes a volume column.",
        "",
    ])
    return "\n".join(lines)


def main(
    db_path: Path | None = None,
    out_dir: Path = DEFAULT_OUT_DIR,
    symbols: tuple[str, ...] = (),
    start_date: str = WINDOW_START,
    end_date: str = WINDOW_END,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Generate the limit-up/down/halt exposure diagnostic report."""
    db_path = db_path or Path(SQLITE_DB_PATH)
    symbols = symbols or tuple(SYMBOLS)
    stamp = stamp or datetime.now().strftime("%Y-%m-%d")

    payload = _build_payload(db_path, symbols, start_date, end_date, stamp)

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"limit_halt_exposure_report_{stamp}.json"
    md_path = out_dir / f"limit_halt_exposure_report_{stamp}.md"

    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_format_md(payload), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(BANNER)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate A50 limit-up/down/halt exposure diagnostic report."
    )
    parser.add_argument(
        "--db-path", type=Path, default=None, help="Path to the SQLite kline database."
    )
    parser.add_argument(
        "--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Directory for report files."
    )
    parser.add_argument(
        "--symbols", nargs="+", default=None, help="Symbols to include."
    )
    parser.add_argument(
        "--start-date", type=str, default=WINDOW_START, help="Window start (YYYY-MM-DD)."
    )
    parser.add_argument(
        "--end-date", type=str, default=WINDOW_END, help="Window end (YYYY-MM-DD)."
    )
    parser.add_argument(
        "--stamp", type=str, default=None, help="Filename stamp (default today)."
    )
    args = parser.parse_args()

    main(
        db_path=args.db_path,
        out_dir=args.out_dir,
        symbols=tuple(args.symbols) if args.symbols else (),
        start_date=args.start_date,
        end_date=args.end_date,
        stamp=args.stamp,
    )
