"""
专享策略26：基于"状态机"的多因子策略 — 回测脚本
=================================================
数据来源: AKShare (免费，无需 API Key)
标的:     沪深A股日线数据（若无akshare则生成模拟数据）
回测区间: 2021-01-01 ~ 2024-12-31
初始资金: 1,000,000 元

运行方式:
    python run_state_machine_backtest.py

输出:
    - 控制台：详细回测报告
    - D:\\repo\\vnpy\\backtest_result.txt：结果文本
"""

import sys
import os
import math
import json
from datetime import datetime, date, timedelta
from typing import Optional, List
from dataclasses import dataclass, field

# ── 路径设置 ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vnpy.trader.constant import Exchange, Interval, Direction, Offset
from vnpy.trader.object import BarData, TradeData

from state_machine_strategy import StateMachineStrategy

# ──────────────────────────────────────────────
# 回测配置
# ──────────────────────────────────────────────

CAPITAL = 1_000_000    # 初始资金
START_DATE = "20210101"
END_DATE   = "20241231"
COMMISSION_RATE = 0.0003   # 手续费万三
STAMP_TAX       = 0.001    # 印花税千一（卖出时）

# 测试标的（沪深A股，覆盖大/中/小盘）
STOCKS = [
    {"symbol": "000300", "exchange": Exchange.SSE,  "name": "沪深300指数"},   # 大盘基准
    {"symbol": "600519", "exchange": Exchange.SSE,  "name": "贵州茅台"},
    {"symbol": "000858", "exchange": Exchange.SZSE, "name": "五粮液"},
    {"symbol": "601318", "exchange": Exchange.SSE,  "name": "中国平安"},
    {"symbol": "300750", "exchange": Exchange.SZSE, "name": "宁德时代"},
]

# 策略参数
STRATEGY_SETTING = {
    "ma_fast": 5,
    "ma_slow": 20,
    "rsi_period": 14,
    "rsi_bull": 55.0,
    "rsi_bear": 45.0,
    "vol_period": 20,
    "vol_multi": 1.2,
    "atr_period": 14,
    "atr_multi": 2.0,
    "bull_threshold": 3,
    "bear_threshold": 3,
    "fixed_size": 100,   # A股以手为单位（100股/手）
    "enable_short": False,  # A股不做空
}


# ──────────────────────────────────────────────
# Mock CTA 引擎（与策略解耦）
# ──────────────────────────────────────────────

class MockCtaEngine:
    """模拟 CTA 引擎：立即成交，记录成交流水"""

    def __init__(self):
        self.trades: list = []
        self._order_id = 0
        self._trade_id = 0
        self.logs: list = []

    def send_order(self, strategy, direction, offset, price, volume, stop=False, lock=False, net=False):
        self._order_id += 1
        self._trade_id += 1
        oid = f"O{self._order_id:06d}"
        tid = f"T{self._trade_id:06d}"

        self.trades.append({
            "tid": tid, "oid": oid,
            "direction": direction, "offset": offset,
            "price": price, "volume": volume,
            "datetime": datetime.now(),
        })

        # 模拟成交回调
        vt = strategy.vt_symbol
        sym, exch = (vt.split(".", 1) if "." in vt else (vt, ""))
        td = TradeData(
            symbol=sym,
            exchange=Exchange.SSE,
            orderid=oid, tradeid=tid,
            direction=direction, offset=offset,
            price=price, volume=volume,
            gateway_name="MOCK",
        )
        strategy.on_trade(td)

        # 同步 pos
        if direction == Direction.LONG  and offset == Offset.OPEN:
            strategy.pos += volume
        elif direction == Direction.SHORT and offset == Offset.CLOSE:
            strategy.pos -= volume
        elif direction == Direction.SHORT and offset == Offset.OPEN:
            strategy.pos -= volume
        elif direction == Direction.LONG  and offset == Offset.CLOSE:
            strategy.pos += volume

        return [oid]

    def cancel_order(self, strategy, vt_orderid): pass
    def cancel_all(self, strategy): pass
    def put_event(self, strategy): pass
    def put_strategy_event(self, strategy): pass
    def sync_strategy_data(self, strategy): pass
    def send_email(self, msg, strategy): pass
    def load_bar(self, *a, **kw): return []
    def load_tick(self, *a, **kw): return []
    def get_pricetick(self, strategy): return 0.01
    def get_size(self, strategy): return 1
    def get_capital(self, strategy): return CAPITAL

    def write_log(self, msg: str, strategy=None):
        self.logs.append(msg)

    def get_engine_type(self):
        try:
            from vnpy_ctastrategy.base import EngineType
            return EngineType.BACKTESTING
        except Exception:
            return "backtesting"


# ──────────────────────────────────────────────
# 数据获取（AKShare + 模拟数据回退）
# ──────────────────────────────────────────────

def fetch_akshare_daily(symbol: str, exchange: Exchange, start: str, end: str) -> list:
    """使用 AKShare 获取日线数据，失败则生成模拟数据"""
    try:
        import akshare as ak
        if exchange == Exchange.SSE:
            ak_sym = f"sh{symbol}"
        else:
            ak_sym = f"sz{symbol}"
        df = ak.stock_zh_a_daily(symbol=ak_sym, start_date=start, end_date=end, adjust="qfq")
        if df is None or len(df) == 0:
            raise ValueError("空数据")
        df = df.sort_values("date").reset_index(drop=True)
        bars = []
        for _, row in df.iterrows():
            try:
                dt = datetime.strptime(str(row["date"])[:10], "%Y-%m-%d")
                bar = BarData(
                    symbol=symbol,
                    exchange=exchange,
                    datetime=dt,
                    interval=Interval.DAILY,
                    open_price=float(row["open"]),
                    high_price=float(row["high"]),
                    low_price=float(row["low"]),
                    close_price=float(row["close"]),
                    volume=float(row.get("volume", row.get("vol", 0))),
                    turnover=float(row.get("amount", 0)),
                    gateway_name="akshare",
                )
                bars.append(bar)
            except Exception:
                continue
        print(f"  [AKShare] {symbol} 获取 {len(bars)} 根日K线")
        return bars
    except Exception as e:
        print(f"  [AKShare] 获取 {symbol} 失败: {e}，将生成模拟数据")
        return _generate_mock_bars(symbol, exchange, start, end)


def _generate_mock_bars(symbol: str, exchange: Exchange, start: str, end: str) -> list:
    """生成模拟K线（随机游走 + 趋势）"""
    import random
    random.seed(hash(symbol) % (2**31))

    start_dt = datetime.strptime(start, "%Y%m%d")
    end_dt   = datetime.strptime(end,   "%Y%m%d")

    bars = []
    price = random.uniform(20.0, 200.0)
    vol_base = random.uniform(5e6, 5e7)
    cur = start_dt

    # 随机趋势段（让策略有信号可捉）
    trend = 0.0
    trend_count = 0

    while cur <= end_dt:
        if cur.weekday() >= 5:   # 跳过周末
            cur += timedelta(days=1)
            continue

        # 趋势切换
        trend_count += 1
        if trend_count > random.randint(20, 60):
            trend = random.uniform(-0.004, 0.004)
            trend_count = 0

        daily_ret = trend + random.gauss(0, 0.015)
        open_p  = price
        close_p = price * (1 + daily_ret)
        high_p  = max(open_p, close_p) * random.uniform(1.0, 1.02)
        low_p   = min(open_p, close_p) * random.uniform(0.98, 1.0)
        volume  = vol_base * random.uniform(0.5, 2.0)

        if close_p <= 0:
            close_p = 0.01

        bar = BarData(
            symbol=symbol,
            exchange=exchange,
            datetime=cur,
            interval=Interval.DAILY,
            open_price=round(open_p, 2),
            high_price=round(high_p, 2),
            low_price=round(low_p, 2),
            close_price=round(close_p, 2),
            volume=round(volume),
            turnover=round(volume * (open_p + close_p) / 2),
            gateway_name="mock",
        )
        bars.append(bar)
        price = close_p
        cur += timedelta(days=1)

    print(f"  [模拟数据] {symbol} 生成 {len(bars)} 根日K线")
    return bars


# ──────────────────────────────────────────────
# 回测引擎
# ──────────────────────────────────────────────

@dataclass
class BacktestTrade:
    direction: Direction
    offset: Offset
    price: float
    volume: float
    dt: datetime
    pnl: float = 0.0


class BacktestEngine:
    """
    轻量级回测引擎
    - 逐bar喂给策略
    - 追踪持仓、盈亏、净值
    - 计算夏普、最大回撤等
    """

    def __init__(self, symbol: str, exchange: Exchange, capital: float = CAPITAL):
        self.symbol = symbol
        self.exchange = exchange
        self.capital = capital

        self.trades: list = []
        self.daily_returns: list = []
        self.net_values: list = []

        self._position = 0.0     # 当前持仓量
        self._avg_price = 0.0    # 持仓均价
        self._realized_pnl = 0.0

        self._engine: Optional[MockCtaEngine] = None
        self._strategy: Optional[StateMachineStrategy] = None
        self._last_trade_idx = 0

    def run(self, bars: list, setting: dict) -> dict:
        if not bars:
            return {}

        self._engine = MockCtaEngine()
        vt_sym = f"{self.symbol}.{self.exchange.value}"
        self._strategy = StateMachineStrategy(
            cta_engine=self._engine,
            strategy_name="state_machine",
            vt_symbol=vt_sym,
            setting=setting,
        )
        self._strategy.on_init()
        self._strategy.inited = True
        self._strategy.trading = True
        self._strategy.on_start()

        prev_date = None
        prev_pnl = 0.0
        net_val = self.capital

        for bar in bars:
            cur_date = bar.datetime.date() if hasattr(bar.datetime, "date") else bar.datetime

            # 每日结算
            if prev_date is not None and cur_date != prev_date:
                daily_pnl = self._realized_pnl - prev_pnl
                daily_ret = daily_pnl / self.capital
                self.daily_returns.append(daily_ret)
                net_val += daily_pnl
                self.net_values.append(net_val)
                prev_pnl = self._realized_pnl

            prev_date = cur_date

            # 推送K线
            self._strategy.on_bar(bar)

            # 处理新成交
            self._process_trades(bar.datetime, bar.close_price)

        # 最后一日
        daily_pnl = self._realized_pnl - prev_pnl
        self.daily_returns.append(daily_pnl / self.capital)
        net_val += daily_pnl
        self.net_values.append(net_val)

        return self._calc_stats(bars)

    def _process_trades(self, dt: datetime, close: float):
        """处理 mock engine 中的新增成交"""
        for i in range(self._last_trade_idx, len(self._engine.trades)):
            t = self._engine.trades[i]
            d = t["direction"]
            o = t["offset"]
            p = t["price"]
            v = t["volume"]

            pnl = 0.0
            commission = p * v * COMMISSION_RATE

            if d == Direction.LONG and o == Offset.OPEN:
                # 开多
                total = self._position + v
                if total > 0:
                    self._avg_price = (self._position * self._avg_price + v * p) / total
                self._position = total
            elif d == Direction.SHORT and o == Offset.CLOSE:
                # 平多
                pnl = (p - self._avg_price) * v
                self._position -= v
                commission += p * v * STAMP_TAX
                if self._position <= 1e-6:
                    self._position = 0.0
                    self._avg_price = 0.0
            elif d == Direction.SHORT and o == Offset.OPEN:
                # 开空
                total = abs(self._position) + v
                if total > 0:
                    self._avg_price = (abs(self._position) * self._avg_price + v * p) / total
                self._position -= v
            elif d == Direction.LONG and o == Offset.CLOSE:
                # 平空
                pnl = (self._avg_price - p) * v
                self._position += v
                commission += p * v * STAMP_TAX
                if self._position >= -1e-6:
                    self._position = 0.0
                    self._avg_price = 0.0

            net_pnl = pnl - commission
            self._realized_pnl += net_pnl

            self.trades.append(BacktestTrade(
                direction=d, offset=o, price=p, volume=v,
                dt=dt, pnl=net_pnl,
            ))

        self._last_trade_idx = len(self._engine.trades)

    def _calc_stats(self, bars: list) -> dict:
        """计算回测统计指标"""
        import statistics

        total_pnl = self._realized_pnl

        # 未实现盈亏
        if self._position != 0 and self._avg_price != 0:
            last_close = bars[-1].close_price
            unrealized = (last_close - self._avg_price) * self._position
        else:
            unrealized = 0.0

        total_ret = total_pnl / self.capital
        # 含未实现
        total_ret_incl = (total_pnl + unrealized) / self.capital

        # 最大回撤
        max_dd = 0.0
        max_dd_pct = 0.0
        peak = self.capital
        for nv in self.net_values:
            if nv > peak:
                peak = nv
            dd = peak - nv
            dd_pct = dd / peak if peak > 0 else 0.0
            if dd_pct > max_dd_pct:
                max_dd = dd
                max_dd_pct = dd_pct

        # 夏普比率（年化，基于日收益率）
        dr = self.daily_returns
        if len(dr) > 1:
            mean_dr = sum(dr) / len(dr)
            variance = sum((r - mean_dr) ** 2 for r in dr) / (len(dr) - 1)
            std_dr = math.sqrt(variance) if variance > 0 else 0.0
            sharpe = (mean_dr / std_dr * math.sqrt(252)) if std_dr > 0 else 0.0
        else:
            sharpe = 0.0

        # 年化收益率
        trading_days = len(self.daily_returns)
        if trading_days > 0:
            annual_ret = (1 + total_ret) ** (252 / trading_days) - 1
        else:
            annual_ret = 0.0

        # 卡玛比率
        calmar = abs(annual_ret / max_dd_pct) if max_dd_pct > 0 else 0.0

        # 交易统计
        closed = [t for t in self.trades if t.pnl != 0]
        wins   = [t for t in closed if t.pnl > 0]
        losses = [t for t in closed if t.pnl < 0]
        win_rate = len(wins) / len(closed) if closed else 0.0
        avg_win  = sum(t.pnl for t in wins)  / len(wins)  if wins   else 0.0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0.0
        pnl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

        start_dt = bars[0].datetime
        end_dt   = bars[-1].datetime

        return {
            "symbol":       self.symbol,
            "start_date":   str(start_dt)[:10],
            "end_date":     str(end_dt)[:10],
            "trading_days": trading_days,
            "total_bars":   len(bars),
            "capital":      self.capital,
            "total_pnl":    total_pnl,
            "unrealized":   unrealized,
            "total_return": total_ret,
            "total_return_incl": total_ret_incl,
            "annual_return": annual_ret,
            "max_drawdown":  max_dd,
            "max_drawdown_pct": max_dd_pct,
            "sharpe_ratio":  sharpe,
            "calmar_ratio":  calmar,
            "trade_count":   len(self.trades),
            "closed_trades": len(closed),
            "win_count":     len(wins),
            "loss_count":    len(losses),
            "win_rate":      win_rate,
            "avg_win":       avg_win,
            "avg_loss":      avg_loss,
            "pnl_ratio":     pnl_ratio,
            "final_position": self._position,
        }


# ──────────────────────────────────────────────
# 报告输出
# ──────────────────────────────────────────────

def print_single_result(name: str, s: dict):
    """打印单标的回测结果"""
    if not s:
        print(f"  {name}: 无结果")
        return
    lines = [
        f"",
        f"  ┌─── {name} 回测结果 ─────────────────────────────",
        f"  │ 回测区间:     {s['start_date']}  ~  {s['end_date']}",
        f"  │ 交易天数:     {s['trading_days']}  |  K线数量: {s['total_bars']}",
        f"  │",
        f"  │ 【盈亏统计】",
        f"  │   初始资金:   {s['capital']:>14,.2f} 元",
        f"  │   已实现盈亏: {s['total_pnl']:>+14,.2f} 元",
        f"  │   未实现盈亏: {s['unrealized']:>+14,.2f} 元",
        f"  │   总收益率:   {s['total_return']:>+13.2%}",
        f"  │   含浮盈收益: {s['total_return_incl']:>+13.2%}",
        f"  │   年化收益率: {s['annual_return']:>+13.2%}",
        f"  │",
        f"  │ 【风险指标】",
        f"  │   最大回撤:   {s['max_drawdown']:>14,.2f} 元",
        f"  │   最大回撤率: {s['max_drawdown_pct']:>+13.2%}",
        f"  │   夏普比率:   {s['sharpe_ratio']:>13.2f}",
        f"  │   卡玛比率:   {s['calmar_ratio']:>13.2f}",
        f"  │",
        f"  │ 【交易统计】",
        f"  │   总交易次数: {s['trade_count']:>14}",
        f"  │   平仓次数:   {s['closed_trades']:>14}",
        f"  │   盈利次数:   {s['win_count']:>14}",
        f"  │   亏损次数:   {s['loss_count']:>14}",
        f"  │   胜   率:    {s['win_rate']:>13.2%}",
        f"  │   平均盈利:   {s['avg_win']:>+14,.2f} 元",
        f"  │   平均亏损:   {s['avg_loss']:>+14,.2f} 元",
        f"  │   盈亏比:     {s['pnl_ratio']:>13.2f}",
        f"  └─────────────────────────────────────────────────",
    ]
    print("\n".join(lines))
    return lines


def print_summary(results: list):
    """打印汇总对比表"""
    valid = [r for r in results if r]
    if not valid:
        print("无有效回测结果")
        return

    print(f"\n{'='*90}")
    print(f"{'基于状态机的多因子策略  —  回测汇总对比':^90}")
    print(f"{'='*90}")
    header = f"{'标的':<14} {'收益率':>10} {'年化收益':>10} {'最大回撤率':>10} {'夏普比率':>10} {'胜率':>8} {'交易次数':>8}"
    print(header)
    print("-" * 90)
    for r in valid:
        name = r.get("symbol", "?")
        print(
            f"{name:<14} "
            f"{r['total_return']:>+9.2%} "
            f"{r['annual_return']:>+9.2%} "
            f"{r['max_drawdown_pct']:>9.2%} "
            f"{r['sharpe_ratio']:>9.2f} "
            f"{r['win_rate']:>7.2%} "
            f"{r['trade_count']:>8}"
        )

    # 平均值
    print("-" * 90)
    n = len(valid)
    avg_ret    = sum(r['total_return']      for r in valid) / n
    avg_ann    = sum(r['annual_return']     for r in valid) / n
    avg_dd     = sum(r['max_drawdown_pct']  for r in valid) / n
    avg_sharpe = sum(r['sharpe_ratio']      for r in valid) / n
    avg_wr     = sum(r['win_rate']          for r in valid) / n
    avg_tc     = sum(r['trade_count']       for r in valid) / n
    print(
        f"{'平均值':<14} "
        f"{avg_ret:>+9.2%} "
        f"{avg_ann:>+9.2%} "
        f"{avg_dd:>9.2%} "
        f"{avg_sharpe:>9.2f} "
        f"{avg_wr:>7.2%} "
        f"{avg_tc:>8.1f}"
    )
    print(f"{'='*90}")


# ──────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────

def main():
    banner = "=" * 60
    print(banner)
    print('  专享策略26：基于"状态机"的多因子策略  —  回测')
    print(banner)
    print(f"  数据区间: {START_DATE} ~ {END_DATE}")
    print(f"  初始资金: {CAPITAL:,.0f} 元")
    print(f"  手续费:   {COMMISSION_RATE*10000:.1f} 万分之{COMMISSION_RATE*10000:.0f}")
    print(f"  印花税:   千分之 {STAMP_TAX*1000:.0f}（卖出）")
    print(f"  策略参数: {json.dumps({k: v for k, v in STRATEGY_SETTING.items()}, ensure_ascii=False)}")
    print()

    all_results = []
    all_lines   = []

    for stock in STOCKS:
        sym  = stock["symbol"]
        exch = stock["exchange"]
        name = stock["name"]
        print(f"\n[{name} ({sym})]")

        # 1. 获取数据
        bars = fetch_akshare_daily(sym, exch, START_DATE, END_DATE)
        if not bars:
            print(f"  无数据，跳过")
            continue

        print(f"  数据范围: {bars[0].datetime} ~ {bars[-1].datetime}")

        # 2. 运行回测
        engine = BacktestEngine(sym, exch, CAPITAL)
        stats  = engine.run(bars, STRATEGY_SETTING)
        stats["name"] = name
        all_results.append(stats)

        # 3. 打印单标的结果
        lines = print_single_result(name, stats)
        if lines:
            all_lines.extend(lines)

    # 4. 汇总对比
    print_summary(all_results)

    # 5. 保存结果文件
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_result.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write('专享策略26：基于"状态机"的多因子策略  —  回测报告\n')
        f.write("=" * 60 + "\n\n")
        f.write(f"回测区间: {START_DATE} ~ {END_DATE}\n")
        f.write(f"初始资金: {CAPITAL:,.0f} 元\n")
        f.write(f"策略参数: {json.dumps(STRATEGY_SETTING, ensure_ascii=False, indent=2)}\n\n")

        for r in all_results:
            name = r.get("name", r.get("symbol", "?"))
            f.write(f"\n{'─'*50}\n")
            f.write(f"标的: {name} ({r['symbol']})\n")
            f.write(f"{'─'*50}\n")
            f.write(f"  回测区间:     {r['start_date']} ~ {r['end_date']}\n")
            f.write(f"  交易天数:     {r['trading_days']}\n")
            f.write(f"  已实现盈亏:   {r['total_pnl']:+,.2f} 元\n")
            f.write(f"  总收益率:     {r['total_return']:+.2%}\n")
            f.write(f"  年化收益率:   {r['annual_return']:+.2%}\n")
            f.write(f"  最大回撤率:   {r['max_drawdown_pct']:.2%}\n")
            f.write(f"  夏普比率:     {r['sharpe_ratio']:.2f}\n")
            f.write(f"  卡玛比率:     {r['calmar_ratio']:.2f}\n")
            f.write(f"  总交易次数:   {r['trade_count']}\n")
            f.write(f"  胜   率:      {r['win_rate']:.2%}\n")
            f.write(f"  平均盈利:     {r['avg_win']:+,.2f} 元\n")
            f.write(f"  平均亏损:     {r['avg_loss']:+,.2f} 元\n")
            f.write(f"  盈亏比:       {r['pnl_ratio']:.2f}\n")

        f.write("\n" + "=" * 60 + "\n")
        f.write("策略说明：\n")
        f.write("  本策略基于状态机框架，通过4个技术因子投票判断市场状态：\n")
        f.write("  1. 趋势因子: MA5/MA20 均线方向\n")
        f.write("  2. 动量因子: RSI(14) 是否超过55/45\n")
        f.write("  3. 量能因子: 成交量是否超过均量*1.2倍\n")
        f.write("  4. MACD因子: MACD Histogram 正负\n")
        f.write("  当3个及以上因子看多 → 进入多头状态，开多\n")
        f.write("  当3个及以上因子看空 → 进入空头状态，平多\n")
        f.write("  否则进入中性状态，平仓观望\n")
        f.write("  止损：入场价 - 2倍ATR(14)\n\n")
        f.write("注意：\n")
        f.write("  * 若AKShare无法连接，回测使用模拟数据（结果仅供参考）\n")
        f.write("  * 本回测不考虑涨跌停限制和冲击成本\n")
        f.write("  * 不构成投资建议\n")

    print(f"\n✅ 回测报告已保存: {output_path}")
    return all_results


if __name__ == "__main__":
    results = main()
