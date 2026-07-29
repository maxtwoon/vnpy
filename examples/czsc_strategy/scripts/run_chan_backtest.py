"""
缠论择时策略回测脚本

使用方法:
    python run_chan_backtest.py

数据来源: SQLite数据库（期货1分钟K线）
    D:\\BaiduNetdiskDownload\\新数据库\\ssquant数据库_20260425\\kline_data.db

数据库结构:
    - 表名格式: {symbol}_1M_raw (如 sc888_1M_raw, pp888_1M_raw)
    - 列: datetime(TEXT), symbol(TEXT), open/high/low/close/volume/amount(REAL)
    - 数据为期货品种1分钟K线
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from chan_strategy.backtest_engine import BacktestEngine, run_single_backtest, run_batch_backtest
from chan_strategy.data_adapter import SqliteDataAdapter
from chan_strategy.config import SQLITE_DB_PATH, BACKTEST_CONFIG


def main():
    """主函数"""
    print("!" * 60)
    print("警告：本入口为 RESEARCH_BASELINE（研究基线）默认入口。")
    print("      生成的报告使用默认研究配置，不构成生产/可交易证据。")
    print("      正式评估请使用 run_formal_evaluation.py。")
    print("!" * 60)
    print()

    print("=" * 60)
    print("缠论择时策略回测系统 v1.0")
    print("=" * 60)
    print(f"数据库: {SQLITE_DB_PATH}")
    print(f"数据库存在: {Path(SQLITE_DB_PATH).exists()}")
    print()

    # 第一步：检查数据库并获取可用数据
    adapter = SqliteDataAdapter(SQLITE_DB_PATH)
    try:
        tables = adapter.get_tables()
        print(f"可用数据表 ({len(tables)}个):")
        for t in tables[:10]:
            print(f"  - {t}")
        if len(tables) > 10:
            print(f"  ... 及其他{len(tables)-10}个表")
        print()

        if not tables:
            print("错误: 数据库中没有数据表")
            return

        # 获取第一个表的信息
        first_table = tables[0]
        print(f"--- 分析数据表: {first_table} ---")

        # 获取表结构
        schema = adapter.get_table_schema(first_table)
        col_names = [col["name"] for col in schema]
        print(f"列名: {col_names[:8]}...")

        # 获取可用股票
        symbols = adapter.get_symbols(first_table)
        print(f"品种代码: {symbols}")

        # 获取样本数据
        sample = adapter.get_sample_data(first_table, limit=3)
        if not sample.empty:
            print(f"\n样本数据 (前3行):")
            # 只显示关键列
            key_cols = [c for c in ["datetime", "symbol", "open", "high", "low", "close", "volume"] if c in sample.columns]
            print(sample[key_cols].to_string(index=False))

        # 获取日期范围
        try:
            date_range = adapter.conn.execute(
                f"SELECT MIN(datetime), MAX(datetime) FROM [{first_table}]"
            ).fetchone()
            print(f"\n日期范围: {date_range[0]} ~ {date_range[1]}")
        except Exception:
            pass

        # 获取数据量
        try:
            count = adapter.conn.execute(f"SELECT COUNT(*) FROM [{first_table}]").fetchone()[0]
            print(f"数据行数: {count:,}")
        except Exception:
            pass

    except Exception as e:
        print(f"数据库检查失败: {e}")
        import traceback
        traceback.print_exc()
        return
    finally:
        adapter.close()

    # 第二步：选择测试品种进行回测
    if not symbols:
        print("\n无可用品种代码")
        return

    test_symbol = symbols[0]
    test_table = first_table
    print(f"\n\n{'=' * 60}")
    print(f"选择测试品种: {test_symbol} (表: {test_table})")
    print(f"{'=' * 60}")

    # 1分钟数据量非常大（每个品种每年约6万根），3年数据约18万根
    # 为了回测速度，默认使用3个月的窗口
    # 如需完整回测，可修改 start_date/end_date
    backtest_start = BACKTEST_CONFIG.get("start_date", "2025-01-01")
    backtest_end = BACKTEST_CONFIG.get("end_date", "2025-12-31")

    # 对于1分钟数据，限制到3个月内避免过长运行时间
    # 可以通过命令行参数或修改config来调整
    print(f"\n回测参数:")
    print(f"  开始日期: {backtest_start}")
    print(f"  结束日期: {backtest_end}")
    print(f"  (提示: 1分钟数据量大, 建议控制在1-3个月内)")

    report = run_single_backtest(
        symbol=test_symbol,
        freq="1",  # 1分钟原始数据
        start_date=backtest_start,
        end_date=backtest_end,
        table_name=test_table,
    )

    # 如果有多个表/品种，尝试批量回测
    if len(tables) >= 3:
        print(f"\n\n{'=' * 60}")
        print("批量回测 (前3个品种):")
        print(f"{'=' * 60}")

        # 为每个表获取symbol
        batch_configs = []
        adapter2 = SqliteDataAdapter(SQLITE_DB_PATH)
        try:
            for t in tables[:3]:
                syms = adapter2.get_symbols(t)
                if syms:
                    batch_configs.append({"symbol": syms[0], "table": t})
        finally:
            adapter2.close()

        if batch_configs:
            results = []
            for cfg in batch_configs:
                print(f"\n--- 回测: {cfg['symbol']} (表: {cfg['table']}) ---")
                engine = BacktestEngine(
                    symbol=cfg["symbol"],
                    freq="1",
                    start_date=backtest_start,
                    end_date=backtest_end,
                    table_name=cfg["table"],
                )
                r = engine.run()
                if "error" not in r:
                    results.append({
                        "symbol": cfg["symbol"],
                        "total_trades": r["total_trades"],
                        "win_rate": r.get("win_rate", 0),
                        "total_return_pct": r.get("total_return_pct", 0),
                        "max_drawdown_pct": r.get("max_drawdown_pct", 0),
                        "sharpe_ratio": r.get("sharpe_ratio", 0),
                    })
                    engine.print_report(r)
                else:
                    print(f"  错误: {r['error']}")
                    results.append({"symbol": cfg["symbol"], "error": r["error"]})

            if results:
                import pandas as pd
                print("\n\n批量回测结果汇总:")
                print("-" * 60)
                df = pd.DataFrame(results)
                print(df.to_string(index=False))


if __name__ == "__main__":
    main()
