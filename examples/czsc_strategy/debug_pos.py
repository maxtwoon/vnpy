# =============================================================================
# !! LEGACY / 已停止维护 —— RESEARCH-ONLY / NOT PROMOTION EVIDENCE !!
# -----------------------------------------------------------------------------
# 本文件（debug_pos.py）是早期 A 股原型代码，已停止维护，未接入当前回测/测试路径；
# 当前唯一活跃维护、有测试覆盖的实现是 chan_strategy/（期货 CTA）。
#
# 本文件不含任何 A 股交易制度建模：
#   - 未建模 T+1（当日买入不可当日卖出）
#   - 未建模 涨跌停 / 停牌（halts）
#   - 未建模 卖出侧印花税
#   - 未建模 A 股禁止做空约束
#   - 成交假设为即时、无约束成交（immediate / unconstrained fills）
#
# 其输出【不得】作为策略有效性的证据（NOT PROMOTION EVIDENCE）。
# =============================================================================
"""调试 pos 爆炸问题的脚本

运行前需设置环境变量 TUSHARE_TOKEN（Tushare API token）；未设置时脚本以
RuntimeError fail-closed，不提供任何默认/回退 token。
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import tushare as ts
from vnpy.trader.object import BarData
from vnpy.trader.constant import Exchange, Interval
import pandas as pd

_token = os.environ.get("TUSHARE_TOKEN")
if not _token:
    raise RuntimeError(
        "环境变量 TUSHARE_TOKEN 未设置：请将其设为你的 Tushare API token 后再运行本脚本"
        "（PowerShell: $env:TUSHARE_TOKEN = '<your-token>'）。本脚本不提供任何默认/回退 token。"
    )
ts.set_token(_token)
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
