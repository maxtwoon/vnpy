"""Focused tests: recording sessions visible in the public store report.

Covers the coordinator-released bounded fix in ``research_store/report.py``:
durable journal-only sessions must be visible, catalog-only historical
sessions retained honestly (missing journal = error), duplicate session ids
reconciled with journal authority, live in-memory counters null (never
inferred zero), unreadable/partial journals visible as errors, read-only
reporting that does not mutate closed journals, and escaped HTML rendering
of actual status/watermarks/errors.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from research_store import init_store
from research_store.journal import create_session
from research_store.journal_models import JournalEvent
from research_store.report import build_report, render_html

SOURCE_SPEC = "futures:synthetic-report-probe@v1"
CALENDAR_SPEC = "tz:Asia/Shanghai"


def _admit_one_and_close(store, session) -> None:
    session.admit(
        JournalEvent(
            kind="tick",
            instrument="IF2403.CFFEX",
            event_ts_ns=1_700_000_000_000_000_000,
            source_event_id="synthetic-1",
            payload={"last_price": 3800.0, "volume": 1.0, "turnover": 3800.0},
        )
    )
    stopped = session.close_at_cutoff(timeout=5.0)
    assert stopped.state.value == "CLOSED"
    session.close()


def _find(recording: dict, session_id: str) -> dict:
    matches = [s for s in recording["sessions"] if s["session_id"] == session_id]
    assert len(matches) == 1, f"expected exactly one entry for {session_id}"
    return matches[0]


def _journal_hash(journal_path: Path) -> str:
    return hashlib.sha256(journal_path.read_bytes()).hexdigest()


def test_journal_only_session_visible_with_watermark(tmp_path: Path) -> None:
    store = init_store(tmp_path / "store")
    try:
        session = create_session(store, SOURCE_SPEC, CALENDAR_SPEC)
        sid = session.session_id
        _admit_one_and_close(store, session)
        report = build_report(store)
        recording = report["recording"]
        assert recording["status"] == "sessions_present"
        entry = _find(recording, sid)
        assert entry["authority"] == "journal"
        assert entry["status"] == "CLOSED"
        assert entry["durable_state"] == "CLOSED"
        assert entry["committed_seq"] == 1
        assert entry["durable_last_seq"] == 1
        assert entry["catalog_status"] is None
        assert entry["error"] is None
        assert recording["counts"]["journal_sessions"] == 1
        assert recording["counts"]["catalog_only_sessions"] == 0
    finally:
        store.close()


def test_report_read_does_not_mutate_closed_journal(tmp_path: Path) -> None:
    store = init_store(tmp_path / "store")
    try:
        session = create_session(store, SOURCE_SPEC, CALENDAR_SPEC)
        journal_path = store.path.journals / f"{session.session_id}.sqlite"
        _admit_one_and_close(store, session)
        before = _journal_hash(journal_path)
        files_before = {
            p.name: _journal_hash(p)
            for p in store.path.journals.iterdir()
            if p.is_file()
        }
        build_report(store)
        build_report(store)
        # the durable journal content is byte-identical after read-only report
        assert _journal_hash(journal_path) == before
        # no pre-existing file was modified or deleted; SQLite may create
        # empty read sidecars (-wal/-shm) for a WAL database, which are not
        # journal mutations (disclosed in report.py docstring)
        for name, digest in files_before.items():
            path = store.path.journals / name
            assert path.is_file(), f"file disappeared: {name}"
            if not name.endswith(("-wal", "-shm")):
                assert _journal_hash(path) == digest, f"file changed: {name}"
        created = set(p.name for p in store.path.journals.iterdir()) - set(files_before)
        assert all(name.endswith(("-wal", "-shm")) for name in created), created
    finally:
        store.close()


def test_catalog_only_session_retained_with_missing_journal_error(
    tmp_path: Path,
) -> None:
    store = init_store(tmp_path / "store")
    try:
        store.catalog.upsert_recording_session(
            "sess-catalogonly",
            "sim:<stale&unescaped>",
            "tz:Elsewhere",
            str(tmp_path / "nowhere" / "sess-catalogonly.sqlite"),
            "CLOSED",
            None,
            "2026-09-30T00:00:00+00:00",
            "2026-09-30T00:00:00+00:00",
        )
        report = build_report(store)
        recording = report["recording"]
        assert recording["status"] == "sessions_present"
        entry = _find(recording, "sess-catalogonly")
        assert entry["authority"] == "catalog_only"
        assert entry["status"] == "CLOSED"
        assert entry["catalog_status"] == "CLOSED"
        assert entry["committed_seq"] is None
        assert entry["durable_state"] is None
        assert entry["error"] is not None
        assert "journal file missing" in entry["error"]
        assert recording["counts"]["catalog_only_sessions"] == 1
    finally:
        store.close()


def test_duplicate_session_reconciled_with_journal_authority(tmp_path: Path) -> None:
    store = init_store(tmp_path / "store")
    try:
        session = create_session(store, SOURCE_SPEC, CALENDAR_SPEC)
        sid = session.session_id
        _admit_one_and_close(store, session)
        # stale catalog row claiming OPEN for the same session id
        store.catalog.upsert_recording_session(
            sid,
            SOURCE_SPEC,
            CALENDAR_SPEC,
            str(store.path.journals / f"{sid}.sqlite"),
            "OPEN",
            None,
            "2026-09-30T00:00:00+00:00",
            "2026-09-30T00:00:01+00:00",
        )
        report = build_report(store)
        entry = _find(report["recording"], sid)
        assert entry["authority"] == "journal"
        assert entry["durable_state"] == "CLOSED"
        assert entry["status"] == "CLOSED", "journal authority must win"
        assert entry["catalog_status"] == "OPEN", "catalog status stays visible"
        assert report["recording"]["counts"]["journal_sessions"] == 1
        assert report["recording"]["counts"]["catalog_only_sessions"] == 0
    finally:
        store.close()


def test_unreadable_journal_visible_as_error(tmp_path: Path) -> None:
    store = init_store(tmp_path / "store")
    try:
        session = create_session(store, SOURCE_SPEC, CALENDAR_SPEC)
        good_sid = session.session_id
        _admit_one_and_close(store, session)
        broken = store.path.journals / "sess-broken.sqlite"
        broken.write_bytes(b"definitely not a sqlite database" * 8)
        report = build_report(store)
        recording = report["recording"]
        entry = _find(recording, "sess-broken")
        assert entry["authority"] == "journal"
        assert entry["status"] == "unreadable_journal"
        assert entry["error"] is not None
        assert "unreadable journal" in entry["error"]
        assert entry["committed_seq"] is None
        # the healthy session is still reported alongside
        assert _find(recording, good_sid)["status"] == "CLOSED"
        assert recording["counts"]["sessions_with_errors"] == 1
    finally:
        store.close()


def test_partial_legacy_journal_visible_not_omitted(tmp_path: Path) -> None:
    store = init_store(tmp_path / "store")
    try:
        legacy = store.path.journals / "sess-legacy.sqlite"
        conn = sqlite3.connect(str(legacy))
        try:
            conn.execute(
                "CREATE TABLE watermark (committed_seq INTEGER NOT NULL)"
            )
            conn.execute("INSERT INTO watermark (committed_seq) VALUES (3)")
            conn.commit()
        finally:
            conn.close()
        report = build_report(store)
        entry = _find(report["recording"], "sess-legacy")
        assert entry["authority"] == "journal"
        assert entry["status"] == "unknown_journal_format"
        assert entry["committed_seq"] == 3
        assert entry["error"] is not None
        assert "no session_id metadata" in entry["error"]
    finally:
        store.close()


def test_successor_lineage_from_durable_predecessor(tmp_path: Path) -> None:
    store = init_store(tmp_path / "store")
    try:
        first = create_session(store, SOURCE_SPEC, CALENDAR_SPEC)
        first_sid = first.session_id
        _admit_one_and_close(store, first)
        second = create_session(
            store, SOURCE_SPEC, CALENDAR_SPEC, predecessor_session_id=first_sid
        )
        second_sid = second.session_id
        _admit_one_and_close(store, second)
        report = build_report(store)
        first_entry = _find(report["recording"], first_sid)
        second_entry = _find(report["recording"], second_sid)
        assert first_entry["successor_session_ids"] == [second_sid]
        assert second_entry["predecessor_session_id"] == first_sid
    finally:
        store.close()


def test_catalog_only_root_parent_gets_durable_child_successor(
    tmp_path: Path,
) -> None:
    """Root lineage repro: catalog-only parent (no journal, no predecessor)
    must still gain its durable child via successor lineage."""

    store = init_store(tmp_path / "store")
    try:
        store.catalog.upsert_recording_session(
            "sess-historical-parent",
            "sim:test@v1",
            "tz:Asia/Shanghai",
            str(tmp_path / "missing.sqlite"),
            "CLOSED",
            None,
            "2026-09-30T00:00:00+00:00",
            "2026-09-30T00:00:00+00:00",
        )
        child = create_session(
            store,
            SOURCE_SPEC,
            CALENDAR_SPEC,
            predecessor_session_id="sess-historical-parent",
        )
        child_sid = child.session_id
        _admit_one_and_close(store, child)
        report = build_report(store)
        parent = _find(report["recording"], "sess-historical-parent")
        child_entry = _find(report["recording"], child_sid)
        assert parent["successor_session_ids"] == [child_sid]
        assert child_entry["predecessor_session_id"] == "sess-historical-parent"
        # the parent is still honestly catalog-only with its missing journal
        assert parent["authority"] == "catalog_only"
        assert parent["error"] is not None
        assert report["recording"]["counts"] == {
            "journal_sessions": 1,
            "catalog_only_sessions": 1,
            "sessions_with_errors": 1,
        }
    finally:
        store.close()


def test_nonroot_parent_lists_children_not_siblings(tmp_path: Path) -> None:
    """A non-root parent (it has its own predecessor) must list its CHILDREN
    (sessions naming it as predecessor), never its siblings."""

    store = init_store(tmp_path / "store")
    try:
        for sid in ("sess-grandparent", "sess-parent"):
            store.catalog.upsert_recording_session(
                sid,
                "sim:test@v1",
                "tz:Asia/Shanghai",
                str(tmp_path / f"{sid}.sqlite"),
                "CLOSED",
                "sess-grandparent" if sid == "sess-parent" else None,
                "2026-09-30T00:00:00+00:00",
                "2026-09-30T00:00:00+00:00",
            )
        child_of_parent = create_session(
            store, SOURCE_SPEC, CALENDAR_SPEC, predecessor_session_id="sess-parent"
        )
        _admit_one_and_close(store, child_of_parent)
        child_of_grandparent = create_session(
            store,
            SOURCE_SPEC,
            CALENDAR_SPEC,
            predecessor_session_id="sess-grandparent",
        )
        _admit_one_and_close(store, child_of_grandparent)
        report = build_report(store)
        grandparent = _find(report["recording"], "sess-grandparent")
        parent = _find(report["recording"], "sess-parent")
        c1 = _find(report["recording"], child_of_parent.session_id)
        c2 = _find(report["recording"], child_of_grandparent.session_id)
        # the grandparent's children are BOTH the durable child and the
        # catalog-only parent (which names it as predecessor); the parent
        # lists only ITS child, never its sibling c2
        assert grandparent["successor_session_ids"] == sorted(
            [child_of_grandparent.session_id, "sess-parent"]
        )
        assert parent["successor_session_ids"] == [child_of_parent.session_id]
        assert c1["predecessor_session_id"] == "sess-parent"
        assert c2["predecessor_session_id"] == "sess-grandparent"
        assert parent["predecessor_session_id"] == "sess-grandparent"
    finally:
        store.close()


def test_live_counters_null_never_inferred_zero(tmp_path: Path) -> None:
    store = init_store(tmp_path / "store")
    try:
        session = create_session(store, SOURCE_SPEC, CALENDAR_SPEC)
        sid = session.session_id
        _admit_one_and_close(store, session)
        entry = _find(build_report(store)["recording"], sid)
        assert entry["accepted_seq"] is None
        assert entry["backlog"] is None
        assert entry["rejected"] is None
        assert entry["errors"] is None
        assert "never inferred zero" in entry["counters_note"]
    finally:
        store.close()


def test_html_escapes_recording_status_watermarks_errors(tmp_path: Path) -> None:
    store = init_store(tmp_path / "store")
    try:
        store.catalog.upsert_recording_session(
            "sess-htmlonly",
            "sim:<script>alert(1)</script>",
            "tz:<b>",
            str(tmp_path / "nope.sqlite"),
            "CLOSED",
            None,
            "2026-09-30T00:00:00+00:00",
            "2026-09-30T00:00:00+00:00",
        )
        report = build_report(store)
        html = render_html(report)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert "&lt;b&gt;" in html
        # actual durable facts rendered for journal sessions too
        session = create_session(store, SOURCE_SPEC, CALENDAR_SPEC)
        _admit_one_and_close(store, session)
        html = render_html(build_report(store))
        assert "CLOSED" in html
        assert "sessions_present" in html
        # null live counters render as explicit UNKNOWN, never blank
        assert ">UNKNOWN</td>" in html
    finally:
        store.close()


def test_no_sessions_still_reported_faithfully(tmp_path: Path) -> None:
    store = init_store(tmp_path / "store")
    try:
        report = build_report(store)
        recording = report["recording"]
        assert recording["status"] == "no_recording_sessions"
        assert recording["sessions"] == []
        assert recording["counts"] == {
            "journal_sessions": 0,
            "catalog_only_sessions": 0,
            "sessions_with_errors": 0,
        }
    finally:
        store.close()
