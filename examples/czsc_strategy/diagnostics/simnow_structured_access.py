from __future__ import annotations

from typing import Any


def safe_get(summary: dict[str, Any], *keys: str, default: Any = "") -> Any:
    """Safely navigate nested dict keys."""
    obj: Any = summary
    for key in keys:
        if isinstance(obj, dict):
            obj = obj.get(key, default)
        else:
            return default
    return obj
