from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_contract_map_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("contract map must be a JSON object")
    return payload


def contract_map_entries(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(symbol): row
        for symbol, row in payload.items()
        if not str(symbol).startswith("_") and isinstance(row, dict)
    }


def enabled_contract_map_entries(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(symbol): row
        for symbol, row in contract_map_entries(payload).items()
        if row.get("enabled", True)
    }


def enabled_symbols(payload: dict[str, Any]) -> list[str]:
    return sorted(str(symbol).upper() for symbol in enabled_contract_map_entries(payload))


def contract_map_provenance(path: Path) -> dict[str, Any]:
    payload = load_contract_map_payload(path)
    meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
    symbols = enabled_symbols(payload)
    return {
        "path": str(path),
        "version": str(meta.get("version") or ""),
        "effective_date": str(meta.get("effective_date") or ""),
        "note": str(meta.get("note") or ""),
        "enabled_symbols": symbols,
        "enabled_count": len(symbols),
    }
