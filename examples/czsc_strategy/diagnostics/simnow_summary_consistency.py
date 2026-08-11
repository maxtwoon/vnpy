from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from simnow_action_summary import _record_reason
from simnow_daily_brief import load_run_summary
from simnow_ledger_summary_schema import filter_safe_ledger_summary
from simnow_run_summary import (
    classify_automation_status,
    extract_record_summary,
    load_json,
    load_ledger_summary,
)


HERE = Path(__file__).resolve().parent


def _expect_line(text: str, expected: str, label: str, errors: list[str]) -> None:
    if expected not in text:
        errors.append(f"{label} missing expected content: {expected}")


def validate_artifacts(
    *,
    date: str,
    run_summary_path: Path,
    record_path: Path,
    ledger_summary_path: Path,
    daily_brief_path: Path,
    report_md_path: Path,
    kline_path: Path | None = None,
) -> None:
    errors: list[str] = []

    run_summary = load_run_summary(run_summary_path)
    if not run_summary:
        raise RuntimeError(f"run_summary missing or empty: {run_summary_path}")

    record = load_json(record_path)
    if not record:
        raise RuntimeError(f"record missing or empty: {record_path}")

    kline = load_json(kline_path) if kline_path else {}
    expected_record = extract_record_summary(record, kline)
    actual_record = run_summary.get("record") or {}

    record_checks = {
        "record.status": (actual_record.get("status"), expected_record["status"]),
        "record.valid_observation": (actual_record.get("valid_observation"), expected_record["valid_observation"]),
        "record.reason": (actual_record.get("reason"), expected_record["reason"]),
        "record.threshold_status": (actual_record.get("threshold_status"), expected_record["threshold_status"]),
        "record.order_safety_status": (actual_record.get("order_safety_status"), expected_record["order_safety_status"]),
        "record.consistency_matched": (actual_record.get("consistency_matched"), expected_record["consistency_matched"]),
        "record.environment_observation_valid": (
            actual_record.get("environment_observation_valid"),
            expected_record["environment_observation_valid"],
        ),
        "record.environment_observation_reason": (
            actual_record.get("environment_observation_reason"),
            expected_record["environment_observation_reason"],
        ),
    }
    for label, (actual, expected) in record_checks.items():
        if actual != expected:
            errors.append(f"{label} mismatch: actual={actual!r} expected={expected!r}")

    expected_automation = classify_automation_status({"record": actual_record})
    for key in ("automation_status", "automation_exit_code", "automation_reason", "automation_action"):
        if run_summary.get(key) != expected_automation[key]:
            errors.append(
                f"{key} mismatch: actual={run_summary.get(key)!r} expected={expected_automation[key]!r}"
            )

    ledger_summary = load_ledger_summary(ledger_summary_path)
    expected_ledger = (
        filter_safe_ledger_summary(ledger_summary)
        if ledger_summary
        else {"available": False, "reason": "missing_ledger_summary"}
    )
    if run_summary.get("ledger_summary") != expected_ledger:
        errors.append("ledger_summary mismatch between run_summary and ledger_summary file")

    if daily_brief_path.exists():
        brief = daily_brief_path.read_text(encoding="utf-8")
        _expect_line(brief, f"automation_status: `{run_summary.get('automation_status', '')}`", "daily_brief", errors)
        if run_summary.get("automation_reason"):
            _expect_line(
                brief,
                f"automation_reason: `{run_summary.get('automation_reason', '')}`",
                "daily_brief",
                errors,
            )
        if run_summary.get("automation_action"):
            _expect_line(
                brief,
                f"automation_action: `{run_summary.get('automation_action', '')}`",
                "daily_brief",
                errors,
            )
        if run_summary.get("automation_action_class"):
            _expect_line(
                brief,
                f"automation_action_class: `{run_summary.get('automation_action_class', '')}`",
                "daily_brief",
                errors,
            )
        if run_summary.get("automation_blocker_class"):
            _expect_line(
                brief,
                f"automation_blocker_class: `{run_summary.get('automation_blocker_class', '')}`",
                "daily_brief",
                errors,
            )
        if actual_record.get("status"):
            _expect_line(
                brief,
                f"record.status: `{actual_record.get('status', '')}`",
                "daily_brief",
                errors,
            )
        if expected_ledger.get("available") and expected_ledger.get("next_action_class"):
            _expect_line(
                brief,
                f"next_action_class: `{expected_ledger.get('next_action_class', '')}`",
                "daily_brief",
                errors,
            )
    else:
        errors.append(f"daily_brief missing: {daily_brief_path}")

    if report_md_path.exists():
        report = report_md_path.read_text(encoding="utf-8")
        observation_start_date = str(
            run_summary.get("promotion", {}).get("observation_start_date") or ""
        )
        if not observation_start_date or date >= observation_start_date:
            expected_row_prefix = (
                f"| {date} | {bool(record.get('valid_observation'))} | {record.get('status')} | {_record_reason(record)} |"
            )
            _expect_line(report, expected_row_prefix, "report_md", errors)
    else:
        errors.append(f"report_md missing: {report_md_path}")

    if errors:
        raise RuntimeError("; ".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate that SimNow record/report/run_summary/ledger_summary artifacts stay consistent."
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--run-summary", type=Path, required=True)
    parser.add_argument("--record-json", type=Path, required=True)
    parser.add_argument("--ledger-summary", type=Path, required=True)
    parser.add_argument("--daily-brief", type=Path, required=True)
    parser.add_argument("--report-md", type=Path, required=True)
    parser.add_argument("--kline-json", type=Path)
    args = parser.parse_args()

    validate_artifacts(
        date=args.date,
        run_summary_path=args.run_summary,
        record_path=args.record_json,
        ledger_summary_path=args.ledger_summary,
        daily_brief_path=args.daily_brief,
        report_md_path=args.report_md,
        kline_path=args.kline_json,
    )
    print("summary consistency: ok")


if __name__ == "__main__":
    main()
