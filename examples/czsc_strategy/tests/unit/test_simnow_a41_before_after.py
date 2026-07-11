"""Before/after evidence that A41's new defaults change unsafe old output.

Each test simulates the old priority/behavior and asserts it would have produced
a "pass" or silent-write outcome, then asserts the new default correctly
downgrades it to "unproven"/"unavailable"/staged-not-promoted.
"""

import sys
from pathlib import Path
from typing import Any


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_daily_monitor import evaluate_thresholds, make_record  # noqa: E402
from simnow_tick_bars import aggregate_ticks_to_1m, upsert_bars_to_sqlite  # noqa: E402


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


def _events() -> dict[str, Any]:
    return {
        "signals": [{"dt": "2026-07-01 10:00", "symbol": "AP888", "strategy": "二买多头", "operate": "LO"}],
        "trades": [{"dt": "2026-07-01 10:00", "symbol": "AP888", "strategy": "二买多头", "operate": "LO"}],
        "positions": [{"dt": "2026-07-01 10:00", "symbol": "AP888", "strategy": "二买多头", "operate": "HOLD"}],
    }


def _raw_snapshot() -> dict[str, Any]:
    return {
        "logs": [{"msg": "connected"}],
        "ticks": [{"dt": "2026-07-01 15:00", "symbol": "AP888"}],
        "contracts_count": 1,
        "accounts": [{"accountid": "demo"}],
        "positions": [],
    }


def test_finding2_old_placeholder_risk_would_pass_new_default_is_unproven():
    """Old priority chain used the all-zero placeholder and could reach pass.

    New default selects replay when available, and forces "unproven" when only
    the placeholder is available.
    """
    simnow: dict[str, Any] = {
        "meta": {
            "read_only": True,
            "orders_sent_by_workflow": 0,
            "workflow_order_actions": [],
            "strategy_surface": {"source": "captured_session"},
        },
        **_events(),
        "risk": _placeholder_risk(),
        "raw": _raw_snapshot(),
    }
    replay: dict[str, Any] = {"meta": {"replay_available": True}, **_events()}

    # Simulate the old one-line priority chain: risk or simnow.risk or replay.risk.
    from simnow_daily_monitor import build_thresholds, normalize_daily_metrics
    thresholds = build_thresholds(_baseline())
    old_metrics_source = simnow.get("risk") or replay.get("risk") or {}
    old_metrics = normalize_daily_metrics(old_metrics_source)
    old_result = evaluate_thresholds(old_metrics, thresholds)
    assert old_result["status"] == "pass", "old behavior would have passed on placeholder risk"

    # New default: only placeholder available -> unproven -> pending.
    record = make_record("2026-07-01", _baseline(), simnow=simnow, replay=replay)
    assert record["risk_source"] == "simnow_capture_placeholder"
    assert record["thresholds"]["status"] == "unproven"
    assert record["status"] == "pending"


def test_finding3_old_replay_surface_match_would_pass_new_default_is_unavailable():
    """Old consistency check used a replay-derived surface and could reach pass.

    New default requires a captured_session source and reports "unavailable".
    """
    simnow: dict[str, Any] = {
        "meta": {
            "read_only": True,
            "orders_sent_by_workflow": 0,
            "workflow_order_actions": [],
            "strategy_surface": {"source": "windowed_strategy_replay"},
        },
        **_events(),
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
        "raw": _raw_snapshot(),
    }
    replay: dict[str, Any] = {"meta": {"replay_available": True}, **_events()}

    # Old behavior: matching replay-derived surface -> pass.
    old_record = make_record(
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
    assert old_record["consistency"]["matched"] is True
    assert old_record["status"] == "pass", "old behavior would have passed on replay-derived surface"

    # New default: replay-derived surface is unavailable -> pending.
    new_record = make_record("2026-07-01", _baseline(), simnow=simnow, replay=replay)
    assert new_record["consistency"]["status"] == "unavailable"
    assert new_record["status"] == "pending"


def test_finding4_old_upsert_wrote_to_raw_new_default_stages(tmp_path):
    """Old upsert wrote directly to {symbol}_1M_raw; new default writes to staging."""
    payload: dict[str, Any] = {
        "meta": {
            "contract_map": {
                "AP888": {"symbol": "ap610", "exchange": "CZCE", "enabled": True},
            }
        },
        "raw": {
            "ticks": [
                {
                    "dt": "2026-07-01 09:00:00+08:00",
                    "symbol": "ap610",
                    "exchange": "CZCE",
                    "last_price": 100.0,
                    "volume": 1000,
                },
            ]
        },
    }
    db_path = tmp_path / "bars.db"
    bars = aggregate_ticks_to_1m(payload)

    # Old behavior simulation: direct write to raw table.
    import sqlite3
    upsert_bars_to_sqlite(db_path, bars, kline_write_mode="direct", allow_direct_write=True)
    with sqlite3.connect(db_path) as conn:
        old_raw_count = conn.execute("SELECT count(*) FROM ap888_1M_raw").fetchone()[0]
    assert old_raw_count == 1, "old behavior wrote directly to raw"

    # New default behavior on a fresh DB: staging only, raw untouched.
    db_path_new = tmp_path / "bars_new.db"
    upsert_bars_to_sqlite(db_path_new, bars)
    with sqlite3.connect(db_path_new) as conn:
        raw_exists = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='ap888_1M_raw'"
        ).fetchone()[0]
        new_staging_count = conn.execute("SELECT count(*) FROM ap888_1M_raw_staging").fetchone()[0]
    assert raw_exists == 0
    assert new_staging_count == 1
