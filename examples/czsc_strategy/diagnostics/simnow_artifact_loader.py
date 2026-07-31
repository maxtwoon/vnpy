from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_dict(path: Path) -> dict[str, Any]:
    """Load a JSON object file if it exists; otherwise return an empty dict."""
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file if it exists; otherwise return an empty list."""
    if not path or not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
