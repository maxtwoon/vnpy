# sync-guardian Initialization Design

## Goal

Initialize the repository-level `sync-guardian` workflow so agents can read one handoff file, run one checker, and advance stages from the repository root.

## Scope

- Root `HANDOFF.md` as the single source of truth
- Root `.synccheck.yml` as the config-driven validation contract
- Root `tools/` entry points that execute the workflow from `D:\repo\vnpy`
- Repository guidance in `AGENTS.md`

## Decisions

- Keep the workflow minimal and repository-local.
- Delegate to the installed `sync-guardian` scripts so the repo gets working entry points without reimplementing the whole engine.
- Use `vnpy/__init__.py::__version__` as the version source and keep `README.md` and `HANDOFF.md` aligned with it.

## Acceptance

- `python tools/sync_check.py` exits successfully from the repo root.
- `python tools/handoff.py status` prints the current stage.
- `python tools/handoff.py next --summary "..."` advances the workflow when the gate passes.
- `AGENTS.md` tells future agents how to use the workflow.
