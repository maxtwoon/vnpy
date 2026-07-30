"""ONE-SHOT / LEGACY patch script for archived Baostock backtest experiments.
路径已随 A107 迁移（原 _patch_backtest4.py → archive/one_shot_scripts/patch_backtest_4.py），未重新验证可运行性。"""

fpath = r'd:\repo\vnpy\examples\czsc_strategy\legacy\run_baostock_backtest.py'
content = open(fpath, 'r', encoding='utf-8').read()

# Change COOLDOWN from 48 to 144
old_cooldown = "        COOLDOWN = 48  # 平仓后至少等待1个交易日（48根5m K线）再开仓"
new_cooldown = "        COOLDOWN = 144  # 平仓后至少等待3个交易日（144根5m K线）再开仓"

if old_cooldown in content:
    content = content.replace(old_cooldown, new_cooldown)
    print("Cooldown changed to 144.")
else:
    print("ERROR: could not find COOLDOWN=48")

open(fpath, 'w', encoding='utf-8').write(content)

# Change profit_lock_pct_2 to 0.40 in STRATEGY_SETTING
fpath2 = r'd:\repo\vnpy\examples\czsc_strategy\legacy\run_baostock_backtest.py'
content2 = open(fpath2, 'r', encoding='utf-8').read()
old_pl2 = '    "profit_lock_pct_2": 0.30,'
new_pl2 = '    "profit_lock_pct_2": 0.40,  # 放宽止盈门槛'
if old_pl2 in content2:
    content2 = content2.replace(old_pl2, new_pl2)
    print("profit_lock_pct_2 changed to 0.40.")
    open(fpath2, 'w', encoding='utf-8').write(content2)
else:
    print("ERROR: could not find profit_lock_pct_2")

print("Patch 4 complete.")
