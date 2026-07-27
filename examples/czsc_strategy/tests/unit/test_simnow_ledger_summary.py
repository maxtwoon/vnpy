import json
import subprocess
import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_ledger_summary import (  # noqa: E402
    build_ledger_summary,
    load_ledger,
)
from simnow_observation_window import filter_records_by_start  # noqa: E402


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in records]
    path.write_text("\n".join(lines), encoding="utf-8")


def _valid_record(date: str) -> dict:
    return {
        "date": date,
        "status": "pass",
        "valid_observation": True,
        "consistency": {"matched": True, "verified": True},
        "thresholds": {"status": "pass"},
        "order_safety": {"status": "pass"},
        "subscription_coverage": {},
        "kline_coverage": {},
    }


def _pending_record(date: str, reason: str) -> dict:
    return {
        "date": date,
        "status": "pending",
        "valid_observation": False,
        "consistency": {"matched": False, "reason": reason},
        "thresholds": {"status": "pass"},
        "order_safety": {"status": "pass"},
        "subscription_coverage": {},
        "kline_coverage": {},
    }


def _skipped_record(date: str, reason: str) -> dict:
    return {
        "date": date,
        "status": "skipped",
        "valid_observation": False,
        "skip_reason": reason,
        "thresholds": {"status": "pass"},
        "order_safety": {"status": "pass"},
    }


def _halt_record(date: str, reason: str) -> dict:
    halt = {
        "rule_id": "workflow_order_safety_breach" if reason == "workflow_order_safety_breach" else "threshold_breach",
        "family": "order_safety" if reason == "workflow_order_safety_breach" else "strategy_risk",
        "severity": "critical",
        "trigger_metrics": [] if reason == "workflow_order_safety_breach" else [reason],
        "explained_cn": "只读观察流程检测到下单动作，必须停止自动化并人工复核。"
        if reason == "workflow_order_safety_breach"
        else f"风险阈值触发停线：{reason}。",
    }
    return {
        "date": date,
        "status": "halt",
        "valid_observation": False,
        "consistency": {"matched": False, "reason": reason},
        "thresholds": {"status": "halt"},
        "order_safety": {"status": "halt"},
        "halt": halt,
    }


def _failed_record(date: str) -> dict:
    return {
        "date": date,
        "status": "unknown",
        "valid_observation": False,
    }


def test_load_ledger_missing_file_returns_empty():
    assert load_ledger(Path("/tmp/simnow_ledger_summary_nonexistent.jsonl")) == []


def test_empty_ledger_summary():
    summary = build_ledger_summary([])

    assert summary["total_rows"] == 0
    assert summary["valid_observation_days"] == 0
    assert summary["pending_days"] == 0
    assert summary["skipped_days"] == 0
    assert summary["halt_days"] == 0
    assert summary["failed_days"] == 0
    assert summary["ready_to_expand"] is False
    assert "need_20_more_valid_observation_days" in summary["promotion_blockers"]
    assert summary["next_action"] == "continue daily observation"


def test_mixed_records_counts_and_blockers():
    records = [
        _valid_record("2026-06-20"),
        _pending_record("2026-06-21", "historical_db_lag"),
        _skipped_record("2026-06-22", "simnow_no_ticks"),
        _halt_record("2026-06-23", "workflow_order_safety_breach"),
        _failed_record("2026-06-24"),
    ]
    summary = build_ledger_summary(records)

    assert summary["total_rows"] == 5
    assert summary["valid_observation_days"] == 1
    assert summary["pending_days"] == 1
    assert summary["skipped_days"] == 1
    assert summary["halt_days"] == 1
    assert summary["failed_days"] == 1
    assert summary["automation_status_counts"]["valid"] == 1
    assert summary["automation_status_counts"]["pending"] == 1
    assert summary["automation_status_counts"]["skipped"] == 1
    assert summary["automation_status_counts"]["halt"] == 1
    assert summary["automation_status_counts"]["failed"] == 1
    assert summary["reason_counts"].get("historical_db_lag") == 1
    assert summary["reason_counts"].get("simnow_no_ticks") == 1
    assert summary["reason_counts"].get("workflow_order_safety_breach") == 1
    assert summary["operational_bucket_counts"] == {
        "data_pending_days": 1,
        "safety_halt_days": 1,
        "trading_session_skipped_days": 1,
    }
    assert summary["halt_family_counts"] == {"order_safety": 1}
    blockers = summary["promotion_blockers"]
    assert "need_19_more_valid_observation_days" in blockers
    assert "pending_days_present" in blockers
    assert "skipped_days_present" in blockers
    assert "halt_days_present" in blockers
    assert "failed_days_present" in blockers


def test_ready_to_expand_with_twenty_valid():
    records = [_valid_record(f"2026-06-{i:02d}") for i in range(1, 21)]
    summary = build_ledger_summary(records)

    assert summary["valid_observation_days"] == 20
    assert summary["ready_to_expand"] is True
    assert summary["promotion_blockers"] == []
    assert summary["next_action"] == "review promotion readiness"


def test_consecutive_valid_days_counts_trailing_sequence():
    records = [
        _valid_record("2026-06-20"),
        _valid_record("2026-06-21"),
        _pending_record("2026-06-22", "historical_db_lag"),
        _valid_record("2026-06-23"),
        _valid_record("2026-06-24"),
    ]
    summary = build_ledger_summary(records)

    assert summary["consecutive_valid_days"] == 2
    assert summary["latest_valid_date"] == "2026-06-24"


def test_latest_action_from_action_summary():
    records = [
        _pending_record("2026-06-21", "kline_coverage_incomplete"),
    ]
    summary = build_ledger_summary(records)

    assert "kline_coverage_incomplete" in summary["latest_action"]["reason"]
    assert summary["latest_action"]["action"] != ""
    assert summary["latest_action"]["action_class"] == "wait_for_data"
    assert summary["latest_action"]["blocker_class"] == "wait"
    assert summary["blocking_action_counts"] == {"wait_for_data": 1}
    assert summary["next_action_class"] == "wait_for_data"


def test_next_action_mapping():
    ready = build_ledger_summary([_valid_record(f"2026-06-{i:02d}") for i in range(1, 21)])
    assert ready["next_action"] == "review promotion readiness"
    assert ready["next_action_class"] == "review_promotion_readiness"

    pending = build_ledger_summary([_pending_record("2026-06-20", "historical_db_lag")])
    assert pending["next_action"] == "resolve latest pending reason"
    assert pending["next_action_class"] == "wait_for_data"

    skipped = build_ledger_summary([_skipped_record("2026-06-20", "simnow_no_ticks")])
    assert skipped["next_action"] == "wait for next valid session"
    assert skipped["next_action_class"] == "rerun_next_session"

    halt = build_ledger_summary([_halt_record("2026-06-20", "workflow_order_safety_breach")])
    assert halt["next_action"] == "manual review required"
    assert halt["next_action_class"] == "manual_review_required"

    other = build_ledger_summary([_valid_record("2026-06-20"), _valid_record("2026-06-21")])
    assert other["next_action"] == "continue daily observation"
    assert other["next_action_class"] == "continue_observation"


def test_cli_writes_summary_json(tmp_path):
    ledger_path = tmp_path / "simnow_observation_ledger.jsonl"
    # This CLI invocation does not pass --start-date, so it falls back to the
    # repo's default simnow_observation_window.json. The record date must stay
    # on/after that config's observation_start_date or it gets filtered out.
    _write_jsonl(ledger_path, [_pending_record("2026-07-27", "historical_db_lag")])
    out_path = tmp_path / "simnow_ledger_summary.json"

    result = subprocess.run(
        [
            sys.executable,
            str(DIAG / "simnow_ledger_summary.py"),
            "--ledger",
            str(ledger_path),
            "--out-json",
            str(out_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert result.returncode == 0
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["total_rows"] == 1


def test_summary_does_not_leak_sensitive_data():
    records = [
        {
            "date": "2026-06-20",
            "status": "pass",
            "valid_observation": True,
            "consistency": {"matched": True, "verified": True},
            "thresholds": {"status": "pass"},
            "order_safety": {"status": "pass"},
            "subscription_coverage": {},
            "kline_coverage": {},
            "simnow": {
                "meta": {
                    "setting_masked": {"密码": "Sm***20", "授权码": "00***00"},
                    "accountid": "24***89",
                }
            },
        }
    ]
    summary = build_ledger_summary(records)
    text = json.dumps(summary, ensure_ascii=False)

    assert "setting_masked" not in text
    assert "密码" not in text
    assert "授权码" not in text
    assert "24***89" not in text
    assert "Sm***20" not in text


def test_consecutive_valid_days_counts_weekend_gap_as_continuous():
    """Consecutive valid days are counted by ledger rows, not calendar adjacency."""
    records = [
        _valid_record("2026-07-03"),
        _valid_record("2026-07-06"),
    ]
    summary = build_ledger_summary(records)

    assert summary["consecutive_valid_days"] == 2


def test_consecutive_valid_days_stops_at_latest_invalid_record():
    records = [
        _valid_record("2026-06-20"),
        _valid_record("2026-06-21"),
        _pending_record("2026-06-22", "historical_db_lag"),
    ]
    summary = build_ledger_summary(records)

    assert summary["consecutive_valid_days"] == 0


def test_filter_records_by_observation_start_keeps_history_out_of_new_cycle():
    records = [
        _valid_record("2026-07-12"),
        _halt_record("2026-07-13", "threshold_breach"),
        _valid_record("2026-07-14"),
    ]

    filtered = filter_records_by_start(records, "2026-07-14")

    assert [row["date"] for row in filtered] == ["2026-07-14"]


def test_ledger_summary_filters_before_observation_start():
    records = [
        _valid_record("2026-07-12"),
        _halt_record("2026-07-13", "threshold_breach"),
        _valid_record("2026-07-14"),
    ]

    summary = build_ledger_summary(records, observation_start_date="2026-07-14")

    assert summary["observation_start_date"] == "2026-07-14"
    assert summary["excluded_before_start_count"] == 2
    assert summary["total_rows"] == 1
    assert summary["valid_observation_days"] == 1
    assert summary["halt_days"] == 0
    assert summary["latest_date"] == "2026-07-14"


def test_operational_buckets_split_data_infra_risk_and_session_causes():
    records = [
        _pending_record("2026-06-20", "historical_db_lag"),
        _pending_record("2026-06-21", "subscription_incomplete"),
        _pending_record("2026-06-22", "kline_coverage_too_short"),
        _skipped_record("2026-06-23", "ctp_disconnect_097_no_snapshot"),
        _halt_record("2026-06-24", "consecutive_loss_abs_pct"),
        _halt_record("2026-06-25", "workflow_order_safety_breach"),
    ]

    summary = build_ledger_summary(records)

    assert summary["operational_bucket_counts"] == {
        "data_pending_days": 2,
        "infra_pending_days": 1,
        "safety_halt_days": 1,
        "strategy_risk_halt_days": 1,
        "trading_session_skipped_days": 1,
    }
    assert summary["halt_family_counts"] == {
        "order_safety": 1,
        "strategy_risk": 1,
    }
