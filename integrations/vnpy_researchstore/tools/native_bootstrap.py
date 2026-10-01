"""Entry command: bootstrap a native snapshot backtest process.

Usage:
    python tools/native_bootstrap.py --config configs/native_backtest.json

Prints the run receipt JSON on stdout; exits nonzero on any refusal. Must be
run as a FRESH process per snapshot (no hot-switching).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vnpy_researchstore.bootstrap import main  # noqa: E402  (sys.path first)

if __name__ == "__main__":
    sys.exit(main())
