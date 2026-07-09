"""Unit test for the A38 intrabar fill reference used by the A35 cross-check.

Verifies the a38_intrabar_trades() model (fill = min/max(trigger, close)) and its gap
flag, independently of the real DB, so the cross-check's per-trade convergence /
conservatism assertions rest on tested logic.
"""
from diagnostics.stop_execution_model_crosscheck import a38_intrabar_trades


class _StubLoader:
    def __init__(self, bars):
        self._bars = bars

    def load(self, symbol, start_dt, end_dt):
        return (self._bars, None)


def _pair(open_price=100.0):
    return {
        "symbol": "X", "strategy": "一买多头", "direction": "long",
        "open_dt": "2024-01-05 22:00:00", "close_dt": "2024-01-05 23:30:00",
        "open_price": open_price, "close_price": 96.0,
    }


def test_a38_non_gap_fills_at_trigger():
    # trigger = 100*(1-0.02) = 98; bar low pierces 98 but closes above it -> non-gap.
    bars = [{"dt": None, "open": 100, "high": 100.5, "low": 97.0, "close": 99.0}]
    loader = _StubLoader(bars)
    trades, unavail = a38_intrabar_trades([_pair()], loader, 200)
    assert not unavail
    t = trades[0]
    assert t["triggered"] is True and t["gap"] is False
    assert abs(t["stressed_exit_price"] - 98.0) < 1e-9        # min(98, 99) = 98
    assert abs(t["pnl_pct"] - (-2.0)) < 1e-9


def test_a38_gap_fills_at_close_worse_than_trigger():
    # bar gaps through: low and close both below trigger 98 -> fill at close (96), gap=True.
    bars = [{"dt": None, "open": 97.0, "high": 97.2, "low": 95.0, "close": 96.0}]
    loader = _StubLoader(bars)
    trades, _ = a38_intrabar_trades([_pair()], loader, 200)
    t = trades[0]
    assert t["gap"] is True
    assert abs(t["stressed_exit_price"] - 96.0) < 1e-9        # min(98, 96) = 96
    assert t["pnl_pct"] < -2.0                                 # worse than nominal stop


def test_a38_no_trigger_when_low_above_trigger():
    bars = [{"dt": None, "open": 100, "high": 101, "low": 99.0, "close": 100.5}]
    loader = _StubLoader(bars)
    trades, _ = a38_intrabar_trades([_pair()], loader, 200)
    assert trades[0]["triggered"] is False
