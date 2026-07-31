from __future__ import annotations

from simnow_action_summary import action_recommendation
from simnow_structured_access import safe_get


def build_record_for_action(summary: dict[str, object]) -> dict[str, object]:
    """Rebuild a monitor-shaped record so action_recommendation can produce text."""
    status = safe_get(summary, "record", "status", default="") or safe_get(summary, "automation_status", default="")
    reason = safe_get(summary, "record", "reason", default="") or safe_get(summary, "automation_reason", default="")
    valid = bool(safe_get(summary, "record", "valid_observation", default=False))

    record: dict[str, object] = {
        "status": status,
        "valid_observation": valid,
    }
    if status == "skipped":
        record["skip_reason"] = reason
    elif status in {"pending", "halt"}:
        record["consistency"] = {"reason": reason}
        record["thresholds"] = {
            "status": safe_get(summary, "record", "threshold_status", default="pass"),
            "rows": list(safe_get(summary, "record", "threshold_rows", default=[])),
        }

    record["kline_coverage"] = {
        "missing_symbols": list(safe_get(summary, "kline", "missing_symbols", default=[])),
        "short_symbols": list(safe_get(summary, "kline", "short_symbols", default=[])),
        "min_bars_per_symbol": safe_get(summary, "kline", "min_bars_per_symbol", default=None),
    }
    return record


def resolve_action_meta(summary: dict[str, object]) -> dict[str, str]:
    """Resolve machine-readable action metadata for the current run."""
    status = safe_get(summary, "automation_status", default="")
    if status == "failed":
        return {
            "action_class": str(safe_get(summary, "automation_action_class", default="unknown") or "unknown"),
            "blocker_class": str(safe_get(summary, "automation_blocker_class", default="review_now") or "review_now"),
        }

    record_action = action_recommendation(build_record_for_action(summary))
    return {
        "action_class": str(
            safe_get(summary, "automation_action_class", default=record_action["action_class"])
            or record_action["action_class"]
        ),
        "blocker_class": str(
            safe_get(summary, "automation_blocker_class", default=record_action["blocker_class"])
            or record_action["blocker_class"]
        ),
    }


def automation_action_text(summary: dict[str, object]) -> str:
    """Resolve the human-facing action text for the current run."""
    status = safe_get(summary, "automation_status", default="")
    action = safe_get(summary, "automation_action", default="")
    if status == "failed":
        return str(action or "check wrapper output and artifact completeness")
    return str(action_recommendation(build_record_for_action(summary))["action"])


def needs_user_action(summary: dict[str, object]) -> bool:
    """Return whether the daily result requires explicit human intervention."""
    status = safe_get(summary, "automation_status", default="")
    reason = safe_get(summary, "automation_reason", default="")

    if status in {"halt", "failed"}:
        return True
    if status in {"valid", "skipped"}:
        return False

    blocker_class = resolve_action_meta(summary)["blocker_class"]
    if blocker_class == "review_now":
        return True
    if reason in {"workflow_order_safety_breach", "subscription_incomplete"}:
        return True
    return False


def user_action_needed_reason_cn(summary: dict[str, object]) -> str:
    """Explain in Chinese why human action is or is not needed."""
    status = safe_get(summary, "automation_status", default="")
    if needs_user_action(summary):
        return "当前结果要求人工立即处理。"
    if status == "valid":
        return "当前结果无需人工处理。"
    if status == "skipped":
        return "当前为跳过日，等待下一个有效时段即可。"
    return "当前阻塞属于等待型，无需立刻人工介入。"


def conclusion_text(summary: dict[str, object], action_text: str) -> str:
    """Produce a Chinese conclusion paragraph."""
    status = safe_get(summary, "automation_status", default="failed")
    if status == "valid":
        return "今日计入 20 日有效观察。"
    if status == "skipped":
        return f"当日未产生有效市场数据，不计入 20 日观察；这不是代码失败，{action_text}"
    if status == "pending":
        return f"当前不计入 20 日有效观察；{action_text}"
    if status == "halt":
        return f"观察流程触发停止条件，必须停止自动化并人工审查；{action_text}"
    fallback_action = safe_get(
        summary,
        "automation_action",
        default="请检查 wrapper 输出和 artifact 完整性。",
    )
    return f"运行失败或缺少关键产物，无法判断当日状态；{fallback_action}"


def operator_explanation_cn(summary: dict[str, object]) -> str:
    """Return the operator-facing Chinese conclusion text."""
    return conclusion_text(summary, automation_action_text(summary))


def classify_automation_status(summary: dict[str, object]) -> dict[str, object]:
    """Derive the external automation status from a run summary."""
    record = summary.get("record") or {}
    status = str(record.get("status") or "")
    reason = str(record.get("reason") or "")
    valid = bool(record.get("valid_observation"))
    action_row = action_recommendation(build_record_for_action(summary))

    if status == "pass" and valid:
        return {
            "automation_status": "valid",
            "automation_exit_code": 0,
            "automation_reason": reason,
            "automation_action": "counts_for_20d",
            "automation_action_class": "counts_for_20d",
            "automation_blocker_class": "none",
        }
    if status == "skipped":
        return {
            "automation_status": "skipped",
            "automation_exit_code": 10,
            "automation_reason": reason,
            "automation_action": "no valid market data / rerun next valid session",
            "automation_action_class": str(action_row.get("action_class") or "rerun_next_session"),
            "automation_blocker_class": str(action_row.get("blocker_class") or "wait"),
        }
    if status == "pending":
        return {
            "automation_status": "pending",
            "automation_exit_code": 20,
            "automation_reason": reason,
            "automation_action": "resolve pending gate before counting",
            "automation_action_class": str(action_row.get("action_class") or "resolve_observation_gaps"),
            "automation_blocker_class": str(action_row.get("blocker_class") or "review_now"),
        }
    if status == "halt":
        return {
            "automation_status": "halt",
            "automation_exit_code": 30,
            "automation_reason": reason,
            "automation_action": "stop automation and review manually",
            "automation_action_class": str(action_row.get("action_class") or "manual_review_required"),
            "automation_blocker_class": str(action_row.get("blocker_class") or "review_now"),
        }
    return {
        "automation_status": "failed",
        "automation_exit_code": 40,
        "automation_reason": reason or "missing critical artifact or unknown status",
        "automation_action": "missing critical artifact or unknown status",
        "automation_action_class": "unknown",
        "automation_blocker_class": "review_now",
    }
