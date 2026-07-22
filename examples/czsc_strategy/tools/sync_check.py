from __future__ import annotations

import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = ROOT / "tools" / "sync_guardian"

sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(ROOT))


if __name__ == "__main__":
    runpy.run_path(str(SCRIPT_DIR / "sync_check.py"), run_name="__main__")
