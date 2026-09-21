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
parent close and exits (no Qt). ``--stop`` starts recording, waits for a
console line, then runs the binding stop protocol: on STOP_FAILED the
parent close and the event engine are NOT touched — each further input
line retries the SAME accepted cutoff until the journal durably reports
committed==cutoff CLOSED. stdin EOF is NOT an exit authorization: the
launcher prints truthful guidance and parks with everything alive (the
journal session stays exactly as-is). With no flag the Qt status window
opens (offscreen-capable via the normal Qt platform env vars); if the Qt
loop ever returns while RECORDING or STOP_FAILED, a fresh status window is
restored so the Retry control stays usable — the launcher only exits after
CLOSED (or a verified never-recorded probe).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
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


#: Park latch for paths where the binding stop contract (B1) forbids ANY
#: teardown: the launcher process simply stays alive. Tests may ``set()`` the
#: event to unblock a parked launcher; production never does.
_PARK = threading.Event()


def _park_no_teardown(detail: str) -> None:
    """B1-compliant hold when the launcher must not exit or tear down.

    A failed stop withholds the parent close AND ``EventEngine.stop``; stdin
    EOF is not authorization to hard-exit, claim success, or drop the
    accepted work. There is therefore NO clean way for this process to exit
    on its own — so it parks the calling thread indefinitely: the event
    dispatch and controller stay alive, the journal session stays exactly
    as-is (OPEN / STOP_FAILED), and a retry against the SAME accepted cutoff
    remains possible. External termination of the whole process (console
    close, task manager) is the operating system's action, not a production
    teardown path, and releases the journal OS lock for public recovery.
    """

    print(detail, file=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()
    _PARK.wait()  # no timeout: B1 forbids self-teardown on a failed stop


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
            if (
                snapshot.state.value == "IDLE"
                and snapshot.session_id is None
                and snapshot.accepted_seq == 0
                and snapshot.committed_seq == 0
            ):
                # Verified: this probe never recorded, no journal session is
                # attached, and no work was accepted — the plain parent
                # close is safe and releases the engine.
                app.stop_recording()
                return 0
            _park_no_teardown(
                "status probe found attached work; per the binding stop "
                "contract nothing is torn down and the process stays alive"
            )
        session_id = app.start_recording()
        print(f"recording session {session_id} (vnpy={vnpy_file})")
        if args.stop:
            try:
                input("recording; press Enter to run the stop-barrier close...")
            except EOFError:
                _park_no_teardown(
                    "stdin closed before the stop request; the recording "
                    f"session {session_id} stays OPEN, event dispatch stays "
                    "alive, and the launcher parks (no teardown, no exit, "
                    "stop still pending operator action)"
                )
            report = app.stop_recording()
            # Binding contract: on STOP_FAILED the parent close and the
            # event engine are NOT touched; each further input line is one
            # retry_stop against the SAME fixed accepted cutoff until the
            # journal durably reaches committed==cutoff CLOSED.
            while report.result.value == "STOP_FAILED":
                print(
                    json.dumps(_stop_report_payload(report), indent=2,
                               sort_keys=True)
                )
                print(
                    "STOP_FAILED: journal did not drain to the exact cutoff "
                    "in time; parent close withheld. Press Enter to retry "
                    "the SAME cutoff until committed==cutoff and CLOSED.",
                    file=sys.stderr,
                )
                try:
                    input()
                except EOFError:
                    # EOF is NOT permission to hard-exit or drop the retry
                    # state: park with everything alive.
                    _park_no_teardown(
                        "stdin closed while STOP_FAILED; parent close and "
                        "engine stop remain withheld, the session stays "
                        "as-is, and the launcher parks so a retry against "
                        "the SAME accepted cutoff stays possible"
                    )
                report = app.retry_stop()
            print(
                json.dumps(_stop_report_payload(report), indent=2,
                           sort_keys=True)
            )
            if report.result.value != "CLOSED":
                # NOT_RECORDING (already closed/never recording): truthful
                # nonzero through the NORMAL exit path only.
                return 2
            return 0
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
