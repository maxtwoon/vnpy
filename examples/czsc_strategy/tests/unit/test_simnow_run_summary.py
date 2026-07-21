import json
import sys
from pathlib import Path

import pytest


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_run_summary import (  # noqa: E402
    build_run_summary,
    contains_sensitive_data,
    load_json,
    load_jsonl,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_run_summary_from_minimal_artifacts(tmp_path):
    date = "2026-07-01"
    capture = {
        "meta": {"read_only": True, "orders_sent_by_workflow": 0},
        "raw": {
            "ticks": [
                {"dt": "2026-07-01 09:30", "symbol": "AP888"},
                {"dt": "2026-07-01 09:31", "symbol": "SC888"},
            ],
            "contracts_count": 100,
            "accounts": [{"accountid": "demo"}],
            "positions": [{"symbol": "AP888"}],
            "orders": [],
            "trades": [],
            "subscribed": [{"research_symbol": "AP888"}, {"research_symbol": "SC888"}],
        },
    }
    kline = {
        "missing_symbols": ["AP888"],
        "short_symbols": ["SC888"],
        "min_bars_per_symbol": 30,
    }
    record = {
        "date": date,
        "status": "pending",
        "valid_observation": False,
        "consistency": {"matched": False, "reason": "kline_coverage_incomplete"},
        "thresholds": {"status": "pass"},
        "order_safety": {"status": "pass"},
    }
    promotion = {
        "ready_to_expand": False,
        "valid_observation_days": 0,
        "observed_days": 1,
        "promotion_blockers": ["need_20_more_valid_observation_days", "pending_days_present"],
        "top_blocking_actions": [{"reason": "kline_coverage_incomplete", "count": 1}],
    }
    files = {
        "capture_json": tmp_path / "capture.json",
        "kline_json": tmp_path / "kline.json",
        "replay_json": tmp_path / "replay.json",
        "record_json": tmp_path / "record.json",
        "observation_report_md": tmp_path / "report.md",
        "promotion_report_md": tmp_path / "promotion.md",
    }
    _write_json(files["capture_json"], capture)
    _write_json(files["kline_json"], kline)
    _write_json(files["record_json"], record)
    summary = build_run_summary(date, files, promotion_summary=promotion)

    assert summary["date"] == date
    assert summary["files"] == {k: str(v) for k, v in files.items()}
    assert summary["capture"]["ticks"] == 2
    assert summary["capture"]["contracts_count"] == 100
    assert summary["capture"]["accounts"] == 1
    assert summary["capture"]["positions"] == 1
    assert summary["capture"]["orders"] == 0
    assert summary["capture"]["trades"] == 0
    assert summary["capture"]["subscribed_count"] == 2
    assert summary["environment_capture"]["tick_counts_by_symbol"] == {"AP888": 1, "SC888": 1}
    assert summary["environment_capture"]["zero_tick_subscribed_symbols"] == []
    assert summary["kline"]["missing_symbols"] == ["AP888"]
    assert summary["kline"]["short_symbols"] == ["SC888"]
    assert summary["kline"]["min_bars_per_symbol"] == 30
    assert summary["record"]["status"] == "pending"
    assert summary["record"]["reason"] == "kline_coverage_incomplete"
    assert summary["record"]["valid_observation"] is False
    assert summary["record"]["threshold_status"] == "pass"
    assert summary["record"]["order_safety_status"] == "pass"
    assert summary["record"]["consistency_matched"] is False
    assert summary["record"]["threshold_rows"] == []
    assert summary["promotion"]["ready_to_expand"] is False
    assert summary["promotion"]["valid_observation_days"] == 0
    assert summary["promotion"]["observed_days"] == 1
    assert "need_20_more_valid_observation_days" in summary["promotion"]["promotion_blockers"]
    assert summary["promotion"]["top_blocking_actions"] == [{"reason": "kline_coverage_incomplete", "count": 1}]


def test_build_run_summary_includes_historical_db_update_status(tmp_path):
    date = "2026-07-14"
    files = _make_files(tmp_path)
    files["historical_db_update_json"] = tmp_path / "historical_update.json"
    _write_json(files["historical_db_update_json"], {
        "status": "passed",
        "exit_code": 0,
        "command": "D:\\repo\\ssquant\\auto_update.bat",
        "started_at": "2026-07-14T01:00:00+08:00",
        "ended_at": "2026-07-14T04:20:00+08:00",
    })

    summary = build_run_summary(date, files)

    assert summary["historical_db_update"] == {
        "status": "passed",
        "exit_code": 0,
        "command": "D:\\repo\\ssquant\\auto_update.bat",
        "started_at": "2026-07-14T01:00:00+08:00",
        "ended_at": "2026-07-14T04:20:00+08:00",
    }


def test_build_run_summary_defaults_missing_historical_db_update_to_skipped(tmp_path):
    files = _make_files(tmp_path)

    summary = build_run_summary("2026-07-14", files)

    assert summary["historical_db_update"]["status"] == "skipped"
    assert summary["historical_db_update"]["exit_code"] is None


def test_build_run_summary_promotion_carries_window_filter_metadata(tmp_path):
    date = "2026-07-01"
    capture = {
        "meta": {"read_only": True, "orders_sent_by_workflow": 0},
        "raw": {
            "ticks": [],
            "contracts_count": 1,
            "accounts": [],
            "positions": [],
            "orders": [],
            "trades": [],
            "subscribed": [],
        },
    }
    record = {
        "date": date,
        "status": "pass",
        "valid_observation": True,
        "consistency": {"matched": True, "reason": "delayed_replay_validated"},
        "thresholds": {"status": "pass"},
        "order_safety": {"status": "pass"},
    }
    promotion = {
        "ready_to_expand": False,
        "valid_observation_days": 5,
        "observed_days": 7,
        "observation_start_date": "2026-04-24",
        "excluded_before_start_count": 3,
        "promotion_blockers": ["need_15_more_valid_observation_days"],
        "top_blocking_actions": [],
    }
    files = {
        "capture_json": tmp_path / "capture.json",
        "kline_json": tmp_path / "kline.json",
        "replay_json": tmp_path / "replay.json",
        "record_json": tmp_path / "record.json",
        "observation_report_md": tmp_path / "report.md",
        "promotion_report_md": tmp_path / "promotion.md",
    }
    _write_json(files["capture_json"], capture)
    _write_json(files["record_json"], record)

    summary = build_run_summary(date, files, promotion_summary=promotion)

    assert summary["promotion"]["observation_start_date"] == "2026-04-24"
    assert summary["promotion"]["excluded_before_start_count"] == 3


def test_build_run_summary_promotion_window_defaults_when_missing(tmp_path):
    date = "2026-07-01"
    capture = {
        "meta": {"read_only": True, "orders_sent_by_workflow": 0},
        "raw": {
            "ticks": [],
            "contracts_count": 1,
            "accounts": [],
            "positions": [],
            "orders": [],
            "trades": [],
            "subscribed": [],
        },
    }
    record = {
        "date": date,
        "status": "pass",
        "valid_observation": True,
        "consistency": {"matched": True, "reason": "delayed_replay_validated"},
        "thresholds": {"status": "pass"},
        "order_safety": {"status": "pass"},
    }
    promotion = {
        "ready_to_expand": False,
        "valid_observation_days": 5,
        "observed_days": 7,
        "promotion_blockers": ["need_15_more_valid_observation_days"],
        "top_blocking_actions": [],
    }
    files = {
        "capture_json": tmp_path / "capture.json",
        "kline_json": tmp_path / "kline.json",
        "replay_json": tmp_path / "replay.json",
        "record_json": tmp_path / "record.json",
        "observation_report_md": tmp_path / "report.md",
        "promotion_report_md": tmp_path / "promotion.md",
    }
    _write_json(files["capture_json"], capture)
    _write_json(files["record_json"], record)

    summary = build_run_summary(date, files, promotion_summary=promotion)

    assert summary["promotion"]["observation_start_date"] == ""
    assert summary["promotion"]["excluded_before_start_count"] == 0


def test_build_run_summary_separates_environment_account_contamination_and_delayed_replay(tmp_path):
    date = "2026-07-13"
    capture = {
        "meta": {"read_only": True, "orders_sent_by_workflow": 0},
        "raw": {
            "ticks": [{"dt": "2026-07-13 15:18:48", "symbol": "sc2608"}],
            "contracts_count": 18023,
            "accounts": [{"accountid": "246189", "balance": 20510820.0}],
            "positions": [{"symbol": "sc2608", "direction": "多", "volume": 1, "price": 468.5, "pnl": 9500.0}],
            "orders": [{"symbol": "sc2608", "direction": "多", "price": 437.8, "volume": 1}],
            "trades": [{"symbol": "sc2608", "direction": "多", "price": 437.8, "volume": 1}],
            "subscribed": [
                {"research_symbol": "SC888", "symbol": "sc2608", "exchange": "INE", "vt_symbol": "sc2608.INE"},
                {"research_symbol": "RB888", "symbol": "rb2610", "exchange": "SHFE", "vt_symbol": "rb2610.SHFE"},
            ],
        },
    }
    replay = {
        "signals": [{"symbol": "SC888"}],
        "trades": [{"symbol": "SC888", "pnl_pct": 0.024}],
        "positions": [{"symbol": "SC888", "gross_exposure": 0.06}],
        "risk": {"daily_return_pct": 0.12, "gross_exposure": 0.06},
        "meta": {
            "replay_available": True,
            "replay_unavailable_reason": "",
            "latest_db_date": "2026-07-13",
            "missing_or_lagged_symbols": [],
        },
    }
    record = {
        "status": "pass",
        "valid_observation": True,
        "consistency": {"matched": True, "reason": "delayed_replay_validated"},
        "thresholds": {"status": "pass"},
        "order_safety": {"status": "pass"},
    }
    files = _make_files(tmp_path)
    _write_json(files["capture_json"], capture)
    _write_json(files["replay_json"], replay)
    _write_json(files["record_json"], record)

    summary = build_run_summary(date, files)

    assert summary["environment_capture"] == {
        "ticks": 1,
        "contracts_count": 18023,
        "accounts": 1,
        "subscribed_count": 2,
        "read_only": True,
        "orders_sent_by_workflow": 0,
        "tick_counts_by_symbol": {"RB888": 0, "SC888": 1},
        "zero_tick_subscribed_symbols": ["RB888"],
    }
    assert summary["account_contamination"]["detected"] is True
    assert summary["account_contamination"]["orders"] == 1
    assert summary["account_contamination"]["trades"] == 1
    assert summary["account_contamination"]["active_positions"] == 1
    assert summary["account_contamination"]["position_symbols"] == ["sc2608"]
    assert summary["account_contamination"]["note"] == "SimNow account activity is external audit evidence only; it is not strategy PnL."
    assert summary["delayed_replay"] == {
        "available": True,
        "status": "pass",
        "valid_observation": True,
        "reason": "delayed_replay_validated",
        "latest_db_date": "2026-07-13",
        "missing_or_lagged_symbols": [],
        "signals": 1,
        "trades": 1,
        "positions": 1,
        "risk_source": "replay_only",
    }
    summary_text = json.dumps(summary, ensure_ascii=False)
    assert "20510820" not in summary_text
    assert "9500" not in summary_text


def test_build_run_summary_preserves_threshold_rows_for_daily_brief(tmp_path):
    files = _make_files(tmp_path)
    record = {
        "status": "halt",
        "valid_observation": False,
        "consistency": {"matched": False, "reason": "consecutive_loss_abs_pct"},
        "thresholds": {
            "status": "halt",
            "rows": [
                {"metric": "drawdown_abs_pct", "value": 1.2992, "level": "warning", "unit": "%"},
                {"metric": "consecutive_loss_abs_pct", "value": 0.1218, "level": "halt", "unit": "%"},
            ],
        },
        "order_safety": {"status": "pass"},
    }
    _write_json(files["record_json"], record)

    summary = build_run_summary("2026-07-21", files)

    assert summary["record"]["threshold_rows"] == [
        {"metric": "drawdown_abs_pct", "value": 1.2992, "level": "warning", "unit": "%"},
        {"metric": "consecutive_loss_abs_pct", "value": 0.1218, "level": "halt", "unit": "%"},
    ]


def test_summary_does_not_leak_sensitive_capture_fields(tmp_path):
    capture = {
        "meta": {
            "setting_masked": {
                "用户名": "24***89",
                "密码": "Sm***20",
                "授权码": "00***00",
            },
            "contract_map": {"AP888": {"enabled": True}},
        },
        "raw": {
            "ticks": [],
            "contracts_count": 1,
            "accounts": [],
            "positions": [],
            "orders": [],
            "trades": [],
            "subscribed": [],
        },
    }
    record = {
        "status": "skipped",
        "valid_observation": False,
        "consistency": {},
        "thresholds": {"status": "pass"},
    }
    files = {
        "capture_json": tmp_path / "capture.json",
        "kline_json": tmp_path / "kline.json",
        "replay_json": tmp_path / "replay.json",
        "record_json": tmp_path / "record.json",
        "observation_report_md": tmp_path / "report.md",
        "promotion_report_md": tmp_path / "promotion.md",
    }
    _write_json(files["capture_json"], capture)
    _write_json(files["record_json"], record)
    promotion = {
        "ready_to_expand": False,
        "valid_observation_days": 0,
        "observed_days": 1,
        "promotion_blockers": [],
        "top_blocking_actions": [],
    }

    summary = build_run_summary("2026-07-01", files, promotion_summary=promotion)

    sensitive = contains_sensitive_data(summary)
    assert not sensitive
    summary_text = json.dumps(summary, ensure_ascii=False)
    assert "setting_masked" not in summary_text
    assert "密码" not in summary_text
    assert "授权码" not in summary_text
    assert "Sm***20" not in summary_text


def test_build_run_summary_handles_missing_files(tmp_path):
    files = {
        "capture_json": tmp_path / "missing_capture.json",
        "kline_json": tmp_path / "missing_kline.json",
        "record_json": tmp_path / "missing_record.json",
        "replay_json": tmp_path / "missing_replay.json",
        "observation_report_md": tmp_path / "missing_report.md",
        "promotion_report_md": tmp_path / "missing_promotion.md",
    }
    promotion = {
        "ready_to_expand": False,
        "valid_observation_days": 0,
        "observed_days": 0,
        "promotion_blockers": [],
        "top_blocking_actions": [],
    }
    summary = build_run_summary("2026-07-01", files, promotion_summary=promotion)

    assert summary["capture"]["ticks"] == 0
    assert summary["capture"]["contracts_count"] == 0
    assert summary["kline"]["missing_symbols"] == []
    assert summary["kline"]["short_symbols"] == []
    assert summary["record"]["status"] == ""
    assert summary["record"]["valid_observation"] is False
    assert summary["promotion"]["ready_to_expand"] is False
    assert summary["promotion"]["valid_observation_days"] == 0


def test_load_json_returns_empty_for_missing_file():
    assert load_json(Path("/tmp/simnow_run_summary_nonexistent.json")) == {}


def test_load_jsonl_returns_empty_for_missing_file():
    assert load_jsonl(Path("/tmp/simnow_run_summary_nonexistent.jsonl")) == []


def _make_files(tmp_path: Path) -> dict[str, Path]:
    return {
        "capture_json": tmp_path / "capture.json",
        "kline_json": tmp_path / "kline.json",
        "replay_json": tmp_path / "replay.json",
        "record_json": tmp_path / "record.json",
        "observation_report_md": tmp_path / "report.md",
        "promotion_report_md": tmp_path / "promotion.md",
    }


def test_automation_status_valid(tmp_path):
    record = {
        "status": "pass",
        "valid_observation": True,
        "consistency": {"matched": True},
        "thresholds": {"status": "pass"},
        "order_safety": {"status": "pass"},
    }
    files = _make_files(tmp_path)
    _write_json(files["record_json"], record)
    summary = build_run_summary("2026-07-01", files)

    assert summary["automation_status"] == "valid"
    assert summary["automation_exit_code"] == 0
    assert summary["automation_reason"] == ""
    assert summary["automation_action"] == "counts_for_20d"


def test_automation_status_skipped_no_ticks(tmp_path):
    record = {
        "status": "skipped",
        "skip_reason": "simnow_no_ticks",
        "valid_observation": False,
        "consistency": {},
        "thresholds": {"status": "pass"},
    }
    files = _make_files(tmp_path)
    _write_json(files["record_json"], record)
    summary = build_run_summary("2026-07-01", files)

    assert summary["automation_status"] == "skipped"
    assert summary["automation_exit_code"] == 10
    assert summary["automation_reason"] == "simnow_no_ticks"
    assert "rerun" in summary["automation_action"].lower()


def test_automation_status_pending_kline_coverage_incomplete(tmp_path):
    record = {
        "status": "pending",
        "valid_observation": False,
        "consistency": {"matched": False, "reason": "kline_coverage_incomplete"},
        "thresholds": {"status": "pass"},
    }
    files = _make_files(tmp_path)
    _write_json(files["record_json"], record)
    summary = build_run_summary("2026-07-01", files)

    assert summary["automation_status"] == "pending"
    assert summary["automation_exit_code"] == 20
    assert summary["automation_reason"] == "kline_coverage_incomplete"
    assert "resolve pending gate" in summary["automation_action"].lower()


def test_automation_status_halt_workflow_order_safety_breach(tmp_path):
    record = {
        "status": "halt",
        "valid_observation": False,
        "consistency": {"matched": False, "reason": "workflow_order_safety_breach"},
        "thresholds": {"status": "pass"},
        "order_safety": {"status": "halt"},
    }
    files = _make_files(tmp_path)
    _write_json(files["record_json"], record)
    summary = build_run_summary("2026-07-01", files)

    assert summary["automation_status"] == "halt"
    assert summary["automation_exit_code"] == 30
    assert summary["automation_reason"] == "workflow_order_safety_breach"
    assert "stop automation" in summary["automation_action"].lower()


def test_automation_status_failed_missing_record_json(tmp_path):
    files = _make_files(tmp_path)
    # intentionally do not write record.json
    summary = build_run_summary("2026-07-01", files)

    assert summary["automation_status"] == "failed"
    assert summary["automation_exit_code"] == 40
    assert "missing" in summary["automation_reason"].lower() or "unknown" in summary["automation_reason"].lower()


def test_automation_status_preserves_existing_summary_fields(tmp_path):
    record = {
        "status": "pending",
        "valid_observation": False,
        "consistency": {"matched": False, "reason": "historical_db_lag"},
        "thresholds": {"status": "pass"},
    }
    files = _make_files(tmp_path)
    _write_json(files["record_json"], record)
    summary = build_run_summary("2026-07-01", files)

    for key in ("date", "generated_at", "files", "capture", "kline", "record", "promotion"):
        assert key in summary
    for key in ("automation_status", "automation_exit_code", "automation_reason", "automation_action"):
        assert key in summary


def test_automation_status_fields_do_not_leak_sensitive_data(tmp_path):
    capture = {
        "meta": {"setting_masked": {"密码": "Sm***20", "授权码": "00***00"}},
        "raw": {
            "ticks": [],
            "contracts_count": 1,
            "accounts": [],
            "positions": [],
            "orders": [],
            "trades": [],
            "subscribed": [],
        },
    }
    record = {
        "status": "pending",
        "valid_observation": False,
        "consistency": {"matched": False, "reason": "kline_coverage_incomplete"},
        "thresholds": {"status": "pass"},
    }
    files = _make_files(tmp_path)
    _write_json(files["capture_json"], capture)
    _write_json(files["record_json"], record)
    summary = build_run_summary("2026-07-01", files)

    sensitive = contains_sensitive_data(summary)
    assert not sensitive
    assert summary["automation_status"] == "pending"
    assert "automation_status" in json.dumps(summary, ensure_ascii=False)


def _make_ledger_summary() -> dict:
    return {
        "generated_at": "2026-07-02T00:00:00+00:00",
        "min_days": 20,
        "total_rows": 5,
        "valid_observation_days": 2,
        "pending_days": 2,
        "skipped_days": 1,
        "halt_days": 0,
        "failed_days": 0,
        "latest_date": "2026-07-02",
        "latest_valid_date": "2026-07-01",
        "consecutive_valid_days": 2,
        "ready_to_expand": False,
        "promotion_blockers": ["need_18_more_valid_observation_days", "pending_days_present"],
        "reason_counts": {"kline_coverage_incomplete": 2, "simnow_no_ticks": 1},
        "automation_status_counts": {"pending": 2, "skipped": 1, "valid": 2},
        "latest_action": {
            "date": "2026-07-02",
            "status": "pending",
            "reason": "kline_coverage_incomplete",
            "severity": "medium",
            "action": "缺少 K 线品种；建议重新采集。",
            "counts_for_20d": False,
        },
        "next_action": "resolve latest pending reason",
    }


def test_build_run_summary_embeds_ledger_summary_fields(tmp_path):
    from simnow_run_summary import load_ledger_summary

    files = _make_files(tmp_path)
    ledger_summary_path = tmp_path / "simnow_ledger_summary.json"
    _write_json(ledger_summary_path, _make_ledger_summary())

    summary = build_run_summary("2026-07-01", files, ledger_summary=load_ledger_summary(ledger_summary_path))

    ls = summary["ledger_summary"]
    assert ls["available"] is True
    assert ls["total_rows"] == 5
    assert ls["valid_observation_days"] == 2
    assert ls["pending_days"] == 2
    assert ls["skipped_days"] == 1
    assert ls["halt_days"] == 0
    assert ls["failed_days"] == 0
    assert ls["consecutive_valid_days"] == 2
    assert ls["ready_to_expand"] is False
    assert "need_18_more_valid_observation_days" in ls["promotion_blockers"]
    assert ls["reason_counts"]["kline_coverage_incomplete"] == 2
    assert ls["automation_status_counts"]["valid"] == 2
    assert ls["latest_date"] == "2026-07-02"
    assert ls["latest_valid_date"] == "2026-07-01"
    assert ls["latest_action"]["reason"] == "kline_coverage_incomplete"
    assert ls["next_action"] == "resolve latest pending reason"


def test_build_run_summary_handles_missing_ledger_summary(tmp_path):
    files = _make_files(tmp_path)
    summary = build_run_summary("2026-07-01", files, ledger_summary=load_json(tmp_path / "nonexistent.json"))

    assert summary["ledger_summary"] == {"available": False, "reason": "missing_ledger_summary"}


def test_build_run_summary_rejects_sensitive_ledger_summary(tmp_path):
    files = _make_files(tmp_path)
    ledger_summary_path = tmp_path / "simnow_ledger_summary.json"
    bad_summary = _make_ledger_summary()
    bad_summary["latest_action"]["action"] = "setting_masked"
    _write_json(ledger_summary_path, bad_summary)

    from simnow_run_summary import load_ledger_summary

    with pytest.raises(RuntimeError):
        summary = build_run_summary("2026-07-01", files, ledger_summary=load_ledger_summary(ledger_summary_path))
        contains_sensitive_data(summary)
