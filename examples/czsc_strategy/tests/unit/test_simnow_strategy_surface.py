import json
import subprocess
import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_run_summary import extract_account_contamination  # noqa: E402
from simnow_strategy_surface import (  # noqa: E402
    build_strategy_surface_from_capture,
    build_strategy_surface_from_captured_session,
    enrich_capture_json,
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


def _captured_trade():
    return {
        "dt": "2026-07-07 09:17:00",
        "symbol": "sc2608",
        "direction": "多",
        "offset": "OPEN",
        "price": 500.0,
        "volume": 1.0,
        "vt_tradeid": "t1",
    }


def _captured_position():
    return {
        "dt": "2026-07-07 09:18:00",
        "symbol": "sc2608",
        "direction": "多",
        "volume": 1.0,
        "yd_volume": 0.0,
        "price": 500.0,
        "pnl": 0.0,
    }


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


def test_enrich_capture_json_auto_prefers_captured_session_when_data_present(tmp_path):
    capture = _capture_payload()
    capture["captured"] = {
        "trades": [_captured_trade()],
        "positions": [_captured_position()],
        "orders": [],
    }
    capture_json = tmp_path / "capture.json"
    capture_json.write_text(json.dumps(capture), encoding="utf-8")

    enriched = enrich_capture_json(capture_json, "2026-07-07", tmp_path / "fake.db")

    assert enriched["meta"]["strategy_surface"]["source"] == "captured_session"
    assert enriched["meta"]["strategy_surface"]["trade_date"] == "2026-07-07"
    assert len(enriched["trades"]) == 1
    assert enriched["trades"][0]["symbol"] == "SC2608"
    assert enriched["trades"][0]["strategy"] == "simnow_trade"
    assert len(enriched["positions"]) == 1
    assert enriched["positions"][0]["strategy"] == "simnow_position"


def test_enrich_capture_json_auto_falls_back_to_windowed_replay_when_no_captured_data(tmp_path):
    capture = _capture_payload()
    assert "captured" not in capture or not capture.get("captured")
    capture_json = tmp_path / "capture.json"
    capture_json.write_text(json.dumps(capture), encoding="utf-8")

    def snapshot_builder(db_path, start, end, day, cost_factor):
        return {
            "signals": [],
            "trades": [{"dt": "2026-07-07 09:17:00", "symbol": "SC888", "strategy": "strategy_trade", "operate": "OPEN"}],
            "positions": [],
            "meta": {"replay_available": True},
        }

    enriched = enrich_capture_json(
        capture_json,
        "2026-07-07",
        tmp_path / "fake.db",
        snapshot_builder=snapshot_builder,
    )

    # File-based round-trip should use the windowed replay path.
    assert enriched["meta"]["strategy_surface"]["source"] == "windowed_strategy_replay"


def test_enrich_capture_json_explicit_modes_override_auto(tmp_path):
    capture = _capture_payload()
    capture["captured"] = {
        "trades": [_captured_trade()],
        "positions": [_captured_position()],
        "orders": [],
    }
    capture_json = tmp_path / "capture.json"
    capture_json.write_text(json.dumps(capture), encoding="utf-8")

    def snapshot_builder(db_path, start, end, day, cost_factor):
        return {
            "signals": [],
            "trades": [{"dt": "2026-07-07 09:17:00", "symbol": "SC888", "strategy": "strategy_trade", "operate": "OPEN"}],
            "positions": [],
            "meta": {"replay_available": True},
        }

    # Explicit windowed_replay ignores captured data.
    enriched = enrich_capture_json(
        capture_json,
        "2026-07-07",
        tmp_path / "fake.db",
        surface_source_mode="windowed_replay",
        snapshot_builder=snapshot_builder,
    )
    assert enriched["meta"]["strategy_surface"]["source"] == "windowed_strategy_replay"


def test_cli_enrich_capture_json_uses_auto_default(tmp_path):
    capture = _capture_payload()
    capture["captured"] = {
        "trades": [_captured_trade()],
        "positions": [_captured_position()],
        "orders": [],
    }
    capture_json = tmp_path / "capture.json"
    capture_json.write_text(json.dumps(capture), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(DIAG / "simnow_strategy_surface.py"),
            "--capture-json", str(capture_json),
            "--date", "2026-07-07",
            "--db-path", str(tmp_path / "fake.db"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    summary = json.loads(result.stdout)
    assert summary["strategy_surface"]["source"] == "captured_session"
    assert summary["trades"] == 1

    # Verify the file was actually overwritten.
    enriched = json.loads(capture_json.read_text(encoding="utf-8"))
    assert enriched["meta"]["strategy_surface"]["source"] == "captured_session"


def _contract_map() -> dict:
    """Realistic contract_map where the value's ``symbol`` is the actual CTP contract."""
    return {
        "SC888": {"symbol": "sc2608", "exchange": "INE", "enabled": True},
        "AP888": {"symbol": "ap888", "exchange": "CZCE", "enabled": False},
    }


def _external_captured_trade():
    return {
        "dt": "2026-07-07 09:17:00",
        "symbol": "rb2501",
        "direction": "空",
        "offset": "OPEN",
        "price": 3200.0,
        "volume": 1.0,
        "vt_tradeid": "t2",
    }


def _external_captured_position():
    return {
        "dt": "2026-07-07 09:18:00",
        "symbol": "rb2501",
        "direction": "空",
        "volume": 1.0,
        "yd_volume": 0.0,
        "price": 3200.0,
        "pnl": 0.0,
    }


def test_build_strategy_surface_filters_external_position_to_contamination():
    capture = _capture_payload()
    capture["meta"]["contract_map"] = _contract_map()
    capture["captured"] = {
        "trades": [],
        "positions": [_captured_position(), _external_captured_position()],
        "orders": [],
    }
    capture["raw"]["positions"] = list(capture["captured"]["positions"])

    surface = build_strategy_surface_from_captured_session(capture)

    assert [row["symbol"] for row in surface["positions"]] == ["SC2608"]
    assert surface["meta"]["filtered_positions_count"] == 1
    assert surface["meta"]["filtered_trades_count"] == 0
    assert surface["meta"]["filtered_symbols"] == ["RB2501"]

    contamination = extract_account_contamination(capture)
    assert contamination["active_positions"] == 2
    assert "rb2501" in contamination["position_symbols"]
    assert "sc2608" in contamination["position_symbols"]


def test_build_strategy_surface_filters_external_trade_to_contamination():
    capture = _capture_payload()
    capture["meta"]["contract_map"] = _contract_map()
    capture["captured"] = {
        "trades": [_captured_trade(), _external_captured_trade()],
        "positions": [],
        "orders": [],
    }
    capture["raw"]["trades"] = list(capture["captured"]["trades"])

    surface = build_strategy_surface_from_captured_session(capture)

    assert [row["symbol"] for row in surface["trades"]] == ["SC2608"]
    assert surface["meta"]["filtered_trades_count"] == 1
    assert surface["meta"]["filtered_positions_count"] == 0
    assert surface["meta"]["filtered_symbols"] == ["RB2501"]

    contamination = extract_account_contamination(capture)
    assert contamination["trades"] == 2


def test_build_strategy_surface_workflow_owned_events_unaffected():
    capture = _capture_payload()
    capture["meta"]["contract_map"] = {
        "SC888": {"symbol": "sc2608", "exchange": "INE", "enabled": True},
    }
    capture["captured"] = {
        "trades": [_captured_trade()],
        "positions": [_captured_position()],
        "orders": [],
    }

    surface = build_strategy_surface_from_captured_session(capture)

    assert len(surface["trades"]) == 1
    assert surface["trades"][0]["symbol"] == "SC2608"
    assert surface["trades"][0]["strategy"] == "simnow_trade"
    assert len(surface["positions"]) == 1
    assert surface["positions"][0]["strategy"] == "simnow_position"
    assert surface["meta"]["filtered_trades_count"] == 0
    assert surface["meta"]["filtered_positions_count"] == 0
    assert surface["meta"]["filtered_symbols"] == []
