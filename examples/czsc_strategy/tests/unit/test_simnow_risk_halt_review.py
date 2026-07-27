import json
import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_risk_halt_review import build_review_pack, render_review_markdown  # noqa: E402


def _summary(status: str = "halt") -> dict:
    return {
        "date": "2026-07-24",
        "automation_status": status,
        "automation_exit_code": 30 if status == "halt" else 0,
        "automation_reason": "consecutive_loss_abs_pct" if status == "halt" else "",
        "automation_action": "stop automation and review manually" if status == "halt" else "counts_for_20d",
        "automation_action_class": "manual_review_required" if status == "halt" else "counts_for_20d",
        "automation_blocker_class": "review_now" if status == "halt" else "none",
        "user_action_needed": status == "halt",
        "formal_readiness": {"overall_ready": True, "blocking_reasons": []},
        "environment_capture": {
            "ticks": 34781,
            "contracts_count": 18052,
            "subscribed_count": 4,
            "read_only": True,
            "orders_sent_by_workflow": 0,
            "zero_tick_subscribed_symbols": [],
        },
        "capture": {"accounts": 1, "positions": 1, "orders": 0, "trades": 0},
        "record": {
            "status": status,
            "valid_observation": False,
            "reason": "consecutive_loss_abs_pct" if status == "halt" else "",
            "threshold_status": "halt" if status == "halt" else "pass",
            "order_safety_status": "pass",
            "consistency_matched": True,
            "threshold_diagnostics": [
                {
                    "metric": "consecutive_loss_abs_pct",
                    "level": "halt",
                    "value": 0.1217590817,
                    "warning": 0.0581202076,
                    "halt": 0.0645780084,
                    "baseline": 0.0645780084,
                    "unit": "%",
                    "warning_gap": 0.0636388741,
                    "halt_gap": 0.0571810733,
                },
            ],
            "halt_rule_id": "threshold_breach",
            "halt_family": "strategy_risk",
            "halt_severity": "critical",
            "halt_trigger_metrics": ["consecutive_loss_abs_pct"],
        },
        "delayed_replay": {
            "available": True,
            "status": status,
            "reason": "no_actionable_events_on_either_side",
            "latest_db_date": "2026-07-24",
            "signals": 4,
            "trades": 0,
            "positions": 11,
            "risk_source": "replay_only",
        },
        "risk_source_breakdown": {
            "consecutive_loss": {
                "available": True,
                "complete": True,
                "rows_available": True,
                "reason": "",
                "source": "delayed_replay.risk.consecutive_loss",
                "days": 6,
                "cumulative_return_pct": -0.1217590817,
                "abs_cumulative_return_pct": 0.1217590817,
                "start_date": "2023-06-19",
                "end_date": "2023-06-28",
                "rows": [
                    {"date": "2023-06-19", "daily_return_pct": -0.0079, "equity": 0.9983},
                    {"date": "2023-06-28", "daily_return_pct": -0.0157, "equity": 0.9972},
                ],
            }
        },
    }


def test_build_review_pack_for_strategy_risk_halt():
    pack = build_review_pack(_summary())

    assert pack["date"] == "2026-07-24"
    assert pack["applicable"] is True
    assert pack["review_status"] == "requires_manual_review"
    assert pack["automation_status"] == "halt"
    assert pack["automation_reason"] == "consecutive_loss_abs_pct"
    assert pack["manual_review"]["required"] is True
    assert pack["manual_review"]["decision_options"] == [
        "keep_halted",
        "adjust_thresholds_with_documented_rationale",
        "retire_candidate",
        "reset_observation_window_after_strategy_change",
    ]
    assert pack["safety_snapshot"] == {
        "read_only": True,
        "orders_sent_by_workflow": 0,
        "orders": 0,
        "trades": 0,
        "order_safety_status": "pass",
    }
    assert pack["threshold_diagnostics"][0]["metric"] == "consecutive_loss_abs_pct"
    assert pack["consecutive_loss"]["complete"] is True
    assert pack["consecutive_loss"]["rows"][0]["date"] == "2023-06-19"
    assert "password" not in json.dumps(pack, ensure_ascii=False).lower()


def test_build_review_pack_not_applicable_for_non_halt():
    pack = build_review_pack(_summary(status="valid"))

    assert pack["applicable"] is False
    assert pack["review_status"] == "not_applicable"
    assert pack["manual_review"]["required"] is False


def test_render_review_markdown_contains_key_sections():
    text = render_review_markdown(build_review_pack(_summary()))

    assert "# SimNow 风险停线人工复核包 - 2026-07-24" in text
    assert "automation_status: `halt`" in text
    assert "## 阈值诊断" in text
    assert "consecutive_loss_abs_pct" in text
    assert "## 连续亏损来源" in text
    assert "2023-06-19" in text
    assert "## 人工决策选项" in text
