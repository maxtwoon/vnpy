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
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from chan_strategy.config import SQLITE_DB_PATH  # noqa: E402
from simnow_contract_map_meta import enabled_symbols as enabled_symbols_from_payload, load_contract_map_payload  # noqa: E402

DEFAULT_CONTRACT_MAP = HERE / "simnow_contract_map.json"


def load_enabled_symbols(contract_map_path: Path = DEFAULT_CONTRACT_MAP) -> list[str]:
    return enabled_symbols_from_payload(load_contract_map_payload(contract_map_path))


def table_ranges(db_path: Path, symbols: list[str]) -> dict[str, dict[str, Any]]:
    ranges: dict[str, dict[str, Any]] = {}
    with sqlite3.connect(db_path) as conn:
        for symbol in symbols:
            table = f"{symbol.lower()}_1M_raw"
            try:
                min_dt, max_dt, rows = conn.execute(
                    f"SELECT MIN(datetime), MAX(datetime), COUNT(*) FROM {table}"
                ).fetchone()
                ranges[symbol] = {
                    "table": table,
                    "min_datetime": min_dt,
                    "max_datetime": max_dt,
                    "rows": rows,
                }
            except Exception as exc:
                ranges[symbol] = {
                    "table": table,
                    "error": str(exc),
                }
    return ranges


def latest_date(ranges: dict[str, dict[str, Any]]) -> str:
    dates = [
        str(row.get("max_datetime", ""))[:10]
        for row in ranges.values()
        if row.get("max_datetime")
    ]
    return max(dates) if dates else ""


def build_readiness(db_path: Path, date_text: str, symbols: list[str]) -> dict[str, Any]:
    datetime.strptime(date_text, "%Y-%m-%d")
    ranges = table_ranges(db_path, symbols)
    latest = latest_date(ranges)
    missing = [
        symbol
        for symbol, row in ranges.items()
        if not row.get("max_datetime") or str(row.get("max_datetime"))[:10] < date_text
    ]
    return {
        "date": date_text,
        "db_path": str(db_path),
        "latest_db_date": latest,
        "ready": bool(latest and latest >= date_text and not missing),
        "missing_or_lagged_symbols": missing,
        "table_ranges": ranges,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether historical DB can support same-day SimNow replay.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--date", required=True)
    parser.add_argument("--symbols", nargs="+")
    args = parser.parse_args()

    symbols = args.symbols or load_enabled_symbols()
    payload = build_readiness(args.db_path, args.date, symbols)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
