import json
import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_daily_brief import (  # noqa: E402
    build_daily_brief,
    load_run_summary,
    needs_user_action,
    render_daily_brief,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _sample_run_summary(date: str = "2026-07-01") -> dict:
    return {
        "date": date,
        "automation_status": "pending",
        "automation_exit_code": 20,
        "automation_reason": "kline_coverage_incomplete",
        "automation_action": "resolve pending gate before counting",
        "automation_action_class": "wait_for_data",
        "automation_blocker_class": "wait",
        "operator_explanation_cn": "当前不计入 20 日有效观察；缺少 K 线覆盖。",
        "user_action_needed_reason_cn": "当前阻塞属于等待型，无需立刻人工介入。",
        "record": {
            "status": "pending",
            "valid_observation": False,
            "reason": "kline_coverage_incomplete",
            "threshold_status": "pass",
            "order_safety_status": "pass",
            "consistency_matched": False,
        },
        "kline": {
            "missing_symbols": ["AP888"],
            "short_symbols": ["A888", "RB888", "SC888", "ZN888"],
            "min_bars_per_symbol": 30,
        },
        "promotion": {
            "valid_observation_days": 0,
            "ready_to_expand": False,
        },
    }


def test_render_daily_brief_contains_required_fields():
    summary = _sample_run_summary()
    text = render_daily_brief(summary)

    assert text.startswith("# SimNow 每日观察日报 - 2026-07-01")
    assert "automation_status: `pending`" in text
    assert "automation_exit_code: `20`" in text
    assert "automation_reason: `kline_coverage_incomplete`" in text
    assert "automation_action: `resolve pending gate before counting`" in text
    assert "operator_explanation_cn: `当前不计入 20 日有效观察；缺少 K 线覆盖。`" in text
    assert "automation_action_class: `wait_for_data`" in text
    assert "automation_blocker_class: `wait`" in text
    assert "record.status: `pending`" in text
    assert "record.valid_observation: `false`" in text
    assert "record.action_class: `wait_for_data`" in text
    assert "record.blocker_class: `wait`" in text
    assert "kline.missing_symbols: `AP888`" in text
    assert "kline.short_symbols: `A888,RB888,SC888,ZN888`" in text
    assert "promotion.valid_observation_days: `0`" in text
    assert "promotion.ready_to_expand: `false`" in text
    assert "needs_user_action: `false`" in text
    assert "user_action_needed_reason_cn: `当前阻塞属于等待型，无需立刻人工介入。`" in text
    assert "## 结论" in text
    assert "## 下一步" in text
    assert "resolve pending gate before counting" in text


def test_render_daily_brief_valid_observation():
    summary = _sample_run_summary()
    summary["automation_status"] = "valid"
    summary["automation_exit_code"] = 0
    summary["automation_reason"] = ""
    summary["automation_action"] = "counts_for_20d"
    summary["record"]["status"] = "pass"
    summary["record"]["valid_observation"] = True
    summary["record"]["reason"] = ""
    summary["kline"]["missing_symbols"] = []
    summary["kline"]["short_symbols"] = []
    summary["promotion"]["valid_observation_days"] = 5
    summary["promotion"]["ready_to_expand"] = False

    text = render_daily_brief(summary)

    assert "automation_status: `valid`" in text
    assert "needs_user_action: `false`" in text
    assert "计入 20 日有效观察" in text or "有效观察" in text


def test_render_daily_brief_halt_needs_user_action():
    summary = _sample_run_summary()
    summary["automation_status"] = "halt"
    summary["automation_exit_code"] = 30
    summary["automation_reason"] = "consecutive_loss_abs_pct"
    summary["automation_action"] = "stop automation and review manually"
    summary["record"]["status"] = "halt"
    summary["record"]["reason"] = "consecutive_loss_abs_pct"
    summary["record"]["threshold_status"] = "halt"
    summary["record"]["threshold_rows"] = [
        {"metric": "drawdown_abs_pct", "value": 1.2992, "level": "warning", "unit": "%"},
        {"metric": "consecutive_loss_abs_pct", "value": 0.1218, "level": "halt", "unit": "%"},
    ]
    summary["record"]["threshold_diagnostics"] = [
        {
            "metric": "drawdown_abs_pct",
            "level": "warning",
            "value": 1.2992,
            "warning": 1.1854,
            "halt": 1.3171,
            "warning_gap": 0.1138,
            "halt_gap": -0.0179,
            "unit": "%",
        },
        {
            "metric": "consecutive_loss_abs_pct",
            "level": "halt",
            "value": 0.1218,
            "warning": 0.0581,
            "halt": 0.0646,
            "warning_gap": 0.0637,
            "halt_gap": 0.0572,
            "unit": "%",
        },
    ]
    summary["risk_source_breakdown"] = {
        "consecutive_loss": {
            "available": True,
            "complete": True,
            "rows_available": True,
            "reason": "",
            "source": "delayed_replay.risk.consecutive_loss",
            "days": 3,
            "cumulative_return_pct": -0.1217590817,
            "abs_cumulative_return_pct": 0.1217590817,
            "start_date": "2026-07-22",
            "end_date": "2026-07-24",
            "rows": [
                {"date": "2026-07-22", "daily_return_pct": -0.0401, "equity": 0.9996},
                {"date": "2026-07-23", "daily_return_pct": -0.0502, "equity": 0.9991},
                {"date": "2026-07-24", "daily_return_pct": -0.0314590817, "equity": 0.9988},
            ],
        },
    }

    text = render_daily_brief(summary)

    assert "automation_status: `halt`" in text
    assert "needs_user_action: `true`" in text
    assert "consecutive_loss_abs_pct=0.1218%" in text
    assert "## 阈值诊断" in text
    assert "drawdown_abs_pct: `warning` (value=1.2992%, warning=1.1854%, halt=1.3171%, warning_gap=0.1138%, halt_gap=-0.0179%)" in text
    assert "## 风险来源拆解" in text
    assert "consecutive_loss: `available=true`, complete=`true`, rows_available=`true`, reason=`无`, source=`delayed_replay.risk.consecutive_loss`, days=`3`" in text
    assert "2026-07-24: daily_return=`-0.0315%`, equity=`0.9988`" in text


def test_render_daily_brief_failed_missing_run_summary():
    text = render_daily_brief({})

    assert "automation_status: `failed`" in text
    assert "automation_exit_code: `40`" in text
    assert "needs_user_action: `true`" in text


def test_cli_writes_default_brief_path(tmp_path):
    date = "2026-07-01"
    summary_path = tmp_path / f"simnow_run_summary_{date}.json"
    _write_json(summary_path, _sample_run_summary(date))

    expected_md = tmp_path / f"simnow_daily_brief_{date}.md"

    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            str(DIAG / "simnow_daily_brief.py"),
            "--date",
            date,
            "--run-summary",
            str(summary_path),
            "--out-dir",
            str(tmp_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert result.returncode == 0
    assert expected_md.exists()
    md_text = expected_md.read_text(encoding="utf-8")
    assert "# SimNow 每日观察日报" in md_text


def test_load_run_summary_missing_file_returns_empty():
    assert load_run_summary(Path("/tmp/simnow_daily_brief_nonexistent.json")) == {}


def test_public_needs_user_action_covers_required_cases():
    assert needs_user_action({"automation_status": "halt"}) is True
    assert needs_user_action({"automation_status": "failed"}) is True
    assert needs_user_action({"automation_status": "pending", "automation_blocker_class": "review_now"}) is True
    assert needs_user_action({"automation_status": "pending", "automation_blocker_class": "wait"}) is False
    assert needs_user_action({"automation_status": "pending", "automation_reason": "workflow_order_safety_breach"}) is True
    assert needs_user_action({"automation_status": "pending", "automation_reason": "subscription_incomplete"}) is True
    assert needs_user_action({"automation_status": "pending", "automation_reason": "kline_coverage_incomplete"}) is False
    assert needs_user_action({"automation_status": "skipped", "automation_reason": "simnow_no_ticks"}) is False
    assert needs_user_action({"automation_status": "valid"}) is False


def test_public_build_daily_brief_matches_render_daily_brief():
    summary = _sample_run_summary()
    assert build_daily_brief(summary) == render_daily_brief(summary)


def test_pending_subscription_incomplete_needs_user_action():
    summary = _sample_run_summary()
    summary["automation_status"] = "pending"
    summary["automation_exit_code"] = 20
    summary["automation_reason"] = "subscription_incomplete"
    summary["automation_action"] = "resolve pending gate before counting"
    summary["record"]["status"] = "pending"
    summary["record"]["reason"] = "subscription_incomplete"

    text = render_daily_brief(summary)

    assert "needs_user_action: `true`" in text
    assert needs_user_action(summary) is True


def test_skipped_simnow_no_ticks_is_not_code_failure():
    summary = _sample_run_summary()
    summary["automation_status"] = "skipped"
    summary["automation_exit_code"] = 10
    summary["automation_reason"] = "simnow_no_ticks"
    summary["automation_action"] = "no valid market data / rerun next valid session"
    summary["record"]["status"] = "skipped"
    summary["record"]["reason"] = "simnow_no_ticks"
    summary["kline"]["missing_symbols"] = []
    summary["kline"]["short_symbols"] = []

    text = render_daily_brief(summary)

    assert "automation_status: `skipped`" in text
    assert "needs_user_action: `false`" in text
    assert needs_user_action(summary) is False
    assert "不算代码失败" in text or "不是代码失败" in text or "不要当作代码失败" in text


def test_render_daily_brief_includes_20d_progress():
    summary = _sample_run_summary()
    summary["ledger_summary"] = {
        "available": True,
        "min_days": 20,
        "valid_observation_days": 3,
        "consecutive_valid_days": 2,
        "ready_to_expand": False,
        "promotion_blockers": ["need_17_more_valid_observation_days"],
    }

    text = render_daily_brief(summary)

    assert "## 20 日进度" in text
    assert "valid_observation_days: `3/20`" in text
    assert "consecutive_valid_days: `2`" in text
    assert "ready_to_expand: `false`" in text
    assert "promotion_blockers: `need_17_more_valid_observation_days`" in text


def test_render_daily_brief_separates_environment_account_and_delayed_replay():
    summary = _sample_run_summary("2026-07-13")
    summary["environment_capture"] = {
        "ticks": 4,
        "contracts_count": 18023,
        "accounts": 1,
        "subscribed_count": 5,
        "read_only": True,
        "orders_sent_by_workflow": 0,
    }
    summary["account_contamination"] = {
        "detected": True,
        "orders": 0,
        "trades": 0,
        "active_positions": 1,
        "position_symbols": ["sc2608"],
        "note": "SimNow account activity is external audit evidence only; it is not strategy PnL.",
    }
    summary["delayed_replay"] = {
        "available": False,
        "status": "pending",
        "valid_observation": False,
        "reason": "historical_db_lag",
        "latest_db_date": "2026-07-13",
        "missing_or_lagged_symbols": ["RB888", "ZN888"],
        "signals": 0,
        "trades": 0,
        "positions": 0,
        "risk_source": "replay_only",
    }

    text = render_daily_brief(summary)

    assert "## SimNow 环境采集" in text
    assert "ticks: `4`" in text
    assert "read_only: `true`" in text
    assert "orders_sent_by_workflow: `0`" in text
    assert "## 账户污染监控" in text
    assert "account_contamination.detected: `true`" in text
    assert "external_position_symbols: `sc2608`" in text
    assert "不计入策略收益" in text
    assert "## 盘后 DB 延迟回放" in text
    assert "delayed_replay.available: `false`" in text
    assert "missing_or_lagged_symbols: `RB888,ZN888`" in text
    assert "risk_source: `replay_only`" in text


def test_render_daily_brief_includes_historical_db_update_status():
    summary = _sample_run_summary()
    summary["historical_db_update"] = {
        "status": "passed",
        "exit_code": 0,
        "started_at": "2026-07-14T01:00:00+08:00",
        "ended_at": "2026-07-14T04:20:00+08:00",
    }

    text = render_daily_brief(summary)

    assert "## 历史 DB 更新" in text
    assert "historical_db_update.status: `passed`" in text
    assert "historical_db_update.exit_code: `0`" in text
    assert "2026-07-14T01:00:00+08:00" in text
    assert "9500" not in text
    assert "账户浮盈" not in text


def test_render_daily_brief_handles_missing_ledger_summary():
    summary = _sample_run_summary()
    summary["ledger_summary"] = {"available": False, "reason": "missing_ledger_summary"}

    text = render_daily_brief(summary)

    assert "ledger_summary 不可用" in text


def test_render_daily_brief_includes_window_fields():
    summary = _sample_run_summary()
    summary["ledger_summary"] = {
        "available": True,
        "min_days": 20,
        "valid_observation_days": 3,
        "consecutive_valid_days": 2,
        "ready_to_expand": False,
        "observation_start_date": "2026-04-14",
        "excluded_before_start_count": 12,
        "next_action": "continue_observation",
        "next_action_class": "continue_observation",
        "promotion_blockers": ["need_17_more_valid_observation_days"],
    }

    text = render_daily_brief(summary)

    assert "observation_start_date: `2026-04-14`" in text
    assert "excluded_before_start_count: `12`" in text
    assert "next_action: `continue_observation`" in text
    assert "next_action_class: `continue_observation`" in text


def test_render_daily_brief_includes_operational_bucket_counts():
    summary = _sample_run_summary()
    summary["ledger_summary"] = {
        "available": True,
        "min_days": 20,
        "valid_observation_days": 3,
        "consecutive_valid_days": 2,
        "ready_to_expand": False,
        "promotion_blockers": ["need_17_more_valid_observation_days"],
        "blocking_action_counts": {
            "rerun_next_session": 1,
            "wait_for_data": 2,
        },
        "operational_bucket_counts": {
            "data_pending_days": 2,
            "infra_pending_days": 1,
            "strategy_risk_halt_days": 1,
            "trading_session_skipped_days": 1,
        },
        "reason_governance_counts": {
            "data_readiness_gap": 2,
            "expected_market_or_session": 1,
            "workflow_safety_halt": 1,
        },
        "reason_rationality_verdict": "mixed_action_required",
        "pareto_summary": {
            "top3_share_pct": 100.0,
        },
    }

    text = render_daily_brief(summary)

    assert "reason_rationality_verdict: `mixed_action_required`" in text
    assert "pareto_summary.top3_share_pct: `100.0`" in text
    assert "reason_governance_counts.data_readiness_gap: `2`" in text
    assert "reason_governance_counts.expected_market_or_session: `1`" in text
    assert "reason_governance_counts.workflow_safety_halt: `1`" in text
    assert "operational_bucket_counts.data_pending_days: `2`" in text
    assert "operational_bucket_counts.infra_pending_days: `1`" in text
    assert "operational_bucket_counts.strategy_risk_halt_days: `1`" in text
    assert "operational_bucket_counts.trading_session_skipped_days: `1`" in text
    assert "blocking_action_counts.rerun_next_session: `1`" in text
    assert "blocking_action_counts.wait_for_data: `2`" in text


def test_render_daily_brief_uses_blocker_class_for_manual_review_signal():
    summary = _sample_run_summary()
    summary["automation_reason"] = "historical_db_lag"
    summary["automation_action_class"] = "investigate_infra"
    summary["automation_blocker_class"] = "review_now"

    text = render_daily_brief(summary)

    assert "needs_user_action: `true`" in text
    assert needs_user_action(summary) is True


def test_render_daily_brief_missing_window_fields_no_crash():
    summary = _sample_run_summary()
    summary["ledger_summary"] = {
        "available": True,
        "min_days": 20,
        "valid_observation_days": 3,
        "consecutive_valid_days": 2,
        "ready_to_expand": False,
        "promotion_blockers": [],
    }

    text = render_daily_brief(summary)

    assert "## 20 日进度" in text
    assert "observation_start_date: `无`" in text
    assert "excluded_before_start_count: `无`" in text
    assert "next_action: `无`" in text
