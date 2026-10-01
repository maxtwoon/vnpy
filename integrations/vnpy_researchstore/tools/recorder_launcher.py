"""Repo-run shim for the packaged recorder launcher.

The real logic lives in ``vnpy_researchstore.launcher`` (shipped with the
package, also reachable via ``python -m vnpy_researchstore`` and the
``vnpy-recorder`` console script). This shim only makes the source checkout
importable, then delegates — installed environments never need it.

Usage::

    python tools/recorder_launcher.py --config configs/recorder_simulated.json
    python tools/recorder_launcher.py --config configs/recorder_simulated.json --status
    python tools/recorder_launcher.py --config configs/recorder_simulated.json --stop
"""

from __future__ import annotations

import sys
from pathlib import Path

INTEGRATION_ROOT = Path(__file__).resolve().parents[1]
if str(INTEGRATION_ROOT) not in sys.path:
    sys.path.insert(0, str(INTEGRATION_ROOT))

from vnpy_researchstore.launcher import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
