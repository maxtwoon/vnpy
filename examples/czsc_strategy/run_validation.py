"""
缠论择时策略验证脚本

运行: python run_validation.py

功能:
1. 加载数据并运行回测获取信号历史
2. 信号验证（穷尽性、互斥性、未来函数）
3. 事件验证（逻辑正确性、信号覆盖）
4. 单策略分别回测
5. 稳健性检验（样本外测试）
6. SimNow准备度评估
7. 输出完整验证报告
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from chan_strategy.config import SQLITE_DB_PATH, BACKTEST_CONFIG
from chan_strategy.data_adapter import SqliteDataAdapter
from chan_strategy.validation import run_full_validation


def main():
    """主函数"""
    print("=" * 60)
    print("缠论择时策略 - 完整验证与优化")
    print("=" * 60)
    print(f"数据库: {SQLITE_DB_PATH}")
    print(f"数据库存在: {Path(SQLITE_DB_PATH).exists()}")
    print()

    # 检查数据库并获取品种信息
    adapter = SqliteDataAdapter(SQLITE_DB_PATH)
    try:
        tables = adapter.get_tables()
        if not tables:
            print("错误: 数据库中没有数据表")
            return

        print(f"可用数据表 ({len(tables)}个):")
        for t in tables[:5]:
            print(f"  - {t}")
        print()

        # 使用AP888（苹果期货）作为主测试品种
        # 查找包含AP的表
        target_table = None
        target_symbol = None

        for t in tables:
            if "AP" in t.upper() or "ap" in t.lower():
                target_table = t
                symbols = adapter.get_symbols(t)
                if symbols:
                    target_symbol = symbols[0]
                break

        # 如果没找到AP，用第一个表
        if not target_table:
            target_table = tables[0]
            symbols = adapter.get_symbols(target_table)
            target_symbol = symbols[0] if symbols else "AP888"

        print(f"测试品种: {target_symbol} (表: {target_table})")

        # 获取数据范围
        try:
            date_range = adapter.conn.execute(
                f"SELECT MIN(datetime), MAX(datetime) FROM [{target_table}]"
            ).fetchone()
            print(f"数据范围: {date_range[0]} ~ {date_range[1]}")
            count = adapter.conn.execute(
                f"SELECT COUNT(*) FROM [{target_table}]"
            ).fetchone()[0]
            print(f"数据行数: {count:,}")
        except Exception as e:
            print(f"获取数据范围失败: {e}")

    except Exception as e:
        print(f"数据库检查失败: {e}")
        import traceback
        traceback.print_exc()
        return
    finally:
        adapter.close()

    print()
    print("=" * 60)
    print("开始完整验证流程...")
    print("=" * 60)
    print()

    # 运行完整验证
    start_date = BACKTEST_CONFIG.get("start_date", "2023-01-01")
    end_date = BACKTEST_CONFIG.get("end_date", "2025-12-31")

    results = run_full_validation(
        symbol=target_symbol,
        freq="1",
        start_date=start_date,
        end_date=end_date,
        table_name=target_table,
    )

    if "error" in results:
        print(f"\n验证失败: {results['error']}")
        return

    # 最终汇总
    print("\n\n" + "=" * 60)
    print("验证完成 - 最终汇总")
    print("=" * 60)

    report = results.get("backtest_report", {})
    print(f"\n回测绩效:")
    print(f"  交易次数: {report.get('total_trades', 0)}")
    print(f"  胜率: {report.get('win_rate', 0)*100:.1f}%")
    print(f"  盈亏比: {report.get('profit_factor', 0):.2f}")
    print(f"  总收益: {report.get('total_return_pct', 0):.2f}%")
    print(f"  最大回撤: {report.get('max_drawdown_pct', 0):.2f}%")
    print(f"  夏普比率: {report.get('sharpe_ratio', 0):.2f}")

    print(f"\n验证状态:")
    print(f"  穷尽性: {'OK' if results.get('exhaustiveness', {}).get('passed') else 'NG'}")
    print(f"  互斥性: {'OK' if results.get('mutual_exclusivity', {}).get('passed') else 'NG'}")
    inc = results.get('incremental_consistency', {})
    rp = results.get('no_repaint', {})
    sf = results.get('signal_freeze', {})
    print(f"  增量一致性检查: {'OK' if inc.get('passed') else 'NG'}")
    print(f"  无重绘检查: {'OK' if rp.get('passed') else 'NG'}")
    print(f"  历史信号冻结检查: {'OK' if sf.get('passed') else 'NG'}")
    print(f"  事件逻辑: {'OK' if results.get('event_logic', {}).get('passed') else 'NG'}")
    print(f"  信号覆盖: {'OK' if results.get('signal_coverage', {}).get('passed') else 'NG'}")

    readiness = results.get("readiness", {})
    print(f"\nSimNow准备度: {readiness.get('passed_count', 0)}/{readiness.get('total_checks', 10)}")
    print(f"结论: {'可以进入SimNow仿真' if readiness.get('ready') else '需要继续优化'}")


if __name__ == "__main__":
    main()
