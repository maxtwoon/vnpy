from __future__ import annotations

import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(r"D:\repo\ashare\skills\sync-guardian\scripts")

sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(ROOT))


if __name__ == "__main__":
    runpy.run_path(str(SCRIPT_DIR / "handoff.py"), run_name="__main__")
