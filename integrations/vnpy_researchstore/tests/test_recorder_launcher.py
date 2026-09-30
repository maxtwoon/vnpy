"""Launcher entry-point tests for ``vnpy_researchstore.launcher``.

These exercise the SAME module shipped in the wheel (console script
``vnpy-recorder`` / ``python -m vnpy_researchstore``): bootstrap ordering,
vnpy origin refusal, ``--status`` JSON snapshot, and the ``--stop``
barrier-close flow INCLUDING the binding failed-stop contract: a failed
stop must NOT exit the process, NOT stop the event engine, and NOT close
the parent. Interactive input lines retry the SAME accepted cutoff; when
stdin is unavailable (EOF), the launcher itself keeps issuing the same
public retries in a visible, individually bounded series with backoff
until the journal durably reports committed==cutoff CLOSED (production EOF
retry — an earlier park-only generation was rejected because liveness is
not a usable retry controller).

All offline, simulated/test labelled, task-owned temp runtime dirs only;
no gateway/account/network is touched. The subprocess test uses an
external deadline and reclaims ONLY its own isolated child (test-only
cleanup, never production behavior).
"""

from __future__ import annotations

import builtins
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_store import init_store  # noqa: E402
from vnpy_researchstore.launcher import (  # noqa: E402
    bootstrap_runtime,
    main,
)

SUBPROCESS_DEADLINE_S = 40


def _write_config(tmp_path: Path, store_root: Path, **overrides) -> Path:
    raw: dict[str, object] = {
        "store_root": str(store_root),
        "runtime_dir": str(tmp_path / "runtime"),
        "repo_path": str(REPO_ROOT),
        "source_id": "sim-test",
        "source_kind": "simulated",
        # Revised 02I grammar: timezone-only display evidence, never a
        # trading-calendar claim.
        "calendar_spec": "tz:Asia/Shanghai",
        "instruments": [{"symbol": "rb2501", "exchange": "SHFE"}],
        "event_kinds": ["tick"],
        "gateway_type": "ctp",
    }
    raw.update(overrides)
    path = tmp_path / "recorder.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


@pytest.fixture()
def launcher_store(tmp_path: Path):
    """Initialized store (kept open, like the other suites' ``store``
    fixture; the launcher opens its own handle)."""

    s = init_store(tmp_path / "store")
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def _restore_cwd():
    cwd = os.getcwd()
    yield
    os.chdir(cwd)


def test_bootstrap_runtime_pins_repo_origin(tmp_path, _restore_cwd) -> None:
    runtime = tmp_path / "runtime"
    vnpy_file = bootstrap_runtime(str(REPO_ROOT), str(runtime))
    assert Path(REPO_ROOT) in vnpy_file.parents
    assert (runtime / ".vntrader").is_dir()
    assert Path.cwd() == runtime.resolve()


def test_bootstrap_runtime_refuses_foreign_vnpy(
    tmp_path, monkeypatch, _restore_cwd
) -> None:
    """A vnpy module resolving OUTSIDE the configured repo path must abort."""

    fake = tmp_path / "fakevnpy"
    fake.mkdir()
    (fake / "vnpy.py").write_text("__version__ = '0'\n", encoding="utf-8")
    # Registering the current entry (module or absent) guarantees restore.
    monkeypatch.setitem(sys.modules, "vnpy", sys.modules.get("vnpy"))
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # noqa: ANN002, ANN003
        if name == "vnpy":
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "vnpy", fake / "vnpy.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            sys.modules["vnpy"] = module
            return module
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(SystemExit, match="not under the configured repo"):
        bootstrap_runtime(str(tmp_path / "elsewhere"), str(tmp_path / "rt2"))


def test_launcher_status_json(
    tmp_path, launcher_store, capsys, _restore_cwd
) -> None:
    config = _write_config(tmp_path, launcher_store.root)
    code = main(["--config", str(config), "--status"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "IDLE"
    assert payload["source_kind"] == "simulated"
    assert payload["instruments"] == ["rb2501.SHFE"]
    assert payload["session_id"] is None


def test_launcher_stop_flow_barrier_close(
    tmp_path, launcher_store, capsys, monkeypatch, _restore_cwd
) -> None:
    """``--stop`` starts, 'waits' for Enter (stubbed), then barrier-closes."""

    config = _write_config(tmp_path, launcher_store.root)
    monkeypatch.setattr(builtins, "input", lambda *_: "")
    code = main(["--config", str(config), "--stop"])
    assert code == 0
    docs = [
        d for d in _json_docs(capsys.readouterr().out) if "result" in d
    ]
    assert len(docs) == 1
    payload = docs[0]
    assert payload["result"] == "CLOSED"
    assert payload["accepted_seq"] == 0
    assert payload["committed_seq"] == 0


def _json_docs(text: str) -> list[dict]:
    """Decode every whitespace-separated JSON document printed on stdout."""

    decoder = json.JSONDecoder()
    docs: list[dict] = []
    idx = 0
    while idx < len(text):
        if text[idx] != "{":
            idx += 1
            continue
        obj, end = decoder.raw_decode(text, idx)
        docs.append(obj)
        idx = end
    return docs


def test_launcher_failed_stop_forbids_exit_and_retries_same_cutoff(
    tmp_path, launcher_store, capsys, monkeypatch, _restore_cwd
) -> None:
    """B1 regression: a failed stop must NOT hard-exit, NOT stop the event
    engine, and NOT close the parent. The launcher retries the SAME fixed
    cutoff; only after committed==cutoff CLOSED may the parent close run.

    Historical failure coverage: the earlier generations violated this with
    a direct ``EventEngine.stop`` and then a renamed ``os._exit(2)``
    "operator abort" (both observed and rejected by the coordinator; the
    pre-fix behavior is additionally captured by
    ``test_launcher_stdin_eof_parks_never_self_exits``).
    """

    from vnpy.event import EventEngine
    from vnpy.trader.engine import MainEngine
    from research_store.journal import JournalSession

    config = _write_config(tmp_path, launcher_store.root)
    original_close = JournalSession.close_at_cutoff
    original_retry = JournalSession.retry_close
    calls: list[str] = []
    attempts = {"n": 0}

    def tracked_close(self, *, timeout=10.0):  # noqa: ANN001, ANN202
        attempts["n"] += 1
        calls.append(f"close_attempt:{attempts['n']}")
        if attempts["n"] == 1:
            return original_close(self, timeout=0.001)  # bounded failure
        return original_close(self, timeout=timeout)

    def tracked_retry(self, *, timeout=10.0):  # noqa: ANN001, ANN202
        # The launcher's retry path MUST go through the journal's public
        # retry_close (same fixed cutoff), never a fresh close.
        calls.append("retry_attempt:2")
        return original_retry(self, timeout=timeout)

    def forbidden_os_exit(code):  # noqa: ANN001
        calls.append("os._exit")
        raise AssertionError(
            f"forbidden os._exit({code}) on a failed stop (B1 violation)"
        )

    real_engine_stop = EventEngine.stop

    def tracked_engine_stop(self):  # noqa: ANN001
        calls.append("engine_stop")
        return real_engine_stop(self)

    real_parent_close = MainEngine.close

    def tracked_parent_close(self):  # noqa: ANN001
        calls.append("parent_close")
        return real_parent_close(self)

    monkeypatch.setattr(JournalSession, "close_at_cutoff", tracked_close)
    monkeypatch.setattr(JournalSession, "retry_close", tracked_retry)
    monkeypatch.setattr(os, "_exit", forbidden_os_exit)
    monkeypatch.setattr(EventEngine, "stop", tracked_engine_stop)
    monkeypatch.setattr(MainEngine, "close", tracked_parent_close)

    answers = iter(["", ""])  # first Enter: stop; second: retry SAME cutoff

    def scripted_input(*_args):  # noqa: ANN002
        try:
            return next(answers)
        except StopIteration as exc:  # a third prompt would mean an extra
            raise AssertionError(  # stop attempt outside the script
                "launcher prompted more times than scripted"
            ) from exc

    monkeypatch.setattr(builtins, "input", scripted_input)
    code = main(["--config", str(config), "--stop"])
    monkeypatch.undo()

    # Exact ordering: one bounded close failure, one public retry_close
    # against the SAME cutoff, then — and only then — the parent close and
    # engine stop inside the successful close. NO os._exit, NO engine stop,
    # and NO parent close at any point while the stop is failed.
    assert calls == [
        "close_attempt:1",
        "retry_attempt:2",
        "parent_close",
        "engine_stop",
    ], calls
    assert code == 0
    docs = _json_docs(capsys.readouterr().out)
    results = [d["result"] for d in docs if "result" in d]
    assert results == ["STOP_FAILED", "CLOSED"], results
    closed_doc = docs[-1]

    # Journal truth: the session durably reached CLOSED at the SAME cutoff
    # (committed == accepted), not merely an OPEN leftover.
    journals = launcher_store.path.journals
    session_ids = [p.stem for p in journals.glob("sess-*.sqlite")]
    assert len(session_ids) == 1, session_ids
    import sqlite3

    conn = sqlite3.connect(str(journals / f"{session_ids[0]}.sqlite"))
    try:
        state = conn.execute(
            "SELECT value FROM session_meta WHERE key='state'"
        ).fetchone()[0]
        watermark = conn.execute(
            "SELECT committed_seq FROM watermark"
        ).fetchone()[0]
    finally:
        conn.close()
    assert state == "CLOSED"
    assert watermark == closed_doc["accepted_seq"] == closed_doc["committed_seq"]


def test_launcher_stdin_eof_runs_normal_stop_and_closes(
    tmp_path, launcher_store, _restore_cwd
) -> None:
    """Subprocess regression: initial stdin EOF still requests the NORMAL
    barrier stop through the original controller, and an empty session
    closes on the first attempt — exit 0, journal durably CLOSED. External
    deadline bounds the child; the harness reclaims only its own child.
    """

    work = tmp_path / "sub"
    work.mkdir()
    config = _write_config(work, launcher_store.root)
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(ROOT), str(REPO_ROOT)]),
        # Offscreen BEFORE any import (no Qt in --stop; belt and braces).
        "QT_QPA_PLATFORM": "offscreen",
    }
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "vnpy_researchstore",
            "--config", str(config), "--stop",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(work),
        env=env,
    )
    try:
        out, err = proc.communicate(timeout=SUBPROCESS_DEADLINE_S)
    except subprocess.TimeoutExpired:
        proc.kill()  # reclaim ONLY this harness-owned child
        out, err = proc.communicate()
        pytest.fail(
            "launcher did not complete the normal stop after EOF within "
            f"{SUBPROCESS_DEADLINE_S}s: "
            f"{(out + err).decode('utf-8', 'replace')[-500:]}"
        )
    detail = (out + err).decode("utf-8", "replace")
    assert proc.returncode == 0, detail[-500:]
    assert '"result": "CLOSED"' in detail
    assert "running the normal stop-barrier close" in detail
    journals = launcher_store.path.journals
    session_ids = [p.stem for p in journals.glob("sess-*.sqlite")]
    assert len(session_ids) == 1, session_ids
    import sqlite3

    conn = sqlite3.connect(str(journals / f"{session_ids[0]}.sqlite"))
    try:
        state = conn.execute(
            "SELECT value FROM session_meta WHERE key='state'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert state == "CLOSED"


def test_launcher_eof_failed_stop_auto_retries_same_cutoff_closed(
    tmp_path, launcher_store, capsys, monkeypatch, _restore_cwd
) -> None:
    """Bounded production EOF retry regression (actual controller).

    stdin is unavailable from the start (EOF everywhere); the FIRST barrier
    stop is forced to fail by a temporarily unavailable writer condition;
    once that condition recovers, the launcher's OWN visible retry series —
    through the original engine barrier and the journal's public
    ``retry_close`` against the SAME accepted cutoff — must reach CLOSED
    with the normal parent close. No os._exit, no engine stop, and no
    parent close before CLOSED, and no test-only wake event anywhere.
    """

    from vnpy.event import EventEngine
    from vnpy.trader.engine import MainEngine
    from research_store.journal import JournalSession

    config = _write_config(tmp_path, launcher_store.root)
    original_close = JournalSession.close_at_cutoff
    original_retry = JournalSession.retry_close
    calls: list[str] = []
    close_attempts = {"n": 0}

    def flaky_close(self, *, timeout=10.0):  # noqa: ANN001, ANN202
        close_attempts["n"] += 1
        calls.append(f"close_attempt:{close_attempts['n']}")
        if close_attempts["n"] == 1:
            # Writer condition temporarily unavailable: bounded failure.
            return original_close(self, timeout=0.001)
        return original_close(self, timeout=timeout)

    def tracked_retry(self, *, timeout=10.0):  # noqa: ANN001, ANN202
        calls.append("retry_close")
        return original_retry(self, timeout=timeout)

    def forbidden_os_exit(code):  # noqa: ANN001
        calls.append("os._exit")
        raise AssertionError(
            f"forbidden os._exit({code}) on a failed stop (B1 violation)"
        )

    real_engine_stop = EventEngine.stop

    def tracked_engine_stop(self):  # noqa: ANN001
        calls.append("engine_stop")
        return real_engine_stop(self)

    real_parent_close = MainEngine.close

    def tracked_parent_close(self):  # noqa: ANN001
        calls.append("parent_close")
        return real_parent_close(self)

    monkeypatch.setattr(JournalSession, "close_at_cutoff", flaky_close)
    monkeypatch.setattr(JournalSession, "retry_close", tracked_retry)
    monkeypatch.setattr(os, "_exit", forbidden_os_exit)
    monkeypatch.setattr(EventEngine, "stop", tracked_engine_stop)
    monkeypatch.setattr(MainEngine, "close", tracked_parent_close)

    def always_eof(*_args):  # noqa: ANN002 — closed stdin for every prompt
        raise EOFError

    monkeypatch.setattr(builtins, "input", always_eof)
    code = main(["--config", str(config), "--stop"])
    monkeypatch.undo()

    # Exact ordering: the bounded failed stop, the launcher's own automatic
    # retry against the SAME cutoff, and only then parent close + engine
    # stop inside the successful close. No os._exit anywhere.
    assert calls == [
        "close_attempt:1",
        "retry_close",
        "parent_close",
        "engine_stop",
    ], calls
    assert code == 0
    docs = [
        d for d in _json_docs(capsys.readouterr().out) if "result" in d
    ]
    assert [d["result"] for d in docs] == ["STOP_FAILED", "CLOSED"]
    closed = docs[-1]
    assert closed["accepted_seq"] == closed["committed_seq"]

    journals = launcher_store.path.journals
    session_ids = [p.stem for p in journals.glob("sess-*.sqlite")]
    assert len(session_ids) == 1, session_ids
    import sqlite3

    conn = sqlite3.connect(str(journals / f"{session_ids[0]}.sqlite"))
    try:
        state = conn.execute(
            "SELECT value FROM session_meta WHERE key='state'"
        ).fetchone()[0]
        watermark = conn.execute(
            "SELECT committed_seq FROM watermark"
        ).fetchone()[0]
    finally:
        conn.close()
    assert state == "CLOSED"
    assert watermark == closed["accepted_seq"]
