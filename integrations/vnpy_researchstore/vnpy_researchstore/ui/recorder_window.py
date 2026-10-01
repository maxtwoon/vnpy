"""Qt widget implementing the recorder status window.

The widget renders a ``RecorderSnapshot`` on a QTimer and issues start /
stop / retry actions to the shared ``ResearchRecorderApp``. All stop work is
marshalled to a worker thread so the Qt event loop — which may also drive the
vnpy ``EventEngine``'s queued callbacks in the same process — never blocks
inside the stop barrier wait.
"""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from ..recorder import UNAVAILABLE, RecorderSnapshot
from ..recording_engine import StopReport, StopResult

STATUS_REFRESH_MS = 500

_LABELS: tuple[tuple[str, str], ...] = (
    ("state", "Recorder state"),
    ("journal_state", "Journal state"),
    ("session_id", "Session id"),
    ("journal_path", "Journal path"),
    ("source", "Source"),
    ("instruments", "Instruments"),
    ("accepted_seq", "Accepted seq"),
    ("committed_seq", "Committed seq"),
    ("backlog", "Backlog"),
    ("rejected", "Rejected"),
    ("errors", "Errors"),
    ("last_error_detail", "Last error detail"),
    ("last_admission", "Last admission"),
    ("successor_session_id", "Successor session (typed)"),
    ("recovery_note", "Last recovery"),
)


class _StopWorker(QtCore.QThread):
    """Runs stop/retry off the Qt thread; emits a typed ``StopReport``."""

    finished_report = QtCore.Signal(object)

    def __init__(self, app: Any, retry: bool, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._retry = retry

    def run(self) -> None:
        if self._retry:
            report = self._app.retry_stop()
        else:
            report = self._app.stop_recording()
        self.finished_report.emit(report)


class RecorderStatusWidget(QtWidgets.QMainWindow):
    """Status window: source/instruments/session/journal/state/watermarks."""

    def __init__(self, app: Any, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._values: dict[str, QtWidgets.QLabel] = {}
        self._stop_worker: _StopWorker | None = None
        self._close_veto_detail: str | None = None

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        form = QtWidgets.QFormLayout()
        for key, label in _LABELS:
            value = QtWidgets.QLabel("-")
            value.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(label, value)
            self._values[key] = value
        layout.addLayout(form)

        buttons = QtWidgets.QHBoxLayout()
        self._start_button = QtWidgets.QPushButton("Start recording")
        self._stop_button = QtWidgets.QPushButton("Stop (barrier close)")
        self._retry_button = QtWidgets.QPushButton("Retry stop")
        self._stop_button.setEnabled(False)
        self._retry_button.setEnabled(False)
        self._start_button.clicked.connect(self._on_start)
        self._stop_button.clicked.connect(self._on_stop)
        self._retry_button.clicked.connect(self._on_retry)
        buttons.addWidget(self._start_button)
        buttons.addWidget(self._stop_button)
        buttons.addWidget(self._retry_button)
        layout.addLayout(buttons)

        # Crash-recovery row: recover an unclosed session id through the
        # public typed core API. The typed successor_session_id of the report
        # is rendered in the status grid (never parsed from prose).
        recover_row = QtWidgets.QHBoxLayout()
        self._recover_input = QtWidgets.QLineEdit()
        self._recover_input.setPlaceholderText("unclosed session id to recover")
        self._recover_button = QtWidgets.QPushButton("Recover session")
        self._recover_button.clicked.connect(self._on_recover)
        recover_row.addWidget(self._recover_input, stretch=1)
        recover_row.addWidget(self._recover_button)
        layout.addLayout(recover_row)

        self._message = QtWidgets.QLabel("")
        layout.addWidget(self._message)
        self.setCentralWidget(central)
        self.setWindowTitle("Research Recorder (research_store journal)")

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(STATUS_REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    # -- rendering -----------------------------------------------------------

    def _refresh(self) -> None:
        # Non-blocking snapshot; safe even if the shared dispatch thread is
        # busy admitting ticks.
        snapshot: RecorderSnapshot = self._app.status()
        self._values["state"].setText(snapshot.state.value)
        self._values["journal_state"].setText(
            snapshot.journal_state.value if snapshot.journal_state else "-"
        )
        self._values["session_id"].setText(snapshot.session_id or "-")
        self._values["journal_path"].setText(snapshot.journal_path or "-")
        self._values["source"].setText(
            f"{snapshot.source_id} ({snapshot.source_kind})"
        )
        self._values["instruments"].setText(", ".join(snapshot.instruments) or "-")
        self._values["accepted_seq"].setText(str(snapshot.accepted_seq))
        self._values["committed_seq"].setText(str(snapshot.committed_seq))
        self._values["backlog"].setText(str(snapshot.backlog))
        self._values["rejected"].setText(str(snapshot.rejected))
        self._values["errors"].setText(str(snapshot.errors))
        # Typed last-error detail (WP09): None means the journal reports no
        # error; the UNAVAILABLE marker only survives when no session exists.
        detail = snapshot.last_error_detail
        self._values["last_error_detail"].setText(
            detail if detail else ("none" if snapshot.journal_state else UNAVAILABLE)
        )
        last = snapshot.last_admission
        self._values["last_admission"].setText(
            f"{last.kind} {last.vt_symbol} accepted={last.accepted} "
            f"seq={last.assigned_seq} reason={last.reason}"
            if last
            else "-"
        )
        # Typed recovery/successor display (WP09 fields; no prose parsing).
        report = self._app.last_recovery
        if report is None:
            self._values["successor_session_id"].setText("-")
            self._values["recovery_note"].setText("-")
        else:
            self._values["successor_session_id"].setText(
                report.successor_session_id or "-"
            )
            note = f"prior={report.prior_status} detail={report.detail}"
            if report.last_error:
                note = f"{note} error={report.last_error}"
            self._values["recovery_note"].setText(note)
        recording = snapshot.state.value == "RECORDING"
        self._start_button.setEnabled(not recording and self._stop_worker is None)
        self._stop_button.setEnabled(recording and self._stop_worker is None)
        self._retry_button.setEnabled(
            snapshot.state.value == "STOP_FAILED" and self._stop_worker is None
        )

    # -- actions ---------------------------------------------------------------

    def _on_start(self) -> None:
        try:
            session_id = self._app.start_recording()
        except Exception as exc:  # noqa: BLE001 - surfaced in the status line
            self._message.setText(f"start failed: {exc}")
            return
        self._message.setText(f"recording session {session_id}")

    def _on_recover(self) -> None:
        """Recover the typed session id from the input box (public API)."""

        session_id = self._recover_input.text().strip()
        if not session_id:
            self._message.setText("enter a session id to recover")
            return
        try:
            report = self._app.recover_session(session_id)
        except Exception as exc:  # noqa: BLE001 - surfaced in the status line
            self._message.setText(f"recover failed: {exc}")
            self._refresh()
            return
        self._message.setText(
            f"recovered {report.session_id}; "
            f"successor={report.successor_session_id or 'none'}"
        )
        self._refresh()

    def _on_stop(self) -> None:
        self._run_stop(retry=False)

    def _on_retry(self) -> None:
        self._run_stop(retry=True)

    def _run_stop(self, *, retry: bool) -> None:
        if self._stop_worker is not None:
            return
        worker = _StopWorker(self._app, retry, self)
        worker.finished_report.connect(self._on_stop_report)
        self._stop_worker = worker
        self._message.setText("stop barrier running...")
        worker.start()

    def _on_stop_report(self, report: StopReport) -> None:
        self._stop_worker = None
        if report.result is StopResult.CLOSED:
            self._message.setText(
                f"closed: session={report.session_id} "
                f"accepted={report.accepted_seq} committed={report.committed_seq}"
            )
            self._close_veto_detail = None
        elif report.result is StopResult.STOP_FAILED:
            self._message.setText(f"STOP FAILED: {report.detail}")
            # Remember the failure so closeEvent can veto the window close.
            self._close_veto_detail = report.detail
        else:
            self._message.setText(report.detail)
        self._refresh()

    # -- close protocol ----------------------------------------------------------

    def closeEvent(self, event: Any) -> None:
        """Honour a failed stop: refuse to close while STOP_FAILED is active.

        The user must retry the stop (or fix the journal condition) before the
        window — and with it the process — may exit; an unconditional exit
        would tear down the event engine underneath a still-open session.
        """

        if self._stop_worker is not None:
            self._message.setText("stop in progress; close ignored")
            event.ignore()
            return
        snapshot = self._app.status()
        if snapshot.state.value == "RECORDING":
            # Ask the binding protocol to close the session first.
            self._run_stop(retry=False)
            event.ignore()
            return
        if snapshot.state.value == "STOP_FAILED" or self._close_veto_detail is not None:
            detail = self._close_veto_detail or (
                "session stop failed; see status line"
            )
            self._message.setText(
                f"close refused: last stop failed ({detail}); "
                "retry the stop first"
            )
            event.ignore()
            return
        super().closeEvent(event)


__all__ = ["RecorderStatusWidget", "STATUS_REFRESH_MS"]
