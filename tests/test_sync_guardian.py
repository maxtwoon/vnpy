"""Tests for the vendored sync-guardian tooling.

These tests create temporary git repositories so they can exercise git-dependent
behaviour (deliverables-freshness and no_auto_advance) without mutating the
containing repository.
"""
from __future__ import annotations

import os
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
    repo: Path, deliverables_policy: bool = True, commands: dict[str, str] | None = None
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
    content = f"""version_source: "VERSION::"
must_match: []
changelog:
  file: CHANGELOG.md
allow_history_notes: true
{policy_block}
handoff:
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
