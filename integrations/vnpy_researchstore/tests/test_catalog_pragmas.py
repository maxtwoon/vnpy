"""Catalog-level tests: pragmas, schema, invariants."""

from __future__ import annotations

import sqlite3

import pytest

from research_store.models import CatalogError


def test_catalog_pragmas(store) -> None:
    conn = store.catalog
    assert conn.query_one("PRAGMA journal_mode")[0] == "wal"
    assert conn.query_one("PRAGMA foreign_keys")[0] == 1
    assert conn.query_one("PRAGMA synchronous")[0] == 2  # FULL
    assert conn.query_one("PRAGMA busy_timeout")[0] == 5000
    assert conn.query_one("PRAGMA user_version")[0] == 1


def test_dataset_semantics_cannot_be_redefined(store) -> None:
    store.catalog.ensure_dataset("ds-x", '{"a": 1}', 1, "now")
    store.catalog.ensure_dataset("ds-x", '{"a": 1}', 1, "later")  # same is fine
    with pytest.raises(CatalogError):
        store.catalog.ensure_dataset("ds-x", '{"a": 2}', 1, "later")


def test_foreign_keys_enforced(store) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        with store.catalog.transaction():
            store.catalog.insert_revision(
                "rev-x", "ds-missing", "2024", None, "/tmp/m", "h", 0,
                "batch-missing", "now",
            )


def test_transaction_rolls_back_on_error(store) -> None:
    store.catalog.ensure_dataset("ds-y", '{"b": 1}', 1, "now")
    with pytest.raises(RuntimeError):
        with store.catalog.transaction():
            store.catalog.execute(
                "INSERT INTO datasets (dataset_id, semantic_json, schema_version, created_at)"
                " VALUES ('ds-z', '{}', 1, 'now')"
            )
            raise RuntimeError("boom")
    assert store.catalog.get_dataset("ds-z") is None
