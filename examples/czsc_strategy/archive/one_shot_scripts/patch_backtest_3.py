"""ONE-SHOT / LEGACY patch script for archived Baostock backtest experiments.
路径已随 A107 迁移（原 _patch_backtest3.py → archive/one_shot_scripts/patch_backtest_3.py），未重新验证可运行性。"""

fpath = r'd:\repo\vnpy\examples\czsc_strategy\legacy\run_baostock_backtest.py'
content = open(fpath, 'r', encoding='utf-8').read()

# -------------------------------------------------------
# Fix: add cooldown to on_5min_bar_wrapped
# -------------------------------------------------------
old_wrapped = (
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

new_wrapped = (
    '        # 将 on_5min_bar 包装：原逻辑 + 触发计数合成 + 冷却期控制\n'
    '        original_on_5min_bar = self.strategy.on_5min_bar\n'
    '        _bar_idx = [0]\n'
    '        _last_close_idx = [-48]  # 初始假设已超过冷却期\n'
    '        _prev_pos = [0]\n'
    '        COOLDOWN = 48  # 平仓后至少等待1个交易日（48根5m K线）再开仓\n'
    '\n'
    '        def on_5min_bar_wrapped(bar: BarData):\n'
    '            strategy = self.strategy\n'
    '            idx = _bar_idx[0]\n'
    '            _bar_idx[0] += 1\n'
    '\n'
    '            # 先合成更高周期（确保本根5m K线处理前，高周期已更新）\n'
    '            merger_30m.update_bar(bar)\n'
    '            merger_4h.update_bar(bar)\n'
    '\n'
    '            # 冷却期内且无持仓：仅更新CZSC分析器，跳过开仓逻辑\n'
    '            in_cooldown = (idx - _last_close_idx[0]) < COOLDOWN\n'
    '            if in_cooldown and strategy.pos == 0:\n'
    '                # 手动更新czsc_5m，跳过交易决策\n'
    '                try:\n'
    '                    strategy.czsc_5m.update(bar)\n'
    '                except Exception:\n'
    '                    pass\n'
    '                strategy.put_event()\n'
    '                return\n'
    '\n'
    '            # 执行原策略逻辑（5m信号检测）\n'
    '            prev_pos = _prev_pos[0]\n'
    '            original_on_5min_bar(bar)\n'
    '\n'
    '            # 检测完全平仓事件，记录冷却起始\n'
    '            if prev_pos != 0 and strategy.pos == 0:\n'
    '                _last_close_idx[0] = idx\n'
    '            _prev_pos[0] = strategy.pos\n'
    '\n'
    '        self.strategy.on_5min_bar = on_5min_bar_wrapped'
)

if old_wrapped in content:
    content = content.replace(old_wrapped, new_wrapped)
    print("Cooldown added to on_5min_bar_wrapped.")
else:
    print("ERROR: could not find old_wrapped block")
    idx = content.find('将 on_5min_bar 包装：原逻辑 + 触发计数合成')
    print(f"  Partial found at {idx}")

open(fpath, 'w', encoding='utf-8').write(content)
print("Patch 3 complete.")
