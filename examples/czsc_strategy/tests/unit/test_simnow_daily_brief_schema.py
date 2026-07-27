import sys
from pathlib import Path


DIAG = Path(__file__).resolve().parents[2] / "diagnostics"
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))

from simnow_daily_brief_schema import (  # noqa: E402
    build_daily_brief_closing_lines,
    build_daily_brief_overview_lines,
)


def test_daily_brief_overview_lines_match_contract():
    action_meta = {
        "action_class": "wait_for_data",
        "blocker_class": "wait",
    }
    record_action = {
        "action_class": "wait_for_data",
        "blocker_class": "wait",
    }
    summary = {
        "automation_status": "pending",
        "automation_exit_code": 20,
        "automation_reason": "kline_coverage_incomplete",
        "automation_action": "resolve pending gate before counting",
        "operator_explanation_cn": "当前不计入 20 日有效观察；等待数据。",
        "user_action_needed_reason_cn": "当前阻塞属于等待型，无需立刻人工介入。",
        "record": {
            "status": "pending",
            "valid_observation": False,
        },
        "kline": {
            "missing_symbols": ["AP888"],
            "short_symbols": ["A888", "RB888", "SC888", "ZN888"],
        },
        "promotion": {
            "valid_observation_days": 0,
            "ready_to_expand": False,
        },
    }

    assert build_daily_brief_overview_lines(
        summary=summary,
        action_meta=action_meta,
        record_action=record_action,
        needs_user_action=False,
    ) == [
        "- automation_status: `pending`",
        "- automation_exit_code: `20`",
        "- automation_reason: `kline_coverage_incomplete`",
        "- automation_action: `resolve pending gate before counting`",
        "- operator_explanation_cn: `当前不计入 20 日有效观察；等待数据。`",
        "- automation_action_class: `wait_for_data`",
        "- automation_blocker_class: `wait`",
        "- record.status: `pending`",
        "- record.valid_observation: `false`",
        "- record.action_class: `wait_for_data`",
        "- record.blocker_class: `wait`",
        "- kline.missing_symbols: `AP888`",
        "- kline.short_symbols: `A888,RB888,SC888,ZN888`",
        "- promotion.valid_observation_days: `0`",
        "- promotion.ready_to_expand: `false`",
        "- needs_user_action: `false`",
        "- user_action_needed_reason_cn: `当前阻塞属于等待型，无需立刻人工介入。`",
    ]


def test_daily_brief_closing_lines_match_contract():
    assert build_daily_brief_closing_lines(
        action="resolve pending gate before counting",
        conclusion="当前不计入 20 日有效观察；等待数据。",
    ) == [
        "",
        "## 结论",
        "",
        "当前不计入 20 日有效观察；等待数据。",
        "",
        "## 下一步",
        "",
        "按 automation_action 执行：resolve pending gate before counting。",
        "",
    ]
