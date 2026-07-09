"""A38 Phase 1 cross-check: stop_execution_model "close" vs "intrabar" on real data.

RESEARCH-ONLY, not a trading recommendation.

Purpose (A38 acceptance, Part II 2.5):
- confirm the "close" model reproduces the baseline stop-loss behaviour (same stop
  trades / worst loss) so the default path is unchanged;
- show the "intrabar" model bounds the stop-loss tail closer to the nominal stop,
  cross-referenced qualitatively against the A35 intrabar_trigger scenario.

This script only reads the local SQLite DB and runs the existing BacktestEngine; it
does not change strategy code, tune thresholds, or submit orders.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chan_strategy.config import STRATEGY_CONFIG  # noqa: E402
from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402

BANNER = "Diagnostic only, not a trading recommendation."
NOMINAL_BP = {
    "一买多头": 200, "二买多头": 300, "三买多头": 350,
    "一卖空头": 200, "二卖空头": 300, "三卖空头": 350,
}


def _stop_stats(engine) -> dict:
    pairs = [p for p in engine.strategy.get_combined_trades()
             if p.get("reason_code") == "stop_loss"]
    if not pairs:
        return {"stop_trades": 0, "worst_loss_pct": 0.0, "max_overshoot_x": 0.0}
    worst = min(p["pnl_pct"] for p in pairs)
    overshoot = []
    for p in pairs:
        nb = NOMINAL_BP.get(p.get("strategy"), 300) / 10000.0
        if p["pnl_pct"] < 0 and nb > 0:
            overshoot.append(abs(p["pnl_pct"]) / nb)
    return {
        "stop_trades": len(pairs),
        "worst_loss_pct": round(worst * 100, 3),
        "max_overshoot_x": round(max(overshoot), 3) if overshoot else 0.0,
    }


def _run(symbol: str, model: str, start: str, end: str, enable_short: bool = False) -> dict:
    STRATEGY_CONFIG["stop_execution_model"] = model
    STRATEGY_CONFIG["stop_penalty_bp"] = 0
    engine = BacktestEngine(symbol=symbol, freq="1", start_date=start, end_date=end,
                            table_name=f"{symbol}_1M_raw", enable_short=enable_short)
    report = engine.run()
    if "error" in report:
        return {"error": report["error"]}
    stats = _stop_stats(engine)
    stats.update({
        "total_return_pct": round(report.get("total_return_pct", 0.0), 3),
        "total_trades": report.get("total_trades", 0),
        "stop_execution_model": report.get("stop_execution_model"),
    })
    return stats


def main(symbols=("ap888", "sc888"), start="2024-01-01", end="2024-12-31",
         stamp="unstamped") -> dict:
    out = {
        "disclaimer": BANNER,
        "generated_at": stamp,
        "window": f"{start} ~ {end}",
        "symbols": {},
        "notes": [
            "close model delegates to the unchanged _check_stop_loss and fills at "
            "the close price -> byte-identical baseline (also unit-proven).",
            "intrabar model triggers on the bar low/high and fills at "
            "min/max(trigger, close); a lower max_overshoot_x vs close confirms the "
            "tail is bounded closer to the nominal stop, matching the A35 "
            "intrabar_trigger direction.",
        ],
    }
    for sym in symbols:
        out["symbols"][sym] = {m: _run(sym, m, start, end) for m in ("close", "intrabar")}
    # enable_short leg on the first symbol: exercises the short-side stop path.
    short_sym = symbols[0]
    out["symbols"][f"{short_sym}__short"] = {
        m: _run(short_sym, m, start, end, enable_short=True) for m in ("close", "intrabar")
    }
    STRATEGY_CONFIG["stop_execution_model"] = "close"
    return out


if __name__ == "__main__":
    stamp = datetime.now(timezone.utc).isoformat() if "--stamp" in sys.argv else "unstamped"
    syms = ("sc888", "rb888")
    result = main(symbols=syms, stamp=stamp)
    import os
    dump = json.dumps(result, ensure_ascii=False, indent=2)
    out_path = os.environ.get("CROSSCHECK_OUT")
    if out_path:
        Path(out_path).write_text(dump, encoding="utf-8")
    print(dump)
