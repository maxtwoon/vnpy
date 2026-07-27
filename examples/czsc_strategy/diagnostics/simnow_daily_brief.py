from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from declassify_historical_reports import build_banner
from simnow_artifact_loader import load_json_dict
from simnow_automation_policy import (
    automation_action_text,
    conclusion_text as _policy_conclusion_text,
    needs_user_action as _policy_needs_user_action,
    resolve_action_meta as _policy_resolve_action_meta,
)
from simnow_daily_brief_default_summary import (
    normalize_daily_brief_summary,
    resolve_failed_action_text,
)
from simnow_daily_brief_schema import (
    build_daily_brief_closing_lines,
    build_daily_brief_overview_lines,
    safe_get,
)
from simnow_daily_brief_sections import (
    build_account_contamination_section_lines,
    build_delayed_replay_section_lines,
    build_environment_capture_section_lines,
    build_historical_db_update_section_lines,
    build_risk_source_breakdown_section_lines,
    build_threshold_diagnostics_section_lines,
)
from simnow_ledger_summary_schema import build_daily_brief_20d_lines


HERE = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = HERE


def load_run_summary(path: Path) -> dict[str, Any]:
    """Load a run summary JSON if it exists; otherwise return an empty dict."""
    return load_json_dict(path)


_resolve_action_meta = _policy_resolve_action_meta
_conclusion_text = _policy_conclusion_text
needs_user_action = _policy_needs_user_action


def build_daily_brief(summary: dict[str, Any]) -> str:
    """Render a fixed-format Chinese daily brief from a run summary dict."""
    summary = normalize_daily_brief_summary(summary)
    status = safe_get(summary, "automation_status", default="failed")

    action = safe_get(summary, "automation_action", default="")
    date = safe_get(summary, "date", default="unknown")

    action_meta = _resolve_action_meta(summary)
    if status == "failed":
        action_text = resolve_failed_action_text(summary)
    else:
        action_text = automation_action_text(summary)
    record_action = action_meta
    conclusion = _conclusion_text(summary, action_text)

    lines = [
        f"# SimNow 每日观察日报 - {date}",
        "",
        build_banner().rstrip("\n"),
        "",
    ]
    lines.extend(
        build_daily_brief_overview_lines(
            summary=summary,
            action_meta=action_meta,
            record_action=record_action,
            needs_user_action=needs_user_action(summary),
        )
    )
    lines.append("")

    lines.extend(build_environment_capture_section_lines(summary))
    lines.extend(build_historical_db_update_section_lines(summary))
    lines.extend(build_account_contamination_section_lines(summary))
    lines.extend(build_delayed_replay_section_lines(summary))
    lines.extend(build_threshold_diagnostics_section_lines(summary))
    lines.extend(build_risk_source_breakdown_section_lines(summary))

    lines.extend([
        "## 20 日进度",
        "",
    ])
    lines.extend(build_daily_brief_20d_lines(summary.get("ledger_summary") or {}))
    lines.extend(build_daily_brief_closing_lines(action=action, conclusion=conclusion))
    return "\n".join(lines)


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
