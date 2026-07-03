"""Replay real 1-minute K-line data through the CZSC/signal pipeline.

This script generates a JSON artifact containing the divergence-status signal
for every trade-frequency bar. It does **not** call BacktestEngine.run(), send
orders, or connect to any broker.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

# czsc is a required third-party dependency
try:
    from czsc import CZSC
    from czsc.objects import Freq
except Exception as exc:  # pragma: no cover - environment guard
    print(f"Error: czsc library is required but could not be imported: {exc}")
    sys.exit(1)

# Make the czsc_strategy package importable when this script is run directly
CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(CZSC_STRATEGY_ROOT))

try:
    from chan_strategy.config import (
        BACKTEST_CONFIG,
        SIGNAL_VERSION,
        SQLITE_DB_PATH,
        STRATEGY_CONFIG,
    )
    from chan_strategy.data_adapter import SqliteDataAdapter, resample_bars
    from chan_strategy.signals import signal_divergence_status
except Exception as exc:  # pragma: no cover - environment guard
    print(f"Error: failed to import chan_strategy modules: {exc}")
    traceback.print_exc()
    sys.exit(1)


DEFAULT_SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent

TRADE_FREQ = STRATEGY_CONFIG.get("trade_freq", "30分钟")
FILTER_FREQ = STRATEGY_CONFIG.get("filter_freq", "日线")


_FNAME_DATE_FMT = "%Y%m%d"


def _freq_name_to_czsc_freq(freq_name: str) -> Freq:
    """Map a Chinese frequency name to a czsc Freq object."""
    mapping = {
        "1分钟": Freq.F1,
        "5分钟": Freq.F5,
        "15分钟": Freq.F15,
        "30分钟": Freq.F30,
        "60分钟": Freq.F60,
        "120分钟": Freq.F120,
        "日线": Freq.D,
        "周线": Freq.W,
        "月线": Freq.M,
    }
    return mapping.get(freq_name, Freq.F30)


def _freq_name_to_minutes(freq_name: str) -> int:
    """Map a Chinese frequency name to its length in minutes."""
    mapping = {
        "1分钟": 1,
        "5分钟": 5,
        "15分钟": 15,
        "30分钟": 30,
        "60分钟": 60,
        "120分钟": 120,
    }
    return mapping.get(freq_name, 30)


def _resolve_db_path(db_path: str | Path | None) -> Path | None:
    """Resolve the SQLite DB path using the project precedence chain.

    Precedence:
      1. Explicit ``db_path`` argument.
      2. ``CHAN_SQLITE_DB_PATH`` environment variable.
      3. ``chan_strategy.config.SQLITE_DB_PATH``.
    """
    if db_path is not None:
        return Path(db_path)

    env_path = os.getenv("CHAN_SQLITE_DB_PATH")
    if env_path:
        return Path(env_path)

    if SQLITE_DB_PATH:
        return Path(SQLITE_DB_PATH)

    return None


def _find_symbol_table(adapter: SqliteDataAdapter, symbol: str) -> str | None:
    """Locate the raw-data table for ``symbol``.

    Reuses the matching strategy from ``BacktestEngine._find_table`` but prefers
    the 1-minute raw table when the DB contains multiple frequency tables for the
    same symbol. Returns ``None`` instead of raising when no unique table is found.
    """
    tables = adapter.get_tables()
    if not tables:
        return None

    norm_symbol = symbol.lower().strip()
    priority_patterns = [
        f"{norm_symbol}_1m_raw",
        f"{norm_symbol}_1min_raw",
    ]

    # 1. Prefer an exact 1-minute match first.
    for pattern in priority_patterns:
        candidates = [table for table in tables if table.lower().strip() == pattern]
        if len(candidates) == 1:
            return candidates[0]

    # 2. Other exact matches (5M, generic raw, symbol itself).
    exact_patterns = [
        f"{norm_symbol}_5m_raw",
        f"{norm_symbol}_5min_raw",
        f"{norm_symbol}_raw",
        norm_symbol,
    ]
    exact_candidates = [
        table for table in tables if table.lower().strip() in exact_patterns
    ]
    if exact_candidates:
        return exact_candidates[0] if len(exact_candidates) == 1 else None

    # 3. Prefix matches; again prefer a 1-minute table.
    prefix_candidates = [
        table for table in tables if table.lower().strip().startswith(norm_symbol + "_")
    ]
    if prefix_candidates:
        for pattern in priority_patterns:
            candidates = [
                table for table in prefix_candidates if table.lower().strip() == pattern
            ]
            if len(candidates) == 1:
                return candidates[0]
        return prefix_candidates[0] if len(prefix_candidates) == 1 else None

    return None


def _extract_divergence_record(
    signals: dict[str, str],
    bar_dt: datetime,
    symbol: str,
    price: float,
    data_version: str,
) -> dict[str, Any]:
    """Build a flat signal-history record from a divergence-status signal dict."""
    signal_key = None
    signal_value = None
    for key, value in signals.items():
        if "背驰" in key:
            signal_key = key
            signal_value = value
            break

    if signal_key is None or signal_value is None:
        # Defensive fallback: should never happen for signal_divergence_status
        signal_key = f"{TRADE_FREQ}_D1BI_背驰{data_version}"
        signal_value = "无_任意_任意_0"

    divergence_status = str(signal_value).split("_")[0]
    return {
        "dt": bar_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": symbol,
        "price": float(price),
        "signal": f"{signal_key}_{signal_value}",
        "signal_key": signal_key,
        "signal_value": signal_value,
        "divergence_status": divergence_status,
        "source": "real_bar_replay",
        "data_version": data_version,
    }


def _replay_symbol(
    symbol: str,
    adapter: SqliteDataAdapter,
    start_date: str,
    end_date: str,
    trade_freq_name: str,
    filter_freq_name: str | None,
    warmup_bars: int,
    data_version: str,
) -> list[dict[str, Any]]:
    """Replay one symbol's 1-minute data and return per-bar signal records."""
    table = _find_symbol_table(adapter, symbol)
    if table is None:
        print(f"  [{symbol}] no unique raw table found; skipping")
        return []

    raw_bars = adapter.load_raw_bars(
        symbol=symbol,
        freq="1",
        start_date=start_date,
        end_date=end_date,
        table_name=table,
    )
    if not raw_bars:
        # Some tables store the symbol column in lowercase (e.g. "rb888").
        raw_bars = adapter.load_raw_bars(
            symbol=symbol.lower(),
            freq="1",
            start_date=start_date,
            end_date=end_date,
            table_name=table,
        )
    if not raw_bars:
        print(f"  [{symbol}] no 1-minute bars loaded from {table}; skipping")
        return []

    trade_freq_obj = _freq_name_to_czsc_freq(trade_freq_name)
    trade_minutes = _freq_name_to_minutes(trade_freq_name)
    trade_bars = resample_bars(raw_bars, trade_freq_obj, trade_minutes)
    if len(trade_bars) < warmup_bars + 1:
        print(
            f"  [{symbol}] insufficient {trade_freq_name} bars "
            f"({len(trade_bars)} < {warmup_bars + 1}); skipping"
        )
        return []

    daily_bars: list[Any] = []
    czsc_daily: CZSC | None = None
    enable_daily_filter = False
    if filter_freq_name == "日线":
        daily_bars = resample_bars(raw_bars, Freq.D, target_minutes=None)
        warmup_dt = trade_bars[warmup_bars - 1].dt
        daily_warmup_bars = [b for b in daily_bars if b.dt <= warmup_dt]
        if len(daily_warmup_bars) >= 3:
            czsc_daily = CZSC(daily_warmup_bars)
            enable_daily_filter = True

    czsc_trade = CZSC(trade_bars[:warmup_bars])
    daily_bar_idx = len([b for b in daily_bars if b.dt <= warmup_dt]) if daily_bars else 0

    records: list[dict[str, Any]] = []
    for i in range(warmup_bars, len(trade_bars)):
        bar = trade_bars[i]
        czsc_trade.update(bar)

        if enable_daily_filter and czsc_daily is not None:
            while daily_bar_idx < len(daily_bars) and daily_bars[daily_bar_idx].dt <= bar.dt:
                czsc_daily.update(daily_bars[daily_bar_idx])
                daily_bar_idx += 1

        signals = signal_divergence_status(czsc_trade, trade_freq_name)
        records.append(
            _extract_divergence_record(
                signals,
                bar.dt,
                symbol,
                float(bar.close),
                data_version,
            )
        )

    print(
        f"  [{symbol}] generated {len(records)} records from "
        f"{len(raw_bars)} 1m bars ({len(trade_bars)} {trade_freq_name} bars)"
    )
    return records


def generate_signal_history(
    db_path: str | Path | None,
    symbols: list[str],
    start_date: str,
    end_date: str,
    output_dir: Path,
    combined: bool = False,
    warmup_bars: int = 100,
    max_file_mb: float = 50.0,
) -> list[Path]:
    """Replay the requested symbols and write JSON signal-history artifacts."""
    resolved_db = _resolve_db_path(db_path)
    if resolved_db is None:
        raise RuntimeError("No SQLite DB path could be resolved")
    if not resolved_db.exists():
        raise FileNotFoundError(f"Resolved DB does not exist: {resolved_db}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data_version = SIGNAL_VERSION
    trade_freq_name = TRADE_FREQ
    filter_freq_name = FILTER_FREQ if STRATEGY_CONFIG.get("filter_freq") == "日线" else None

    written: list[Path] = []
    all_records: list[dict[str, Any]] = []
    adapter = SqliteDataAdapter(str(resolved_db))
    try:
        for symbol in symbols:
            records = _replay_symbol(
                symbol=symbol,
                adapter=adapter,
                start_date=start_date,
                end_date=end_date,
                trade_freq_name=trade_freq_name,
                filter_freq_name=filter_freq_name,
                warmup_bars=warmup_bars,
                data_version=data_version,
            )
            if not combined:
                fname = f"signal_history_{symbol}_{start_date.replace('-', '')}_{end_date.replace('-', '')}.json"
                path = output_dir / fname
                _write_json_records(path, records, max_file_mb=max_file_mb)
                written.append(path)
            else:
                all_records.extend(records)

        if combined:
            fname = (
                f"signal_history_{data_version}_"
                f"{start_date.replace('-', '')}_{end_date.replace('-', '')}.json"
            )
            path = output_dir / fname
            _write_json_records(path, all_records, max_file_mb=max_file_mb)
            written.append(path)
    finally:
        adapter.close()

    return written


def _write_json_records(
    path: Path,
    records: list[dict[str, Any]],
    max_file_mb: float = 50.0,
) -> None:
    """Serialize records to JSON, guarding against oversized artifacts."""
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    max_bytes = max_file_mb * 1024 * 1024
    if len(payload.encode("utf-8")) > max_bytes:
        raise RuntimeError(
            f"Artifact {path.name} exceeds {max_file_mb} MB; "
            "reduce the date range or increase --max-file-mb"
        )
    path.write_text(payload, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay 1-minute bars through the CZSC divergence-status signal pipeline."
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated list of continuous-contract symbols to replay.",
    )
    parser.add_argument(
        "--start-date",
        default=BACKTEST_CONFIG["start_date"],
        help="Start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        default=BACKTEST_CONFIG["end_date"],
        help="End date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where JSON artifacts are written.",
    )
    parser.add_argument(
        "--combined",
        action="store_true",
        help="Write a single combined JSON file instead of one per symbol.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Override the SQLite DB path.",
    )
    parser.add_argument(
        "--warmup-bars",
        type=int,
        default=100,
        help="Number of trade-frequency bars used to warm up the CZSC object.",
    )
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=50.0,
        help="Maximum artifact size in megabytes.",
    )
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    written = generate_signal_history(
        db_path=args.db_path,
        symbols=symbols,
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=args.output_dir,
        combined=args.combined,
        warmup_bars=args.warmup_bars,
        max_file_mb=args.max_file_mb,
    )

    for path in written:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
