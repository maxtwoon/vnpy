"""
正式评估回测入口

Usage:
    python run_formal_evaluation.py [--symbol SYMBOL] [--table TABLE]

本入口显式启用 `sizing_model="risk"` + `limit_halt_model="enforce"`，
用于生成比默认研究基线更接近真实合约约束的正式评估报告。
它不会修改 `chan_strategy/config.py` 中的默认字典值。

数据来源、数据库结构与 `run_chan_backtest.py` 一致。
"""
import argparse
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from chan_strategy.backtest_engine import run_formal_evaluation
from chan_strategy.config import BACKTEST_CONFIG, SQLITE_DB_PATH
from chan_strategy.data_adapter import SqliteDataAdapter


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="缠论择时策略正式评估回测（risk + enforce）"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="测试品种代码（默认使用数据库中第一个表的第一个品种）",
    )
    parser.add_argument(
        "--table",
        type=str,
        default=None,
        help="数据表名（默认使用数据库中第一个表）",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("缠论择时策略正式评估回测")
    print("模式: sizing_model=risk, limit_halt_model=enforce")
    print("=" * 60)
    print(f"数据库: {SQLITE_DB_PATH}")
    print(f"数据库存在: {Path(SQLITE_DB_PATH).exists()}")
    print()

    adapter = SqliteDataAdapter(SQLITE_DB_PATH)
    try:
        tables = adapter.get_tables()
        if not tables:
            print("错误: 数据库中没有数据表")
            return

        table_name = args.table if args.table else tables[0]
        symbols = adapter.get_symbols(table_name)
        if not symbols:
            print(f"错误: 表 {table_name} 中没有可用品种代码")
            return

        symbol = args.symbol if args.symbol else symbols[0]
    finally:
        adapter.close()

    print(f"选择测试品种: {symbol} (表: {table_name})")
    print()

    backtest_start = BACKTEST_CONFIG.get("start_date", "2025-01-01")
    backtest_end = BACKTEST_CONFIG.get("end_date", "2025-12-31")

    run_formal_evaluation(
        symbol=symbol,
        freq="1",
        start_date=backtest_start,
        end_date=backtest_end,
        table_name=table_name,
    )


if __name__ == "__main__":
    main()
