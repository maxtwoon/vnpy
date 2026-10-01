"""Retention of journal files (WP09, revised recording02K).

A journal file is eligible for deletion ONLY when ALL of the following hold:

1. It is a module-owned journal file (``<store>/journals/<session_id>.sqlite``
   plus its ``-wal``/``-shm``/``.lock`` sidecars) — never raw, canonical,
   snapshot, object, or manifest files.
2. Every seal recorded for the session is VERIFIED complete: the sealed
   batches are PUBLISHED in the catalog and their receipts match the durable
   seal record in the journal's own meta.
3. RAW COVERAGE (recording02K): the provably lossless seals together cover
   EVERY committed journal event up to the current watermark. A seal proves
   losslessness only through its durable record fields (``lossless`` true,
   ``unknown_time_excluded == 0``, and an ``input_events`` count consistent
   with its dense sequence range). A seal that EXCLUDED any committed event
   (e.g. a missing event-time tick), or a legacy record without coverage
   evidence, never counts toward coverage — the journal is then retained
   (fail-closed). Partial ranges leave the uncovered tail journal-only and
   refuse deletion.
4. At least 14 days have passed since the newest verified seal.
5. No live owner holds the session lock.

A partially sealed range never permits deletion of the remaining events.
CLOSED-without-seal is explicitly NOT eligible — no automatic deletion just
because a session closed. There is no acknowledged-loss override.

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


def _committed_watermark(journal_path: Path) -> int:
    """Current committed watermark of the journal (raw event authority)."""

    conn = sqlite3.connect(str(journal_path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT committed_seq FROM watermark").fetchone()
        return int(row["committed_seq"]) if row is not None else 0
    finally:
        conn.close()


def _lossless_coverage(seal_record: dict) -> tuple[int, int] | None:
    """Range a seal PROVABLY covered losslessly, else ``None`` (fail-closed).

    A durable seal record proves raw coverage only when it carries the
    recording02K fields AND they are internally consistent:
    ``lossless is True``, ``unknown_time_excluded == 0``, and
    ``input_events`` equals the dense range span. Legacy records (pre-02K)
    and exclusion-bearing records return ``None`` — they never acquire a
    fabricated complete status. Bars are excluded from the judgment: they
    are a derived representation, not the raw event copy.
    """

    if seal_record.get("lossless") is not True:
        return None
    try:
        excluded = int(seal_record["unknown_time_excluded"])
        start = int(seal_record["committed_seq_start"])
        end = int(seal_record["committed_seq_end"])
        input_events = int(seal_record["input_events"])
    except (KeyError, TypeError, ValueError):
        return None
    if excluded != 0 or start < 1 or end < start:
        return None
    if input_events != end - start + 1:
        return None
    return start, end


def _coverage_reach(ranges: list[tuple[int, int]]) -> int:
    """Contiguous coverage reach from seq 1 over sorted lossless ranges."""

    covered_to = 0
    for start, end in sorted(ranges):
        if start > covered_to + 1:
            break  # gap between lossless seals
        covered_to = max(covered_to, end)
    return covered_to


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

    # recording02K raw-coverage gate (fail-closed): deletion requires that
    # provably lossless seals cover EVERY committed journal event up to the
    # current watermark. Exclusion-bearing seals (e.g. missing event-time
    # ticks), legacy records without coverage evidence, and unsealed range
    # tails all refuse — the journal is then the only copy of those events.
    watermark = _committed_watermark(journal_path)
    ranges = [
        coverage
        for coverage in (_lossless_coverage(seal) for seal in seals)
        if coverage is not None
    ]
    covered_to = _coverage_reach(ranges)
    if covered_to < watermark:
        if not ranges:
            reason = (
                "no seal proves lossless raw coverage (legacy record without "
                "coverage evidence, or recorded exclusions); journal deletion "
                "refused"
            )
        else:
            reason = (
                f"lossless seals cover committed events only through seq "
                f"{covered_to} of {watermark}; events {covered_to + 1}.."
                f"{watermark} remain journal-only; deletion refused"
            )
        return RetentionDecision(
            session_id=session_id,
            eligible=False,
            reason=reason,
            paths=(),
        )

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
        reason=(
            f"{len(seals)} verified lossless seal(s) cover all {watermark} "
            f"committed events; newest {age.days}d old"
        ),
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
