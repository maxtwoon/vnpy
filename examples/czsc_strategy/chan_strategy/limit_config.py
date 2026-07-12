"""Shared daily price-limit configuration and helpers.

This module is the single source of truth for the exchange-published
steady-state daily price-limit percentages used by both the A50 diagnostic
and the A51 per-trade limit/halt tagging logic.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


# Exchange-published steady-state daily price-limit percentages.
# The exchanges reserve the right to widen limits for specific contracts,
# newly listed contracts, or after limit-hit days; consumers of this config
# document that simplification explicitly.
SYMBOL_LIMIT_CONFIG: dict[str, dict[str, Any]] = {
    "AP888": {
        "limit_pct": 0.05,
        "source": (
            "CZCE 鲜苹果期货合约：每日涨跌停板幅度为前一交易日结算价的±5% "
            "(郑州商品交易所〔2017〕17号公告，《郑州商品交易所鲜苹果期货业务细则》)"
        ),
    },
    "RB888": {
        "limit_pct": 0.03,
        "source": (
            "SHFE 螺纹钢期货合约：涨跌停板幅度为上一交易日结算价±3% "
            "(shfe.com.cn/products/futures/metal/ferrousandpreciousmetal/rb_f/, 2024-09-24修订)"
        ),
    },
    "SC888": {
        "limit_pct": 0.04,
        "source": (
            "INE 原油期货标准合约：Daily Price Limits ±4% from the settlement price "
            "of the previous trading day (ine.cn/eng/market/futures/energy/sc/contract/)"
        ),
    },
    "A888": {
        "limit_pct": 0.04,
        "source": (
            "DCE 黄大豆1号期货合约：涨跌停板幅度为上一交易日结算价的±4% "
            "(大连商品交易所黄大豆1号期货合约文本 / 《大连商品交易所风险管理办法》)"
        ),
    },
    "ZN888": {
        "limit_pct": 0.04,
        "source": (
            "SHFE 锌期货合约：涨跌停板幅度为上一交易日结算价±4% "
            "(shfe.com.cn/publicnotice/notice/202408/W020240823636323134983.docx 修订稿)"
        ),
    },
}


def _bar_date(bar: Any) -> date:
    """Return the calendar date of a bar (handles datetime and pandas Timestamp)."""
    dt = bar.dt
    if isinstance(dt, datetime):
        return dt.date()
    return pd.Timestamp(dt).date()


def _daily_prev_close_map(bars: list[Any]) -> dict[date, tuple[float | None, date | None]]:
    """Map each trading date to the previous trading day's last close.

    Returns ``{date: (prev_close, prev_date)}``.  The first date in the
    loaded window has no previous close and is therefore mapped to
    ``(None, None)``.
    """
    daily_close: dict[date, float] = {}
    for bar in bars:
        d = _bar_date(bar)
        daily_close[d] = float(bar.close)

    sorted_dates = sorted(daily_close)
    prev_map: dict[date, tuple[float | None, date | None]] = {}
    for i, d in enumerate(sorted_dates):
        if i == 0:
            prev_map[d] = (None, None)
        else:
            prev_date = sorted_dates[i - 1]
            prev_map[d] = (daily_close[prev_date], prev_date)
    return prev_map


def _limit_band(prev_close: float, limit_pct: float) -> tuple[float, float]:
    """Upper and lower price-limit bounds from the previous close."""
    return prev_close * (1.0 + limit_pct), prev_close * (1.0 - limit_pct)


def _bar_at_limit(
    bar: Any,
    prev_close: float | None,
    limit_pct: float,
) -> tuple[bool, float | None, float | None]:
    """Return (at_limit, upper, lower) for a bar.

    A bar is considered at or beyond its daily limit if any part of the
    bar's range (high/low) touches or breaches the computed band.
    """
    if prev_close is None or prev_close <= 0:
        return False, None, None
    upper, lower = _limit_band(prev_close, limit_pct)
    at_limit = bool(bar.high >= upper - 1e-9 or bar.low <= lower + 1e-9)
    return at_limit, upper, lower
