"""
上证指数日线抓取 (AKShare)
==========================

用 AKShare 抓取指数历史日线，规整为统一列并输出 CSV，可选写入 sqlite
（表结构与 chan_strategy 的 SqliteDataAdapter 兼容：datetime/symbol/OHLC/volume/amount）。

日线作为本项目的主数据源（解盘文本主轴是日线结构）。分钟级历史不在此脚本
范围内——免费 AKShare 指数分钟历史回溯有限，仅用于近期实时辅助分析。

接口按优先级回退（不同 akshare 版本/接口列名不同，已统一规整）：
    1. stock_zh_index_daily_em(symbol="sh000001")
    2. index_zh_a_hist(symbol="000001", period="daily", start_date, end_date)
    3. stock_zh_index_daily_tx(symbol="sh000001")

输出列：datetime, symbol, open, high, low, close, volume, amount

用法：
    pip install akshare
    python fetch_sh_index_daily.py --start 2023-08-01 --end 2026-06-12 \
        --symbol sh000001 --out sh000001_daily.csv
    # 同时写入 sqlite（表名默认 {symbol}_1D_raw）：
    python fetch_sh_index_daily.py --sqlite index_daily.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd


# 中英文列名 → 标准列名
_COL_MAP = {
    "日期": "datetime", "date": "datetime",
    "开盘": "open", "open": "open",
    "最高": "high", "high": "high",
    "最低": "low", "low": "low",
    "收盘": "close", "close": "close",
    "成交量": "volume", "volume": "volume", "vol": "volume",
    "成交额": "amount", "amount": "amount", "turnover": "amount",
}
_REQUIRED = ["datetime", "open", "high", "low", "close"]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: _COL_MAP.get(str(c).strip(), str(c).strip()) for c in df.columns})
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"接口返回缺少必要列 {missing}；实际列: {list(df.columns)}")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    if "amount" not in df.columns:
        df["amount"] = 0.0
    df = df[["datetime", "open", "high", "low", "close", "volume", "amount"]].copy()
    df["datetime"] = pd.to_datetime(df["datetime"]).dt.strftime("%Y-%m-%d")
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=_REQUIRED).sort_values("datetime")
    # 去重（同一交易日只留一行）
    df = df.drop_duplicates(subset="datetime", keep="last").reset_index(drop=True)

    # OHLC 不变量检查：high>=max(o,c,l)，low<=min(o,c,h)，价格为正
    bad = df[
        (df["high"] < df[["open", "close", "low"]].max(axis=1))
        | (df["low"] > df[["open", "close", "high"]].min(axis=1))
        | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
    ]
    if len(bad):
        print(f"  [警告] {len(bad)} 行 OHLC 不合法，已剔除: {list(bad['datetime'])[:5]}...")
        df = df.drop(bad.index).reset_index(drop=True)
    return df


def _try_fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
    import akshare as ak

    s_compact = start.replace("-", "")
    e_compact = end.replace("-", "")
    code6 = symbol[-6:]  # sh000001 -> 000001

    attempts = [
        ("stock_zh_index_daily_em",
         lambda: ak.stock_zh_index_daily_em(symbol=symbol)),
        ("index_zh_a_hist",
         lambda: ak.index_zh_a_hist(symbol=code6, period="daily",
                                    start_date=s_compact, end_date=e_compact)),
        ("stock_zh_index_daily_tx",
         lambda: ak.stock_zh_index_daily_tx(symbol=symbol)),
        ("stock_zh_index_daily",
         lambda: ak.stock_zh_index_daily(symbol=symbol)),
    ]

    last_err = None
    for name, fn in attempts:
        try:
            df = fn()
            if df is None or len(df) == 0:
                print(f"  [{name}] 返回空，尝试下一个接口")
                continue
            df = _normalize(df)
            # 区间过滤（有些接口不支持日期参数，统一在此裁剪）
            df = df[(df["datetime"] >= start) & (df["datetime"] <= end)].reset_index(drop=True)
            if len(df) == 0:
                print(f"  [{name}] 区间内无数据，尝试下一个接口")
                continue
            print(f"  [{name}] 成功: {len(df)} 根日线 ({df['datetime'].iloc[0]} ~ {df['datetime'].iloc[-1]})")
            return df
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  [{name}] 失败: {e}")
            continue

    raise RuntimeError(f"所有接口均失败，最后错误: {last_err}")


def _write_sqlite(df: pd.DataFrame, db_path: str, table: str, symbol: str) -> None:
    df2 = df.copy()
    df2.insert(1, "symbol", symbol)
    if not table.replace("_", "").isalnum():
        raise ValueError(f"非法表名: {table}")
    with sqlite3.connect(db_path) as conn:
        conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.execute(
            f'''CREATE TABLE "{table}" (
                datetime TEXT, symbol TEXT,
                open REAL, high REAL, low REAL, close REAL,
                volume REAL, amount REAL
            )'''
        )
        df2.to_sql(table, conn, if_exists="append", index=False)
    print(f"  已写入 sqlite: {db_path} 表 {table} ({len(df2)} 行)")


def main():
    ap = argparse.ArgumentParser(description="AKShare 上证指数日线抓取")
    ap.add_argument("--symbol", default="sh000001", help="指数代码，如 sh000001")
    ap.add_argument("--start", default="2023-08-01", help="开始日期 YYYY-MM-DD")
    ap.add_argument("--end", default="2026-06-12", help="结束日期 YYYY-MM-DD")
    ap.add_argument("--out", default="sh000001_daily.csv", help="输出 CSV 路径")
    ap.add_argument("--sqlite", default=None, help="可选：写入的 sqlite 文件路径")
    ap.add_argument("--table", default=None, help="sqlite 表名，默认 {symbol}_1D_raw")
    args = ap.parse_args()

    try:
        import akshare  # noqa: F401
    except ImportError:
        print("未安装 akshare，请先: pip install akshare")
        sys.exit(1)

    print(f"抓取 {args.symbol} 日线 {args.start} ~ {args.end} ...")
    try:
        df = _try_fetch(args.symbol, args.start, args.end)
    except Exception as e:  # noqa: BLE001
        print(f"抓取失败: {e}")
        print("提示: 需要能访问东方财富/新浪行情的网络环境。")
        sys.exit(1)

    out_path = Path(args.out)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"  已写入 CSV: {out_path.resolve()} ({len(df)} 行)")

    if args.sqlite:
        table = args.table or f"{args.symbol}_1D_raw"
        _write_sqlite(df, args.sqlite, table, args.symbol)

    # 覆盖率报告：实际交易日 vs 工作日近似
    import pandas as pd
    dts = pd.to_datetime(df["datetime"])
    n_business = len(pd.bdate_range(dts.iloc[0], dts.iloc[-1]))
    cover = len(df) / n_business if n_business else 0
    print(f"覆盖率: {len(df)} 交易日 / 约 {n_business} 工作日 = {cover:.1%} "
          f"(区间 {dts.iloc[0].date()} ~ {dts.iloc[-1].date()})")
    if cover < 0.85:
        print("  [提示] 覆盖率偏低，可能有缺口或区间未抓全，建议核对接口与日期范围。")
    print(f"完成。列: {list(df.columns)}")


if __name__ == "__main__":
    main()
