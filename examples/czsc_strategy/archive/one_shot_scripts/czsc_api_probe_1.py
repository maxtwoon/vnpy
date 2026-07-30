"""ONE-SHOT / 开发期 czsc 库 API 探索脚本，非 pytest 用例，不在 tests/unit 门禁范围内。
路径已随 A107 迁移并改名（原 test_czsc_api.py → archive/one_shot_scripts/czsc_api_probe_1.py），未重新验证可运行性。

Test czsc API compatibility"""
import datetime
import random

from czsc import CZSC, Direction, Freq, RawBar

# Create zigzag bars
bars = []
price = 100.0
for i in range(100):
    # Zigzag pattern
    if i % 10 < 5:
        o = price
        c = price + 2 + random.random()
        h = max(o, c) + random.random()
        low_ = min(o, c) - random.random()
        price = c
    else:
        o = price
        c = price - 2 - random.random()
        h = max(o, c) + random.random()
        low_ = min(o, c) - random.random()
        price = c
    bars.append(RawBar(
        symbol='test',
        dt=datetime.datetime(2024, 1, 1) + datetime.timedelta(hours=i),
        freq=Freq.F60,
        open=round(o, 2),
        close=round(c, 2),
        high=round(h, 2),
        low=round(low_, 2),
        vol=1,
        amount=1,
        id=i
    ))

c = CZSC(bars_raw=bars)
print('bi_list len:', len(c.bi_list))
print('fx_list len:', len(c.fx_list))
print('has zs_list:', hasattr(c, 'zs_list'))

if c.bi_list:
    b = c.bi_list[0]
    print('bi direction:', b.direction, type(b.direction))
    print('bi high:', b.high, 'low:', b.low)

if c.fx_list:
    f = c.fx_list[0]
    print('fx mark:', f.mark, type(f.mark))
    fx_attrs = [a for a in dir(f) if not a.startswith('_')]
    print('fx attrs:', fx_attrs)
    print('fx mark value:', f.mark.value if hasattr(f.mark, 'value') else f.mark)

# Test update
new_bar = RawBar(
    symbol='test',
    dt=datetime.datetime(2024, 1, 1) + datetime.timedelta(hours=100),
    freq=Freq.F60,
    open=price,
    close=price+1,
    high=price+2,
    low=price-1,
    vol=1,
    amount=1,
    id=100
)
c.update(new_bar)
print('after update bi_list len:', len(c.bi_list))

# Check what Direction is
print('Direction.Up:', Direction.Up)
print('Direction.Down:', Direction.Down)
