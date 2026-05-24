"""Patch script to update run_baostock_backtest.py for new strategy."""
import re

fpath = r'd:\repo\vnpy\examples\czsc_strategy\run_baostock_backtest.py'
content = open(fpath, 'r', encoding='utf-8').read()

# -------------------------------------------------------
# Fix 1: run_single_backtest - remove fixed_size
# -------------------------------------------------------
old_func = (
    'def run_single_backtest(bars_5min: list[BarData], stock: dict) -> dict:\n'
    '    """为单只股票运行5分钟真实多周期回测。"""\n'
    '    # 按10%资金比例动态计算每次交易股数（A股最小单位100股）\n'
    '    price = bars_5min[0].close_price\n'
    '    position_value = CAPITAL * 0.10\n'
    '    fixed_size = max(100, int(position_value / price / 100) * 100)\n'
    '\n'
    '    setting = dict(STRATEGY_SETTING)\n'
    '    setting["fixed_size"] = fixed_size\n'
    '\n'
    '    backtester = SimpleBacktester(\n'
    '        strategy_class=CzscMultiTimeframeStrategy,\n'
    '        setting=setting,\n'
    '        symbol=stock["symbol"],\n'
    '        exchange=stock["exchange"],\n'
    '        capital=CAPITAL,\n'
    '    )\n'
    '\n'
    '    stats = backtester.run(bars_5min, disable_short=True)\n'
    '    stats["fixed_size"] = fixed_size\n'
    '    stats["price"] = price\n'
    '    return stats'
)

new_func = (
    'def run_single_backtest(bars_5min: list[BarData], stock: dict) -> dict:\n'
    '    """为单只股票运行5分钟真实多周期回测。"""\n'
    '    # 新策略通过total_capital参数自行计算仓位，直接使用STRATEGY_SETTING\n'
    '    setting = dict(STRATEGY_SETTING)\n'
    '\n'
    '    backtester = SimpleBacktester(\n'
    '        strategy_class=CzscMultiTimeframeStrategy,\n'
    '        setting=setting,\n'
    '        symbol=stock["symbol"],\n'
    '        exchange=stock["exchange"],\n'
    '        capital=CAPITAL,\n'
    '    )\n'
    '\n'
    '    stats = backtester.run(bars_5min, disable_short=True)\n'
    '    return stats'
)

if old_func in content:
    content = content.replace(old_func, new_func)
    print("Fix 1 (run_single_backtest) applied.")
else:
    print("Fix 1 FAILED: could not find old_func")

# -------------------------------------------------------
# Fix 2: print_report - remove fixed_size display
# -------------------------------------------------------
old_print = (
    '    fixed_size = stats.get("fixed_size", 0)\n'
    '    price_ref = stats.get("price", 0)\n'
    '    if fixed_size and price_ref:\n'
    '        pos_val = fixed_size * price_ref\n'
    '        pct = pos_val / CAPITAL * 100\n'
    '        print(f"  │ 动态仓位:   {fixed_size:>12,}股 (约{pos_val / 10000:.1f}万元，占资金{pct:.1f}%)")\n'
)
new_print = ''

if old_print in content:
    content = content.replace(old_print, new_print)
    print("Fix 2 (print_report fixed_size) applied.")
else:
    print("Fix 2 FAILED: could not find old_print")

# -------------------------------------------------------
# Fix 3: main() - remove old param prints and COOLDOWN_BARS
# -------------------------------------------------------
old_main_print = (
    '    print(f"策略参数: stop_loss={STRATEGY_SETTING[\'stop_loss_pct\']:.0%}, "\n'
    '          f"take_profit={STRATEGY_SETTING[\'take_profit_pct\']:.0%}, "\n'
    '          f"trailing_stop={STRATEGY_SETTING[\'trailing_stop_pct\']:.0%}")\n'
    '    print(f"入场条件: 4H!=DOWN, 30m!=DOWN, 无背驰, 5m底分型, 5m最后笔向上, 分型12根内新鲜")\n'
    '    print(f"冷却期: 平仓后 {COOLDOWN_BARS} 根K线禁止重开（减少频繁交易）")\n'
)
new_main_print = (
    '    print(f"策略参数: max_dist={STRATEGY_SETTING[\'max_distance_pct\']:.0%}, "\n'
    '          f"filter={STRATEGY_SETTING[\'filter_distance_pct\']:.0%}, "\n'
    '          f"profit_lock1={STRATEGY_SETTING[\'profit_lock_pct_1\']:.0%}, "\n'
    '          f"profit_lock2={STRATEGY_SETTING[\'profit_lock_pct_2\']:.0%}, "\n'
    '          f"risk_factor={STRATEGY_SETTING[\'risk_factor\']}")\n'
    '    print(f"入场条件: 5m突破中枢上沿 + 距4H下轨<={STRATEGY_SETTING[\'max_distance_pct\']:.0%}")\n'
    '    print(f"止损规则: 破4H下轨全清（无条件止损）")\n'
)

if old_main_print in content:
    content = content.replace(old_main_print, new_main_print)
    print("Fix 3 (main params print) applied.")
else:
    print("Fix 3 FAILED: could not find old_main_print")
    # Try simplified version
    old_v2 = (
        '    print(f"入场条件: 4H!=DOWN, 30m!=DOWN, 无背驰, 5m底分型, 5m最后笔向上, 分型12根内新鲜")\n'
        '    print(f"冷却期: 平仓后 {COOLDOWN_BARS} 根K线禁止重开（减少频繁交易）")\n'
    )
    new_v2 = (
        '    print(f"入场条件: 5m突破中枢上沿 + 距4H下轨<={STRATEGY_SETTING[\'max_distance_pct\']:.0%}")\n'
        '    print(f"止损规则: 破4H下轨全清（无条件止损）")\n'
    )
    if old_v2 in content:
        content = content.replace(old_v2, new_v2)
        print("Fix 3b applied.")

# -------------------------------------------------------
# Fix 4: main() title update
# -------------------------------------------------------
old_title = '    print("缱论多时间周期策略 — Baostock 5分钟真实多周期回测 [v2优化版]")'
new_title = '    print("缠论多时间周期策略 — Baostock 5分钟真实多周期回测 [波段战法分仓版]")'
if old_title in content:
    content = content.replace(old_title, new_title)
    print("Fix 4 (title) applied.")
else:
    print("Fix 4 FAILED (title)")

open(fpath, 'w', encoding='utf-8').write(content)
print("Patch complete.")
