"""Debug: check why no trades happen - diagnose 4H and 5m ZS formation."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
from datetime import datetime
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.utility import BarGenerator
from czsc_adapter import CzscAnalyzer

DATA_CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")

def load_bars(symbol, exchange_val):
    cache_file = os.path.join(DATA_CACHE_DIR, f"{symbol}_2021-01-01_2022-12-31.csv")
    df = pd.read_csv(cache_file, dtype={"datetime": str})
    bars = []
    ex = Exchange(exchange_val)
    for _, row in df.iterrows():
        dt = datetime.strptime(str(row["datetime"]), "%Y%m%d%H%M%S")
        bar = BarData(
            symbol=symbol, exchange=ex, datetime=dt,
            interval=Interval.MINUTE,
            open_price=float(row["open"]), high_price=float(row["high"]),
            low_price=float(row["low"]), close_price=float(row["close"]),
            volume=float(row["volume"]), turnover=float(row["turnover"]),
            gateway_name="baostock",
        )
        bars.append(bar)
    return bars

def run_diag(symbol, exchange_val, name):
    bars = load_bars(symbol, exchange_val)
    print(f"\n{name} ({symbol}): {len(bars)} bars")

    czsc_5m = CzscAnalyzer(freq=5, max_count=500)
    czsc_30m = CzscAnalyzer(freq=30, max_count=300)
    czsc_4h = CzscAnalyzer(freq=240, max_count=200)

    # Setup BG for 30m and 4h from 5m bars
    bg_30m = BarGenerator(lambda b: None, window=6, on_window_bar=czsc_30m.update, interval=Interval.MINUTE)
    bg_4h = BarGenerator(lambda b: None, window=48, on_window_bar=czsc_4h.update, interval=Interval.MINUTE)

    entry_candidates = 0
    entry_blocked_4h = 0
    entry_blocked_5m = 0
    zs_4h_count_at_end = 0
    zs_5m_count_at_end = 0

    for bar in bars:
        czsc_5m.update(bar)
        bg_30m.update_bar(bar)
        bg_4h.update_bar(bar)

        if not czsc_5m.is_ready(100):
            continue

        dist_4h = czsc_4h.get_distance_to_lower(bar.close_price)
        upper_break_5m = czsc_5m.check_upper_break(bar.close_price)

        if dist_4h > 0.30:
            entry_blocked_4h += 1
        elif not upper_break_5m:
            entry_blocked_5m += 1
        else:
            entry_candidates += 1

    # Final state
    zs_4h_list = czsc_4h.get_zs_list()
    zs_5m_list = czsc_5m.get_zs_list()
    bi_4h = czsc_4h.get_bi_list()
    bi_5m = czsc_5m.get_bi_list()

    print(f"  4H bars received: {czsc_4h._bar_count}, bi_list: {len(bi_4h)}, zs_list: {len(zs_4h_list)}")
    print(f"  5m bars received: {czsc_5m._bar_count}, bi_list: {len(bi_5m)}, zs_list: {len(zs_5m_list)}")
    print(f"  Last dist_4h: {czsc_4h.get_distance_to_lower(bars[-1].close_price):.4f}")
    if zs_4h_list:
        last_zs = zs_4h_list[-1]
        print(f"  Last 4H ZS: zg={last_zs.zg:.2f}, zd={last_zs.zd:.2f}")
    print(f"  Entry candidates: {entry_candidates}")
    print(f"  Blocked by 4H dist: {entry_blocked_4h}")
    print(f"  Blocked by no 5m upper break: {entry_blocked_5m}")

# Run for first stock
run_diag("600133", "SSE", "东湖高新")
run_diag("002036", "SZSE", "联创电子")
run_diag("300256", "SZSE", "星星科技")
