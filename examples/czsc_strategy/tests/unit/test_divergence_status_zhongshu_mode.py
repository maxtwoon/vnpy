"""P4 zhongshu selection fix tests.

Verify that ``STRATEGY_CONFIG["divergence_status_zhongshu_mode"]`` toggles
``signal_divergence_status`` between the legacy naive ``zhongshu_list[-1]``
behavior and the corrected ``departure_leg`` search already used by
``signal_first_buy`` / ``signal_first_sell``.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from czsc import Direction

from chan_strategy.config import STRATEGY_CONFIG
from chan_strategy.signals import (
    _select_zhongshu_for_departure_leg,
    signal_divergence_status,
)
from chan_strategy.sell_signals import signal_first_sell


@pytest.fixture
def divergence_status_fixture(bi_factory, czsc_factory):
    """Return a CZSC where legacy and departure_leg produce different status.

    Structure (7 confirmed BIs):

    - BI0: Up 90-110   (enter for first zhongshu A, power = 20)
    - BI1: Down 92-108
    - BI2: Up 94-106   -> zhongshu A (zd=94, zg=106, end_idx=2)
    - BI3: Down 107-115 (breaks A, low=107 >= zg=106)
    - BI4: Up 108-120
    - BI5: Down 110-118 -> zhongshu B (zd=110, zg=115, end_idx=6 after extension)
    - BI6: Up 112-114  (overlaps B so B extends to the last BI; not a departure
                        from B because high=114 <= zg=115)

    A third candidate C (BIs 4-6, zd=112, zg=114) also ends at the last BI,
    so it is the true ``zhongshu_list[-1]``.  Because no candidate has BIs
    after it, legacy mode reports "无".

    departure_leg mode searches backward and selects A (end_idx=2), the most
    recent candidate with BIs after it.  BI6 is above A's zg=106 and its
    power (2) is weaker than A's enter BI0 (power=20), so departure_leg
    reports "疑似".
    """
    base = datetime(2024, 1, 1)
    bis = [
        bi_factory(Direction.Up, 90, 110, base, base + timedelta(minutes=1)),
        bi_factory(Direction.Down, 92, 108, base + timedelta(minutes=1), base + timedelta(minutes=2)),
        bi_factory(Direction.Up, 94, 106, base + timedelta(minutes=2), base + timedelta(minutes=3)),
        bi_factory(Direction.Down, 107, 115, base + timedelta(minutes=3), base + timedelta(minutes=4)),
        bi_factory(Direction.Up, 108, 120, base + timedelta(minutes=4), base + timedelta(minutes=5)),
        bi_factory(Direction.Down, 110, 118, base + timedelta(minutes=5), base + timedelta(minutes=6)),
        bi_factory(Direction.Up, 112, 114, base + timedelta(minutes=6), base + timedelta(minutes=7)),
    ]
    return czsc_factory(bis)


def _status_value(c):
    return next(iter(signal_divergence_status(c).values()))


def test_default_divergence_status_zhongshu_mode_is_legacy():
    assert STRATEGY_CONFIG.get("divergence_status_zhongshu_mode") == "legacy"


def test_legacy_mode_returns_no_divergence(divergence_status_fixture):
    c = divergence_status_fixture
    STRATEGY_CONFIG["divergence_status_zhongshu_mode"] = "legacy"
    try:
        value = _status_value(c)
        assert value.startswith("无_")
    finally:
        STRATEGY_CONFIG["divergence_status_zhongshu_mode"] = "legacy"


def test_departure_leg_mode_returns_candidate_divergence(divergence_status_fixture):
    c = divergence_status_fixture
    STRATEGY_CONFIG["divergence_status_zhongshu_mode"] = "departure_leg"
    try:
        value = _status_value(c)
        assert value.startswith("疑似_")
    finally:
        STRATEGY_CONFIG["divergence_status_zhongshu_mode"] = "legacy"


def test_helper_selects_departure_leg_zhengshu(divergence_status_fixture):
    from chan_strategy.signals import _get_confirmed_bi_list
    from chan_strategy.zhongshu import build_zhongshu_from_bis

    c = divergence_status_fixture
    bi_list = _get_confirmed_bi_list(c)
    zhongshu_list = build_zhongshu_from_bis(bi_list)
    assert len(zhongshu_list) >= 2

    selected = _select_zhongshu_for_departure_leg(bi_list, zhongshu_list)
    # Should pick the earlier zhongshu that actually has BIs after it.
    assert selected["end_idx"] < len(bi_list) - 1
    assert bi_list[selected["end_idx"] + 1:]


def test_helper_falls_back_to_last_when_no_after_bis():
    """When no candidate has BIs after it, helper returns the last candidate."""
    fake_zs1 = {"end_idx": 4}
    fake_zs2 = {"end_idx": 4}
    # 5 BIs (indices 0-4); every candidate ends at the last index, so no after BIs.
    bi_list = [None] * 5
    assert _select_zhongshu_for_departure_leg(bi_list, [fake_zs1, fake_zs2]) is fake_zs2


def test_helper_matches_first_buy_and_first_sell_selection(divergence_status_fixture):
    """The extracted helper must produce the same zhongshu as the inline logic."""
    from chan_strategy.signals import _get_confirmed_bi_list
    from chan_strategy.zhongshu import build_zhongshu_from_bis

    c = divergence_status_fixture
    bi_list = _get_confirmed_bi_list(c)
    zhongshu_list = build_zhongshu_from_bis(bi_list)

    helper_zs = _select_zhongshu_for_departure_leg(bi_list, zhongshu_list)
    inline_buy_zs = next(
        (zs for zs in reversed(zhongshu_list) if bi_list[zs["end_idx"] + 1:]),
        zhongshu_list[-1],
    )
    inline_sell_zs = next(
        (zs for zs in reversed(zhongshu_list) if bi_list[zs["end_idx"] + 1:]),
        zhongshu_list[-1],
    )
    assert helper_zs["end_idx"] == inline_buy_zs["end_idx"]
    assert helper_zs["end_idx"] == inline_sell_zs["end_idx"]


def test_departure_leg_unblocks_first_buy_like_classification(divergence_status_fixture):
    """departure_leg mode makes divergence_status agree with first-buy/sell selection."""
    c = divergence_status_fixture

    STRATEGY_CONFIG["divergence_status_zhongshu_mode"] = "departure_leg"
    try:
        status_value = _status_value(c)
        sell_value = next(iter(signal_first_sell(c).values()))

        # In this fixture there is an upward departure from A, so first_sell
        # should detect a candidate/confirmed first sell and divergence_status
        # should report "疑似".
        assert status_value.startswith("疑似_")
        assert "一卖" in sell_value
        assert "非一卖" not in sell_value
    finally:
        STRATEGY_CONFIG["divergence_status_zhongshu_mode"] = "legacy"


def test_unknown_mode_acts_as_legacy(divergence_status_fixture):
    """An unrecognised mode value falls back to the legacy path."""
    c = divergence_status_fixture
    STRATEGY_CONFIG["divergence_status_zhongshu_mode"] = "not_a_real_mode"
    try:
        value = _status_value(c)
        assert value.startswith("无_")
    finally:
        STRATEGY_CONFIG["divergence_status_zhongshu_mode"] = "legacy"
