---
task: A103 - Fix tautological test assertion and remove dead utils.py (4th re-audit L-NEW-9, L-NEW-10)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-22
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/tests/unit/test_more_coverage.py
  - examples/czsc_strategy/chan_strategy/utils.py
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
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

## Manual Verification

(pending — dev fills in)

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-22 | claude-code → claude-code | design → design | A103 (tautological test fix + dead code removal, 4th re-audit L-NEW-9/L-NEW-10) scoped; drafting design brief |
| 2026-07-22 | claude-code → kimi-code | design → dev | A103 promoted design->dev |
