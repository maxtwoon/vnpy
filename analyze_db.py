"""SQLite 数据库快速诊断脚本。

用法:
    python analyze_db.py
    python analyze_db.py <db_path>
    set CHAN_SQLITE_DB_PATH=<db_path> && python analyze_db.py
"""
import os
import sys
import sqlite3


def analyze_db(db_path: str) -> None:
    """分析 SQLite 数据库中的 kline_data 表结构。"""
    if not os.path.exists(db_path):
        print(f"错误: 数据库不存在: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()

        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        print('TABLES:', [t[0] for t in c.fetchall()])

        c.execute('PRAGMA table_info(kline_data)')
        print('COLUMNS:', [(x[1], x[2]) for x in c.fetchall()])

        c.execute('SELECT COUNT(*) FROM kline_data')
        print('ROWS:', c.fetchone()[0])

        c.execute('SELECT COUNT(DISTINCT symbol) FROM kline_data')
        print('SYMBOLS:', c.fetchone()[0])

        c.execute('SELECT MIN(datetime), MAX(datetime) FROM kline_data')
        print('RANGE:', c.fetchone())

        c.execute('SELECT DISTINCT frequency FROM kline_data')
        print('FREQ:', [x[0] for x in c.fetchall()])

        c.execute('SELECT * FROM kline_data LIMIT 1')
        print('SAMPLE:', c.fetchone())
    finally:
        conn.close()


def main() -> None:
    if len(sys.argv) >= 2:
        db_path = sys.argv[1]
    else:
        # 兼容原硬编码路径作为 fallback，同时支持环境变量覆盖
        db_path = os.getenv(
            "CHAN_SQLITE_DB_PATH",
            r"D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db",
        )

    analyze_db(db_path)


if __name__ == "__main__":
    main()
