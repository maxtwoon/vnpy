"""App-facade and Qt UI tests for the research recorder.

The Qt tests run offscreen (QT_QPA_PLATFORM=offscreen) and never open a real
on-screen window. Covers config validation, the app control surface, and the
window's failed-close refusal.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from research_store import init_store  # noqa: E402
from vnpy_researchstore.app import (  # noqa: E402
    ResearchRecorderApp,
    RecorderAppConfig,
    load_recorder_config,
)
from vnpy_researchstore.recorder import (  # noqa: E402
    RecorderConfigError,
    RecorderInstrument,
)
from vnpy_researchstore.recording_engine import StopResult  # noqa: E402


def _teardown_app(app: ResearchRecorderApp) -> None:
    """Deterministic teardown: never leave vnpy's non-daemon event threads
    running (a failed assertion mid-test would otherwise hang interpreter
    exit). Stop attempts are idempotent; STOP_FAILED retries once."""

    try:
        state = app.status().state.value
        if state == "RECORDING":
            state = app.stop_recording().result.value
        if state == "STOP_FAILED":
            report = app.retry_stop()
            if report.result is StopResult.STOP_FAILED:
                app.recorder.release()
                app.engine.event_engine.stop()
    finally:
        app.shutdown()


def _write_config(tmp_path: Path, store_root: Path, **overrides) -> Path:
    raw = {
        "store_root": str(store_root),
        "source_id": "sim-test",
        "source_kind": "simulated",
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
def store(tmp_path: Path):
    s = init_store(tmp_path / "store")
    yield s
    s.close()


def test_load_config_rejects_unknown_keys(tmp_path, store) -> None:
    path = _write_config(tmp_path, store.root, bogus_key=1)
    with pytest.raises(RecorderConfigError, match="unknown keys"):
        load_recorder_config(path)


def test_load_config_rejects_local_instrument(tmp_path, store) -> None:
    path = _write_config(
        tmp_path,
        store.root,
        instruments=[{"symbol": "SYNTH", "exchange": "LOCAL"}],
    )
    with pytest.raises(RecorderConfigError, match="LOCAL"):
        load_recorder_config(path)


def test_load_config_rejects_bad_source_kind(tmp_path, store) -> None:
    path = _write_config(tmp_path, store.root, source_kind="live-ish")
    with pytest.raises(RecorderConfigError, match="source_kind"):
        load_recorder_config(path)


def test_load_config_accepts_launcher_keys(tmp_path, store) -> None:
    path = _write_config(
        tmp_path,
        store.root,
        repo_path="D:/repo/vnpy",
        runtime_dir=str(tmp_path / "runtime"),
    )
    config = load_recorder_config(path)
    assert config.source_kind == "simulated"
    assert config.instruments[0].vt_symbol == "rb2501.SHFE"


def test_app_start_status_stop(store) -> None:
    config = RecorderAppConfig(
        store_root=str(store.root),
        source_id="sim-test",
        source_kind="simulated",
        calendar_spec="tz:Asia/Shanghai",
        instruments=(RecorderInstrument("rb2501", "SHFE"),)
    )
    app = ResearchRecorderApp(config)
    try:
        session_id = app.start_recording()
        snapshot = app.status()
        assert snapshot.session_id == session_id
        assert snapshot.state.value == "RECORDING"
        # Typed WP09 field: a session with no writer/admission error reports
        # None 鈥?never a fabricated string and never the UNAVAILABLE marker.
        assert snapshot.last_error_detail is None
        report = app.stop_recording()
        assert report.result is StopResult.CLOSED
        assert report.session_id == session_id
    finally:
        _teardown_app(app)


def test_app_never_connects_gateway(store, monkeypatch) -> None:
    import vnpy.trader.engine as engine_module

    def _forbidden(*args, **kwargs):  # noqa: ANN002, ANN003
        pytest.fail("connect() must not be called")

    monkeypatch.setattr(engine_module.MainEngine, "connect", _forbidden)
    config = RecorderAppConfig(
        store_root=str(store.root),
        source_id="sim-test",
        source_kind="simulated",
        calendar_spec="tz:Asia/Shanghai",
        instruments=(RecorderInstrument("rb2501", "SHFE"),)
    )
    app = ResearchRecorderApp(config)
    try:
        app.start_recording()
        assert app.stop_recording().result is StopResult.CLOSED
    finally:
        _teardown_app(app)


def test_ui_close_event_vetoes_failed_stop(store, monkeypatch) -> None:
    """A window close after STOP_FAILED must be ignored, not exit."""

    from research_store.journal import JournalSession

    from vnpy_researchstore.ui.recorder_window import RecorderStatusWidget

    config = RecorderAppConfig(
        store_root=str(store.root),
        source_id="sim-test",
        source_kind="simulated",
        calendar_spec="tz:Asia/Shanghai",
        instruments=(RecorderInstrument("rb2501", "SHFE"),)
    )
    app = ResearchRecorderApp(config)
    original = JournalSession.close_at_cutoff
    try:
        app.start_recording()
        # Force a bounded journal close failure so the app reports STOP_FAILED.
        monkeypatch.setattr(
            JournalSession,
            "close_at_cutoff",
            lambda self, *, timeout=10.0: original(self, timeout=0.001),
        )
        report = app.stop_recording()
        monkeypatch.undo()
        assert report.result is StopResult.STOP_FAILED

        from PySide6 import QtWidgets

        _qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        window = RecorderStatusWidget(app)
        window.show()
        # Simulate the user clicking the window close button.
        window.close()
        assert window.isVisible(), "closeEvent must veto the close after STOP_FAILED"
        # Retry the stop from the UI action; now the real close succeeds and
        # the window may close.
        worker_done = []

        from vnpy_researchstore.ui.recorder_window import _StopWorker

        worker = _StopWorker(app, retry=True)
        worker.finished_report.connect(
            lambda rep: worker_done.append(rep)
        )
        worker.run()  # run synchronously: the protocol is thread-based anyway
        assert worker_done[0].result is StopResult.CLOSED
        window._on_stop_report(worker_done[0])
        window.close()
        assert not window.isVisible()
    finally:
        _teardown_app(app)


def test_ui_status_rendering_does_not_block_dispatch(store) -> None:
    """_refresh reads a snapshot; with a busy dispatch thread it must still
    return promptly (it never joins the event engine)."""

    import time

    from PySide6 import QtWidgets

    from vnpy_researchstore.ui.recorder_window import RecorderStatusWidget

    config = RecorderAppConfig(
        store_root=str(store.root),
        source_id="sim-test",
        source_kind="simulated",
        calendar_spec="tz:Asia/Shanghai",
        instruments=(RecorderInstrument("rb2501", "SHFE"),)
    )
    app = ResearchRecorderApp(config)
    try:
        app.start_recording()
        _qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        window = RecorderStatusWidget(app)
        started = time.monotonic()
        window._refresh()
        elapsed = time.monotonic() - started
        assert elapsed < 1.0, "status rendering blocked the UI thread"
        assert window._values["state"].text() == "RECORDING"
        # Typed WP09 field, honest render: a healthy attached session shows
        # "none" (no error), not the UNAVAILABLE marker.
        assert window._values["last_error_detail"].text() == "none"
        assert window._values["successor_session_id"].text() == "-"
        assert app.stop_recording().result is StopResult.CLOSED
    finally:
        _teardown_app(app)
