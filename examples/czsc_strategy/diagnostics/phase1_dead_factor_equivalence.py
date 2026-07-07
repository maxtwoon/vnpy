"""Phase 1 equivalence proof for A37 dead-factor removal.

This script proves that removing the two dead exit factors
("方向反转且在中枢内" from 二买平多 / 二卖平空) is behavior-neutral on real
1-minute bar data. It runs before/after backtests and requires an empty
trade-pair diff on both a long-only leg and a short-enabled leg.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import BACKTEST_CONFIG, SQLITE_DB_PATH, STRATEGY_CONFIG
from chan_strategy.positions import Factor, Position


DEFAULT_SYMBOLS = ["AP888", "RB888"]
DEFAULT_ENABLE_SHORT_SYMBOLS = ["SC888"]
DEFAULT_START = "2024-01-01"
DEFAULT_END = "2024-12-31"
DISCLAIMER = "Research-only equivalence check, not a trading recommendation."


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

def _trade_key(trade: dict[str, Any]) -> tuple[str, str, str]:
    """Stable key for trade-pair comparison."""
    return (
        str(trade["strategy"]),
        trade["open_dt"].isoformat(sep=" "),
        f"{float(trade['open_price']):.8f}",
    )


def _diff_trades(
    baseline: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare two trade lists keyed by (strategy, open_dt, open_price)."""
    base_map = {_trade_key(t): t for t in baseline}
    cur_map = {_trade_key(t): t for t in current}
    base_keys = set(base_map)
    cur_keys = set(cur_map)

    removed = [base_map[k] for k in sorted(base_keys - cur_keys)]
    added = [cur_map[k] for k in sorted(cur_keys - base_keys)]
    changed: list[dict[str, Any]] = []
    unchanged: list[tuple[str, str, str]] = []

    for key in sorted(base_keys & cur_keys):
        b = base_map[key]
        c = cur_map[key]
        close_dt_changed = b["close_dt"] != c["close_dt"]
        reason_changed = b.get("reason_code") != c.get("reason_code")
        raw_delta = (float(c["pnl_pct"]) - float(b["pnl_pct"])) * 100
        if close_dt_changed or reason_changed or abs(raw_delta) > 1e-12:
            changed.append({"key": key, "baseline": b, "current": c})
        else:
            unchanged.append(key)

    return {
        "removed": removed,
        "added": added,
        "changed": changed,
        "unchanged_count": len(unchanged),
        "summary": {
            "removed_count": len(removed),
            "added_count": len(added),
            "changed_count": len(changed),
            "unchanged_count": len(unchanged),
        },
    }


# ---------------------------------------------------------------------------
# Baseline factory wrappers (current code + dead factor)
# ---------------------------------------------------------------------------

def _make_baseline_create_second_buy_position(
    current: Any,
) -> Any:
    """Return a factory that re-adds the dead factor to 二买平多."""
    def _factory(
        symbol: str,
        freq: str = "30分钟",
        commission_rate: float | None = None,
        slippage: float | None = None,
        enable_daily_filter: bool = True,
    ) -> Position:
        pos = current(symbol, freq, commission_rate, slippage, enable_daily_filter)
        pos.exits[0].factors.append(
            Factor.load({
                "name": "方向反转且在中枢内",
                "signals_all": [
                    f"{freq}_D1BI_方向V260615_向下_任意_任意_0",
                    f"{freq}_D1ZS_位置V260615_中枢内_任意_任意_0",
                    f"{freq}_D1BI_背驰V260615_失效_任意_任意_0",
                ],
                "signals_any": [],
                "signals_not": [],
            })
        )
        return pos

    return _factory


def _make_baseline_create_second_sell_position(
    current: Any,
) -> Any:
    """Return a factory that re-adds the dead factor to 二卖平空."""
    def _factory(
        symbol: str,
        freq: str = "30分钟",
        commission_rate: float | None = None,
        slippage: float | None = None,
        enable_daily_filter: bool = True,
    ) -> Position:
        pos = current(symbol, freq, commission_rate, slippage, enable_daily_filter)
        pos.exits[0].factors.append(
            Factor.load({
                "name": "方向反转且在中枢内",
                "signals_all": [
                    f"{freq}_D1BI_方向V260615_向上_任意_任意_0",
                    f"{freq}_D1ZS_位置V260615_中枢内_任意_任意_0",
                    f"{freq}_D1BI_背驰V260615_失效_任意_任意_0",
                ],
                "signals_any": [],
                "signals_not": [],
            })
        )
        return pos

    return _factory


@contextlib.contextmanager
def _baseline_factories() -> Generator[None, None, None]:
    """Monkeypatch the two position factories to their baseline versions."""
    from chan_strategy import positions as pos_mod

    current_buy = pos_mod.create_second_buy_position
    current_sell = pos_mod.create_second_sell_position
    pos_mod.create_second_buy_position = _make_baseline_create_second_buy_position(current_buy)
    pos_mod.create_second_sell_position = _make_baseline_create_second_sell_position(current_sell)
    try:
        yield
    finally:
        pos_mod.create_second_buy_position = current_buy
        pos_mod.create_second_sell_position = current_sell


# ---------------------------------------------------------------------------
# Backtest runner
# ---------------------------------------------------------------------------

def _dominant_symbol(db_path: Path, table_name: str, start: str, end: str) -> str:
    """Select the symbol whose data covers the end of the requested range.

    Mirrors the logic in ``backtest_matrix_report.py`` so the replay uses the
    primary continuous-contract series even when the table mixes symbols.
    """
    end_inclusive = str(end)
    if len(end_inclusive) <= 10 and " " not in end_inclusive:
        end_inclusive = f"{end_inclusive} 23:59:59"

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            f"""
            SELECT symbol, MIN(datetime) AS mindt, MAX(datetime) AS maxdt, COUNT(*) AS n
            FROM {table_name}
            WHERE datetime >= ? AND datetime <= ?
            GROUP BY symbol
            """,
            (start, end_inclusive),
        ).fetchall()

    if not rows:
        raise RuntimeError(f"{table_name} has no rows for {start} ~ {end}")

    covering = [row for row in rows if row[2] is not None and str(row[2]) >= str(end)]
    if covering:
        best = max(covering, key=lambda r: (r[3], str(r[2]) if r[2] else ""))
        return str(best[0])

    best = max(rows, key=lambda r: (str(r[2]) if r[2] else "", r[3]))
    return str(best[0])


def _run_symbol_trades(
    db_path: Path,
    symbol: str,
    start: str,
    end: str,
    enable_short: bool,
) -> dict[str, Any]:
    """Run one symbol and return combined trade pairs plus status metadata."""
    table_name = f"{symbol.lower()}_1M_raw"
    try:
        data_symbol = _dominant_symbol(db_path, table_name, start, end)
    except Exception as exc:
        return {
            "status": "unavailable",
            "reason": f"dominant symbol selection failed: {exc}",
            "trades": [],
        }

    engine = BacktestEngine(
        symbol=data_symbol,
        db_path=str(db_path),
        table_name=table_name,
        start_date=start,
        end_date=end,
        enable_short=enable_short,
    )
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            report = engine.run()
    except Exception as exc:
        return {
            "status": "unavailable",
            "reason": f"backtest execution failed: {exc}",
            "trades": [],
        }

    if "error" in report:
        return {
            "status": "unavailable",
            "reason": f"backtest error: {report['error']}",
            "trades": [],
        }

    trades = engine.strategy.get_combined_trades()
    for trade in trades:
        trade["requested_symbol"] = symbol
        trade["data_symbol"] = data_symbol
    return {"status": "ok", "trades": trades, "report": report}


# ---------------------------------------------------------------------------
# Leg runner
# ---------------------------------------------------------------------------

def _snapshot_config() -> dict[str, Any]:
    """Deep-copy ``STRATEGY_CONFIG`` so mutations can be rolled back."""
    return copy.deepcopy(STRATEGY_CONFIG)


@contextlib.contextmanager
def _restore_config() -> Generator[None, None, None]:
    """Preserve ``STRATEGY_CONFIG`` across a block."""
    snapshot = _snapshot_config()
    try:
        yield
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(snapshot)


def _run_leg(
    db_path: Path,
    symbols: list[str],
    start: str,
    end: str,
    enable_short: bool,
) -> dict[str, Any]:
    """Run baseline + current for a list of symbols and compare trades."""
    per_symbol: dict[str, Any] = {}
    all_baseline: list[dict[str, Any]] = []
    all_current: list[dict[str, Any]] = []
    equivalent = True

    for symbol in symbols:
        with _restore_config(), _baseline_factories():
            baseline_result = _run_symbol_trades(
                db_path, symbol, start, end, enable_short
            )

        with _restore_config():
            current_result = _run_symbol_trades(
                db_path, symbol, start, end, enable_short
            )

        if baseline_result["status"] != "ok":
            per_symbol[symbol] = baseline_result
            equivalent = False
            continue
        if current_result["status"] != "ok":
            per_symbol[symbol] = current_result
            equivalent = False
            continue

        diff = _diff_trades(baseline_result["trades"], current_result["trades"])
        per_symbol[symbol] = {
            "status": "ok",
            "baseline_trade_count": len(baseline_result["trades"]),
            "current_trade_count": len(current_result["trades"]),
            "diff": diff,
        }
        all_baseline.extend(baseline_result["trades"])
        all_current.extend(current_result["trades"])

        if (
            diff["summary"]["removed_count"]
            or diff["summary"]["added_count"]
            or diff["summary"]["changed_count"]
        ):
            equivalent = False

    portfolio_diff = _diff_trades(all_baseline, all_current)
    if (
        portfolio_diff["summary"]["removed_count"]
        or portfolio_diff["summary"]["added_count"]
        or portfolio_diff["summary"]["changed_count"]
    ):
        equivalent = False

    return {
        "enable_short": enable_short,
        "symbols": list(symbols),
        "start_date": start,
        "end_date": end,
        "per_symbol": per_symbol,
        "portfolio_diff": portfolio_diff,
        "equivalent": equivalent,
    }


# ---------------------------------------------------------------------------
# Report / CLI
# ---------------------------------------------------------------------------

def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return value


def _build_missing_db_report(
    db_path: Path,
    symbols: list[str],
    enable_short_symbols: list[str],
    start: str,
    end: str,
) -> dict[str, Any]:
    """Build a report when the requested database is missing."""
    unavailable = {
        "status": "unavailable",
        "reason": f"resolved DB does not exist: {db_path}",
    }
    return {
        "disclaimer": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "db_path": str(db_path),
            "start_date": start,
            "end_date": end,
            "symbols": list(symbols),
            "enable_short_symbols": list(enable_short_symbols),
        },
        "long_leg": {
            "enable_short": False,
            "symbols": list(symbols),
            "start_date": start,
            "end_date": end,
            "per_symbol": {symbol: unavailable for symbol in symbols},
            "portfolio_diff": {
                "removed": [],
                "added": [],
                "changed": [],
                "unchanged_count": 0,
                "summary": {
                    "removed_count": 0,
                    "added_count": 0,
                    "changed_count": 0,
                    "unchanged_count": 0,
                },
            },
            "equivalent": False,
        },
        "short_leg": {
            "enable_short": True,
            "symbols": list(enable_short_symbols),
            "start_date": start,
            "end_date": end,
            "per_symbol": {symbol: unavailable for symbol in enable_short_symbols},
            "portfolio_diff": {
                "removed": [],
                "added": [],
                "changed": [],
                "unchanged_count": 0,
                "summary": {
                    "removed_count": 0,
                    "added_count": 0,
                    "changed_count": 0,
                    "unchanged_count": 0,
                },
            },
            "equivalent": False,
        },
        "equivalent": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 1 equivalence proof for A37 dead-factor removal."
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help="Long-only leg symbols (>=2 recommended).",
    )
    parser.add_argument(
        "--enable-short-symbols",
        nargs="+",
        default=DEFAULT_ENABLE_SHORT_SYMBOLS,
        help="Short-enabled leg symbols (>=1 required).",
    )
    parser.add_argument(
        "--start-date",
        default=DEFAULT_START,
        help="Start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        default=DEFAULT_END,
        help="End date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(SQLITE_DB_PATH),
        help="SQLite database path.",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path(__file__).with_name("phase1_dead_factor_equivalence.json"),
        help="Path for the JSON report.",
    )
    args = parser.parse_args(argv)

    if not args.db_path.exists():
        report = _build_missing_db_report(
            args.db_path,
            args.symbols,
            args.enable_short_symbols,
            args.start_date,
            args.end_date,
        )
        args.out_json.write_text(
            json.dumps(_json_safe(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Missing database: {args.db_path}")
        return 1

    long_leg = _run_leg(
        args.db_path, args.symbols, args.start_date, args.end_date, enable_short=False
    )
    short_leg = _run_leg(
        args.db_path,
        args.enable_short_symbols,
        args.start_date,
        args.end_date,
        enable_short=True,
    )

    report = {
        "disclaimer": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "db_path": str(args.db_path),
            "start_date": args.start_date,
            "end_date": args.end_date,
            "symbols": list(args.symbols),
            "enable_short_symbols": list(args.enable_short_symbols),
        },
        "long_leg": long_leg,
        "short_leg": short_leg,
        "equivalent": long_leg["equivalent"] and short_leg["equivalent"],
    }

    args.out_json.write_text(
        json.dumps(_json_safe(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if report["equivalent"]:
        print("Phase 1 equivalence: EMPTY DIFF (dead-factor removal is behavior-neutral).")
        return 0

    print("Phase 1 equivalence: DIFF DETECTED or data unavailable.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
