import sys
from pathlib import Path
from typing import Any


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_daily_monitor import compare_simnow_replay, make_record  # noqa: E402
from simnow_strategy_surface import build_strategy_surface_from_captured_session  # noqa: E402


def _baseline() -> dict[str, Any]:
    return {
        "candidate": "demo",
        "portfolio_risk": {
            "max_single_day_loss_pct": -0.30,
            "max_drawdown_pct": -1.30,
            "max_gross_exposure": 0.28,
            "max_net_exposure": 0.28,
            "max_both_long_short_symbols": 2,
            "max_consecutive_loss": {"days": 6, "cumulative_return_pct": -0.07},
            "symbol_concentration": {"top1_abs_share": 0.45},
            "strategy_concentration": {"top1_abs_share": 0.66},
        },
    }


def _captured_trade() -> dict[str, Any]:
    return {
        "dt": "2026-07-01 10:00:00",
        "symbol": "AP888",
        "strategy": "simnow_trade",
        "operate": "LONG",
        "offset": "OPEN",
        "price": 100.0,
        "volume": 1.0,
        "vt_tradeid": "t1",
    }


def _captured_position() -> dict[str, Any]:
    return {
        "dt": "2026-07-01 10:00:00",
        "symbol": "AP888",
        "strategy": "simnow_position",
        "operate": "POSITION",
        "direction": "多",
        "volume": 1.0,
        "yd_volume": 0.0,
        "price": 100.0,
        "pnl": 0.0,
    }


def test_build_strategy_surface_from_captured_session_uses_real_callbacks():
    capture: dict[str, Any] = {
        "captured": {
            "trades": [_captured_trade()],
            "positions": [_captured_position()],
            "orders": [],
        },
    }
    surface = build_strategy_surface_from_captured_session(capture)
    assert surface["meta"]["source"] == "captured_session"
    assert len(surface["trades"]) == 1
    assert surface["trades"][0]["symbol"] == "AP888"
    assert len(surface["positions"]) == 1


def test_compare_simnow_replay_require_captured_returns_unavailable_for_replay_surface():
    simnow: dict[str, Any] = {
        "meta": {
            "strategy_surface": {"source": "windowed_strategy_replay"},
        },
        "signals": [],
        "trades": [],
        "positions": [],
    }
    replay: dict[str, Any] = {
        "signals": [],
        "trades": [],
        "positions": [],
        "meta": {"replay_available": True},
    }
    result = compare_simnow_replay(simnow, replay, consistency_source_mode="require_captured")
    assert result["status"] == "unavailable"
    assert result["reason"] == "no_captured_session_data_only_replay_derived"
    assert "matched" not in result


def test_compare_simnow_replay_legacy_mode_allows_replay_surface_match():
    events = {
        "signals": [{"dt": "2026-07-01 10:00", "symbol": "AP888", "strategy": "二买多头", "operate": "LO"}],
        "trades": [{"dt": "2026-07-01 10:00", "symbol": "AP888", "strategy": "二买多头", "operate": "LO"}],
        "positions": [{"dt": "2026-07-01 10:00", "symbol": "AP888", "strategy": "二买多头", "operate": "HOLD"}],
    }
    simnow: dict[str, Any] = {
        "meta": {"strategy_surface": {"source": "windowed_strategy_replay"}},
        **events,
    }
    replay: dict[str, Any] = {"meta": {"replay_available": True}, **events}
    result = compare_simnow_replay(simnow, replay, consistency_source_mode="replay_derived_allowed")
    assert result["matched"] is True


def test_make_record_never_passes_when_consistency_unavailable():
    simnow: dict[str, Any] = {
        "meta": {
            "read_only": True,
            "orders_sent_by_workflow": 0,
            "workflow_order_actions": [],
            "strategy_surface": {"source": "windowed_strategy_replay"},
        },
        "signals": [],
        "trades": [],
        "positions": [],
        "risk": {
            "daily_return_pct": -0.10,
            "drawdown_pct": -0.20,
            "gross_exposure": 0.10,
            "net_exposure": 0.10,
            "both_long_short_symbols": 0,
            "consecutive_loss": {"days": 1, "cumulative_return_pct": -0.01},
            "symbol_concentration": {"top1_abs_share": 0.20},
            "strategy_concentration": {"top1_abs_share": 0.20},
        },
        "raw": {
            "logs": [{"msg": "connected"}],
            "ticks": [{"dt": "2026-07-01 15:00", "symbol": "AP888"}],
            "contracts_count": 1,
            "accounts": [{"accountid": "demo"}],
            "positions": [],
        },
    }
    replay: dict[str, Any] = {
        "signals": [],
        "trades": [],
        "positions": [],
        "meta": {"replay_available": True},
    }
    record = make_record("2026-07-01", _baseline(), simnow=simnow, replay=replay)
    assert record["consistency"]["status"] == "unavailable"
    assert record["status"] != "pass"
    assert record["status"] == "pending"


def test_make_record_passes_with_captured_session_surface_match():
    events = {
        "signals": [{"dt": "2026-07-01 10:00", "symbol": "AP888", "strategy": "二买多头", "operate": "LO"}],
        "trades": [{"dt": "2026-07-01 10:00", "symbol": "AP888", "strategy": "二买多头", "operate": "LO"}],
        "positions": [{"dt": "2026-07-01 10:00", "symbol": "AP888", "strategy": "二买多头", "operate": "HOLD"}],
    }
    simnow: dict[str, Any] = {
        "meta": {
            "read_only": True,
            "orders_sent_by_workflow": 0,
            "workflow_order_actions": [],
            "strategy_surface": {"source": "captured_session"},
        },
        **events,
        "risk": {
            "daily_return_pct": -0.10,
            "drawdown_pct": -0.20,
            "gross_exposure": 0.10,
            "net_exposure": 0.10,
            "both_long_short_symbols": 0,
            "consecutive_loss": {"days": 1, "cumulative_return_pct": -0.01},
            "symbol_concentration": {"top1_abs_share": 0.20},
            "strategy_concentration": {"top1_abs_share": 0.20},
        },
        "raw": {
            "logs": [{"msg": "connected"}],
            "ticks": [{"dt": "2026-07-01 15:00", "symbol": "AP888"}],
            "contracts_count": 1,
            "accounts": [{"accountid": "demo"}],
            "positions": [],
        },
    }
    replay: dict[str, Any] = {"meta": {"replay_available": True}, **events}
    record = make_record("2026-07-01", _baseline(), simnow=simnow, replay=replay)
    assert record["consistency"]["matched"] is True
    assert record["status"] == "pass"
