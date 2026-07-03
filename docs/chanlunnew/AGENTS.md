# Repository Guidelines

## Project Structure & Module Organization

This repository is a research and audit workspace for a Chan-theory trading system. Top-level Markdown files and the PDF are reference materials. Most executable content lives under `codex_chan_audit_pack/`:

- `scripts/`: static, runtime, and PyPI verification utilities.
- `payload/chan_system_v1.0.2_extracted/`: audited Python source in `src/`, tests in `tests/`, and supporting documentation.
- `records/`: audit prompts, claims, and review records.
- `expected_outputs/`: generated verification reports and sample output.

Treat ZIP files in `payload/` as immutable source artifacts. Make code changes in the extracted tree and document any divergence from the archives.

## Build, Test, and Development Commands

Run commands from `codex_chan_audit_pack/`.

- `python scripts/verify_static_claims.py`: checks source-level audit claims without requiring `czsc`.
- `python scripts/verify_runtime_with_czsc.py`: runs bundled tests and runtime/API checks using the installed `czsc`.
- `python scripts/verify_runtime_with_czsc.py --install`: installs the pinned prerelease dependency before runtime checks; use only in an isolated environment.
- `bash scripts/run_all.sh`: runs static, runtime, and PyPI checks and refreshes `expected_outputs/`.
- `powershell -ExecutionPolicy Bypass -File scripts/update_czsc_latest.ps1`: creates a managed Python 3.12 environment and verifies `czsc==1.0.0rc8`.

There is no separate build step or package configuration.

## Coding Style & Naming Conventions

Use Python 3 with four-space indentation, UTF-8 encoding, `snake_case` functions and variables, `PascalCase` classes, and uppercase constants. Preserve existing Chinese domain terminology and ensure editors do not corrupt its encoding. Prefer `pathlib.Path`, type hints, structured JSON output, and small verification functions. No formatter or linter is configured, so keep changes PEP 8-compatible.

## Testing Guidelines

The bundled test is a standalone script, not a pytest suite:

```bash
cd payload/chan_system_v1.0.2_extracted/tests
python test_basic.py
```

Expected result: `7 passed, 0 failed`. Add invariant checks to `test_basic.py` and audit-specific assertions to the relevant `scripts/verify_*.py`. Review generated reports before committing them.

## Commit & Pull Request Guidelines

No Git history is included, so no existing commit convention can be inferred. Use short imperative subjects, such as `Add full whitelist validation`. Pull requests should describe the audited claim or behavior, list commands run and results, identify regenerated files, and call out dependency/version changes. Include screenshots only for visual documentation changes.
