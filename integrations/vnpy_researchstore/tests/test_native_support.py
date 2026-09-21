"""Shared helpers for the native bridge tests (test_native_*.py).

This module is import-safe at pytest collection time: it never imports vnpy
at module level (a core test asserts ``import research_store`` leaves
``sys.modules`` vnpy-free, and collection imports every test module first).
Call ``ensure_isolated_vnpy()`` — directly or through the lazy accessors —
from inside fixtures/test bodies: on first use it switches the cwd into an
isolated temporary runtime BEFORE the first ``vnpy.trader.utility`` import
(so ``TRADER_DIR`` never points at the default ``~/.vntrader``), then restores
the previous cwd.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from research_store import (
    Selection,
    SnapshotRequest,
    Store,
    freeze,
)
from research_store import Interval as RSInterval  # noqa: F401  (re-export)
from research_store import AssetClass  # noqa: F401  (re-export)

from conftest import bar_row, import_rows, make_spec, ns

if TYPE_CHECKING:
    from vnpy_researchstore.alpha import ResearchAlphaLab
    from vnpy_researchstore.database import Database

DAILY_DATES = [
    date(2024, 1, 2),
    date(2024, 1, 3),
    date(2024, 1, 4),
    date(2024, 1, 5),
    date(2024, 1, 8),
]

# Minute bar_start values in UTC; in Asia/Shanghai these are 09:30+ local.
MINUTE_STARTS = [ns(2024, 1, 2, 1, 30 + i) for i in range(6)]


def ensure_isolated_vnpy() -> None:
    """Import vnpy.trader.utility under an isolated cwd exactly once."""
    if "vnpy.trader.utility" in sys.modules:
        return
    runtime = Path(tempfile.mkdtemp(prefix="vnpy-researchstore-test-runtime-"))
    (runtime / ".vntrader").mkdir(parents=True, exist_ok=True)
    previous_cwd = Path.cwd()
    os.chdir(runtime)
    try:
        import vnpy.trader.utility  # noqa: F401  (pins TRADER_DIR to runtime)
    finally:
        os.chdir(previous_cwd)


def vt_constants() -> tuple[Any, Any]:
    """Lazy (Exchange, Interval) — call from inside test bodies only."""
    ensure_isolated_vnpy()
    from vnpy.trader.constant import Exchange, Interval

    return Exchange, Interval


def daily_rows(
    instrument: str,
    *,
    exchange: str = "XSHE",
    close0: float = 10.0,
    turnover: float | None = 1000.0,
    open_interest: float | None = None,
    field_quality: str | None = None,
    volume: float | None = 100.0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, day in enumerate(DAILY_DATES):
        row = bar_row(
            "DATASET",
            instrument,
            ns(day.year, day.month, day.day, 1, 30),
            close=close0 + i,
            volume=volume,
            turnover=None if turnover is None else turnover + i,
            open_interest=open_interest,
            trading=day,
        )
        row["exchange"] = exchange
        row["field_quality"] = field_quality
        rows.append(row)
    return rows


def minute_rows(
    instrument: str,
    *,
    exchange: str = "XSHE",
    trading: date | None = date(2024, 1, 2),
    turnover: float | None = 100.0,
    open_interest: float | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, start_ns in enumerate(MINUTE_STARTS):
        row = bar_row(
            "DATASET",
            instrument,
            start_ns,
            close=10.0 + i,
            turnover=turnover,
            open_interest=open_interest,
            trading=trading,  # type: ignore[arg-type]
        )
        row["exchange"] = exchange
        rows.append(row)
    return rows


def import_dataset(
    store: Store,
    tmp_path: Path,
    rows: list[dict[str, Any]],
    *,
    asset_name: str,
    **spec_overrides: Any,
) -> str:
    """Import rows under a distinct semantic spec; returns the dataset id."""
    spec = make_spec(**spec_overrides)
    receipt = import_rows(
        store,
        tmp_path,
        rows,
        spec,
        asset_name=asset_name,
        asset_content=f"fixture-{asset_name}".encode(),
    )
    return receipt.dataset_id


def freeze_all(store: Store, dataset_ids: list[str]) -> str:
    ref = freeze(
        store,
        SnapshotRequest(
            selections=tuple(Selection(dataset_id, "*") for dataset_id in dataset_ids)
        ),
    )
    return ref.snapshot_id


def make_database(
    store_root: Path | str,
    snapshot_id: str,
    *,
    allow_missing_auxiliary: bool = False,
) -> Database:
    ensure_isolated_vnpy()
    from vnpy.trader.setting import SETTINGS

    from vnpy_researchstore.database import Database

    SETTINGS["researchstore.root"] = str(store_root)
    SETTINGS["researchstore.snapshot_id"] = snapshot_id
    SETTINGS["researchstore.allow_missing_auxiliary"] = allow_missing_auxiliary
    SETTINGS.pop("researchstore.exchange_map", None)
    return Database()


def make_lab(
    lab_path: Path,
    store: Store,
    snapshot_id: str,
    **kwargs: Any,
) -> ResearchAlphaLab:
    ensure_isolated_vnpy()
    from vnpy_researchstore.alpha import ResearchAlphaLab

    return ResearchAlphaLab(str(lab_path), str(store.root), snapshot_id, **kwargs)


def native_minute_dt(index: int) -> datetime:
    """Expected native (naive DB_TZ) datetime for MINUTE_STARTS[index]."""
    ensure_isolated_vnpy()
    from vnpy.trader.database import DB_TZ

    aware = datetime.fromtimestamp(MINUTE_STARTS[index] / 1e9, tz=timezone.utc)
    return aware.astimezone(DB_TZ).replace(tzinfo=None)


def untrusted_quality() -> str:
    return json.dumps({"flags": [], "amount_untrusted": True})
