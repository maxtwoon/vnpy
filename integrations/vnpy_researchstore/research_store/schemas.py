"""Record schemas for immutable Parquet objects.

Schema version 1. Float measures are float64 and nullable: real NULLs are
preserved end to end and non-finite values are rejected at publish time.

Time contract (time-contract disposition, 2026-09-16): canonical interval
bounds (bar_start/bar_end, ts) are always real and NOT NULL. ``trading_date``
is nullable ONLY for minute-interval datasets whose source cannot honestly
attribute a trading day without calendar evidence, and then the row must
carry an explicit field_quality note. Daily datasets always carry a non-null
trading_date; daily identity/dedup is (instrument-or-series, trading_date),
enforced at publish. No field is ever derived from a natural date.

Tick identity (core fix03 F3): tick rows carry an explicit non-empty
``session_id`` and an importer-assigned ``seq`` (ingest sequence within the
session), both NOT NULL. Together with the instrument-or-series identity they
form the canonical tick event identity used for validation, dedup, conflict
detection, publication order, and reader ordering; ``ts`` is preserved at its
original precision but is not the identity. Schema compatibility: v1 is
unreleased (0.1.0.dev) and is redefined in place — no tick dataset written
against the earlier ts-only shape exists, and any such store would fail the
strict schema equality check at publish/read rather than be misread. The
core never invents or defaults a session id for historical rows.
"""

from __future__ import annotations

import math

import pyarrow as pa

SCHEMA_VERSION = 1

# Provenance columns carried by every record kind.
_PROVENANCE_FIELDS = [
    pa.field("asset_id", pa.string(), nullable=False),
    pa.field("batch_id", pa.string(), nullable=False),
    pa.field("transform_version", pa.string(), nullable=False),
]

BARS_SCHEMA_V1 = pa.schema(
    [
        pa.field("dataset_id", pa.string(), nullable=False),
        pa.field("instrument_id", pa.string(), nullable=True),
        pa.field("series_id", pa.string(), nullable=True),
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("exchange", pa.string(), nullable=True),
        pa.field("bar_start", pa.int64(), nullable=False),  # UTC epoch ns, inclusive
        pa.field("bar_end", pa.int64(), nullable=False),  # UTC epoch ns, exclusive
        # trading_date is nullable for minute-interval datasets whose source
        # cannot honestly attribute a trading day (no calendar evidence);
        # daily datasets must always carry it (enforced at publish).
        pa.field("trading_date", pa.date32(), nullable=True),
        pa.field("source_label", pa.string(), nullable=True),
        pa.field("open", pa.float64(), nullable=True),
        pa.field("high", pa.float64(), nullable=True),
        pa.field("low", pa.float64(), nullable=True),
        pa.field("close", pa.float64(), nullable=True),
        pa.field("volume", pa.float64(), nullable=True),
        pa.field("turnover", pa.float64(), nullable=True),
        pa.field("open_interest", pa.float64(), nullable=True),
        pa.field("completeness", pa.string(), nullable=False),
        pa.field("field_quality", pa.string(), nullable=True),  # JSON per-field notes
        pa.field("contract_id", pa.string(), nullable=True),  # continuous -> real mapping
        *_PROVENANCE_FIELDS,
        pa.field("extensions_json", pa.string(), nullable=True),  # nonstandard source columns
    ]
)

TICKS_SCHEMA_V1 = pa.schema(
    [
        pa.field("dataset_id", pa.string(), nullable=False),
        pa.field("instrument_id", pa.string(), nullable=True),
        pa.field("series_id", pa.string(), nullable=True),
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("exchange", pa.string(), nullable=True),
        # Canonical tick event identity: the recording/import session plus
        # the ingest sequence within it. Both required and never defaulted;
        # two distinct events at the same ts (seq 1, 2) both survive.
        pa.field("session_id", pa.string(), nullable=False),
        pa.field("seq", pa.int64(), nullable=False),  # ingest seq within session
        pa.field("ts", pa.int64(), nullable=False),  # UTC epoch ns of the event
        # Same time contract as bars: unknown trading day stays NULL with an
        # explicit field_quality note; never derived from a natural date.
        pa.field("trading_date", pa.date32(), nullable=True),
        pa.field("source_label", pa.string(), nullable=True),
        pa.field("last_price", pa.float64(), nullable=True),
        pa.field("last_volume", pa.float64(), nullable=True),
        pa.field("turnover", pa.float64(), nullable=True),
        pa.field("bid_price1", pa.float64(), nullable=True),
        pa.field("ask_price1", pa.float64(), nullable=True),
        pa.field("bid_volume1", pa.float64(), nullable=True),
        pa.field("ask_volume1", pa.float64(), nullable=True),
        pa.field("completeness", pa.string(), nullable=False),
        pa.field("field_quality", pa.string(), nullable=True),
        pa.field("contract_id", pa.string(), nullable=True),
        *_PROVENANCE_FIELDS,
        pa.field("extensions_json", pa.string(), nullable=True),
    ]
)

MEASURE_FIELDS: dict[str, tuple[str, ...]] = {
    "bars": ("open", "high", "low", "close", "volume", "turnover", "open_interest"),
    "ticks": (
        "last_price",
        "last_volume",
        "turnover",
        "bid_price1",
        "ask_price1",
        "bid_volume1",
        "ask_volume1",
    ),
}

KEY_COLUMNS: dict[str, tuple[str, ...]] = {
    # Identity column is instrument_id OR series_id; validated jointly.
    # Ticks additionally disambiguate by (session_id, seq) — see F3 above.
    "bars": ("bar_start",),
    "ticks": ("session_id", "seq"),
}

SCHEMAS: dict[str, pa.Schema] = {
    "bars": BARS_SCHEMA_V1,
    "ticks": TICKS_SCHEMA_V1,
}


def schema_for(record_kind: str) -> pa.Schema:
    try:
        return SCHEMAS[record_kind]
    except KeyError as exc:
        raise ValueError(f"no v1 schema for record kind {record_kind!r}") from exc


def identity_of(row: dict[str, object]) -> str:
    """Instrument or series identity; exactly one must be present."""

    instrument = row.get("instrument_id")
    series = row.get("series_id")
    if (instrument is None) == (series is None):
        raise ValueError(
            "exactly one of instrument_id/series_id must be non-null "
            f"(got instrument_id={instrument!r}, series_id={series!r})"
        )
    return str(instrument if instrument is not None else series)


def contains_nonfinite(batch: pa.RecordBatch, record_kind: str) -> list[str]:
    """Names of measure columns holding inf/nan; publish rejects non-empty."""

    bad: list[str] = []
    for name in MEASURE_FIELDS[record_kind]:
        col = batch.column(name)
        values = col.to_pylist()
        if any(v is not None and not math.isfinite(v) for v in values):
            bad.append(name)
    return bad
