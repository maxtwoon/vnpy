import sys
from pathlib import Path
from typing import Any


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_action_summary import action_recommendation, build_action_summary  # noqa: E402
from simnow_daily_monitor import (  # noqa: E402
    build_20d_report,
    build_thresholds,
    compare_simnow_replay,
    evaluate_thresholds,
    load_json,
    load_thresholds_config,
    make_record,
    normalize_daily_metrics,
    read_ledger,
    upsert_ledger,
    write_20d_markdown,
)
from simnow_promotion_decision import decide_promotion, write_report  # noqa: E402


def _baseline():
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


def _events():
    return {
        "signals": [{"dt": "2026-06-19 14:30", "symbol": "AP888", "strategy": "二买多头", "operate": "LO"}],
        "trades": [{"dt": "2026-06-19 15:00", "symbol": "AP888", "strategy": "二买多头", "operate": "LO"}],
        "positions": [{"dt": "2026-06-19 15:00", "symbol": "AP888", "strategy": "二买多头", "operate": "HOLD"}],
    }


def test_thresholds_warn_before_halt():
    thresholds = build_thresholds(_baseline())
    warning_metrics = normalize_daily_metrics({
        "daily_return_pct": -0.28,
        "drawdown_pct": -1.0,
        "gross_exposure": 0.20,
        "net_exposure": 0.20,
        "both_long_short_symbols": 1,
        "consecutive_loss": {"days": 1, "cumulative_return_pct": -0.02},
        "symbol_concentration": {"top1_abs_share": 0.40},
        "strategy_concentration": {"top1_abs_share": 0.40},
    })
    halted_metrics = dict(warning_metrics, gross_exposure=0.29)

    assert evaluate_thresholds(warning_metrics, thresholds)["status"] == "warning"
    assert evaluate_thresholds(halted_metrics, thresholds)["status"] == "halt"


def test_threshold_config_can_override_baseline(tmp_path):
    path = tmp_path / "thresholds.json"
    path.write_text(
        """
        {
          "schema_version": 1,
          "metrics": {
            "gross_exposure": {
              "baseline": 0.5,
              "warning": 0.4,
              "halt": 0.5,
              "direction": "high",
              "unit": ""
            }
          }
        }
        """,
        encoding="utf-8",
    )
    thresholds = load_thresholds_config(path)
    assert thresholds["gross_exposure"].warning == 0.4

    record = make_record(
        "2026-06-19",
        _baseline(),
        simnow=_events(),
        replay=_events(),
        risk={"gross_exposure": 0.45},
        thresholds=thresholds,
    )
    assert record["thresholds"]["status"] == "warning"


def test_load_json_accepts_utf8_bom(tmp_path):
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"meta":{"replay_available":false}}')

    payload = load_json(path)

    assert payload["meta"]["replay_available"] is False


def test_compare_simnow_replay_requires_exact_event_surface_match():
    assert compare_simnow_replay(_events(), _events())["matched"] is True

    changed = _events()
    changed["trades"] = []
    result = compare_simnow_replay(changed, _events())
    assert result["matched"] is False


def test_compare_simnow_replay_filters_replay_to_capture_window():
    simnow: dict[str, Any] = {
        "meta": {
            "strategy_surface": {
                "window_start": "2026-07-07T09:14:59+08:00",
                "window_end": "2026-07-07T09:19:59+08:00",
            }
        },
        "signals": [],
        "trades": [],
        "positions": [],
    }
    replay: dict[str, Any] = {
        "signals": [{"dt": "2026-07-07 14:59:00", "symbol": "AP888", "strategy": "signal_snapshot", "operate": "SIGNAL"}],
        "trades": [{"dt": "2026-07-07 23:29:00", "symbol": "SC888", "strategy": "strategy_trade", "operate": "CLOSE"}],
        "positions": [{"dt": "2026-07-07 22:59:00", "symbol": "RB888", "strategy": "portfolio", "operate": "POSITION"}],
        "meta": {"replay_available": True},
    }
    result = compare_simnow_replay(simnow, replay)
    assert result["matched"] is True
    assert result["reason"] == "no_actionable_events_on_either_side"


def test_compare_simnow_replay_reports_event_surface_mismatch_reason():
    simnow: dict[str, Any] = {
        "signals": [],
        "trades": [{"dt": "2026-07-07 09:14:59+08:00", "symbol": "sc2608", "strategy": "simnow_trade", "operate": "LONG"}],
        "positions": [],
    }
    replay: dict[str, Any] = {
        "signals": [{"dt": "2026-07-07 14:59:00", "symbol": "AP888", "strategy": "signal_snapshot", "operate": "SIGNAL"}],
        "trades": [{"dt": "2026-07-07 23:29:00", "symbol": "SC888", "strategy": "strategy_trade", "operate": "CLOSE"}],
        "positions": [{"dt": "2026-07-07 14:59:00", "symbol": "AP888", "strategy": "portfolio", "operate": "POSITION"}],
        "meta": {"replay_available": True},
    }
    result = compare_simnow_replay(simnow, replay)
    assert result["matched"] is False
    assert result["reason"] == "event_surface_mismatch"
    assert result["reason"] == "event_surface_mismatch"
    assert result["reason"] == "event_surface_mismatch"
    assert result["details"]["trades"]["missing_in_simnow"]


def test_compare_simnow_replay_keeps_unavailable_replay_pending():
    result = compare_simnow_replay(
        {"signals": [], "trades": [], "positions": []},
        {"signals": [], "trades": [], "positions": [], "meta": {"replay_available": False}},
    )
    assert result["matched"] is False
    assert result["reason"] == "replay_unavailable"


def test_compare_simnow_replay_uses_specific_unavailable_reason():
    result = compare_simnow_replay(
        {"signals": [], "trades": [], "positions": []},
        {
            "signals": [],
            "trades": [],
            "positions": [],
            "meta": {
                "replay_available": False,
                "replay_unavailable_reason": "historical_db_lag",
            },
        },
    )
    assert result["matched"] is False
    assert result["reason"] == "historical_db_lag"


def test_make_record_classifies_disconnect_empty_snapshot_as_skipped():
    record = make_record(
        "2026-06-27",
        _baseline(),
        simnow={
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "disconnect 097"}],
                "ticks": [],
                "contracts_count": 0,
                "accounts": [],
                "positions": [],
            },
        },
        replay={},
    )

    assert record["status"] == "skipped"
    assert record["skip_reason"] == "ctp_disconnect_097_no_snapshot"
    assert record["consistency"]["reason"] == "ctp_disconnect_097_no_snapshot"


def test_make_record_classifies_connected_snapshot_without_ticks_as_skipped():
    record = make_record(
        "2026-07-02",
        _baseline(),
        simnow={
            "meta": {"read_only": True, "orders_sent_by_workflow": 0, "workflow_order_actions": []},
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "connected"}],
                "ticks": [],
                "contracts_count": 100,
                "accounts": [{"accountid": "demo"}],
                "positions": [],
                "subscribed": [{"research_symbol": "AP888"}],
            },
        },
        replay={
            "signals": [],
            "trades": [],
            "positions": [],
            "meta": {"replay_available": False, "replay_unavailable_reason": "historical_db_lag"},
        },
        kline={"missing_symbols": ["AP888"]},
    )

    assert record["status"] == "skipped"
    assert record["skip_reason"] == "simnow_no_ticks"
    assert record["consistency"]["reason"] == "simnow_no_ticks"
    assert record["valid_observation"] is False


def test_make_record_combines_consistency_threshold_and_attribution():
    simnow = _events()
    simnow["raw"] = {
        "logs": [{"msg": "connected"}],
        "ticks": [{"dt": "2026-06-19 14:30", "symbol": "AP888"}],
        "contracts_count": 1,
        "accounts": [{"accountid": "demo"}],
        "positions": [{"symbol": "AP888"}],
    }
    replay = _events()
    replay["meta"] = {"replay_available": True}
    simnow["trades"].append({
        "dt": "2026-06-19 15:00",
        "symbol": "SC888",
        "strategy": "三卖空头 short",
        "operate": "SC",
        "pnl_pct": -0.01,
    })
    replay["trades"] = list(simnow["trades"])
    record = make_record(
        "2026-06-19",
        _baseline(),
        simnow=simnow,
        replay=replay,
        risk={
            "daily_return_pct": -0.10,
            "drawdown_pct": -0.20,
            "gross_exposure": 0.10,
            "net_exposure": 0.10,
            "both_long_short_symbols": 0,
            "consecutive_loss": {"days": 1, "cumulative_return_pct": -0.01},
            "symbol_concentration": {"top1_abs_share": 0.20},
            "strategy_concentration": {"top1_abs_share": 0.20},
        },
    )

    assert record["status"] == "pass"
    assert record["consistency"]["matched"] is True
    assert record["attribution_watch"]["SC_SHORT"]["count"] == 1


def test_make_record_reports_missing_enabled_subscriptions_before_replay_lag():
    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow={
            "meta": {
                "contract_map": {
                    "AP888": {"enabled": True},
                    "SC888": {"enabled": True},
                    "RB888": {"enabled": False},
                }
            },
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "connected"}],
                "ticks": [{"dt": "2026-07-01 15:00", "symbol": "SC888"}],
                "contracts_count": 1,
                "accounts": [{"accountid": "demo"}],
                "positions": [],
                "subscribed": [{"research_symbol": "SC888"}],
            },
        },
        replay={
            "signals": [],
            "trades": [],
            "positions": [],
            "meta": {
                "replay_available": False,
                "replay_unavailable_reason": "historical_db_lag",
            },
        },
    )

    assert record["status"] == "pending"
    assert record["consistency"]["reason"] == "subscription_incomplete"
    assert record["subscription_coverage"]["missing_symbols"] == ["AP888"]


def test_make_record_reports_incomplete_kline_coverage_before_replay_lag():
    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow={
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "connected"}],
                "ticks": [{"dt": "2026-07-01 15:00", "symbol": "SC888"}],
                "contracts_count": 1,
                "accounts": [{"accountid": "demo"}],
                "positions": [],
            },
        },
        replay={
            "signals": [],
            "trades": [],
            "positions": [],
            "meta": {
                "replay_available": False,
                "replay_unavailable_reason": "historical_db_lag",
            },
        },
        kline={
            "expected_symbols": ["AP888", "SC888"],
            "symbols": ["SC888"],
            "missing_symbols": ["AP888"],
            "coverage_by_symbol": {
                "SC888": {
                    "bars": 1,
                    "tick_count": 1,
                    "start_datetime": "2026-07-01 15:00:00",
                    "end_datetime": "2026-07-01 15:00:00",
                }
            },
        },
    )

    assert record["status"] == "pending"
    assert record["consistency"]["reason"] == "kline_coverage_incomplete"
    assert record["kline_coverage"]["missing_symbols"] == ["AP888"]


def test_make_record_reports_too_short_kline_coverage_before_replay_lag():
    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow={
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "connected"}],
                "ticks": [{"dt": "2026-07-01 15:00", "symbol": "SC888"}],
                "contracts_count": 1,
                "accounts": [{"accountid": "demo"}],
                "positions": [],
            },
        },
        replay={
            "signals": [],
            "trades": [],
            "positions": [],
            "meta": {
                "replay_available": False,
                "replay_unavailable_reason": "historical_db_lag",
            },
        },
        kline={
            "expected_symbols": ["SC888"],
            "symbols": ["SC888"],
            "missing_symbols": [],
            "short_symbols": ["SC888"],
            "min_bars_per_symbol": 30,
            "coverage_by_symbol": {
                "SC888": {
                    "bars": 1,
                    "tick_count": 1,
                    "start_datetime": "2026-07-01 15:00:00",
                    "end_datetime": "2026-07-01 15:00:00",
                }
            },
        },
    )

    assert record["status"] == "pending"
    assert record["consistency"]["reason"] == "kline_coverage_too_short"
    assert record["consistency"]["kline_short_symbols"] == ["SC888"]


def test_make_record_halts_when_workflow_order_safety_is_breached():
    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow={
            "meta": {
                "read_only": False,
                "orders_sent_by_workflow": 1,
                "workflow_order_actions": [{"symbol": "AP888", "action": "send_order"}],
            },
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "connected"}],
                "ticks": [{"dt": "2026-07-01 15:00", "symbol": "SC888"}],
                "contracts_count": 1,
                "accounts": [{"accountid": "demo"}],
                "positions": [],
                "orders": [{"symbol": "AP888"}],
                "trades": [{"symbol": "AP888"}],
            },
        },
        replay={"signals": [], "trades": [], "positions": [], "meta": {"replay_available": True}},
    )

    assert record["status"] == "halt"
    assert record["order_safety"]["status"] == "halt"
    assert record["order_safety"]["orders_sent_by_workflow"] == 1
    assert record["order_safety"]["observed_raw_orders"] == 1
    assert record["order_safety"]["observed_raw_trades"] == 1
    assert record["consistency"]["reason"] == "workflow_order_safety_breach"


def test_make_record_allows_observed_account_orders_when_workflow_is_read_only():
    simnow = _events()
    simnow["meta"] = {"read_only": True, "orders_sent_by_workflow": 0, "workflow_order_actions": []}
    simnow["raw"] = {
        "logs": [{"msg": "connected"}],
        "ticks": [{"dt": "2026-07-01 15:00", "symbol": "AP888"}],
        "contracts_count": 1,
        "accounts": [{"accountid": "demo"}],
        "positions": [],
        "orders": [{"symbol": "AP888"}],
        "trades": [{"symbol": "AP888"}],
    }
    replay = _events()
    replay["meta"] = {"replay_available": True}

    record = make_record("2026-07-01", _baseline(), simnow=simnow, replay=replay)

    assert record["status"] == "pass"
    assert record["order_safety"]["status"] == "pass"
    assert record["order_safety"]["observed_raw_orders"] == 1
    assert record["order_safety"]["observed_raw_trades"] == 1


def test_make_record_infers_legacy_read_only_when_new_order_fields_never_existed():
    simnow = {
        "signals": [{"dt": "2026-06-22 15:22", "symbol": "AP888", "strategy": "second_buy", "operate": "LO"}],
        "trades": [{"dt": "2026-06-22 15:23", "symbol": "AP888", "strategy": "second_buy", "operate": "LO"}],
        "positions": [{"dt": "2026-06-22 15:24", "symbol": "AP888", "strategy": "second_buy", "operate": "HOLD"}],
    }
    simnow["meta"] = {
        "generated_at": "2026-06-22T07:26:24.155182+00:00",
        "started_at": "2026-06-22T07:21:23.265502+00:00",
        "ended_at": "2026-06-22T07:26:23.598245+00:00",
        "duration_seconds": 300,
        "contract_map": {"AP888": {"enabled": True}},
        "strategy_surface": {
            "source": "windowed_strategy_replay",
            "window_start": "2026-06-22T15:21:23.265502+08:00",
            "window_end": "2026-06-22T15:26:23.598245+08:00",
            "trade_date": "2026-06-22",
        },
    }
    simnow["raw"] = {
        "logs": [{"msg": "connected"}],
        "ticks": [{"dt": "2026-06-22 15:21:23", "symbol": "AP888"}],
        "contracts_count": 1,
        "accounts": [{"accountid": "demo"}],
        "positions": [],
        "subscribed": [{"research_symbol": "AP888"}],
    }
    replay = {
        "signals": [{"dt": "2026-06-22 15:22", "symbol": "AP888", "strategy": "second_buy", "operate": "LO"}],
        "trades": [{"dt": "2026-06-22 15:23", "symbol": "AP888", "strategy": "second_buy", "operate": "LO"}],
        "positions": [{"dt": "2026-06-22 15:24", "symbol": "AP888", "strategy": "second_buy", "operate": "HOLD"}],
    }
    replay["meta"] = {"replay_available": True}

    record = make_record(
        "2026-06-22",
        _baseline(),
        simnow=simnow,
        replay=replay,
        kline={
            "expected_symbols": ["AP888"],
            "symbols": ["AP888"],
            "missing_symbols": [],
            "short_symbols": [],
            "min_bars_per_symbol": 30,
        },
    )

    assert record["status"] == "pass"
    assert record["order_safety"]["status"] == "pass"
    assert record["order_safety"]["read_only"] is True
    assert record["order_safety"]["orders_sent_by_workflow"] == 0
    assert record["order_safety"]["workflow_order_actions"] == []
    assert record["order_safety"]["legacy_inferred"] is True
    assert record["valid_observation"] is True


def test_make_record_marks_only_fully_matched_safe_days_as_valid_observations():
    simnow = _events()
    simnow["meta"] = {"read_only": True, "orders_sent_by_workflow": 0, "workflow_order_actions": []}
    simnow["raw"] = {
        "logs": [{"msg": "connected"}],
        "ticks": [{"dt": "2026-07-01 15:00", "symbol": "AP888"}],
        "contracts_count": 1,
        "accounts": [{"accountid": "demo"}],
        "positions": [],
        "subscribed": [{"research_symbol": "AP888"}],
    }
    simnow["meta"]["contract_map"] = {"AP888": {"enabled": True}}
    replay = _events()
    replay["meta"] = {"replay_available": True}

    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow=simnow,
        replay=replay,
        kline={
            "expected_symbols": ["AP888"],
            "symbols": ["AP888"],
            "missing_symbols": [],
            "short_symbols": [],
            "min_bars_per_symbol": 30,
        },
    )

    assert record["status"] == "pass"
    assert record["valid_observation"] is True

    record["order_safety"]["status"] = "unknown"
    record["valid_observation"] = False
    assert record["valid_observation"] is False


def test_20d_report_requires_twenty_clean_days():
    records = [
        {
            "date": f"2026-06-{day:02d}",
            "status": "pass",
            "consistency": {"matched": True},
            "thresholds": {"status": "pass"},
            "order_safety": {"status": "pass"},
            "subscription_coverage": {"missing_symbols": []},
            "kline_coverage": {"missing_symbols": [], "short_symbols": []},
            "valid_observation": True,
        }
        for day in range(1, 21)
    ]
    assert build_20d_report(records)["ready_to_expand"] is True

    records[-1]["thresholds"] = {"status": "halt"}
    assert build_20d_report(records)["ready_to_expand"] is False


def test_20d_report_tracks_pending_skipped_reasons_and_clean_streak(tmp_path):
    records = [
        {
            "date": "2026-06-17",
            "status": "pass",
            "consistency": {"matched": True},
            "thresholds": {"status": "pass"},
            "order_safety": {"status": "pass"},
            "subscription_coverage": {"missing_symbols": []},
            "kline_coverage": {"missing_symbols": [], "short_symbols": []},
            "valid_observation": True,
        },
        {
            "date": "2026-06-18",
            "status": "pending",
            "consistency": {"matched": False, "reason": "replay_unavailable"},
            "thresholds": {"status": "pass"},
            "subscription_coverage": {"missing_symbols": ["AP888"]},
            "kline_coverage": {"missing_symbols": ["AP888"], "short_symbols": ["SC888"]},
        },
        {
            "date": "2026-06-19",
            "status": "skipped",
            "skip_reason": "holiday",
            "consistency": {"matched": False},
            "thresholds": {"status": "pass"},
        },
        {
            "date": "2026-06-22",
            "status": "pass",
            "consistency": {"matched": True},
            "thresholds": {"status": "pass"},
            "order_safety": {"status": "pass"},
            "subscription_coverage": {"missing_symbols": []},
            "kline_coverage": {"missing_symbols": [], "short_symbols": []},
            "valid_observation": True,
        },
    ]
    summary = build_20d_report(records, min_days=5)
    assert summary["valid_observation_days"] == 2
    assert summary["pending_days"] == 1
    assert summary["skipped_days"] == 1
    assert summary["reason_counts"] == {"holiday": 1, "replay_unavailable": 1}
    assert summary["last_valid_observation_date"] == "2026-06-22"
    assert summary["consecutive_clean_days"] == 1
    assert "need_3_more_valid_observation_days" in summary["promotion_blockers"]

    out = tmp_path / "report.md"
    write_20d_markdown(summary, out)
    text = out.read_text(encoding="utf-8")
    assert "## Status Counts" in text
    assert "## Pending / Skipped / Risk Reasons" in text
    assert "| replay_unavailable | 1 |" in text
    assert "| holiday | 1 |" in text
    assert "kline_missing" in text
    assert "kline_short" in text
    assert "subscription_missing" in text
    assert "valid_observation_days" in text
    assert "valid" in text
    assert "AP888" in text
    assert "SC888" in text


def test_upsert_ledger_replaces_same_date_and_keeps_sorted(tmp_path):
    path = tmp_path / "ledger.jsonl"
    upsert_ledger(path, {"date": "2026-06-20", "status": "pass", "version": 1})
    upsert_ledger(path, {"date": "2026-06-19", "status": "pass", "version": 1})
    upsert_ledger(path, {"date": "2026-06-20", "status": "pass", "version": 2})

    rows = read_ledger(path)
    assert [row["date"] for row in rows] == ["2026-06-19", "2026-06-20"]
    assert rows[-1]["version"] == 2


def test_promotion_decision_reports_ready_only_when_all_days_pass():
    records = [
        {
            "date": f"2026-06-{day:02d}",
            "status": "pass",
            "consistency": {"matched": True},
            "thresholds": {"status": "pass"},
            "order_safety": {"status": "pass"},
            "subscription_coverage": {"missing_symbols": []},
            "kline_coverage": {"missing_symbols": [], "short_symbols": []},
            "valid_observation": True,
        }
        for day in range(1, 21)
    ]
    summary = decide_promotion(records, min_days=20)
    assert summary["ready_to_expand"] is True
    assert summary["promotion_blockers"] == []
    assert summary["valid_observation_days"] == 20
    assert summary["last_valid_observation_date"] == "2026-06-20"


def test_promotion_decision_reports_blockers_and_writes_markdown(tmp_path):
    records = [
        {
            "date": "2026-06-19",
            "status": "pass",
            "consistency": {"matched": True},
            "thresholds": {"status": "pass"},
            "order_safety": {"status": "pass"},
            "subscription_coverage": {"missing_symbols": []},
            "kline_coverage": {"missing_symbols": [], "short_symbols": []},
            "valid_observation": True,
        },
        {
            "date": "2026-06-20",
            "status": "pending",
            "consistency": {"matched": False, "reason": "replay_unavailable"},
            "thresholds": {"status": "pass"},
        },
    ]
    summary = decide_promotion(records, min_days=20)
    assert summary["ready_to_expand"] is False
    assert "need_19_more_valid_observation_days" in summary["promotion_blockers"]
    assert "pending_days_present" in summary["promotion_blockers"]

    out = tmp_path / "promotion.md"
    write_report(summary, out)
    text = out.read_text(encoding="utf-8")
    assert "# SimNow 20-Day Promotion Decision" in text
    assert "Candidate cannot expand yet." in text
    assert "blocker: pending_days_present" in text


def _valid_simnow_and_replay():
    simnow = _events()
    simnow["meta"] = {
        "read_only": True,
        "orders_sent_by_workflow": 0,
        "workflow_order_actions": [],
        "contract_map": {"AP888": {"enabled": True}},
    }
    simnow["raw"] = {
        "logs": [{"msg": "connected"}],
        "ticks": [{"dt": "2026-07-01 15:00", "symbol": "AP888"}],
        "contracts_count": 1,
        "accounts": [{"accountid": "demo"}],
        "positions": [],
        "subscribed": [{"research_symbol": "AP888"}],
    }
    replay = _events()
    replay["meta"] = {"replay_available": True}
    return simnow, replay


def test_action_recommendation_pass_valid_counts_for_20d():
    simnow, replay = _valid_simnow_and_replay()
    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow=simnow,
        replay=replay,
        kline={
            "expected_symbols": ["AP888"],
            "symbols": ["AP888"],
            "missing_symbols": [],
            "short_symbols": [],
            "min_bars_per_symbol": 30,
        },
    )
    rec = action_recommendation(record)
    assert rec["status"] == "pass"
    assert rec["reason"] == ""
    assert rec["severity"] == "ok"
    assert rec["counts_for_20d"] is True
    assert "计入 20 日有效观察" in rec["action"]


def test_action_recommendation_pass_invalid_lists_gaps():
    simnow, replay = _valid_simnow_and_replay()
    # Remove read_only declaration so order_safety is unknown
    simnow["meta"].pop("read_only")
    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow=simnow,
        replay=replay,
        kline={
            "expected_symbols": ["AP888"],
            "symbols": ["AP888"],
            "missing_symbols": [],
            "short_symbols": [],
            "min_bars_per_symbol": 30,
        },
    )
    assert record["status"] == "pass"
    assert record["valid_observation"] is False
    rec = action_recommendation(record)
    assert rec["severity"] == "warning"
    assert rec["counts_for_20d"] is False
    assert "gate" in rec["action"]
    assert "order_safety" in rec["action"]


def test_action_recommendation_skipped_no_ticks():
    record = make_record(
        "2026-07-02",
        _baseline(),
        simnow={
            "meta": {"read_only": True, "orders_sent_by_workflow": 0, "workflow_order_actions": []},
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "connected"}],
                "ticks": [],
                "contracts_count": 100,
                "accounts": [{"accountid": "demo"}],
                "positions": [],
                "subscribed": [{"research_symbol": "AP888"}],
            },
        },
        replay={"signals": [], "trades": [], "positions": [], "meta": {"replay_available": False}},
    )
    rec = action_recommendation(record)
    assert rec["status"] == "skipped"
    assert rec["reason"] == "simnow_no_ticks"
    assert rec["severity"] == "info"
    assert rec["counts_for_20d"] is False
    assert "节假日" in rec["action"] or "非交易时段" in rec["action"]


def test_action_recommendation_skipped_disconnect():
    record = make_record(
        "2026-06-27",
        _baseline(),
        simnow={
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "disconnect 097"}],
                "ticks": [],
                "contracts_count": 0,
                "accounts": [],
                "positions": [],
            },
        },
        replay={},
    )
    rec = action_recommendation(record)
    assert rec["status"] == "skipped"
    assert rec["reason"] == "ctp_disconnect_097_no_snapshot"
    assert rec["severity"] == "info"
    assert "CTP 连接失败" in rec["action"]


def test_action_recommendation_pending_historical_db_lag():
    record = make_record(
        "2026-06-22",
        _baseline(),
        simnow={
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "connected"}],
                "ticks": [{"dt": "2026-06-22 15:00", "symbol": "AP888"}],
                "contracts_count": 1,
                "accounts": [{"accountid": "demo"}],
                "positions": [],
            },
        },
        replay={
            "signals": [],
            "trades": [],
            "positions": [],
            "meta": {
                "replay_available": False,
                "replay_unavailable_reason": "historical_db_lag",
            },
        },
    )
    rec = action_recommendation(record)
    assert rec["status"] == "pending"
    assert rec["reason"] == "historical_db_lag"
    assert rec["severity"] == "medium"
    assert rec["counts_for_20d"] is False
    assert "历史 DB" in rec["action"] and "backfill" in rec["action"]


def test_action_recommendation_pending_subscription_incomplete():
    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow={
            "meta": {
                "contract_map": {
                    "AP888": {"enabled": True},
                    "SC888": {"enabled": True},
                }
            },
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "connected"}],
                "ticks": [{"dt": "2026-07-01 15:00", "symbol": "SC888"}],
                "contracts_count": 1,
                "accounts": [{"accountid": "demo"}],
                "positions": [],
                "subscribed": [{"research_symbol": "SC888"}],
            },
        },
        replay={"signals": [], "trades": [], "positions": [], "meta": {"replay_available": True}},
    )
    rec = action_recommendation(record)
    assert rec["status"] == "pending"
    assert rec["reason"] == "subscription_incomplete"
    assert "AP888" in rec["action"]
    assert "simnow_contract_map.json" in rec["action"]


def test_action_recommendation_pending_kline_coverage_incomplete():
    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow={
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "connected"}],
                "ticks": [{"dt": "2026-07-01 15:00", "symbol": "SC888"}],
                "contracts_count": 1,
                "accounts": [{"accountid": "demo"}],
                "positions": [],
            },
        },
        replay={"signals": [], "trades": [], "positions": [], "meta": {"replay_available": True}},
        kline={
            "expected_symbols": ["AP888", "SC888"],
            "symbols": ["SC888"],
            "missing_symbols": ["AP888"],
            "short_symbols": [],
        },
    )
    rec = action_recommendation(record)
    assert rec["status"] == "pending"
    assert rec["reason"] == "kline_coverage_incomplete"
    assert "AP888" in rec["action"]
    assert "重新采集" in rec["action"]


def test_action_recommendation_pending_kline_coverage_too_short():
    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow={
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "connected"}],
                "ticks": [{"dt": "2026-07-01 15:00", "symbol": "SC888"}],
                "contracts_count": 1,
                "accounts": [{"accountid": "demo"}],
                "positions": [],
            },
        },
        replay={"signals": [], "trades": [], "positions": [], "meta": {"replay_available": True}},
        kline={
            "expected_symbols": ["SC888"],
            "symbols": ["SC888"],
            "missing_symbols": [],
            "short_symbols": ["SC888"],
            "min_bars_per_symbol": 30,
        },
    )
    rec = action_recommendation(record)
    assert rec["status"] == "pending"
    assert rec["reason"] == "kline_coverage_too_short"
    assert "SC888" in rec["action"]
    assert "30" in rec["action"]
    assert "DurationSeconds" in rec["action"]


def test_action_recommendation_pending_event_surface_mismatch():
    record = make_record(
        "2026-07-07",
        _baseline(),
        simnow={
            "meta": {"read_only": True, "orders_sent_by_workflow": 0, "workflow_order_actions": []},
            "signals": [],
            "trades": [{"dt": "2026-07-07 09:14:59+08:00", "symbol": "sc2608", "strategy": "simnow_trade", "operate": "LONG"}],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "connected"}],
                "ticks": [{"dt": "2026-07-07 09:14:59+08:00", "symbol": "sc2608"}],
                "contracts_count": 1,
                "accounts": [{"accountid": "demo"}],
                "positions": [],
                "subscribed": [{"research_symbol": "SC888"}],
            },
        },
        replay={
            "signals": [{"dt": "2026-07-07 14:59:00", "symbol": "AP888", "strategy": "signal_snapshot", "operate": "SIGNAL"}],
            "trades": [{"dt": "2026-07-07 23:29:00", "symbol": "SC888", "strategy": "strategy_trade", "operate": "CLOSE"}],
            "positions": [{"dt": "2026-07-07 14:59:00", "symbol": "AP888", "strategy": "portfolio", "operate": "POSITION"}],
            "meta": {"replay_available": True},
        },
    )
    rec = action_recommendation(record)
    assert rec["status"] == "pending"
    assert rec["reason"] == "event_surface_mismatch"
    assert "SimNow" in rec["action"]
    assert "replay" in rec["action"]


def test_action_recommendation_halt_workflow_order_safety_breach():
    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow={
            "meta": {
                "read_only": False,
                "orders_sent_by_workflow": 1,
                "workflow_order_actions": [{"symbol": "AP888", "action": "send_order"}],
            },
            "signals": [],
            "trades": [],
            "positions": [],
            "risk": {},
            "raw": {
                "logs": [{"msg": "connected"}],
                "ticks": [{"dt": "2026-07-01 15:00", "symbol": "SC888"}],
                "contracts_count": 1,
                "accounts": [{"accountid": "demo"}],
                "positions": [],
            },
        },
        replay={"signals": [], "trades": [], "positions": [], "meta": {"replay_available": True}},
    )
    rec = action_recommendation(record)
    assert rec["status"] == "halt"
    assert rec["reason"] == "workflow_order_safety_breach"
    assert rec["severity"] == "critical"
    assert "停止观察" in rec["action"] and "人工审查" in rec["action"]


def test_action_recommendation_halt_threshold_breach_lists_metrics():
    simnow, replay = _valid_simnow_and_replay()
    record = make_record(
        "2026-07-01",
        _baseline(),
        simnow=simnow,
        replay=replay,
        risk={
            "daily_return_pct": -0.10,
            "drawdown_pct": -0.20,
            "gross_exposure": 0.35,
            "net_exposure": 0.10,
            "both_long_short_symbols": 0,
            "consecutive_loss": {"days": 1, "cumulative_return_pct": -0.01},
            "symbol_concentration": {"top1_abs_share": 0.20},
            "strategy_concentration": {"top1_abs_share": 0.20},
        },
    )
    assert record["status"] == "halt"
    assert record["thresholds"]["status"] == "halt"
    rec = action_recommendation(record)
    assert rec["severity"] == "critical"
    assert "gross_exposure" in rec["action"]
    assert "阈值" in rec["action"]


def test_build_action_summary_returns_one_row_per_record():
    records = [
        make_record(
            "2026-06-27",
            _baseline(),
            simnow={
                "signals": [],
                "trades": [],
                "positions": [],
                "risk": {},
                "raw": {
                    "logs": [{"msg": "disconnect 097"}],
                    "ticks": [],
                    "contracts_count": 0,
                    "accounts": [],
                    "positions": [],
                },
            },
            replay={},
        ),
        make_record(
            "2026-07-01",
            _baseline(),
            simnow={
                "signals": [],
                "trades": [],
                "positions": [],
                "risk": {},
                "raw": {
                    "logs": [{"msg": "connected"}],
                    "ticks": [{"dt": "2026-07-01 15:00", "symbol": "SC888"}],
                    "contracts_count": 1,
                    "accounts": [{"accountid": "demo"}],
                    "positions": [],
                },
            },
            replay={
                "signals": [],
                "trades": [],
                "positions": [],
                "meta": {
                    "replay_available": False,
                    "replay_unavailable_reason": "historical_db_lag",
                },
            },
        ),
    ]
    summary = build_action_summary(records)
    assert len(summary) == 2
    assert {row["date"] for row in summary} == {"2026-06-27", "2026-07-01"}
    assert summary[0]["date"] == "2026-06-27"
    for row in summary:
        assert set(row.keys()) >= {"date", "status", "reason", "severity", "action", "counts_for_20d"}


def test_write_20d_markdown_includes_action_summary(tmp_path):
    records = [
        {
            "date": "2026-06-27",
            "status": "skipped",
            "skip_reason": "ctp_disconnect_097_no_snapshot",
            "consistency": {"matched": False},
            "thresholds": {"status": "pass"},
            "valid_observation": False,
        },
        {
            "date": "2026-07-01",
            "status": "pending",
            "consistency": {"matched": False, "reason": "kline_coverage_incomplete", "kline_missing_symbols": ["AP888"]},
            "thresholds": {"status": "pass"},
            "kline_coverage": {"missing_symbols": ["AP888"], "short_symbols": []},
            "valid_observation": False,
        },
    ]
    summary = build_20d_report(records, min_days=2)
    out = tmp_path / "report.md"
    write_20d_markdown(summary, out)
    text = out.read_text(encoding="utf-8")
    assert "## Action Summary" in text
    assert "| date | status | reason | severity | action | counts_for_20d |" in text
    assert "ctp_disconnect_097_no_snapshot" in text
    assert "kline_coverage_incomplete" in text
    assert "AP888" in text


def test_promotion_decision_report_includes_action_summary_with_reason_actions(tmp_path):
    records = [
        {
            "date": "2026-06-22",
            "status": "pending",
            "consistency": {"matched": False, "reason": "historical_db_lag"},
            "thresholds": {"status": "pass"},
            "valid_observation": False,
        },
        {
            "date": "2026-07-01",
            "status": "pending",
            "consistency": {"matched": False, "reason": "kline_coverage_incomplete", "kline_missing_symbols": ["AP888"]},
            "thresholds": {"status": "pass"},
            "kline_coverage": {"missing_symbols": ["AP888"], "short_symbols": []},
            "valid_observation": False,
        },
        {
            "date": "2026-06-20",
            "status": "pass",
            "consistency": {"matched": True},
            "thresholds": {"status": "pass"},
            "order_safety": {"status": "pass"},
            "subscription_coverage": {"missing_symbols": []},
            "kline_coverage": {"missing_symbols": [], "short_symbols": []},
            "valid_observation": True,
        },
    ]
    summary = decide_promotion(records, min_days=3)
    out = tmp_path / "promotion.md"
    write_report(summary, out)
    text = out.read_text(encoding="utf-8")
    assert "## Action Summary" in text
    assert "| date | status | reason | severity | action | counts_for_20d |" in text
    assert "historical_db_lag" in text
    assert "backfill" in text
    assert "kline_coverage_incomplete" in text
    assert "重新采集" in text
    assert "计入 20 日有效观察" in text


def test_promotion_decision_summary_includes_valid_days_and_blocking_actions():
    records = [
        {
            "date": "2026-06-22",
            "status": "pending",
            "consistency": {"matched": False, "reason": "historical_db_lag"},
            "thresholds": {"status": "pass"},
            "valid_observation": False,
        },
        {
            "date": "2026-06-23",
            "status": "pending",
            "consistency": {"matched": False, "reason": "historical_db_lag"},
            "thresholds": {"status": "pass"},
            "valid_observation": False,
        },
        {
            "date": "2026-07-01",
            "status": "pending",
            "consistency": {"matched": False, "reason": "kline_coverage_incomplete"},
            "thresholds": {"status": "pass"},
            "valid_observation": False,
        },
        {
            "date": "2026-06-20",
            "status": "pass",
            "consistency": {"matched": True},
            "thresholds": {"status": "pass"},
            "order_safety": {"status": "pass"},
            "subscription_coverage": {"missing_symbols": []},
            "kline_coverage": {"missing_symbols": [], "short_symbols": []},
            "valid_observation": True,
        },
    ]
    summary = decide_promotion(records, min_days=4)
    assert summary["valid_observation_days"] == 1
    assert summary["action_summary_count"] == 4
    assert summary["top_blocking_actions"] == [
        {"reason": "historical_db_lag", "count": 2},
        {"reason": "kline_coverage_incomplete", "count": 1},
    ]


def test_promotion_decision_pass_valid_shows_counts_for_20d_true(tmp_path):
    records = [
        {
            "date": "2026-06-20",
            "status": "pass",
            "consistency": {"matched": True},
            "thresholds": {"status": "pass"},
            "order_safety": {"status": "pass"},
            "subscription_coverage": {"missing_symbols": []},
            "kline_coverage": {"missing_symbols": [], "short_symbols": []},
            "valid_observation": True,
        },
    ]
    summary = decide_promotion(records, min_days=1)
    out = tmp_path / "promotion.md"
    write_report(summary, out)
    text = out.read_text(encoding="utf-8")
    assert "counts_for_20d" in text
    assert "计入 20 日有效观察" in text
    assert "| 2026-06-20 | pass |" in text
    assert "| ok |" in text
    assert "| True |" in text


def test_promotion_decision_does_not_import_daily_monitor():
    import simnow_promotion_decision as promo_mod

    src = Path(promo_mod.__file__).read_text(encoding="utf-8")
    assert "from simnow_daily_monitor" not in src
    assert "import simnow_daily_monitor" not in src


def test_daily_monitor_imports_action_summary_instead_of_defining_it():
    import simnow_daily_monitor as monitor_mod

    src = Path(monitor_mod.__file__).read_text(encoding="utf-8")
    assert "from simnow_action_summary import" in src
    assert "def action_recommendation" not in src
    assert "def build_action_summary" not in src
    assert "def _pass_gaps" not in src


def test_both_modules_share_the_same_action_summary_function():
    import simnow_action_summary as action_mod
    import simnow_daily_monitor as monitor_mod
    import simnow_promotion_decision as promo_mod

    assert monitor_mod.build_action_summary is action_mod.build_action_summary
    assert promo_mod.build_action_summary is action_mod.build_action_summary


def test_compare_simnow_replay_matches_no_actionable_events_day():
    """A day with no live events and no replay trades is considered consistent."""
    simnow: dict[str, Any] = {"signals": [], "trades": [], "positions": []}
    replay: dict[str, Any] = {
        "signals": [{"dt": "2026-07-06 10:00", "symbol": "AP888", "strategy": "snapshot", "operate": "SIGNAL"}],
        "trades": [],
        "positions": [{"dt": "2026-07-06 10:00", "symbol": "AP888", "strategy": "portfolio", "operate": "POSITION"}],
        "meta": {"replay_available": True},
    }
    result = compare_simnow_replay(simnow, replay)
    assert result["matched"] is True
    assert result["reason"] == "no_actionable_events_on_either_side"
    assert result["details"]["positions"]["matched"] is True


def test_compare_simnow_replay_matches_unavailable_no_replay_events_when_simnow_empty():
    simnow: dict[str, Any] = {"signals": [], "trades": [], "positions": []}
    replay: dict[str, Any] = {
        "signals": [],
        "trades": [],
        "positions": [],
        "meta": {
            "replay_available": False,
            "replay_unavailable_reason": "no_replay_events_for_day",
        },
    }
    result = compare_simnow_replay(simnow, replay)
    assert result["matched"] is True
    assert result["reason"] == "no_actionable_events_on_either_side"


def test_compare_simnow_replay_still_mismatches_when_replay_has_trades():
    simnow: dict[str, Any] = {"signals": [], "trades": [], "positions": []}
    replay: dict[str, Any] = {
        "signals": [],
        "trades": [{"dt": "2026-07-06 10:00", "symbol": "AP888", "strategy": "二买多头", "operate": "OPEN"}],
        "positions": [],
        "meta": {"replay_available": True},
    }
    result = compare_simnow_replay(simnow, replay)
    assert result["matched"] is False
