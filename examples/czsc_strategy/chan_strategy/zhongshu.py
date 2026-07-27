"""Shared Zhongshu construction helpers.

All strategy signals and analysis tools should use this module so the displayed
current center and the center used by buy/sell point signals stay aligned.

Terminology source note: ``skill_build/reference/缠论术语表.md`` is the
workspace mapping between Chan-theory terms and code signal fields. It is a
non-authoritative glossary for this repository, not a claim that these helpers
match a single canonical Chan-theory definition.

Deviation from textbook Chan-theory zhongshu (non-authoritative implementation
note, added 2026-07-26 audit; not a claim about what "correct" Chan theory
requires): standard Chan-theory zhongshu construction lets a center extend
indefinitely until broken by a qualifying three-type buy/sell point structure.
This module instead caps every center at ``max_bis`` (default 9) BIs and, in
``mode="recent"``, only scans the most recent ``lookback`` (default 30) BIs.
Both are deliberate engineering bounds (see ``max_bis`` docstring above) to
keep centers from silently swallowing later structure and to bound compute —
they are not sourced from any Chan-theory reference and have not been diffed
against the third-party ``czsc`` library's own ``ZS`` object. Downstream code
should not assume this module's centers are interchangeable with either the
textbook definition or ``czsc.ZS``.

``mode`` split between callers (see ``sell_signals.py``): risk/structural-
invalidation checks use ``mode="segment"`` (old from-the-beginning, non-
overlapping segmentation — one canonical center per bi range) while entry
signals default to ``mode="recent"`` (overlapping local-window centers,
biased toward the latest structure). This means the center a position was
opened against and the center later used to judge "structural invalidation"
for that same position are not guaranteed to be the same object. This is an
existing, intentional trade-off (recent-mode entries want the freshest local
center; segment-mode risk checks want a stable, non-overlapping reference)
rather than an oversight, but it is not documented anywhere else — see
AUDIT_REPORT_2026-07-03.md for the original finding.
"""
from __future__ import annotations


def _make_zhongshu(bis: list, start_idx: int, max_bis: int) -> dict | None:
    """Build one capped zhongshu candidate from start_idx, if the first 3 BIs overlap."""
    window = bis[start_idx:start_idx + 3]
    if len(window) < 3:
        return None

    zd = max(float(b.low) for b in window)
    zg = min(float(b.high) for b in window)
    if zd >= zg:
        return None

    dd = min(float(b.low) for b in window)
    gg = max(float(b.high) for b in window)
    end_idx = start_idx + 2
    for j in range(start_idx + 3, min(len(bis), start_idx + max_bis)):
        bj = bis[j]
        if float(bj.low) < zg and float(bj.high) > zd:
            dd = min(dd, float(bj.low))
            gg = max(gg, float(bj.high))
            end_idx = j
        else:
            break

    return {
        "zd": zd,
        "zg": zg,
        "dd": dd,
        "gg": gg,
        "start_idx": start_idx,
        "end_idx": end_idx,
        "n_bis": end_idx - start_idx + 1,
        "bis": bis[start_idx:end_idx + 1],
    }


def build_zhongshu_from_bis(
    bi_list: list,
    max_bis: int = 9,
    lookback: int | None = 30,
    mode: str = "recent",
) -> list:
    """
    Build zhongshu candidates from confirmed BIs.

    Parameters
    ----------
    bi_list:
        Confirmed BI list.
    max_bis:
        Maximum BIs allowed in one center. This prevents old centers from
        expanding indefinitely and swallowing later market structure.
    lookback:
        In ``recent`` mode, only scan the latest N BIs. Use ``None`` to scan all.
    mode:
        ``recent`` scans overlapping windows and returns the nearest local
        centers sorted by end/start index. ``segment`` keeps the old
        from-the-beginning segmentation semantics for diagnostics.
    """
    if len(bi_list) < 3:
        return []

    max_bis = max(3, int(max_bis or 9))
    if mode not in {"recent", "segment"}:
        raise ValueError(f"unsupported zhongshu mode: {mode}")

    if mode == "segment":
        out = []
        i = 0
        while i < len(bi_list) - 2:
            z = _make_zhongshu(bi_list, i, max_bis)
            if z:
                out.append(z)
                i = z["end_idx"] + 1
            else:
                i += 1
        return out

    start = 0 if lookback is None else max(0, len(bi_list) - max(3, int(lookback)))
    out = [
        z for i in range(start, len(bi_list) - 2)
        if (z := _make_zhongshu(bi_list, i, max_bis)) is not None
    ]
    out.sort(key=lambda z: (z["end_idx"], z["start_idx"]))
    return out
