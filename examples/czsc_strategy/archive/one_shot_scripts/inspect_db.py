"""
ONE-SHOT / 开发调试脚本，不在文档化测试或回测入口范围内。
独立脚本：检查SQLite数据库结构
运行: python inspect_db.py
路径已随 A107 迁移（原 inspect_db.py → archive/one_shot_scripts/inspect_db.py），未重新验证可运行性。
"""
import os
import sys
import sqlite3
import pandas as pd
from pathlib import Path

# 与 chan_strategy/config.py 的 SQLITE_DB_PATH 保持同一覆盖方式（CHAN_SQLITE_DB_PATH），
# 2026-07-26 审核后修复：此前硬编码个人网盘路径且不可通过环境变量覆盖。
DB_PATH = os.getenv(
    "CHAN_SQLITE_DB_PATH",
    r"D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db",
)

# 也尝试不带.db后缀的路径
DB_PATH_ALT = DB_PATH[:-3] if DB_PATH.lower().endswith(".db") else DB_PATH


def inspect():
    # 确定正确的数据库路径
    db_path = None
    for path in [DB_PATH, DB_PATH_ALT]:
        if Path(path).exists():
            db_path = path
            break

    if not db_path:
        # 尝试列出目录内容
        dir_path = Path(r"D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425")
        if dir_path.exists():
            print(f"目录存在: {dir_path}")
            print("目录内容:")
            for f in dir_path.iterdir():
                print(f"  {f.name} ({f.stat().st_size / 1024 / 1024:.1f} MB)")
        else:
            print(f"目录不存在: {dir_path}")
            # 尝试上一级
            parent = dir_path.parent
            if parent.exists():
                print(f"上级目录内容: {parent}")
                for f in parent.iterdir():
                    print(f"  {f.name}")
        return

    print(f"数据库路径: {db_path}")
    print(f"文件大小: {Path(db_path).stat().st_size / 1024 / 1024:.1f} MB")
    print()

    conn = sqlite3.connect(db_path)

    # 获取所有表
    tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)
    print(f"数据表: {tables['name'].tolist()}")
    print()

    # 检查每个表
    for table_name in tables['name']:
        print(f"=== 表: {table_name} ===")

        # 表结构
        schema = pd.read_sql(f"PRAGMA table_info({table_name})", conn)
        print("列结构:")
        for _, row in schema.iterrows():
            print(f"  {row['name']} ({row['type']})")

        # 行数
        count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        print(f"总行数: {count:,}")

        # 样本数据
        sample = pd.read_sql(f"SELECT * FROM {table_name} LIMIT 5", conn)
        print("样本数据:")
        print(sample.to_string(index=False))
        print()

        # 尝试获取可用的symbol列表
        for col in ["symbol", "code", "stock_code", "ts_code"]:
            if col in schema['name'].values:
                symbols = pd.read_sql(
                    f"SELECT DISTINCT {col} FROM {table_name} LIMIT 20", conn
                )
                print(f"股票代码样本 ({col}列): {symbols[col].tolist()}")
                break

        # 尝试获取日期范围
        for col in ["datetime", "date", "trade_date", "dt"]:
            if col in schema['name'].values:
                date_range = conn.execute(
                    f"SELECT MIN({col}), MAX({col}) FROM {table_name}"
                ).fetchone()
                print(f"日期范围: {date_range[0]} ~ {date_range[1]}")
                break

        # 尝试获取频率
        for col in ["frequency", "freq", "period"]:
            if col in schema['name'].values:
                freqs = pd.read_sql(
                    f"SELECT DISTINCT {col} FROM {table_name}", conn
                )
                print(f"可用频率: {freqs[col].tolist()}")
                break

        print()

    conn.close()


if __name__ == "__main__":
    inspect()
