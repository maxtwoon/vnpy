# OpenCode development assignment 01 — inventory/readers/import adapters

You are actual OpenCode developer requested by user. Codex co-ordinates, Kimi implements core, actual Claude Code audits/tests. Read IMPLEMENTATION_PLAN.md, PLAN_AUDIT.md, PLAN_AUDIT_DISPOSITION.md, .coordination/PREFLIGHT.md. Personal local research, minimal useful implementation, full agreed capability scope.

Own WP03/WP04/WP06 import side: source metadata inventory, safe streaming readers, securities/repair indexes, normalization, quality/coverage, RQ ETF first, SSQuant/JQ/RQ futures adapters. Begin with reader/inventory work while Kimi produces INTERFACES.md. Read that contract once present before integrating; do not invent or edit Kimi's core API. If a core API is missing, record exact request in .coordination/opencode-core-requests.md and continue independent importer work.

Owned paths: research_store/importers/**, research_store/quality.py,coverage.py, tests/test_import_*.py,test_quality*.py,test_coverage*.py and importer configs. Do NOT edit pyproject/models/schemas/catalog/objects/revisions/snapshots/reader/store/common conftest, vnpy_researchstore adapters, or datasource yet. Kimi owns common package/env and core. No coordination plan/audit/TASKS overwrite. Write .coordination/opencode-import01-handoff.md.

Read-only input roots exactly those in plan. Safe tar member validation; no extractall, pickle or source scripts. Chunk CSV100k; one member at a time; Parquet rowgroups via bounded staging. Source SQLite consistent backup via read-only connection into store captures, quick_check+hash, no direct raw mutation/copy ignoring WAL. Preserve hash/member/table/range/config provenance.

Important factual rules: normalize RQ ETF END label; import repairs BEFORE base archive;133 repaired rows already inside2016/17/18 base,118 refetch conflicts. Unknown JQ adjustment despite factor1. SSQuant openint is not totalOI, MA amount untrusted; preserve raw values, don't guess multipliers. SimNow staging isolated and precise8 main keys; don't misclassify all metadata overlap. source 888/777 separate from real contracts, unknown roll rules explicit. Zhengzhou3digit codes require unique universe/date match. .INDX namespace preserved. Coverage expected unknown without calendar/session/suspension evidence. Gaps/NULL never filled. RQ futures preserves trading_date/dominant_id/member-derived identity.

Full inventory includes all other categories catalog-only and stated missing overlays/shares fallback/version conflicts/PIT limitations, not fabricated PASS. Formal streaming full market imports can be executed incrementally after smoke and core readiness; this assignment must build the actual functionality, not hard-coded sample-only readers.

Run focused development tests and lint using Kimi-provisioned .venv (Studio sufficient early reader checks if venv pending). Record actual evidence and remaining work. No network downloads/account connections/git commit/push/root HANDOFF/unrelated edits. Raw real samples may be read into temporary or D:/quant-data output, never commit bulk purchased data as fixtures.

Return concrete changed files, working importer APIs, sample/coverage facts, tests, and blockers needing exact core interface resolution.
