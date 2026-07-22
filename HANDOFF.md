---
task: A103 - Fix tautological test assertion and remove dead utils.py (4th re-audit L-NEW-9, L-NEW-10)
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-22
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/tests/unit/test_more_coverage.py
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

`diagnostics_ai_stock_review_report_2026-07-22d.md` (the FOURTH comprehensive re-audit) flagged two Low
findings. The user explicitly asked to fix both (unusual — every prior Low finding in this series was left
unfixed by design); this task addresses both in one go since they're small, independent, mechanical fixes.

**L-NEW-9 — tautological test assertion, `tests/unit/test_more_coverage.py`
(`test_data_adapter_default_paths_and_errors`):**

```python
with pytest.raises(ValueError, match="没有找到"):
    SqliteDataAdapter(str(db)).load_kline_data("T", table_name=None) if False else (_ for _ in ()).throw(ValueError("数据库中没有找到数据表"))
```

**claude-code independently confirmed this by reading the code:**
- `X if False else Y` always evaluates `Y` — the `SqliteDataAdapter(...).load_kline_data(...)` call before
  `if False` is dead, unreachable code; it never executes.
- `Y` is `(_ for _ in ()).throw(ValueError("数据库中没有找到数据表"))` — this constructs a generator and
  immediately calls `.throw()` on it, which raises the `ValueError` synchronously at that line, regardless
  of what the constructed-but-never-called `SqliteDataAdapter`/`load_kline_data` would have actually done.
  The `pytest.raises(...)` context manager "catches" this self-manufactured exception every time — the test
  always passes, and never actually exercises `load_kline_data`'s real "no table" error path.
- **Why the original author likely wrote it this way**: `db` (this test's fixture, built earlier in the same
  test function) already has two tables (`no_symbol`, `dates`) at this point in the test. Calling
  `load_kline_data("T", table_name=None)` on it would make `get_tables()` return a non-empty list, so
  `table_name = tables[0]` would be truthy and the real `raise ValueError("数据库中没有找到数据表")` at
  `data_adapter.py:301` would NOT fire — the test author's fixture couldn't naturally trigger this error, so
  they synthesized a fake exception instead of building a genuinely empty database to test against.
- **Confirmed real coverage exists elsewhere** (so this is not a live coverage gap, just a misleading/dead
  line): `tests/unit/test_branch_completion.py::test_adapter_empty_defaults_and_numeric_dates` (~lines
  58-65) builds a genuinely empty sqlite file (`db2`, zero tables) and calls
  `adapter2.load_kline_data("T")` inside `pytest.raises(ValueError)` — this DOES exercise the real
  `data_adapter.py:301` raise, just without the specific `match="没有找到"` string pin.

**L-NEW-10 — `chan_strategy/utils.py` is entirely dead code:**

- The file defines exactly three functions: `parse_signal`, `signal_key`, `signal_value` — none referenced
  anywhere else in the repo. **claude-code independently confirmed via repo-wide grep** (
  `grep -rn "parse_signal\|signal_key\|signal_value\|chan_strategy.utils\|from \.utils\|from chan_strategy import utils"`)
  that every other hit for these names is either czsc's own `Signal.signal_value`/`.key` properties (a
  different, unrelated object with a same-named property), independently-defined local test helpers with
  the same names (e.g. `tests/unit/test_exit_model.py`'s own `_signal_key`/`_signal_value`), or unrelated
  local variables — none of them import from `chan_strategy.utils`. `chan_strategy/__init__.py` doesn't
  reference `utils` either. The codebase's real signal parsing goes through czsc's own `Signal` class
  (`.key`, `.signal_value` properties) instead.

## Goal

1. **L-NEW-9 fix**: replace the tautological line in
   `test_data_adapter_default_paths_and_errors` with a real exercise of `load_kline_data`'s "no table"
   error path, using a genuinely empty database (zero tables) — mirror the pattern already used by
   `test_branch_completion.py::test_adapter_empty_defaults_and_numeric_dates`'s `db2` fixture (a fresh
   `sqlite3.connect(path).close()` with no `create table` calls at all). Since this test function already
   has a populated `db`/`adapter` in scope, create a second, separate empty-db fixture within the same test
   (a new `tmp_path`-based empty sqlite file, e.g. `empty_db = tmp_path / "empty_for_l9.db"`) rather than
   trying to reuse or mutate the existing populated `db`. Call the REAL
   `SqliteDataAdapter(str(empty_db)).load_kline_data("T", table_name=None)` inside
   `pytest.raises(ValueError, match="没有找到")`, keeping the same match string so the assertion is at
   least as specific as before, just genuinely exercised now. Close the new adapter properly (use the same
   `try/finally: adapter.close()` pattern the rest of this test file already uses).
2. **L-NEW-10 fix**: delete `chan_strategy/utils.py` entirely. Do a final repo-wide grep immediately before
   deleting (`grep -rn "parse_signal\|signal_key\|signal_value" --include="*.py" .` from
   `examples/czsc_strategy/`) to re-confirm no import/reference was added since this design brief was
   written, and record the grep output in the Decision Log as the final confirmation. If the grep turns up
   ANY reference to `chan_strategy.utils` or an import of `parse_signal`/`signal_key`/`signal_value` from
   that module specifically (not czsc's own `Signal` properties or unrelated local names), STOP and report
   it in the Decision Log instead of deleting — that would mean this task's premise was wrong.
3. **Do not touch anything else** in either file, and do not touch any other test in
   `test_more_coverage.py` or `test_branch_completion.py`.

## Acceptance Criteria

- [ ] `test_data_adapter_default_paths_and_errors`'s tautological `if False else (_ for _ in ()).throw(...)`
      construct is replaced with a real call to `load_kline_data` against a genuinely empty database,
      still inside `pytest.raises(ValueError, match="没有找到")`.
- [ ] `chan_strategy/utils.py` is deleted (confirmed via `git status`/diff — file removed, not just emptied).
- [ ] Re-confirmed via fresh repo-wide grep (recorded in Decision Log) that no code references
      `chan_strategy.utils`, `parse_signal`, or imports `signal_key`/`signal_value` from that module before
      deleting.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes — count should be
      UNCHANGED (no test added or removed, only one existing test's assertion made real; note this
      explicitly in the Decision Log since it's a rare "same count" acceptance case in this series).
- [ ] `-m realdb` equivalence gate still passes unchanged (this task doesn't touch
      `backtest_engine.py`/`positions.py`/`signals.py` — verify rather than assume per AGENTS.md rule).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] `ruff check` clean on touched files (note: deleting `utils.py` may also require checking no other
      file's ruff output referenced it, e.g. an unused-import warning elsewhere pointing at it — verify via
      a before/after ruff diff on the whole `chan_strategy/` package if in doubt).
- [ ] VERSION/CHANGELOG bumped — CHANGELOG entry should mention both fixes plainly: the test assertion is
      now real (was previously tautological/always-passing), and the unused `utils.py` module was removed.
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.
- [ ] **Remember the `synccheck:ignore` marker** for any version-like string in this task's own HANDOFF
      notes.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **Two small, independent, low-risk fixes in one task** — a test-assertion fix and a dead-code deletion.
   Neither touches production risk-control logic, unlike most tasks in this series.
2. **Do the final repo-wide grep before deleting `utils.py`** (Goal item 2) — this is a real safety check,
   not busywork; record its output in the Decision Log even if (as expected) it confirms zero references.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/WORK_LOG.md`, `diagnostics/simnow_20d_promotion_decision.md`, and any other SimNow-workstream
   files you see) — these belong to a concurrent, unrelated workstream. **Before committing, run
   `git status --short` and confirm only your own A103-scoped files are staged.**
4. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
5. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A103 tautological test + dead code cleanup completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times out
   for environment reasons, do not manually hand-edit HANDOFF.md's stage/owner fields to bypass it — leave
   the working tree with your changes uncommitted and note the failure in the Decision Log; claude-code will
   verify and commit properly.

## Decision Log

- 2026-07-22 (claude-code, design) - User explicitly requested both Low findings from the fourth
  comprehensive re-audit be fixed (unlike every prior Low finding in this series, which was deliberately
  left unfixed per this project's "don't chase every Low into a task" practice). Both are small, mechanical,
  independent fixes with no production risk-control logic touched, so scoped together in one task rather
  than two.
- 2026-07-22 (claude-code, design) - Confirmed via code reading that the L-NEW-9 tautological construct
  always raises its own synthesized exception regardless of what the never-executed
  `SqliteDataAdapter(...).load_kline_data(...)` call before `if False` would have done, and that real
  coverage of the same production error path already exists in `test_branch_completion.py` (without the
  specific match string) — so this fix closes a "misleading dead test line" rather than a live coverage gap.
- 2026-07-22 (claude-code, design) - Confirmed via repo-wide grep that `chan_strategy/utils.py`'s three
  functions have zero references anywhere in the repo; the codebase's real signal-parsing goes through
  czsc's own `Signal` class instead. Required dev to re-run the same grep immediately before deleting as a
  final safety check, in case anything changed between design and dev.

- 2026-07-22 (kimi-code, dev) - L-NEW-9 fixed as designed: the tautological
  `X if False else (_ for _ in ()).throw(ValueError("数据库中没有找到数据表"))` line in
  `test_data_adapter_default_paths_and_errors` replaced with a genuinely empty database
  (`empty_db = tmp_path / "empty_for_l9.db"`, `sqlite3.connect(empty_db).close()`, zero tables) and a REAL
  `SqliteDataAdapter(str(empty_db)).load_kline_data("T", table_name=None)` call inside the same
  `pytest.raises(ValueError, match="没有找到")`; new adapter closed via the file's existing
  `try/finally: adapter.close()` pattern. Nothing else in either test file touched.
- 2026-07-22 (kimi-code, dev) - L-NEW-10 final safety grep run immediately before deleting `utils.py`,
  from `examples/czsc_strategy/`: `grep -rn "parse_signal\|signal_key\|signal_value" --include="*.py" .`
  returned hits ONLY in these categories — (a) the three definitions inside `chan_strategy/utils.py`
  itself; (b) czsc's own `Signal`-adjacent code (`positions.py` `signal_value` property /
  `restructured_structural_signal_key` local names, `validation.py` `sig.signal_value` /
  `"signal_key"` dict keys); (c) `diagnostics/generate_signal_history.py` local variables;
  (d) independently-defined test helpers (`test_exit_model.py` `_signal_key`/`_signal_value`,
  `test_coverage_closure.py` `signal_value=` kwarg, `test_signal_contract.py` czsc `Signal.signal_value`
  assertions, `test_audit_issue_diagnostics.py` dict keys); (e) `diagnostics/signal_funnel.py`
  `signal_obj.signal_value` (czsc Signal property). A second grep for
  `chan_strategy.utils|from .utils import|from chan_strategy import utils|import utils` returned ZERO
  matches (exit 1). Confirmed: no import of `chan_strategy.utils` anywhere — file deleted.
- 2026-07-22 (kimi-code, dev) - Test count UNCHANGED as required: 779 passed / 4 deselected both before
  (A102 baseline) and after A103 — this is the series' rare "same count" acceptance case; one existing
  test's assertion was made real, no test added or removed.
- 2026-07-22 (kimi-code, dev) - Interpreter note: initial acceptance runs under `.venv_new` showed
  `test_position_sizing_research_equivalence.py::test_research_mode_equivalence_to_baseline` failing with
  a last-digit float drift (`sharpe_ratio: baseline=0.8091974663759458 actual=0.809197466375945`).
  Verified rather than assumed per AGENTS.md: stashed A103 changes, re-ran on clean HEAD — fails
  IDENTICALLY, so pre-existing/environmental to `.venv_new` (library-version drift vs the stored
  baseline), NOT caused by A103. The canonical interpreter for this series (used by A102's passing
  Manual Verification) is system Python 3.14 (`C:\Python314\python.exe`); under it both gates pass:
  779 not-realdb, 4/4 realdb.
- 2026-07-22 (kimi-code, dev) - ruff: workspace-wide baseline is dirty by design (`ruff check .` = 440
  pre-existing errors). Before/after comparison on the touched file: identical single pre-existing F401
  (`build_zhongshu_from_bis` unused import, present in HEAD too — verified via `git show HEAD:...`), zero
  new findings from A103; deleting `utils.py` reduced the `chan_strategy/` package error count 79 -> 78.
- 2026-07-22 (kimi-code, dev) - Root `tools/sync_check.py` initially failed on
  `deliverable 不存在 examples/czsc_strategy/chan_strategy/utils.py` — expected consequence of the
  deletion; fixed by removing `utils.py` from this task's HANDOFF frontmatter deliverables in the same
  edit that adds this log; a second re-run then flagged the literal pytest version string (9.0.3  # synccheck:ignore)
  in the Manual Verification preamble, fixed with an inline ignore marker (as the acceptance criteria
  require for version-like strings in HANDOFF notes). Final re-run of both gates: PASS.
- 2026-07-22 (kimi-code, dev) - VERSION bumped 0.2.40 -> 0.2.41  # synccheck:ignore with a CHANGELOG
  entry stating plainly: the test assertion is now real (was tautological/always-passing), and the unused
  `utils.py` module was removed. Concurrent SimNow-workstream files (`diagnostics/WORK_LOG.md`,
  `diagnostics/simnow_20d_promotion_decision.md`) left untouched.

## Manual Verification

All commands run natively on Windows from `D:\repo\vnpy` (canonical interpreter: system Python 3.14,
`C:\Python314\python.exe`, pytest 9.0.3  # synccheck:ignore — same interpreter previous tasks in this
series used; see Decision Log for why `.venv_new` was rejected).

1. Unit tests, count UNCHANGED (rare "same count" acceptance case — no test added/removed, one existing
   test's assertion made real):

   ```
   > python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
   ...........................................................              [100%]
   779 passed, 4 deselected in 49.18s
   ```

   (A102 baseline was also 779 — 779 -> 779  # synccheck:ignore as required.)

2. `-m realdb` equivalence gate (from `examples/czsc_strategy/`), verified rather than assumed:

   ```
   > python -m pytest tests/unit -m realdb -q
   ....                                                                     [100%]
   4 passed, 779 deselected in 80.42s (0:01:20)
   ```

3. Both sync_check gates (root gate re-run AFTER HANDOFF.md deliverables fix in this same edit):

   ```
   > python tools/sync_check.py --root examples/czsc_strategy
   [SYNC-CHECK][OK] 版本单一真相 = 0.2.41  (source: VERSION::)  # synccheck:ignore
   [SYNC-CHECK] PASS: 版本与文档一致
   ```

   Root `python tools/sync_check.py` initially FAILED only because HANDOFF.md frontmatter still listed the
   now-deleted `chan_strategy/utils.py` as a deliverable; fixed in this same HANDOFF edit, re-run passes
   (see Decision Log).

4. Preflight gate (`run_next_work.ps1` lives under `diagnostics/`, run from there; exit code 0):

   ```
   > powershell -ExecutionPolicy Bypass -File .\run_next_work.ps1 -Preflight
   ...
   ==> Preflight complete; live SimNow capture was not requested
   ```

5. ruff before/after on touched scope (no new findings introduced; package total went DOWN by 1 after
   deleting `utils.py`):

   ```
   > ruff check .tmp\a103_head_tmc.py            # HEAD copy of test_more_coverage.py
   Found 1 error.   (pre-existing F401: build_zhongshu_from_bis imported but unused)
   > ruff check examples/czsc_strategy/tests/unit/test_more_coverage.py
   Found 1 error.   (identical single pre-existing F401, untouched by A103)
   > ruff check examples/czsc_strategy/chan_strategy/ --statistics
   Found 78 errors. (was 79 before deleting utils.py — net -1; workspace-wide baseline is dirty
                     by design: `ruff check .` reports 440 pre-existing errors)
   ```

6. Final repo-wide grep before deleting `utils.py` (full output recorded in Decision Log):

   ```
   > grep -rn "parse_signal\|signal_key\|signal_value" --include="*.py" .   # from examples/czsc_strategy/
   (only definitions live in chan_strategy/utils.py itself; all other hits are czsc Signal.signal_value
    properties, diagnostics-script local variables, or independently-defined test helpers)
   > grep -rn "chan_strategy.utils|from .utils import|from chan_strategy import utils|import utils" .
   (exit 1 — zero matches)
   ```

7. Scope check before handoff — only A103-scoped files changed by this task (the two `diagnostics/*.md`
   modifications belong to the concurrent SimNow workstream and were NOT touched by kimi-code):

   ```
   > git status --short
    M examples/czsc_strategy/CHANGELOG.md
    M examples/czsc_strategy/VERSION
    D examples/czsc_strategy/chan_strategy/utils.py
    M examples/czsc_strategy/diagnostics/WORK_LOG.md                      (concurrent workstream, untouched)
    M examples/czsc_strategy/diagnostics/simnow_20d_promotion_decision.md (concurrent workstream, untouched)
    M examples/czsc_strategy/tests/unit/test_more_coverage.py
   ```

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-22 | claude-code → claude-code | design → design | A103 (tautological test fix + dead code removal, 4th re-audit L-NEW-9/L-NEW-10) scoped; drafting design brief |
| 2026-07-22 | claude-code → kimi-code | design → dev | A103 promoted design->dev |
| 2026-07-22 | kimi-code → codex | dev → review | A103 tautological test + dead code cleanup completed |
| 2026-07-22 | codex → codex | review → done | A103 review passed: verified committed diff, sync gates, reference grep, version/changelog, and accepted documented sandbox-limited pytest/preflight via Manual Verification |
