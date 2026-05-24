"""调试 pos 爆炸问题的脚本"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import tushare as ts
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
import pandas as pd

ts.set_token('da1f00839c22e497ddd81a46973751bc84315ba33d96472fd10547ca')
pro = ts.pro_api()
df = pro.daily(ts_code='600519.SH', start_date='20230101', end_date='20231231')
df = df.sort_values('trade_date').reset_index(drop=True)
print('Got', len(df), 'bars')

bars = []
for _, row in df.iterrows():
    dt = pd.to_datetime(row['trade_date'])
    bar = BarData(symbol='600519', exchange=Exchange.SSE, datetime=dt,
                  interval=Interval.DAILY, open_price=float(row['open']),
                  high_price=float(row['high']), low_price=float(row['low']),
                  close_price=float(row['close']), volume=float(row['vol']),
                  turnover=float(row['amount']), gateway_name='tushare')
    bars.append(bar)

from run_stock_backtest import MockCtaEngine, CAPITAL
from czsc_multi_timeframe_strategy import CzscMultiTimeframeStrategy

engine = MockCtaEngine()
orig_send = engine.send_order
call_count = [0]

def patched_send(strategy, direction, offset, price, volume, stop=False, lock=False, net=False):
    call_count[0] += 1
    if call_count[0] <= 20:
        print(f'  trade #{call_count[0]}: dir={direction.value}, offset={offset.value}, price={price:.2f}, vol={volume}, pos_before={strategy.pos:.1f}')
    result = orig_send(strategy, direction, offset, price, volume, stop, lock, net)
    if call_count[0] <= 20:
        print(f'    -> pos_after={strategy.pos:.1f}')
    return result

engine.send_order = patched_send

setting = {
    'fixed_size': 1, 'max_pos': 3, 'stop_loss_pct': 0.03, 'take_profit_pct': 0.05,
    'trailing_stop_pct': 0.025, 'min_bars_5m': 20, 'min_bars_30m': 15, 'min_bars_4h': 8,
    'support_tolerance_pct': 0.05
}

strategy = CzscMultiTimeframeStrategy(engine, 'test', '600519.SSE', setting)
strategy.on_init()
strategy.inited = True
strategy.trading = True
strategy.on_start()

print('Running 100 bars...')
for i, bar in enumerate(bars[:100]):
    real_pos = strategy.pos
    strategy.pos = 0
    strategy.on_4hour_bar(bar)
    strategy.pos = 0
    strategy.on_30min_bar(bar)
    strategy.pos = real_pos
    strategy.on_5min_bar(bar)
    if abs(strategy.pos) > 5:
        print(f'POS EXPLOSION at bar {i}: pos={strategy.pos}')
        break

print(f'\nFinal pos: {strategy.pos}')
print(f'Total trades: {len(engine.trades)}')
for t in engine.trades[:15]:
    print(f'  {t["direction"].value} {t["offset"].value} {t["price"]:.2f} x{t["volume"]}')
