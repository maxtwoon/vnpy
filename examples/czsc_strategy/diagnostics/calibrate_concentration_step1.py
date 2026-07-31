"""Step 1 (per symbol): replay one symbol and pickle its closed trades.

Usage: python calibrate_concentration_step1.py <symbol>
Read-only diagnostic; writes diagnostics/.calib_trades_<symbol>.pkl
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diagnostics.export_simnow_replay_snapshot import (  # noqa: E402
    DEFAULT_SYMBOLS,
    SQLITE_DB_PATH,
    _run_symbol,
)
from diagnostics.portfolio_goal_evaluator import _strategy_weight  # noqa: E402

START = "2023-06-01"
END = "2026-07-29"
COST_FACTOR = 1.0


def main() -> None:
    symbol = sys.argv[1]
    assert symbol in DEFAULT_SYMBOLS, f"{symbol} not in {DEFAULT_SYMBOLS}"
    row = _run_symbol(Path(SQLITE_DB_PATH), symbol, START, END, COST_FACTOR)
    trades = []
    for trade in row["engine"].strategy.get_combined_trades():
        item = dict(trade)
        item["symbol"] = row["symbol"]
        item["weighted_pnl_pct"] = (
            float(item.get("pnl_pct", 0.0)) * _strategy_weight(str(item.get("strategy")), row["symbol"]) * 100 / len(DEFAULT_SYMBOLS)
        )
        trades.append(item)
    out = Path(__file__).resolve().parent / f".calib_trades_{symbol}.pkl"
    with out.open("wb") as fh:
        pickle.dump(trades, fh)
    print(f"{symbol}: {len(trades)} trades -> {out}")


if __name__ == "__main__":
    main()
