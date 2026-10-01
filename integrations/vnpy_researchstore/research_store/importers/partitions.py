"""Canonical partition mapping owned by the importers.

The core treats partition strings as opaque; the deterministic mapping is the
importer's responsibility (INTERFACES.md section 5, plan "Partitions"):

* daily datasets: ``"{year}"`` (year of the source trading_date)
* equity/ETF minute: ``"{exchange}/{year-month}/{bucket16}"`` — 16 stable
  instrument buckets so one partition stays a manageable size
* futures minute: ``"{product}/{year-month}"``

SSQuant ``table x month`` is a resumable INPUT work unit, never a canonical
partition: rows from a table/month job map into ``{product}/{year-month}``
partitions exactly like other futures minute data.

Year-month labels are taken from the bar's Shanghai-local time (the source
labels are Asia/Shanghai wall clock), never from the UTC calendar day.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
BUCKET_COUNT = 16

_DIGITS_TAIL_RE = re.compile(r"\d+$")


def bucket16(identity: str) -> str:
    """Stable instrument bucket name (``bucket-00`` .. ``bucket-15``)."""
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"bucket-{int(digest, 16) % BUCKET_COUNT:02d}"


def product_of(instrument: str) -> str:
    """Futures product code: the instrument symbol minus its trailing digits."""
    product = _DIGITS_TAIL_RE.sub("", instrument.strip().upper())
    if not product:
        raise ValueError(f"cannot derive product from instrument {instrument!r}")
    return product


def _year_month_from_ns(bar_end_ns: int) -> str:
    """Shanghai-local ``YYYY-MM`` of the bar's END bound (the source label)."""
    local = datetime.fromtimestamp(bar_end_ns / 1_000_000_000, tz=timezone.utc)
    local = local.astimezone(SHANGHAI_TZ)
    return f"{local.year:04d}-{local.month:02d}"


def partition_for_row(
    row: dict[str, Any],
    interval: str,
    asset_class: str,
) -> str:
    """Map one canonical row to its canonical partition string.

    ``row`` is the importer canonical shape (``instrument``, ``exchange``,
    ``trading_date``, ``bar_end_ns``, ``extensions``). Daily rows key on the
    trading date's year; minute rows on the Shanghai-local year-month of the
    bar's end label. Rows without real bounds cannot be partitioned and raise
    (they are candidates for the inspection path, not publishable bars).
    """
    instrument = str(row["instrument"])
    if interval == "1d":
        trading_date = row.get("trading_date")
        if trading_date is None:
            raise ValueError(
                f"daily row {instrument} @ {row.get('source_label')} has no "
                "trading_date; cannot derive its canonical year partition"
            )
        return str(trading_date)[:4]
    end_ns = row.get("bar_end_ns")
    if end_ns is None:
        raise ValueError(
            f"minute row {instrument} @ {row.get('source_label')} has unknown "
            "bar bounds; route it to the candidate/inspection path instead"
        )
    year_month = _year_month_from_ns(int(end_ns))
    if asset_class in ("equity", "etf", "index"):
        exchange = row.get("exchange") or "unknown"
        return f"{exchange}/{year_month}/{bucket16(instrument)}"
    if asset_class == "futures":
        underlying = (row.get("extensions") or {}).get("underlying_symbol")
        product = product_of(str(underlying) if underlying else instrument)
        return f"{product}/{year_month}"
    return f"{year_month}/{bucket16(instrument)}"


__all__ = [
    "BUCKET_COUNT",
    "SHANGHAI_TZ",
    "bucket16",
    "partition_for_row",
    "product_of",
]
