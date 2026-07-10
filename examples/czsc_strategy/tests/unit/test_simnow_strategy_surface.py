import json
import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_strategy_surface import (  # noqa: E402
    build_strategy_surface_from_capture,
    enrich_capture_payload,
    filter_events_to_window,
)


def _capture_payload() -> dict:
    return {
        "meta": {
            "started_at": "2026-07-07T01:14:59+00:00",
            "ended_at": "2026-07-07T01:19:59+00:00",
            "read_only": True,
            "orders_sent_by_workflow": 0,
            "workflow_order_actions": [],
        },
        "signals": [],
        "trades": [],
        "positions": [],
        "raw": {
            "ticks": [{"dt": "2026-07-07 09:14:59+08:00", "symbol": "sc2608"}],
            "contracts_count": 1,
            "accounts": [{"accountid": "demo"}],
            "positions": [],
            "orders": [],
            "trades": [],
            "subscribed": [{"research_symbol": "SC888"}],
        },
    }


def test_filter_events_to_window_keeps_only_overlapping_rows():
    events = [
        {"dt": "2026-07-07 09:10:00", "symbol": "AP888"},
        {"dt": "2026-07-07 09:15:00", "symbol": "SC888"},
        {"dt": "2026-07-07 09:25:00", "symbol": "RB888"},
    ]

    filtered = filter_events_to_window(
        events,
        "2026-07-07T09:14:59+08:00",
        "2026-07-07T09:19:59+08:00",
    )

    assert filtered == [{"dt": "2026-07-07 09:15:00", "symbol": "SC888"}]


def test_build_strategy_surface_from_capture_uses_capture_window():
    capture = _capture_payload()

    def snapshot_builder(db_path: Path, start: str, end: str, day: str, cost_factor: float) -> dict:
        return {
            "signals": [
                {"dt": "2026-07-07 09:15:00", "symbol": "SC888", "strategy": "signal_snapshot", "operate": "SIGNAL"},
                {"dt": "2026-07-07 14:59:00", "symbol": "AP888", "strategy": "signal_snapshot", "operate": "SIGNAL"},
            ],
            "trades": [
                {"dt": "2026-07-07 09:17:00", "symbol": "SC888", "strategy": "strategy_trade", "operate": "OPEN"},
                {"dt": "2026-07-07 23:29:00", "symbol": "SC888", "strategy": "strategy_trade", "operate": "CLOSE"},
            ],
            "positions": [
                {"dt": "2026-07-07 09:18:00", "symbol": "SC888", "strategy": "portfolio", "operate": "POSITION"},
                {"dt": "2026-07-07 22:59:00", "symbol": "RB888", "strategy": "portfolio", "operate": "POSITION"},
            ],
            "meta": {"replay_available": True},
        }

    surface = build_strategy_surface_from_capture(
        capture,
        Path("fake.db"),
        "2026-07-07",
        snapshot_builder=snapshot_builder,
    )

    assert [row["dt"] for row in surface["signals"]] == ["2026-07-07 09:15:00"]
    assert [row["dt"] for row in surface["trades"]] == ["2026-07-07 09:17:00"]
    assert [row["dt"] for row in surface["positions"]] == ["2026-07-07 09:18:00"]
    assert surface["meta"]["window_start"] == "2026-07-07T09:14:59+08:00"
    assert surface["meta"]["window_end"] == "2026-07-07T09:19:59+08:00"


def test_enrich_capture_payload_writes_strategy_surface_to_top_level():
    capture = _capture_payload()
    surface = {
        "signals": [{"dt": "2026-07-07 09:15:00", "symbol": "SC888", "strategy": "signal_snapshot", "operate": "SIGNAL"}],
        "trades": [{"dt": "2026-07-07 09:17:00", "symbol": "SC888", "strategy": "strategy_trade", "operate": "OPEN"}],
        "positions": [{"dt": "2026-07-07 09:18:00", "symbol": "SC888", "strategy": "portfolio", "operate": "POSITION"}],
        "meta": {"window_start": "2026-07-07T09:14:59+08:00", "window_end": "2026-07-07T09:19:59+08:00"},
    }

    enriched = enrich_capture_payload(capture, surface)

    assert enriched["signals"] == surface["signals"]
    assert enriched["trades"] == surface["trades"]
    assert enriched["positions"] == surface["positions"]
    assert enriched["raw"]["trades"] == []
    assert enriched["meta"]["strategy_surface"]["window_start"] == "2026-07-07T09:14:59+08:00"
