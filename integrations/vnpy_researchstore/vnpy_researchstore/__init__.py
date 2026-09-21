"""vnpy_researchstore — native VeighNa bridges over a research_store snapshot.

Lazy package init is MANDATORY: importing this package must not import
``vnpy``, ``research_store``, or Qt. ``bootstrap.bootstrap_session()`` isolates
the runtime cwd and selects the repo path BEFORE anything transitively imports
``vnpy.trader.utility`` (which pins ``TRADER_DIR`` at import time); an eager
import here would defeat that ordering.

``vnpy.trader.database.get_database`` does ``import_module("vnpy_<name>")`` and
then accesses ``module.Database`` — the PEP 562 ``__getattr__`` below satisfies
that access while keeping package import side-effect free.

The recorder surface (bridge / stop-barrier engine / app / launcher) is
exported through the same lazy ``__getattr__``: recorder modules pull in
``research_store`` and ``vnpy.event`` at import time, so they must stay behind
the lazy accessor too.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .alpha import ResearchAlphaLab
    from .app import RecorderAppConfig, ResearchRecorderApp, load_recorder_config
    from .bootstrap import NativeSession, bootstrap_session, load_config
    from .database import Database
    from .launcher import main as recorder_main
    from .recorder import (
        RecorderConfig,
        RecorderInstrument,
        RecorderSnapshot,
        RecorderState,
        ResearchRecorder,
    )
    from .recording_engine import (
        RecordingMainEngine,
        RecorderStopError,
        StopReport,
        StopResult,
    )

__version__ = "0.1.0.dev1"

_RECORDER_APP = ("RecorderAppConfig", "ResearchRecorderApp", "load_recorder_config")
_RECORDER_CORE = (
    "RecorderConfig",
    "RecorderInstrument",
    "RecorderSnapshot",
    "RecorderState",
    "ResearchRecorder",
)
_RECORDER_ENGINE = (
    "RecordingMainEngine",
    "RecorderStopError",
    "StopReport",
    "StopResult",
)

__all__ = [
    "Database",
    "NativeSession",
    "RecorderAppConfig",
    "RecorderConfig",
    "RecorderInstrument",
    "RecorderSnapshot",
    "RecorderState",
    "RecorderStopError",
    "RecordingMainEngine",
    "ResearchAlphaLab",
    "ResearchRecorder",
    "ResearchRecorderApp",
    "StopReport",
    "StopResult",
    "__version__",
    "bootstrap_session",
    "load_config",
    "load_recorder_config",
    "recorder_main",
]


def __getattr__(name: str) -> object:
    if name == "Database":
        from .database import Database

        return Database
    if name == "ResearchAlphaLab":
        from .alpha import ResearchAlphaLab

        return ResearchAlphaLab
    if name in ("NativeSession", "bootstrap_session", "load_config"):
        from . import bootstrap

        return getattr(bootstrap, name)
    if name in _RECORDER_APP:
        from . import app

        return getattr(app, name)
    if name in _RECORDER_CORE:
        from . import recorder

        return getattr(recorder, name)
    if name in _RECORDER_ENGINE:
        from . import recording_engine

        return getattr(recording_engine, name)
    if name == "recorder_main":
        from .launcher import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
