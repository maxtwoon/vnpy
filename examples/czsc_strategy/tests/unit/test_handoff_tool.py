"""Regression coverage for the local sync-guardian handoff wrapper."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_handoff_status_uses_authoritative_sync_check_engine():
    project_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, "tools/handoff.py", "status"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "stage:" in completed.stdout
    assert "owner:" in completed.stdout
