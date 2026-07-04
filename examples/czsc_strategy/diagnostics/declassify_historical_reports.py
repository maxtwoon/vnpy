"""Declassify historical final-candidate reports in the diagnostics folder.

The audit remediation (A34 Phase 2) requires that every historical report that
still shows ``GOAL PASSED`` or a ``0.847`` pass row is explicitly marked as
research-only / not promotion evidence.  This script is idempotent: reports
already carrying the declassification marker are skipped.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

HISTORICAL_DATA_WINDOW: str = "2022-01-01~2026-04-24"
DECISION_DATA_WINDOWS: list[str] = ["2026-04-24~present", "SimNow observation"]

DECLASSIFY_MARKER: str = "<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->"

# Reports that are logs, acceptance specs, or audit diagnostics rather than
# historical final-candidate / parameter-scan reports.
SKIP_NAMES: set[str] = {
    "WORK_LOG.md",
    "ACCEPTANCE.md",
    "AUTOMATION_PROMPT.md",
    "NEXT_WORK.md",
    "simnow_daily_observation_workflow.md",
    "simnow_connection_probe.md",
}

BANNER_TEMPLATE: str = (
    "{marker}\n\n"
    "> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**\n>\n"
    "> This report was produced using the historical out-of-sample window "
    "`{historical_window}`, which was repeatedly used for parameter selection. "
    "High-precision weights such as `0.847` and any bare `GOAL PASSED` rows are "
    "gate-fitting signatures, not evidence of a robust trading discovery. "
    "This artifact is retained as negative / contaminated evidence only.\n>\n"
    "> - `is_promotion_evidence`: False\n"
    "> - `research_only`: True\n"
    "> - `used_data_windows`: `[\"{historical_window}\"]`\n"
    "> - `decision_data_windows`: {decision_windows_repr}\n"
    "> - `note`: Future validation must use post-2026-04-24 incremental data "
    "and SimNow observation before any promotion claim can be considered.\n\n"
)

GOAL_PASSED_RE: re.Pattern[str] = re.compile(
    r"^\*\*GOAL PASSED:\s*`([^`]+)`\*\*$"
)


def build_banner() -> str:
    return BANNER_TEMPLATE.format(
        marker=DECLASSIFY_MARKER,
        historical_window=HISTORICAL_DATA_WINDOW,
        decision_windows_repr=repr(DECISION_DATA_WINDOWS),
    )


def is_candidate_report(path: Path) -> bool:
    """Return True for .md files that contain old-OOS pass markers."""
    if path.name in SKIP_NAMES:
        return False
    if path.name.startswith("audit_issue_diagnostics_"):
        return False
    text = path.read_text(encoding="utf-8")
    return "0.847" in text or "GOAL PASSED" in text


def find_candidate_reports(directory: Path) -> list[Path]:
    return [p for p in sorted(directory.glob("*.md")) if is_candidate_report(p)]


def sanitize_goal_passed_lines(path: Path) -> bool:
    """Rewrite bare ``**GOAL PASSED: `X`**`` lines so they cannot be read as
    active promotion claims.

    Returns True if any line was changed.
    """
    text = path.read_text(encoding="utf-8")
    new_lines: list[str] = []
    changed = False
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n\r")
        match = GOAL_PASSED_RE.match(stripped)
        if match:
            value = match.group(1)
            new_line = (
                f"**HISTORICAL GATE RESULT: `{value}` "
                f"(DECLASSIFIED; NOT PROMOTION EVIDENCE)**\n"
            )
            new_lines.append(new_line)
            changed = True
        else:
            new_lines.append(line)
    if changed:
        path.write_text("".join(new_lines), encoding="utf-8")
    return changed


def needs_declassification(path: Path, marker: str | None = None) -> bool:
    """Return True if the report lacks the marker or still has a bare
    ``GOAL PASSED`` line.
    """
    marker = marker or DECLASSIFY_MARKER
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        return True
    return any(
        GOAL_PASSED_RE.match(line.rstrip("\n\r"))
        for line in text.splitlines()
    )


def declassify_file(path: Path, marker: str | None = None, banner: str | None = None) -> bool:
    """Prepend the declassification banner after the first H1 heading and
    sanitize any bare ``GOAL PASSED`` lines.

    Returns True if the file was changed, False if the marker was already
    present and no sanitization was needed.
    """
    marker = marker or DECLASSIFY_MARKER
    banner = banner or build_banner()

    changed = False
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        lines = text.splitlines(keepends=True)
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("# "):
                insert_idx = i + 1
                break

        new_lines = lines[:insert_idx] + ["\n", banner] + lines[insert_idx:]
        path.write_text("".join(new_lines), encoding="utf-8")
        changed = True

    if sanitize_goal_passed_lines(path):
        changed = True

    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mark historical final-candidate reports as research-only."
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory containing Markdown reports to declassify",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the files that would be changed without modifying them",
    )
    args = parser.parse_args(argv)

    banner = build_banner()
    changed = 0
    already_marked = 0

    for path in find_candidate_reports(args.dir):
        if args.dry_run:
            if needs_declassification(path):
                print(f"would declassify/sanitize: {path.name}")
                changed += 1
            else:
                print(f"already marked: {path.name}")
                already_marked += 1
            continue

        if declassify_file(path, banner=banner):
            print(f"declassified/sanitized: {path.name}")
            changed += 1
        else:
            already_marked += 1

    print(f"changed={changed} already_marked={already_marked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
