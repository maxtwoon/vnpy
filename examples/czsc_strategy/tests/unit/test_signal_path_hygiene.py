"""Signal-path import-hygiene guard.

A75: statically detect direct, unrenamed imports of the deprecated
``chan_strategy.signals.get_all_signals`` entry in production/execution-path
files. The authoritative implementation lives in ``chan_strategy.sell_signals``;
``chan_strategy.signals.get_all_signals`` is kept only as a DeprecationWarning-
emitting compatibility wrapper.

Scope (all under ``examples/czsc_strategy``):
  - ``chan_strategy/`` (except ``chan_strategy/signals.py`` itself)
  - ``diagnostics/``
  - ``skill_build/``
  - ``run_chan_backtest.py``

Test files are excluded because legacy-implementation tests deliberately import
``get_legacy_signals``.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


BASE_DIR: Path = Path(__file__).resolve().parents[2]

# Production / execution paths to scan for hygiene violations.
SCANNED_PATHS: list[Path] = [
    BASE_DIR / "chan_strategy",
    BASE_DIR / "diagnostics",
    BASE_DIR / "skill_build",
    BASE_DIR / "run_chan_backtest.py",
]

# Files that define or explicitly maintain the legacy entry are not violations.
EXCLUDED_FILES: set[Path] = {
    BASE_DIR / "chan_strategy" / "signals.py",
}

BANNED_MODULE: str = "chan_strategy.signals"
BANNED_NAME: str = "get_all_signals"


def _is_banned_import(node: ast.AST) -> bool:
    """Return True if *node* is ``from chan_strategy.signals import get_all_signals``."""
    if not isinstance(node, ast.ImportFrom):
        return False
    if node.module != BANNED_MODULE:
        return False
    return any(alias.name == BANNED_NAME for alias in node.names)


def find_violations(source: str, filename: str = "<str>") -> list[tuple[int, str]]:
    """Return (line_number, line_text) tuples for banned imports in *source*."""
    tree = ast.parse(source, filename=filename)
    lines = source.splitlines()
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if _is_banned_import(node):
            lineno = node.lineno or 1
            line_text = lines[lineno - 1] if lineno <= len(lines) else ""
            violations.append((lineno, line_text.strip()))
    return violations


def scan_paths(paths: list[Path]) -> list[tuple[Path, int, str]]:
    """Scan *paths* for banned imports, honouring exclusions."""
    violations: list[tuple[Path, int, str]] = []
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            files = [path]
        elif path.is_dir():
            files = sorted(path.rglob("*.py"))
        else:
            continue

        for file_path in files:
            if file_path in EXCLUDED_FILES:
                continue
            rel_parts = file_path.relative_to(BASE_DIR).parts
            if "tests" in rel_parts:
                continue
            source = file_path.read_text(encoding="utf-8")
            for lineno, line_text in find_violations(source, filename=str(file_path)):
                violations.append((file_path, lineno, line_text))
    return violations


# ---------------------------------------------------------------------------
# Self-test: prove the detector actually catches the banned pattern.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "source,expected_count",
    [
        ("from chan_strategy.sell_signals import get_all_signals\n", 0),
        (
            "from chan_strategy.signals import get_legacy_signals as get_all_signals\n",
            0,
        ),
        ("from chan_strategy.signals import get_legacy_signals\n", 0),
        ("import chan_strategy.signals\n", 0),
        ("from chan_strategy.signals import get_all_signals\n", 1),
        (
            "from chan_strategy.signals import get_all_signals as old_get_all_signals\n",
            1,
        ),
        (
            "from chan_strategy.signals import (\n    get_all_signals,\n)\n",
            1,
        ),
        (
            "from chan_strategy.signals import get_legacy_signals, get_all_signals\n",
            1,
        ),
    ],
)
def test_detector_flags_only_direct_unrenamed_legacy_import(
    source: str, expected_count: int
) -> None:
    """The guard must flag only imports that take the deprecated name directly."""
    found = find_violations(source)
    assert len(found) == expected_count


def test_no_direct_unrenamed_legacy_import_in_production_paths() -> None:
    """Current codebase must be clean of the banned import pattern."""
    violations = scan_paths(SCANNED_PATHS)
    assert not violations, _format_violations(violations)


def _format_violations(violations: list[tuple[Path, int, str]]) -> str:
    lines = [f"{len(violations)} direct legacy import(s) found:"]
    for file_path, lineno, line_text in violations:
        lines.append(f"  {file_path}:{lineno}: {line_text}")
    lines.append(
        "Use 'from chan_strategy.sell_signals import get_all_signals' "
        "or, for legacy-only code, 'from chan_strategy.signals import "
        "get_legacy_signals as get_all_signals'."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Manual verification (natively run):
#   python -m pytest examples/czsc_strategy/tests/unit/test_signal_path_hygiene.py -v
#
# Expected result on a clean tree:
#   9 passed
#   scanned files: 109 .py files under chan_strategy/ (minus signals.py),
#   diagnostics/, skill_build/, and run_chan_backtest.py
#   violations found: 0
# ---------------------------------------------------------------------------
