"""Save checked history into an explicitly selected research directory."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from collections.abc import Iterator
from uuid import uuid4
from zoneinfo import ZoneInfo


MANIFEST_NAME = "datasource-manifest.json"
CHINA_TZ = ZoneInfo("Asia/Shanghai")
UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
PRICE_FIELDS = ("open_price", "high_price", "low_price", "close_price")
VALUE_FIELDS = (*PRICE_FIELDS, "volume", "turnover", "open_interest")
STORE_MEASURE_FIELDS = ("open", "high", "low", "close", "volume", "turnover", "open_interest")
STORE_INTERVALS = {"d": "1d", "1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h"}
STORE_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
STORE_ASSET_CLASSES = {
    "stock": "equity", "etf": "etf", "index": "index", "futures": "futures",
    "option": "option", "convertible": "convertible",
}
STORE_ADAPTER = "vnpy_datasource/0.1"


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(_json_text(value) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _directory_lock(directory: Path) -> Iterator[None]:
    lock = directory / ".datasource-write.lock"
    try:
        with lock.open("x", encoding="utf-8") as stream:
            stream.write(datetime.now(timezone.utc).isoformat())
    except FileExistsError as exc:
        raise RuntimeError(f"Research directory is already being written: {lock}") from exc
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _normalized_rows(result: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    from .datafeed import to_bars

    rows = []
    for bar in to_bars(result, symbol):
        stamp = bar.datetime
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=CHINA_TZ)
        stamp = stamp.astimezone(CHINA_TZ).replace(tzinfo=None)
        rows.append({
            "symbol": bar.symbol,
            "exchange": bar.exchange.value,
            "interval": bar.interval.value,
            "datetime": stamp,
            **{field: float(getattr(bar, field)) for field in VALUE_FIELDS},
        })
    if not rows:
        raise ValueError("An ok history response must contain bars")
    return rows


def _create_sqlite_schema(connection: sqlite3.Connection) -> None:
    """Create the four tables understood by the vnpy_sqlite adapter."""
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS dbbardata (
            id INTEGER PRIMARY KEY, symbol VARCHAR(255) NOT NULL,
            exchange VARCHAR(255) NOT NULL, datetime DATETIME NOT NULL,
            interval VARCHAR(255) NOT NULL, volume REAL NOT NULL,
            turnover REAL NOT NULL, open_interest REAL NOT NULL,
            open_price REAL NOT NULL, high_price REAL NOT NULL,
            low_price REAL NOT NULL, close_price REAL NOT NULL,
            UNIQUE (symbol, exchange, interval, datetime)
        );
        CREATE TABLE IF NOT EXISTS dbbaroverview (
            id INTEGER PRIMARY KEY, symbol VARCHAR(255) NOT NULL,
            exchange VARCHAR(255) NOT NULL, interval VARCHAR(255) NOT NULL,
            count INTEGER NOT NULL, start DATETIME NOT NULL, end DATETIME NOT NULL,
            UNIQUE (symbol, exchange, interval)
        );
        CREATE TABLE IF NOT EXISTS dbtickoverview (
            id INTEGER PRIMARY KEY, symbol VARCHAR(255) NOT NULL,
            exchange VARCHAR(255) NOT NULL, count INTEGER NOT NULL,
            start DATETIME NOT NULL, end DATETIME NOT NULL,
            UNIQUE (symbol, exchange)
        );
    """)
    fixed = [
        "id INTEGER PRIMARY KEY", "symbol VARCHAR(255) NOT NULL",
        "exchange VARCHAR(255) NOT NULL", "datetime DATETIME NOT NULL",
        "name VARCHAR(255) NOT NULL",
    ]
    numeric = (
        "volume", "turnover", "open_interest", "last_price", "last_volume",
        "limit_up", "limit_down", "open_price", "high_price", "low_price", "pre_close",
    )
    fixed.extend(f"{field} REAL NOT NULL" for field in numeric)
    for side in ("bid", "ask"):
        for field in ("price", "volume"):
            for level in range(1, 6):
                suffix = " NOT NULL" if level == 1 else ""
                fixed.append(f"{side}_{field}_{level} REAL{suffix}")
    fixed.extend(("localtime DATETIME", "UNIQUE (symbol, exchange, datetime)"))
    connection.execute("CREATE TABLE IF NOT EXISTS dbtickdata (" + ", ".join(fixed) + ")")


def _save_sqlite(directory: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    path = directory / "database.db"
    columns = ("symbol", "exchange", "interval", "datetime", *VALUE_FIELDS)
    values = [tuple(
        row[field].isoformat(sep=" ", timespec="microseconds")
        if field == "datetime" else row[field]
        for field in columns
    ) for row in rows]
    with sqlite3.connect(path) as connection:
        _create_sqlite_schema(connection)
        connection.executemany(
            "INSERT OR REPLACE INTO dbbardata (" + ",".join(columns) + ") VALUES ("
            + ",".join("?" for _ in columns) + ")", values,
        )
        first = rows[0]
        key = (first["symbol"], first["exchange"], first["interval"])
        count, start, end = connection.execute(
            "SELECT COUNT(*), MIN(datetime), MAX(datetime) FROM dbbardata "
            "WHERE symbol=? AND exchange=? AND interval=?", key,
        ).fetchone()
        connection.execute(
            "INSERT OR REPLACE INTO dbbaroverview "
            "(symbol, exchange, interval, count, start, end) VALUES (?, ?, ?, ?, ?, ?)",
            (*key, count, start, end),
        )
        for expected in values:
            actual = connection.execute(
                "SELECT " + ",".join(columns) + " FROM dbbardata "
                "WHERE symbol=? AND exchange=? AND interval=? AND datetime=?", expected[:4],
            ).fetchone()
            if actual != expected:
                raise RuntimeError("SQLite readback did not match the downloaded bars")
    return {"path": str(path), "verified_rows": len(rows), "readback": "sqlite3"}


def _save_alpha(directory: Path, rows: list[dict[str, Any]], symbol: str) -> dict[str, Any]:
    try:
        import polars as pl
    except ImportError as exc:
        raise RuntimeError(
            "Alpha export requires polars in the Studio Python environment; "
            "install polars with that interpreter and retry"
        ) from exc

    interval = rows[0]["interval"]
    if interval not in {"d", "1m"}:
        raise ValueError("AlphaLab stores daily and 1m bars only")
    folder = directory / ("daily" if interval == "d" else "minute")
    folder.mkdir(exist_ok=True)
    path = folder / f"{symbol}.parquet"
    renamed = {"open_price": "open", "high_price": "high", "low_price": "low", "close_price": "close"}
    data = [{
        "datetime": row["datetime"],
        **{renamed.get(field, field): row[field] for field in VALUE_FIELDS},
    } for row in rows]
    frame = pl.DataFrame(data)
    if path.exists():
        frame = pl.concat([pl.read_parquet(path), frame])
    frame = frame.unique(subset=["datetime"], keep="last").sort("datetime")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        frame.write_parquet(temporary)
        readback = pl.read_parquet(temporary)
        actual = {row["datetime"]: row for row in readback.to_dicts()}
        if any(actual.get(row["datetime"]) != row for row in data):
            raise RuntimeError("Alpha Parquet readback did not match the downloaded bars")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(path), "verified_rows": len(rows), "readback": "polars", "format": "AlphaLab"}


def _utc_ns(stamp: datetime) -> int:
    """Exact UTC epoch nanoseconds (integer arithmetic, no float rounding)."""
    delta = stamp.astimezone(timezone.utc) - UTC_EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1000


def _store_modules() -> tuple[Any, Any, Any]:
    """Lazy import of the immutable research store and its Arrow dependency."""
    try:
        import pyarrow as pa
        import research_store
        from research_store.schemas import BARS_SCHEMA_V1
    except ImportError as exc:
        raise RuntimeError(
            "The store target needs the vnpy_researchstore integration: make "
            "D:/repo/vnpy/integrations/vnpy_researchstore importable (its .venv "
            "interpreter already provides research_store, pyarrow, duckdb and "
            f"zstandard) and retry ({exc})"
        ) from exc
    return research_store, BARS_SCHEMA_V1, pa


def _store_rows(
    records: list[dict[str, Any]], symbol: str, interval: str, time_label: Any,
    dataset_id: str, asset_id: str, batch_id: str,
) -> list[dict[str, Any]]:
    """Canonical BARS_SCHEMA_V1 rows straight from result records.

    NULL measures stay NULL (never 0.0); non-finite values become NULL plus a
    per-row field_quality note. Daily bounds are [day 00:00 Asia/Shanghai,
    next day) in UTC ns; minute intervals require a start time label.
    """
    instrument = symbol.split(".")[0]
    exchange = symbol.split(".")[1] if "." in symbol else None
    rows: list[dict[str, Any]] = []
    for record in records:
        raw_stamp = record.get("datetime")
        if not isinstance(raw_stamp, str) or not raw_stamp:
            raise ValueError("Every history record must carry a datetime string")
        stamp = datetime.fromisoformat(raw_stamp.replace("Z", "+00:00"))
        stamp = stamp.replace(tzinfo=CHINA_TZ) if stamp.tzinfo is None else stamp.astimezone(CHINA_TZ)
        if interval == "d":
            day = stamp.date()
            start = datetime.combine(day, time(), CHINA_TZ)
            end = start + timedelta(days=1)
            trading_date: Any = day
        else:
            if time_label != "start":
                raise ValueError(
                    f"Minute history with time_label {time_label!r} has no evidenced "
                    "bar-start semantics; refusing to guess bar bounds"
                )
            start = stamp
            end = stamp + timedelta(minutes=STORE_MINUTES[interval])
            trading_date = None  # no calendar evidence for minute bars
        quality: dict[str, Any] = {}
        measures: dict[str, Any] = {}
        for field in STORE_MEASURE_FIELDS:
            value = record.get(field)
            if value is None:
                measures[field] = None
                quality.setdefault("missing", []).append(field)
                continue
            number = float(value)
            if not math.isfinite(number):
                measures[field] = None
                quality.setdefault("nonfinite", []).append(field)
                continue
            measures[field] = number
        extensions = {
            key: value for key, value in record.items()
            if key not in {"datetime", *STORE_MEASURE_FIELDS}
        }
        rows.append({
            "dataset_id": dataset_id,
            "instrument_id": instrument,
            "series_id": None,
            "symbol": symbol,
            "exchange": exchange,
            "bar_start": _utc_ns(start),
            "bar_end": _utc_ns(end),
            "trading_date": trading_date,
            "source_label": raw_stamp,
            **measures,
            "completeness": "unknown",
            "field_quality": json.dumps(quality, ensure_ascii=False, sort_keys=True) if quality else None,
            "contract_id": None,
            "asset_id": asset_id,
            "batch_id": batch_id,
            "transform_version": STORE_ADAPTER,
            "extensions_json": json.dumps(extensions, ensure_ascii=False, sort_keys=True)
            if extensions else None,
        })
    rows.sort(key=lambda row: (row["instrument_id"], row["bar_start"]))
    return rows


def _verify_store_readback(
    research_store: Any, store: Any, snapshot_id: str, dataset_id: str,
    rows: list[dict[str, Any]],
) -> int:
    """Real snapshot readback: every input row must exist with equal values."""
    snapshot = research_store.open_snapshot(store, snapshot_id)
    try:
        actual: dict[int, dict[str, Any]] = {}
        for batch in snapshot.bars(dataset_id, required_fields=(), allow_missing_auxiliary=True):
            for row in batch.to_pylist():
                actual[row["bar_start"]] = row
    finally:
        snapshot.close()
    for expected in rows:
        seen = actual.get(expected["bar_start"])
        if seen is None:
            raise RuntimeError(
                f"Store readback is missing bar_start {expected['bar_start']}"
            )
        for field in ("open", "high", "low", "close", "volume", "turnover"):
            if seen[field] != expected[field] and not (seen[field] is None and expected[field] is None):
                raise RuntimeError(
                    f"Store readback mismatch at {expected['bar_start']} field {field}: "
                    f"{seen[field]!r} != {expected[field]!r}"
                )
        if seen["trading_date"] != expected["trading_date"]:
            raise RuntimeError(
                f"Store readback trading_date mismatch at {expected['bar_start']}"
            )
    return len(rows)


def _save_store(result: dict[str, Any], symbol: str, output: str | Path) -> dict[str, Any]:
    """Save one ok result into an immutable research_store at ``output``.

    The raw result JSON (records, metadata, attempts, request, registry_sha256,
    fetched_at — all verbatim) is captured under the store's ``captures/`` and
    registered as the content-hashed import asset, so identical payloads replay
    idempotently. Real NULLs (e.g. missing turnover) are preserved end to end;
    the write is verified by a snapshot readback. The datasource receipt lives
    under the store's ``reports/`` directory; no datasource manifest is written
    into the store root.
    """
    metadata = result.get("metadata", {})
    provenance = metadata.get("warehouse_provenance")
    mapping_key = None
    if result.get("source") == "warehouse":
        if not provenance or provenance.get("status") != "verified":
            raise ValueError("Warehouse source mapping missing; re-read a pinned source snapshot")
        manifest = Path(provenance["manifest_path"])
        if hashlib.sha256(manifest.read_bytes()).hexdigest() != provenance["manifest_sha256"]:
            raise ValueError("Warehouse manifest hash mismatch")
        provenance = {**provenance, "storage_transform_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        mapping_key = hashlib.sha256(_json_text({"source": provenance, "symbol": symbol,
            "recipe": result.get("recipe")}).encode()).hexdigest()
    interval = metadata.get("interval")
    if not isinstance(interval, str) or not interval:
        raise ValueError("History metadata must explicitly specify interval")
    adjustment = metadata.get("adjustment")
    if not isinstance(adjustment, str) or not adjustment:
        raise ValueError("History metadata must explicitly specify adjustment")
    if interval not in STORE_INTERVALS:
        raise ValueError(f"research_store has no interval for {interval!r}")
    records = result.get("records", [])
    if not records:
        raise ValueError("An ok history response must contain records")
    research_store, bars_schema, pa = _store_modules()

    directory = Path(output).expanduser().resolve()
    if directory.exists() and not directory.is_dir():
        raise ValueError("output must be a research directory")
    directory.mkdir(parents=True, exist_ok=True)
    # init_store is a no-op for an identified store and refuses any other
    # non-empty directory, so unmanaged directories are never adopted.
    store = research_store.init_store(directory)
    try:
        with _directory_lock(store.root):
            capture = store.path.captures / (
                f"datasource-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:12]}.json"
            )
            _write_json(capture, {**result, "bridge_provenance": provenance} if mapping_key else result)
            capture_bytes = capture.read_bytes()
            asset_sha256 = hashlib.sha256(capture_bytes).hexdigest()
            asset_id = f"asset-datasource-{asset_sha256[:16]}"
            batch_label = f"datasource-{asset_sha256[:16]}"

            asset_hint = (
                metadata.get("asset")
                or result.get("request", {}).get("asset")
                or result.get("request", {}).get("params", {}).get("asset")
            )
            asset_class = research_store.AssetClass(
                STORE_ASSET_CLASSES.get(str(asset_hint), "other")
            )
            adjustment_map = {
                "none": research_store.Adjustment.NONE,
                "qfq": research_store.Adjustment.QFQ,
                "hfq": research_store.Adjustment.HFQ,
            }
            time_label = metadata.get("time_label")
            label = research_store.TimeLabel.START if (
                (interval == "d" and time_label == "date")
                or (interval != "d" and time_label == "start")
            ) else research_store.TimeLabel.UNKNOWN
            spec = research_store.SemanticSpec(
                source_id=str(result.get("source") or "unknown"),
                asset_class=asset_class,
                record_kind=research_store.RecordKind.BARS,
                interval=research_store.Interval(STORE_INTERVALS[interval]),
                adjustment=adjustment_map.get(adjustment, research_store.Adjustment.UNKNOWN),
                adjustment_version="",
                series_kind="instrument",
                rule_version="",
                timezone="Asia/Shanghai",
                source_time_label=label,
                volume_unit=str(metadata.get("volume_unit", "")),
                turnover_unit=str(metadata.get("turnover_unit", "")),
                origin_method=research_store.OriginMethod.SOURCE,
                schema_version=1,
            )
            dataset_id = research_store.compute_dataset_id(spec)
            rows = _store_rows(
                records, symbol, interval, time_label, dataset_id, asset_id, batch_label,
            )
            mapping_path = store.path.reports / f"warehouse-map-{mapping_key}.json" if mapping_key else None
            if mapping_path and mapping_path.exists():
                prior = json.loads(mapping_path.read_text(encoding="utf-8"))
                records_hash = hashlib.sha256(_json_text(records).encode()).hexdigest()
                if prior["records_sha256"] != records_hash:
                    raise ValueError("Same warehouse mapping produced conflicting records")
                _verify_store_readback(research_store, store, prior["snapshot_id"], dataset_id, rows)
                return {**prior["result"], "idempotent_replay": True}
            year_of = (
                (lambda row: row["trading_date"].year) if interval == "d"
                else (lambda row: datetime.fromtimestamp(
                    row["bar_start"] / 1_000_000_000, timezone.utc,
                ).astimezone(CHINA_TZ).year)
            )
            partitions = tuple(sorted({str(year_of(row)) for row in rows}))
            by_partition = {
                partition: [row for row in rows if str(year_of(row)) == partition]
                for partition in partitions
            }
            config = {
                "registry_sha256": str(result.get("registry_sha256") or ""),
                "fetched_at": str(result.get("fetched_at") or ""),
                "source": str(result.get("source") or ""),
                "recipe": str(result.get("recipe") or ""),
                "request": _json_text(result.get("request", {})),
                "attempts": str(len(result.get("attempts", []))),
                "capture": capture.name,
                "symbol": symbol,
                "interval": interval,
                "adjustment": adjustment,
            }
            idempotency_key = hashlib.sha256(_json_text({
                "adapter": STORE_ADAPTER, "asset_sha256": asset_sha256,
                "dataset_id": dataset_id, "target": "store",
            }).encode("utf-8")).hexdigest()
            request = research_store.ImportRequest(
                asset=research_store.AssetRef(
                    asset_id=asset_id,
                    origin=f"datasource_capture:{capture.name}",
                    format="datasource_result_json",
                    size=len(capture_bytes),
                    sha256=asset_sha256,
                ),
                spec=spec,
                adapter=STORE_ADAPTER,
                config=config,
                partitions=partitions,
                idempotency_key=idempotency_key,
            )

            def stream(partition: str) -> Iterator[Any]:
                chunk = by_partition[partition]
                for offset in range(0, len(chunk), 65536):
                    part = chunk[offset:offset + 65536]
                    yield pa.RecordBatch.from_pydict(
                        {name: [row[name] for row in part] for name in bars_schema.names},
                        schema=bars_schema,
                    )

            missing_turnover = [row.get("datetime") for row in records if row.get("turnover") is None]
            receipt_path = store.path.reports / (
                f"datasource-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:12]}.json"
            )
            receipt = {
                **{key: value for key, value in result.items() if key != "records"},
                "schema_version": 1, "symbol": symbol, "target": "store",
                "stored_at": datetime.now(timezone.utc).isoformat(),
                "storage_status": "pending",
                "record_count": len(records),
                "records_sha256": hashlib.sha256(_json_text(records).encode("utf-8")).hexdigest(),
                "turnover_missing": bool(missing_turnover),
                "turnover_missing_at": missing_turnover,
                "turnover_placeholder": None,
                "turnover_note": "Missing turnover stays NULL in the research store."
                if missing_turnover else "",
                "capture": str(capture), "capture_sha256": asset_sha256,
                "dataset_id": dataset_id,
            }
            _write_json(receipt_path, receipt)
            try:
                imported = research_store.import_asset(store, request, stream)
            except Exception as exc:
                receipt.update(storage_status="failed", error=f"{type(exc).__name__}: {exc}")
                _write_json(receipt_path, receipt)
                raise
            receipt.update(batch_id=imported.batch_id, batch_state=imported.state.value)
            if imported.state is not research_store.BatchState.PUBLISHED:
                conflicts = [
                    {"conflict_id": item.conflict_id, "partition": item.partition, "key": item.key}
                    for item in imported.conflicts
                ]
                receipt.update(storage_status="conflict", conflicts=conflicts)
                _write_json(receipt_path, receipt)
                return {
                    "status": "conflict", "source": result.get("source"),
                    "recipe": result.get("recipe"), "symbol": symbol, "target": "store",
                    "output": str(directory), "path": str(store.root),
                    "dataset_id": dataset_id, "batch_id": imported.batch_id,
                    "state": imported.state.value, "conflicts": conflicts,
                    "capture": str(capture), "receipt": str(receipt_path),
                    "turnover_missing": bool(missing_turnover), "adjustment": adjustment,
                    "detail": imported.detail,
                }
            try:
                snapshot = research_store.freeze(
                    store,
                    research_store.SnapshotRequest(
                        selections=(research_store.Selection(dataset_id, "*"),),
                        required_fields=(),
                    ),
                )
                verified = _verify_store_readback(
                    research_store, store, snapshot.snapshot_id, dataset_id, rows,
                )
            except Exception as exc:
                receipt.update(storage_status="failed", error=f"{type(exc).__name__}: {exc}")
                _write_json(receipt_path, receipt)
                raise
            saved = {
                "path": str(store.root), "dataset_id": dataset_id,
                "batch_id": imported.batch_id, "snapshot_id": snapshot.snapshot_id,
                "verified_rows": verified, "readback": "research_store",
                "capture": str(capture), "accepted_rows": imported.accepted_rows,
                "duplicate_rows": imported.duplicate_rows,
                "idempotent_replay": bool(imported.detail),
            }
            receipt.update(storage_status="verified", storage=saved)
            _write_json(receipt_path, receipt)
            response = {
                "status": "ok", "source": result.get("source"),
                "recipe": result.get("recipe"), "symbol": symbol, "target": "store",
                "output": str(directory), **saved,
                "receipt": str(receipt_path),
                "turnover_missing": bool(missing_turnover), "adjustment": adjustment,
            }
            if mapping_path:
                response["source_mapping"] = str(mapping_path)
                mapping = {"schema_version": 1, "source": provenance,
                    "snapshot_id": snapshot.snapshot_id, "dataset_id": dataset_id,
                    "input_rows": len(records), "verified_rows": verified,
                    "records_sha256": receipt["records_sha256"], "result": response}
                _write_json(mapping_path, mapping)
                receipt["source_mapping"] = mapping
                _write_json(receipt_path, receipt)
            return response
    finally:
        store.close()


def save_history(
    result: dict[str, Any], symbol: str, target: str, output: str | Path,
) -> dict[str, Any]:
    """Save one successful query with provenance and verify the saved values.

    The directory must be empty or created by this function. Price adjustment
    cannot change within a research directory. No global vnpy setting is edited.
    Target ``store`` writes into an immutable research_store directory instead,
    preserving real NULLs and verbatim historical metadata; it has its own
    store.json identity and never receives a datasource manifest.
    """
    if target not in {"sqlite", "alpha", "store"}:
        raise ValueError("target must be sqlite, alpha or store")
    if result.get("status") != "ok":
        raise ValueError(f"Cannot store history with status {result.get('status')!r}")
    if target == "store":
        return _save_store(result, symbol, output)
    rows = _normalized_rows(result, symbol)
    metadata = result.get("metadata", {})
    adjustment = metadata.get("adjustment")
    if not isinstance(adjustment, str) or not adjustment:
        raise ValueError("History metadata must explicitly specify adjustment")
    if target == "alpha" and rows[0]["interval"] not in {"d", "1m"}:
        raise ValueError("AlphaLab stores daily and 1m bars only")
    directory = Path(output).expanduser().resolve()
    if directory.exists() and not directory.is_dir():
        raise ValueError("output must be a research directory")
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / MANIFEST_NAME
    with _directory_lock(directory):
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("schema_version") != 1 or not isinstance(manifest.get("receipts"), list):
                raise ValueError("Existing research manifest has an unsupported format")
            if manifest.get("target") != target or manifest.get("adjustment") != adjustment:
                raise ValueError("Existing research directory has a different target or adjustment")
        else:
            unrelated = [path.name for path in directory.iterdir() if path.name != ".datasource-write.lock"]
            if unrelated:
                raise ValueError("Refusing to write an existing unmanaged directory; choose an empty output")
            manifest = {
                "schema_version": 1, "target": target, "adjustment": adjustment,
                "timezone": "Asia/Shanghai", "receipts": [],
            }
        receipts = directory / "receipts"
        receipts.mkdir(exist_ok=True)
        receipt_path = receipts / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:12]}.json"
        records = result.get("records", [])
        missing_turnover = [row.get("datetime") for row in records if row.get("turnover") is None]
        receipt = {
            **{key: value for key, value in result.items() if key != "records"},
            "schema_version": 1, "symbol": symbol, "target": target,
            "stored_at": datetime.now(timezone.utc).isoformat(), "storage_status": "pending",
            "record_count": len(records),
            "records_sha256": hashlib.sha256(_json_text(records).encode("utf-8")).hexdigest(),
            "turnover_missing": bool(missing_turnover), "turnover_missing_at": missing_turnover,
            "turnover_placeholder": 0.0 if missing_turnover else None,
            "turnover_note": "Missing turnover uses 0 only for BarData compatibility; it is not measured turnover."
            if missing_turnover else "",
        }
        _write_json(manifest_path, manifest)
        _write_json(receipt_path, receipt)
        try:
            saved = _save_sqlite(directory, rows) if target == "sqlite" else _save_alpha(directory, rows, symbol)
        except Exception as exc:
            receipt.update(storage_status="failed", error=f"{type(exc).__name__}: {exc}")
            _write_json(receipt_path, receipt)
            raise
        receipt.update(storage_status="verified", storage=saved)
        _write_json(receipt_path, receipt)
        manifest["receipts"].append(str(receipt_path.relative_to(directory)))
        _write_json(manifest_path, manifest)
    return {
        "status": "ok", "source": result.get("source"), "recipe": result.get("recipe"),
        "symbol": symbol, "target": target, "output": str(directory), **saved,
        "receipt": str(receipt_path), "manifest": str(manifest_path),
        "turnover_missing": bool(missing_turnover), "adjustment": adjustment,
    }
