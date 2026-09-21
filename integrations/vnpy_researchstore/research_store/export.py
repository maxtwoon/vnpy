"""Snapshot export to external targets.

Rules (execution contract):

* The target directory must be unmanaged-empty, or already bound to THIS
  store + snapshot + format via ``export-manifest.json``. Anything else is
  refused — exports never overwrite raw inputs or someone else's directory.
* ``parquet`` exports are faithful copies streamed from the snapshot reader
  (one file per dataset/partition, Zstandard) with full write/readback
  verification.
* ``sqlite`` (vnpy_sqlite schema) and ``alpha`` (AlphaLab layout) exports are
  REBUILDABLE COMPATIBILITY COPIES, never new truth: rows with NULL OHLCV are
  skipped and recorded, NULL turnover/open_interest become explicit 0.0
  placeholders recorded in the receipt, unmapped exchange labels are skipped
  and recorded. Missing-field rules live in the receipt, not in silent data.
* Raw source inputs are never touched.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .models import StoreError
from .snapshots import load_snapshot_manifest, open_snapshot
from .store import Store

EXPORT_BINDING_NAME = "export-manifest.json"

# Source exchange label -> vnpy exchange label for the sqlite compatibility
# copy. Unmapped labels are skipped and recorded, never guessed.
_EXCHANGE_MAP = {"XSHG": "SSE", "XSHE": "SZSE"}

_ALPHA_INTERVALS = {"1m": "minute", "1d": "daily"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_target(target: Path, store: Store, snapshot_id: str, format: str) -> None:
    binding_path = target / EXPORT_BINDING_NAME
    if target.exists() and any(target.iterdir()):
        if not binding_path.is_file():
            raise StoreError(
                f"export target {target} is not empty and carries no export "
                "binding; refusing to write an unmanaged directory"
            )
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        if (
            binding.get("store_id") != store.store_id
            or binding.get("snapshot_id") != snapshot_id
            or binding.get("format") != format
        ):
            raise StoreError(
                f"export target {target} is bound to a different "
                "store/snapshot/format; choose an empty directory"
            )
    target.mkdir(parents=True, exist_ok=True)


def _ns_to_shanghai_naive(ns: int) -> str:
    """Asia/Shanghai wall clock, naive (vnpy_sqlite convention)."""
    from zoneinfo import ZoneInfo

    utc = datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc)
    return (
        utc.astimezone(ZoneInfo("Asia/Shanghai"))
        .replace(tzinfo=None)
        .isoformat(sep=" ", timespec="microseconds")
    )


def export_snapshot(
    store: Store,
    snapshot_id: str,
    target: str | Path,
    format: str = "parquet",
) -> dict[str, Any]:
    """Export one immutable snapshot; returns the machine-readable receipt."""
    if format not in ("parquet", "sqlite", "alpha"):
        raise StoreError(f"unsupported export format {format!r}")
    manifest = load_snapshot_manifest(store, snapshot_id)
    target_path = Path(target).resolve()
    _check_target(target_path, store, snapshot_id, format)

    receipt: dict[str, Any] = {
        "store_id": store.store_id,
        "store_root": str(store.root),
        "snapshot_id": snapshot_id,
        "format": format,
        "exported_at": _utcnow(),
        "datasets": {},
        "compatibility_copy": format != "parquet",
        "compatibility_note": (
            ""
            if format == "parquet"
            else "rebuildable compatibility copy; the store snapshot remains "
            "the only truth — NULL placeholders and skips are recorded per "
            "dataset below"
        ),
    }
    reader = open_snapshot(store, snapshot_id)
    try:
        dataset_ids = sorted({s["dataset_id"] for s in manifest["selections"]})
        for dataset_id in dataset_ids:
            semantic = {}
            for selection in manifest["selections"]:
                if selection["dataset_id"] == dataset_id:
                    semantic = selection.get("semantic", {})
                    break
            # Default qualified export: intersecting unallowed default-
            # qualified exclusions raise CoverageGapError (same contract as
            # the reader); allowed exclusions are filtered out of the export
            # and recorded in the receipt per dataset.
            captured_exclusions = [
                e
                for e in manifest.get("default_qualified_exclusions", [])
                if e.get("dataset_id") == dataset_id
            ]
            allowed_pairs = {
                (g["start_ns"], g["end_ns"])
                for g in manifest.get("allowed_gaps", [])
                if g["dataset_id"] == dataset_id
            }
            excluded_allowed = [
                e
                for e in captured_exclusions
                if (e["start_ns"], e["end_ns"]) in allowed_pairs
            ]
            batches = list(
                reader.bars(
                    dataset_id, required_fields=(), allow_missing_auxiliary=True
                )
            )
            rows = [r for batch in batches for r in batch.to_pylist()]
            if format == "parquet":
                receipt["datasets"][dataset_id] = _export_parquet(
                    target_path, dataset_id, manifest, batches
                )
            elif format == "sqlite":
                receipt["datasets"][dataset_id] = _export_sqlite(
                    target_path, dataset_id, semantic, rows
                )
            else:
                receipt["datasets"][dataset_id] = _export_alpha(
                    target_path, dataset_id, semantic, rows
                )
            if captured_exclusions:
                receipt["datasets"][dataset_id][
                    "default_qualified_exclusions"
                ] = len(captured_exclusions)
                receipt["datasets"][dataset_id][
                    "default_qualified_excluded_rows_omitted"
                ] = len(excluded_allowed)
                receipt["datasets"][dataset_id][
                    "default_qualified_note"
                ] = (
                    "snapshot carries default-qualified exclusions "
                    "(repaired/disputed keys); rows covered by an explicit "
                    "allow_known_gaps entry are omitted from this export; "
                    "unallowed exclusions refuse the export with "
                    "CoverageGapError"
                )
    finally:
        reader.close()

    binding = {
        "store_id": store.store_id,
        "snapshot_id": snapshot_id,
        "format": format,
        "exported_at": receipt["exported_at"],
    }
    (target_path / EXPORT_BINDING_NAME).write_text(
        json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    receipts_dir = target_path / "receipts"
    receipts_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt_path = receipts_dir / f"export-{snapshot_id}-{stamp}.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    receipt["receipt_path"] = str(receipt_path)
    return receipt


def _export_parquet(
    target: Path, dataset_id: str, manifest: dict, batches: list[pa.RecordBatch]
) -> dict[str, Any]:
    """Faithful per-dataset copy with full readback verification.

    The reader returns one globally key-sorted stream per dataset (partitions
    interleave), so the faithful unit is one file per dataset; the partition
    structure stays recorded in the snapshot manifest itself.
    """
    out_dir = target / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    if batches:
        table = pa.Table.from_batches(batches)
    else:
        table = None
    out_path = out_dir / f"{dataset_id}.parquet"
    if table is None:
        # Empty stream: no rows legitimately selected. Write nothing; record it.
        return {
            "files": [],
            "rows": 0,
            "readback": "empty_selection_no_rows",
        }
    pq.write_table(table, str(out_path), compression="zstd")
    readback = pq.read_table(str(out_path))
    if not readback.equals(table):
        raise StoreError(f"export readback mismatch for {dataset_id} at {out_path}")
    partitions = sorted(
        {str(s["partition"]) for s in manifest["selections"] if s["dataset_id"] == dataset_id}
    )
    return {
        "files": [str(out_path)],
        "rows": table.num_rows,
        "partitions": partitions,
        "readback": "verified",
    }


def _export_sqlite(
    target: Path, dataset_id: str, semantic: dict, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """vnpy_sqlite-schema compatibility copy with explicit missing-field rules."""
    interval = str(semantic.get("interval", ""))
    path = target / f"{dataset_id}.db"
    skipped_null_price: list[dict[str, Any]] = []
    skipped_exchange: list[str] = []
    turnover_placeholders = 0
    oi_placeholders = 0
    written: list[tuple[Any, ...]] = []
    for row in rows:
        identity = row.get("instrument_id") or row.get("series_id")
        open_ = row.get("open")
        high = row.get("high")
        low = row.get("low")
        close = row.get("close")
        volume = row.get("volume")
        if (
            open_ is None
            or high is None
            or low is None
            or close is None
            or volume is None
        ):
            skipped_null_price.append(
                {"instrument": identity, "bar_start": row.get("bar_start")}
            )
            continue
        exchange_label = row.get("exchange")
        exchange = _EXCHANGE_MAP.get(str(exchange_label)) if exchange_label else None
        if exchange is None:
            skipped_exchange.append(str(identity))
            continue
        if row.get("turnover") is None:
            turnover_placeholders += 1
        if row.get("open_interest") is None:
            oi_placeholders += 1
        written.append(
            (
                str(identity),
                exchange,
                _ns_to_shanghai_naive(int(row["bar_start"])),
                interval,
                float(volume),
                float(row["turnover"]) if row.get("turnover") is not None else 0.0,
                (
                    float(row["open_interest"])
                    if row.get("open_interest") is not None
                    else 0.0
                ),
                float(open_),
                float(high),
                float(low),
                float(close),
            )
        )
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS dbbardata ("
            "id INTEGER PRIMARY KEY, symbol VARCHAR(255) NOT NULL,"
            " exchange VARCHAR(255) NOT NULL, datetime DATETIME NOT NULL,"
            " interval VARCHAR(255) NOT NULL, volume REAL NOT NULL,"
            " turnover REAL NOT NULL, open_interest REAL NOT NULL,"
            " open_price REAL NOT NULL, high_price REAL NOT NULL,"
            " low_price REAL NOT NULL, close_price REAL NOT NULL,"
            " UNIQUE (symbol, exchange, interval, datetime))"
        )
        con.executemany(
            "INSERT OR REPLACE INTO dbbardata (symbol, exchange, datetime,"
            " interval, volume, turnover, open_interest, open_price,"
            " high_price, low_price, close_price)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            written,
        )
        readback = list(
            con.execute(
                "SELECT symbol, exchange, datetime, interval, volume, turnover,"
                " open_interest, open_price, high_price, low_price, close_price"
                " FROM dbbardata ORDER BY symbol, datetime"
            )
        )
    if readback != sorted(written, key=lambda r: (r[0], r[2])):
        raise StoreError(f"sqlite export readback mismatch at {path}")
    return {
        "path": str(path),
        "rows_written": len(written),
        "readback": "verified",
        "skipped_null_required": skipped_null_price,
        "skipped_unmapped_exchange": skipped_exchange,
        "turnover_zero_placeholders": turnover_placeholders,
        "open_interest_zero_placeholders": oi_placeholders,
        "missing_field_rules": (
            "rows with NULL OHLCV skipped and listed; NULL turnover/"
            "open_interest written as explicit 0.0 placeholders (recorded "
            "counts), matching vnpy_sqlite NOT NULL columns; placeholders are "
            "compatibility values, not measurements"
        ),
    }


def _export_alpha(
    target: Path, dataset_id: str, semantic: dict, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """AlphaLab-layout compatibility copy (daily/minute parquet per instrument)."""
    interval = str(semantic.get("interval", ""))
    folder_name = _ALPHA_INTERVALS.get(interval)
    if folder_name is None:
        raise StoreError(
            f"AlphaLab export supports 1m/1d datasets only; dataset {dataset_id} "
            f"is {interval!r}"
        )
    out_dir = target / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    by_instrument: dict[str, list[dict[str, Any]]] = {}
    skipped: list[dict[str, Any]] = []
    for row in rows:
        identity = str(row.get("instrument_id") or row.get("series_id"))
        if row.get("close") is None:
            skipped.append({"instrument": identity, "bar_start": row.get("bar_start")})
            continue
        by_instrument.setdefault(identity, []).append(row)
    files: list[str] = []
    total = 0
    for identity, instrument_rows in sorted(by_instrument.items()):
        frame_rows = [
            {
                "datetime": datetime.fromtimestamp(
                    int(r["bar_start"]) / 1_000_000_000, tz=timezone.utc
                ),
                "open": r.get("open"),
                "high": r.get("high"),
                "low": r.get("low"),
                "close": r.get("close"),
                "volume": r.get("volume"),
                "turnover": r.get("turnover"),
                "open_interest": r.get("open_interest"),
            }
            for r in instrument_rows
        ]
        table = pa.Table.from_pylist(frame_rows)
        out_path = out_dir / f"{identity}.parquet"
        pq.write_table(table, str(out_path), compression="zstd")
        readback = pq.read_table(str(out_path))
        if not readback.equals(table):
            raise StoreError(f"alpha export readback mismatch at {out_path}")
        files.append(str(out_path))
        total += table.num_rows
    return {
        "folder": folder_name,
        "files": files,
        "rows_written": total,
        "readback": "verified",
        "skipped_null_close": skipped,
        "missing_field_rules": (
            "rows with NULL close skipped and listed; other NULLs are written "
            "as real NULLs (parquet is nullable) — no zero placeholders"
        ),
    }


__all__ = ["EXPORT_BINDING_NAME", "export_snapshot"]
