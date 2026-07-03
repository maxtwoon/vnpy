import os
import sqlite3
import time

import pytest

from chan_strategy.backtest_engine import BacktestEngine


@pytest.mark.slow
@pytest.mark.realdb
def test_real_db_performance_smoke(real_db_path):
    if os.getenv("RUN_CHAN_PERF") != "1":
        pytest.skip("set RUN_CHAN_PERF=1 to run performance smoke test")
    if not real_db_path.exists():
        pytest.skip("real DB not available")

    symbol = os.getenv("CHAN_PERF_SYMBOL", "AP888")
    table_name = os.getenv("CHAN_PERF_TABLE", f"{symbol.lower()}_1M_raw")
    start_date = os.getenv("CHAN_PERF_START", "2024-01-01")
    end_date = os.getenv("CHAN_PERF_END", "2024-12-31")
    with sqlite3.connect(real_db_path) as conn:
        row = conn.execute(
            f"""
            select symbol, count(*) as n
            from {table_name}
            where datetime >= ? and datetime <= ?
            group by symbol
            order by n desc
            limit 1
            """,
            (start_date, end_date),
        ).fetchone()
    if row is None:
        pytest.fail(f"{symbol} has no rows in {table_name} for {start_date}~{end_date}")

    start = time.perf_counter()
    engine = BacktestEngine(
        symbol=row[0],
        db_path=str(real_db_path),
        table_name=table_name,
        start_date=start_date,
        end_date=end_date,
    )
    report1 = engine.run()
    report2 = engine.run()
    elapsed = time.perf_counter() - start

    assert "error" not in report1
    assert report1["total_bars"] > 0
    assert report1["total_trades"] == report2["total_trades"]
    assert elapsed < float(os.getenv("CHAN_PERF_MAX_SECONDS", "120"))
