from datetime import datetime, timedelta

from czsc.objects import Freq

from chan_strategy.data_adapter import resample_bars


def test_daily_filter_does_not_see_current_day_before_daily_bar_closes(synthetic_1m_bars):
    bars = synthetic_1m_bars(days=2, per_day=3, start=datetime(2024, 1, 2, 9, 0))
    daily_bars = resample_bars(bars, Freq.D)
    assert len(daily_bars) == 2

    daily_bar_idx = 1
    current_intraday_bar = bars[4]  # second day 09:01, before second daily bar timestamp 09:02
    seen = []
    while daily_bar_idx < len(daily_bars) and daily_bars[daily_bar_idx].dt <= current_intraday_bar.dt:
        seen.append(daily_bars[daily_bar_idx])
        daily_bar_idx += 1

    assert seen == []
    assert daily_bar_idx == 1

    current_day_closed_bar = bars[5]
    while daily_bar_idx < len(daily_bars) and daily_bars[daily_bar_idx].dt <= current_day_closed_bar.dt:
        seen.append(daily_bars[daily_bar_idx])
        daily_bar_idx += 1

    assert seen == [daily_bars[1]]
    assert daily_bar_idx == 2

