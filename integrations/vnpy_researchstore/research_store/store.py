"""Store root lifecycle: init/open, layout, identification.

Layout under the store root (plan §Layout):
    store.json, catalog.sqlite, objects/, manifests/revisions/,
    manifests/snapshots/, captures/, staging/, journals/, configs/, reports/,
    exports/, runtime/
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .catalog import Catalog
from .models import StoreExistsError, StoreNotFoundError, StoreError

STORE_FORMAT = 1


@dataclass(frozen=True)
class StorePaths:
    root: Path
    catalog: Path
    objects: Path
    revision_manifests: Path
    snapshot_manifests: Path
    captures: Path
    staging: Path
    journals: Path
    configs: Path
    reports: Path
    exports: Path
    runtime: Path

    def all_dirs(self) -> tuple[Path, ...]:
        return (
            self.objects,
            self.revision_manifests,
            self.snapshot_manifests,
            self.captures,
            self.staging,
            self.journals,
            self.configs,
            self.reports,
            self.exports,
            self.runtime,
        )


def store_paths(root: Path) -> StorePaths:
    return StorePaths(
        root=root,
        catalog=root / "catalog.sqlite",
        objects=root / "objects",
        revision_manifests=root / "manifests" / "revisions",
        snapshot_manifests=root / "manifests" / "snapshots",
        captures=root / "captures",
        staging=root / "staging",
        journals=root / "journals",
        configs=root / "configs",
        reports=root / "reports",
        exports=root / "exports",
        runtime=root / "runtime",
    )


class Store:
    """An open research store. Works from any cwd: every path is absolute."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        meta_path = self.root / "store.json"
        if not meta_path.is_file():
            raise StoreNotFoundError(f"no store.json under {self.root}")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError(f"unreadable store.json at {meta_path}: {exc}") from exc
        if meta.get("store_format") != STORE_FORMAT:
            raise StoreError(
                f"unsupported store_format {meta.get('store_format')!r} at {meta_path}"
            )
        self.store_id: str = str(meta["store_id"])
        self.path = store_paths(self.root)
        self.catalog = Catalog(self.path.catalog)

    def close(self) -> None:
        self.catalog.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _is_empty_dir(root: Path) -> bool:
    return not any(root.iterdir())


def init_store(root: Path | str) -> Store:
    """Create a store. Only an empty directory or an already-identified store.

    Re-initializing an identified store is a no-op; anything else raises
    StoreExistsError so a wrong path can never silently become a store.
    """

    root_path = Path(root).resolve()
    meta_path = root_path / "store.json"
    if meta_path.is_file():
        return open_store(root_path)
    root_path.mkdir(parents=True, exist_ok=True)
    if not _is_empty_dir(root_path):
        raise StoreExistsError(
            f"refusing to initialize non-empty unidentified directory {root_path}"
        )
    paths = store_paths(root_path)
    for directory in paths.all_dirs():
        directory.mkdir(parents=True, exist_ok=True)
    meta = {
        "store_format": STORE_FORMAT,
        "store_id": f"store-{uuid.uuid4().hex[:16]}",
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    meta_path.write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return Store(root_path)


def open_store(root: Path | str) -> Store:
    return Store(root)
