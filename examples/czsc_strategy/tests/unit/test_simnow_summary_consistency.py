import json
import sys
from pathlib import Path

import pytest


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_daily_brief import build_daily_brief  # noqa: E402
from simnow_daily_monitor import build_20d_report, write_20d_markdown  # noqa: E402
from simnow_run_summary import build_run_summary  # noqa: E402
from simnow_summary_consistency import validate_artifacts  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_files(tmp_path: Path, date: str) -> dict[str, Path]:
    return {
        "capture_json": tmp_path / f"simnow_export_{date}.json",
        "kline_json": tmp_path / f"simnow_kline_update_{date}.json",
        "replay_json": tmp_path / f"simnow_replay_{date}.json",
        "historical_db_update_json": tmp_path / f"simnow_historical_db_update_{date}.json",
        "record_json": tmp_path / f"simnow_record_{date}.json",
        "observation_report_md": tmp_path / f"simnow_report_{date}.md",
        "promotion_report_md": tmp_path / "simnow_20d_promotion_decision.md",
    }


def _base_record(date: str) -> dict:
    return {
        "date": date,
        "status": "pending",
        "valid_observation": False,
        "environment_observation_valid": True,
        "environment_observation_reason": "",
        "consistency": {"matched": False, "reason": "historical_db_lag", "verified": True},
        "thresholds": {"status": "unproven", "rows": []},
        "order_safety": {"status": "pass", "read_only": True, "orders_sent_by_workflow": 0},
        "subscription_coverage": {"missing_symbols": []},
        "kline_coverage": {"missing_symbols": [], "short_symbols": [], "min_bars_per_symbol": 30},
        "simnow": {},
        "replay": {"meta": {"replay_available": False, "replay_unavailable_reason": "historical_db_lag"}},
        "risk_metrics": {},
        "risk_source": "replay_computed",
        "skip_reason": "",
    }


def test_validate_artifacts_accepts_consistent_summary_and_reports(tmp_path):
    date = "2026-07-15"
    files = _make_files(tmp_path, date)
    capture = {
        "meta": {"read_only": True, "orders_sent_by_workflow": 0},
        "raw": {"ticks": [], "contracts_count": 10, "accounts": [], "positions": [], "orders": [], "trades": [], "subscribed": []},
    }
    record = _base_record(date)
    ledger_summary = {
        "generated_at": "2026-07-15T15:00:00+08:00",
        "min_days": 20,
        "total_rows": 1,
        "valid_observation_days": 0,
        "pending_days": 1,
        "skipped_days": 0,
        "halt_days": 0,
        "failed_days": 0,
        "latest_date": date,
        "latest_valid_date": "",
        "consecutive_valid_days": 0,
        "ready_to_expand": False,
        "promotion_blockers": ["need_20_more_valid_observation_days", "pending_days_present", "non_pass_days_present", "consistency_not_fully_matched"],
        "reason_counts": {"historical_db_lag": 1},
        "automation_status_counts": {"pending": 1},
        "latest_action": {
            "date": date,
            "status": "pending",
            "reason": "historical_db_lag",
            "severity": "medium",
            "action": "等待历史库覆盖后补刷",
            "counts_for_20d": False,
        },
        "next_action": "resolve latest pending reason",
    }
    promotion = {
        "ready_to_expand": False,
        "valid_observation_days": 0,
        "observed_days": 1,
        "promotion_blockers": ["need_20_more_valid_observation_days", "pending_days_present"],
        "top_blocking_actions": [{"reason": "historical_db_lag", "count": 1}],
    }

    _write_json(files["capture_json"], capture)
    _write_json(files["record_json"], record)
    summary = build_run_summary(date, files, promotion_summary=promotion, ledger_summary=ledger_summary)
    run_summary_path = tmp_path / f"simnow_run_summary_{date}.json"
    ledger_summary_path = tmp_path / "simnow_ledger_summary.json"
    daily_brief_path = tmp_path / f"simnow_daily_brief_{date}.md"
    report_path = files["observation_report_md"]
    _write_json(run_summary_path, summary)
    _write_json(ledger_summary_path, ledger_summary)
    daily_brief_path.write_text(build_daily_brief(summary), encoding="utf-8")
    report_summary = build_20d_report([record], observation_start_date=None)
    write_20d_markdown(report_summary, report_path)

    validate_artifacts(
        date=date,
        run_summary_path=run_summary_path,
        record_path=files["record_json"],
        ledger_summary_path=ledger_summary_path,
        daily_brief_path=daily_brief_path,
        report_md_path=report_path,
        kline_path=files["kline_json"],
    )


def test_validate_artifacts_allows_report_to_exclude_pre_window_record(tmp_path):
    date = "2026-08-11"
    files = _make_files(tmp_path, date)
    capture = {
        "meta": {"read_only": True, "orders_sent_by_workflow": 0},
        "raw": {"ticks": [], "contracts_count": 10, "accounts": [], "positions": [], "orders": [], "trades": [], "subscribed": []},
    }
    record = _base_record(date)
    ledger_summary = {
        "generated_at": "2026-08-11T21:30:00+08:00",
        "min_days": 20,
        "observation_start_date": "2026-08-12",
        "excluded_before_start_count": 1,
        "total_rows": 0,
        "valid_observation_days": 0,
        "pending_days": 0,
        "skipped_days": 0,
        "halt_days": 0,
        "failed_days": 0,
        "latest_date": "",
        "latest_valid_date": "",
        "consecutive_valid_days": 0,
        "ready_to_expand": False,
        "promotion_blockers": ["need_20_more_valid_observation_days"],
        "reason_counts": {},
        "automation_status_counts": {},
        "latest_action": {},
        "next_action": "continue daily observation",
    }
    promotion = {
        "ready_to_expand": False,
        "valid_observation_days": 0,
        "observed_days": 0,
        "observation_start_date": "2026-08-12",
        "excluded_before_start_count": 1,
        "promotion_blockers": ["need_20_more_valid_observation_days"],
        "top_blocking_actions": [],
    }

    _write_json(files["capture_json"], capture)
    _write_json(files["record_json"], record)
    summary = build_run_summary(date, files, promotion_summary=promotion, ledger_summary=ledger_summary)
    run_summary_path = tmp_path / f"simnow_run_summary_{date}.json"
    ledger_summary_path = tmp_path / "simnow_ledger_summary.json"
    daily_brief_path = tmp_path / f"simnow_daily_brief_{date}.md"
    report_path = files["observation_report_md"]
    _write_json(run_summary_path, summary)
    _write_json(ledger_summary_path, ledger_summary)
    daily_brief_path.write_text(build_daily_brief(summary), encoding="utf-8")
    report_summary = build_20d_report([record], observation_start_date="2026-08-12")
    write_20d_markdown(report_summary, report_path)

    validate_artifacts(
        date=date,
        run_summary_path=run_summary_path,
        record_path=files["record_json"],
        ledger_summary_path=ledger_summary_path,
        daily_brief_path=daily_brief_path,
        report_md_path=report_path,
        kline_path=files["kline_json"],
    )


def test_validate_artifacts_rejects_stale_run_summary_record_status(tmp_path):
    date = "2026-07-15"
    files = _make_files(tmp_path, date)
    record = _base_record(date)
    _write_json(files["record_json"], record)
    summary = build_run_summary(date, files)
    summary["record"]["status"] = "halt"
    run_summary_path = tmp_path / f"simnow_run_summary_{date}.json"
    _write_json(run_summary_path, summary)

    with pytest.raises(RuntimeError, match="record.status"):
        validate_artifacts(
            date=date,
            run_summary_path=run_summary_path,
            record_path=files["record_json"],
            ledger_summary_path=tmp_path / "missing_ledger_summary.json",
            daily_brief_path=tmp_path / "missing_daily_brief.md",
            report_md_path=tmp_path / "missing_report.md",
            kline_path=files["kline_json"],
        )


def test_validate_artifacts_rejects_daily_brief_status_drift(tmp_path):
    date = "2026-07-15"
    files = _make_files(tmp_path, date)
    record = _base_record(date)
    _write_json(files["record_json"], record)
    summary = build_run_summary(date, files)
    run_summary_path = tmp_path / f"simnow_run_summary_{date}.json"
    _write_json(run_summary_path, summary)
    daily_brief_path = tmp_path / f"simnow_daily_brief_{date}.md"
    daily_brief_path.write_text("# brief\n\nautomation_status: `halt`\nrecord.status: `pending`\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="daily_brief"):
        validate_artifacts(
            date=date,
            run_summary_path=run_summary_path,
            record_path=files["record_json"],
            ledger_summary_path=tmp_path / "missing_ledger_summary.json",
            daily_brief_path=daily_brief_path,
            report_md_path=tmp_path / "missing_report.md",
            kline_path=files["kline_json"],
        )


def test_validate_artifacts_rejects_daily_brief_action_class_drift(tmp_path):
    date = "2026-07-15"
    files = _make_files(tmp_path, date)
    record = _base_record(date)
    _write_json(files["record_json"], record)
    summary = build_run_summary(date, files)
    run_summary_path = tmp_path / f"simnow_run_summary_{date}.json"
    _write_json(run_summary_path, summary)
    daily_brief_path = tmp_path / f"simnow_daily_brief_{date}.md"
    daily_brief_path.write_text(
        "# brief\n\nautomation_status: `pending`\nautomation_action_class: `investigate_infra`\nautomation_blocker_class: `review_now`\nrecord.status: `pending`\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="daily_brief"):
        validate_artifacts(
            date=date,
            run_summary_path=run_summary_path,
            record_path=files["record_json"],
            ledger_summary_path=tmp_path / "missing_ledger_summary.json",
            daily_brief_path=daily_brief_path,
            report_md_path=tmp_path / "missing_report.md",
            kline_path=files["kline_json"],
        )
