from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from declassify_historical_reports import build_banner
from simnow_action_summary import action_recommendation


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE


def load_run_summary(path: Path) -> dict[str, Any]:
    """Load a run summary JSON if it exists; otherwise return an empty dict."""
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _safe_get(summary: dict[str, Any], *keys: str, default: Any = "") -> Any:
    """Safely navigate nested dict keys."""
    obj: Any = summary
    for key in keys:
        if isinstance(obj, dict):
            obj = obj.get(key, default)
        else:
            return default
    return obj


def _format_symbols(symbols: list[str] | None) -> str:
    """Format a symbol list for display; empty becomes '无'."""
    if not symbols:
        return "无"
    return ",".join(str(s) for s in symbols)


def _format_bool(value: Any) -> str:
    """Format booleans as lowercase text for stable reports."""
    return str(bool(value)).lower()


def needs_user_action(summary: dict[str, Any]) -> bool:
    """Return whether the daily result requires explicit human intervention.

    Rules:
      - halt / failed → True
      - workflow order safety breach → True
      - subscription incomplete → True
      - other pending / skipped / valid → False
    """
    status = _safe_get(summary, "automation_status", default="")
    reason = _safe_get(summary, "automation_reason", default="")
    if status in {"halt", "failed"}:
        return True
    if reason in {"workflow_order_safety_breach", "subscription_incomplete"}:
        return True
    return False


def _build_record_for_action(summary: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a monitor-shaped record so action_recommendation can produce Chinese text."""
    status = _safe_get(summary, "record", "status", default="")
    reason = _safe_get(summary, "record", "reason", default="")
    valid = bool(_safe_get(summary, "record", "valid_observation", default=False))

    record: dict[str, Any] = {
        "status": status,
        "valid_observation": valid,
    }
    if status == "skipped":
        record["skip_reason"] = reason
    elif status in {"pending", "halt"}:
        record["consistency"] = {"reason": reason}
        record["thresholds"] = {
            "status": _safe_get(summary, "record", "threshold_status", default="pass")
        }

    record["kline_coverage"] = {
        "missing_symbols": list(_safe_get(summary, "kline", "missing_symbols", default=[])),
        "short_symbols": list(_safe_get(summary, "kline", "short_symbols", default=[])),
        "min_bars_per_symbol": _safe_get(summary, "kline", "min_bars_per_symbol", default=None),
    }
    return record


def _conclusion_text(summary: dict[str, Any], action_text: str) -> str:
    """Produce a Chinese conclusion paragraph."""
    status = _safe_get(summary, "automation_status", default="failed")
    if status == "valid":
        return "今日已计入 20 日有效观察。"
    if status == "skipped":
        return f"当日未产生有效市场数据，不计入 20 日观察；这不是代码失败，{action_text}"
    if status == "pending":
        return f"当前不计入 20 日有效观察；{action_text}"
    if status == "halt":
        return f"观察流程触发停止条件，必须停止自动化并人工审查；{action_text}"
    fallback_action = _safe_get(
        summary, "automation_action", default="请检查 wrapper 输出和 artifact 完整性。"
    )
    return f"运行失败或缺少关键产物，无法判断当日状态；{fallback_action}"


def build_daily_brief(summary: dict[str, Any]) -> str:
    """Render a fixed-format Chinese daily brief from a run summary dict."""
    if not summary:
        summary = {
            "date": "unknown",
            "automation_status": "failed",
            "automation_exit_code": 40,
            "automation_reason": "missing run summary JSON",
            "automation_action": "check wrapper output and artifact completeness",
            "record": {},
            "kline": {},
            "promotion": {},
        }

    status = _safe_get(summary, "automation_status", default="failed")
    default_exit = 40 if status == "failed" else 0
    exit_code = _safe_get(summary, "automation_exit_code", default=default_exit)
    reason = _safe_get(summary, "automation_reason", default="")
    action = _safe_get(summary, "automation_action", default="")
    date = _safe_get(summary, "date", default="unknown")

    record_status = _safe_get(summary, "record", "status", default="")
    valid_observation = bool(_safe_get(summary, "record", "valid_observation", default=False))
    missing_symbols = _format_symbols(_safe_get(summary, "kline", "missing_symbols", default=[]))
    short_symbols = _format_symbols(_safe_get(summary, "kline", "short_symbols", default=[]))
    valid_days = _safe_get(summary, "promotion", "valid_observation_days", default=0)
    ready_to_expand = bool(_safe_get(summary, "promotion", "ready_to_expand", default=False))

    if status == "failed":
        action_text = action or "请检查 wrapper 输出和 artifact 完整性。"
    else:
        record_for_action = _build_record_for_action(summary)
        action_text = action_recommendation(record_for_action)["action"]

    conclusion = _conclusion_text(summary, action_text)

    lines = [
        f"# SimNow 每日观察日报 - {date}",
        "",
        build_banner().rstrip("\n"),
        "",
        f"- automation_status: `{status}`",
        f"- automation_exit_code: `{exit_code}`",
        f"- automation_reason: `{reason or '无'}`",
        f"- automation_action: `{action or '无'}`",
        f"- record.status: `{record_status or '无'}`",
        f"- record.valid_observation: `{str(valid_observation).lower()}`",
        f"- kline.missing_symbols: `{missing_symbols}`",
        f"- kline.short_symbols: `{short_symbols}`",
        f"- promotion.valid_observation_days: `{valid_days}`",
        f"- promotion.ready_to_expand: `{str(ready_to_expand).lower()}`",
        f"- needs_user_action: `{str(needs_user_action(summary)).lower()}`",
        "",
        "## SimNow 环境采集",
        "",
        f"- ticks: `{_safe_get(summary, 'environment_capture', 'ticks', default=0)}`",
        f"- contracts_count: `{_safe_get(summary, 'environment_capture', 'contracts_count', default=0)}`",
        f"- accounts: `{_safe_get(summary, 'environment_capture', 'accounts', default=0)}`",
        f"- subscribed_count: `{_safe_get(summary, 'environment_capture', 'subscribed_count', default=0)}`",
        f"- read_only: `{_format_bool(_safe_get(summary, 'environment_capture', 'read_only', default=False))}`",
        f"- orders_sent_by_workflow: `{_safe_get(summary, 'environment_capture', 'orders_sent_by_workflow', default=0)}`",
        "",
        "## 账户污染监控",
        "",
        f"- account_contamination.detected: `{_format_bool(_safe_get(summary, 'account_contamination', 'detected', default=False))}`",
        f"- external_orders: `{_safe_get(summary, 'account_contamination', 'orders', default=0)}`",
        f"- external_trades: `{_safe_get(summary, 'account_contamination', 'trades', default=0)}`",
        f"- external_active_positions: `{_safe_get(summary, 'account_contamination', 'active_positions', default=0)}`",
        f"- external_position_symbols: `{_format_symbols(_safe_get(summary, 'account_contamination', 'position_symbols', default=[]))}`",
        "- note: `SimNow 账户活动仅作为外部污染审计证据，不计入策略收益`",
        "",
        "## 盘后 DB 延迟回放",
        "",
        f"- delayed_replay.available: `{_format_bool(_safe_get(summary, 'delayed_replay', 'available', default=False))}`",
        f"- delayed_replay.status: `{_safe_get(summary, 'delayed_replay', 'status', default='') or '无'}`",
        f"- delayed_replay.valid_observation: `{_format_bool(_safe_get(summary, 'delayed_replay', 'valid_observation', default=False))}`",
        f"- delayed_replay.reason: `{_safe_get(summary, 'delayed_replay', 'reason', default='') or '无'}`",
        f"- latest_db_date: `{_safe_get(summary, 'delayed_replay', 'latest_db_date', default='') or '无'}`",
        f"- missing_or_lagged_symbols: `{_format_symbols(_safe_get(summary, 'delayed_replay', 'missing_or_lagged_symbols', default=[]))}`",
        f"- replay_signals: `{_safe_get(summary, 'delayed_replay', 'signals', default=0)}`",
        f"- replay_trades: `{_safe_get(summary, 'delayed_replay', 'trades', default=0)}`",
        f"- replay_positions: `{_safe_get(summary, 'delayed_replay', 'positions', default=0)}`",
        f"- risk_source: `{_safe_get(summary, 'delayed_replay', 'risk_source', default='replay_only')}`",
        "",
        "## 20 日进度",
        "",
    ]

    ledger_summary = summary.get("ledger_summary") or {}
    if ledger_summary.get("available"):
        min_days = ledger_summary.get("min_days", 20)
        lines.append(f"- valid_observation_days: `{ledger_summary.get('valid_observation_days', 0)}/{min_days}`")
        lines.append(f"- consecutive_valid_days: `{ledger_summary.get('consecutive_valid_days', 0)}`")
        lines.append(f"- ready_to_expand: `{str(ledger_summary.get('ready_to_expand', False)).lower()}`")
        blockers = ledger_summary.get("promotion_blockers") or []
        lines.append(f"- promotion_blockers: `{','.join(str(b) for b in blockers) or '无'}`")
    else:
        lines.append("- ledger_summary 不可用")

    lines.extend([
        "",
        "## 结论",
        "",
        conclusion,
        "",
        "## 下一步",
        "",
        f"按 automation_action 执行：{action or '无'}。",
        "",
    ])
    return "\n".join(lines)


# Backward-compatible alias for existing callers and tests.
render_daily_brief = build_daily_brief


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Generate a fixed-format Chinese daily brief from a SimNow run summary JSON."
    )
    parser.add_argument("--date", required=True, help="Observation date (YYYY-MM-DD).")
    parser.add_argument("--run-summary", type=Path, help="Path to simnow_run_summary_YYYY-MM-DD.json.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Directory to write the brief markdown.")
    parser.add_argument("--out-md", type=Path, help="Path to write the brief markdown (overrides default).")
    args = parser.parse_args()

    run_summary_path = args.run_summary or (args.out_dir / f"simnow_run_summary_{args.date}.json")
    out_md_path = args.out_md or (args.out_dir / f"simnow_daily_brief_{args.date}.md")

    summary = load_run_summary(run_summary_path)
    brief = build_daily_brief(summary)

    out_md_path.parent.mkdir(parents=True, exist_ok=True)
    out_md_path.write_text(brief, encoding="utf-8")
    print(brief)


if __name__ == "__main__":
    main()
