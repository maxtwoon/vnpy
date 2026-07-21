---
task: A102 - Add parity regression test for the two 20d promotion-readiness implementations (3rd re-audit M-NEW-3)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-22
deliverables:
  - HANDOFF.md
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

`diagnostics_ai_stock_review_report_2026-07-22c.md` (the THIRD comprehensive re-audit) flagged **M-NEW-3**:
two independently-maintained functions compute the "20-day SimNow promotion readiness" verdict from the
same `simnow_observation_ledger.jsonl` data and already disagree on their sub-computations:

- `diagnostics/simnow_daily_monitor.py:625-692` (`build_20d_report`) — `halt_days` also checks
  `order_safety.status == "halt"`; `matched_days` requires `consistency.matched is True AND
  consistency.verified is True`.
- `diagnostics/simnow_promotion_decision.py:35-105` (`decide_promotion`) — `halt_days` only checks
  `thresholds.status == "halt"` (ignores `order_safety`); `matched_days` accepts any truthy
  `consistency.matched` (doesn't require `verified`).

**claude-code independently re-verified this by reading both functions in full** (re-verify yourself in
case line numbers have drifted) — the audit's characterization is accurate. **claude-code also
independently re-verified the audit's "why this doesn't currently flip the final verdict" claim**: both
functions gate `ready_to_expand`/`ready` first on `valid_observation_days >= min_days`, where
`is_valid_observation()` (`diagnostics/simnow_observation_rules.py:9-44`, imported identically by both
modules) requires `status=="pass"`, `consistency.matched is True`, `consistency.verified is True`,
`thresholds.status=="pass"`, AND `order_safety.status=="pass"` — strictly stricter than either function's
own diverging `halt_days`/`matched_days` sub-checks, so any day that would make the two implementations
disagree is already excluded from `valid_observation_days` by the shared, non-diverged gate. This is a real
but currently-inert divergence, not a live bug today.

## Decision: this is a real finding, but it touches live, concurrently-active files — scope minimally

**This task deliberately does NOT modify `simnow_daily_monitor.py` or `simnow_promotion_decision.py`.**
Unlike every prior A9x/A10x task (which touched pure backtest-engine code), these two files are part of
the actively-running SimNow 20-day promotion-decision workstream — per this repo's own recent commit
history (`simnow: refresh 20d promotion decision status (observed 5/20, halt 2, pending 3)`), a live,
concurrent process is producing new ledger entries and consuming these functions' output right now.
Deleting/merging one implementation (the audit's suggested fix) or changing either function's
`halt_days`/`matched_days` logic carries real risk of interfering with or invalidating that in-progress
external process, for a bug that is independently confirmed NOT currently live (see Background). This is a
materially different risk profile from every fix so far in this series and warrants extra caution beyond
the project's usual "verify before changing" discipline.

**Scope: add a pure regression/parity test only** — no changes to either function's implementation, no
changes to `run_next_work.ps1`, `simnow_20d_promotion_decision.md`, or any other file in the established
do-not-touch list. This still delivers real value: it converts the audit's "no test enforces these stay in
sync" observation into an actual, permanent regression test that will fail loudly the moment a future edit
to either function (or to `is_valid_observation`) breaks the currently-incidental safety net the audit
identified — exactly the audit's own secondary suggestion ("at minimum add a regression test... so any
future edit... fails CI immediately"). If a human maintainer later decides to actually consolidate the two
implementations, that becomes a separate, deliberately-scoped task done with direct visibility into the
concurrent workstream's state — explicitly NOT this task.

## Goal

1. Create a NEW test file `tests/unit/test_simnow_promotion_parity.py` (do not extend the existing
   `tests/unit/test_simnow_daily_monitor.py` — creating a new file avoids any chance of touching a file the
   concurrent SimNow workstream might also be editing). Import both `build_20d_report`
   (`diagnostics/simnow_daily_monitor.py`) and `decide_promotion` (`diagnostics/simnow_promotion_decision.py`)
   directly — check how `test_simnow_daily_monitor.py` imports `diagnostics/` modules (it's likely a
   non-package directory needing a `sys.path`/importlib shim; match whatever pattern that existing test file
   already uses so the new file is consistent with the codebase's existing convention for testing
   `diagnostics/` scripts).
2. Build a small set of synthetic ledger-record fixtures (list-of-dict rows shaped like
   `simnow_observation_ledger.jsonl` entries — check `is_valid_observation()`
   (`diagnostics/simnow_observation_rules.py:9-44`) and both target functions' field reads to construct
   valid minimal rows) covering at least:
   - A "clean" 20-day window where every day is fully valid (`is_valid_observation` true for all) → assert
     both `build_20d_report(...)["ready_to_expand"]` and `decide_promotion(...)["ready_to_expand"]` agree
     (both `True`).
   - A window exercising the CURRENT divergence directly: at least one day where `order_safety.status ==
     "halt"` but `thresholds.status != "halt"` (so the two `halt_days` computations would disagree if
     nothing else gated them) — assert both functions still agree on `ready_to_expand` (both `False`,
     since `is_valid_observation` already excludes that day via its own `order_safety` check) AND
     explicitly assert on `halt_days`/`consistency_matched_days`/`matched_days` from each function's own
     output to document that the sub-COUNTS differ even though the final verdict doesn't — this is the
     actual regression pin: if a future change to either function or to `is_valid_observation` ever makes
     the sub-count divergence propagate into a `ready_to_expand` disagreement, this test must fail.
   - A window with fewer than `min_days` valid days → assert both functions agree `ready_to_expand=False`
     for the same underlying reason (`valid_observation_days < min_days`).
3. **Do not modify `build_20d_report`, `decide_promotion`, `is_valid_observation`, or any file under
   `diagnostics/` other than adding the one new test file under `tests/unit/`.**
4. Add a short docstring/comment at the top of the new test file explaining WHY this test exists (pins the
   currently-incidental safety-net property M-NEW-3 identified; not a claim that the two implementations
   are actually unified) and linking back to `diagnostics_ai_stock_review_report_2026-07-22c.md`'s M-NEW-3
   for the full context, so a future reader understands this is intentionally a parity-pin, not proof the
   duplication itself has been resolved.

## Acceptance Criteria

- [ ] New file `tests/unit/test_simnow_promotion_parity.py` added; zero changes to any file under
      `diagnostics/`, `chan_strategy/`, or `examples/czsc_strategy/tests/unit/test_simnow_daily_monitor.py`.
- [ ] At least the three scenarios from Goal item 2 are covered, all passing.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes (count increases only
      by the new tests added — note the exact delta in the Decision Log).
- [ ] `-m realdb` equivalence gate still passes unchanged (this task touches only a new diagnostics test
      file, not any backtest-engine code — verify rather than assume per AGENTS.md rule).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes — **run it, do not skip it just
      because this task avoids editing `run_next_work.ps1` itself; the preflight gate still needs to pass**.
- [ ] `ruff check` clean on the new test file.
- [ ] VERSION/CHANGELOG bumped — CHANGELOG entry must state this is a **test-only addition, explicitly NOT
      a fix to the underlying duplication** (the duplication itself remains, by deliberate scope decision,
      for a human maintainer to address with direct visibility into the concurrent SimNow workstream).
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.
- [ ] **Remember the `synccheck:ignore` marker** for any version-like string in this task's own HANDOFF
      notes.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **This task is test-only. Do NOT touch `diagnostics/simnow_daily_monitor.py`,
   `diagnostics/simnow_promotion_decision.py`, or `diagnostics/simnow_observation_rules.py`** — read the
   "Decision: this is a real finding, but it touches live, concurrently-active files" section above in full
   before starting. This is different from every prior task in this series; do not "helpfully" fix the
   duplication itself even though the audit's suggested fix mentions it — that's explicitly out of scope.
2. **Create a brand-new test file, do not extend `tests/unit/test_simnow_daily_monitor.py`** — this avoids
   any risk of a merge conflict with the concurrent SimNow workstream, which may also be touching that file.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/WORK_LOG.md`, `diagnostics/simnow_20d_promotion_decision.md`, and any other SimNow-workstream
   files you see) — these belong to a concurrent, unrelated workstream. **Before committing, run
   `git status --short` and confirm only your own A102-scoped files are staged** — this check matters more
   than usual for this task given how close it sits to the concurrent workstream's territory.
4. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
5. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A102 promotion-readiness parity test completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times out
   for environment reasons, do not manually hand-edit HANDOFF.md's stage/owner fields to bypass it — leave
   the working tree with your changes uncommitted and note the failure in the Decision Log; claude-code will
   verify and commit properly.
6. This is the sole Medium-severity finding from the third comprehensive re-audit
   (`diagnostics_ai_stock_review_report_2026-07-22c.md`); that report also flagged 1 new Low (L-NEW-8,
   the legacy `future_func_result` compatibility shim in `validation.py` has the same "unknown defaults to
   pass" shape A101 fixed, but on a confirmed-unreachable code path) which was NOT scoped as a follow-up
   task, consistent with this project's practice of not chasing every Low finding into its own task. The
   report found **0 new High-severity findings** — the fourth consecutive audit pass with no new High issue
   in the core risk-mechanics code.

## Decision Log

- 2026-07-22 (claude-code, design) - This is the sole Medium-severity finding from the THIRD comprehensive
  re-audit. Deliberately scoped to test-only (no production code change) because, unlike every prior
  A9x/A10x fix, the affected functions (`build_20d_report`, `decide_promotion`) are part of a live,
  concurrently-running SimNow promotion-decision process (evidenced by this repo's own recent commit
  history showing active 20-day observation tracking) — the risk of interfering with that in-progress
  external work outweighs closing a divergence that is independently confirmed not currently live (both
  functions' final `ready_to_expand` verdict is protected by the stricter, non-diverged
  `is_valid_observation()` gate today).
- 2026-07-22 (claude-code, design) - Explicitly rejected the audit's primary suggested fix (delete/merge one
  implementation) as out of scope for this task — that requires a human maintainer's direct visibility into
  which implementation the concurrent workstream currently depends on, which claude-code does not have.
  Implemented only the audit's secondary suggestion (a parity regression test) instead.
- 2026-07-22 (claude-code, design) - Chose to create a brand-new test file rather than extend
  `tests/unit/test_simnow_daily_monitor.py` specifically to minimize any chance of a merge conflict with
  the concurrent workstream, which may independently be modifying that file.

## Manual Verification

(pending — dev fills in)

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-22 | claude-code → claude-code | design → design | A102 (promotion-readiness parity test, 3rd re-audit M-NEW-3) scoped; drafting design brief |
| 2026-07-22 | claude-code → kimi-code | design → dev | A102 promoted design->dev |
