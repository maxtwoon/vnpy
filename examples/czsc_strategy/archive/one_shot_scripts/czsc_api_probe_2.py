"""ONE-SHOT / 开发期 czsc 库 API 探索脚本，非 pytest 用例，不在 tests/unit 门禁范围内。
路径已随 A107 迁移并改名（原 test_czsc_api2.py → archive/one_shot_scripts/czsc_api_probe_2.py），未重新验证可运行性。

Test czsc API compatibility - ZS"""
import datetime
import random

from czsc import CZSC, Direction, Freq, Mark, RawBar, ZS

bars = []
price = 100.0
for i in range(100):
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
