"""ResearchRecorderApp — headless-friendly app facade over the recorder bridge.

The app wires a ``ResearchRecorder`` to a ``RecordingMainEngine`` and exposes
start / stop / retry_stop / status actions that both the CLI launcher and the
Qt UI call. It never connects gateways, accounts, or strategies; the only
events recorded are those an explicitly configured upstream pushes into the
shared ``EventEngine``.

The app object is intentionally UI-toolkit free so the same control surface
is testable offline (simulated/test labelled) and drivable from the Qt status
window without duplicating protocol logic.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

from research_store import (
    # Canonical public entries (recording02I corrected the top-level
    # recover_session wrapper: it forwards create_successor and the
    # successor spec overrides faithfully). Only typed public results are
    # consumed; no private attribute is read and no prose id is parsed.
    SessionRecoveryReport,
    recover_session,
)
from research_store.store import Store, open_store

from .recorder import (
    RecorderConfig,
    RecorderConfigError,
    RecorderInstrument,
    RecorderSnapshot,
    ResearchRecorder,
)
from .recording_engine import RecordingMainEngine, StopReport

CONFIG_KEYS = {
    "store_root",
    "source_id",
    "source_kind",
    "calendar_spec",
    "instruments",
    "event_kinds",
    "gateway_type",
    "session_id",
    "predecessor_session_id",
    # consumed by tools/recorder_launcher.py before the app is built
    "repo_path",
    "runtime_dir",
}

SOURCE_KINDS = ("simulated", "production")


@dataclass(frozen=True)
class RecorderAppConfig:
    """Validated launcher/app configuration."""

    store_root: str
    source_id: str
    source_kind: str
    calendar_spec: str
    instruments: tuple[RecorderInstrument, ...]
    event_kinds: tuple[str, ...] = ("tick",)
    gateway_type: str = ""
    session_id: str | None = None
    predecessor_session_id: str | None = None


def load_recorder_config(config_path: str | Path) -> RecorderAppConfig:
    """Parse and validate a recorder JSON config.

    Unknown keys are rejected so a typo can never silently disable a safety
    check. Keys starting with ``_`` are comments.
    """

    path = Path(config_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RecorderConfigError(f"recorder config {path} must be a JSON object")
    unknown = sorted(k for k in raw if k not in CONFIG_KEYS and not k.startswith("_"))
    if unknown:
        raise RecorderConfigError(
            f"recorder config {path} has unknown keys {unknown}"
        )
    missing = [
        key
        for key in ("store_root", "source_id", "source_kind", "calendar_spec", "instruments")
        if not raw.get(key)
    ]
    if missing:
        raise RecorderConfigError(
            f"recorder config {path} missing required keys {missing}"
        )
    if raw["source_kind"] not in SOURCE_KINDS:
        raise RecorderConfigError(
            f"source_kind must be one of {SOURCE_KINDS}; got {raw['source_kind']!r}"
        )
    calendar_spec = str(raw["calendar_spec"])
    if not calendar_spec:
        raise RecorderConfigError("calendar_spec is required")
    # Revised 02I seal grammar: "", IANA zone, or "tz:<IANA zone>".
    # Timezone-only is display evidence — never a trading-calendar claim.
    from research_store.sealing import SealError, validate_calendar_spec

    try:
        validate_calendar_spec(calendar_spec)
    except SealError as exc:
        raise RecorderConfigError(
            f"calendar_spec {calendar_spec!r} violates the seal grammar "
            f"(v1): {exc}"
        ) from None
    instruments: list[RecorderInstrument] = []
    for entry in raw["instruments"]:
        if not isinstance(entry, dict):
            raise RecorderConfigError(f"instrument entries must be objects: {entry!r}")
        symbol = str(entry.get("symbol", "")).strip()
        exchange = str(entry.get("exchange", "")).strip().upper()
        if not symbol or not exchange:
            raise RecorderConfigError(
                f"instrument needs explicit symbol and exchange: {entry!r}"
            )
        if exchange == "LOCAL":
            raise RecorderConfigError(
                "LOCAL synthetic contracts are refused; configure a real exchange "
                f"for {entry!r}"
            )
        instruments.append(RecorderInstrument(symbol=symbol, exchange=exchange))
    if not instruments:
        raise RecorderConfigError("at least one instrument must be configured")
    event_kinds = tuple(raw.get("event_kinds", ("tick",)))
    for kind in event_kinds:
        if kind not in ("tick", "trade", "bar"):
            raise RecorderConfigError(f"unsupported event kind {kind!r}")
    return RecorderAppConfig(
        store_root=str(raw["store_root"]),
        source_id=str(raw["source_id"]),
        source_kind=str(raw["source_kind"]),
        calendar_spec=calendar_spec,
        instruments=tuple(instruments),
        event_kinds=event_kinds,
        gateway_type=str(raw.get("gateway_type", "")),
        session_id=raw.get("session_id"),
        predecessor_session_id=raw.get("predecessor_session_id"),
    )


class ResearchRecorderApp:
    """Control surface shared by the launcher CLI and the Qt status UI."""

    def __init__(self, config: RecorderAppConfig) -> None:
        self.config = config
        self._store: Store = open_store(config.store_root)
        recorder_config = RecorderConfig(
            source_id=config.source_id,
            source_kind=config.source_kind,
            calendar_spec=config.calendar_spec,
            instruments=config.instruments,
            event_kinds=config.event_kinds,
            gateway_type=config.gateway_type,
            session_id=config.session_id,
            predecessor_session_id=config.predecessor_session_id,
        )
        self._recorder = ResearchRecorder(self._store, recorder_config)
        self._engine = RecordingMainEngine()
        self._engine.add_recorder(self._recorder)
        self._started = False
        self._last_recovery: SessionRecoveryReport | None = None
        # Recovery touches journal locks and SQLite; serialize it against
        # concurrent recover calls (the UI and a CLI probe could race).
        self._recover_lock = threading.Lock()

    # -- actions ---------------------------------------------------------------

    def start_recording(self) -> str:
        """Open the journal session; returns the session id."""

        session_id = self._recorder.start()
        self._started = True
        return session_id

    def stop_recording(self) -> StopReport:
        """Binding stop-barrier close; see ``RecordingMainEngine.close``."""

        return self._engine.close()

    def retry_stop(self) -> StopReport:
        """Re-attempt a failed stop against the same fixed cutoff."""

        return self._engine.retry_stop()

    def status(self) -> RecorderSnapshot:
        """Non-blocking status snapshot; safe from UI timers."""

        return self._recorder.snapshot()

    def recover_session(
        self, session_id: str, *, create_successor: bool = True
    ) -> SessionRecoveryReport:
        """Recover an unclosed session through the public core API.

        Consumes only the typed ``SessionRecoveryReport`` (including
        ``successor_session_id`` / ``last_error``); no prose is parsed. The
        typed report is kept for status/successor display and returned.
        Raises ``SessionRecoveryError`` for unknown/unrecoverable sessions.
        """

        with self._recover_lock:
            report = recover_session(
                self._store,
                session_id,
                create_successor=create_successor,
            )
            self._last_recovery = report
            return report

    @property
    def last_recovery(self) -> SessionRecoveryReport | None:
        """Typed report of the most recent ``recover_session`` call."""

        return self._last_recovery

    @property
    def engine(self) -> RecordingMainEngine:
        return self._engine

    @property
    def recorder(self) -> ResearchRecorder:
        return self._recorder

    # -- teardown ----------------------------------------------------------------

    def shutdown(self) -> None:
        """Release the store; the engine close protocol is the caller's job."""

        self._store.close()

    def __enter__(self) -> ResearchRecorderApp:
        return self

    def __exit__(self, *exc: object) -> None:
        self.shutdown()


__all__ = [
    "RecorderAppConfig",
    "ResearchRecorderApp",
    "load_recorder_config",
]
