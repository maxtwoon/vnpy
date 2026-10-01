# Kimi development assignment 01 — foundation and immutable store

You are the actual Kimi developer chosen by the user. Codex co-ordinates, OpenCode handles other paths, actual Claude Code audits/tests. Read IMPLEMENTATION_PLAN.md, PLAN_AUDIT.md, PLAN_AUDIT_DISPOSITION.md and .coordination/PREFLIGHT.md before coding. The coordinator only dispatches this after the first audit is incorporated. Personal local research: implement a usable minimal system, not placeholders or enterprise services.

Own WP00, WP01, WP02 in this turn: environment/package, models/schemas/catalog, immutable objects/revisions/conflicts/snapshots/reader/recover. First write INTERFACES.md giving real public call signatures, record schema, receipt/error types, insertion boundary for OpenCode's importers and consumers. Then implement those interfaces. Interface file is an early deliverable, not a replacement for working code.

Owned: pyproject.toml, .gitignore, research_store/__init__.py, models.py, schemas.py, catalog.py, objects.py, revisions.py, snapshots.py, reader.py, store.py (if useful), test files prefixed test_core_/test_catalog_/test_snapshot_/test_revision_, package .venv. Tests' common conftest may be created here, coordinate changes. Do NOT edit research_store/importers/,quality.py,coverage.py,cli.py,__main__.py,vnpy_researchstore/ or ../vnpy_datasource; OpenCode owns those. Do not overwrite plan/coordinator TASKS, audit or task files. Write developer handoff .coordination/kimi-core01-handoff.md. Journal/aggregation later task, unless core API prerequisites need typed stubs documented as pending (never counted complete).

Create .venv from D:/veighna_studio/python.exe --system-site-packages. Add duckdb,mypy/build as needed only there; existing Studio unchanged. Record installed dependencies and module origin. Ensure package works from repo root and other cwd with explicit configuration. Pure core import must not import vnpy/providerSDK or mutate default .vntrader.

Implement full meaningful tests for idempotency, same-key conflict handling, simultaneous partition publication CAS, injected interruption and recovery, exact immutable snapshot selection, snapshot quality binding, missing/tampered files, NULL preservation, time/field requirements. Do not merely mirror implementation or weaken invariants for green tests. Streaming, not full-history pandas materialization.

Use package's scoped typing, follow repo Ruff conventions. Run own focused tests/lint as development checks and record exact results. Claude will independently review. Never write raw roots or dataSource ledger/credentials, never update root HANDOFF or existing ETF research, no accounts/network data queries/git lifecycle. All source edits stay in owned scope.

Return actual implemented capabilities, remaining WP items, test results, interface details, exact changed paths. Do not claim all v0.1 complete at the end of this bounded assignment. Do not create fake readiness or suppress unknown metadata.
