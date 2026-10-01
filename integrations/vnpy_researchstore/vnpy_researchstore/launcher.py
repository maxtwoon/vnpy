"""Recorder launcher as a shipped package entry point.

This module is the packaged equivalent of the repo-run shim
``tools/recorder_launcher.py``: installed console scripts / ``python -m
vnpy_researchstore`` land here, so the installed entrypoint never relies on
unshipped source tools.

Bootstrap order (mandatory, unchanged from the 03C contract):

1. Parse the recorder config (``--config``); unknown keys are refused later by
   ``load_recorder_config``; ``repo_path`` / ``runtime_dir`` are read here.
2. Put the optional integration path (repo-run mode only) and the explicit
   vnpy repo path at the front of ``sys.path`` and ``chdir`` into the
   configured isolated runtime directory (creating ``runtime_dir/.vntrader``)
   BEFORE anything transitively imports ``vnpy.trader.utility`` — which pins
   ``TRADER_DIR`` at import time.
3. Import ``vnpy`` and assert its module file lives under the configured repo
   path (same version string does not prove same source).
4. Only then import ``vnpy_researchstore.app`` / ``.ui`` and start the
   configured app/engine. No gateway is connected; no strategy is loaded; no
   settings file is edited; the default ``~/.vntrader`` / SQLite database is
   never touched.

Usage::

    python -m vnpy_researchstore --config configs/recorder_simulated.json
    python -m vnpy_researchstore --config ... --status
    python -m vnpy_researchstore --config ... --stop

``--status`` verifies the probe never recorded (IDLE, no attached session,
no accepted work), prints one JSON status snapshot, performs the plain
parent close and exits (no Qt); attached work would be closed through the
binding protocol instead. ``--stop`` starts recording, waits for a console
line, then runs the binding stop protocol: on STOP_FAILED the parent close
and the event engine are NOT touched — each further input line retries the
SAME accepted cutoff until the journal durably reports committed==cutoff
CLOSED. stdin EOF is not an exit authorization: the launcher then issues
the same public retries itself in a visible, individually bounded series
with backoff (dispatch and journal writer keep running) until CLOSED. With
no flag the Qt status window opens (offscreen-capable via the normal Qt
platform env vars); if the Qt loop ever returns while RECORDING or
STOP_FAILED, a fresh status window is restored so the Retry control stays
usable — the launcher only exits after CLOSED (or a verified
never-recorded probe).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def bootstrap_runtime(
    repo_path: str, runtime_dir: str, *, integration_root: str | None = None
) -> Path:
    """Order-critical path/cwd setup; see module docstring.

    ``integration_root`` is only used by the repo-run shim (the source
    checkout is not present in an installed environment).
    """

    for path in (integration_root, str(Path(repo_path).resolve())):
        if path and path not in sys.path:
            sys.path.insert(0, path)
    runtime = Path(runtime_dir).resolve()
    (runtime / ".vntrader").mkdir(parents=True, exist_ok=True)
    os.chdir(runtime)
    import vnpy

    vnpy_file = Path(str(vnpy.__file__)).resolve()
    repo_root = Path(repo_path).resolve()
    if repo_root not in vnpy_file.parents:
        raise SystemExit(
            f"vnpy module origin {vnpy_file} is not under the configured repo "
            f"path {repo_root}; refusing to continue"
        )
    return vnpy_file


def _status_dict(app: object) -> dict[str, object]:
    snapshot = app.status()  # type: ignore[attr-defined]
    last = snapshot.last_admission
    return {
        "state": snapshot.state.value,
        "journal_state": snapshot.journal_state.value if snapshot.journal_state else None,
        "session_id": snapshot.session_id,
        "journal_path": snapshot.journal_path,
        "source_id": snapshot.source_id,
        "source_kind": snapshot.source_kind,
        "instruments": list(snapshot.instruments),
        "event_kinds": list(snapshot.event_kinds),
        "gateway_type": snapshot.gateway_type,
        "accepted_seq": snapshot.accepted_seq,
        "committed_seq": snapshot.committed_seq,
        "backlog": snapshot.backlog,
        "rejected": snapshot.rejected,
        "errors": snapshot.errors,
        "last_error_detail": snapshot.last_error_detail,
        "last_admission": (
            {
                "accepted": last.accepted,
                "assigned_seq": last.assigned_seq,
                "reason": last.reason,
                "vt_symbol": last.vt_symbol,
                "kind": last.kind,
            }
            if last
            else None
        ),
    }


def _stop_report_payload(report: object) -> dict[str, object]:
    return {
        "result": report.result.value,  # type: ignore[attr-defined]
        "session_id": report.session_id,  # type: ignore[attr-defined]
        "accepted_seq": report.accepted_seq,  # type: ignore[attr-defined]
        "committed_seq": report.committed_seq,  # type: ignore[attr-defined]
        "detail": report.detail,  # type: ignore[attr-defined]
    }


#: Backoff for the automatic retry series when stdin is unavailable (EOF).
#: Each attempt stays individually bounded by the journal close bound inside
#: the barrier; the backoff only spaces the attempts — never a busy spin.
EOF_RETRY_BACKOFF_START_S = 1.0
EOF_RETRY_BACKOFF_CAP_S = 5.0


def _verified_no_work(snapshot: object) -> bool:
    """True only for a status probe that never recorded: IDLE, no attached
    session, zero accepted and zero committed work."""

    return (
        snapshot.state.value == "IDLE"  # type: ignore[attr-defined]
        and snapshot.session_id is None  # type: ignore[attr-defined]
        and snapshot.accepted_seq == 0  # type: ignore[attr-defined]
        and snapshot.committed_seq == 0  # type: ignore[attr-defined]
    )


def _binding_stop_loop(app: object, *, first_prompt: bool) -> int:
    """Run the binding stop protocol until the SAME cutoff is CLOSED.

    Interactive control: every ``input()`` line is one public ``retry_stop``
    through the original engine barrier (same fixed accepted cutoff; the
    journal's ``retry_close`` re-attempts that exact cutoff). When stdin is
    unavailable (EOFError), the launcher itself keeps issuing the same
    public retries in a visible, individually bounded series with backoff —
    the event dispatch and the journal writer keep running and nothing is
    torn down before the journal durably reports committed==cutoff CLOSED.
    There is no hard exit, no silent success, and no unreachable wait: every
    attempt prints its truthful JSON report on stdout.
    """

    if first_prompt:
        try:
            input("recording; press Enter to run the stop-barrier close...")
        except EOFError:
            # Initial EOF still requests the NORMAL stop through the
            # barrier — it never skips or abandons the session.
            print(
                "stdin closed; running the normal stop-barrier close",
                file=sys.stderr,
            )
    report = app.stop_recording()  # type: ignore[attr-defined]
    backoff = EOF_RETRY_BACKOFF_START_S
    while report.result.value == "STOP_FAILED":
        print(
            json.dumps(_stop_report_payload(report), indent=2, sort_keys=True)
        )
        print(
            "STOP_FAILED: journal did not drain to the exact cutoff in "
            "time; parent close withheld. Press Enter to retry the SAME "
            "accepted cutoff now (stdin EOF: automatic bounded retries "
            "continue until committed==cutoff and CLOSED).",
            file=sys.stderr,
        )
        try:
            input()
        except EOFError:
            time.sleep(backoff)
            backoff = min(backoff * 2.0, EOF_RETRY_BACKOFF_CAP_S)
        report = app.retry_stop()  # type: ignore[attr-defined]
    print(
        json.dumps(_stop_report_payload(report), indent=2, sort_keys=True)
    )
    if report.result.value != "CLOSED":
        # NOT_RECORDING (already closed / never recording): truthful
        # nonzero through the NORMAL exit path only.
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vnpy_researchstore",
        description="research recorder launcher (isolated runtime, explicit repo binding)",
    )
    parser.add_argument("--config", required=True, help="recorder config JSON")
    parser.add_argument(
        "--status",
        action="store_true",
        help="print one JSON status snapshot and exit (no Qt)",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="start, wait for Enter, then run the stop-barrier close and exit",
    )
    args = parser.parse_args(argv)

    # (1) config first — repo_path/runtime_dir come from it. Resolve to an
    # absolute path NOW: the bootstrap chdirs into the isolated runtime dir,
    # so any later relative read would break. The integration root is this
    # package's parent when running from the source checkout; installed
    # environments rely on the packaged modules plus the explicit repo path.
    config_path = Path(args.config).resolve()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"recorder config {config_path} must be a JSON object")
    repo_path = str(raw.get("repo_path") or "D:/repo/vnpy")
    runtime_dir = str(raw.get("runtime_dir") or "")
    integration_root: str | None = None
    package_root = Path(__file__).resolve().parents[1]
    if (package_root / "pyproject.toml").is_file():
        # Source checkout (editable or direct path run): make the checkout
        # importable exactly like the historical tools/ shim did.
        integration_root = str(package_root)

    # (2)+(3) path selection, cwd isolation, vnpy origin assertion.
    vnpy_file = bootstrap_runtime(repo_path, runtime_dir, integration_root=integration_root)

    # (4) app/engine imports only after the environment is pinned.
    from vnpy_researchstore.app import ResearchRecorderApp, load_recorder_config

    config = load_recorder_config(config_path)
    app = ResearchRecorderApp(config)
    try:
        if args.status:
            snapshot = app.status()
            print(json.dumps(_status_dict(app), indent=2, sort_keys=True))
            if _verified_no_work(snapshot):
                # Verified: this probe never recorded, no journal session is
                # attached, and no work was accepted — the plain parent
                # close is safe and releases the engine.
                app.stop_recording()
                return 0
            # Defensive: a status probe cannot start recording in-process,
            # so attached work here means the process was reconfigured
            # mid-flight. Close it through the binding protocol — never a
            # teardown skip, never a silent success.
            print(
                "status probe found attached work; closing it through the "
                "binding stop protocol",
                file=sys.stderr,
            )
            return _binding_stop_loop(app, first_prompt=False)
        session_id = app.start_recording()
        print(f"recording session {session_id} (vnpy={vnpy_file})")
        if args.stop:
            return _binding_stop_loop(app, first_prompt=True)
        # Qt status window (offscreen-capable via QT_QPA_PLATFORM).
        from vnpy.trader.ui import create_qapp

        from vnpy_researchstore.ui import RecorderStatusWindow

        qapp = create_qapp()
        window = RecorderStatusWindow.create(app)
        window.show()
        exit_code = qapp.exec()
        # Binding contract: while the recorder is RECORDING or STOP_FAILED
        # the launcher keeps a usable window/controller and the event
        # dispatch ALIVE — a Qt loop that somehow returned is re-entered
        # with a fresh status window so the operator retains the Retry
        # control against the SAME accepted cutoff until CLOSED. Nothing is
        # torn down on a failed stop.
        while app.status().state.value in ("RECORDING", "STOP_FAILED"):
            print(
                f"recorder still {app.status().state.value}; restoring the "
                "status window (retry against the same cutoff remains "
                "available)",
                file=sys.stderr,
            )
            window = RecorderStatusWindow.create(app)
            window.show()
            exit_code = qapp.exec()
        # IDLE or STOPPED: nothing recording, parent close is safe.
        app.stop_recording()
        return int(exit_code)
    finally:
        app.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
