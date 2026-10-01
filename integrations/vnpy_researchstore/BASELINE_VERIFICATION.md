## Baseline Verification Report — `integrations/vnpy_datasource`

**Scope:** Read-only baseline check per `TASK_CLAUDE_BASELINE_01.md`. No product code edited, no source/gateway queries run, no `.coordination/*.jsonl` scanned.

### Interpreter / module origins
```
sys.executable: D:\veighna_studio\python.exe
sys.version:    3.13.8 (heads/4.1-dirty:851bb6b, Dec 6 2025) [MSC v.1936 64 bit (AMD64)]
vnpy.__file__:            D:\repo\vnpy\vnpy\__init__.py           (vnpy.__version__ = 4.4.0)
vnpy_datasource.__file__: D:\repo\vnpy\integrations\vnpy_datasource\vnpy_datasource\__init__.py  (version 0.1.0)
```
Both resolve to editable installs in the existing repo tree under the Studio interpreter, no separate `.venv`. No engine/datafeed instantiated — only module import.

### Baseline hash verification
Checked all 24 entries in `integrations/vnpy_researchstore/.coordination/datasource-baseline.json` against current files on disk (sha256 + byte count).
- **Result: 24/24 match, 0 missing, 0 mismatches.**
- `git status --porcelain` shows both `integrations/vnpy_datasource/` and `integrations/vnpy_researchstore/` as untracked (`??`), consistent with no committed changes since the baseline was recorded.
- Label: this is a **current/concurrent** baseline confirmation taken now (2026-09-16), not a claim about future edits — no evidence found of in-flight modification at check time.

### Test suite
```
D:\veighna_studio\python.exe -m pytest integrations/vnpy_datasource/tests -q
→ 81 passed, 1 warning in 6.59s   (exit 0)
```
Warning: `pytz` `DeprecationWarning` in `test_client.py::test_daily_framework_dates_are_converted_to_shanghai_first` (via `pytz/tzinfo.py` using `datetime.utcfromtimestamp`). Matches VERIFICATION.md's stated "81项针对性离线测试通过" and its noted pre-existing pytz deprecation notice — no new failures.

### Ruff
```
D:\veighna_studio\python.exe -m ruff check integrations/vnpy_datasource
→ All checks passed!   (exit 0)
```

### `tools/sync_check.py`
```
D:\veighna_studio\python.exe tools/sync_check.py
→ [OK] 版本单一真相 = 4.4.0 (source: vnpy/__init__.py::__version__)
→ [WARN] archive_dir 不存在: docs/archive/（仅提示，不 FAIL）
→ PASS: 版本与文档一致。   (exit 0)
```
(First run showed mojibake under default console codepage; re-ran once with `PYTHONIOENCODING=utf-8` for legible text only — same result/exit code, not a re-run of check logic.) The `docs/archive/` warning is pre-existing/informational and unrelated to `vnpy_datasource`; it does not fail the gate.

### Limitations / what was not covered
- Did not run `verify_live.py`, `research_data.py`, or any networked/source query, per task restriction.
- Did not inspect `.coordination/*.jsonl` transcripts.
- Did not run `mypy` (not requested by this task).
- No pre-existing root sync failures observed in this single run; nothing to distinguish from new-integration issues since sync_check passed cleanly.
- This confirms only: interpreter/module identity, baseline-file integrity, datasource test/lint status, and sync_check status at this point in time — not datasource data-source acceptance or whole-project state.
