"""Core model / store / identity tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from research_store import (
    Adjustment,
    ImportRequest,
    SealRequest,
    SealError,
    SessionRecoveryError,
    StoreError,
    StoreExistsError,
    StoreNotFoundError,
    compute_dataset_id,
    default_idempotency_key,
    init_store,
    open_store,
    recover_session,
    seal,
)

from conftest import make_asset, make_spec


def test_pure_core_import_has_no_vnpy_side_effects() -> None:
    # Fresh interpreter: immune to other suites importing vnpy earlier in the
    # same pytest process.
    import subprocess

    code = (
        "import sys; import research_store; "
        "bad = [m for m in sys.modules if m == 'vnpy' or m.startswith('vnpy.')]; "
        "assert not bad, f'pure core import pulled in {bad}'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_dataset_id_is_content_addressed_and_stable() -> None:
    spec = make_spec()
    assert compute_dataset_id(spec) == compute_dataset_id(make_spec())
    assert compute_dataset_id(spec).startswith("ds-")
    # Any discriminating semantic field changes the identity: adjustments and
    # native-vs-derived data can never silently merge.
    assert compute_dataset_id(make_spec(adjustment=Adjustment.QFQ)) != compute_dataset_id(spec)
    assert compute_dataset_id(make_spec(source_id="other")) != compute_dataset_id(spec)


def test_default_idempotency_key_requires_verified_hash(tmp_path: Path) -> None:
    asset = make_asset(tmp_path, "a.csv", b"data")
    spec = make_spec()
    request = ImportRequest(
        asset=asset, spec=spec, adapter="synthetic/0.1",
        config={"member": "a.csv"}, partitions=("2024",),
    )
    key1 = default_idempotency_key(request)
    assert key1 == default_idempotency_key(request)  # stable, no timestamps

    unverified = ImportRequest(
        asset=type(asset)(asset.asset_id, asset.origin, asset.format, asset.size, None),
        spec=spec, adapter="synthetic/0.1", config={"member": "a.csv"},
        partitions=("2024",),
    )
    with pytest.raises(StoreError):
        default_idempotency_key(unverified)


def test_init_store_only_empty_or_identified(tmp_path: Path) -> None:
    root = tmp_path / "s"
    store = init_store(root)
    store_id = store.store_id
    store.close()
    again = init_store(root)  # re-init of identified store is a no-op
    assert again.store_id == store_id
    again.close()

    dirty = tmp_path / "dirty"
    dirty.mkdir()
    (dirty / "unrelated.txt").write_text("keep me")
    with pytest.raises(StoreExistsError):
        init_store(dirty)

    with pytest.raises(StoreNotFoundError):
        open_store(tmp_path / "missing")


def test_store_works_from_other_cwd(store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")
    reopened = open_store(store.root)
    assert reopened.path.objects.is_dir()
    reopened.close()


def test_recording_apis_raise_typed_error_for_unknown_session(store) -> None:
    # recover_session / seal are implemented (WP09); unknown sessions must
    # raise their typed errors, not PendingCapabilityError stubs.
    with pytest.raises(SessionRecoveryError):
        recover_session(store, "session-x")
    with pytest.raises(SealError):
        seal(store, SealRequest(
            session_id="session-x", committed_seq_start=1, committed_seq_end=2,
            transform_version="t0", source_spec="s", calendar_spec="c",
        ))
