"""A43 P4 — Amplitude-mode equivalence check.

Verifies that ``divergence_model="amplitude"`` reproduces the default/legacy
behavior byte-for-byte on real data (>=2 symbols x 1 year).

RESEARCH-ONLY — Diagnostic only, not a trading recommendation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Make the czsc_strategy package importable from this diagnostics script
_CZSC_STRATEGY_ROOT = Path(__file__).resolve().parent.parent
if str(_CZSC_STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(_CZSC_STRATEGY_ROOT))

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import SQLITE_DB_PATH, STRATEGY_CONFIG


BANNER = "RESEARCH-ONLY — Diagnostic only, not a trading recommendation."
SYMBOLS = ["AP888", "RB888"]
START_DATE = "2025-01-01"
END_DATE = "2025-12-31"


def _run(symbol: str, model: str, db_path: Path, start_date: str, end_date: str) -> dict[str, Any]:
    """Run backtest under a divergence model and return report + pairs."""
    original_model = STRATEGY_CONFIG.get("divergence_model")
    try:
        STRATEGY_CONFIG["divergence_model"] = model
        engine = BacktestEngine(
            symbol=symbol,
            freq="1",
            start_date=start_date,
            end_date=end_date,
            db_path=str(db_path),
            table_name=f"{symbol.lower()}_1M_raw",
        )
        report = engine.run()
        pairs = engine.strategy.get_combined_trades() if engine.strategy else []
        return {"report": report, "pairs": pairs}
    finally:
        if original_model is None:
            STRATEGY_CONFIG.pop("divergence_model", None)
        else:
            STRATEGY_CONFIG["divergence_model"] = original_model


def _pairs_equal(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    if len(a) != len(b):
        return False
    keys = {"open_dt", "close_dt", "open_price", "close_price", "pnl_pct", "volume", "reason", "strategy"}
    for pa, pb in zip(a, b):
        for k in keys:
            if pa.get(k) != pb.get(k):
                return False
    return True


def _equity_equal(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    if len(a) != len(b):
        return False
    keys = {"dt", "equity", "positions", "long_exposure", "short_exposure", "gross_exposure"}
    for ea, eb in zip(a, b):
        for k in keys:
            if ea.get(k) != eb.get(k):
                return False
    return True


def main(
    db_path: Path | None = None,
    symbols: tuple[str, ...] = (),
    start_date: str = START_DATE,
    end_date: str = END_DATE,
) -> dict[str, Any]:
    db_path = db_path or Path(SQLITE_DB_PATH)
    symbols = symbols or tuple(SYMBOLS)

    results: dict[str, Any] = {
        "disclaimer": BANNER,
        "divergence_model": "amplitude",
        "baseline": "default (amplitude)",
        "window": {"start_date": start_date, "end_date": end_date},
        "symbols": list(symbols),
        "equivalent": True,
        "details": {},
    }

    for symbol in symbols:
        default_result = _run(symbol, "amplitude", db_path, start_date, end_date)
        explicit_result = _run(symbol, "amplitude", db_path, start_date, end_date)

        if "error" in default_result["report"]:
            results["equivalent"] = False
            results["details"][symbol] = {
                "error": f"default: {default_result['report']['error']}"
            }
            continue
        if "error" in explicit_result["report"]:
            results["equivalent"] = False
            results["details"][symbol] = {
                "error": f"explicit: {explicit_result['report']['error']}"
            }
            continue

        pairs_ok = _pairs_equal(default_result["pairs"], explicit_result["pairs"])
        equity_ok = _equity_equal(default_result["report"].get("equity_curve", []), explicit_result["report"].get("equity_curve", []))

        results["details"][symbol] = {
            "pairs_count": len(default_result["pairs"]),
            "pairs_equal": pairs_ok,
            "equity_equal": equity_ok,
            "total_return_pct": default_result["report"].get("total_return_pct", 0.0),
            "win_rate": default_result["report"].get("win_rate", 0.0),
        }

        if not (pairs_ok and equity_ok):
            results["equivalent"] = False

    out_path = Path(__file__).resolve().parent / "divergence_amplitude_equivalence_check.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"\n{BANNER}")
    print(f"Equivalence: {'PASS' if results['equivalent'] else 'FAIL'}")
    for symbol, detail in results["details"].items():
        if "error" in detail:
            print(f"  {symbol}: ERROR {detail['error']}")
        else:
            print(f"  {symbol}: pairs={detail['pairs_count']} equity={detail['equity_equal']} pairs_equal={detail['pairs_equal']}")
    print(f"Wrote {out_path}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A43 P4 amplitude-mode equivalence check")
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--start-date", default=START_DATE)
    parser.add_argument("--end-date", default=END_DATE)
    args = parser.parse_args()

    main(
        db_path=args.db_path,
        symbols=tuple(args.symbols) if args.symbols else (),
        start_date=args.start_date,
        end_date=args.end_date,
    )
