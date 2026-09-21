"""End-to-end check: local warehouse snapshot -> research SQLite -> vnpy CTA backtest.

Run from D:\\repo\\vnpy with the Studio interpreter:

    D:\\veighna_studio\\python.exe -X utf8 integrations\\vnpy_datasource\\examples\\warehouse_backtest.py

It points ``database.database`` at the research directory for this process only
(no global vt_setting.json change), loads bars through vnpy's own database layer and
runs DoubleMaStrategy on 159915.SZSE daily bars. The snapshot id printed at the end is
what should be written into any backtest result for reproducibility.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from vnpy.trader.setting import SETTINGS

RESEARCH_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "D:/repo/vnpy/research_data/wh_etf_sqlite").resolve()
SETTINGS["database.name"] = "sqlite"
SETTINGS["database.database"] = str(RESEARCH_DIR / "database.db")

from vnpy.trader.constant import Exchange, Interval  # noqa: E402
from vnpy.trader.database import get_database  # noqa: E402
from vnpy_ctastrategy.backtesting import BacktestingEngine  # noqa: E402
from vnpy_ctastrategy.strategies.double_ma_strategy import DoubleMaStrategy  # noqa: E402


def main() -> int:
    manifest = json.loads((RESEARCH_DIR / "datasource-manifest.json").read_text(encoding="utf-8"))
    receipts = [json.loads((RESEARCH_DIR / r).read_text(encoding="utf-8")) for r in manifest["receipts"]]
    snapshots = sorted({r.get("snapshot_id") for r in receipts if r.get("snapshot_id")})
    print("research dir:", RESEARCH_DIR)
    print("adjustment:", manifest["adjustment"], "| warehouse snapshot(s):", snapshots)

    db = get_database()
    overview = {(o.symbol, o.exchange.value, o.interval.value): (o.count, o.start, o.end) for o in db.get_bar_overview()}
    print("database overview:", overview)
    bars = db.load_bar_data("159915", Exchange.SZSE, Interval.DAILY, datetime(2024, 1, 1), datetime(2026, 9, 18))
    if not bars:
        print("no bars loaded from research database")
        return 1
    print(f"loaded {len(bars)} bars {bars[0].datetime.date()} -> {bars[-1].datetime.date()}, last close {bars[-1].close_price}")

    engine = BacktestingEngine()
    engine.set_parameters(vt_symbol="159915.SZSE", interval=Interval.DAILY,
                          start=datetime(2024, 1, 1), end=datetime(2026, 9, 18),
                          rate=0.0001, slippage=0.001, size=1, pricetick=0.001, capital=100_000)
    engine.add_strategy(DoubleMaStrategy, {"fast_window": 10, "slow_window": 20})
    engine.load_data()
    engine.run_backtesting()
    engine.calculate_result()
    stats = engine.calculate_statistics(output=False)
    keys = ("start_date", "end_date", "total_days", "total_trade_count", "total_return", "annual_return", "max_ddpercent", "sharpe_ratio")
    print("backtest:", {k: stats.get(k) for k in keys})
    print("record in results ->", {"warehouse_snapshot_id": snapshots, "adjustment": manifest["adjustment"], "database": SETTINGS["database.database"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
