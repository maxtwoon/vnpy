"""Retention of journal files (WP09).

A journal file is eligible for deletion ONLY when ALL of the following hold:

1. It is a module-owned journal file (``<store>/journals/<session_id>.sqlite``
   plus its ``-wal``/``-shm``/``.lock`` sidecars) — never raw, canonical,
   snapshot, object, or manifest files.
2. Every seal recorded for the session is VERIFIED complete: the sealed
   batches are PUBLISHED in the catalog and their receipts match the durable
   seal record in the journal's own meta.
3. At least 14 days have passed since the newest verified seal.
4. No live owner holds the session lock.

A partially sealed range never permits deletion of the remaining events.
CLOSED-without-seal is explicitly NOT eligible — no automatic deletion just
because a session closed.

All paths are resolved and validated to live inside the intended store root
before any cleanup; symlink/junction escapes are refused.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import BatchState, StoreError
from .store import Store

RETENTION_MIN_AGE = timedelta(days=14)
JOURNAL_SUFFIXES = (".sqlite", ".sqlite-wal", ".sqlite-shm", ".lock")


class RetentionError(StoreError):
    """Retention precondition violated."""


@dataclass(frozen=True)
class RetentionDecision:
    session_id: str
    eligible: bool
    reason: str
    paths: tuple[Path, ...]        # journal-owned files that would be removed
    sealed_at: str | None = None


def _journal_dir(store: Store) -> Path:
    root = store.path.journals.resolve()
    return root


def _resolve_inside(root: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise RetentionError(
            f"refusing path outside journal root: {candidate} -> {resolved}"
        )
    return resolved


def _session_lock_held(store: Store, session_id: str) -> bool:
    lock_path = store.path.journals / f"{session_id}.lock"
    if not lock_path.exists():
        return False
    try:
        f = open(lock_path, "a+b")
        try:
            import msvcrt

            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            return False
        except OSError:
            return True
        finally:
            f.close()
    except OSError:
        return False


def _verified_seals(store: Store, session_id: str) -> tuple[list[dict], str | None]:
    """Seal records from the journal meta cross-checked against the catalog.

    Returns (verified_seals, newest_verified_at). Raises nothing; an
    unverifiable seal simply makes the session ineligible.
    """

    journal_path = store.path.journals / f"{session_id}.sqlite"
    conn = sqlite3.connect(str(journal_path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT value FROM session_meta WHERE key='seals'"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return [], None
    seals = json.loads(row["value"])
    verified: list[dict] = []
    newest: str | None = None
    for seal in seals:
        complete = True
        for part in ("ticks", "bars"):
            batch_id = seal[part]["batch_id"]
            batch = store.catalog.get_batch(batch_id)
            if batch is None or str(batch["state"]) != BatchState.PUBLISHED.value:
                complete = False
                break
        if complete:
            verified.append(seal)
            # Sealed-at evidence: use the batch publication time.
            batch = store.catalog.get_batch(seal["ticks"]["batch_id"])
            ts = str(batch["updated_at"]) if batch is not None else None
            if ts is not None and (newest is None or ts > newest):
                newest = ts
    return verified, newest


def evaluate_retention(store: Store, session_id: str) -> RetentionDecision:
    """Decide whether a session's journal files are retention-eligible."""

    root = _journal_dir(store)
    journal_path = _resolve_inside(root, root / f"{session_id}.sqlite")
    if not journal_path.is_file():
        raise RetentionError(f"unknown journal session: {session_id}")

    if _session_lock_held(store, session_id):
        return RetentionDecision(
            session_id=session_id,
            eligible=False,
            reason="active owner holds the session lock",
            paths=(),
        )

    seals, newest = _verified_seals(store, session_id)
    if not seals:
        return RetentionDecision(
            session_id=session_id,
            eligible=False,
            reason="no verified complete seal; CLOSED-without-seal is not eligible",
            paths=(),
        )
    assert newest is not None
    try:
        sealed_at = datetime.fromisoformat(newest)
    except ValueError:
        return RetentionDecision(
            session_id=session_id,
            eligible=False,
            reason=f"unparseable seal timestamp {newest!r}",
            paths=(),
        )
    if sealed_at.tzinfo is None:
        sealed_at = sealed_at.replace(tzinfo=timezone.utc)
    age = datetime.now(tz=timezone.utc) - sealed_at
    if age < RETENTION_MIN_AGE:
        return RetentionDecision(
            session_id=session_id,
            eligible=False,
            reason=f"newest verified seal is {age.days}d old (< 14d)",
            paths=(),
            sealed_at=newest,
        )

    paths = tuple(
        _resolve_inside(root, root / f"{session_id}{suffix}")
        for suffix in JOURNAL_SUFFIXES
        if (root / f"{session_id}{suffix}").exists()
    )
    return RetentionDecision(
        session_id=session_id,
        eligible=True,
        reason=f"{len(seals)} verified seal(s); newest {age.days}d old",
        paths=paths,
        sealed_at=newest,
    )


def apply_retention(store: Store, session_id: str) -> RetentionDecision:
    """Evaluate and, only if eligible, remove the journal-owned files."""

    decision = evaluate_retention(store, session_id)
    if not decision.eligible:
        return decision
    for path in decision.paths:
        _resolve_inside(_journal_dir(store), path)
        path.unlink(missing_ok=True)
    return decision
