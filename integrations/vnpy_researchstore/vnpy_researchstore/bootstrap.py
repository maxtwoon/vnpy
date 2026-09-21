"""Process bootstrap for native consumers (CTA/Portfolio backtests, overview).

Guarantees, in order:

1. parse + validate the JSON config (unknown keys are rejected);
2. refuse to run when ``vnpy.trader.utility`` is already imported (its
   ``TRADER_DIR`` is pinned at import time, so the required cwd isolation
   could no longer be guaranteed) or when the vnpy database singleton is
   already initialized (no hot-switching);
3. put the configured repo path and integration path at the front of
   ``sys.path`` and ``chdir`` into the isolated runtime directory BEFORE
   anything transitively imports ``vnpy.trader.utility``;
4. import ``vnpy`` and assert its actual module file lives under the
   configured repo path (same version string does not prove same source);
5. set process-local nonsecret SETTINGS and explicitly import
   ``vnpy_researchstore.database`` so ``get_database`` cannot swallow a
   ModuleNotFoundError and fall back to SQLite;
6. call ``get_database`` and assert the actual plugin class and bound
   snapshot id;
7. only THEN import the CTA/Portfolio backtester modules;
8. emit a run receipt (config identity, module origins, snapshot, adapter,
   range) under the runtime directory.

No settings files are changed, no snapshot is hot-switched, and the existing
SQLite database is never used as a fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any

from research_store import StoreError

CONFIG_KEYS = {
    "store_root",
    "snapshot_id",
    "runtime_dir",
    "repo_path",
    "integration_path",
    "allow_missing_auxiliary",
    "exchange_map",
    "database_timezone",
    "backtesters",
    "range",
}

BACKTESTER_MODULES = {
    "cta": "vnpy_ctastrategy.backtesting",
    "portfolio": "vnpy_portfoliostrategy.backtesting",
}

ADAPTER_NAME = "vnpy_researchstore/0.1.0.dev1"


@dataclass(frozen=True)
class NativeBootstrapConfig:
    store_root: str
    snapshot_id: str
    runtime_dir: str
    repo_path: str
    integration_path: str
    allow_missing_auxiliary: bool = False
    exchange_map: str | None = None
    database_timezone: str | None = None
    backtesters: tuple[str, ...] = ("cta",)
    range: dict[str, str] | None = None


def load_config(config_path: str | Path) -> tuple[NativeBootstrapConfig, str]:
    """Parse and validate a bootstrap config; returns (config, identity)."""

    path = Path(config_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise StoreError(f"bootstrap config {path} must be a JSON object")
    unknown = sorted(k for k in raw if k not in CONFIG_KEYS and not k.startswith("_"))
    if unknown:
        raise StoreError(f"bootstrap config {path} has unknown keys {unknown}")
    missing = [
        key
        for key in ("store_root", "snapshot_id", "runtime_dir", "repo_path")
        if not raw.get(key)
    ]
    if missing:
        raise StoreError(f"bootstrap config {path} missing required keys {missing}")

    integration_path = raw.get("integration_path") or str(
        Path(__file__).resolve().parents[1]
    )
    backtesters = tuple(raw.get("backtesters", ("cta",)))
    for name in backtesters:
        if name not in BACKTESTER_MODULES:
            raise StoreError(
                f"unknown backtester {name!r}; known: {sorted(BACKTESTER_MODULES)}"
            )
    config = NativeBootstrapConfig(
        store_root=str(raw["store_root"]),
        snapshot_id=str(raw["snapshot_id"]),
        runtime_dir=str(raw["runtime_dir"]),
        repo_path=str(raw["repo_path"]),
        integration_path=str(integration_path),
        allow_missing_auxiliary=bool(raw.get("allow_missing_auxiliary", False)),
        exchange_map=raw.get("exchange_map"),
        database_timezone=raw.get("database_timezone"),
        backtesters=backtesters,
        range=raw.get("range"),
    )
    identity = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return config, identity


@dataclass
class NativeSession:
    """Result of a successful bootstrap: receipt plus live handles."""

    receipt: dict[str, Any]
    database: Any
    backtesters: dict[str, Any]


def bootstrap_session(
    config: NativeBootstrapConfig, config_identity: str
) -> NativeSession:
    """Run the guarded bootstrap sequence; see module docstring."""

    # (2) import-order and singleton guards
    if "vnpy.trader.utility" in sys.modules:
        raise StoreError(
            "vnpy.trader.utility is already imported; TRADER_DIR is pinned at "
            "import time, so cwd isolation can no longer be guaranteed. Run "
            "bootstrap in a fresh process."
        )
    if "vnpy.trader.database" in sys.modules:
        module = sys.modules["vnpy.trader.database"]
        if getattr(module, "database", None) is not None:
            raise StoreError(
                "vnpy database singleton is already initialized; refusing to "
                "hot-switch an existing process onto a research snapshot"
            )

    # (3) path selection and cwd isolation BEFORE any vnpy.trader import
    for path in (config.integration_path, config.repo_path):
        resolved = str(Path(path).resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)
    runtime_dir = Path(config.runtime_dir).resolve()
    (runtime_dir / ".vntrader").mkdir(parents=True, exist_ok=True)
    os.chdir(runtime_dir)

    # (4) import vnpy and assert actual origin
    import vnpy

    vnpy_file = Path(str(vnpy.__file__)).resolve()
    repo_root = Path(config.repo_path).resolve()
    if repo_root not in vnpy_file.parents:
        raise StoreError(
            f"vnpy module origin {vnpy_file} is not under the configured repo "
            f"path {repo_root}; version string alone does not prove the source"
        )

    # (5) process-local nonsecret settings + explicit plugin import
    from vnpy.trader.setting import SETTINGS

    SETTINGS["database.name"] = "researchstore"
    SETTINGS["researchstore.root"] = str(Path(config.store_root).resolve())
    SETTINGS["researchstore.snapshot_id"] = config.snapshot_id
    SETTINGS["researchstore.allow_missing_auxiliary"] = config.allow_missing_auxiliary
    if config.exchange_map:
        SETTINGS["researchstore.exchange_map"] = config.exchange_map
    if config.database_timezone:
        SETTINGS["database.timezone"] = config.database_timezone

    try:
        plugin_module = import_module("vnpy_researchstore.database")
    except ModuleNotFoundError as exc:
        raise StoreError(
            f"explicit import of vnpy_researchstore.database failed: {exc}; "
            "there is no SQLite fallback for native snapshot runs"
        ) from exc

    # (6) database singleton + class/snapshot assertions
    from vnpy.trader import database as database_module

    if database_module.database is not None:
        raise StoreError(
            "vnpy database singleton became initialized before plugin binding; "
            "refusing to continue"
        )
    database = database_module.get_database()
    if not isinstance(database, plugin_module.Database):
        raise StoreError(
            f"get_database returned {type(database).__module__}."
            f"{type(database).__name__}, expected vnpy_researchstore.database."
            "Database; refusing a silent fallback database"
        )
    if database.snapshot_id != config.snapshot_id:
        raise StoreError(
            f"plugin bound snapshot {database.snapshot_id} != configured "
            f"{config.snapshot_id}"
        )

    # (7) backtester imports AFTER the database is provably bound
    backtesters: dict[str, Any] = {}
    for name in config.backtesters:
        backtesters[name] = import_module(BACKTESTER_MODULES[name])

    # (8) run receipt
    receipt: dict[str, Any] = {
        "adapter": ADAPTER_NAME,
        "config_identity": config_identity,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "pid": os.getpid(),
        "python": sys.executable,
        "cwd": str(runtime_dir),
        "store_root": str(Path(config.store_root).resolve()),
        "snapshot_id": config.snapshot_id,
        "range": config.range,
        "vnpy": {
            "version": vnpy.__version__,
            "module_file": str(vnpy_file),
            "repo_path": str(repo_root),
        },
        "database": {
            "module": type(database).__module__,
            "class": type(database).__name__,
            "settings_name": SETTINGS["database.name"],
            "allow_missing_auxiliary": config.allow_missing_auxiliary,
            "diagnostics": list(database.diagnostics),
        },
        "backtesters": {
            name: str(Path(str(mod.__file__)).resolve())
            for name, mod in backtesters.items()
        },
    }
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt_path = runtime_dir / f"native_bootstrap_receipt-{timestamp}.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    receipt["receipt_path"] = str(receipt_path)
    return NativeSession(receipt=receipt, database=database, backtesters=backtesters)


def main(argv: list[str] | None = None) -> int:
    """CLI entry: ``python tools/native_bootstrap.py --config <path>``."""

    import argparse

    parser = argparse.ArgumentParser(description="native snapshot bootstrap")
    parser.add_argument("--config", required=True, help="bootstrap config JSON")
    args = parser.parse_args(argv)
    config, identity = load_config(args.config)
    session = bootstrap_session(config, identity)
    print(json.dumps(session.receipt, indent=2, sort_keys=True))
    return 0
