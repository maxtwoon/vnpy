from __future__ import annotations

import json
from typing import Any

from simnow_daily_brief_schema import format_bool, format_symbols, safe_get


def build_environment_capture_section_lines(summary: dict[str, Any]) -> list[str]:
    """Render the environment capture section lines."""
    return [
        "## SimNow 环境采集",
        "",
        f"- ticks: `{safe_get(summary, 'environment_capture', 'ticks', default=0)}`",
        f"- contracts_count: `{safe_get(summary, 'environment_capture', 'contracts_count', default=0)}`",
        f"- accounts: `{safe_get(summary, 'environment_capture', 'accounts', default=0)}`",
        f"- subscribed_count: `{safe_get(summary, 'environment_capture', 'subscribed_count', default=0)}`",
        f"- read_only: `{format_bool(safe_get(summary, 'environment_capture', 'read_only', default=False))}`",
        f"- orders_sent_by_workflow: `{safe_get(summary, 'environment_capture', 'orders_sent_by_workflow', default=0)}`",
        f"- tick_counts_by_symbol: `{json.dumps(safe_get(summary, 'environment_capture', 'tick_counts_by_symbol', default={}), ensure_ascii=False, sort_keys=True)}`",
        f"- zero_tick_subscribed_symbols: `{format_symbols(safe_get(summary, 'environment_capture', 'zero_tick_subscribed_symbols', default=[]))}`",
        "",
    ]


def build_historical_db_update_section_lines(summary: dict[str, Any]) -> list[str]:
    """Render the historical DB update section lines."""
    return [
        "## 历史 DB 更新",
        "",
        f"- historical_db_update.status: `{safe_get(summary, 'historical_db_update', 'status', default='skipped')}`",
        f"- historical_db_update.exit_code: `{safe_get(summary, 'historical_db_update', 'exit_code', default='')}`",
        f"- historical_db_update.started_at: `{safe_get(summary, 'historical_db_update', 'started_at', default='') or '无'}`",
        f"- historical_db_update.ended_at: `{safe_get(summary, 'historical_db_update', 'ended_at', default='') or '无'}`",
        "",
    ]


def build_account_contamination_section_lines(summary: dict[str, Any]) -> list[str]:
    """Render the account contamination section lines."""
    return [
        "## 账户污染监控",
        "",
        f"- account_contamination.detected: `{format_bool(safe_get(summary, 'account_contamination', 'detected', default=False))}`",
        f"- external_orders: `{safe_get(summary, 'account_contamination', 'orders', default=0)}`",
        f"- external_trades: `{safe_get(summary, 'account_contamination', 'trades', default=0)}`",
        f"- external_active_positions: `{safe_get(summary, 'account_contamination', 'active_positions', default=0)}`",
        f"- external_position_symbols: `{format_symbols(safe_get(summary, 'account_contamination', 'position_symbols', default=[]))}`",
        "- note: `SimNow 账户活动仅作为外部污染审计证据，不计入策略收益`",
        "",
    ]


def build_delayed_replay_section_lines(summary: dict[str, Any]) -> list[str]:
    """Render the delayed replay section lines."""
    return [
        "## 盘后 DB 延迟回放",
        "",
        f"- delayed_replay.available: `{format_bool(safe_get(summary, 'delayed_replay', 'available', default=False))}`",
        f"- delayed_replay.status: `{safe_get(summary, 'delayed_replay', 'status', default='') or '无'}`",
        f"- delayed_replay.valid_observation: `{format_bool(safe_get(summary, 'delayed_replay', 'valid_observation', default=False))}`",
        f"- delayed_replay.reason: `{safe_get(summary, 'delayed_replay', 'reason', default='') or '无'}`",
        f"- latest_db_date: `{safe_get(summary, 'delayed_replay', 'latest_db_date', default='') or '无'}`",
        f"- missing_or_lagged_symbols: `{format_symbols(safe_get(summary, 'delayed_replay', 'missing_or_lagged_symbols', default=[]))}`",
        f"- replay_signals: `{safe_get(summary, 'delayed_replay', 'signals', default=0)}`",
        f"- replay_trades: `{safe_get(summary, 'delayed_replay', 'trades', default=0)}`",
        f"- replay_positions: `{safe_get(summary, 'delayed_replay', 'positions', default=0)}`",
        f"- risk_source: `{safe_get(summary, 'delayed_replay', 'risk_source', default='replay_only')}`",
        "",
    ]


def build_threshold_diagnostics_section_lines(summary: dict[str, Any]) -> list[str]:
    """Render breached/warning threshold diagnostics for manual review."""
    diagnostics = safe_get(summary, "record", "threshold_diagnostics", default=[])
    if not diagnostics:
        return []

    lines = [
        "## 阈值诊断",
        "",
    ]
    for row in diagnostics:
        unit = str(row.get("unit") or "")
        value = row.get("value")
        warning = row.get("warning")
        halt = row.get("halt")
        warning_gap = row.get("warning_gap")
        halt_gap = row.get("halt_gap")
        suffix = unit
        lines.append(
            f"- {row.get('metric', '')}: `{row.get('level', '')}` "
            f"(value={value:.4f}{suffix}, warning={warning:.4f}{suffix}, halt={halt:.4f}{suffix}, "
            f"warning_gap={warning_gap:.4f}{suffix}, halt_gap={halt_gap:.4f}{suffix})"
        )
    lines.append("")
    return lines


def build_risk_source_breakdown_section_lines(summary: dict[str, Any]) -> list[str]:
    """Render replay risk source details needed to audit threshold halts."""
    consecutive = safe_get(summary, "risk_source_breakdown", "consecutive_loss", default={})
    if not consecutive or not bool(consecutive.get("available")):
        return []

    rows = list(consecutive.get("rows") or [])
    lines = [
        "## 风险来源拆解",
        "",
        "- consecutive_loss: "
        f"`available={format_bool(consecutive.get('available'))}`, "
        f"complete=`{format_bool(consecutive.get('complete'))}`, "
        f"rows_available=`{format_bool(consecutive.get('rows_available'))}`, "
        f"reason=`{consecutive.get('reason', '') or '无'}`, "
        f"source=`{consecutive.get('source', '')}`, "
        f"days=`{int(consecutive.get('days', 0) or 0)}`, "
        f"start=`{consecutive.get('start_date', '') or '无'}`, "
        f"end=`{consecutive.get('end_date', '') or '无'}`, "
        f"cumulative_return=`{float(consecutive.get('cumulative_return_pct', 0.0) or 0.0):.4f}%`, "
        f"abs_cumulative_return=`{float(consecutive.get('abs_cumulative_return_pct', 0.0) or 0.0):.4f}%`",
    ]
    if not rows:
        lines.append("- streak_rows: `无`")
        lines.append("")
        return lines

    lines.append("- streak_rows:")
    for row in rows:
        lines.append(
            f"- {row.get('date', '')}: "
            f"daily_return=`{float(row.get('daily_return_pct', 0.0) or 0.0):.4f}%`, "
            f"equity=`{float(row.get('equity', 0.0) or 0.0):.4f}`"
        )
    lines.append("")
    return lines
