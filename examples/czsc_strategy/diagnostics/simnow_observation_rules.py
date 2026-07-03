from __future__ import annotations

from typing import Any


def is_valid_observation(record: dict[str, Any]) -> bool:
    """Return True only for a day eligible for the 20-day SimNow promotion count."""
    subscription = record.get("subscription_coverage") or {}
    kline = record.get("kline_coverage") or {}
    return (
        record.get("status") == "pass"
        and record.get("consistency", {}).get("matched") is True
        and record.get("thresholds", {}).get("status") == "pass"
        and record.get("order_safety", {}).get("status") == "pass"
        and not subscription.get("missing_symbols")
        and not kline.get("missing_symbols")
        and not kline.get("short_symbols")
    )
