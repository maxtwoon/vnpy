"""
Fetch recent Shanghai index minute bars with AKShare.

AKShare / EastMoney usually does not provide two years of 1-minute history for
indices, so this script is intentionally a recent-data helper for live analysis.
Historical evaluation remains daily-level.

Usage:
    python fetch_sh_index_minute.py --symbol 000001 --period 1 --out sh000001_minute.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch recent index minute bars by AKShare")
    ap.add_argument("--symbol", default="000001", help="EastMoney index code, e.g. 000001 for Shanghai Composite")
    ap.add_argument("--period", default="1", choices=["1", "5", "15", "30", "60"], help="minute period")
    ap.add_argument("--out", default="sh000001_minute.csv")
    args = ap.parse_args()

    import akshare as ak

    try:
        df = ak.index_zh_a_hist_min_em(symbol=args.symbol, period=args.period)
    except Exception as exc:
        print(
            "failed to fetch minute bars from AKShare / EastMoney; "
            f"check network/proxy and retry. reason: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)
    rename = {
        "时间": "datetime",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    keep = [c for c in ["datetime", "open", "high", "low", "close", "volume", "amount"] if c in df.columns]
    df = df[keep].sort_values("datetime")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False, encoding="utf-8")
    print(f"saved {len(df)} rows -> {args.out}")


if __name__ == "__main__":
    main()
