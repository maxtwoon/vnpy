"""Read-only stop-loss stress diagnostic for the Chan strategy workspace.

This script only inspects existing diagnostics JSON files and optional SQLite
K-line data.  It does not connect to a broker, send orders, or modify strategy,
Position, SimNow, gateway, or trading logic.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Make the czsc_strategy package importable from this diagnostics script
_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.config import BACKTEST_CONFIG, SQLITE_DB_PATH  # noqa: E402


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE
DEFAULT_DIAGNOSTICS_DIR = HERE
DEFAULT_STOP_LOSS_BP = 300
DEFAULT_PENALTY_BP = 10
DEFAULT_GAP_THRESHOLD_MINUTES = 12 * 60

DISCLAIMER = "Diagnostic only, not a trading recommendation."

EXIT_REASON_KEYS = ("exit_reason", "reason", "reason_code", "close_reason", "exit_signal")
PNL_PCT_KEYS = ("pnl_pct", "return_pct", "profit_pct", "pnl_rate")
STOP_LOSS_REASON_TOKENS = ("stop_loss", "止损")
OPEN_PRICE_KEYS = ("open_price", "open", "开盘价")
CLOSE_PRICE_KEYS = ("close_price", "close", "收盘价")
SYMBOL_KEYS = ("requested_symbol", "symbol", "data_symbol", "code")
DIRECTION_KEYS = ("direction", "side", "trade_direction")


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    cols_lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    return None


def _extract_value(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None:
            return value
    return None


def _is_stop_loss_record(record: dict[str, Any]) -> bool:
    for key in EXIT_REASON_KEYS:
        value = str(record.get(key, "")).lower()
        if any(token in value for token in STOP_LOSS_REASON_TOKENS):
            return True
    return False


def _canonical_exit_reason(record: dict[str, Any]) -> str | None:
    """Return a normalized stop-loss reason string for deduplication."""
    for key in EXIT_REASON_KEYS:
        value = str(record.get(key, "")).lower()
        if any(token in value for token in STOP_LOSS_REASON_TOKENS):
            return "stop_loss"
    return None


def _iter_dict_candidates(obj: Any) -> Any:
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _iter_dict_candidates(value)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                yield item
            else:
                yield from _iter_dict_candidates(item)


def _parse_dt(dt_val: Any) -> datetime | None:
    if dt_val is None:
        return None
    s = str(dt_val)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _normalize_pnl_pct(pnl: Any) -> float:
    """Return pnl as percentage points (e.g. -0.126 -> -12.6)."""
    f = float(pnl)  # type: ignore[arg-type]
    if abs(f) <= 1.0:
        f *= 100.0
    return f


def _as_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _infer_direction(pnl_pct: float, open_price: float, close_price: float) -> str | None:
    """Infer long/short from the sign of price return versus pnl."""
    if open_price == 0:
        return None
    price_return = (close_price - open_price) / open_price * 100.0
    if price_return * pnl_pct >= 0:
        return "long"
    return "short"


def _trade_key(pair: dict[str, Any]) -> tuple[str, ...]:
    """Stable key for deduplicating stop-loss records across JSON files."""
    return (
        str(pair.get("symbol")),
        str(pair.get("strategy")),
        str(pair.get("open_dt")),
        str(pair.get("close_dt")),
        f"{pair.get('pnl_pct'):.6f}" if pair.get("pnl_pct") is not None else "",
        str(pair.get("exit_reason")),
    )


def collect_stop_loss_pairs(
    diagnostics_dir: Path,
    max_file_mb: float = 50.0,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Scan diagnostics JSON files for stop-loss trade records.

    Returns the deduplicated list of trades plus a metadata dict with
    raw, unique, and duplicate counts.
    """
    if not diagnostics_dir or not diagnostics_dir.exists():
        return [], {"raw": 0, "unique": 0, "duplicates": 0}

    pairs: list[dict[str, Any]] = []
    max_bytes = max_file_mb * 1024 * 1024
    for path in diagnostics_dir.rglob("*.json"):
        if path.name.startswith("stop_loss_stress_report"):
            continue
        if path.name.startswith("audit_issue_diagnostics"):
            continue
        if path.stat().st_size > max_bytes:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue

        for record in _iter_dict_candidates(data):
            if not _is_stop_loss_record(record):
                continue
            pnl = _extract_value(record, PNL_PCT_KEYS)
            if pnl is None:
                continue
            pnl_pct = _as_number(pnl)
            if pnl_pct is None:
                continue

            symbol = _extract_value(record, SYMBOL_KEYS)
            open_dt = _parse_dt(record.get("open_dt") or record.get("open_time"))
            close_dt = _parse_dt(record.get("close_dt") or record.get("close_time"))
            open_price = _as_number(_extract_value(record, OPEN_PRICE_KEYS))
            close_price = _as_number(_extract_value(record, CLOSE_PRICE_KEYS))
            direction = str(record.get("direction", "")).lower() or None

            pairs.append(
                {
                    "symbol": symbol,
                    "strategy": record.get("strategy"),
                    "open_dt": open_dt.isoformat() if open_dt else None,
                    "close_dt": close_dt.isoformat() if close_dt else None,
                    "open_price": open_price,
                    "close_price": close_price,
                    "pnl_pct": _normalize_pnl_pct(pnl_pct),
                    "exit_reason": _canonical_exit_reason(record),
                    "direction": direction,
                    "source_file": str(path.relative_to(diagnostics_dir)),
                }
            )

    seen: set[tuple[str, ...]] = set()
    unique: list[dict[str, Any]] = []
    for pair in pairs:
        key = _trade_key(pair)
        if key in seen:
            continue
        seen.add(key)
        unique.append(pair)

    counts = {"raw": len(pairs), "unique": len(unique), "duplicates": len(pairs) - len(unique)}
    return unique, counts


class BarLoader:
    """Lightweight cache for loading 1M/daily bars from the project SQLite DB."""

    def __init__(self, db_path: Path | None):
        self.db_path = db_path
        self._cache: dict[tuple[str, datetime, datetime], list[dict[str, Any]]] = {}

    def load(
        self, symbol: str | None, start_dt: datetime, end_dt: datetime
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        if not symbol:
            return None, "missing_symbol"
        key = (symbol, start_dt, end_dt)
        if key in self._cache:
            return self._cache[key], None

        bars, error = _load_bars_from_sqlite(self.db_path, symbol, start_dt, end_dt)
        self._cache[key] = bars or []
        return bars, error


def _load_bars_from_sqlite(
    db_path: Path | None, symbol: str, start_dt: datetime, end_dt: datetime
) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not db_path or not db_path.exists():
        return None, "db_unavailable"

    try:
        conn = sqlite3.connect(str(db_path))
    except Exception as exc:
        return None, f"db_open_error: {exc}"

    try:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        if not tables:
            return None, "no_tables"

        table_name: str | None = None
        columns: list[str] = []
        for table in tables:
            schema = conn.execute(f"PRAGMA table_info({table})").fetchall()
            col_names = [row[1] for row in schema]
            symbol_col = _find_column(col_names, ["symbol", "code", "stock_code", "ts_code"])
            date_col = _find_column(col_names, ["datetime", "date", "trade_date", "dt", "time"])
            open_col = _find_column(col_names, ["open", "open_price", "开盘价"])
            high_col = _find_column(col_names, ["high", "high_price", "最高价"])
            low_col = _find_column(col_names, ["low", "low_price", "最低价"])
            close_col = _find_column(col_names, ["close", "close_price", "收盘价"])
            if symbol_col and date_col and open_col and high_col and low_col and close_col:
                table_name = table
                columns = col_names
                break

        if table_name is None:
            return None, "no_suitable_table"

        symbol_col = _find_column(columns, ["symbol", "code", "stock_code", "ts_code"])
        date_col = _find_column(columns, ["datetime", "date", "trade_date", "dt", "time"])
        open_col = _find_column(columns, ["open", "open_price", "开盘价"])
        high_col = _find_column(columns, ["high", "high_price", "最高价"])
        low_col = _find_column(columns, ["low", "low_price", "最低价"])
        close_col = _find_column(columns, ["close", "close_price", "收盘价"])

        start_s = start_dt.strftime("%Y-%m-%d")
        end_s = end_dt.strftime("%Y-%m-%d")
        query = (
            f"SELECT {date_col}, {open_col}, {high_col}, {low_col}, {close_col} "
            f"FROM {table_name} WHERE {symbol_col} = ? AND {date_col} >= ? AND {date_col} <= ? "
            f"ORDER BY {date_col}"
        )
        cursor = conn.execute(query, (symbol, start_s, end_s))
        bars: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            dt_val, o, h, l, c = row
            dt = _parse_dt(dt_val)
            if dt is None:
                continue
            try:
                bars.append(
                    {
                        "dt": dt,
                        "open": float(o),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c),
                    }
                )
            except (TypeError, ValueError):
                continue
        return (bars, None) if bars else (None, "no_bars_for_window")
    except Exception as exc:
        return None, f"query_error: {exc}"
    finally:
        conn.close()


def _scenario_summary(
    trades: list[dict[str, Any]],
    unavailable: list[dict[str, Any]],
    stop_loss_bp: int,
) -> dict[str, Any]:
    stop_loss_pct = -stop_loss_bp * 0.01
    trade_count = len(trades)
    affected_trade_count = sum(1 for t in trades if t.get("pnl_pct", 0.0) < stop_loss_pct - 1e-9)
    affected_symbols = sorted({str(t.get("symbol")) for t in trades if t.get("pnl_pct", 0.0) < stop_loss_pct - 1e-9})

    if not trades:
        return {
            "status": "unavailable",
            "trade_count": 0,
            "affected_trade_count": 0,
            "affected_symbols": [],
            "worst_loss_pct": None,
            "overshoot_count": 0,
            "max_overshoot_multiple": None,
            "avg_loss_pct": None,
            "sample_trades": [],
            "unavailable_count": len(unavailable),
            "unavailable_reasons": _collect_reasons(unavailable),
        }

    losses = [t["pnl_pct"] for t in trades]
    worst_loss_pct = min(losses)
    overshoot_trades = [t for t in trades if t["pnl_pct"] < stop_loss_pct - 1e-9]
    overshoot_count = len(overshoot_trades)
    max_overshoot_multiple = 0.0
    if overshoot_trades:
        max_overshoot_multiple = max(t["pnl_pct"] / stop_loss_pct for t in overshoot_trades)

    avg_loss_pct = sum(losses) / len(losses)
    sorted_trades = sorted(trades, key=lambda t: t["pnl_pct"])[:3]
    sample_trades = [
        {
            "symbol": t.get("symbol"),
            "strategy": t.get("strategy"),
            "open_dt": t.get("open_dt"),
            "close_dt": t.get("close_dt"),
            "pnl_pct": round(t["pnl_pct"], 4),
            "stressed_exit_price": t.get("stressed_exit_price"),
            "triggered": t.get("triggered"),
            "source_file": t.get("source_file"),
        }
        for t in sorted_trades
    ]

    return {
        "status": "ok" if not unavailable else "partial",
        "trade_count": trade_count,
        "affected_trade_count": affected_trade_count,
        "affected_symbols": affected_symbols,
        "worst_loss_pct": round(worst_loss_pct, 4),
        "overshoot_count": overshoot_count,
        "max_overshoot_multiple": round(max_overshoot_multiple, 4) if overshoot_count else 0.0,
        "avg_loss_pct": round(avg_loss_pct, 4),
        "sample_trades": sample_trades,
        "unavailable_count": len(unavailable),
        "unavailable_reasons": _collect_reasons(unavailable),
    }


def _collect_reasons(unavailable: list[dict[str, Any]]) -> dict[str, int]:
    reasons: dict[str, int] = defaultdict(int)
    for item in unavailable:
        reason = item.get("reason", "unknown")
        reasons[reason] += 1
    return dict(reasons)


def scenario_observed_close(
    pairs: list[dict[str, Any]], stop_loss_bp: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Baseline scenario using the recorded close-based PnL."""
    trades: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for pair in pairs:
        if pair.get("pnl_pct") is None:
            unavailable.append({**pair, "reason": "missing_pnl"})
            continue
        trades.append({**pair, "stressed_exit_price": pair.get("close_price"), "triggered": False})
    return trades, unavailable


def _resolve_direction(pair: dict[str, Any]) -> str | None:
    direction = pair.get("direction")
    if direction in ("long", "short"):
        return direction
    open_price = pair.get("open_price")
    close_price = pair.get("close_price")
    pnl_pct = pair.get("pnl_pct")
    if open_price is not None and close_price is not None and pnl_pct is not None:
        return _infer_direction(pnl_pct, open_price, close_price)
    return None


def scenario_intrabar_trigger(
    pairs: list[dict[str, Any]],
    bar_loader: BarLoader,
    stop_loss_bp: int,
    penalty_bp: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Stress scenario: stop triggered by an intraday/intrabar extreme."""
    trades: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for pair in pairs:
        symbol = pair.get("symbol")
        open_dt = _parse_dt(pair.get("open_dt"))
        close_dt = _parse_dt(pair.get("close_dt"))
        open_price = pair.get("open_price")
        direction = _resolve_direction(pair)

        if direction is None:
            unavailable.append({**pair, "reason": "missing_direction"})
            continue
        if open_price is None:
            unavailable.append({**pair, "reason": "missing_open_price"})
            continue
        if open_dt is None or close_dt is None:
            unavailable.append({**pair, "reason": "missing_dates"})
            continue

        bars, error = bar_loader.load(symbol, open_dt, close_dt)
        if error or not bars:
            unavailable.append({**pair, "reason": error or "no_bars"})
            continue

        first_bar = bars[0]
        derived_open = open_price if open_price is not None else first_bar["open"]
        trigger_level = (
            derived_open * (1 - stop_loss_bp / 10000)
            if direction == "long"
            else derived_open * (1 + stop_loss_bp / 10000)
        )

        triggered = False
        exit_price = pair.get("close_price") if pair.get("close_price") is not None else bars[-1]["close"]
        for bar in bars:
            if direction == "long" and bar["low"] <= trigger_level:
                triggered = True
                exit_price = trigger_level
                break
            if direction == "short" and bar["high"] >= trigger_level:
                triggered = True
                exit_price = trigger_level
                break

        if triggered and penalty_bp:
            penalty_price = derived_open * penalty_bp / 10000
            exit_price = exit_price - penalty_price if direction == "long" else exit_price + penalty_price

        pnl = (
            (exit_price - derived_open) / derived_open * 100.0
            if direction == "long"
            else (derived_open - exit_price) / derived_open * 100.0
        )
        trades.append(
            {
                **pair,
                "open_price": derived_open,
                "stressed_exit_price": exit_price,
                "triggered": triggered,
                "pnl_pct": pnl,
            }
        )
    return trades, unavailable


def scenario_gap_open_exit(
    pairs: list[dict[str, Any]],
    bar_loader: BarLoader,
    stop_loss_bp: int,
    gap_threshold_minutes: int = DEFAULT_GAP_THRESHOLD_MINUTES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Stress scenario: stop filled on a gap open after a session break."""
    trades: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for pair in pairs:
        symbol = pair.get("symbol")
        open_dt = _parse_dt(pair.get("open_dt"))
        close_dt = _parse_dt(pair.get("close_dt"))
        open_price = pair.get("open_price")
        direction = _resolve_direction(pair)

        if direction is None:
            unavailable.append({**pair, "reason": "missing_direction"})
            continue
        if open_price is None:
            unavailable.append({**pair, "reason": "missing_open_price"})
            continue
        if open_dt is None or close_dt is None:
            unavailable.append({**pair, "reason": "missing_dates"})
            continue

        bars, error = bar_loader.load(symbol, open_dt, close_dt)
        if error or not bars:
            unavailable.append({**pair, "reason": error or "no_bars"})
            continue

        trigger_level = (
            open_price * (1 - stop_loss_bp / 10000)
            if direction == "long"
            else open_price * (1 + stop_loss_bp / 10000)
        )

        exit_price = pair.get("close_price") if pair.get("close_price") is not None else bars[-1]["close"]
        triggered = False
        gap_method = "none"
        prev_dt = bars[0]["dt"]
        for i, bar in enumerate(bars):
            # Check for gap after a session break
            gap_minutes = (bar["dt"] - prev_dt).total_seconds() / 60.0
            is_gap = i > 0 and gap_minutes > gap_threshold_minutes
            if is_gap or bar["dt"] >= close_dt:
                if direction == "long" and bar["open"] <= trigger_level:
                    exit_price = bar["open"]
                    triggered = True
                    gap_method = "session_gap" if is_gap else "post_close"
                    break
                if direction == "short" and bar["open"] >= trigger_level:
                    exit_price = bar["open"]
                    triggered = True
                    gap_method = "session_gap" if is_gap else "post_close"
                    break
            prev_dt = bar["dt"]

        pnl = (
            (exit_price - open_price) / open_price * 100.0
            if direction == "long"
            else (open_price - exit_price) / open_price * 100.0
        )
        trades.append(
            {
                **pair,
                "stressed_exit_price": exit_price,
                "triggered": triggered,
                "gap_method": gap_method,
                "pnl_pct": pnl,
            }
        )
    return trades, unavailable


def scenario_penalty_slippage(
    pairs: list[dict[str, Any]],
    bar_loader: BarLoader,
    stop_loss_bp: int,
    penalty_bp: int = DEFAULT_PENALTY_BP,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Overlay scenario: worsen the most pessimistic available exit by penalty_bp."""
    # Prefer intrabar, then gap, then observed as the base exit.
    intrabar_trades, _ = scenario_intrabar_trigger(pairs, bar_loader, stop_loss_bp, penalty_bp=0)
    gap_trades, _ = scenario_gap_open_exit(pairs, bar_loader, stop_loss_bp)
    observed_trades, _ = scenario_observed_close(pairs, stop_loss_bp)

    base_map: dict[int, dict[str, Any]] = {}
    for t in observed_trades:
        base_map[t["_index"]] = t
    for t in gap_trades:
        idx = t["_index"]
        if idx not in base_map or t["pnl_pct"] < base_map[idx]["pnl_pct"]:
            base_map[idx] = t
    for t in intrabar_trades:
        idx = t["_index"]
        if idx not in base_map or t["pnl_pct"] < base_map[idx]["pnl_pct"]:
            base_map[idx] = t

    trades: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for pair in pairs:
        idx = pair.get("_index")
        base = base_map.get(idx) if idx is not None else None
        if base is None or pair.get("pnl_pct") is None:
            unavailable.append({**pair, "reason": "no_base_scenario"})
            continue

        # Worsen the most pessimistic base PnL by the penalty amount.  This keeps
        # the overlay monotonic even when the recorded PnL includes costs or
        # slippage not captured by raw open/close prices.
        pnl = base["pnl_pct"] - penalty_bp * 0.01

        # Compute a display-only exit price when possible.
        direction = _resolve_direction(pair)
        open_price = pair.get("open_price")
        exit_price = base.get("stressed_exit_price")
        if open_price is not None and exit_price is not None and direction is not None:
            penalty_price = open_price * penalty_bp / 10000
            exit_price = exit_price - penalty_price if direction == "long" else exit_price + penalty_price

        trades.append(
            {
                **pair,
                "stressed_exit_price": exit_price,
                "triggered": base.get("triggered", False),
                "pnl_pct": pnl,
            }
        )
    return trades, unavailable


def _top_level_status(scenarios: dict[str, Any]) -> str:
    statuses = [s.get("status") for s in scenarios.values()]
    if all(s == "unavailable" for s in statuses):
        return "unavailable"
    has_ok = any(s in ("ok", "partial") for s in statuses)
    has_unavailable = any(s == "unavailable" for s in statuses)
    if has_unavailable and has_ok:
        return "partial"
    if any(s == "partial" for s in statuses):
        return "partial"
    if any(s == "ok" for s in statuses):
        return "ok"
    return "unavailable"


def build_report(
    diagnostics_dir: Path,
    db_path: Path | None,
    stop_loss_bp: int = DEFAULT_STOP_LOSS_BP,
    penalty_bp: int = DEFAULT_PENALTY_BP,
) -> dict[str, Any]:
    """Build the stop-loss stress report."""
    generated_at = datetime.now(timezone.utc).isoformat()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    pairs, pair_counts = collect_stop_loss_pairs(diagnostics_dir)
    for i, pair in enumerate(pairs):
        pair["_index"] = i
    bar_loader = BarLoader(db_path)

    observed_trades, observed_unavailable = scenario_observed_close(pairs, stop_loss_bp)
    intrabar_trades, intrabar_unavailable = scenario_intrabar_trigger(
        pairs, bar_loader, stop_loss_bp, penalty_bp=0
    )
    gap_trades, gap_unavailable = scenario_gap_open_exit(pairs, bar_loader, stop_loss_bp)
    penalty_trades, penalty_unavailable = scenario_penalty_slippage(
        pairs, bar_loader, stop_loss_bp, penalty_bp=penalty_bp
    )

    scenarios = {
        "observed_close": _scenario_summary(observed_trades, observed_unavailable, stop_loss_bp),
        "intrabar_trigger": _scenario_summary(intrabar_trades, intrabar_unavailable, stop_loss_bp),
        "gap_open_exit": _scenario_summary(gap_trades, gap_unavailable, stop_loss_bp),
        "penalty_slippage": _scenario_summary(penalty_trades, penalty_unavailable, stop_loss_bp),
    }

    scenario_trades = [
        ("observed_close", observed_trades),
        ("intrabar_trigger", intrabar_trades),
        ("gap_open_exit", gap_trades),
        ("penalty_slippage", penalty_trades),
    ]
    worst_map: dict[int, dict[str, Any]] = {}
    for scenario_name, trades in scenario_trades:
        for t in trades:
            idx = t.get("_index")
            if idx is None:
                continue
            candidate = {**t, "scenario": scenario_name}
            if idx not in worst_map or candidate["pnl_pct"] < worst_map[idx]["pnl_pct"]:
                worst_map[idx] = candidate
    worst_trades = sorted(worst_map.values(), key=lambda t: t["pnl_pct"])[:5]
    worst_trades = [
        {
            "symbol": t.get("symbol"),
            "strategy": t.get("strategy"),
            "open_dt": t.get("open_dt"),
            "close_dt": t.get("close_dt"),
            "pnl_pct": round(t["pnl_pct"], 4),
            "scenario": t.get("scenario", "unknown"),
            "source_file": t.get("source_file"),
        }
        for t in worst_trades
    ]

    unavailable_trades = (
        observed_unavailable + intrabar_unavailable + gap_unavailable + penalty_unavailable
    )
    unavailable_summary_map: dict[int, dict[str, Any]] = {}
    for t in unavailable_trades:
        idx = t.get("_index")
        if idx is None or idx in unavailable_summary_map:
            continue
        unavailable_summary_map[idx] = {
            "symbol": t.get("symbol"),
            "strategy": t.get("strategy"),
            "open_dt": t.get("open_dt"),
            "close_dt": t.get("close_dt"),
            "reason": t.get("reason"),
            "source_file": t.get("source_file"),
        }
    unavailable_summary = list(unavailable_summary_map.values())

    notes = [
        "Baseline uses recorded close-based stop-loss outcomes from existing diagnostics JSON files.",
        "Intrabar and gap scenarios require SQLite K-line data; missing data is marked unavailable rather than silently passing.",
        "Penalty slippage is an overlay applied to the most pessimistic available exit price.",
        "This diagnostic does not modify Position, BacktestEngine, strategy parameters, SimNow, or trading interfaces.",
    ]

    return {
        "date": date,
        "generated_at": generated_at,
        "disclaimer": DISCLAIMER,
        "status": _top_level_status(scenarios),
        "stop_loss_bp": stop_loss_bp,
        "penalty_bp": penalty_bp,
        "raw_trade_count": pair_counts["raw"],
        "unique_trade_count": pair_counts["unique"],
        "duplicate_trade_count": pair_counts["duplicates"],
        "data_source": {
            "pairs": "diagnostics_json_scan",
            "bars": str(db_path) if db_path and db_path.exists() else "unavailable",
        },
        "scenarios": scenarios,
        "worst_trades": worst_trades,
        "unavailable_trades": unavailable_summary,
        "notes": notes,
    }


def _fmt_num(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.2f}%"


def write_markdown_report(report: dict[str, Any], out_path: Path) -> None:
    """Render the report as Markdown."""
    lines: list[str] = [
        "# Stop-Loss Stress Diagnostic Report",
        "",
        f"- Date: `{report['date']}`",
        f"- Generated at: `{report['generated_at']}`",
        f"- Stop-loss budget: `{report['stop_loss_bp']}bp`",
        f"- Penalty slippage: `{report['penalty_bp']}bp`",
        f"- Status: `{report['status']}`",
        "",
        f"> {report['disclaimer']}",
        "",
        "## Executive Summary",
        "",
        "| scenario | status | trade_count | affected_count | worst_loss | overshoot_count | max_overshoot_multiple | avg_loss |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, summary in report["scenarios"].items():
        lines.append(
            f"| {name} | {summary['status']} | {summary['trade_count']} | "
            f"{summary['affected_trade_count']} | {_fmt_pct(summary['worst_loss_pct'])} | "
            f"{summary['overshoot_count']} | {_fmt_num(summary['max_overshoot_multiple'])} | "
            f"{_fmt_pct(summary['avg_loss_pct'])} |"
        )
    lines.append("")
    lines.extend(
        [
            "## Trade Counts",
            "",
            f"- raw_trade_count: `{report.get('raw_trade_count', 'N/A')}`",
            f"- unique_trade_count: `{report.get('unique_trade_count', 'N/A')}`",
            f"- duplicate_trade_count: `{report.get('duplicate_trade_count', 'N/A')}`",
            "",
        ]
    )

    for name, summary in report["scenarios"].items():
        lines.extend(
            [
                f"## Scenario: {name}",
                "",
                f"- status: `{summary['status']}`",
                f"- trade_count: `{summary['trade_count']}`",
                f"- affected_trade_count: `{summary['affected_trade_count']}`",
                f"- affected_symbols: `{', '.join(summary['affected_symbols']) or 'N/A'}`",
                f"- worst_loss_pct: `{_fmt_num(summary['worst_loss_pct'])}`",
                f"- overshoot_count: `{summary['overshoot_count']}`",
                f"- max_overshoot_multiple: `{_fmt_num(summary['max_overshoot_multiple'])}`",
                f"- avg_loss_pct: `{_fmt_num(summary['avg_loss_pct'])}`",
                f"- unavailable_count: `{summary['unavailable_count']}`",
                f"- unavailable_reasons: `{summary['unavailable_reasons']}`",
                "",
                "### Sample Worst Trades",
                "",
                "| symbol | strategy | open_dt | close_dt | pnl_pct | stressed_exit | source |",
                "|---|---|---|---:|---:|---|---|",
            ]
        )
        for t in summary["sample_trades"]:
            lines.append(
                f"| {t.get('symbol', 'N/A')} | {t.get('strategy', 'N/A')} | "
                f"{t.get('open_dt', 'N/A')} | {t.get('close_dt', 'N/A')} | "
                f"{_fmt_pct(t.get('pnl_pct'))} | {_fmt_num(t.get('stressed_exit_price'))} | "
                f"{t.get('source_file', 'N/A')} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Worst Trades Across Scenarios",
            "",
            "| symbol | strategy | open_dt | close_dt | pnl_pct | scenario | source |",
            "|---|---|---|---:|---:|---|---|",
        ]
    )
    for t in report["worst_trades"]:
        lines.append(
            f"| {t.get('symbol', 'N/A')} | {t.get('strategy', 'N/A')} | "
            f"{t.get('open_dt', 'N/A')} | {t.get('close_dt', 'N/A')} | "
            f"{_fmt_pct(t.get('pnl_pct'))} | {t.get('scenario', 'N/A')} | "
            f"{t.get('source_file', 'N/A')} |"
        )
    lines.append("")

    lines.extend(
        [
            "## Unavailable Trades",
            "",
            "| symbol | strategy | open_dt | close_dt | reason | source |",
            "|---|---|---|---|---|---|",
        ]
    )
    for t in report["unavailable_trades"]:
        lines.append(
            f"| {t.get('symbol', 'N/A')} | {t.get('strategy', 'N/A')} | "
            f"{t.get('open_dt', 'N/A')} | {t.get('close_dt', 'N/A')} | "
            f"{t.get('reason', 'N/A')} | {t.get('source_file', 'N/A')} |"
        )
    lines.append("")

    lines.extend(
        [
            "## Notes",
            "",
        ]
        + [f"- {note}" for note in report["notes"]]
        + ["", "## Data Source", "", f"- pairs: `{report['data_source']['pairs']}`", f"- bars: `{report['data_source']['bars']}`", ""]
    )

    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_json_report(report: dict[str, Any], out_path: Path) -> None:
    """Write the report as JSON."""
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a read-only stop-loss stress diagnostic report."
    )
    parser.add_argument(
        "--diagnostics-dir",
        type=Path,
        default=DEFAULT_DIAGNOSTICS_DIR,
        help="Directory containing diagnostics JSON files",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Optional SQLite K-line database path",
    )
    parser.add_argument(
        "--stop-loss-bp",
        type=int,
        default=DEFAULT_STOP_LOSS_BP,
        help="Nominal stop-loss level in basis points",
    )
    parser.add_argument(
        "--penalty-bp",
        type=int,
        default=DEFAULT_PENALTY_BP,
        help="Penalty slippage overlay in basis points",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Output directory for JSON and Markdown reports",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db_path) if args.db_path else (Path(SQLITE_DB_PATH) if SQLITE_DB_PATH else None)
    report = build_report(
        diagnostics_dir=args.diagnostics_dir,
        db_path=db_path,
        stop_loss_bp=args.stop_loss_bp,
        penalty_bp=args.penalty_bp,
    )

    date = report["date"]
    json_path = args.out_dir / f"stop_loss_stress_report_{date}.json"
    md_path = args.out_dir / f"stop_loss_stress_report_{date}.md"
    write_json_report(report, json_path)
    write_markdown_report(report, md_path)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
