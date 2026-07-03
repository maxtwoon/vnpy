import os
import sqlite3

import pytest

from chan_strategy.backtest_engine import BacktestEngine


SYMBOLS = ["AP888", "RB888", "SC888", "A888", "ZN888"]


def _run_real_backtest(symbol, real_db_path, start, end):
    table_name = f"{symbol.lower()}_1M_raw"
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
            (start, end),
        ).fetchone()
    if row is None:
        pytest.fail(f"{symbol} has no rows in {table_name} for {start}~{end}")

    engine = BacktestEngine(
        symbol=row[0],
        db_path=str(real_db_path),
        table_name=table_name,
        start_date=start,
        end_date=end,
    )
    report = engine.run()
    return engine, report


@pytest.mark.realdb
@pytest.mark.slow
@pytest.mark.parametrize("symbol", SYMBOLS)
def test_real_data_matrix_runs_and_is_repeatable(symbol, real_db_path):
    if not real_db_path.exists():
        pytest.skip("real DB not available")

    start = os.getenv("CHAN_REAL_MATRIX_START", "2024-01-01")
    end = os.getenv("CHAN_REAL_MATRIX_END", "2024-03-31")
    engine, report1 = _run_real_backtest(symbol, real_db_path, start, end)
    report2 = engine.run()

    assert "error" not in report1
    assert report1["total_bars"] > 100
    assert report1["traded_bars"] > 0
    assert set(report1["sub_strategies"]) == {"一买多头", "二买多头", "三买多头"}
    assert report1["total_trades"] == sum(x["total_trades"] for x in report1["sub_strategies"].values())
    assert report1["total_trades"] == report2["total_trades"]
    assert report1["final_equity"] == report2["final_equity"]


@pytest.mark.realdb
@pytest.mark.slow
@pytest.mark.parametrize("symbol", SYMBOLS)
def test_real_data_in_sample_out_of_sample_smoke(symbol, real_db_path):
    if not real_db_path.exists():
        pytest.skip("real DB not available")

    is_start = os.getenv("CHAN_REAL_IS_START", "2024-01-01")
    is_end = os.getenv("CHAN_REAL_IS_END", "2024-06-30")
    oos_start = os.getenv("CHAN_REAL_OOS_START", "2024-07-01")
    oos_end = os.getenv("CHAN_REAL_OOS_END", "2024-12-31")

    _, in_sample = _run_real_backtest(symbol, real_db_path, is_start, is_end)
    _, out_sample = _run_real_backtest(symbol, real_db_path, oos_start, oos_end)

    assert "error" not in in_sample
    assert "error" not in out_sample
    assert in_sample["traded_bars"] > 0
    assert out_sample["traded_bars"] > 0
    assert out_sample["final_equity"] > 0
