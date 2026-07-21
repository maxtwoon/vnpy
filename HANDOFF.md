---
task: A94 - Document the always-false "确认" branch in divergence gating (audit M4)
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-21
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/positions.py
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

`diagnostics_ai_stock_review_report.md` (2026-07-21 full project audit) flagged **M4**:
`signal_divergence_status()` (`signals.py:295-347`) only ever produces `v1 = "无"` or `v1 = "疑似"` — there
is no code path in that function that produces `"确认"` (confirmed the function's docstring already says
single-level divergence can only ever yield "疑似", never a confirmed level; `grep` confirms the literal
string `"确认"` never appears as an assigned value of `v1` anywhere in the function). Two consumer sites —
`positions.py:396` and `positions.py:468` — gate on
`div_val.startswith("疑似") or div_val.startswith("确认")`. Since the producer can never emit `"确认"`,
that half of the `or` is permanently dead — not a logic bug (the gating still works correctly via the
`"疑似"` branch), but a maintenance trap: a future reader could reasonably assume a "confirmed divergence"
tier exists and is being checked for, when it does not exist anywhere in the codebase.

## Goal

**This is a documentation-only clarification, not a behavior change or a dead-code removal.** claude-code
deliberately chose "add a comment explaining the intent" over "delete the dead half of the `or`" for this
task: removing `startswith("确认")` would carry a small forward-looking risk (if a future divergence-level
enhancement ever does produce a `"确认"` value, silently having removed this check would require someone
to remember to re-add it) for zero present-day benefit (the check costs nothing at runtime). A one-line
comment fully addresses the audit's actual concern (a maintainer being misled into thinking a "confirmed"
tier is being actively distinguished) without taking on any removal risk.

1. At both `positions.py:396` and `positions.py:468`, add a short comment directly above (or on the same
   line as) the `if not (div_val.startswith("疑似") or div_val.startswith("确认")):` check, stating plainly
   that `signal_divergence_status()` (`signals.py`) currently only ever emits `"疑似"` (never `"确认"`), so
   the `"确认"` half of this check is presently dead but kept for forward compatibility should a future
   divergence-level enhancement add a genuine "confirmed" tier. Chinese or English is fine — match the
   surrounding code's language (this file mixes both; existing nearby comments are Chinese, so Chinese is
   probably the better fit, dev's call).
2. **Do not change the `if` condition itself, do not touch `signal_divergence_status()` in `signals.py`,
   do not add a new divergence tier.** This task is exactly two comment additions, nothing else.
3. Optionally (dev's call, not required): if you want to make the always-false-half explicit for a future
   test-coverage tool without changing behavior, you may add a `# pragma: no branch` or equivalent marker
   consistent with how this codebase already marks other known-dead-but-intentional branches (e.g.
   `signals.py:340`'s existing `# pragma: no branch - complementary divergence direction` comment is the
   established style for exactly this situation in this codebase — follow that precedent if you add a
   marker, don't invent a new annotation style).

## Acceptance Criteria

- [ ] A comment exists at both `positions.py:396` and `positions.py:468` explaining that the `"确认"`
      branch is currently unreachable because `signal_divergence_status()` never emits it, and why it's
      being kept (forward compatibility, zero cost).
- [ ] No change to the `if` condition's logic, to `signals.py`, or to any test's assertions.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes, exact same pass
      count as before this change (pure comment addition).
- [ ] `-m realdb` equivalence gate still passes unchanged (comment-only change should not need this, but
      this task touches `positions.py` again right after A93, so verify rather than assume).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] `ruff check` clean on touched files (positions.py is already clean after A93 — do not reintroduce
      any findings).
- [ ] VERSION/CHANGELOG bumped (even for a comment-only change, per house convention — document which
      case this is in the Decision Log; if the team convention actually treats pure comments as not
      needing a version bump, state that reasoning explicitly rather than silently skipping it).
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **This is the smallest task in the M-series so far — two comments, nothing else.** Do not use this as
   an opportunity to also touch `signals.py` or add a real "confirmed divergence" tier — that would be a
   scope change requiring its own design, not something to bundle in here.
2. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to a
   concurrent, unrelated SimNow-observation workstream. **Before committing, run `git status --short`
   and confirm only your own A94-scoped files are staged.**
3. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
4. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A94 divergence dead-branch documented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times
   out for environment reasons (this has happened repeatedly on this machine, apparently correlated with
   the pipeline's timeout landing right at the finish line), do not manually hand-edit HANDOFF.md's
   stage/owner fields to bypass it — leave the working tree with your changes uncommitted and note the
   failure in the Decision Log; claude-code will verify and commit properly.

## Decision Log

- 2026-07-21 - Continuing the M-series from the audit report after M5 (A93) closed. This task (A94) is
  M4, chosen next for being the smallest/lowest-risk remaining item (pure comment, no logic touched).
- 2026-07-21 (kimi-code, dev) - Implemented exactly two comment additions in `positions.py`
  (above both `if not (div_val.startswith("疑似") or div_val.startswith("确认")):` sites), in English to
  match the surrounding comments at those sites. Did **not** add a `# pragma: no branch` marker: coverage
  branch analysis does not split the two halves of an `or` into separate branch arcs, so the marker would
  be meaningless here — unlike `signals.py:340`'s pragma, which marks a genuinely complementary
  `elif` branch. VERSION/CHANGELOG bumped to 0.2.32 <!-- synccheck:ignore --> per house convention (every externally visible
  change = code + version bump + changelog entry, same commit); a comment-only change still counts as
  externally visible since it ships in the tracked source tree.
- 2026-07-21 (claude-code, design) - Deliberately chose "document the dead branch" over "remove it" —
  removal carries small forward-looking risk for zero present-day benefit; a comment fully addresses the
  audit's actual concern (maintainer confusion) without that risk. Confirmed via grep that
  `signal_divergence_status()` never assigns `"确认"` to `v1` anywhere in its body, and noted the existing
  `signals.py:340` `# pragma: no branch - complementary divergence direction` comment as this codebase's
  established precedent for marking known-but-intentional dead branches, in case dev wants to add a similar
  marker here.

## Manual Verification

Run natively on this machine (kimi-code, 2026-07-21). All commands from repo root `D:\repo\vnpy`
unless noted. Pass counts identical to A93 baseline (pure comment addition, no behavior change).

```
$ git status --short   # pre-change baseline: clean working tree
(no output — clean)

$ ruff check examples/czsc_strategy/chan_strategy/positions.py
All checks passed!

$ python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
761 passed, 4 deselected in 40.90s

$ python -m pytest examples/czsc_strategy/tests/unit -q -m realdb
4 passed, 761 deselected in 78.03s (0:01:18)

$ python tools/sync_check.py
[SYNC-CHECK][OK] 版本单一真相 = 4.4.0  (source: vnpy/__init__.py::__version__)
[SYNC-CHECK][WARN] archive_dir 不存在: docs/archive/（仅提示，不 FAIL）
[SYNC-CHECK] PASS: 版本与文档一致。
(exit 0)

$ python tools/sync_check.py --root examples/czsc_strategy
[SYNC-CHECK][OK] 版本单一真相 = 0.2.32  (source: VERSION::) <!-- synccheck:ignore -->
[SYNC-CHECK] PASS: 版本与文档一致。
(exit 0)

$ cd examples\czsc_strategy; powershell -ExecutionPolicy Bypass -File .\diagnostics\run_next_work.ps1 -Preflight
Repository: D:\repo\vnpy
Diagnostics: D:\repo\vnpy\examples\czsc_strategy\diagnostics
Date: 2026-07-21
==> Compile SimNow capture script
==> Run SimNow workflow unit tests
200 passed in 23.25s
==> Build pending replay backfill plan
==> Preflight complete; live SimNow capture was not requested
(exit 0)
```

Note: `run_next_work.ps1` lives at `examples/czsc_strategy/diagnostics/run_next_work.ps1` (not the
workspace root as the acceptance line literally suggests); it was invoked from
`examples/czsc_strategy/` as the working directory, per the intent of the criterion.

Verification of the actual deliverable (comment-only, no logic touched):

```
$ git diff --stat examples/czsc_strategy/chan_strategy/positions.py
... 8 insertions(+)
$ git diff examples/czsc_strategy/chan_strategy/positions.py | Select-String '^[+-]'
(only '+' comment lines; no '-' lines; the `if` conditions are untouched)
```

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-21 | claude-code → kimi-code | design → dev | A94 (document dead 确认 branch, audit M4) promoted; handoff design->dev |
| 2026-07-21 | kimi-code → codex | dev → review | A94 divergence dead-branch documented |
| 2026-07-21 | codex → codex | review → done | A94 review passed |
