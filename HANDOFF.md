---
task: A80 - Data Adapter Unparseable-Row Counting
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-16
deliverables:
  - HANDOFF.md
  - docs/design/a79-fifth-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

Second of three tasks (A79-A81) from the fifth third-party audit remediation roadmap
(`docs/design/a79-fifth-audit-remediation-roadmap.md`), promoted after A79 reached `done` (codex
accepted on the first review round).

`chan_strategy/data_adapter.py`'s `SqliteDataAdapter.load_raw_bars()` (confirmed by claude-code:
method starts at line 341, the skip happens at line 407 — `continue  # 跳过无法解析的行` — inside
the date-parsing `for`/`else` block at lines 398-407) currently skips rows whose `datetime` column
can't be parsed against any of the four tried formats, with no counting or reporting. If a database
contains malformed timestamps, the backtest silently loses data without any visible signal — this
could subtly change bar counts, signal timing, or trade counts.

**Full contract**: `docs/design/a79-fifth-audit-remediation-roadmap.md` §"A80" (this HANDOFF
summarizes it).

## Goal

Add a counter for skipped/unparseable rows in `load_raw_bars()`, and surface that count in
`BacktestEngine.generate_report()`'s output dict (confirmed by claude-code: `load_raw_bars()` is
called from `BacktestEngine.load_data()` at line 230, which sets `self.bars`).

**This is an always-on, honest data-quality report, NOT a formal-evaluation-only feature** — unlike
A74/A76/A78/A79's pattern, this field should appear in `generate_report()`'s output regardless of
whether the run is formal-evaluation or default research-baseline, because it reports a fact about
the input data, not a stricter execution assumption. Record this design decision in the Decision
Log — do NOT wire it through `formal_evaluation_config()`.

**Do NOT add any fail/block behavior when the skipped-row count is non-zero** — this task is
explicitly a measurement/reporting addition only. A future task could decide what threshold (if
any) should turn "N rows skipped" into a hard failure, but inventing that threshold now, without
dedicated design attention, would repeat the exact anti-pattern this whole project has guarded
against (see A71's Decision Log for the established reasoning on why thresholds need their own
justification, not just being added because "some check felt incomplete").

## Acceptance Criteria

- [x] `load_raw_bars()` (or an appropriate wrapper) tracks how many rows were skipped due to
      unparseable datetime values, without changing which rows are skipped or how (the skip
      behavior itself is unchanged — only counting is added).
- [x] `BacktestEngine.generate_report()`'s output dict includes this count (field name is dev's
      call, e.g. `unparseable_rows_skipped`) in BOTH the default and formal-evaluation paths.
- [x] New unit tests: a dataset with some unparseable timestamps produces an accurate non-zero
      count; a clean dataset produces a count of zero.
- [x] No new fail/block/threshold behavior is introduced based on this count.
- [x] No changes to existing bar-loading behavior, signal calculation, or any existing test's
      numeric assertions.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [x] VERSION/CHANGELOG bumped.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a79-fifth-audit-remediation-roadmap.md` §"A80". Second of three
   A79-A81 tasks.
2. **Scope:** `chan_strategy/data_adapter.py`'s `load_raw_bars()`, and
   `chan_strategy/backtest_engine.py`'s `load_data()`/`generate_report()` to propagate and surface
   the count, plus test files under `tests/unit/`. Do NOT touch any signal-calculation logic, any
   SimNow order/cancel/send path, or add any new fail/threshold behavior.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A80-scoped files are staged.**
4. **Guardrails (reject-on-violation):** no new threshold/fail logic based on the skip count; no
   changes to which rows are skipped or the parsing formats tried; no SimNow order/cancel/send
   paths touched; no `GOAL PASSED`.
5. **Include a literal `## Manual Verification` heading** with natively-run counts (A77's first
   review round was rejected purely for lacking this literal heading — do not repeat that mistake).
   Run `ruff check` proactively before finishing.
6. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A80 unparseable-row counting implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Manual Verification

Run natively on the dev machine (Windows, Python 3.13):

```text
$ python -m pytest examples/czsc_strategy/tests/unit/test_a80_unparseable_rows.py -q
....                                                                     [100%]
4 passed in 0.25s

$ python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
707 passed, 4 deselected in 30.46s

$ python tools/sync_check.py
[SYNC-CHECK] PASS: 版本与文档一致。

$ python tools/sync_check.py --root examples/czsc_strategy
[SYNC-CHECK] PASS: 版本与文档一致。

$ examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight
==> Preflight complete; live SimNow capture was not requested

$ ruff check examples/czsc_strategy/chan_strategy/data_adapter.py \
              examples/czsc_strategy/chan_strategy/backtest_engine.py \
              examples/czsc_strategy/tests/unit/test_a80_unparseable_rows.py
All checks passed!
```

Note: `ruff check .` at the repository root still reports pre-existing lint issues in
`examples/czsc_strategy/chan_strategy/__init__.py`, `positions.py`, `utils.py`,
`validation.py`, and other local workspace files that are outside the A80 scope.

## Decision Log

- 2026-07-16 - A80 promoted from `docs/design/a79-fifth-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task, immediately after A79 reached `done`. Second of three tasks in the fifth
  audit-remediation roadmap.
- 2026-07-16 (claude-code pre-promotion research) - Confirmed `load_raw_bars()` (data_adapter.py:341)
  skips unparseable rows at line 407 with no counting; confirmed `BacktestEngine.load_data()`
  (backtest_engine.py:230) is the call site that would need to propagate a count into
  `generate_report()`'s output. Decided this is an always-on field (not formal-evaluation-only),
  since it reports data-quality fact, not a stricter execution assumption.
- 2026-07-16 (kimi-code dev) - Implemented counting via an optional `unparseable_count` out-parameter
  on `SqliteDataAdapter.load_raw_bars()` so existing call sites are unaffected; propagated the count
  to `BacktestEngine.unparseable_rows_skipped` and `generate_report()`/`print_report()` for both
  default and formal-evaluation paths. No skip logic, parsing formats, signal calculation, or
  threshold/fail behavior was changed.
- 2026-07-16 (claude-code independent verification, before triggering codex review) - Read the
  full diff: the `unparseable_count` out-parameter pattern (mutable single-element list) correctly
  avoids changing `load_raw_bars()`'s return type, keeping all existing call sites unaffected; the
  field is correctly always-present in `generate_report()`'s dict regardless of formal-evaluation
  mode, matching the design decision. Confirmed no new threshold/fail logic was introduced. Diffed
  `ruff check` before/after: 22 pre-existing errors before this diff, 21 after (one fewer — A80's
  own new parameter uses modern `list[int] | None` syntax correctly) — no regression. Re-ran
  everything independently, matching kimi-code's recorded counts exactly: full unit suite `707
  passed, 4 deselected`; both `sync_check.py` gates passed; `run_next_work.ps1 -Preflight` passed.
  Scope was clean (only A80-scoped files staged).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-16 | claude-code → kimi-code | design → dev | A80 (data adapter unparseable-row counting) promoted from fifth third-party audit remediation roadmap; handoff design->dev |
| 2026-07-16 | kimi-code → codex | dev → review | A80 unparseable-row counting implemented |
