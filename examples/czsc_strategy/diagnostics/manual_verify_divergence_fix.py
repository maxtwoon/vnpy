"""Manual verification for divergence_status_zhongshu_mode fix.

Run a real A888/SC888 full-year backtest with enable_short=True under both
``legacy`` and ``departure_leg`` modes, count P4 gate passes, and report
whether any short trades appear.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.positions import _research_short_open_allowed


SYMBOLS = [("A888", "a888_1M_raw"), ("SC888", "sc888_1M_raw")]
START_DATE = "2025-04-25"
END_DATE = "2026-04-24"


def run_mode(mode: str):
    STRATEGY_CONFIG["divergence_status_zhongshu_mode"] = mode
    STRATEGY_CONFIG["enable_short"] = True

    p4_pass_count = 0
    original_gate = _research_short_open_allowed

    def counting_gate(symbol, signals_dict, freq):
        nonlocal p4_pass_count
        result = original_gate(symbol, signals_dict, freq)
        if result:
            p4_pass_count += 1
        return result

    results = []
    for symbol, table in SYMBOLS:
        print(f"\n=== {symbol} @ {STRATEGY_CONFIG['trade_freq']} | mode={mode} ===")
        engine = BacktestEngine(
            symbol=symbol,
            freq="1",
            start_date=START_DATE,
            end_date=END_DATE,
            table_name=table,
            enable_short=True,
        )
        # Monkey-patch only inside this backtest run.
        import chan_strategy.positions as positions_module
        positions_module._research_short_open_allowed = counting_gate
        try:
            report = engine.run()
        finally:
            positions_module._research_short_open_allowed = original_gate

        trades = engine.strategy.get_combined_trades()
        short_trades = [t for t in trades if "卖" in t.get("strategy", "")]
        results.append({
            "symbol": symbol,
            "mode": mode,
            "p4_pass_count": p4_pass_count,
            "total_trades": report.get("total_trades", 0),
            "short_trades": len(short_trades),
            "short_trade_strategies": sorted({t["strategy"] for t in short_trades}),
        })
        print(f"P4 pass count: {p4_pass_count}")
        print(f"Total trades: {report.get('total_trades', 0)}")
        print(f"Short trades: {len(short_trades)}")
        if short_trades:
            print("Short trade strategies:", {t["strategy"] for t in short_trades})

    return results


def main():
    print("Manual verification: divergence_status_zhongshu_mode fix")
    print(f"Date range: {START_DATE} ~ {END_DATE}")
    print(f"Trade freq: {STRATEGY_CONFIG['trade_freq']}")

    legacy_results = run_mode("legacy")
    departure_results = run_mode("departure_leg")

    print("\n=== SUMMARY ===")
    for r in legacy_results + departure_results:
        print(
            f"{r['symbol']} | {r['mode']:14s} | "
            f"P4={r['p4_pass_count']:>6} | total={r['total_trades']:>4} | short={r['short_trades']:>3}"
        )

    # Restore default.
    STRATEGY_CONFIG["divergence_status_zhongshu_mode"] = "legacy"
    STRATEGY_CONFIG["enable_short"] = False


if __name__ == "__main__":
    main()
