from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chan_strategy.config import SQLITE_DB_PATH  # noqa: E402
from simnow_monitor_config import SIMNOW_MONITOR_CONFIG  # noqa: E402


_FLOAT_TOLERANCE = 1e-9

DEFAULT_OUT_DB = Path(SQLITE_DB_PATH)


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def _minute_text(dt: datetime) -> str:
    return dt.replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _contract_lookup(contract_map: dict[str, Any]) -> dict[tuple[str, str], str]:
    lookup = {}
    for research_symbol, row in contract_map.items():
        if not isinstance(row, dict) or not row.get("enabled", True):
            continue
        symbol = str(row.get("symbol") or "").lower()
        exchange = str(row.get("exchange") or "").upper()
        if symbol and exchange:
            lookup[(symbol, exchange)] = str(research_symbol).upper()
    return lookup


def _expected_symbols(payload: dict[str, Any]) -> list[str]:
    contract_map = payload.get("meta", {}).get("contract_map") or {}
    symbols = [
        str(research_symbol).upper()
        for research_symbol, row in contract_map.items()
        if isinstance(row, dict) and row.get("enabled", True)
    ]
    return sorted(symbols)


def _tick_key(tick: dict[str, Any]) -> tuple[str, str]:
    return (
        str(tick.get("symbol") or "").lower(),
        str(tick.get("exchange") or "").upper(),
    )


def aggregate_ticks_to_1m(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Aggregate SimNow CTP ticks into research-symbol 1M OHLC bars.

    Tick volume is cumulative intraday volume, so bar volume is calculated from
    positive deltas between consecutive ticks of the same contract. A one-tick
    bar has zero volume because there is no previous observation to prove the
    minute's traded volume.
    """
    contract_map = payload.get("meta", {}).get("contract_map") or {}
    lookup = _contract_lookup(contract_map)
    ticks = payload.get("raw", {}).get("ticks") or []
    parsed = []
    for tick in ticks:
        key = _tick_key(tick)
        research_symbol = lookup.get(key)
        price = tick.get("last_price")
        dt_value = tick.get("dt")
        if not research_symbol or price is None or not dt_value:
            continue
        dt = _parse_dt(str(dt_value))
        parsed.append({
            "dt": dt,
            "minute": _minute_text(dt),
            "research_symbol": research_symbol,
            "source_symbol": str(tick.get("symbol") or ""),
            "exchange": str(tick.get("exchange") or ""),
            "vt_symbol": str(tick.get("vt_symbol") or f"{tick.get('symbol')}.{tick.get('exchange')}"),
            "price": float(price),
            "volume": float(tick.get("volume") or 0.0),
        })
    parsed.sort(key=lambda row: (row["research_symbol"], row["dt"]))

    groups: dict[tuple[str, str], dict[str, Any]] = {}
    last_volume_by_contract: dict[tuple[str, str], float] = {}
    order: list[tuple[str, str]] = []
    for row in parsed:
        contract_key = (row["source_symbol"].lower(), row["exchange"].upper())
        group_key = (row["research_symbol"], row["minute"])
        if group_key not in groups:
            groups[group_key] = {
                "datetime": row["minute"],
                "symbol": row["research_symbol"],
                "open": row["price"],
                "high": row["price"],
                "low": row["price"],
                "close": row["price"],
                "volume": 0.0,
                "amount": 0.0,
                "source": "simnow_tick_agg",
                "source_symbol": row["source_symbol"],
                "exchange": row["exchange"],
                "vt_symbol": row["vt_symbol"],
                "tick_count": 0,
            }
            order.append(group_key)
        bar = groups[group_key]
        bar["high"] = max(float(bar["high"]), row["price"])
        bar["low"] = min(float(bar["low"]), row["price"])
        bar["close"] = row["price"]
        bar["tick_count"] += 1
        previous_volume = last_volume_by_contract.get(contract_key)
        if previous_volume is not None:
            bar["volume"] += max(row["volume"] - previous_volume, 0.0)
        last_volume_by_contract[contract_key] = row["volume"]

    return [groups[key] for key in sorted(order, key=lambda item: (item[1], item[0]))]


def _ensure_bar_table(conn: sqlite3.Connection, table: str) -> None:
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {table} (
            datetime TEXT NOT NULL,
            symbol TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            amount REAL NOT NULL,
            PRIMARY KEY (datetime, symbol)
        )"""
    )


def _ensure_meta_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS simnow_bar_meta (
            datetime TEXT NOT NULL,
            symbol TEXT NOT NULL,
            source TEXT NOT NULL,
            source_symbol TEXT NOT NULL,
            exchange TEXT NOT NULL,
            vt_symbol TEXT NOT NULL,
            tick_count INTEGER NOT NULL,
            generated_at TEXT NOT NULL,
            PRIMARY KEY (datetime, symbol)
        )"""
    )


def _raw_table(symbol: str) -> str:
    return f"{str(symbol).lower()}_1M_raw"


def _staging_table(symbol: str) -> str:
    return f"{str(symbol).lower()}_1M_raw_staging"


def _bars_date_range(bars: list[dict[str, Any]]) -> tuple[str, str]:
    datetimes = [str(bar["datetime"]) for bar in bars]
    return (min(datetimes), max(datetimes)) if datetimes else ("", "")


def _rows_close_enough(left: tuple[Any, ...], right: tuple[Any, ...]) -> bool:
    """Compare two row tuples (datetime, symbol, open, high, low, close, volume, amount)."""
    if len(left) < 7 or len(right) < 7:
        return False
    for idx in (2, 3, 4, 5, 6):  # open, high, low, close, volume
        if abs(float(left[idx]) - float(right[idx])) > _FLOAT_TOLERANCE:
            return False
    return True


def upsert_bars_to_sqlite(
    db_path: Path,
    bars: list[dict[str, Any]],
    *,
    kline_write_mode: str = "staging",
    allow_direct_write: bool = False,
) -> dict[str, Any]:
    """Write SimNow-derived 1M bars to SQLite.

    Default ``kline_write_mode="staging"`` writes to
    ``{symbol}_1M_raw_staging`` and never touches ``{symbol}_1M_raw``.
    ``kline_write_mode="direct"`` requires the additional
    ``allow_direct_write=True`` flag and writes directly to the raw table
    (legacy opt-out, for A/B diffing only).
    """
    if kline_write_mode == "direct" and not allow_direct_write:
        raise ValueError(
            "kline_write_mode='direct' requires allow_direct_write=True "
            "(pass --allow-direct-write on the CLI)."
        )
    db_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat(sep=" ", timespec="seconds")
    written = 0
    with sqlite3.connect(db_path) as conn:
        _ensure_meta_table(conn)
        for bar in bars:
            symbol = str(bar["symbol"])
            if kline_write_mode == "direct":
                table = _raw_table(symbol)
            else:
                table = _staging_table(symbol)
            _ensure_bar_table(conn, table)
            conn.execute(
                f"""INSERT OR REPLACE INTO {table}
                (datetime, symbol, open, high, low, close, volume, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    bar["datetime"],
                    bar["symbol"],
                    bar["open"],
                    bar["high"],
                    bar["low"],
                    bar["close"],
                    bar["volume"],
                    bar["amount"],
                ),
            )
            conn.execute(
                """INSERT OR REPLACE INTO simnow_bar_meta
                (datetime, symbol, source, source_symbol, exchange, vt_symbol, tick_count, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    bar["datetime"],
                    bar["symbol"],
                    bar["source"],
                    bar["source_symbol"],
                    bar["exchange"],
                    bar["vt_symbol"],
                    int(bar["tick_count"]),
                    generated_at,
                ),
            )
            written += 1
        conn.commit()
    return {
        "db_path": str(db_path),
        "bars": len(bars),
        "inserted_or_replaced": written,
        "kline_write_mode": kline_write_mode,
    }


def promote_staged_bars(
    db_path: Path,
    symbol: str,
    date_range: tuple[str, str],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Promote staged 1M bars into the primary ``{symbol}_1M_raw`` table.

    Defaults to ``dry_run=True``: it returns a diff summary without writing.
    Only ``dry_run=False`` performs the ``INSERT OR REPLACE``. The staging
    table is left untouched so the operation is reviewable.
    """
    raw_table = _raw_table(symbol)
    staging_table = _staging_table(symbol)
    start_dt, end_dt = date_range
    summary: dict[str, Any] = {
        "db_path": str(db_path),
        "symbol": symbol,
        "raw_table": raw_table,
        "staging_table": staging_table,
        "date_range": [start_dt, end_dt],
        "dry_run": dry_run,
        "staged_count": 0,
        "raw_count_before": 0,
        "overlapping_rows": 0,
        "materially_different_overwrites": 0,
        "promoted_count": 0,
    }
    with sqlite3.connect(db_path) as conn:
        # Verify staging table exists
        staging_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (staging_table,),
        ).fetchone()
        if not staging_exists:
            summary["reason"] = "staging_table_missing"
            return summary

        raw_exists = bool(conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (raw_table,),
        ).fetchone())
        if not dry_run:
            _ensure_bar_table(conn, raw_table)

        staged_rows = conn.execute(
            f"""SELECT datetime, symbol, open, high, low, close, volume, amount
                FROM {staging_table}
                WHERE datetime >= ? AND datetime <= ?
                ORDER BY datetime""",
            (start_dt, end_dt),
        ).fetchall()
        summary["staged_count"] = len(staged_rows)

        raw_rows = conn.execute(
            f"""SELECT datetime, symbol, open, high, low, close, volume, amount
                FROM {raw_table}
                ORDER BY datetime""",
        ).fetchall() if raw_exists else []
        summary["raw_count_before"] = len(raw_rows)

        raw_by_key = {(row[0], row[1]): row for row in raw_rows}
        different_overwrites: list[dict[str, Any]] = []
        for row in staged_rows:
            key = (row[0], row[1])
            if key in raw_by_key:
                summary["overlapping_rows"] += 1
                if not _rows_close_enough(row, raw_by_key[key]):
                    summary["materially_different_overwrites"] += 1
                    different_overwrites.append({
                        "datetime": row[0],
                        "symbol": row[1],
                        "staged": {
                            "open": row[2],
                            "high": row[3],
                            "low": row[4],
                            "close": row[5],
                            "volume": row[6],
                            "amount": row[7],
                        },
                        "existing": {
                            "open": raw_by_key[key][2],
                            "high": raw_by_key[key][3],
                            "low": raw_by_key[key][4],
                            "close": raw_by_key[key][5],
                            "volume": raw_by_key[key][6],
                            "amount": raw_by_key[key][7],
                        },
                    })

        if dry_run:
            summary["materially_different_overwrites_details"] = different_overwrites
            return summary

        conn.execute(
            f"""INSERT OR REPLACE INTO {raw_table}
            (datetime, symbol, open, high, low, close, volume, amount)
            SELECT datetime, symbol, open, high, low, close, volume, amount
            FROM {staging_table}
            WHERE datetime >= ? AND datetime <= ?""",
            (start_dt, end_dt),
        )
        summary["promoted_count"] = conn.total_changes
        conn.commit()
    return summary


def summarize_bars(
    db_path: Path,
    bars: list[dict[str, Any]],
    payload: dict[str, Any],
    min_bars_per_symbol: int = 1,
) -> dict[str, Any]:
    expected = _expected_symbols(payload)
    symbols = sorted({str(bar["symbol"]) for bar in bars})
    coverage: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        symbol_bars = [bar for bar in bars if bar["symbol"] == symbol]
        coverage[symbol] = {
            "bars": len(symbol_bars),
            "tick_count": sum(int(bar.get("tick_count", 0)) for bar in symbol_bars),
            "start_datetime": min(bar["datetime"] for bar in symbol_bars),
            "end_datetime": max(bar["datetime"] for bar in symbol_bars),
        }
    short_symbols = [
        symbol
        for symbol in symbols
        if int(coverage[symbol]["bars"]) < min_bars_per_symbol
    ]
    return {
        "db_path": str(db_path),
        "bars": len(bars),
        "symbols": symbols,
        "expected_symbols": expected,
        "missing_symbols": sorted(set(expected) - set(symbols)),
        "short_symbols": short_symbols,
        "min_bars_per_symbol": min_bars_per_symbol,
        "coverage_by_symbol": coverage,
        "start_datetime": min((bar["datetime"] for bar in bars), default=""),
        "end_datetime": max((bar["datetime"] for bar in bars), default=""),
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Aggregate SimNow capture ticks into local 1M replay bars.")
    parser.add_argument("--simnow-json", type=Path, required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_OUT_DB)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--min-bars-per-symbol", type=int, default=1)
    parser.add_argument(
        "--kline-write-mode",
        choices=["staging", "direct"],
        default=SIMNOW_MONITOR_CONFIG["kline_write_mode"],
        help="Where to write aggregated bars (default: staging).",
    )
    parser.add_argument(
        "--allow-direct-write",
        action="store_true",
        help="Required additional flag to actually use kline_write_mode=direct.",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Promote staged bars into {symbol}_1M_raw (default dry_run=True).",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="With --promote, actually perform the INSERT OR REPLACE.",
    )
    args = parser.parse_args(argv)

    payload = load_json(args.simnow_json)
    bars = aggregate_ticks_to_1m(payload)

    if args.promote:
        # Stage first so --promote operates on the current capture's staged bars.
        stage_summary = upsert_bars_to_sqlite(args.db_path, bars, kline_write_mode="staging")
        symbols = sorted({str(bar["symbol"]) for bar in bars})
        start_dt, end_dt = _bars_date_range(bars)
        summaries = []
        for symbol in symbols:
            summaries.append(promote_staged_bars(
                args.db_path,
                symbol,
                (start_dt, end_dt),
                dry_run=not args.no_dry_run,
            ))
        summary = {
            "db_path": str(args.db_path),
            "simnow_json": str(args.simnow_json),
            "promote": True,
            "dry_run": not args.no_dry_run,
            "symbols": symbols,
            "date_range": [start_dt, end_dt],
            "stage_summary": stage_summary,
            "promote_summaries": summaries,
        }
    else:
        write_summary = upsert_bars_to_sqlite(
            args.db_path,
            bars,
            kline_write_mode=args.kline_write_mode,
            allow_direct_write=args.allow_direct_write,
        )
        summary = summarize_bars(args.db_path, bars, payload, min_bars_per_symbol=args.min_bars_per_symbol)
        summary.update(write_summary)
        summary["simnow_json"] = str(args.simnow_json)
    if args.summary_json:
        write_json(args.summary_json, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
