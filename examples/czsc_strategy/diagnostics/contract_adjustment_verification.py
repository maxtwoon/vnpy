"""A52 Part A — Continuous-contract adjustment-method verification.

Read-only diagnostic that inspects the raw SQLite table(s) for the five default
888 continuous-contract symbols and determines the splicing/adjustment method
actually in use.  It cross-references the A34 H4 ``found_spliced`` finding and
states explicitly whether that finding still holds.

The conclusion is written both to stdout and to a JSON report next to this
script, so it can be cited from ``chan_strategy/data_adapter.py``.

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Make the czsc_strategy package importable from this diagnostics script
_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.config import SQLITE_DB_PATH  # noqa: E402
from chan_strategy.rollover_config import ROLLOVER_SYMBOLS, _detect_transitions  # noqa: E402


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE
BANNER = "RESEARCH-ONLY — Diagnostic only, not a trading recommendation."

# Column-name substrings that would indicate an explicit adjustment method.
_ADJUSTMENT_COLUMN_HINTS = (
    "adjust",
    "factor",
    "back_adjust",
    "front_adjust",
    "roll_adj",
    "continuous_adj",
    "adj",
)

# Minimum price gap (absolute percent) that is considered a discontinuity.
_GAP_THRESHOLD_PCT = 0.5


def _find_price_columns(cur: sqlite3.Cursor, table: str) -> dict[str, str]:
    """Return the exact column names for open/high/low/close if present."""
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1].lower(): row[1] for row in cur.fetchall()}
    result: dict[str, str] = {}
    for key, candidates in (
        ("open", ["open", "open_price", "开盘价"]),
        ("high", ["high", "high_price", "最高价"]),
        ("low", ["low", "low_price", "最低价"]),
        ("close", ["close", "close_price", "收盘价"]),
    ):
        for cand in candidates:
            if cand in columns:
                result[key] = columns[cand]
                break
    return result


def _boundary_price_gap(
    conn: sqlite3.Connection,
    table: str,
    prev_contract: str,
    to_contract: str,
    transition_dt: datetime,
    price_cols: dict[str, str],
) -> dict[str, Any] | None:
    """Measure the close-to-open price gap across a contract transition."""
    if not price_cols:
        return None

    close_col = price_cols["close"]
    open_col = price_cols["open"]
    cur = conn.cursor()

    # Last close of the previous contract strictly before the transition.
    cur.execute(
        f"SELECT {close_col}, datetime FROM {table} "
        f"WHERE symbol = ? COLLATE NOCASE AND real_symbol = ? AND datetime < ? "
        f"ORDER BY datetime DESC LIMIT 1",
        (table.split("_")[0].upper(), prev_contract, transition_dt.strftime("%Y-%m-%d %H:%M:%S")),
    )
    prev_row = cur.fetchone()

    # First open of the new contract at/after the transition.
    cur.execute(
        f"SELECT {open_col}, datetime FROM {table} "
        f"WHERE symbol = ? COLLATE NOCASE AND real_symbol = ? AND datetime >= ? "
        f"ORDER BY datetime ASC LIMIT 1",
        (table.split("_")[0].upper(), to_contract, transition_dt.strftime("%Y-%m-%d %H:%M:%S")),
    )
    next_row = cur.fetchone()

    if prev_row is None or next_row is None:
        return None

    prev_close, prev_dt = prev_row
    next_open, next_dt = next_row
    if prev_close is None or next_open is None or prev_close == 0:
        return None

    gap_pct = (float(next_open) - float(prev_close)) / abs(float(prev_close)) * 100.0
    return {
        "prev_close": float(prev_close),
        "prev_dt": str(prev_dt),
        "next_open": float(next_open),
        "next_dt": str(next_dt),
        "gap_pct": round(gap_pct, 4),
        "discontinuous": abs(gap_pct) > _GAP_THRESHOLD_PCT,
    }


def _schema_has_adjustment_columns(cur: sqlite3.Cursor, table: str) -> list[str]:
    """Return any column names that look like adjustment factors."""
    cur.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cur.fetchall()]
    return [c for c in columns if any(hint in c.lower() for hint in _ADJUSTMENT_COLUMN_HINTS)]


def _verify_symbol(db_path: Path, symbol: str) -> dict[str, Any]:
    """Verify the adjustment/splicing method for a single symbol."""
    table = f"{symbol.lower()}_1M_raw"
    result: dict[str, Any] = {
        "symbol": symbol,
        "table": table,
        "database": str(db_path),
        "verified_at": datetime.now().isoformat(),
        "table_exists": False,
        "real_symbol_column": False,
        "adjustment_columns": [],
        "transitions": [],
        "price_gaps": [],
        "method": "unknown",
        "a34_h4_found_spliced": None,
        "a34_h4_still_holds": None,
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

        result["table_exists"] = True
        result["adjustment_columns"] = _schema_has_adjustment_columns(cur, table)

        # Detect transitions across the full table (no date filter so we see the
        # contract structure used to build the continuous series).
        transitions_result = _detect_transitions(db_path, symbol)
        result["real_symbol_column"] = transitions_result["detection_method"] == "real_symbol"
        result["transitions"] = transitions_result.get("transition_dates", [])
        if transitions_result.get("unavailable"):
            result["unavailable"] = transitions_result["unavailable"]
            return result

        price_cols = _find_price_columns(cur, table)
        gaps: list[dict[str, Any]] = []
        for tr in result["transitions"]:
            gap = _boundary_price_gap(
                conn, table,
                tr["from_contract"], tr["to_contract"],
                datetime.fromisoformat(tr["datetime"]),
                price_cols,
            )
            if gap is not None:
                gap["transition_date"] = tr["date"]
                gap["from_contract"] = tr["from_contract"]
                gap["to_contract"] = tr["to_contract"]
                gaps.append(gap)
        result["price_gaps"] = gaps

        # Decide the method.
        has_adjustment_columns = bool(result["adjustment_columns"])
        has_real_symbol = result["real_symbol_column"]
        any_discontinuity = any(g.get("discontinuous") for g in gaps)
        multiple_contracts = len(result["transitions"]) > 0

        if has_adjustment_columns:
            result["method"] = "explicit_adjustment_detected"
            result["a34_h4_found_spliced"] = False
            result["a34_h4_still_holds"] = False
        elif has_real_symbol and multiple_contracts and any_discontinuity:
            result["method"] = "raw_unadjusted_splice"
            result["a34_h4_found_spliced"] = True
            result["a34_h4_still_holds"] = True
        elif has_real_symbol and multiple_contracts and not any_discontinuity:
            result["method"] = "spliced_with_smoothing_or_adjustment"
            result["a34_h4_found_spliced"] = False
            result["a34_h4_still_holds"] = False
        elif has_real_symbol and not multiple_contracts:
            result["method"] = "single_contract_no_rollover"
            result["a34_h4_found_spliced"] = False
            result["a34_h4_still_holds"] = False
        else:
            result["method"] = "insufficient_metadata"
            result["a34_h4_found_spliced"] = None
            result["a34_h4_still_holds"] = None

        return result
    finally:
        conn.close()


def _format_summary(report: dict[str, Any]) -> str:
    """Return a human-readable summary of the verification report."""
    lines = [
        "=" * 70,
        "A52 — Continuous-Contract Adjustment-Method Verification",
        BANNER,
        f"Database: {report['database']}",
        f"Generated: {report['generated_at']}",
        "-" * 70,
        f"Overall conclusion: {report['overall_conclusion']}",
        f"A34 H4 'found_spliced' still holds: {report['a34_h4_still_holds_overall']}",
        "",
        "Per-symbol findings:",
    ]
    for symbol_report in report["symbols"]:
        sym = symbol_report["symbol"]
        method = symbol_report["method"]
        holds = symbol_report["a34_h4_still_holds"]
        gaps = symbol_report["price_gaps"]
        gap_summary = "; ".join(
            f"{g['transition_date']}: {g['gap_pct']:+.2f}% "
            f"({g['from_contract']}->{g['to_contract']})"
            for g in gaps
        ) if gaps else "no measurable gaps"
        lines.append(f"  {sym}: {method} | A34 H4 holds: {holds} | gaps: [{gap_summary}]")
        if symbol_report.get("unavailable"):
            lines.append(f"    unavailable: {symbol_report['unavailable']}")
    lines.append("=" * 70)
    return "\n".join(lines)


def main(
    db_path: Path = Path(SQLITE_DB_PATH),
    symbols: tuple[str, ...] = ROLLOVER_SYMBOLS,
    out_dir: Path = DEFAULT_OUT_DIR,
    stamp: str | None = None,
) -> dict[str, Any]:
    """Run the adjustment-method verification and write the JSON report."""
    if stamp is None:
        stamp = datetime.now().astimezone().date().isoformat()

    symbols_report = [_verify_symbol(db_path, s) for s in symbols]

    methods = {s["method"] for s in symbols_report}
    unavailable = [s for s in symbols_report if s.get("unavailable")]
    h4_holds_count = sum(
        1 for s in symbols_report if s["a34_h4_still_holds"] is True
    )
    h4_total = sum(
        1 for s in symbols_report if s["a34_h4_still_holds"] is not None
    )

    if unavailable:
        overall = f"partial_verification; {len(unavailable)} symbol(s) unavailable"
        a34_overall = f"indeterminate ({len(unavailable)} unavailable)"
    elif len(methods) == 1:
        method = next(iter(methods))
        overall = method
        if method == "raw_unadjusted_splice":
            a34_overall = f"yes ({h4_holds_count}/{h4_total} verifiable symbols)"
        else:
            a34_overall = "no"
    else:
        overall = f"mixed_methods: {sorted(methods)}"
        a34_overall = f"mixed ({h4_holds_count}/{h4_total} verifiable symbols still spliced)"

    report: dict[str, Any] = {
        "database": str(db_path),
        "generated_at": datetime.now().isoformat(),
        "symbols": symbols_report,
        "overall_conclusion": overall,
        "a34_h4_still_holds_overall": a34_overall,
        "disclaimer": BANNER,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"contract_adjustment_verification_{stamp}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(_format_summary(report))
    print(f"\nFull report written to: {out_path}")
    return report


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    parser = argparse.ArgumentParser(description="Verify 888 continuous-contract adjustment method.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    parser.add_argument("--symbols", nargs="+", default=list(ROLLOVER_SYMBOLS))
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--stamp", default=None)
    args = parser.parse_args()

    main(
        db_path=args.db_path,
        symbols=tuple(args.symbols),
        out_dir=args.out_dir,
        stamp=args.stamp,
    )
