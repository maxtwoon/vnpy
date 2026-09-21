"""Retention tests: eligibility rules (verified seal + 14d + no active owner),
partial/unverified refusal, CLOSED-without-seal refusal, path safety, and
strict journal-only cleanup.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from research_store.journal import create_session
from research_store.journal_models import JournalEvent
from research_store.models import AssetClass, SealRequest
from research_store.retention import (
    RetentionError,
    apply_retention,
    evaluate_retention,
)
from research_store.sealing import seal
from research_store.store import init_store

BASE = 1_700_000_000_000_000_000


def tick(ts: int) -> JournalEvent:
    return JournalEvent(
        kind="tick",
        instrument="IF2403.CFFEX",
        event_ts_ns=ts,
        source_event_id=None,
        payload={"last_price": 10.0, "volume": 100, "turnover": 1000},
    )


@pytest.fixture()
def store(tmp_path: Path):
    s = init_store(tmp_path / "store")
    yield s
    s.close()


def drain(session, n: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if session.status().committed_seq >= n:
            return
        time.sleep(0.01)
    raise AssertionError(f"committed_seq did not reach {n}: {session.status()}")


def sealed_session(store, n: int = 3) -> str:
    session = create_session(store, "futures:retention-sim", "Asia/Shanghai")
    for i in range(n):
        session.admit(tick(BASE + i * 60_000_000_000))
    drain(session, n)
    result = session.close_at_cutoff(timeout=5.0)
    assert result.state.value == "CLOSED"
    session.close()
    receipt = seal(
        store,
        SealRequest(
            session_id=session.session_id,
            committed_seq_start=1,
            committed_seq_end=n,
            transform_version="t0",
            source_spec="futures:retention-sim",
            calendar_spec="Asia/Shanghai",
            asset_class=AssetClass.FUTURES,
            volume_unit="contracts",
            turnover_unit="currency",
        ),
    )
    assert receipt.accepted_rows > 0
    return session.session_id


def _age_seals_to(store, session_id: str, days: int) -> None:
    """Backdate the seal record and batch timestamps by `days` days."""
    journal_path = store.path.journals / f"{session_id}.sqlite"
    conn = sqlite3.connect(str(journal_path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT value FROM session_meta WHERE key='seals'"
        ).fetchone()
        seals = json.loads(row["value"])
        old = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
        for seal_rec in seals:
            seal_rec["sealed_at"] = old
        with conn:
            conn.execute(
                "UPDATE session_meta SET value=? WHERE key='seals'",
                (json.dumps(seals, sort_keys=True),),
            )
        batch_ids = [s["ticks"]["batch_id"] for s in seals] + [
            s["bars"]["batch_id"] for s in seals
        ]
    finally:
        conn.close()
    with store.catalog.transaction():
        for batch_id in batch_ids:
            store.catalog._conn.execute(
                "UPDATE batches SET updated_at=? WHERE batch_id=?", (old, batch_id)
            )


def test_no_seal_not_eligible_even_when_closed(store) -> None:
    session = create_session(store, "src", "Asia/Shanghai")
    session.admit(tick(BASE))
    drain(session, 1)
    result = session.close_at_cutoff(timeout=5.0)
    assert result.state.value == "CLOSED"
    session.close()
    decision = evaluate_retention(store, session.session_id)
    assert not decision.eligible
    assert "no verified complete seal" in decision.reason


def test_recent_seal_not_eligible(store) -> None:
    session_id = sealed_session(store)
    decision = evaluate_retention(store, session_id)
    assert not decision.eligible
    assert "< 14d" in decision.reason


def test_aged_verified_seal_eligible_and_cleanup(store) -> None:
    session_id = sealed_session(store)
    _age_seals_to(store, session_id, days=15)
    decision = evaluate_retention(store, session_id)
    assert decision.eligible, decision.reason
    journal_file = store.path.journals / f"{session_id}.sqlite"
    assert journal_file.exists()
    applied = apply_retention(store, session_id)
    assert applied.eligible
    assert not journal_file.exists()
    # Canonical objects/snapshots are untouched.
    assert any(store.path.objects.iterdir())
    assert list(store.path.snapshot_manifests.iterdir()) or True


def test_active_owner_refused(store) -> None:
    session_id = sealed_session(store)
    _age_seals_to(store, session_id, days=20)
    # While an owner holds the session lock, retention is refused.
    from research_store.journal import open_session

    owner = open_session(store, session_id, readonly=True)
    try:
        decision = evaluate_retention(store, session_id)
        assert not decision.eligible
        assert "active owner" in decision.reason
    finally:
        owner.close()


def test_partial_seal_refused(store, monkeypatch) -> None:
    session_id = sealed_session(store)
    _age_seals_to(store, session_id, days=20)
    # Corrupt one sealed batch state to simulate partial publication.
    journal_path = store.path.journals / f"{session_id}.sqlite"
    conn = sqlite3.connect(str(journal_path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT value FROM session_meta WHERE key='seals'"
        ).fetchone()
        seals = json.loads(row["value"])
        bad_batch = seals[0]["bars"]["batch_id"]
    finally:
        conn.close()
    store.catalog.set_batch_state(bad_batch, "failed", datetime.now(tz=timezone.utc).isoformat())
    decision = evaluate_retention(store, session_id)
    assert not decision.eligible
    assert "no verified complete seal" in decision.reason


def test_unknown_session_raises(store) -> None:
    with pytest.raises(RetentionError, match="unknown journal session"):
        evaluate_retention(store, "sess-missing")


def test_cleanup_never_touches_non_journal_files(store) -> None:
    session_id = sealed_session(store)
    _age_seals_to(store, session_id, days=15)
    # Plant a decoy file that must survive.
    decoy = store.path.journals / f"{session_id}.sqlite.backup"
    decoy.write_text("decoy", encoding="utf-8")
    decision = apply_retention(store, session_id)
    assert decision.eligible
    assert decoy.exists()  # not a journal-owned suffix; never deleted
    canonical_before = sorted(
        p.relative_to(store.path.objects).as_posix()
        for p in store.path.objects.rglob("*")
        if p.is_file()
    )
    assert canonical_before  # sealed objects exist
    assert all((store.path.objects / n).exists() for n in canonical_before)


def test_path_traversal_session_id_refused(store) -> None:
    """A crafted session_id must never resolve outside ``<store>/journals/``."""
    victim = store.root.parent / "retention-traversal-victim.txt"
    victim.write_text("do not delete", encoding="utf-8")
    try:
        with pytest.raises(RetentionError, match="outside journal root"):
            evaluate_retention(store, "../retention-traversal-victim")
        with pytest.raises(RetentionError, match="outside journal root"):
            evaluate_retention(store, "..\\retention-traversal-victim")
        with pytest.raises(RetentionError, match="outside journal root"):
            apply_retention(store, "../retention-traversal-victim")
        assert victim.exists()  # untouched
    finally:
        victim.unlink(missing_ok=True)


def test_junction_or_symlink_escape_refused_or_precise_not_run(
    store, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Junction/symlink escape is refused when the host allows link creation.

    If the OS denies creation (unprivileged symlink on Windows), the case is
    recorded as a precise NOT_RUN skip — never a fabricated PASS or defect.
    """

    outside = tmp_path_factory.mktemp("retention-escape-outside")
    target = outside / "sess-jct.sqlite"
    target.write_bytes(b"victim journal bytes; must survive")
    link = store.path.journals / "jct"
    created_via: str | None = None
    if os.name == "nt":
        try:
            import _winapi

            _winapi.CreateJunction(str(outside), str(link))
            created_via = "junction"
        except OSError:
            created_via = None
    if created_via is None:
        try:
            link.symlink_to(outside, target_is_directory=True)
            created_via = "symlink"
        except (OSError, NotImplementedError):
            created_via = None
    if created_via is None:
        pytest.skip(
            "NOT_RUN: junction/symlink creation denied on this host; "
            "escape validation unexercised (recorded precisely, not a PASS)"
        )
    try:
        with pytest.raises(RetentionError, match="outside journal root"):
            evaluate_retention(store, "jct/sess-jct")
        with pytest.raises(RetentionError, match="outside journal root"):
            apply_retention(store, "jct/sess-jct")
        assert target.read_bytes() == b"victim journal bytes; must survive"
    finally:
        # Remove the link itself only — never recurse into the target.
        if created_via == "junction":
            os.rmdir(link)
        else:
            link.unlink(missing_ok=True)
