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
        "temporary_widening_windows": [
            {
                "start_date": date(2026, 5, 6),
                "end_date": date(2026, 5, 6),
                "limit_pct": 0.08,
                "source": (
                    "claude-code 2026-07-13 web search during A50 review "
                    "(see HANDOFF commit 4b228834); not independently verified against a "
                    "primary exchange notice — flagged for human confirmation"
                ),
            },
        ],
    },
    "RB888": {
        "limit_pct": 0.03,
        "source": (
            "SHFE 螺纹钢期货合约：涨跌停板幅度为上一交易日结算价±3% "
            "(shfe.com.cn/products/futures/metal/ferrousandpreciousmetal/rb_f/, 2024-09-24修订)"
        ),
        "temporary_widening_windows": [
            {
                "start_date": date(2026, 5, 19),
                "end_date": date(2026, 5, 19),
                "limit_pct": 0.05,
                "source": (
                    "claude-code 2026-07-13 web search during A50 review "
                    "(see HANDOFF commit 4b228834); not independently verified against a "
                    "primary exchange notice — flagged for human confirmation"
                ),
            },
        ],
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


def _trading_day_for_limit(dt: datetime, night_session_start_hour: int = 20) -> date:
    """Map a bar timestamp to its exchange trading day for limit-band purposes.

    Reuses ``portfolio_engine._trading_day`` so limit-config bucketing stays
    aligned with the strategy's own trading-calendar semantics.  Bars in the
    evening session (hour >= ``night_session_start_hour``) belong to the next
    trading day.
    """
    # Local import breaks the ``backtest_engine <-> portfolio_engine`` import
    # cycle: ``limit_config`` is imported at module level by ``backtest_engine``,
    # while ``portfolio_engine`` imports ``backtest_engine``.
    from chan_strategy.portfolio_engine import _trading_day

    return _trading_day(dt, daily_agg="trading_calendar", night_session_start_hour=night_session_start_hour)


def _daily_prev_close_map(
    bars: list[Any],
    night_session_start_hour: int | None = None,
) -> dict[date, tuple[float | None, date | None]]:
    """Map each trading date to the previous trading day's last close.

    Returns ``{trading_day: (prev_close, prev_trading_day)}``.  The first
    trading day in the loaded window has no previous close and is therefore
    mapped to ``(None, None)``.

    Bucketing uses exchange trading days so that a night-session bar
    (e.g. 21:00 on calendar day D) is not treated as part of day D's "previous
    close" computation for day D+1.
    """
    from chan_strategy.config import STRATEGY_CONFIG

    if night_session_start_hour is None:
        night_session_start_hour = int(STRATEGY_CONFIG.get("night_session_start_hour", 20))

    daily_close: dict[date, float] = {}
    for bar in bars:
        trading_day = _trading_day_for_limit(bar.dt, night_session_start_hour)
        daily_close[trading_day] = float(bar.close)

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


def _limit_pct_for_date(symbol: str, bar_date: date) -> float | None:
    """Return the effective limit percentage for ``symbol`` on ``bar_date``.

    Falls back to the steady-state percentage when no registered temporary
    widening window covers the date.
    """
    symbol = symbol.upper()
    config = SYMBOL_LIMIT_CONFIG.get(symbol)
    if config is None:
        return None

    for window in config.get("temporary_widening_windows", []):
        start = window["start_date"]
        end = window["end_date"]
        if start <= bar_date <= end:
            return float(window["limit_pct"])

    return float(config["limit_pct"])


def _bar_at_limit(
    bar: Any,
    prev_close: float | None,
    limit_pct: float,
) -> tuple[bool, bool, float | None, float | None]:
    """Return (touched_upper, touched_lower, upper, lower) for a bar.

    A bar is considered to have touched or breached its daily upper limit if
    any part of the bar's range (high/low) reaches or exceeds the computed
    upper bound; similarly for the lower limit.
    """
    if prev_close is None or prev_close <= 0:
        return False, False, None, None
    upper, lower = _limit_band(prev_close, limit_pct)
    touched_upper = bool(bar.high >= upper - 1e-9)
    touched_lower = bool(bar.low <= lower + 1e-9)
    return touched_upper, touched_lower, upper, lower
