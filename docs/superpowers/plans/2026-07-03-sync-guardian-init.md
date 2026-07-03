# sync-guardian Initialization Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Initialize the `sync-guardian` workflow in the `vnpy` repository with a root `HANDOFF.md`, a root `.synccheck.yml`, runnable `tools/` entry points, and repository guidance that matches the template contract.

**Architecture:** The workflow will use a single root handoff file as the source of truth for stage transitions, and a config-driven checker to validate version/doc/archive invariants. Thin `tools/` wrappers will expose the checker and handoff driver from the repository root so the workflow can be run locally without remembering template paths.

**Tech Stack:** Python 3.10+, YAML config, existing `vnpy` repository docs and version metadata.

## Global Constraints

- `vnpy` version source remains `vnpy/__init__.py::__version__` and `README.md` badge text must stay aligned with it.
- The checker must be config-driven from a root `.synccheck.yml`.
- `HANDOFF.md` is the only cross-agent state file.
- Root-level archive files matching the configured ignore patterns must not exist.
- The repository already targets Python 3.10+ and must keep the workflow portable on Windows, Linux, and macOS.

---

### Task 1: Add the root sync-guardian configuration files

**Files:**
- Create: `D:/repo/vnpy/HANDOFF.md`
- Create: `D:/repo/vnpy/.synccheck.yml`

**Interfaces:**
- Consumes: `vnpy/__init__.py::__version__`, `README.md`, `CHANGELOG.md`, `docs/index.rst`, `docs/community/index.rst`, `docs/elite/index.rst`
- Produces: root handoff metadata with `task`, `stage`, `owner`, `updated`, `deliverables`, and a config file the checker can read

- [ ] **Step 1: Write the failing test**

Run: `python D:/repo/ashare/skills/sync-guardian/scripts/sync_check.py --root D:/repo/vnpy`
Expected: fail because `HANDOFF.md` and `.synccheck.yml` do not exist yet.

- [ ] **Step 2: Create the minimal files**

```markdown
---
task: Initialize sync-guardian workflow
stage: design
owner: claude-code
updated: 2026-07-03
deliverables:
  - HANDOFF.md
  - .synccheck.yml
  - tools/sync_check.py
  - tools/handoff.py
blockers: []
---

## 背景与目标

Initialize the repository-level sync-guardian workflow so progress can be checked and advanced from the repository root.

## 验收标准

- `tools/sync_check.py` reads the root `.synccheck.yml` and validates the repository.
- `tools/handoff.py status` prints the current handoff stage, owner, and deliverables.
- The handoff file stays the single source of truth for multi-agent state.
```

```yaml
version_source: vnpy/__init__.py::__version__

must_match:
  - README.md
  - HANDOFF.md

changelog:
  file: CHANGELOG.md

doc_index: docs/index.rst

archive_dir: docs/archive/
archive_must_not_be_in_root:
  - docs/*_CODE_AGENT*.md
  - docs/*_DEPRECATED*.md

allow_history_notes: true

handoff:
  file: HANDOFF.md
  stages: [design, dev, review, done]
  owners:
    design: claude-code
    dev: kimi-code
    review: codex
  commands:
    design: claude -p "Read HANDOFF.md and AGENTS.md, finish the design stage, then run python tools/handoff.py next"
    dev: kimi -p "Read HANDOFF.md and AGENTS.md, finish the dev stage, then run python tools/handoff.py next"
    review: codex exec "Read HANDOFF.md and AGENTS.md, review against the handoff acceptance criteria, then run python tools/handoff.py next or python tools/handoff.py reject"
```

- [ ] **Step 3: Run the checker again**

Run: `python tools/sync_check.py`
Expected: fail only if repository references or version alignment are still missing.

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md .synccheck.yml
git commit -m "chore: initialize sync-guardian workflow"
```

### Task 2: Add root tool wrappers for the workflow

**Files:**
- Create: `D:/repo/vnpy/tools/sync_check.py`
- Create: `D:/repo/vnpy/tools/handoff.py`

**Interfaces:**
- Consumes: root `.synccheck.yml`, root `HANDOFF.md`
- Produces: CLI commands `python tools/sync_check.py` and `python tools/handoff.py status|next|reject|run`

- [ ] **Step 1: Write the failing test**

Run: `python tools/sync_check.py`
Expected: fail until the root wrapper exists.

- [ ] **Step 2: Implement the wrappers**

```python
from __future__ import annotations

from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(r"D:\repo\ashare\skills\sync-guardian\scripts")

sys.path.insert(0, str(SCRIPT_DIR))


if __name__ == "__main__":
    runpy.run_path(str(SCRIPT_DIR / "sync_check.py"), run_name="__main__")
```

```python
from __future__ import annotations

from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(r"D:\repo\ashare\skills\sync-guardian\scripts")

sys.path.insert(0, str(SCRIPT_DIR))


if __name__ == "__main__":
    runpy.run_path(str(SCRIPT_DIR / "handoff.py"), run_name="__main__")
```

- [ ] **Step 3: Run the wrappers**

Run:
`python tools/sync_check.py`
`python tools/handoff.py status`

Expected: the checker runs against the repository root and `status` prints handoff state.

- [ ] **Step 4: Commit**

```bash
git add tools/sync_check.py tools/handoff.py
git commit -m "chore: add sync-guardian tool wrappers"
```

### Task 3: Add repository guidance and discovery hooks

**Files:**
- Modify: `D:/repo/vnpy/AGENTS.md`
- Create: `D:/repo/vnpy/docs/superpowers/specs/2026-07-03-sync-guardian-init-design.md`

**Interfaces:**
- Consumes: root handoff workflow and checker contract
- Produces: repository-facing instructions that tell future agents how to use the workflow

- [ ] **Step 1: Write the failing test**

Review the current root `AGENTS.md` and confirm it does not mention `sync-guardian` yet.

- [ ] **Step 2: Add the guidance snippet**

```markdown
## sync-guardian workflow

Use `python tools/sync_check.py` to validate repository synchronization.
Use `python tools/handoff.py status` to inspect the current handoff state.
Use `python tools/handoff.py next --summary "..."` to advance the stage after finishing your assigned work.
Do not edit `HANDOFF.md` by hand for routine stage transitions; use the driver instead.
```

- [ ] **Step 3: Run a final validation**

Run:
`python tools/sync_check.py`
`python tools/handoff.py status`

Expected: both commands succeed from the repository root.

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md docs/superpowers/specs/2026-07-03-sync-guardian-init-design.md
git commit -m "docs: document sync-guardian workflow"
```
