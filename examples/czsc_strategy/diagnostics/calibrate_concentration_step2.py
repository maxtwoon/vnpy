"""Step 2: rolling-60d concentration distribution from pickled trades.

Usage: python calibrate_concentration_step2.py
Reads diagnostics/.calib_trades_<symbol>.pkl written by step1.
Read-only diagnostic; prints distribution stats for threshold calibration.
"""

from __future__ import annotations

import pickle
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diagnostics.export_simnow_replay_snapshot import (  # noqa: E402
    DEFAULT_SYMBOLS,
    _filter_trades_for_concentration,
)
from diagnostics.simnow_precheck_risk_report import _concentration  # noqa: E402

END = "2026-07-29"
WINDOW_DAYS = 60
MIN_TRADES = 5


def main() -> None:
    trades = []
    for symbol in DEFAULT_SYMBOLS:
        pkl = Path(__file__).resolve().parent / f".calib_trades_{symbol}.pkl"
        with pkl.open("rb") as fh:
            trades.extend(pickle.load(fh))
    print(f"total closed trades: {len(trades)}")

    close_dates = [t["close_dt"].date() for t in trades if hasattr(t.get("close_dt"), "date")]
    first = min(close_dates) + timedelta(days=WINDOW_DAYS - 1)
    last = max(max(close_dates), __import__("datetime").date.fromisoformat(END))
    print(f"window evaluation range: {first} .. {last}")

    day = first
    sym_values = []
    strat_values = []
    sufficient_days = 0
    insufficient_days = 0
    while day <= last:
        kept = _filter_trades_for_concentration(trades, day, WINDOW_DAYS)
        if len(kept) >= MIN_TRADES:
            sufficient_days += 1
            sym_values.append((_concentration(kept, "symbol")["top1_abs_share"], day, len(kept)))
            strat_values.append((_concentration(kept, "strategy")["top1_abs_share"], day, len(kept)))
        else:
            insufficient_days += 1
        day += timedelta(days=1)

    def report(name, values):
        values.sort(reverse=True)
        print(f"\n== {name} (sufficient days={sufficient_days}, insufficient days={insufficient_days}) ==")
        if not values:
            print("  no sufficient-sample days")
            return
        print(f"  max: {values[0][0]:.4f} on {values[0][1]} (trades={values[0][2]})")
        p95 = values[int(len(values) * 0.05)]
        med = values[len(values) // 2]
        print(f"  p95: {p95[0]:.4f} on {p95[1]}")
        print(f"  median: {med[0]:.4f}")
        print("  top 5 days:")
        for v, d, n in values[:5]:
            print(f"    {v:.4f} on {d} (trades={n})")

    report("symbol_top1_abs_share", sym_values)
    report("strategy_top1_abs_share", strat_values)

    for name, values in (("symbol", sym_values), ("strategy", strat_values)):
        today = [v for v in values if str(v[1]) == END]
        if today:
            v = today[0][0]
            rank = sum(1 for x in values if x[0] > v) + 1
            print(f"\n{name}: {END} value={v:.4f}, rank {rank}/{len(values)} (1 = historical max)")


if __name__ == "__main__":
    main()
