"""Phase 0 diagnostic: exit-event reachability on real 1-minute bars.

This script replays real 1-minute bars per symbol through the existing CZSC
signal pipeline and evaluates the six structural exit events three ways:

- ``legacy_fired``: current ``Event.is_match`` result.
- ``struct_alone``: event-level signals satisfied, but no factor matched.
- ``factor_alone``: at least one factor matched, but event-level signals not
  satisfied.

It is read-only: no orders, no broker calls, no position state mutations.
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
    from chan_strategy.config import BACKTEST_CONFIG, SIGNAL_VERSION, SQLITE_DB_PATH, STRATEGY_CONFIG
    from chan_strategy.data_adapter import SqliteDataAdapter, resample_bars
    from chan_strategy.positions import (
        Event,
        create_first_buy_position,
        create_first_sell_position,
        create_second_buy_position,
        create_second_sell_position,
        create_third_buy_position,
        create_third_sell_position,
    )
    from chan_strategy.sell_signals import signal_short_risk_control
    from chan_strategy.signals import (
        signal_bi_direction,
        signal_divergence_status,
        signal_risk_control,
        signal_zs_position,
    )
except Exception as exc:  # pragma: no cover - environment guard
    print(f"Error: failed to import chan_strategy modules: {exc}")
    traceback.print_exc()
    sys.exit(1)


DEFAULT_SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent

TRADE_FREQ = STRATEGY_CONFIG.get("trade_freq", "30分钟")
FILTER_FREQ = STRATEGY_CONFIG.get("filter_freq", "日线")

DISCLAIMER = "Diagnostic only, not a trading recommendation."
DEAD_SIGNAL_VALUE = "失效"
DEAD_SIGNAL_COUNT_KEY = f"{TRADE_FREQ}_D1BI_背驰{SIGNAL_VERSION}_{DEAD_SIGNAL_VALUE}"

_FNAME_DATE_FMT = "%Y-%m-%d"


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


def event_signals_match(event: Event, signals_dict: dict) -> bool:
    """Return whether an event's event-level signal gates are satisfied.

    Mirrors ``Event.is_match`` but ignores factors.
    """
    if event.signals_all:
        if not all(s.is_match(signals_dict) for s in event.signals_all):
            return False
    if event.signals_any:
        if not any(s.is_match(signals_dict) for s in event.signals_any):
            return False
    if event.signals_not:
        if any(s.is_match(signals_dict) for s in event.signals_not):
            return False
    return True


def event_factors_match(event: Event, signals_dict: dict) -> bool:
    """Return whether at least one of the event's factors matches."""
    if not event.factors:
        return False
    return any(f.is_match(signals_dict) for f in event.factors)


def evaluate_exit_event_three_way(
    event: Event,
    signals_dict: dict,
) -> dict[str, bool]:
    """Evaluate a single exit event in the three required dimensions.

    Returns a dict with ``legacy_fired``, ``struct_alone``, and ``factor_alone``.
    """
    legacy_fired = event.is_match(signals_dict)
    signals_ok = event_signals_match(event, signals_dict)
    factors_ok = event_factors_match(event, signals_dict)

    struct_alone = signals_ok and not factors_ok
    factor_alone = factors_ok and not signals_ok

    return {
        "legacy_fired": legacy_fired,
        "struct_alone": struct_alone,
        "factor_alone": factor_alone,
    }


def build_exit_events(symbol: str, freq: str = TRADE_FREQ) -> list[Event]:
    """Return the six structural exit events for ``symbol``."""
    positions = [
        create_first_buy_position(symbol, freq),
        create_second_buy_position(symbol, freq),
        create_third_buy_position(symbol, freq),
        create_first_sell_position(symbol, freq),
        create_second_sell_position(symbol, freq),
        create_third_sell_position(symbol, freq),
    ]
    events: list[Event] = []
    for position in positions:
        events.extend(position.exits)
    return events


def build_signal_dict(
    czsc_trade: CZSC,
    trade_freq_name: str,
) -> dict[str, str]:
    """Build the per-bar signal dictionary used by exit events."""
    signals: dict[str, str] = {}
    signals.update(signal_risk_control(czsc_trade, trade_freq_name))
    signals.update(signal_short_risk_control(czsc_trade, trade_freq_name))
    signals.update(signal_bi_direction(czsc_trade, trade_freq_name))
    signals.update(signal_zs_position(czsc_trade, trade_freq_name))
    signals.update(signal_divergence_status(czsc_trade, trade_freq_name))
    return signals


def _count_dead_signal(signals_dict: dict[str, str]) -> int:
    """Count occurrences of the dead ``背驰*_失效`` classification."""
    divergence_key = f"{TRADE_FREQ}_D1BI_背驰{SIGNAL_VERSION}"
    value = signals_dict.get(divergence_key, "")
    return 1 if value.startswith(DEAD_SIGNAL_VALUE) else 0


def _replay_symbol(
    symbol: str,
    adapter: SqliteDataAdapter,
    start_date: str,
    end_date: str,
    trade_freq_name: str,
    warmup_bars: int,
    exit_events: list[Event],
) -> dict[str, Any]:
    """Replay one symbol and return aggregated reachability statistics."""
    table = _find_symbol_table(adapter, symbol)
    if table is None:
        return {"status": "unavailable", "reason": f"no unique raw table found for {symbol}"}

    raw_bars = adapter.load_raw_bars(
        symbol=symbol,
        freq="1",
        start_date=start_date,
        end_date=end_date,
        table_name=table,
    )
    if not raw_bars:
        raw_bars = adapter.load_raw_bars(
            symbol=symbol.lower(),
            freq="1",
            start_date=start_date,
            end_date=end_date,
            table_name=table,
        )
    if not raw_bars:
        return {
            "status": "unavailable",
            "reason": f"no 1-minute bars loaded from {table} for {symbol}",
        }

    trade_freq_obj = _freq_name_to_czsc_freq(trade_freq_name)
    trade_minutes = _freq_name_to_minutes(trade_freq_name)
    trade_bars = resample_bars(raw_bars, trade_freq_obj, trade_minutes)
    if len(trade_bars) < warmup_bars + 1:
        return {
            "status": "unavailable",
            "reason": (
                f"insufficient {trade_freq_name} bars for {symbol} "
                f"({len(trade_bars)} < {warmup_bars + 1})"
            ),
        }

    czsc_trade = CZSC(trade_bars[:warmup_bars])

    event_names = [event.name for event in exit_events]
    counts: dict[str, dict[str, int]] = {
        name: {"legacy_fired": 0, "struct_alone": 0, "factor_alone": 0}
        for name in event_names
    }
    dead_signal_count = 0

    for i in range(warmup_bars, len(trade_bars)):
        bar = trade_bars[i]
        czsc_trade.update(bar)
        signals_dict = build_signal_dict(czsc_trade, trade_freq_name)
        dead_signal_count += _count_dead_signal(signals_dict)

        for event in exit_events:
            result = evaluate_exit_event_three_way(event, signals_dict)
            for key in ("legacy_fired", "struct_alone", "factor_alone"):
                if result[key]:
                    counts[event.name][key] += 1

    return {
        "status": "ok",
        "records": len(trade_bars) - warmup_bars,
        "raw_bars": len(raw_bars),
        "trade_bars": len(trade_bars),
        "events": counts,
        "dead_signal_counts": {DEAD_SIGNAL_COUNT_KEY: dead_signal_count},
    }


def _aggregate_totals(symbol_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-symbol counts into global totals."""
    totals: dict[str, int] = {"legacy_fired": 0, "struct_alone": 0, "factor_alone": 0}
    dead_signal_counts: dict[str, int] = {DEAD_SIGNAL_COUNT_KEY: 0}

    for result in symbol_results.values():
        if result.get("status") != "ok":
            continue
        for event_counts in result.get("events", {}).values():
            for key in totals:
                totals[key] += event_counts.get(key, 0)
        for key, value in result.get("dead_signal_counts", {}).items():
            dead_signal_counts[key] = dead_signal_counts.get(key, 0) + value

    return {
        "totals": totals,
        "dead_signal_counts": dead_signal_counts,
    }


def _build_report(
    parameters: dict[str, Any],
    symbol_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the JSON-serializable report."""
    aggregates = _aggregate_totals(symbol_results)
    return {
        "disclaimer": DISCLAIMER,
        "generated_at": datetime.now().isoformat(),
        "parameters": parameters,
        "summary": {
            "total_legacy_fired": aggregates["totals"]["legacy_fired"],
            "total_struct_alone": aggregates["totals"]["struct_alone"],
            "total_factor_alone": aggregates["totals"]["factor_alone"],
            "dead_signal_counts": aggregates["dead_signal_counts"],
        },
        "symbol_results": symbol_results,
        "notes": [
            "struct_alone counts bars where event-level signals fired but no factor matched.",
            "factor_alone counts bars where a factor matched but event-level signals did not.",
            "Per-bar open-position exit tracking is not joined in Phase 0 (trade pairs unavailable).",
        ],
    }


def _write_json_report(path: Path, report: dict[str, Any], max_file_mb: float = 50.0) -> None:
    """Serialize the report to JSON, guarding against oversized artifacts."""
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    max_bytes = max_file_mb * 1024 * 1024
    if len(payload.encode("utf-8")) > max_bytes:
        raise RuntimeError(
            f"Artifact {path.name} exceeds {max_file_mb} MB; "
            "reduce the date range or increase --max-file-mb"
        )
    path.write_text(payload, encoding="utf-8")


def _blocked_ratio(struct_alone: int, legacy_fired: int) -> float | None:
    """Compute blocked_ratio = struct_alone / (struct_alone + legacy_fired)."""
    denominator = struct_alone + legacy_fired
    if denominator == 0:
        return None
    return struct_alone / denominator


def _write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    """Render the report as Markdown."""
    params = report["parameters"]
    summary = report["summary"]
    symbol_results = report["symbol_results"]

    lines: list[str] = [
        "# Exit-Event Reachability Report (Phase 0)",
        "",
        f"**{DISCLAIMER}**",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Date range: {params['start_date']} to {params['end_date']}",
        f"- Trade frequency: {params['trade_freq']}",
        f"- Symbols: {', '.join(params['symbols'])}",
        f"- DB path: {params['db_path']}",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| ------ | ----- |",
        f"| legacy_fired | {summary['total_legacy_fired']} |",
        f"| struct_alone | {summary['total_struct_alone']} |",
        f"| factor_alone | {summary['total_factor_alone']} |",
        "",
        "### Dead-signal confirmation",
        "",
    ]

    dead_counts = summary.get("dead_signal_counts", {})
    if dead_counts:
        lines.extend(["| Signal | Count |", "| ------ | ----- |"])
        for key, value in dead_counts.items():
            lines.append(f"| {key} | {value} |")
    else:
        lines.append("No dead-signal counts recorded.")

    lines.extend(["", "## Per-symbol results", ""])

    for symbol, result in symbol_results.items():
        lines.append(f"### {symbol}")
        lines.append("")
        if result.get("status") != "ok":
            lines.append(f"- **status**: {result.get('status', 'unknown')}")
            lines.append(f"- **reason**: {result.get('reason', 'unknown')}")
            lines.append("")
            continue

        lines.append(f"- **status**: ok")
        lines.append(f"- **records**: {result.get('records', 0)}")
        lines.append(
            f"- **bars**: {result.get('raw_bars', 0)} 1m → "
            f"{result.get('trade_bars', 0)} {params['trade_freq']}"
        )
        lines.append("")

        event_table = [
            "| Event | legacy_fired | struct_alone | factor_alone | blocked_ratio |",
            "| ----- | ------------ | ------------ | ------------ | ------------- |",
        ]
        for event_name, counts in result.get("events", {}).items():
            legacy = counts.get("legacy_fired", 0)
            struct = counts.get("struct_alone", 0)
            factor = counts.get("factor_alone", 0)
            ratio = _blocked_ratio(struct, legacy)
            ratio_str = f"{ratio:.4f}" if ratio is not None else "N/A"
            event_table.append(
                f"| {event_name} | {legacy} | {struct} | {factor} | {ratio_str} |"
            )
        lines.extend(event_table)
        lines.append("")

    lines.extend(["## Notes", ""])
    for note in report.get("notes", []):
        lines.append(f"- {note}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def generate_exit_event_reachability_report(
    db_path: str | Path | None,
    symbols: list[str],
    start_date: str,
    end_date: str,
    output_dir: Path,
    warmup_bars: int = 100,
    max_file_mb: float = 50.0,
) -> tuple[Path, Path, dict[str, Any]]:
    """Replay the requested symbols and write JSON+Markdown artifacts."""
    resolved_db = _resolve_db_path(db_path)
    if resolved_db is None:
        raise RuntimeError("No SQLite DB path could be resolved")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report_date = datetime.now().strftime(_FNAME_DATE_FMT)
    json_path = output_dir / f"exit_event_reachability_report_{report_date}.json"
    md_path = output_dir / f"exit_event_reachability_report_{report_date}.md"

    parameters = {
        "start_date": start_date,
        "end_date": end_date,
        "symbols": list(symbols),
        "db_path": str(resolved_db),
        "trade_freq": TRADE_FREQ,
        "warmup_bars": warmup_bars,
    }

    if not resolved_db.exists():
        symbol_results = {
            symbol: {
                "status": "unavailable",
                "reason": f"resolved DB does not exist: {resolved_db}",
            }
            for symbol in symbols
        }
        report = _build_report(parameters, symbol_results)
        _write_json_report(json_path, report, max_file_mb=max_file_mb)
        _write_markdown_report(md_path, report)
        return json_path, md_path, report

    adapter = SqliteDataAdapter(str(resolved_db))
    try:
        symbol_results: dict[str, dict[str, Any]] = {}
        for symbol in symbols:
            exit_events = build_exit_events(symbol, TRADE_FREQ)
            symbol_results[symbol] = _replay_symbol(
                symbol=symbol,
                adapter=adapter,
                start_date=start_date,
                end_date=end_date,
                trade_freq_name=TRADE_FREQ,
                warmup_bars=warmup_bars,
                exit_events=exit_events,
            )
    finally:
        adapter.close()

    report = _build_report(parameters, symbol_results)
    _write_json_report(json_path, report, max_file_mb=max_file_mb)
    _write_markdown_report(md_path, report)
    return json_path, md_path, report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 0 diagnostic: exit-event reachability on real 1-minute bars."
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
        help="Directory where JSON/Markdown artifacts are written.",
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

    json_path, md_path, report = generate_exit_event_reachability_report(
        db_path=args.db_path,
        symbols=symbols,
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=args.output_dir,
        warmup_bars=args.warmup_bars,
        max_file_mb=args.max_file_mb,
    )

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    summary = report["summary"]
    print(
        "Summary: "
        f"legacy_fired={summary['total_legacy_fired']}, "
        f"struct_alone={summary['total_struct_alone']}, "
        f"factor_alone={summary['total_factor_alone']}, "
        f"dead_signal_counts={summary['dead_signal_counts']}"
    )


if __name__ == "__main__":
    main()
