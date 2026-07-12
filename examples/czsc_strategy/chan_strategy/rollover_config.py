"""Shared rollover transition detection and exclusion-window helpers.

This module is the single source of truth for detecting 888 continuous-contract
rollover dates from the raw table's ``real_symbol`` column and computing the
``transition_date ± 1 trading day`` exclusion window used by both the A39
diagnostic and the A52 per-trade rollover-window tagging logic.
"""
from __future__ import annotations

import bisect
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any


# Default symbols monitored by the A39 diagnostic and the A52 verification script.
ROLLOVER_SYMBOLS: tuple[str, ...] = ("AP888", "RB888", "SC888", "A888", "ZN888")


def _find_real_symbol_column(cur: sqlite3.Cursor, table: str) -> str | None:
    """Return the exact column name if the table has a real-symbol-like column."""
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1].lower(): row[1] for row in cur.fetchall()}
    for cand in ("real_symbol", "source_symbol"):
        if cand in columns:
            return columns[cand]
    return None


def _parse_dt(value: str) -> datetime | None:
    """Parse a datetime string from the database."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _detect_transitions(
    db_path: Path,
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Detect rollover transitions from the raw table's real_symbol column.

    This is the same detection logic originally introduced in the A39 diagnostic
    ``diagnostics/rollover_exclusion_report.py``; moving it here makes it reusable
    without creating a circular import between ``chan_strategy.backtest_engine``
    and the diagnostic script.
    """
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
        where_clauses = ["symbol = ?"]
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


def _trading_dates_from_bars(db_path: Path, symbol: str) -> set[date]:
    """Return all calendar dates with at least one bar for the symbol."""
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
