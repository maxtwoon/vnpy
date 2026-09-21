"""Qt status UI for the research recorder.

The window shows source / instruments / session / journal path / state /
accepted / committed / backlog / rejected / last error, plus start, stop and
retry actions. Rendering reads a non-blocking ``RecorderSnapshot`` and never
blocks the shared event-dispatch thread. A ``closeEvent`` honours a failed
stop: when the stop protocol reports STOP_FAILED the window refuses to close
so the process (and event engine) stays usable for a retry.
"""

from __future__ import annotations

from typing import Any

from ..recorder import UNAVAILABLE, RecorderSnapshot
from ..recording_engine import StopReport, StopResult

#: Refresh period of the status grid; independent of the event engine timer.
STATUS_REFRESH_MS = 500


class RecorderStatusWindow:
    """Qt window (kept in ui/recorder_window.py at runtime).

    Imported lazily so ``import vnpy_researchstore.ui`` stays side-effect free
    without Qt installed; ``create`` builds the real widget.
    """

    @staticmethod
    def create(app: Any, parent: Any = None) -> Any:
        from .recorder_window import RecorderStatusWidget

        return RecorderStatusWidget(app, parent)


__all__ = ["RecorderStatusWindow", "RecorderSnapshot", "StopReport", "StopResult", "UNAVAILABLE"]
