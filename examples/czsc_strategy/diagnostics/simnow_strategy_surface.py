from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from export_simnow_replay_snapshot import build_snapshot
from chan_strategy.config import SQLITE_DB_PATH


ASIA_SHANGHAI = timezone(timedelta(hours=8))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_capture_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ASIA_SHANGHAI)


def _parse_event_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ASIA_SHANGHAI)
    return dt.astimezone(ASIA_SHANGHAI)


def capture_window(meta: dict[str, Any]) -> tuple[str, str]:
    start = _parse_capture_dt(str(meta["started_at"])).isoformat()
    end = _parse_capture_dt(str(meta["ended_at"])).isoformat()
    return start, end


def filter_events_to_window(events: list[dict[str, Any]], window_start: str, window_end: str) -> list[dict[str, Any]]:
    start_dt = _parse_capture_dt(window_start)
    end_dt = _parse_capture_dt(window_end)
    filtered: list[dict[str, Any]] = []
    for row in events:
        raw_dt = str(row.get("dt") or row.get("datetime") or "")
        if not raw_dt:
            continue
        event_dt = _parse_event_dt(raw_dt)
        if start_dt <= event_dt <= end_dt:
            filtered.append(row)
    return filtered


def build_strategy_surface_from_capture(
    capture: dict[str, Any],
    db_path: Path,
    trade_date: str,
    snapshot_builder: Callable[[Path, str, str, str, float], dict[str, Any]] = build_snapshot,
) -> dict[str, Any]:
    window_start, window_end = capture_window(capture.get("meta") or {})
    replay_like = snapshot_builder(db_path, "2022-01-01", trade_date, trade_date, 1.0)
    return {
        "signals": filter_events_to_window(list(replay_like.get("signals") or []), window_start, window_end),
        "trades": filter_events_to_window(list(replay_like.get("trades") or []), window_start, window_end),
        "positions": filter_events_to_window(list(replay_like.get("positions") or []), window_start, window_end),
        "meta": {
            "source": "windowed_strategy_replay",
            "window_start": window_start,
            "window_end": window_end,
            "trade_date": trade_date,
        },
    }


def build_strategy_surface_from_captured_session(capture: dict[str, Any]) -> dict[str, Any]:
    """Build a comparison surface from the session's own captured trades/positions.

    Unlike ``build_strategy_surface_from_capture`` (which windows replay output
    to the capture timestamps), this surface uses ``capture["captured"]`` —
    real CTP callbacks recorded during the live session. The returned surface
    carries ``meta.source == "captured_session"`` so downstream callers can
    distinguish authoritative captured data from replay-derived references.
    """
    captured = capture.get("captured") or {}
    trades = [_trade_event_from_capture(row) for row in captured.get("trades") or []]
    positions = [_position_event_from_capture(row) for row in captured.get("positions") or []]
    orders = captured.get("orders") or []
    return {
        "signals": [],
        "trades": trades,
        "positions": positions,
        "meta": {
            "source": "captured_session",
            "trade_date": "",
            "captured_orders_count": len(orders),
        },
    }


def _trade_event_from_capture(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a captured raw trade into the strategy-event surface shape."""
    return {
        "dt": row.get("dt") or row.get("datetime") or row.get("time") or "",
        "symbol": str(row.get("symbol") or "").upper(),
        "strategy": "simnow_trade",
        "operate": str(row.get("direction") or row.get("operate") or "TRADE").upper(),
        "offset": str(row.get("offset") or "").upper(),
        "price": float(row.get("price") or 0.0),
        "volume": float(row.get("volume") or 0.0),
        "vt_tradeid": str(row.get("vt_tradeid") or ""),
    }


def _position_event_from_capture(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a captured raw position into the strategy-event surface shape."""
    return {
        "dt": row.get("dt") or row.get("datetime") or row.get("time") or "",
        "symbol": str(row.get("symbol") or "").upper(),
        "strategy": "simnow_position",
        "operate": "POSITION",
        "direction": str(row.get("direction") or ""),
        "volume": float(row.get("volume") or 0.0),
        "yd_volume": float(row.get("yd_volume") or 0.0),
        "price": float(row.get("price") or 0.0),
        "pnl": float(row.get("pnl") or 0.0),
    }


def enrich_capture_payload(capture: dict[str, Any], surface: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(capture)
    meta = dict(enriched.get("meta") or {})
    meta["strategy_surface"] = dict(surface.get("meta") or {})
    enriched["meta"] = meta
    enriched["signals"] = list(surface.get("signals") or [])
    enriched["trades"] = list(surface.get("trades") or [])
    enriched["positions"] = list(surface.get("positions") or [])
    return enriched


def enrich_capture_json(capture_json: Path, trade_date: str, db_path: Path) -> dict[str, Any]:
    capture = load_json(capture_json)
    surface = build_strategy_surface_from_capture(capture, db_path, trade_date)
    enriched = enrich_capture_payload(capture, surface)
    write_json(capture_json, enriched)
    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich a SimNow capture JSON with windowed strategy event surfaces.")
    parser.add_argument("--capture-json", type=Path, required=True)
    parser.add_argument("--date", required=True, help="Trading day to build strategy surfaces for, YYYY-MM-DD.")
    parser.add_argument("--db-path", type=Path, default=Path(SQLITE_DB_PATH))
    args = parser.parse_args()

    enriched = enrich_capture_json(args.capture_json, args.date, args.db_path)
    print(json.dumps({
        "capture_json": str(args.capture_json),
        "signals": len(enriched.get("signals") or []),
        "trades": len(enriched.get("trades") or []),
        "positions": len(enriched.get("positions") or []),
        "strategy_surface": enriched.get("meta", {}).get("strategy_surface", {}),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
