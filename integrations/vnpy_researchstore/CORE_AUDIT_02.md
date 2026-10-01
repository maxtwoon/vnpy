# Claude Code Core Audit 02 — Result

## Environment

```
cd D:/repo/vnpy/integrations/vnpy_researchstore
./.venv/Scripts/python.exe -c "import sys; print(sys.executable); print(sys.version)"
→ D:\repo\vnpy\integrations\vnpy_researchstore\.venv\Scripts\python.exe  (3.13.8)
./.venv/Scripts/python.exe -c "import research_store; print(research_store.__file__)"
→ D:\repo\vnpy\integrations\vnpy_researchstore\research_store\__init__.py
./.venv/Scripts/python.exe -c "import zstandard; print(zstandard.__version__, zstandard.__file__)"
→ 0.25.0  ...\.venv\Lib\site-packages\zstandard\__init__.py   (genuinely package-local, not Studio site-packages)
./.venv/Scripts/python.exe -c "import duckdb; print(duckdb.__version__)" → 1.5.5
```
No vnpy import needed for core (pure-core), so no `vnpy.__file__` applies to this milestone.

```
cd D:/repo/vnpy && integrations/vnpy_researchstore/.venv/Scripts/python.exe -m pytest integrations/vnpy_researchstore/tests -q
→ 180 passed, 1 failed, 1 warning (30.5s)
   FAILED tests/test_dominant_overlay.py::test_overlay_import_conflicts_not_last_wins
./.venv/Scripts/python.exe -m mypy research_store/{models,schemas,catalog,objects,revisions,snapshots,reader,store,__init__}.py
→ Success: no issues found in 9 source files
D:/veighna_studio/python.exe -m ruff check research_store/{models,schemas,catalog,objects,revisions,snapshots,reader,store}.py
→ All checks passed!
```
Plus one temporary reproduction (kept at `.coordination/review-core02/repro_multipartition.py`, not part of the suite) for the multi-partition interruption scenario, run with the same `.venv` interpreter.

## Findings (highest-impact, ≤5)

**F1 — HIGH — `ConflictRecord` never exposes `gap_ns`, so the documented resolve→quarantine→`allow_known_gaps` workflow is not usable from the public API alone.**
`research_store/models.py:267-278` (`ConflictRecord` fields: `key`, `existing_evidence`, `candidate_evidence` — no bounds). `research_store/revisions.py:346-358` builds the `ConflictRecord` without `gap_ns`; the real bounds (`prior["bar_start"]`/`["bar_end"]`) only go into the internal sidecar evidence dict at `revisions.py:366-368`, later surfaced only inside `quality_issues.evidence_json` / snapshot `quality_decisions` (`snapshots.py:126`), never on the object the importer actually receives.
Trigger: reproduced live — `tests/test_dominant_overlay.py::test_overlay_import_conflicts_not_last_wins` currently **fails** in the full suite because it derives the gap from `conflict.key.rsplit("@",1)[1]` (assuming a 1ns point), while the reader's real quarantined interval is the full 60s bar width (`reader.py:111-129`, `_check_gaps`). Core's own tests (`test_core_time_contract.py:166`) only avoid this because the test author independently knows the original `bar_start`/`bar_end` used to build the fixture — a real caller only has `ConflictRecord`.
Minimum fix: add `gap_ns: tuple[int,int] | None` to `ConflictRecord`, populated from the same evidence already computed in `_build_partition`.

**F2 — MEDIUM — `recover(store)` (no `batch_id`) silently skips `FAILED` batches, so a genuinely interrupted multi-partition batch (one partition committed, a later one didn't) is invisible to the one general-sweep recovery API the plan names.**
`research_store/revisions.py:942-946`: `SELECT ... FROM batches WHERE state IN ('prepared','published','running')` excludes `'failed'`. Reproduced with `.coordination/review-core02/repro_multipartition.py`: a 2-partition batch where partition `2024`'s CAS commits and partition `2025`'s raises — result: `batch state=failed`, `head(2024)` durably published, `head(2025)=None`, and `recover(store)` examines **zero** batches (confirmed empty). Data integrity holds (no false "published" claim; a same-idempotency-key retry does correctly finish it — verified), but the documented crash-recovery sweep gives no visibility or remediation for this class of interruption.
Minimum fix: either fold `'failed'` batches with a durable anchor into `recover()`'s sweep (resume via the same path `_recover_prepared` already uses), or explicitly document that callers must retry by `idempotency_key` and `recover()` is scoped to `prepared`/`running` only.

**F3 — HIGH — Tick identity/dedup key has no session/sequence component, contradicting the disposed time contract and the plan's explicitly required "tick same-time/replay" test, which does not exist anywhere in the suite.**
`research_store/schemas.py:59-84` (`TICKS_SCHEMA_V1`: `ts` int64 only, no `seq`/session column). `research_store/revisions.py:218-219` (`_row_key` ticks branch: `(identity, ts)` only). `TIME_CONTRACT_DISPOSITION.md` item 2 states "ticks retain session+sequence"; `IMPLEMENTATION_PLAN.md`'s required-tests list names "tick same-time/replay" by name. `grep` across `tests/` for same-timestamp tick coverage returns nothing.
Trigger: two genuinely distinct ticks for the same instrument at the identical `ts` (routine in real tick streams) collide on one key — if values differ this raises a spurious `ConflictRecord`/quarantine (losing real market data instead of preserving two disambiguated events); if they happen to match it silently drops a real second event as a "duplicate."
Minimum fix: add a `seq`/session disambiguator column to `TICKS_SCHEMA_V1`, include it in the tick `_row_key`, and add the plan-required same-time/replay test.

**Not a defect (explicitly checked per task instruction):** `opencode-import01-core-loop.log`'s printed `"manifest_revisions": []` — there is no field named `manifest_revisions` anywhere in `SnapshotRef` or in the real snapshot manifest JSON (`snapshots.py:130-145` — the real key is `selections`, each with a populated `revision_id`/`files`/`rows`). This is OpenCode's own diagnostic script reading a nonexistent field, not evidence the core snapshot is empty or unusable — confirmed functional via the passing `test_snapshot_freeze`/`test_core_time_contract` suites and my own repro's successful `freeze()`/read.

## Itemized core acceptance

**Proven (real assertions read, not just green counts):**
- Pure-core import, zero vnpy modules, package-local zstandard/duckdb.
- Minute `trading_date=NULL` roundtrip with quality flag; rejected without flag.
- Daily identity = (instrument-or-series, trading_date): dedup across differing labels, real-value conflict keyed by date (not label), NULL rejected at publish, series-only daily rows accepted.
- Concurrent same-partition CAS: real two-thread barrier test, exactly one winner, clean loser retry.
- Crash-after-prepared-anchor recovery; tampered/missing published object fails loudly; orphans reported not deleted.
- Old snapshot independence after later conflict resolution.
- Exact manifest file selection (no globbing), per-file sha256 verify, tamper/missing → `IntegrityError`.
- OHLCV real-NULL persistence (never zero-filled); required-field NULL → `MissingFieldDataError`; unknown field → `UnavailableFieldError`; naive datetime rejected.
- Genuine streaming reads (`DuckDB.to_arrow_reader(65536)`, no whole-table materialization).
- Windows fsync durability fix present and correct (O_RDWR handle on `nt`, directory-fsync skipped on `nt`, errors propagate).
- mypy strict / ruff clean on the 9 core-owned files (re-verified today).

**Incomplete / defective:** F1 (conflict gap_ns not exposed — currently causing a real full-suite test failure), F2 (recover() blind to failed multi-partition batches), F3 (tick session/sequence identity unimplemented, plan-required test missing).

**Out of scope for this verdict (not counted as core defects):** importers/quality/coverage/native/consumer modules generally; SSQuant label-profile work (OpenCode, not reviewed as final); recorder/journal/`recover_session`/`seal` (WP08/WP09 PENDING stubs by design); live-gateway paths (NOT_RUN, no credentials/network used).

## Verdict: **FAIL (CORE only)**

Reasoning: two of the three findings are genuine gaps in core's own public contract (F1 breaks a documented, tested-as-required workflow — demonstrated by an actual failing test in the current tree, not a hypothetical; F3 is an explicit, plan-mandated requirement with zero implementation or test coverage). F2 is a real but lower-severity recovery-visibility gap. This is not a whole-v0.1 verdict — importers/consumer/recorder remain in progress and are excluded.
