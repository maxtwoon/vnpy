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
    resolve_contract_map_for_subscription,
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
    assert set(data) == {"A888", "ZN888", "RB888"}


def test_resolve_contract_map_uses_account_activity_override_for_rollover():
    contract_map = {
        "SC888": {"symbol": "sc2608", "exchange": "INE", "vt_symbol": "sc2608.INE"},
        "RB888": {"symbol": "rb2610", "exchange": "SHFE", "vt_symbol": "rb2610.SHFE"},
    }
    state = CaptureState()
    state.contracts["sc2608.INE"] = {"symbol": "sc2608", "exchange": "INE", "vt_symbol": "sc2608.INE"}
    state.contracts["sc2609.INE"] = {"symbol": "sc2609", "exchange": "INE", "vt_symbol": "sc2609.INE"}
    state.contracts["rb2610.SHFE"] = {"symbol": "rb2610", "exchange": "SHFE", "vt_symbol": "rb2610.SHFE"}
    state.positions["sc2609.INE.short"] = {"symbol": "sc2609", "exchange": "INE", "volume": 1}

    resolved, details = resolve_contract_map_for_subscription(contract_map, state)

    assert resolved["SC888"]["symbol"] == "sc2609"
    assert resolved["SC888"]["vt_symbol"] == "sc2609.INE"
    assert details["SC888"]["source"] == "account_activity"
    assert details["SC888"]["account_activity_symbol"] == "sc2609"
    assert resolved["RB888"]["symbol"] == "rb2610"


def test_resolve_contract_map_keeps_default_when_query_still_contains_it():
    contract_map = {
        "A888": {"symbol": "a2609", "exchange": "DCE", "vt_symbol": "a2609.DCE"},
    }
    state = CaptureState()
    state.contracts["a2609.DCE"] = {"symbol": "a2609", "exchange": "DCE", "vt_symbol": "a2609.DCE"}
    state.contracts["a2611.DCE"] = {"symbol": "a2611", "exchange": "DCE", "vt_symbol": "a2611.DCE"}

    resolved, details = resolve_contract_map_for_subscription(contract_map, state)

    assert resolved["A888"]["symbol"] == "a2609"
    assert details["A888"]["source"] == "contract_query_default"
    assert details["A888"]["query_candidates"] == ["a2609", "a2611"]


def test_resolve_contract_map_uses_query_candidate_when_default_missing():
    contract_map = {
        "ZN888": {"symbol": "zn2608", "exchange": "SHFE", "vt_symbol": "zn2608.SHFE"},
    }
    state = CaptureState()
    state.contracts["zn2609.SHFE"] = {"symbol": "zn2609", "exchange": "SHFE", "vt_symbol": "zn2609.SHFE"}
    state.contracts["zn2610.SHFE"] = {"symbol": "zn2610", "exchange": "SHFE", "vt_symbol": "zn2610.SHFE"}

    resolved, details = resolve_contract_map_for_subscription(contract_map, state)

    assert resolved["ZN888"]["symbol"] == "zn2610"
    assert resolved["ZN888"]["vt_symbol"] == "zn2610.SHFE"
    assert details["ZN888"]["source"] == "contract_query_roll_forward"
    assert details["ZN888"]["query_candidates"] == ["zn2609", "zn2610"]


def test_build_export_includes_contract_resolution_metadata(tmp_path):
    state = CaptureState()
    payload = build_export(
        state=state,
        config_path=tmp_path / "cfg.json",
        contract_map_path=tmp_path / "map.json",
        contract_map={"SC888": {"symbol": "sc2609", "exchange": "INE", "vt_symbol": "sc2609.INE"}},
        contract_map_provenance={
            "path": str(tmp_path / "map.json"),
            "version": "V1",
            "effective_date": "2026-08-11",
            "note": "",
            "enabled_symbols": ["SC888"],
            "enabled_count": 1,
        },
        started_at="2026-08-11T05:39:31+00:00",
        ended_at="2026-08-11T07:01:11+00:00",
        duration_seconds=4900,
        setting_masked={},
        contract_map_resolution={
            "SC888": {
                "source": "account_activity",
                "default_symbol": "sc2608",
                "resolved_symbol": "sc2609",
                "query_candidates": ["sc2608", "sc2609"],
                "account_activity_symbol": "sc2609",
            }
        },
    )

    assert payload["meta"]["contract_map"]["SC888"]["symbol"] == "sc2609"
    assert payload["meta"]["contract_map_resolution"]["SC888"]["source"] == "account_activity"
