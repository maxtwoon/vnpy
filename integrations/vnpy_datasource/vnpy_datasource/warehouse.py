"""Read the dataSource local backtest warehouse (fixed Parquet snapshots via DuckDB).

This is the offline, reproducible path: no network, millisecond latency, and every
result carries the ``snapshot_id`` it was read from. It produces the same envelope as
:meth:`DataSourceClient.history`, so ``to_bars`` / ``save_history`` work unchanged.
"""

from __future__ import annotations

import json
import hashlib
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .validation import history_params, local_time, validate_bars

EXCHANGE_TO_WH = {"SSE": "XSHG", "SZSE": "XSHE"}
WH_TO_EXCHANGE = {value: key for key, value in EXCHANGE_TO_WH.items()}
INTERVAL_TO_WH = {"d": "1d", "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "60m"}
BAR_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}
VOLUME_UNITS = {"stock": "shares", "etf": "units", "index": "shares"}


class WarehouseUnavailable(RuntimeError):
    """The local warehouse cannot be read in this interpreter (deps or data missing)."""


class WarehouseReader:
    """Query ``warehouse.query.Snapshot`` of a dataSource checkout."""

    def __init__(self, root: str | Path = "D:/repo/dataSource", snapshot_id: str | None = None) -> None:
        self.root = Path(root)
        self.snapshot_id = snapshot_id or None
        self._checked: str | None = None

    # -- readiness -----------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        """Cheap readiness probe: dependencies importable and a current snapshot pointer exists."""
        pointer = self.root / "data" / "backtest" / "current.json"
        info: dict[str, Any] = {"root": str(self.root), "pointer": str(pointer), "ready": False}
        try:
            import duckdb  # noqa: F401
            import pyarrow  # noqa: F401
        except ImportError as exc:
            info["reason"] = f"missing_dependency:{exc.name}"
            return info
        if not pointer.exists():
            info["reason"] = "no_current_snapshot"
            return info
        info["current_snapshot"] = json.loads(pointer.read_text(encoding="utf-8")).get("snapshot_id")
        info["pinned_snapshot"] = self.snapshot_id
        info["ready"] = True
        return info

    def available(self) -> bool:
        return bool(self.status().get("ready"))

    def _snapshot(self):
        if str(self.root) not in sys.path:
            sys.path.insert(0, str(self.root))
        try:
            from warehouse.query import Snapshot
        except ImportError as exc:
            raise WarehouseUnavailable(f"warehouse_import_failed:{exc}") from exc
        return Snapshot(self.snapshot_id)

    # -- query ---------------------------------------------------------------------
    def history(self, symbol: str, start: str, end: str, interval: str = "d",
                adjust: str = "none", asset: str | None = None) -> dict[str, Any]:
        """Return closed bars from the local warehouse in the client envelope.

        Unadjusted only; warehouse ``adjusted=True`` is deliberately not exposed here
        because vnpy stores raw prices and mixing regimes in one research directory is
        refused by ``save_history``.
        """
        params = history_params(symbol, start, end, interval, adjust, asset)
        if adjust != "none":
            return self._envelope(params, "unsupported", reason="warehouse_serves_unadjusted_only")
        if interval not in INTERVAL_TO_WH:
            return self._envelope(params, "unsupported", reason="unsupported_interval")
        code, exchange = symbol.split(".")
        if exchange not in EXCHANGE_TO_WH:
            return self._envelope(params, "unsupported", reason="exchange_not_in_warehouse")
        wh_symbol = f"{code}.{EXCHANGE_TO_WH[exchange]}"
        frequency = INTERVAL_TO_WH[interval]
        begin, finish = local_time(start), local_time(end)
        try:
            with self._snapshot() as db:
                snapshot_id = db.snapshot_id
                provenance = {"status": "missing", "snapshot_id": snapshot_id}
                if hasattr(db, "root"):
                    manifest_path = Path(db.root) / "snapshots" / f"{snapshot_id}.json"
                    manifest_bytes = manifest_path.read_bytes()
                    provenance = {
                        "status": "verified", "snapshot_id": snapshot_id,
                        "manifest_path": str(manifest_path),
                        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                        "query": params,
                        "parameters_sha256": hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest(),
                        "transform_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    }
                dataset = f"bars_{params['asset']}_{frequency}"
                provenance["dataset"] = dataset
                if dataset not in db.datasets():
                    return self._envelope(params, "no_data", reason=f"dataset_not_in_warehouse:{dataset}", snapshot_id=snapshot_id)
                frame = db.bars([wh_symbol], begin.date(), finish.date(), asset=params["asset"], frequency=frequency)
                if provenance["status"] == "verified" and hashlib.sha256(manifest_path.read_bytes()).hexdigest() != provenance["manifest_sha256"]:
                    raise ValueError("Warehouse manifest changed during query")
        except WarehouseUnavailable as exc:
            return self._envelope(params, "error", reason=str(exc))
        if frame.empty:
            return self._envelope(params, "no_data", reason="no_rows_in_warehouse", snapshot_id=snapshot_id)

        paused_dropped = 0
        if "paused" in frame:
            paused = frame["paused"].fillna(0) == 1
            paused_dropped = int(paused.sum())
            frame = frame[~paused]
        records, volume_missing, sources = [], [], set()
        for row in frame.itertuples(index=False):
            stamp = row.timestamp.to_pydatetime() if hasattr(row.timestamp, "to_pydatetime") else row.timestamp
            if interval == "d":
                label = stamp.date().isoformat()
            else:
                # Warehouse minute bars are end-labelled; vnpy labels a bar by its start.
                label = (stamp - timedelta(minutes=BAR_MINUTES[interval])).isoformat()
            volume = float(row.volume) if row.volume is not None and math.isfinite(float(row.volume)) else None
            if volume is None:
                volume_missing.append(label)
                volume = 0.0
            amount = float(row.amount) if row.amount is not None and math.isfinite(float(row.amount)) else None
            records.append({"datetime": label, "open": float(row.open), "high": float(row.high),
                            "low": float(row.low), "close": float(row.close), "volume": volume,
                            "turnover": amount, "open_interest": 0.0})
            sources.add(str(row.source))
        result = self._envelope(params, "ok", snapshot_id=snapshot_id)
        result.update(kind="bars", records=records, recipe=dataset, metadata={
            "interval": interval, "asset": params["asset"], "adjustment": "none",
            "timezone": "Asia/Shanghai", "time_label": "start",
            "volume_unit": VOLUME_UNITS[params["asset"]], "turnover_unit": "CNY",
            "missing_fields": ["volume"] if volume_missing else [],
            "volume_missing_at": volume_missing,
            "volume_note": "Index rows whose vendor volume definition differs from the archive keep volume=0 here; see warehouse README."
            if volume_missing else "",
            "paused_rows_dropped": paused_dropped,
            "warehouse_sources": sorted(sources),
            "snapshot_id": snapshot_id,
            "warehouse_provenance": provenance,
        })
        return validate_bars(result, params)

    @staticmethod
    def _envelope(params: dict[str, Any], status: str, *, reason: str | None = None,
                  snapshot_id: str | None = None) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "status": status, "kind": None, "records": [], "metadata": {},
            "source": "warehouse", "recipe": None, "attempts": [],
            "request": {"route": "warehouse", "params": params},
            "snapshot_id": snapshot_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        if reason:
            envelope["reason"] = reason
            envelope["attempts"].append({"source": "warehouse", "status": status, "reason": reason})
        return envelope
