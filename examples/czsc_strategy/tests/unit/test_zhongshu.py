from datetime import datetime, timedelta

import pytest
from czsc import Direction

from chan_strategy.zhongshu import _make_zhongshu, build_zhongshu_from_bis


def _bis(bi_factory, ranges):
    base = datetime(2024, 1, 1)
    out = []
    for i, (low, high) in enumerate(ranges):
        direction = Direction.Up if i % 2 == 0 else Direction.Down
        out.append(bi_factory(direction, low, high, base, base + timedelta(minutes=i)))
    return out


def test_zhongshu_empty_and_invalid_mode(bi_factory):
    assert build_zhongshu_from_bis([]) == []
    assert build_zhongshu_from_bis(_bis(bi_factory, [(1, 2), (2, 3)])) == []
    assert _make_zhongshu(_bis(bi_factory, [(1, 2), (2, 3)]), 0, 9) is None
    with pytest.raises(ValueError):
        build_zhongshu_from_bis(_bis(bi_factory, [(1, 5), (2, 6), (3, 7)]), mode="bad")


def test_recent_mode_returns_nearest_overlapping_candidate(bi_factory):
    bis = _bis(
        bi_factory,
        [
            (90, 120),
            (94, 115),
            (96, 112),
            (80, 100),
            (88, 104),
            (250, 300),
            (260, 310),
            (270, 320),
            (280, 330),
        ],
    )

    centers = build_zhongshu_from_bis(bis, mode="recent", lookback=30)

    assert centers
    assert centers[-1]["start_idx"] == 6
    assert centers[-1]["end_idx"] == 8
    assert centers[-1]["zd"] == 280
    assert centers[-1]["zg"] == 310


def test_recent_mode_respects_lookback_and_none_scans_all(bi_factory):
    bis = _bis(
        bi_factory,
        [
            (90, 120),
            (94, 115),
            (96, 112),
            (80, 100),
            (88, 104),
            (250, 300),
            (260, 310),
            (270, 320),
        ],
    )

    assert build_zhongshu_from_bis(bis, mode="recent", lookback=3)[-1]["start_idx"] == 5
    assert build_zhongshu_from_bis(bis, mode="recent", lookback=None)[0]["start_idx"] == 0


def test_max_bis_caps_extension_in_recent_and_segment_modes(bi_factory):
    bis = _bis(
        bi_factory,
        [
            (90, 120),
            (92, 118),
            (94, 116),
            (93, 117),
            (91, 119),
            (95, 115),
            (96, 114),
        ],
    )

    recent = build_zhongshu_from_bis(bis, mode="recent", max_bis=4, lookback=None)
    segment = build_zhongshu_from_bis(bis, mode="segment", max_bis=4)

    assert max(z["n_bis"] for z in recent) == 4
    assert segment[0]["n_bis"] == 4


def test_segment_mode_returns_independent_centers(bi_factory):
    bis = _bis(
        bi_factory,
        [
            (90, 120),
            (94, 115),
            (96, 112),
            (10, 20),
            (12, 22),
            (14, 24),
        ],
    )

    centers = build_zhongshu_from_bis(bis, mode="segment", lookback=None)

    assert [(z["start_idx"], z["end_idx"]) for z in centers] == [(0, 2), (3, 5)]


def test_segment_mode_skips_non_overlapping_starts(bi_factory):
    bis = _bis(
        bi_factory,
        [
            (1, 2),
            (3, 4),
            (5, 6),
            (10, 20),
            (12, 22),
            (14, 24),
        ],
    )

    centers = build_zhongshu_from_bis(bis, mode="segment")

    assert [(z["start_idx"], z["end_idx"]) for z in centers] == [(3, 5)]
