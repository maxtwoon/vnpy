"""A39 Phase 0 — Rollover-pollution exclusion diagnostic.

Read-only. Detects 888 continuous-contract rollover dates from the raw table's
``real_symbol`` column, runs the close-model baseline backtest, and reports the
before/after impact of excluding trades whose open or close falls within
``transition_date ± 1 trading day``.

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Make the czsc_strategy package importable from this diagnostics script
_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import BACKTEST_CONFIG, SQLITE_DB_PATH, STRATEGY_CONFIG

# Reuse the A35/A38 stop-loss overshoot definition.
from diagnostics.audit_issue_diagnostics import analyze_stop_loss_overshoot


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE
BANNER = "RESEARCH-ONLY — Diagnostic only, not a trading recommendation."
SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
WINDOW_START = "2026-04-24"
WINDOW_END = "2026-07-09"


def _find_real_symbol_column(cur: sqlite3.Cursor, table: str) -> str | None:
    """Return the exact column name if the table has a real-symbol-like column."""
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1].lower(): row[1] for row in cur.fetchall()}
    for cand in ("real_symbol", "source_symbol"):
        if cand in columns:
            return columns[cand]
    return None


def _detect_transitions(
    db_path: Path,
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Detect rollover transitions from the raw table's real_symbol column."""
    table = f"{symbol.lower()}_1M_raw"
    result: dict[str, Any] = {
        "symbol": symbol,
        "table": table,
        "detection_method": "real_symbol",
        "transition_dates": [],
        "unavailable": None,
    }

    if not db_path.exists():
        result["unavailable"] = "database_not_found"
        return result

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        if table not in tables:
            result["unavailable"] = f"table_not_found: {table}"
            return result

        real_symbol_col = _find_real_symbol_column(cur, table)
        if real_symbol_col is None:
            result["detection_method"] = "price_gap_fallback_unimplemented"
            result["unavailable"] = "no_real_symbol_column"
            return result

        params: list[Any] = [symbol]
        where_clauses = [f"symbol = ?"]
        if start_date:
            where_clauses.append("datetime >= ?")
            params.append(str(start_date))
        if end_date:
            where_clauses.append("datetime <= ?")
            params.append(f"{end_date} 23:59:59")
        where = " AND ".join(where_clauses)

        where = where.replace("symbol = ?", "symbol = ? COLLATE NOCASE")
        cur.execute(
            f"SELECT MIN(datetime) AS first_dt, {real_symbol_col} "
            f"FROM {table} WHERE {where} GROUP BY {real_symbol_col} "
            f"ORDER BY first_dt",
            tuple(params),
        )
        rows = cur.fetchall()
        if len(rows) <= 1:
            # Single contract in window — no rollovers to report.
            result["transition_dates"] = []
            return result

        prev_contract = None
        for first_dt_str, contract in rows:
            if contract is None:
                continue
            if prev_contract is None:
                prev_contract = contract
                continue
            transition_dt = _parse_dt(str(first_dt_str))
            if transition_dt is None:
                continue
            result["transition_dates"].append({
                "date": transition_dt.date().isoformat(),
                "datetime": transition_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "from_contract": prev_contract,
                "to_contract": contract,
            })
            prev_contract = contract

        return result
    finally:
        conn.close()


def _parse_dt(value: str) -> datetime | None:
    """Parse a datetime string from the database."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _trading_dates_from_bars(db_path: Path, symbol: str) -> set[date]:
    """Return all calendar dates with at least one bar for the symbol.

    Previously this filtered to day-session hours only, which produced sparse
    trading-date sets for futures with night sessions and caused non-adjacent
    dates to be picked as the ``transition ± 1 trading day`` exclusion window.
    """
    table = f"{symbol.lower()}_1M_raw"
    trading_dates: set[date] = set()
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT DISTINCT DATE(datetime) FROM {table} WHERE symbol = ? COLLATE NOCASE",
            (symbol,),
        )
        for row in cur.fetchall():
            try:
                trading_dates.add(date.fromisoformat(row[0]))
            except ValueError:
                continue
        return trading_dates
    finally:
        conn.close()


def _exclusion_dates(
    transition_dates: list[dict[str, Any]], trading_dates: set[date]
) -> tuple[set[date], list[dict[str, Any]]]:
    """Expand each transition date to {prev, transition, next} actual adjacent trading dates.

    Only immediately adjacent observed trading dates are used.  If the adjacent
    date is missing from the diagnostic data (gap larger than a normal holiday
    window), the corresponding side is marked unavailable instead of picking a
    non-adjacent date months away.
    """
    excluded: set[date] = set()
    notes: list[dict[str, Any]] = []
    sorted_trading = sorted(trading_dates)
    # Normal futures holiday windows are <= 7 calendar days; anything larger is
    # treated as missing data rather than an actual adjacent trading date.
    max_gap_days = 7

    for tr in transition_dates:
        tr_date = date.fromisoformat(str(tr["date"]))
        tr_notes: dict[str, Any] = {
            "date": tr_date.isoformat(),
            "prev": None,
            "next": None,
        }

        idx = bisect.bisect_left(sorted_trading, tr_date)
        if idx < len(sorted_trading) and sorted_trading[idx] == tr_date:
            # Transition date itself is an observed trading date.
            excluded.add(tr_date)
            # Previous trading date
            if idx > 0 and (tr_date - sorted_trading[idx - 1]).days <= max_gap_days:
                excluded.add(sorted_trading[idx - 1])
            else:
                tr_notes["prev"] = "absent_from_diagnostic_window"
            # Next trading date
            if idx < len(sorted_trading) - 1 and (sorted_trading[idx + 1] - tr_date).days <= max_gap_days:
                excluded.add(sorted_trading[idx + 1])
            else:
                tr_notes["next"] = "absent_from_diagnostic_window"
        else:
            # Transition date is not an observed trading date; bracket it with
            # the nearest observed dates when they are close enough.
            if idx > 0 and (tr_date - sorted_trading[idx - 1]).days <= max_gap_days:
                excluded.add(sorted_trading[idx - 1])
            else:
                tr_notes["prev"] = "absent_from_diagnostic_window"
            if idx < len(sorted_trading) and (sorted_trading[idx] - tr_date).days <= max_gap_days:
                excluded.add(sorted_trading[idx])
            else:
                tr_notes["next"] = "absent_from_diagnostic_window"

        notes.append(tr_notes)

    return excluded, notes


def _pair_in_exclusion_window(
    pair: dict[str, Any],
    excluded_dates: set[date],
) -> bool:
    """True if the pair's open or close date falls in the exclusion window."""
    open_dt = pair.get("open_dt")
    close_dt = pair.get("close_dt")
    for dt in (open_dt, close_dt):
        if dt is None:
            continue
        if isinstance(dt, str):
            dt = _parse_dt(dt)
        if dt is None:
            continue
        if dt.date() in excluded_dates:
            return True
    return False


def _max_drawdown_from_pnls(pnls: list[float]) -> float:
    """Compute max drawdown (in percent points) from a sequence of trade pnl fractions."""
    if not pnls:
        return 0.0
    cumulative = [0.0]
    for p in pnls:
        cumulative.append(cumulative[-1] + p)
    peak = cumulative[0]
    max_dd = 0.0
    for eq in cumulative:
        peak = max(peak, eq)
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100.0


def _metrics_from_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the diagnostic metrics required by A39 from a list of pairs."""
    pnls = [float(p.get("pnl_pct", 0.0)) for p in pairs]
    total_return = sum(pnls) * 100.0
    max_dd = _max_drawdown_from_pnls(pnls)
    overshoot = analyze_stop_loss_overshoot(pairs)
    return {
        "trade_count": len(pairs),
        "return": round(total_return, 4),
        "drawdown": round(max_dd, 4),
        "stop_loss_overshoot": {
            "worst_loss_pct": overshoot.get("worst_loss_pct"),
            "overshoot_count": overshoot.get("overshoot_count"),
            "max_overshoot_multiple": overshoot.get("max_overshoot_multiple"),
        },
    }


def _run_symbol(
    db_path: Path,
    symbol: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Run baseline close-model backtest and exclusion comparison for one symbol."""
    transitions = _detect_transitions(db_path, symbol, start_date, end_date)
    empty_metrics = _metrics_from_pairs([])
    if transitions.get("unavailable"):
        return {
            "symbol": symbol,
            "unavailable": transitions["unavailable"],
            "detection_method": transitions.get("detection_method"),
            "transition_dates": transitions.get("transition_dates", []),
            "before": empty_metrics,
            "after": empty_metrics,
        }

    # Ensure the baseline close model is active.
    STRATEGY_CONFIG["stop_execution_model"] = "close"

    engine = BacktestEngine(
        symbol=symbol,
        freq="1",
        start_date=start_date,
        end_date=end_date,
        db_path=str(db_path),
        table_name=f"{symbol.lower()}_1M_raw",
    )
    report = engine.run()
    if "error" in report:
        unavailable = f"backtest_error: {report['error']}"
        if "数据加载失败" in report.get("error", ""):
            unavailable = "no_bars_in_window"
        elif "数据不足" in report.get("error", ""):
            unavailable = "insufficient_bars_in_window"
        return {
            "symbol": symbol,
            "unavailable": unavailable,
            "detection_method": transitions.get("detection_method"),
            "transition_dates": transitions.get("transition_dates", []),
            "before": empty_metrics,
            "after": empty_metrics,
        }

    all_pairs = engine.strategy.get_combined_trades()

    trading_dates = _trading_dates_from_bars(db_path, symbol)
    excluded_dates, exclusion_notes = _exclusion_dates(
        transitions.get("transition_dates", []), trading_dates
    )
    filtered_pairs = [p for p in all_pairs if not _pair_in_exclusion_window(p, excluded_dates)]

    return {
        "symbol": symbol,
        "detection_method": transitions.get("detection_method"),
        "transition_dates": transitions.get("transition_dates", []),
        "excluded_dates": sorted(d.isoformat() for d in excluded_dates),
        "exclusion_notes": exclusion_notes,
        "before": _metrics_from_pairs(all_pairs),
        "after": _metrics_from_pairs(filtered_pairs),
        "baseline_report_summary": {
            "total_trades": report.get("total_trades"),
            "total_return_pct": report.get("total_return_pct"),
            "max_drawdown_pct": report.get("max_drawdown_pct"),
        },
    }


def _write_outputs(
    out_dir: Path,
    stamp: str,
    payload: dict[str, Any],
) -> tuple[Path, Path]:
    """Write JSON and Markdown evidence files."""
    json_path = out_dir / f"rollover_exclusion_report_{stamp}.json"
    md_path = out_dir / f"rollover_exclusion_report_{stamp}.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = [
        "# Rollover Exclusion Diagnostic Report",
        "",
        f"**Generated at:** {payload['generated_at']}",
        f"**Window:** {payload['window']}",
        "",
        f"> {payload['disclaimer']}",
        "",
        "## Method",
        "",
        "- Rollover transitions are detected from the raw table's `real_symbol` column (primary).",
        "- For each transition date, trades with open or close in `{prev, transition, next}` "
        "trading dates are excluded.",
        "- The baseline backtest uses the default `stop_execution_model='close'`.",
        "- `return` and `drawdown` are computed from the cumulative pair P&L curve; "
        "`stop_loss_overshoot` reuses the A35/A38 definition.",
        "",
        "## Results by Symbol",
        "",
    ]

    for symbol, data in payload["symbols"].items():
        lines.append(f"### {symbol}")
        lines.append("")
        if data.get("unavailable"):
            lines.append(f"- **Unavailable:** {data['unavailable']}")
            lines.append(f"- **Detection method:** {data.get('detection_method', 'N/A')}")
            lines.append("")
            before = data.get("before", _metrics_from_pairs([]))
            after = data.get("after", _metrics_from_pairs([]))
            lines.append("| Metric | Before | After |")
            lines.append("|--------|--------|-------|")
            lines.append(f"| trade_count | {before['trade_count']} | {after['trade_count']} |")
            lines.append(f"| return | {before['return']} | {after['return']} |")
            lines.append(f"| drawdown | {before['drawdown']} | {after['drawdown']} |")
            lines.append(
                f"| stop_loss_overshoot_count | "
                f"{before['stop_loss_overshoot']['overshoot_count']} | "
                f"{after['stop_loss_overshoot']['overshoot_count']} |"
            )
            lines.append(
                f"| stop_loss_worst_loss_pct | "
                f"{before['stop_loss_overshoot']['worst_loss_pct']} | "
                f"{after['stop_loss_overshoot']['worst_loss_pct']} |"
            )
            lines.append("")
            continue

        lines.append(f"- **Detection method:** {data['detection_method']}")
        lines.append(f"- **Transitions:** {len(data['transition_dates'])}")
        for tr in data["transition_dates"]:
            lines.append(
                f"  - {tr['date']}: {tr['from_contract']} -> {tr['to_contract']}"
            )
        lines.append(f"- **Excluded dates:** {', '.join(data['excluded_dates'])}")
        if data.get("exclusion_notes"):
            lines.append("- **Exclusion notes:**")
            for note in data["exclusion_notes"]:
                prev_note = note.get("prev")
                next_note = note.get("next")
                parts: list[str] = []
                if prev_note:
                    parts.append(f"previous side {prev_note}")
                if next_note:
                    parts.append(f"next side {next_note}")
                if parts:
                    lines.append(f"  - {note['date']}: " + "; ".join(parts))
        lines.append("")
        lines.append("| Metric | Before | After |")
        lines.append("|--------|--------|-------|")
        before = data["before"]
        after = data["after"]
        lines.append(f"| trade_count | {before['trade_count']} | {after['trade_count']} |")
        lines.append(f"| return | {before['return']} | {after['return']} |")
        lines.append(f"| drawdown | {before['drawdown']} | {after['drawdown']} |")
        lines.append(
            f"| stop_loss_overshoot_count | "
            f"{before['stop_loss_overshoot']['overshoot_count']} | "
            f"{after['stop_loss_overshoot']['overshoot_count']} |"
        )
        lines.append(
            f"| stop_loss_worst_loss_pct | "
            f"{before['stop_loss_overshoot']['worst_loss_pct']} | "
            f"{after['stop_loss_overshoot']['worst_loss_pct']} |"
        )
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- 888 continuous contracts are raw splices (`found_spliced`).")
    lines.append("- `real_symbol` is the primary rollover source; no cross-rollover price adjustment is applied.")
    lines.append("- This diagnostic excludes rollover windows for comparison only; it does not alter live prices or gating.")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main(
    db_path: Path | None = None,
    symbols: tuple[str, ...] = tuple(SYMBOLS),
    start_date: str = WINDOW_START,
    end_date: str = WINDOW_END,
    out_dir: Path = DEFAULT_OUT_DIR,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Run the rollover exclusion diagnostic and write evidence."""
    db_path = db_path or Path(SQLITE_DB_PATH)
    if stamp is None:
        stamp = datetime.now(timezone.utc).date().isoformat()

    payload: dict[str, Any] = {
        "disclaimer": BANNER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": f"{start_date} ~ {end_date}",
        "db_path": str(db_path),
        "symbols": {},
    }

    for symbol in symbols:
        print(f"[rollover diagnostic] processing {symbol} ...")
        payload["symbols"][symbol] = _run_symbol(db_path, symbol, start_date, end_date)

    json_path, md_path = _write_outputs(out_dir, stamp, payload)
    print(f"[rollover diagnostic] wrote {json_path.name}")
    print(f"[rollover diagnostic] wrote {md_path.name}")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A39 rollover exclusion diagnostic")
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--start-date", default=WINDOW_START)
    parser.add_argument("--end-date", default=WINDOW_END)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--stamp", default=None)
    parser.add_argument("--symbols", nargs="+", default=SYMBOLS)
    args = parser.parse_args()

    main(
        db_path=args.db_path,
        symbols=tuple(args.symbols),
        start_date=args.start_date,
        end_date=args.end_date,
        out_dir=args.out_dir,
        stamp=args.stamp,
    )
