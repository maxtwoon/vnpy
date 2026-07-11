import sys
from pathlib import Path
from typing import Any


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_daily_monitor import (  # noqa: E402
    _is_zero_placeholder_risk,
    evaluate_thresholds,
    make_record,
    select_risk_metrics,
)


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


def _placeholder_risk() -> dict[str, Any]:
    """The exact all-zero placeholder shape emitted by build_risk()."""
    return {
        "daily_return_pct": 0.0,
        "drawdown_pct": 0.0,
        "gross_exposure": 0.0,
        "net_exposure": 0.0,
        "both_long_short_symbols": 0,
        "consecutive_loss": {"days": 0, "cumulative_return_pct": 0.0},
        "symbol_concentration": {"top1_abs_share": 0.0},
        "strategy_concentration": {"top1_abs_share": 0.0},
    }


def _replay_risk() -> dict[str, Any]:
    """A replay-computed risk block with genuinely non-zero fields."""
    return {
        "daily_return_pct": -0.10,
        "drawdown_pct": -0.20,
        "gross_exposure": 0.10,
        "net_exposure": 0.10,
        "both_long_short_symbols": 0,
        "consecutive_loss": {"days": 1, "cumulative_return_pct": -0.01},
        "symbol_concentration": {"top1_abs_share": 0.20},
        "strategy_concentration": {"top1_abs_share": 0.20},
    }


def test_is_zero_placeholder_risk_detects_build_risk_placeholder():
    assert _is_zero_placeholder_risk(_placeholder_risk()) is True
    assert _is_zero_placeholder_risk({}) is True


def test_is_zero_placeholder_risk_rejects_non_zero_risk():
    risk = _placeholder_risk()
    risk["gross_exposure"] = 0.01
    assert _is_zero_placeholder_risk(risk) is False


def test_select_risk_metrics_prefers_replay_when_simnow_is_placeholder():
    simnow = {"risk": _placeholder_risk()}
    replay = {"risk": _replay_risk()}
    metrics, source = select_risk_metrics(None, simnow, replay, mode="replay_first")
    assert metrics == _replay_risk()
    assert source == "replay_computed"


def test_select_risk_metrics_prefers_simnow_when_not_placeholder():
    simnow = {"risk": _replay_risk()}
    replay = {"risk": _placeholder_risk()}
    metrics, source = select_risk_metrics(None, simnow, replay, mode="replay_first")
    assert metrics == _replay_risk()
    assert source == "simnow_capture"


def test_select_risk_metrics_legacy_mode_returns_placeholder():
    simnow = {"risk": _placeholder_risk()}
    replay = {"risk": _replay_risk()}
    metrics, source = select_risk_metrics(None, simnow, replay, mode="legacy_simnow_first")
    assert metrics == _placeholder_risk()
    assert source == "simnow_capture_placeholder"


def test_select_risk_metrics_explicit_risk_wins_over_both():
    explicit = {"gross_exposure": 0.99}
    simnow = {"risk": _placeholder_risk()}
    replay = {"risk": _replay_risk()}
    metrics, source = select_risk_metrics(explicit, simnow, replay, mode="replay_first")
    assert metrics == explicit
    assert source == "explicit_risk_json"


def test_evaluate_thresholds_downgrades_placeholder_risk_to_unproven():
    thresholds = {
        "gross_exposure": type("T", (), {"warning": 0.1, "halt": 0.2, "baseline": 0.2, "unit": ""}),
        "drawdown_abs_pct": type("T", (), {"warning": 0.5, "halt": 1.0, "baseline": 1.0, "unit": "%"}),
    }
    metrics = {"gross_exposure": 0.05, "drawdown_abs_pct": 0.1}
    result = evaluate_thresholds(metrics, thresholds, risk_source="simnow_capture_placeholder")
    assert result["status"] == "unproven"
    assert result["risk_source"] == "simnow_capture_placeholder"


def test_make_record_never_passes_on_placeholder_risk_only():
    """A fixture that would have passed under old behavior must not pass now."""
    simnow: dict[str, Any] = {
        "meta": {
            "read_only": True,
            "orders_sent_by_workflow": 0,
            "workflow_order_actions": [],
            "strategy_surface": {"source": "captured_session"},
        },
        "signals": [],
        "trades": [],
        "positions": [],
        "risk": _placeholder_risk(),
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
    assert record["risk_source"] == "simnow_capture_placeholder"
    assert record["thresholds"]["status"] == "unproven"
    assert record["status"] != "pass"
    assert record["status"] == "pending"


def test_make_record_passes_with_replay_risk_and_captured_surface():
    simnow: dict[str, Any] = {
        "meta": {
            "read_only": True,
            "orders_sent_by_workflow": 0,
            "workflow_order_actions": [],
            "strategy_surface": {"source": "captured_session"},
        },
        "signals": [],
        "trades": [],
        "positions": [],
        "risk": _placeholder_risk(),
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
        "risk": _replay_risk(),
    }
    record = make_record("2026-07-01", _baseline(), simnow=simnow, replay=replay)
    assert record["risk_source"] == "replay_computed"
    assert record["thresholds"]["status"] == "pass"
    assert record["status"] == "pass"


def test_make_record_legacy_mode_selects_placeholder_but_still_not_pass():
    """Legacy mode reproduces the old risk *selection* (placeholder returned),
    but the no-silent-pass guard still prevents a pass status.
    """
    simnow: dict[str, Any] = {
        "meta": {
            "read_only": True,
            "orders_sent_by_workflow": 0,
            "workflow_order_actions": [],
            "strategy_surface": {"source": "captured_session"},
        },
        "signals": [],
        "trades": [],
        "positions": [],
        "risk": _placeholder_risk(),
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
    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow=simnow,
        replay=replay,
        monitor_config={
            "risk_priority": "legacy_simnow_first",
            "consistency_source_mode": "replay_derived_allowed",
            "kline_write_mode": "staging",
        },
    )
    assert record["risk_source"] == "simnow_capture_placeholder"
    assert record["thresholds"]["status"] == "unproven"
    assert record["status"] == "pending"
