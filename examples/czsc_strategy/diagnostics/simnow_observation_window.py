from __future__ import annotations

import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
DEFAULT_WINDOW_CONFIG = HERE / "simnow_observation_window.json"


def load_observation_start_date(path: Path = DEFAULT_WINDOW_CONFIG) -> str:
    """Load the formal observation start date from config.

    Missing config is treated as no start-date filter so existing ad-hoc tests
    and historical diagnostics remain backward compatible.
    """
    if not path.exists():
        return ""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return str(payload.get("observation_start_date") or "")


def filter_records_by_start(records: list[dict[str, Any]], start_date: str | None) -> list[dict[str, Any]]:
    """Return records on or after ``start_date``.

    The ledger is append-only evidence. Restarting a 20-day observation cycle
    should not erase old evidence; it should only exclude rows before the new
    cycle start from promotion statistics.
    """
    if not start_date:
        return list(records)
    return [
        row
        for row in records
        if str(row.get("date") or "") >= start_date
    ]
