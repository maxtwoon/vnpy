from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"


def _prompt_text() -> str:
    return (DIAG / "AUTOMATION_PROMPT.md").read_text(encoding="utf-8")


def test_automation_prompt_uses_observation_duration_not_smoke_for_daily_run():
    text = _prompt_text()

    assert "-DurationSeconds 1800" in text
    assert "-MinKlineBarsPerSymbol 30" in text
    assert "-DurationSeconds 300 -SkipKlineUpdate" in text
    assert "-DurationSeconds 300\n" not in text


def test_automation_prompt_machine_source_is_run_summary_only():
    text = _prompt_text()

    assert "simnow_run_summary_YYYY-MM-DD.json" in text
    assert "最终机器判定来源" in text
    assert "simnow_run_summary_YYYY-MM-DD.json" in text
    assert "不要通过解析多个 markdown" in text or "不得通过解析多个 markdown" in text


def test_automation_prompt_human_report_source_is_daily_brief():
    text = _prompt_text()

    assert "simnow_daily_brief_YYYY-MM-DD.md" in text
    assert "人类可读日报来源" in text or "human-readable report" in text
    assert (
        "daily brief 只用于" in text
        or "不作为机器判定源" in text
        or "not the machine-readable source" in text.lower()
    )


def test_automation_prompt_includes_automation_status_fields():
    text = _prompt_text()

    for field in (
        "automation_status",
        "automation_exit_code",
        "automation_reason",
        "automation_action",
    ):
        assert field in text


def test_automation_prompt_includes_ledger_summary_fields_for_20d_progress():
    text = _prompt_text()

    for field in (
        "ledger_summary.valid_observation_days",
        "ledger_summary.consecutive_valid_days",
        "ledger_summary.ready_to_expand",
        "ledger_summary.promotion_blockers",
        "ledger_summary.next_action",
    ):
        assert field in text, f"missing {field}"


def test_automation_prompt_includes_status_handling_rules():
    text = _prompt_text()

    for status in ("valid", "skipped", "pending", "halt", "failed"):
        assert f"automation_status={status}" in text


def test_automation_prompt_includes_required_final_response_fields():
    text = _prompt_text()

    for field in (
        "date",
        "automation_status",
        "automation_exit_code",
        "automation_reason",
        "automation_action",
        "ledger_summary.valid_observation_days",
        "ledger_summary.consecutive_valid_days",
        "ledger_summary.ready_to_expand",
        "ledger_summary.promotion_blockers",
        "ledger_summary.next_action",
        "record.status",
        "record.valid_observation",
        "kline.missing_symbols",
        "kline.short_symbols",
    ):
        assert field in text, f"missing {field}"
    assert "是否需要用户处理" in text


def test_automation_prompt_declares_delayed_replay_as_strategy_pnl_source():
    text = _prompt_text()

    assert "delayed_replay" in text
    assert "local historical DB is the only strategy market-data source" in text
    assert "strategy PnL comes only from delayed replay" in text
    assert "SimNow account balance/PnL must not be used as strategy PnL" in text


def test_automation_prompt_reports_account_contamination_separately():
    text = _prompt_text()

    assert "account_contamination" in text
    assert "environment_capture" in text
    assert "external SimNow account activity is audit evidence only" in text


def test_automation_prompt_requires_read_only_no_orders():
    text = _prompt_text()

    assert "不得发送任何委托" in text or "read-only" in text.lower()
    assert "no orders" in text.lower() or "不发送" in text or "委托" in text


def test_automation_prompt_treats_skipped_not_as_code_failure():
    text = _prompt_text()

    assert "automation_status=skipped" in text
    assert "不算代码失败" in text or "不应当作代码失败" in text or "not a code failure" in text.lower()
    assert (
        "节假日" in text
        or "非交易时段" in text
        or "无 tick" in text
        or "无有效 tick" in text
        or "无行情" in text
    )
