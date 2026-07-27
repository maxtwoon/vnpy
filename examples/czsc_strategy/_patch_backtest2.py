"""ONE-SHOT / LEGACY patch script for archived Baostock backtest experiments."""

fpath = r'd:\repo\vnpy\examples\czsc_strategy\run_baostock_backtest.py'
content = open(fpath, 'r', encoding='utf-8').read()

# -------------------------------------------------------
# Insert CountBarMerger class before SimpleBacktester
# -------------------------------------------------------
insert_before = '# ---------------------------------------------------------------------------\n# 简化回测器\n# ---------------------------------------------------------------------------'

new_class = '''# ---------------------------------------------------------------------------
# 基于计数的K线合成器（替代BarGenerator的分钟边界触发方式）
# ---------------------------------------------------------------------------

class CountBarMerger:
    """基于计数的K线合成器 - 每N根输入K线合成1根输出K线。

    不依赖BarGenerator的分钟边界触发，适用于5分钟数据合成30分钟/4小时。
    """

    def __init__(self, window: int, on_bar_callback):
        self.window = window
        self.on_bar_callback = on_bar_callback
        self._count = 0
        self._merged: BarData | None = None

    def update_bar(self, bar: BarData) -> None:
        """接收一根K线，累计window根后回调合成K线。"""
        if self._merged is None:
            # 第一根：初始化合成K线
            self._merged = BarData(
                symbol=bar.symbol,
                exchange=bar.exchange,
                datetime=bar.datetime,
                interval=bar.interval,
                gateway_name=bar.gateway_name,
                open_price=bar.open_price,
                high_price=bar.high_price,
                low_price=bar.low_price,
                close_price=bar.close_price,
                volume=bar.volume,
                turnover=bar.turnover,
            )
        else:
            # 后续根：更新high/low/close/volume/turnover
            self._merged.high_price = max(self._merged.high_price, bar.high_price)
            self._merged.low_price = min(self._merged.low_price, bar.low_price)
            self._merged.close_price = bar.close_price
            self._merged.volume += bar.volume
            self._merged.turnover += bar.turnover

        self._count += 1
        if self._count >= self.window:
            # 触发回调
            if self.on_bar_callback:
                self.on_bar_callback(self._merged)
            # 重置
            self._merged = None
            self._count = 0


# ---------------------------------------------------------------------------
# 简化回测器
# ---------------------------------------------------------------------------'''

if insert_before in content:
    content = content.replace(insert_before, new_class)
    print("CountBarMerger class inserted.")
else:
    print("ERROR: could not find insert location")

# -------------------------------------------------------
# Fix SimpleBacktester.run: replace BG with CountBarMerger
# -------------------------------------------------------
old_bg_setup = (
    '        # ---------------------------------------------------------------\n'
    '        # 关键：重新设置 BarGenerator，使其适配5分钟数据源\n'
    '        # bg_30m: 接收5分钟bar，每6根合成1根30分钟\n'
    '        # bg_4h : 接收5分钟bar，每48根合成1根4小时\n'
    '        # ---------------------------------------------------------------\n'
    '        self.strategy.bg_30m = BarGenerator(\n'
    '            lambda bar: None,\n'
    '            window=6,\n'
    '            on_window_bar=self.strategy.on_30min_bar,\n'
    '            interval=Interval.MINUTE,\n'
    '        )\n'
    '        self.strategy.bg_4h = BarGenerator(\n'
    '            lambda bar: None,\n'
    '            window=48,\n'
    '            on_window_bar=self.strategy.on_4hour_bar,\n'
    '            interval=Interval.MINUTE,\n'
    '        )\n'
    '\n'
    '        # 将 on_5min_bar 包装：原逻辑 + 触发BG合成\n'
    '        original_on_5min_bar = self.strategy.on_5min_bar\n'
    '\n'
    '        def on_5min_bar_wrapped(bar: BarData):\n'
    '            strategy = self.strategy\n'
    '\n'
    '            # 执行原策略逻辑\n'
    '            original_on_5min_bar(bar)\n'
    '\n'
    '            # 触发合成更高周期K线\n'
    '            strategy.bg_30m.update_bar(bar)\n'
    '            strategy.bg_4h.update_bar(bar)\n'
    '\n'
    '        self.strategy.on_5min_bar = on_5min_bar_wrapped'
)

new_bg_setup = (
    '        # ---------------------------------------------------------------\n'
    '        # 关键：使用CountBarMerger替代BarGenerator，基于精确计数合成\n'
    '        # merger_30m: 每6根5分钟 → 1根30分钟\n'
    '        # merger_4h : 每48根5分钟 → 1根4小时\n'
    '        # ---------------------------------------------------------------\n'
    '        merger_30m = CountBarMerger(\n'
    '            window=6,\n'
    '            on_bar_callback=self.strategy.on_30min_bar,\n'
    '        )\n'
    '        merger_4h = CountBarMerger(\n'
    '            window=48,\n'
    '            on_bar_callback=self.strategy.on_4hour_bar,\n'
    '        )\n'
    '\n'
    '        # 将 on_5min_bar 包装：原逻辑 + 触发计数合成\n'
    '        original_on_5min_bar = self.strategy.on_5min_bar\n'
    '\n'
    '        def on_5min_bar_wrapped(bar: BarData):\n'
    '            strategy = self.strategy\n'
    '\n'
    '            # 先合成更高周期（确保本根5m K线处理前，高周期已更新）\n'
    '            merger_30m.update_bar(bar)\n'
    '            merger_4h.update_bar(bar)\n'
    '\n'
    '            # 执行原策略逻辑（5m信号检测）\n'
    '            original_on_5min_bar(bar)\n'
    '\n'
    '        self.strategy.on_5min_bar = on_5min_bar_wrapped'
)

if old_bg_setup in content:
    content = content.replace(old_bg_setup, new_bg_setup)
    print("BG -> CountBarMerger replacement applied.")
else:
    print("ERROR: could not find BG setup block")
    # Try to find partial
    idx = content.find('关键：重新设置 BarGenerator')
    print(f"  Partial match at {idx}")

open(fpath, 'w', encoding='utf-8').write(content)
print("Patch 2 complete.")
