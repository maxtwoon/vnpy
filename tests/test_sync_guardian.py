"""Tests for the vendored sync-guardian tooling.

These tests create temporary git repositories so they can exercise git-dependent
behaviour (deliverables-freshness and no_auto_advance) without mutating the
containing repository.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDOFF_PY = REPO_ROOT / "tools" / "handoff.py"
SYNC_CHECK_PY = REPO_ROOT / "tools" / "sync_check.py"


def _run(cmd: list[str] | str, cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a shell command in cwd, returning the completed process."""
    if isinstance(cmd, list):
        # For list commands, run directly without shell.
        return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=check)
    return subprocess.run(cmd, cwd=cwd, shell=True, text=True, capture_output=True, check=check)


def _git_init(repo: Path) -> None:
    """Initialize a git repository with a committed initial file."""
    _run(["git", "init"], repo, check=True)
    _run(["git", "config", "user.email", "test@example.com"], repo, check=True)
    _run(["git", "config", "user.name", "Test User"], repo, check=True)
    (repo / "README.md").write_text("# test repo\n", encoding="utf-8")
    _run(["git", "add", "README.md"], repo, check=True)
    _run(["git", "commit", "-m", "initial"], repo, check=True)


def _commit_all(repo: Path, message: str) -> None:
    _run(["git", "add", "-A"], repo, check=True)
    result = _run(["git", "commit", "-m", message], repo)
    if result.returncode != 0 and "nothing to commit" not in result.stdout:
        raise subprocess.CalledProcessError(
            result.returncode, result.args, output=result.stdout, stderr=result.stderr
        )


def _sync_check(repo: Path, args: str = "") -> subprocess.CompletedProcess[str]:
    cmd = f"{sys.executable} {SYNC_CHECK_PY}"
    if args:
        cmd += f" {args}"
    return _run(cmd, repo)


def _handoff(repo: Path, args: str = "") -> subprocess.CompletedProcess[str]:
    return _run(f"{sys.executable} {HANDOFF_PY} {args}", repo)


def _write_synccheck_yml(
    repo: Path,
    deliverables_policy: bool = True,
    commands: dict[str, str] | None = None,
    diagnostics_banner_check: dict[str, Any] | None = None,
    project_version_freshness: dict[str, Any] | None = None,
) -> None:
    policy_block = ""
    if deliverables_policy:
        policy_block = """
deliverables_policy:
  require_new_evidence_on_dev_to_review: true
"""
    commands_block = ""
    if commands:
        lines = ["  commands:"]
        for stage, cmd in commands.items():
            lines.append(f"    {stage}: {cmd}")
        commands_block = "\n" + "\n".join(lines) + "\n"
    banner_block = ""
    if diagnostics_banner_check:
        lines = ["diagnostics_banner_check:"]
        if "dir" in diagnostics_banner_check:
            lines.append(f"  dir: {diagnostics_banner_check['dir']}")
        if "dirs" in diagnostics_banner_check:
            lines.append("  dirs:")
            for d in diagnostics_banner_check["dirs"]:
                lines.append(f"    - {d}")
        lines.append(f"  banner: {diagnostics_banner_check['banner']!r}")
        if "skip" in diagnostics_banner_check:
            lines.append("  skip:")
            for s in diagnostics_banner_check["skip"]:
                lines.append(f"    - {s}")
        if "exempt_dirs" in diagnostics_banner_check:
            lines.append("  exempt_dirs:")
            for d in diagnostics_banner_check["exempt_dirs"]:
                lines.append(f"    - {d}")
        banner_block = "\n" + "\n".join(lines) + "\n"
    pvf_block = ""
    if project_version_freshness:
        lines = ["project_version_freshness:"]
        if "project_root" in project_version_freshness:
            lines.append(f"  project_root: {project_version_freshness['project_root']}")
        if "config_file" in project_version_freshness:
            lines.append(f"  config_file: {project_version_freshness['config_file']}")
        if "watch_variables" in project_version_freshness:
            lines.append("  watch_variables:")
            for v in project_version_freshness["watch_variables"]:
                lines.append(f"    - {v}")
        if "version_file" in project_version_freshness:
            lines.append(f"  version_file: {project_version_freshness['version_file']}")
        if "changelog_file" in project_version_freshness:
            lines.append(f"  changelog_file: {project_version_freshness['changelog_file']}")
        pvf_block = "\n" + "\n".join(lines) + "\n"
    content = f"""version_source: "VERSION::"
must_match: []
changelog:
  file: CHANGELOG.md
allow_history_notes: true
{policy_block}{banner_block}{pvf_block}handoff:
  file: HANDOFF.md
  stages: [design, dev, review, done]
  owners:
    design: designer
    dev: developer
    review: reviewer
  no_auto_advance: [review]{commands_block}"""
    (repo / ".synccheck.yml").write_text(content, encoding="utf-8")


def _write_handoff(
    repo: Path,
    stage: str,
    owner: str,
    deliverables: list[str] | None = None,
    transition: dict[str, str] | None = None,
) -> None:
    transition_lines = ""
    if transition:
        for key, value in transition.items():
            transition_lines += f"{key}: {value}\n"
    deliverable_lines = ""
    if deliverables:
        deliverable_lines = "deliverables:\n" + "".join(f"  - {d}\n" for d in deliverables)
    content = f"""---
task: test task
stage: {stage}
owner: {owner}
updated: 2026-07-12
{deliverable_lines}blockers: []
{transition_lines}---

## Background

Test.
"""
    (repo / "HANDOFF.md").write_text(content, encoding="utf-8")


def _write_version_and_changelog(repo: Path) -> None:
    (repo / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("# 0.1.0\n\nInitial.\n", encoding="utf-8")


@pytest.fixture
def fresh_repo(tmp_path: Path) -> Path:
    """A temporary git repository configured for sync-guardian tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    _write_version_and_changelog(repo)
    _write_synccheck_yml(repo)
    _commit_all(repo, "initial project files")
    return repo


def test_no_auto_advance_halt_run_loop_at_review(fresh_repo: Path) -> None:
    """At stage review, an agent command that exits 0 without transitioning must
    halt the run loop with a non-zero exit and leave the stage as review."""
    repo = fresh_repo
    # design -> dev -> review, with proper transition metadata at each step.
    _write_handoff(repo, "design", "designer", deliverables=["docs/design.md"])
    (repo / "docs").mkdir()
    (repo / "docs" / "design.md").write_text("design\n", encoding="utf-8")
    _commit_all(repo, "design handoff")

    _handoff(repo, "next --actor designer --summary design-done")
    _commit_all(repo, "dev handoff")

    # Use --no-gate so this test isolates the no_auto_advance run-loop behaviour
    # from the deliverables-freshness check (which has its own tests below).
    _handoff(repo, "next --actor developer --summary dev-done --no-gate")
    _commit_all(repo, "review handoff")

    text = (repo / "HANDOFF.md").read_text(encoding="utf-8")
    assert "stage: review" in text

    # Configure a review command that exits 0 without changing HANDOFF.md.
    _write_synccheck_yml(repo, deliverables_policy=False, commands={"review": 'python -c "exit(0)"'})
    _commit_all(repo, "add review command")

    result = _handoff(repo, "run --once")
    assert result.returncode != 0
    assert "no_auto_advance" in result.stderr or "no_auto_advance" in result.stdout
    final_text = (repo / "HANDOFF.md").read_text(encoding="utf-8")
    assert "stage: review" in final_text


def test_deliverables_freshness_fails_when_none_fresh_after_design_to_dev(
    fresh_repo: Path,
) -> None:
    """A review-stage handoff whose deliverables predate the design->dev transition
    must fail sync_check with the stale deliverable named."""
    repo = fresh_repo

    # Pre-existing deliverable committed during design.
    (repo / "docs").mkdir()
    (repo / "docs" / "design.md").write_text("design\n", encoding="utf-8")
    _write_handoff(
        repo,
        "design",
        "designer",
        deliverables=["docs/design.md"],
    )
    _commit_all(repo, "design: add deliverable")

    # design -> dev, touching only the HANDOFF file.
    _handoff(repo, "next --actor designer --summary design-done")
    _commit_all(repo, "design->dev transition")

    # dev -> review, still pointing at the old deliverable.
    _handoff(repo, "next --actor developer --summary dev-done --no-gate")
    _commit_all(repo, "dev->review transition")

    result = _sync_check(repo)
    assert result.returncode != 0
    assert "docs/design.md" in result.stderr


def test_deliverables_freshness_passes_when_one_fresh_after_design_to_dev(
    fresh_repo: Path,
) -> None:
    """A review-stage handoff passes when at least one deliverable was touched after
    the design->dev transition."""
    repo = fresh_repo

    # Pre-existing deliverable.
    (repo / "docs").mkdir()
    (repo / "docs" / "design.md").write_text("design\n", encoding="utf-8")
    _write_handoff(
        repo,
        "design",
        "designer",
        deliverables=["docs/design.md"],
    )
    _commit_all(repo, "design: add deliverable")

    # design -> dev.
    _handoff(repo, "next --actor designer --summary design-done")
    _commit_all(repo, "design->dev transition")

    # dev stage touches a new deliverable.
    (repo / "docs" / "report.md").write_text("report\n", encoding="utf-8")
    _write_handoff(
        repo,
        "dev",
        "developer",
        deliverables=["docs/design.md", "docs/report.md"],
    )
    _commit_all(repo, "dev: add report deliverable")

    # dev -> review.
    _handoff(repo, "next --actor developer --summary dev-done")
    _commit_all(repo, "dev->review transition")

    result = _sync_check(repo)
    assert result.returncode == 0, result.stderr


def test_gitignored_deliverable_fails_without_force_add(fresh_repo: Path) -> None:
    """A deliverable under a git-ignored directory that exists on disk but was never
    `git add -f`'d must fail the freshness check."""
    repo = fresh_repo

    # Ignore diagnostics/.
    (repo / ".gitignore").write_text("diagnostics/\n", encoding="utf-8")
    _commit_all(repo, "add gitignore")

    # Initial design deliverable.
    (repo / "docs").mkdir()
    (repo / "docs" / "design.md").write_text("design\n", encoding="utf-8")
    _write_handoff(repo, "design", "designer", deliverables=["docs/design.md"])
    _commit_all(repo, "design")

    # design -> dev.
    _handoff(repo, "next --actor designer --summary design-done")
    _commit_all(repo, "design->dev")

    # dev creates a deliverable inside the ignored directory but does NOT force-add it.
    (repo / "diagnostics").mkdir()
    (repo / "diagnostics" / "report.md").write_text("report\n", encoding="utf-8")
    _write_handoff(
        repo,
        "dev",
        "developer",
        deliverables=["docs/design.md", "diagnostics/report.md"],
    )
    _commit_all(repo, "dev: add ignored deliverable (not force-added)")

    # dev -> review.
    _handoff(repo, "next --actor developer --summary dev-done --no-gate")
    _commit_all(repo, "dev->review")

    result = _sync_check(repo)
    assert result.returncode != 0
    assert "diagnostics/report.md" in result.stderr


def test_gitignored_deliverable_passes_after_force_add(fresh_repo: Path) -> None:
    """The same git-ignored deliverable passes once it is `git add -f`'d into a
    dev-stage commit."""
    repo = fresh_repo

    (repo / ".gitignore").write_text("diagnostics/\n", encoding="utf-8")
    _commit_all(repo, "add gitignore")

    (repo / "docs").mkdir()
    (repo / "docs" / "design.md").write_text("design\n", encoding="utf-8")
    _write_handoff(repo, "design", "designer", deliverables=["docs/design.md"])
    _commit_all(repo, "design")

    _handoff(repo, "next --actor designer --summary design-done")
    _commit_all(repo, "design->dev")

    (repo / "diagnostics").mkdir()
    (repo / "diagnostics" / "report.md").write_text("report\n", encoding="utf-8")
    _write_handoff(
        repo,
        "dev",
        "developer",
        deliverables=["docs/design.md", "diagnostics/report.md"],
    )
    _run(["git", "add", "-f", "diagnostics/report.md"], repo, check=True)
    _run(["git", "add", "HANDOFF.md"], repo, check=True)
    _run(["git", "commit", "-m", "dev: force-add ignored deliverable"], repo, check=True)

    _handoff(repo, "next --actor developer --summary dev-done")
    _commit_all(repo, "dev->review")

    result = _sync_check(repo)
    assert result.returncode == 0, result.stderr


def test_wrappers_use_internal_script_dir(fresh_repo: Path) -> None:
    """The wrapper entry points must work when the external ashare path is not
    available (simulated by running in a fresh repo that lacks it)."""
    repo = fresh_repo
    _write_handoff(repo, "design", "designer")
    _commit_all(repo, "design")

    result = _handoff(repo, "status")
    assert result.returncode == 0, result.stderr
    assert "design" in result.stdout

    result = _sync_check(repo)
    assert result.returncode == 0, result.stderr


def test_diagnostics_banner_check_fails_without_banner(fresh_repo: Path) -> None:
    """A diagnostics/*.md file lacking the RESEARCH-ONLY banner must fail
    sync_check with the file named in the error."""
    repo = fresh_repo
    _write_synccheck_yml(
        repo,
        deliverables_policy=False,
        diagnostics_banner_check={
            "dir": "diagnostics",
            "banner": "<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->",
        },
    )
    _write_handoff(repo, "design", "designer")
    (repo / "diagnostics").mkdir()
    bad_report = repo / "diagnostics" / "new_report.md"
    bad_report.write_text("# New report\n\nSome findings.\n", encoding="utf-8")
    _commit_all(repo, "add banner check config and new report")

    result = _sync_check(repo)
    assert result.returncode != 0, result.stdout
    assert "diagnostics/new_report.md" in result.stderr
    assert "RESEARCH-ONLY banner" in result.stderr


def test_diagnostics_banner_check_passes_with_banner(fresh_repo: Path) -> None:
    """The same file passes once the banner is added."""
    repo = fresh_repo
    _write_synccheck_yml(
        repo,
        deliverables_policy=False,
        diagnostics_banner_check={
            "dir": "diagnostics",
            "banner": "<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->",
        },
    )
    _write_handoff(repo, "design", "designer")
    (repo / "diagnostics").mkdir()
    report = repo / "diagnostics" / "new_report.md"
    report.write_text(
        "# New report\n\n<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->\n\nSome findings.\n",
        encoding="utf-8",
    )
    _commit_all(repo, "add banner check config and bannered report")

    result = _sync_check(repo)
    assert result.returncode == 0, result.stderr


def test_diagnostics_banner_skip_pattern_honors_config(fresh_repo: Path) -> None:
    """The audit_issue_diagnostics_* prefix exemption must be config-driven, not hardcoded."""
    repo = fresh_repo
    _write_synccheck_yml(
        repo,
        deliverables_policy=False,
        diagnostics_banner_check={
            "dir": "diagnostics",
            "banner": "<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->",
            "skip": ["audit_issue_diagnostics_*.md"],
        },
    )
    _write_handoff(repo, "design", "designer")
    (repo / "diagnostics").mkdir()
    audit = repo / "diagnostics" / "audit_issue_diagnostics_2026-07-14.md"
    audit.write_text("# Audit\n\nNo banner here.\n", encoding="utf-8")
    _commit_all(repo, "add config and unbannered audit file")

    result = _sync_check(repo)
    assert result.returncode == 0, result.stderr


def test_diagnostics_banner_archive_exempt_honors_config(fresh_repo: Path) -> None:
    """Files under diagnostics/archive/ must be skippable via exempt_dirs config.

    The same unbannered archived file should fail when exempt_dirs is absent or
    changed, and pass when diagnostics/archive is configured. This proves the
    exemption is the active reason the file is skipped, not a glob accident.
    """
    repo = fresh_repo
    _write_synccheck_yml(
        repo,
        deliverables_policy=False,
        diagnostics_banner_check={
            "dir": "diagnostics",
            "banner": "<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->",
            "exempt_dirs": ["diagnostics/archive"],
        },
    )
    _write_handoff(repo, "design", "designer")
    (repo / "diagnostics" / "archive").mkdir(parents=True)
    archived = repo / "diagnostics" / "archive" / "HANDOFF-A32-archived-2026-07-11.md"
    archived.write_text("# Archived\n\nNo banner.\n", encoding="utf-8")
    _commit_all(repo, "add config and archived file")

    result = _sync_check(repo)
    assert result.returncode == 0, result.stderr

    # Remove the exemption; the archived file is now scanned and must fail.
    _write_synccheck_yml(
        repo,
        deliverables_policy=False,
        diagnostics_banner_check={
            "dir": "diagnostics",
            "banner": "<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->",
        },
    )
    _commit_all(repo, "remove archive exemption")

    result = _sync_check(repo)
    assert result.returncode != 0
    assert "HANDOFF-A32-archived-2026-07-11.md" in result.stderr


def _setup_project_version_freshness_repo(repo: Path) -> None:
    """Configure a fresh repo with the A60 project_version_freshness gate."""
    _write_synccheck_yml(
        repo,
        deliverables_policy=False,
        project_version_freshness={
            "project_root": ".",
            "config_file": "config.py",
            "watch_variables": ["STRATEGY_CONFIG", "BACKTEST_CONFIG"],
            "version_file": "VERSION",
            "changelog_file": "CHANGELOG.md",
        },
    )
    (repo / "config.py").write_text(
        'STRATEGY_CONFIG = {"a": 1}\nBACKTEST_CONFIG = {"start": "2023-01-01"}\n',
        encoding="utf-8",
    )
    (repo / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("# 0.1.0\n\nInitial.\n", encoding="utf-8")
    _write_handoff(repo, "design", "designer")
    _commit_all(repo, "add project version freshness config")


def test_project_version_freshness_fails_when_config_changes_without_version_or_changelog(
    fresh_repo: Path,
) -> None:
    """A commit that changes watched config keys without touching VERSION or CHANGELOG fails."""
    repo = fresh_repo
    _setup_project_version_freshness_repo(repo)

    # Bad commit: change a top-level config key but leave VERSION/CHANGELOG alone.
    (repo / "config.py").write_text(
        'STRATEGY_CONFIG = {"a": 2}\nBACKTEST_CONFIG = {"start": "2023-01-01"}\n',
        encoding="utf-8",
    )
    _commit_all(repo, "change config key without versioning")

    result = _sync_check(repo)
    assert result.returncode != 0
    assert "STRATEGY_CONFIG" in result.stderr
    assert "VERSION" in result.stderr
    assert "CHANGELOG.md" in result.stderr


def test_project_version_freshness_passes_when_version_or_changelog_touched(
    fresh_repo: Path,
) -> None:
    """The same config change passes when VERSION or CHANGELOG is touched in the same commit."""
    repo = fresh_repo
    _setup_project_version_freshness_repo(repo)

    (repo / "config.py").write_text(
        'STRATEGY_CONFIG = {"a": 2}\nBACKTEST_CONFIG = {"start": "2023-01-01"}\n',
        encoding="utf-8",
    )
    (repo / "VERSION").write_text("0.2.0\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("# 0.2.0\n\nChanged a.\n", encoding="utf-8")
    _commit_all(repo, "change config key and bump version")

    result = _sync_check(repo)
    assert result.returncode == 0, result.stderr


def test_project_version_freshness_handles_non_ascii_config_content(fresh_repo: Path) -> None:
    """A config.py with non-ASCII (e.g. Chinese) comments/strings must not crash the gate.

    Regression test for a real bug found during A67's review: on Windows,
    subprocess's default text-mode decoding uses the system locale (often
    GBK/cp936), which raised UnicodeDecodeError on any UTF-8 source file
    containing non-ASCII bytes -- silently swallowed into a false "could not
    read" gate failure. The fix pins encoding="utf-8" on the git subprocess
    calls that read file content.
    """
    repo = fresh_repo
    _write_synccheck_yml(
        repo,
        deliverables_policy=False,
        project_version_freshness={
            "project_root": ".",
            "config_file": "config.py",
            "watch_variables": ["STRATEGY_CONFIG", "BACKTEST_CONFIG"],
            "version_file": "VERSION",
            "changelog_file": "CHANGELOG.md",
        },
    )
    (repo / "config.py").write_text(
        '"""缠论择时策略配置"""\nSTRATEGY_CONFIG = {"a": 1}  # 一买仓位\nBACKTEST_CONFIG = {"start": "2023-01-01"}\n',
        encoding="utf-8",
    )
    (repo / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("# 0.1.0\n\n初始版本。\n", encoding="utf-8")
    _write_handoff(repo, "design", "designer")
    _commit_all(repo, "add project version freshness config with Chinese comments")

    (repo / "config.py").write_text(
        '"""缠论择时策略配置"""\nSTRATEGY_CONFIG = {"a": 2}  # 一买仓位调整\nBACKTEST_CONFIG = {"start": "2023-01-01"}\n',
        encoding="utf-8",
    )
    _commit_all(repo, "change config key without versioning, non-ascii file")

    result = _sync_check(repo)
    assert result.returncode != 0
    assert "could not read" not in result.stderr
    assert "STRATEGY_CONFIG" in result.stderr


def test_project_version_freshness_handles_arithmetic_expressions_in_config(
    fresh_repo: Path,
) -> None:
    """A config.py dict value written as a simple arithmetic expression (e.g. ``3600 * 24``)
    must not crash the gate's AST-based fingerprinting.

    Regression test for a real bug found during A67's review: the fingerprint
    parser used ``ast.literal_eval`` directly, which rejects any non-literal
    expression node (including basic numeric arithmetic that real config files
    commonly use for readability, e.g. "one day in seconds").
    """
    repo = fresh_repo
    _write_synccheck_yml(
        repo,
        deliverables_policy=False,
        project_version_freshness={
            "project_root": ".",
            "config_file": "config.py",
            "watch_variables": ["STRATEGY_CONFIG", "BACKTEST_CONFIG"],
            "version_file": "VERSION",
            "changelog_file": "CHANGELOG.md",
        },
    )
    (repo / "config.py").write_text(
        'STRATEGY_CONFIG = {"interval": 3600 * 24, "a": 1}\nBACKTEST_CONFIG = {"start": "2023-01-01"}\n',
        encoding="utf-8",
    )
    (repo / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("# 0.1.0\n\nInitial.\n", encoding="utf-8")
    _write_handoff(repo, "design", "designer")
    _commit_all(repo, "add project version freshness config with arithmetic expr")

    (repo / "config.py").write_text(
        'STRATEGY_CONFIG = {"interval": 3600 * 24, "a": 2}\nBACKTEST_CONFIG = {"start": "2023-01-01"}\n',
        encoding="utf-8",
    )
    _commit_all(repo, "change config key without versioning, arithmetic expr file")

    result = _sync_check(repo)
    assert result.returncode != 0
    assert "parse error" not in result.stderr
    assert "STRATEGY_CONFIG" in result.stderr
