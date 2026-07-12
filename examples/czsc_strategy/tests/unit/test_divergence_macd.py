"""A43 P4 — MACD-area divergence gate tests.

Verify that ``divergence_model="amplitude"`` reproduces the legacy amplitude
behavior, while ``"macd"`` can produce a different classification on a fixture
where price amplitude and MACD |hist| area disagree.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest
from czsc.objects import Direction

from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.sell_signals import signal_first_sell
from chan_strategy.signals import (
    _macd,
    _divergence_power,
    signal_divergence_status,
    signal_first_buy,
)


def _raw_bar(dt, close, high=None, low=None):
    from czsc.objects import RawBar, Freq
    high = high if high is not None else close + 0.5
    low = low if low is not None else close - 0.5
    return RawBar(
        symbol="TEST", id=0, dt=dt, freq=Freq.F30,
        open=close, high=high, low=low, close=close,
        vol=100, amount=100 * close,
    )


def _trend_bars(start_dt, n, start_close, end_close):
    """Return n bars whose closes trend linearly from start_close to end_close."""
    dts = [start_dt + timedelta(minutes=i) for i in range(n)]
    closes = np.linspace(start_close, end_close, n)
    return [_raw_bar(dt, float(c)) for dt, c in zip(dts, closes, strict=False)]


def _flat_bars(start_dt, n, close):
    """Return n bars with a constant close (very low MACD momentum)."""
    return [_raw_bar(start_dt + timedelta(minutes=i), float(close)) for i in range(n)]


def _bi_with_bars(direction, low, high, sdt, edt, bars):
    from tests.conftest import FakeBI
    return FakeBI(direction=direction, low=low, high=high, sdt=sdt, edt=edt, raw_bars=bars)


def _czsc_from_bis(bis):
    """Build a FakeCZSC whose bars_raw is the concatenation of BI raw_bars."""
    from tests.conftest import FakeCZSC
    all_bars = []
    for bi in bis:
        all_bars.extend(list(getattr(bi, "raw_bars", []) or []))
    all_bars.sort(key=lambda b: b.dt)
    return FakeCZSC(bis=bis, bars_raw=all_bars)


def test_macd_helper_standard_params():
    closes = np.concatenate([
        np.linspace(100, 95, 30),   # sustained down trend
        np.linspace(95, 97, 10),    # small pullback
    ])
    dif, dea, hist = _macd(closes, 12, 26, 9)
    assert len(dif) == len(closes)
    assert len(dea) == len(closes)
    assert len(hist) == len(closes)
    assert np.isfinite(hist).all()


def test_amplitude_default_is_byte_identical_to_explicit(czsc_factory, bi_factory):
    """Default divergence_model must behave identically to explicit amplitude."""
    base = datetime(2024, 1, 1)
    bis = [
        bi_factory(Direction.Up, 90, 110, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 92, 108, base + timedelta(minutes=1), base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 94, 106, base + timedelta(minutes=2), base + timedelta(minutes=3)),
        bi_factory(Direction.Down, 80, 100, base + timedelta(minutes=3), base + timedelta(minutes=4)),
        bi_factory(Direction.Up, 88, 103, base + timedelta(minutes=4), base + timedelta(minutes=5)),
        bi_factory(Direction.Down, 78, 95, base + timedelta(minutes=5), base + timedelta(minutes=6)),
        bi_factory(Direction.Up, 85, 105, base + timedelta(minutes=6), base + timedelta(minutes=7)),
    ]
    c = czsc_factory(bis)

    default_status = signal_divergence_status(c)
    default_buy = signal_first_buy(c)

    STRATEGY_CONFIG["divergence_model"] = "amplitude"
    try:
        amplitude_status = signal_divergence_status(c)
        amplitude_buy = signal_first_buy(c)
    finally:
        STRATEGY_CONFIG["divergence_model"] = "amplitude"

    assert amplitude_status == default_status
    assert amplitude_buy == default_buy


def test_divergence_power_respects_config():
    base = datetime(2024, 1, 1)
    enter_bars = _flat_bars(base, 40, 100.0)
    leave_bars = _flat_bars(base + timedelta(minutes=40), 40, 100.0)
    enter_bi = _bi_with_bars(Direction.Down, 95, 105, base, base + timedelta(minutes=39), enter_bars)
    leave_bi = _bi_with_bars(Direction.Down, 96, 104, base + timedelta(minutes=40), base + timedelta(minutes=79), leave_bars)
    c = _czsc_from_bis([enter_bi, leave_bi])

    STRATEGY_CONFIG["divergence_model"] = "amplitude"
    try:
        amp_enter, amp_leave = _divergence_power(enter_bi, leave_bi, c)
        assert amp_enter == pytest.approx(abs(enter_bi.high - enter_bi.low))
        assert amp_leave == pytest.approx(abs(leave_bi.high - leave_bi.low))

        STRATEGY_CONFIG["divergence_model"] = "macd"
        macd_enter, macd_leave = _divergence_power(enter_bi, leave_bi, c)
        # Flat closes -> MACD magnitudes should be near zero.
        assert macd_enter >= 0.0
        assert macd_leave >= 0.0
    finally:
        STRATEGY_CONFIG["divergence_model"] = "amplitude"


def test_amplitude_diverges_macd_does_not():
    """Fixture: price amplitude says divergence, MACD |hist| area says no."""
    base = datetime(2024, 1, 1)
    # Enter segment: large amplitude but flat closes -> small MACD area.
    enter_bars = _flat_bars(base, 40, 100.0)
    enter_bi = _bi_with_bars(Direction.Down, 95, 105, base, base + timedelta(minutes=39), enter_bars)

    # Leave segment: smaller amplitude but sustained directional trend -> larger MACD area.
    leave_start = base + timedelta(minutes=40)
    leave_bars = _trend_bars(leave_start, 30, 104.0, 99.0)
    leave_bi = _bi_with_bars(Direction.Down, 99, 104, leave_start, leave_start + timedelta(minutes=29), leave_bars)

    c = _czsc_from_bis([enter_bi, leave_bi])

    STRATEGY_CONFIG["divergence_model"] = "amplitude"
    try:
        amp_enter, amp_leave = _divergence_power(enter_bi, leave_bi, c)
        assert amp_leave < amp_enter  # amplitude diverges

        STRATEGY_CONFIG["divergence_model"] = "macd"
        macd_enter, macd_leave = _divergence_power(enter_bi, leave_bi, c)
        assert macd_leave > macd_enter  # MACD does NOT diverge
    finally:
        STRATEGY_CONFIG["divergence_model"] = "amplitude"


def test_macd_diverges_amplitude_does_not():
    """Fixture: MACD |hist| area says divergence, price amplitude says no."""
    base = datetime(2024, 1, 1)
    # Enter segment: strong sustained trend -> large MACD area.
    enter_bars = _trend_bars(base, 30, 105.0, 99.0)
    enter_bi = _bi_with_bars(Direction.Down, 99, 105, base, base + timedelta(minutes=29), enter_bars)

    # Leave segment: same amplitude as enter but flat closes -> small MACD area.
    leave_start = base + timedelta(minutes=30)
    leave_bars = _flat_bars(leave_start, 30, 100.0)
    leave_bi = _bi_with_bars(Direction.Down, 94, 100, leave_start, leave_start + timedelta(minutes=29), leave_bars)

    c = _czsc_from_bis([enter_bi, leave_bi])

    STRATEGY_CONFIG["divergence_model"] = "amplitude"
    try:
        amp_enter, amp_leave = _divergence_power(enter_bi, leave_bi, c)
        assert amp_leave >= amp_enter  # amplitude does NOT diverge

        STRATEGY_CONFIG["divergence_model"] = "macd"
        macd_enter, macd_leave = _divergence_power(enter_bi, leave_bi, c)
        assert macd_leave < macd_enter  # MACD diverges
    finally:
        STRATEGY_CONFIG["divergence_model"] = "amplitude"


def test_signal_first_buy_differs_between_models():
    """A fixture where amplitude and MACD produce different first-buy classifications."""
    base = datetime(2024, 1, 1)
    # Zhongshu: BIs 0-2 overlap (zd=94, zg=106).
    # Enter segment (BI0): large amplitude, flat closes -> MACD area small.
    # Leave segment (BI3): smaller amplitude, strong down trend -> MACD area large.
    # Confirming up segment (BI4).
    bis = [
        _bi_with_bars(Direction.Up, 90, 110, base, base + timedelta(minutes=40),
                      _flat_bars(base, 41, 100.0)),
        _bi_with_bars(Direction.Down, 92, 108, base + timedelta(minutes=41), base + timedelta(minutes=50),
                      _trend_bars(base + timedelta(minutes=41), 10, 108.0, 92.0)),
        _bi_with_bars(Direction.Up, 94, 106, base + timedelta(minutes=51), base + timedelta(minutes=60),
                      _trend_bars(base + timedelta(minutes=51), 10, 94.0, 106.0)),
        _bi_with_bars(Direction.Down, 82, 88, base + timedelta(minutes=61), base + timedelta(minutes=90),
                      _trend_bars(base + timedelta(minutes=61), 30, 88.0, 82.0)),
        _bi_with_bars(Direction.Up, 82, 86, base + timedelta(minutes=91), base + timedelta(minutes=100),
                      _trend_bars(base + timedelta(minutes=91), 10, 82.0, 86.0)),
    ]
    c = _czsc_from_bis(bis)

    STRATEGY_CONFIG["divergence_model"] = "amplitude"
    try:
        amplitude_value = next(iter(signal_first_buy(c).values()))

        STRATEGY_CONFIG["divergence_model"] = "macd"
        macd_value = next(iter(signal_first_buy(c).values()))

        assert "一买" in amplitude_value or "非一买" in amplitude_value
        assert "一买" in macd_value or "非一买" in macd_value
        # The two models disagree on this fixture.
        assert amplitude_value.split("_")[0] != macd_value.split("_")[0]
    finally:
        STRATEGY_CONFIG["divergence_model"] = "amplitude"


def test_signal_first_sell_differs_between_models():
    """A fixture where amplitude and MACD produce different first-sell classifications."""
    base = datetime(2024, 1, 1)
    # Zhongshu: BIs 0-2 overlap (zd=94, zg=106).
    # Enter segment (BI0): large amplitude, flat closes -> MACD area small.
    # Leave segment (BI3): smaller amplitude, strong up trend -> MACD area large.
    # Confirming down segment (BI4).
    bis = [
        _bi_with_bars(Direction.Down, 90, 110, base, base + timedelta(minutes=40),
                      _flat_bars(base, 41, 100.0)),
        _bi_with_bars(Direction.Up, 92, 108, base + timedelta(minutes=41), base + timedelta(minutes=50),
                      _trend_bars(base + timedelta(minutes=41), 10, 92.0, 108.0)),
        _bi_with_bars(Direction.Down, 94, 106, base + timedelta(minutes=51), base + timedelta(minutes=60),
                      _trend_bars(base + timedelta(minutes=51), 10, 106.0, 94.0)),
        _bi_with_bars(Direction.Up, 112, 118, base + timedelta(minutes=61), base + timedelta(minutes=90),
                      _trend_bars(base + timedelta(minutes=61), 30, 112.0, 118.0)),
        _bi_with_bars(Direction.Down, 115, 118, base + timedelta(minutes=91), base + timedelta(minutes=100),
                      _trend_bars(base + timedelta(minutes=91), 10, 118.0, 115.0)),
    ]
    c = _czsc_from_bis(bis)

    STRATEGY_CONFIG["divergence_model"] = "amplitude"
    try:
        amplitude_value = next(iter(signal_first_sell(c).values()))

        STRATEGY_CONFIG["divergence_model"] = "macd"
        macd_value = next(iter(signal_first_sell(c).values()))

        assert amplitude_value.split("_")[0] != macd_value.split("_")[0]
    finally:
        STRATEGY_CONFIG["divergence_model"] = "amplitude"


def test_signal_divergence_status_amplitude_vs_macd():
    base = datetime(2024, 1, 1)
    # Need >=5 BIs for signal_divergence_status.  Add a dummy BI before the
    # zhongshu so the latest zhongshu still has a leave segment after it.
    bis = [
        _bi_with_bars(Direction.Down, 88, 112, base, base + timedelta(minutes=10),
                      _flat_bars(base, 11, 100.0)),
        _bi_with_bars(Direction.Up, 90, 110, base + timedelta(minutes=11), base + timedelta(minutes=50),
                      _flat_bars(base + timedelta(minutes=11), 40, 100.0)),
        _bi_with_bars(Direction.Down, 92, 108, base + timedelta(minutes=51), base + timedelta(minutes=60),
                      _trend_bars(base + timedelta(minutes=51), 10, 108.0, 92.0)),
        _bi_with_bars(Direction.Up, 94, 106, base + timedelta(minutes=61), base + timedelta(minutes=70),
                      _trend_bars(base + timedelta(minutes=61), 10, 94.0, 106.0)),
        _bi_with_bars(Direction.Down, 82, 88, base + timedelta(minutes=71), base + timedelta(minutes=100),
                      _trend_bars(base + timedelta(minutes=71), 30, 88.0, 82.0)),
    ]
    c = _czsc_from_bis(bis)

    STRATEGY_CONFIG["divergence_model"] = "amplitude"
    try:
        amplitude_value = next(iter(signal_divergence_status(c).values()))

        STRATEGY_CONFIG["divergence_model"] = "macd"
        macd_value = next(iter(signal_divergence_status(c).values()))

        assert amplitude_value.split("_")[0] != macd_value.split("_")[0]
    finally:
        STRATEGY_CONFIG["divergence_model"] = "amplitude"


def test_macd_params_are_standard_and_not_tuned():
    assert STRATEGY_CONFIG.get("macd_fast") == 12
    assert STRATEGY_CONFIG.get("macd_slow") == 26
    assert STRATEGY_CONFIG.get("macd_signal") == 9


def test_macd_mode_does_not_fallback_to_close_difference_on_short_history():
    """MACD mode must never fall back to an amplitude/close-difference proxy.

    With fewer confirmed bars than the conventional MACD warm-up length, the
    old fallback returned ``abs(last.close - first.close)``.  This test uses a
    short history (10 bars < 26) where both segments have the same first/last
    close, so a close-difference proxy would assign both segments zero power.
    The MACD-based result must instead reflect the intra-segment price action
    and therefore differ between the flat and trending segments.
    """
    base = datetime(2024, 1, 1)

    # Enter segment: flat closes -> MACD area near zero.
    enter_bars = _flat_bars(base, 5, 100.0)
    enter_bi = _bi_with_bars(
        Direction.Down, 95, 105, base, base + timedelta(minutes=4), enter_bars
    )

    # Leave segment: V-shaped trend that starts and ends at 100.
    leave_start = base + timedelta(minutes=5)
    leave_closes = [100.0, 104.0, 102.0, 104.0, 100.0]
    leave_bars = [
        _raw_bar(leave_start + timedelta(minutes=i), close=c)
        for i, c in enumerate(leave_closes)
    ]
    leave_bi = _bi_with_bars(
        Direction.Down, 96, 104, leave_start, leave_start + timedelta(minutes=4), leave_bars
    )

    c = _czsc_from_bis([enter_bi, leave_bi])

    # Amplitude mode is unaffected and uses the configured BI high/low.
    STRATEGY_CONFIG["divergence_model"] = "amplitude"
    try:
        amp_enter, amp_leave = _divergence_power(enter_bi, leave_bi, c)
        assert amp_enter == pytest.approx(10.0)
        assert amp_leave == pytest.approx(8.0)

        # MACD mode computes |hist| area even on short confirmed-bar history.
        STRATEGY_CONFIG["divergence_model"] = "macd"
        macd_enter, macd_leave = _divergence_power(enter_bi, leave_bi, c)
        # A close-difference fallback would have assigned zero to both segments.
        assert macd_leave > 0.0
        assert macd_enter < macd_leave
    finally:
        STRATEGY_CONFIG["divergence_model"] = "amplitude"
