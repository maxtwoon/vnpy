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


def upsert_bars_to_sqlite(db_path: Path, bars: list[dict[str, Any]]) -> dict[str, Any]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat(sep=" ", timespec="seconds")
    with sqlite3.connect(db_path) as conn:
        _ensure_meta_table(conn)
        for bar in bars:
            table = f"{str(bar['symbol']).lower()}_1M_raw"
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
        conn.commit()
    return {
        "db_path": str(db_path),
        "bars": len(bars),
        "inserted_or_replaced": len(bars),
    }


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
    args = parser.parse_args(argv)

    payload = load_json(args.simnow_json)
    bars = aggregate_ticks_to_1m(payload)
    write_summary = upsert_bars_to_sqlite(args.db_path, bars)
    summary = summarize_bars(args.db_path, bars, payload, min_bars_per_symbol=args.min_bars_per_symbol)
    summary.update(write_summary)
    summary["simnow_json"] = str(args.simnow_json)
    if args.summary_json:
        write_json(args.summary_json, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
