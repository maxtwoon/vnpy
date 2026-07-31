from __future__ import annotations

from typing import Any

from simnow_structured_access import safe_get


def format_symbols(symbols: list[str] | None) -> str:
    """Format a symbol list for display; empty becomes '无'."""
    if not symbols:
        return "无"
    return ",".join(str(symbol) for symbol in symbols)


def format_bool(value: Any) -> str:
    """Format booleans as lowercase text for stable reports."""
    return str(bool(value)).lower()


def build_daily_brief_overview_lines(
    *,
    summary: dict[str, Any],
    action_meta: dict[str, Any],
    record_action: dict[str, Any],
    needs_user_action: bool,
) -> list[str]:
    """Render the overview bullet list for the daily brief."""
    record_status = safe_get(summary, "record", "status", default="")
    valid_observation = bool(safe_get(summary, "record", "valid_observation", default=False))
    missing_symbols = format_symbols(safe_get(summary, "kline", "missing_symbols", default=[]))
    short_symbols = format_symbols(safe_get(summary, "kline", "short_symbols", default=[]))
    valid_days = safe_get(summary, "promotion", "valid_observation_days", default=0)
    ready_to_expand = bool(safe_get(summary, "promotion", "ready_to_expand", default=False))

    return [
        f"- automation_status: `{safe_get(summary, 'automation_status', default='failed')}`",
        f"- automation_exit_code: `{safe_get(summary, 'automation_exit_code', default=40)}`",
        f"- automation_reason: `{safe_get(summary, 'automation_reason', default='') or '无'}`",
        f"- automation_action: `{safe_get(summary, 'automation_action', default='') or '无'}`",
        f"- operator_explanation_cn: `{safe_get(summary, 'operator_explanation_cn', default='') or '无'}`",
        f"- automation_action_class: `{action_meta['action_class']}`",
        f"- automation_blocker_class: `{action_meta['blocker_class']}`",
        f"- record.status: `{record_status or '无'}`",
        f"- record.valid_observation: `{str(valid_observation).lower()}`",
        f"- record.action_class: `{record_action.get('action_class', 'unknown')}`",
        f"- record.blocker_class: `{record_action.get('blocker_class', 'review_now')}`",
        f"- kline.missing_symbols: `{missing_symbols}`",
        f"- kline.short_symbols: `{short_symbols}`",
        f"- promotion.valid_observation_days: `{valid_days}`",
        f"- promotion.ready_to_expand: `{str(ready_to_expand).lower()}`",
        f"- needs_user_action: `{str(needs_user_action).lower()}`",
        f"- user_action_needed_reason_cn: `{safe_get(summary, 'user_action_needed_reason_cn', default='') or '无'}`",
    ]


def build_daily_brief_closing_lines(*, action: str, conclusion: str) -> list[str]:
    """Render the closing conclusion and next-step block."""
    return [
        "",
        "## 结论",
        "",
        conclusion,
        "",
        "## 下一步",
        "",
        f"按 automation_action 执行：{action or '无'}。",
        "",
    ]
