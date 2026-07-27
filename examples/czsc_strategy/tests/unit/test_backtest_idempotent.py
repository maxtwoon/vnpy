"""Regression test for BacktestEngine.run() idempotency."""
from datetime import datetime, timedelta
from czsc.objects import RawBar, Freq

from chan_strategy.backtest_engine import BacktestEngine


def make_raw_bars(n: int = 600) -> list:
    """Create synthetic 1-minute bars for idempotency testing."""
    base = datetime(2024, 1, 2, 9, 30)
    bars = []
    price = 100.0
    for i in range(n):
        dt = base + timedelta(minutes=i)
        # Simple oscillating price to create some structure
        open_price = price
        close = price + (1 if i % 20 < 10 else -1) * 0.5
        high = max(open_price, close) + 0.2
        low = min(open_price, close) - 0.2
        bars.append(RawBar(
            symbol="TEST",
            id=i,
            dt=dt,
            freq=Freq.F1,
            open=open_price,
            close=close,
            high=high,
            low=low,
            vol=100,
            amount=open_price * 100,
        ))
        price = close
    return bars


def test_run_is_idempotent():
    """BacktestEngine.run() 重复调用应得到相同结果，不污染状态。"""
    engine = BacktestEngine(
        symbol="TEST",
        freq="1",
        initial_capital=1000000,
        commission_rate=0.0001,
        slippage=0.0005,
        db_path="__nonexistent__.db",  # 阻止真实数据库加载
    )
    # 绕过数据库加载，直接注入测试数据
    test_bars = make_raw_bars()
    engine.load_data = lambda: setattr(engine, "bars", test_bars) or True

    report1 = engine.run(warmup_bars=5)
    curve1 = list(engine.equity_curve)

    report2 = engine.run(warmup_bars=5)
    curve2 = list(engine.equity_curve)

    assert "error" not in report1, f"First run failed: {report1}"
    assert "error" not in report2, f"Second run failed: {report2}"
    assert len(curve1) == len(curve2), (
        f"Equity curve length changed between runs: {len(curve1)} vs {len(curve2)}"
    )
    assert report1["total_return_pct"] == report2["total_return_pct"], (
        f"Total return changed between runs: {report1['total_return_pct']} "
        f"vs {report2['total_return_pct']}"
    )
    assert report1["total_trades"] == report2["total_trades"], (
        f"Total trades changed between runs: {report1['total_trades']} "
        f"vs {report2['total_trades']}"
    )
    print("test_run_is_idempotent passed:")
    print(f"  equity_curve length: {len(curve1)}")
    print(f"  total_return_pct: {report1['total_return_pct']:.4f}")
    print(f"  total_trades: {report1['total_trades']}")


def test_run_creates_fresh_state():
    """BacktestEngine.run() 每次调用都应创建全新的策略/持仓对象，避免状态污染。"""
    engine = BacktestEngine(
        symbol="TEST",
        freq="1",
        initial_capital=1000000,
        commission_rate=0.0001,
        slippage=0.0005,
        db_path="__nonexistent__.db",
    )
    test_bars = make_raw_bars()
    engine.load_data = lambda: setattr(engine, "bars", test_bars) or True

    report1 = engine.run(warmup_bars=5)
    assert "error" not in report1
    curve1_len = len(engine.equity_curve)
    old_strategy = engine.strategy
    old_positions = list(engine.strategy.positions)

    # 故意污染第一次运行后的状态（模拟错误地保留引用）
    for pos in old_positions:
        pos.pairs.append({"dummy": True})

    report2 = engine.run(warmup_bars=5)
    assert "error" not in report2

    # run() 必须创建新的策略对象与持仓对象
    assert engine.strategy is not old_strategy, (
        "run() reused the same strategy instance between calls"
    )
    new_positions = list(engine.strategy.positions)
    assert len(new_positions) == len(old_positions)
    for new_pos, old_pos in zip(new_positions, old_positions):
        assert new_pos is not old_pos, (
            f"run() reused position instance {new_pos.name} between calls"
        )
        # 新持仓的 pairs 不应被旧持仓的污染影响
        assert {"dummy": True} not in new_pos.pairs, (
            f"position {new_pos.name} was polluted by previous run"
        )

    # 引擎级别的曲线也应被重置为与第一次运行时相同长度
    assert len(engine.equity_curve) == curve1_len, (
        f"equity_curve length not reset: {len(engine.equity_curve)} vs {curve1_len}"
    )

    print("test_run_creates_fresh_state passed:")
    print(f"  strategy recreated: {engine.strategy is not old_strategy}")
    print(f"  positions recreated: {all(a is not b for a, b in zip(new_positions, old_positions))}")


if __name__ == "__main__":
    test_run_is_idempotent()
    test_run_creates_fresh_state()
