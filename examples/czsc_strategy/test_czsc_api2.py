"""Test czsc API compatibility - ZS"""
from czsc import CZSC
from czsc.objects import RawBar, ZS, Direction, Mark
import datetime, random

bars = []
price = 100.0
for i in range(100):
    if i % 10 < 5:
        o = price
        c = price + 2 + random.random()
        h = max(o, c) + random.random()
        l = min(o, c) - random.random()
        price = c
    else:
        o = price
        c = price - 2 - random.random()
        h = max(o, c) + random.random()
        l = min(o, c) - random.random()
        price = c
    bars.append(RawBar(
        symbol='test',
        dt=datetime.datetime(2024, 1, 1) + datetime.timedelta(hours=i),
        freq='F60',
        open=round(o, 2),
        close=round(c, 2),
        high=round(h, 2),
        low=round(l, 2),
        vol=1,
        amount=1,
        id=i
    ))

c = CZSC(bars=bars)
print('bis:', len(c.bi_list))
bis = c.bi_list[:3]
print('first 3 dirs:', [b.direction for b in bis])

zs = ZS(bis=bis)
print('ZS is_valid (prop):', zs.is_valid)
print('ZS attrs:', [a for a in dir(zs) if not a.startswith('_')])
print('zg:', getattr(zs, 'zg', None))
print('zd:', getattr(zs, 'zd', None))

# Test Mark comparison
print('Mark.D:', Mark.D)
print('Mark.G:', Mark.G)
print('mark compare:', c.fx_list[0].mark == Mark.D)

# Test Direction comparison
print('dir compare Up:', c.bi_list[0].direction == Direction.Up)
print('dir compare Down:', c.bi_list[0].direction == Direction.Down)
