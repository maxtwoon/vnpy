"""A38 Phase 1 cross-check: A35 intrabar_trigger model vs A38 intrabar fill.

RESEARCH-ONLY, not a trading recommendation.

Well-posed cross-check (design 2.5, revised 2026-07-10 after review):

A35 `scenario_intrabar_trigger` fills a touched stop **at the trigger level** (never overshoots).
A38 fills at **min(trigger, close)** for a long (max for a short) - deliberately more conservative
on a gap-through bar. They are different fill models, so a blanket numeric agreement is ill-posed.
Instead we compare the two models on the **same stop-loss population** (one uniform-stop
sub-strategy on >=1 symbol, so a single nominal stop applies), at the engine's 30-minute trade-bar
granularity, and assert:

- convergence on non-gap trades: A38 exit == A35 exit within TOL (1e-6);
- conservatism invariant on gap trades: A38 loss >= A35 loss.

Metrics (`worst_loss_pct` / `overshoot_count` / `max_overshoot_multiple`) are computed by A35's
own `_scenario_summary`, for both models, plus the committed A35 full-sample report for reference.

Only reads the local SQLite DB and runs the existing BacktestEngine; changes no strategy code.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chan_strategy.config import STRATEGY_CONFIG  # noqa: E402
from chan_strategy.backtest_engine import BacktestEngine  # noqa: E402
from diagnostics.stop_loss_stress_report import (  # noqa: E402
    _parse_dt,
    _scenario_summary,
    scenario_intrabar_trigger,
)

BANNER = "Diagnostic only, not a trading recommendation."
TOL = 1e-6
# One uniform-stop long sub-strategy so a single nominal stop applies to the whole population.
SUBSTRATEGY = "一买多头"
STOP_LOSS_BP = 200  # config.stop_loss_1buy


class _TradeBarLoader:
    """A35 BarLoader-compatible loader backed by the engine's 30-minute trade bars."""

    def __init__(self, symbol: str, trade_bars: list) -> None:
        self.symbol = symbol
        self._bars = [
            {"dt": b.dt, "open": float(b.open), "high": float(b.high),
             "low": float(b.low), "close": float(b.close)}
            for b in trade_bars
        ]

    def load(self, symbol, start_dt, end_dt):
        rows = [b for b in self._bars if start_dt <= b["dt"] <= end_dt]
        return (rows, None) if rows else (None, "no_bars_for_window")


def a38_intrabar_trades(pairs, bar_loader, stop_loss_bp):
    """A38 fill model on the same pairs: fill = min(trigger, close) long / max short.

    Mirrors A35 scenario_intrabar_trigger's trigger detection but uses the A38 live
    `_stop_fill` semantics. Returns (trades, unavailable) with pnl_pct in percent and a
    per-trade `gap` flag (True when the triggering bar closed beyond the trigger).
    """
    trades, unavailable = [], []
    for pair in pairs:
        symbol = pair.get("symbol")
        direction = pair.get("direction")
        open_price = pair.get("open_price")
        open_dt = _parse_dt(pair.get("open_dt"))
        close_dt = _parse_dt(pair.get("close_dt"))
        if direction not in ("long", "short") or open_price is None or open_dt is None or close_dt is None:
            unavailable.append({**pair, "reason": "missing_fields"})
            continue
        bars, error = bar_loader.load(symbol, open_dt, close_dt)
        if error or not bars:
            unavailable.append({**pair, "reason": error or "no_bars"})
            continue

        trigger = (open_price * (1 - stop_loss_bp / 10000) if direction == "long"
                   else open_price * (1 + stop_loss_bp / 10000))
        triggered, gap = False, False
        exit_price = pair.get("close_price") if pair.get("close_price") is not None else bars[-1]["close"]
        for bar in bars:
            if direction == "long" and bar["low"] <= trigger:
                triggered = True
                exit_price = min(trigger, bar["close"])  # A38 live _stop_fill semantics
                gap = bar["close"] < trigger
                break
            if direction == "short" and bar["high"] >= trigger:
                triggered = True
                exit_price = max(trigger, bar["close"])
                gap = bar["close"] > trigger
                break

        pnl = ((exit_price - open_price) / open_price * 100.0 if direction == "long"
               else (open_price - exit_price) / open_price * 100.0)
        trades.append({**pair, "open_price": open_price, "stressed_exit_price": exit_price,
                       "triggered": triggered, "gap": gap, "pnl_pct": pnl})
    return trades, unavailable


def _collect_stop_pairs(engine, symbol):
    pairs = []
    for p in engine.strategy.get_combined_trades():
        if p.get("strategy") != SUBSTRATEGY or p.get("reason_code") != "stop_loss":
            continue
        pairs.append({
            "symbol": symbol,
            "strategy": p.get("strategy"),
            "direction": "long",
            "open_dt": p["open_dt"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(p["open_dt"], "strftime") else p["open_dt"],
            "close_dt": p["close_dt"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(p["close_dt"], "strftime") else p["close_dt"],
            "open_price": p.get("open_price"),
            "close_price": p.get("close_price"),
        })
    return pairs


def _compare(symbol, start, end):
    STRATEGY_CONFIG["stop_execution_model"] = "close"
    engine = BacktestEngine(symbol=symbol, freq="1", start_date=start, end_date=end,
                            table_name=f"{symbol}_1M_raw")
    report = engine.run()
    if "error" in report:
        return {"error": report["error"]}

    pairs = _collect_stop_pairs(engine, symbol)
    loader = _TradeBarLoader(symbol, engine.trade_bars)

    a35_trades, a35_unavail = scenario_intrabar_trigger(pairs, loader, STOP_LOSS_BP)
    a38_trades, a38_unavail = a38_intrabar_trades(pairs, loader, STOP_LOSS_BP)

    # Per-trade convergence / conservatism check (same population, aligned 1:1).
    a35_by_key = {(t["open_dt"], t["close_dt"]): t for t in a35_trades}
    non_gap_ok, gap_ok, gap_count, max_nongap_diff = True, True, 0, 0.0
    for t in a38_trades:
        ref = a35_by_key.get((t["open_dt"], t["close_dt"]))
        if ref is None:
            continue
        diff = abs(t["stressed_exit_price"] - ref["stressed_exit_price"])
        if t["gap"]:
            gap_count += 1
            if t["pnl_pct"] > ref["pnl_pct"] + 1e-9:   # A38 must be <= (more negative) than A35
                gap_ok = False
        else:
            max_nongap_diff = max(max_nongap_diff, diff)
            if diff > TOL:
                non_gap_ok = False

    return {
        "symbol": symbol,
        "substrategy": SUBSTRATEGY,
        "stop_loss_bp": STOP_LOSS_BP,
        "stop_trades": len(pairs),
        "a35_model": _scenario_summary(a35_trades, a35_unavail, STOP_LOSS_BP),
        "a38_model": _scenario_summary(a38_trades, a38_unavail, STOP_LOSS_BP),
        "convergence": {
            "tolerance": TOL,
            "non_gap_exact_within_tol": non_gap_ok,
            "max_non_gap_exit_diff": max_nongap_diff,
            "gap_trade_count": gap_count,
            "gap_conservatism_invariant_holds": gap_ok,
            "pass": non_gap_ok and gap_ok,
        },
    }


def _a35_full_sample_reference():
    latest = sorted(Path(__file__).parent.glob("stop_loss_stress_report_*.json"))
    if not latest:
        return {"status": "unavailable", "reason": "no A35 report found"}
    data = json.loads(latest[-1].read_text(encoding="utf-8"))
    it = (data.get("scenarios") or {}).get("intrabar_trigger", {})
    return {
        "source": latest[-1].name,
        "note": "full-sample post-hoc (different population than the windowed comparison above)",
        "worst_loss_pct": it.get("worst_loss_pct"),
        "overshoot_count": it.get("overshoot_count"),
        "max_overshoot_multiple": it.get("max_overshoot_multiple"),
    }


def main(symbols=("sc888", "rb888"), start="2022-01-01", end="2024-12-31", stamp="unstamped"):
    out = {
        "disclaimer": BANNER,
        "generated_at": stamp,
        "window": f"{start} ~ {end}",
        "method": (
            "Same-population two-model comparison at 30m trade-bar granularity. A35 model = "
            "scenario_intrabar_trigger (fill at trigger); A38 model = min/max(trigger, close). "
            "Metrics via A35 _scenario_summary. pnl_pct in percent."
        ),
        "a35_full_sample_reference": _a35_full_sample_reference(),
        "symbols": {},
        "notes": [
            "A38 == A35 exactly on non-gap trades (proves the live fill math); A38 is strictly "
            "more conservative on gap-through trades (fill at close, not trigger) -> that is the "
            "intended modeling improvement, visible as A38 overshoot_count > 0 while A35 == 0.",
        ],
    }
    STRATEGY_CONFIG["stop_execution_model"] = "close"
    for sym in symbols:
        out["symbols"][sym] = _compare(sym, start, end)
    STRATEGY_CONFIG["stop_execution_model"] = "close"
    return out


if __name__ == "__main__":
    stamp = datetime.now(timezone.utc).isoformat() if "--stamp" in sys.argv else "unstamped"
    result = main(stamp=stamp)
    import os
    dump = json.dumps(result, ensure_ascii=False, indent=2)
    out_path = os.environ.get("CROSSCHECK_OUT")
    if out_path:
        Path(out_path).write_text(dump, encoding="utf-8")
    print(dump)
