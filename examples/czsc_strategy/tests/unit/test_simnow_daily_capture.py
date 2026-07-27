import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

CONTRACT_MAP_PATH = DIAG / "simnow_contract_map.json"

from simnow_daily_capture import (  # noqa: E402
    CaptureState,
    build_export,
    build_risk,
    contract_subscriptions,
    load_contract_map,
)
from simnow_daily_monitor import make_record  # noqa: E402


def test_load_contract_map_filters_disabled_and_validates(tmp_path):
    p = tmp_path / "map.json"
    p.write_text(
        """
        {
          "_meta": {"version": "V1", "effective_date": "2026-07-22"},
          "AP888": {"symbol": "ap610", "exchange": "CZCE", "enabled": true},
          "SC888": {"symbol": "sc2608", "exchange": "INE", "enabled": false}
        }
        """,
        encoding="utf-8",
    )
    data = load_contract_map(p)
    assert list(data) == ["AP888"]


def test_contract_subscriptions_deduplicates_real_contracts():
    rows = contract_subscriptions({
        "AP888": {"symbol": "ap610", "exchange": "CZCE", "vt_symbol": "ap610.CZCE"},
        "AP999": {"symbol": "ap610", "exchange": "CZCE", "vt_symbol": "ap610.CZCE"},
    })
    assert rows == [{
        "research_symbol": "AP888",
        "symbol": "ap610",
        "exchange": "CZCE",
        "vt_symbol": "ap610.CZCE",
    }]


def test_build_export_matches_daily_monitor_schema(tmp_path):
    state = CaptureState()
    state.logs.append({"dt": "2026-06-22 10:00:00", "msg": "connected"})
    state.ticks.append({"dt": "2026-06-22 10:00:01", "symbol": "ap610", "vt_symbol": "ap610.CZCE"})
    state.accounts["SIM"] = {"accountid": "SIM", "balance": 20000000, "available": 19990000}
    state.positions["ap610.CZCE.long"] = {
        "symbol": "ap610",
        "direction": "多",
        "volume": 1,
        "yd_volume": 0,
        "price": 100,
        "pnl": 0,
    }
    payload = build_export(
        state=state,
        config_path=tmp_path / "cfg.json",
        contract_map_path=tmp_path / "map.json",
        contract_map={"AP888": {"symbol": "ap610", "exchange": "CZCE"}},
        contract_map_provenance={
            "path": str(tmp_path / "map.json"),
            "version": "V1",
            "effective_date": "2026-07-22",
            "note": "",
            "enabled_symbols": ["AP888"],
            "enabled_count": 1,
        },
        started_at="2026-06-22T02:00:00+00:00",
        ended_at="2026-06-22T02:05:00+00:00",
        duration_seconds=300,
        setting_masked={"用户名": "xx***xx"},
    )

    assert set(["signals", "trades", "positions", "risk", "captured", "raw"]).issubset(payload)
    assert payload["meta"]["read_only"] is True
    assert payload["meta"]["orders_sent_by_workflow"] == 0
    assert payload["meta"]["workflow_order_actions"] == []
    assert payload["meta"]["contract_map_provenance"] == {
        "path": str(tmp_path / "map.json"),
        "version": "V1",
        "effective_date": "2026-07-22",
        "note": "",
        "enabled_symbols": ["AP888"],
        "enabled_count": 1,
    }
    assert payload["signals"] == []
    assert payload["trades"] == []
    assert payload["positions"] == []
    assert payload["captured"]["trades"] == []
    assert payload["captured"]["positions"][0]["symbol"] == "ap610"
    assert payload["raw"]["positions"][0]["symbol"] == "ap610"
    assert payload["risk"]["account_balance"] == 20000000

    baseline = {
        "candidate": "demo",
        "portfolio_risk": {
            "max_single_day_loss_pct": -1,
            "max_drawdown_pct": -1,
            "max_gross_exposure": 1,
            "max_net_exposure": 1,
            "max_both_long_short_symbols": 1,
            "max_consecutive_loss": {"days": 1, "cumulative_return_pct": -1},
            "symbol_concentration": {"top1_abs_share": 1},
            "strategy_concentration": {"top1_abs_share": 1},
        },
    }
    record = make_record(
        "2026-06-22",
        baseline,
        simnow=payload,
        replay={"signals": [], "trades": [], "positions": []},
        monitor_config={
            "risk_priority": "legacy_simnow_first",
            "consistency_source_mode": "replay_derived_allowed",
            "kline_write_mode": "staging",
        },
    )
    assert record["consistency"]["details"]["positions"]["matched"] is True


def test_build_risk_has_required_threshold_fields():
    risk = build_risk(CaptureState())
    for key in [
        "daily_return_pct",
        "drawdown_pct",
        "gross_exposure",
        "net_exposure",
        "both_long_short_symbols",
        "consecutive_loss",
        "symbol_concentration",
        "strategy_concentration",
    ]:
        assert key in risk


def test_live_contract_map_excludes_ap888_from_formal_observation_set():
    data = load_contract_map(CONTRACT_MAP_PATH)

    assert "AP888" not in data
    assert set(data) == {"SC888", "A888", "ZN888", "RB888"}
