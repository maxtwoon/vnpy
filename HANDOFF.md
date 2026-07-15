---
task: A65 - Fix Failing Test + Harden capture_window Against Missing Capture Metadata
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a65-third-party-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

First task of the 2026-07-14 third-party-audit remediation roadmap
(`docs/design/a65-third-party-audit-remediation-roadmap.md` §"A65"), started immediately after the
roadmap was designed (per the user's explicit choice to follow the audit's own priority order in
full).

**Re-verified 2026-07-15 by claude-code, still failing, line numbers unchanged:**
`python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` produces
`1 failed, 610 passed, 4 deselected`. The failure:
`test_simnow_consistency_source.py::test_build_strategy_surface_from_captured_session_uses_real_
callbacks` raises `KeyError: 'started_at'` inside `simnow_strategy_surface.py:40`'s
`capture_window` function, called unconditionally from `build_strategy_surface_from_captured_
session` at line 157.

**Root cause (confirmed via `git log`/`git show`):** this call to `capture_window` was added by a
separate, PARALLEL commit (`fb18b45e`, "A35: add optional historical DB auto-update to SimNow
observation wrapper") — this is NOT related to this session's own A61-A64 work (which touched
`simnow_strategy_surface.py`'s `build_strategy_surface_from_captured_session` for a different
reason — the workflow-owned symbol filter). The `fb18b45e` commit added `window_start`/
`window_end` fields to the captured-session surface's `meta`, but did not update the
`test_simnow_consistency_source.py` fixture (dating to A41, well before `fb18b45e`), which
constructs a capture dict with no `meta` key at all. Confirmed via direct read of
`simnow_daily_capture.py` that PRODUCTION captures always populate `started_at`/`ended_at` — this
is a test/robustness gap, not a live-capture risk, but it currently blocks a clean test run.

Full contract: `docs/design/a65-third-party-audit-remediation-roadmap.md` §"A65 — Fix Failing Test
+ Harden `capture_window` Against Missing Capture Metadata" (the authoritative design — this
HANDOFF summarizes it).

## Goal

Make `capture_window` (and/or its caller `build_strategy_surface_from_captured_session`) tolerant
of missing `started_at`/`ended_at` — either (a) `capture_window` returns a sentinel (e.g.
`("", "")` or `(None, None)`) when either key is absent, with callers treating that as "window
unavailable," or (b) `build_strategy_surface_from_captured_session` catches the missing-key case
explicitly and omits `window_start`/`window_end` from its `meta` output. Pick whichever keeps
`build_strategy_surface_from_capture` (the OTHER, older caller at line 65, which this task must
NOT change the behavior of) unaffected. Additionally, decide whether
`test_simnow_consistency_source.py`'s fixture should be updated to include `started_at`/
`ended_at` (matching real production captures) in addition to, or instead of, making the function
more tolerant.

## Acceptance Criteria

- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes with ZERO
      failures (currently `1 failed, 610 passed, 4 deselected`).
- [x] `build_strategy_surface_from_capture`'s (the pre-existing caller) own tests remain
      byte-identical — this task must not change its behavior.
- [x] A fixture proves `capture_window`/`build_strategy_surface_from_captured_session` handles
      missing `started_at`/`ended_at` gracefully (no crash), with the chosen semantic (sentinel
      value or graceful omission) explicitly asserted.
- [x] No threshold tuning; no pre-2026-04-24 data; no SimNow order/cancel/send path changed; no
      `GOAL PASSED`.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

## Manual Verification

Natively-run counts:

```text
python -m pytest examples/czsc_strategy/tests/unit/test_simnow_consistency_source.py -q
7 passed in 0.09s

python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
613 passed, 4 deselected in 29.06s

python tools/sync_check.py
PASS: 版本与文档一致。

python tools/sync_check.py --root examples/czsc_strategy
PASS: 版本与文档一致。

ruff check examples/czsc_strategy/diagnostics/simnow_strategy_surface.py examples/czsc_strategy/tests/unit/test_simnow_consistency_source.py
All checks passed!

.\run_next_work.ps1 -Preflight (from examples/czsc_strategy/diagnostics/)
189 passed in 16.02s
Preflight complete; live SimNow capture was not requested
```

Chosen semantic: `capture_window` returns `(None, None)` when either `started_at` or `ended_at`
is absent. `build_strategy_surface_from_captured_session` omits `window_start`/`window_end` from
`meta` in that case. `build_strategy_surface_from_capture` is unchanged (it continues to assume
production captures populate the window metadata).

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a65-third-party-audit-remediation-roadmap.md` §"A65". First task
   of a new 5-task roadmap (A65-A69) triaging the 2026-07-14 third-party audit's findings — read
   the design doc's Background for the full picture, including why this bug is unrelated to this
   session's own A61-A64 work.
2. **Scope:** `examples/czsc_strategy/diagnostics/simnow_strategy_surface.py` (`capture_window`
   and/or `build_strategy_surface_from_captured_session`) and
   `examples/czsc_strategy/tests/unit/test_simnow_consistency_source.py`. Do not touch the other
   changes from the parallel `fb18b45e` commit (`run_next_work.ps1`,
   `simnow_run_summary.py`'s historical-DB-auto-update feature, etc.) beyond what's needed to fix
   this one `KeyError` — this task is scoped to the test failure only.
3. **Two callers of `capture_window`, only one should change behavior:**
   `build_strategy_surface_from_capture` (line 65, pre-existing since A41-era work, its own tests
   must stay byte-identical) and `build_strategy_surface_from_captured_session` (line 157, where
   `fb18b45e` added the new, unguarded call). Whatever fix you choose must not alter the first
   caller's behavior.
4. **Don't silently paper over a genuinely-missing-metadata case in production** — if you choose
   the "return a sentinel" approach, make sure "unavailable" is genuinely distinguishable from a
   real window, not defaulted to a fake-but-plausible-looking value.
5. **Guardrails (reject-on-violation):** no threshold tuning; no pre-2026-04-24 data; no SimNow
   order/cancel/send paths touched; no `GOAL PASSED`; `build_strategy_surface_from_capture`'s
   existing tests must stay byte-identical.
6. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing** — this consistently correlates with one-round review acceptance.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A65 capture_window hardening + test fix implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-15 - A65 promoted from `docs/design/a65-third-party-audit-remediation-roadmap.md`'s
  draft to an active HANDOFF task, started immediately after the roadmap was designed. First task
  of the A65-A69 third-party-audit remediation wave, per the user's explicit choice to follow the
  audit's own priority order in full.
- 2026-07-15 - claude-code re-verified the test failure is still present and line numbers
  unchanged: `simnow_strategy_surface.py:40`'s `capture_window`, called unconditionally from
  `build_strategy_surface_from_captured_session:157` (added by the unrelated, parallel `fb18b45e`
  commit), raises `KeyError` against `test_simnow_consistency_source.py`'s pre-`fb18b45e` fixture.
  Confirmed via `simnow_daily_capture.py` that production captures always populate the required
  fields — this is a test/robustness gap, not a live-capture risk.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | codex → claude-code | done → dev | A65 (fix failing test + harden capture_window) promoted from third-party audit remediation roadmap; handoff design->dev |
| 2026-07-15 | kimi-code → codex | dev → review | A65 capture_window hardening + test fix implemented |
| 2026-07-15 | codex → codex | review → done | A65 review accepted |
