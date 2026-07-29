"""最小可运行示例：不依赖真实历史数据库，演示 chan_strategy 核心 API 的组合。

运行方式：
    cd examples/czsc_strategy
    python docs/reference/quickstart_example.py

依赖：
    - 已安装 czsc==1.0.0rc8（见 requirements.txt）
    - 已安装 vnpy 核心依赖（本示例不调用实盘接口）

输出：
    - 由随机游走合成的 1 分钟 K 线重采样为 30 分钟 K 线
    - 对合成数据构建 CZSC 对象并调用 sell_signals.get_all_signals()
    - 用 create_first_buy_position() 创建一个"一买多头"子策略实例并打印其事件描述
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 本脚本位于 docs/reference/，仓库根目录为其上两级
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from czsc import CZSC, Freq, RawBar  # noqa: E402

from chan_strategy import (  # noqa: E402
    create_first_buy_position,
    get_all_signals,
    resample_bars,
)


def make_synthetic_1m_bars(
    symbol: str = "TEST",
    days: int = 5,
    bars_per_day: int = 240,
    start: datetime | None = None,
) -> list[RawBar]:
    """生成一段锯齿状随机游走的 1 分钟合成 K 线。"""
    if start is None:
        start = datetime(2024, 1, 2, 9, 0)
    bars: list[RawBar] = []
    price = 100.0
    for d in range(days):
        day_start = datetime.combine(start.date() + timedelta(days=d), start.time())
        for i in range(bars_per_day):
            dt = day_start + timedelta(minutes=i)
            delta = 0.3 if (i // 30) % 2 == 0 else -0.25
            noise = (random.random() - 0.5) * 0.2
            open_ = round(price, 4)
            close = round(price + delta + noise, 4)
            high = round(max(open_, close) + abs(random.random() * 0.1), 4)
            low = round(min(open_, close) - abs(random.random() * 0.1), 4)
            bars.append(
                RawBar(
                    symbol=symbol,
                    id=len(bars),
                    dt=dt,
                    freq=Freq.F1,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    vol=1000 + len(bars),
                    amount=(1000 + len(bars)) * close,
                )
            )
            price = close
    return bars


def main() -> None:
    random.seed(42)

    # 1. 合成 1 分钟数据并重采样到 30 分钟
    raw_1m = make_synthetic_1m_bars()
    bars_30m = resample_bars(
        raw_1m,
        target_freq=Freq.F30,
        target_minutes=30,
        daily_agg="natural",
    )
    print(f"合成 1 分钟 bar 数: {len(raw_1m)}")
    print(f"重采样后 30 分钟 bar 数: {len(bars_30m)}")

    # 2. 构建 CZSC 对象并生成信号
    c = CZSC(bars_raw=bars_30m)
    signals = get_all_signals(c, freq="30分钟")
    print(f"\n生成的信号键数: {len(signals)}")
    for key, value in signals.items():
        print(f"  {key}: {value}")
        # 仅打印前几条，避免输出过长
        if key.startswith("30分钟_D1BSP_三买"):
            break

    # 3. 创建一个"一买多头"子策略实例，展示其开仓/平仓事件
    position = create_first_buy_position(
        symbol="TEST",
        freq="30分钟",
    )
    print(f"\n一买多头子策略名称: {position.name}")
    print(f"开仓事件数量: {len(position.opens)}")
    for ev in position.opens:
        print(f"  开仓事件: {ev}")
    print(f"平仓事件数量: {len(position.exits)}")
    for ev in position.exits:
        print(f"  平仓事件: {ev}")


if __name__ == "__main__":
    main()
