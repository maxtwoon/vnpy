"""A44 P5 — 4H CZSC no-lookahead test.

Mirrors ``test_daily_no_lookahead.py`` for the 240-minute CZSC level.
"""
from datetime import datetime

import pytest
from czsc.objects import Freq

from chan_strategy.backtest_engine import BacktestEngine
from chan_strategy.data_adapter import resample_bars


def test_4h_filter_does_not_see_current_bar_before_4h_bar_closes(synthetic_1m_bars):
    """4H bar timestamp is the last constituent 1m bar; the loop advances 4H
    CZSC only when ``h4_bar.dt <= current_bar.dt``.
    """
    # Start at a 4H-aligned boundary so groups are full 240-minute buckets.
    bars = synthetic_1m_bars(days=2, per_day=240, start=datetime(2024, 1, 2, 0, 0))
    h4_bars = resample_bars(bars, Freq.F120, 240)
    assert len(h4_bars) >= 2

    # 4H bar timestamp is the last 1m bar of the 240-minute group.
    first_h4 = h4_bars[0]
    expected_last_1m = bars[239]
    assert first_h4.dt == expected_last_1m.dt

    h4_bar_idx = 1
    # Current bar is before the second 4H bar has closed.
    current_intrabar = bars[240 + 120]  # inside the second 4H group
    seen = []
    while h4_bar_idx < len(h4_bars) and h4_bars[h4_bar_idx].dt <= current_intrabar.dt:
        seen.append(h4_bars[h4_bar_idx])
        h4_bar_idx += 1

    assert seen == []
    assert h4_bar_idx == 1

    # Once the current bar reaches the second 4H bar timestamp, it advances.
    current_at_close = h4_bars[1]
    while h4_bar_idx < len(h4_bars) and h4_bars[h4_bar_idx].dt <= current_at_close.dt:
        seen.append(h4_bars[h4_bar_idx])
        h4_bar_idx += 1

    assert seen == [h4_bars[1]]
    assert h4_bar_idx == 2


@pytest.mark.parametrize("resonance_filter", ["daily", "daily_4h"])
def test_backtest_engine_runs_without_4h_warmup_error(
    monkeypatch, mini_backtest_bars, resonance_filter
):
    """When 4H warmup is insufficient the engine should disable 4H filter, not crash."""
    from chan_strategy.config import STRATEGY_CONFIG

    original = dict(STRATEGY_CONFIG)
    try:
        STRATEGY_CONFIG["resonance_filter"] = resonance_filter
        STRATEGY_CONFIG["resonance_freq_4h"] = "240分钟"
        engine = BacktestEngine("TEST", db_path="none")
        engine.load_data = lambda: setattr(engine, "bars", mini_backtest_bars[:420]) or True
        report = engine.run(warmup_bars=2)
        assert "error" not in report
    finally:
        STRATEGY_CONFIG.clear()
        STRATEGY_CONFIG.update(original)
