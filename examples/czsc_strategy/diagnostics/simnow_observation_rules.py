from __future__ import annotations

from typing import Any


REASON_CONSISTENCY_PROVENANCE_UNVERIFIED = "consistency_provenance_unverified"


def is_valid_observation(record: dict[str, Any]) -> bool:
    """Return True only for a day eligible for the 20-day SimNow promotion count."""
    return valid_observation_reason(record) is None


def valid_observation_reason(record: dict[str, Any]) -> str | None:
    """Return the first gate preventing a record from being a valid observation.

    Returns ``None`` when the record passes every gate.  The provenance gate
    requires ``consistency.verified`` to be ``True`` so that hand-edited or
    legacy-format ledger rows cannot silently count as valid observations
    merely by setting ``consistency.matched=True``.
    """
    subscription = record.get("subscription_coverage") or {}
    kline = record.get("kline_coverage") or {}
    consistency = record.get("consistency") or {}
    thresholds = record.get("thresholds") or {}
    safety = record.get("order_safety") or {}

    if record.get("status") != "pass":
        return "status_not_pass"
    if consistency.get("matched") is not True:
        return "consistency_not_matched"
    if consistency.get("verified") is not True:
        return REASON_CONSISTENCY_PROVENANCE_UNVERIFIED
    if thresholds.get("status") != "pass":
        return "thresholds_not_pass"
    if safety.get("status") != "pass":
        return "order_safety_not_pass"
    if subscription.get("missing_symbols"):
        return "subscription_missing_symbols"
    if kline.get("missing_symbols"):
        return "kline_missing_symbols"
    if kline.get("short_symbols"):
        return "kline_short_symbols"
    return None
