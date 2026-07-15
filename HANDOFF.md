---
task: A78 - Formal-Evaluation intrabar Stop-Loss Default + RESEARCH_BASELINE Consumption Guard
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-16
deliverables:
  - HANDOFF.md
  - docs/design/a76-fourth-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

Third and FINAL task of the fourth third-party audit remediation roadmap
(`docs/design/a76-fourth-audit-remediation-roadmap.md`), promoted after A77 reached `done` (codex
accepted on the second review round, after a first-round rejection over a missing explicit Manual
Verification block — a documentation formatting gap, not a substantive code issue). Completing this
task finishes the entire A76-A78 roadmap.

Two medium-severity audit findings, both related to "formal evaluation should be more conservative
than research baseline," bundled into one task to avoid a fourth separate edit to
`formal_evaluation_config()` (A74/A76 already extended it twice):

1. `chan_strategy/config.py`'s `stop_execution_model` defaults to `"close"` (stop-loss checked only
   at bar close); `"intrabar"` (uses bar high/low to detect intra-bar stop touches) is opt-in.
   Futures can gap or move through a stop level within a bar, so `"close"` can report a later, more
   favorable stop-loss trigger than would really occur — formal evaluation should default to the
   more conservative `"intrabar"`.
2. The audit recommended a lightweight guard preventing any future "promotion/acceptance" logic
   from consuming a report whose `mode_label` (A70) is `"RESEARCH_BASELINE"` as if it were
   production-tradable evidence.

**Full contract**: `docs/design/a76-fourth-audit-remediation-roadmap.md` §"A78" (this HANDOFF
summarizes it).

## Goal

1. Extend `formal_evaluation_config()` (A74, further extended by A76 for
   `rollover_open_gating`) to ALSO temporarily override `stop_execution_model` to `"intrabar"` for
   the duration of a formal-evaluation run, restoring the original value afterward (including on
   exception) — following the exact same save/restore pattern already used for the other three
   overridden keys.
2. Add a new, reusable guard function (naming is dev's call, e.g.
   `assert_not_research_baseline(report: dict) -> None`) that raises if
   `report.get("mode_label") == "RESEARCH_BASELINE"`, intended for future promotion/acceptance
   logic to call. This task only adds the function itself with tests proving it behaves correctly
   — it does NOT need to wire this into any existing SimNow promotion-decision logic or any other
   existing script (that would be a separate, larger task outside this roadmap's scope).

## Acceptance Criteria

- [x] `formal_evaluation_config()` additionally overrides `STRATEGY_CONFIG["stop_execution_model"]`
      to `"intrabar"` and restores the original value afterward, including when the wrapped code
      raises an exception — proven by a dedicated test (following the same pattern as A74's
      `test_formal_evaluation_config_restores_original_values_on_exception` and A76's equivalent).
- [x] A test proves `run_formal_evaluation()`'s reported `stop_execution_model` is `"intrabar"`
      during the run.
- [x] A new reusable guard function exists that raises when given a report dict with
      `mode_label == "RESEARCH_BASELINE"`, and does NOT raise for any other `mode_label` value.
      Tests cover both cases.
- [x] No changes to the non-formal-evaluation default path's behavior — all existing tests pass
      unmodified, no numeric assertions change.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [x] VERSION/CHANGELOG bumped.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a76-fourth-audit-remediation-roadmap.md` §"A78". Third and FINAL
   task of the A76-A78 roadmap — completing this closes out the entire fourth audit remediation
   wave.
2. **Scope:** `chan_strategy/backtest_engine.py` (extend `formal_evaluation_config()`; add the new
   guard function — or place the guard function in a more fitting shared module if you judge one
   exists, record the choice in the Decision Log), plus test files under `tests/unit/`. Do NOT touch
   any SimNow order/cancel/send path, and do NOT wire the guard function into any existing SimNow
   promotion-decision script — that is explicitly out of scope for this task.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A78-scoped files are staged.**
4. **Guardrails:** no threshold tuning; no pre-2026-04-24 data for any new parameter choice; no
   SimNow order/cancel/send paths touched; no `GOAL PASSED`; the `stop_execution_model` override
   must be provably restored on both success and exception paths — a leak into subsequent test runs
   is a reject-worthy bug.
5. **Include a literal `## Manual Verification` heading with natively-run counts** — A77's first
   review round was rejected purely because this heading was missing even though the content was
   present elsewhere in the Decision Log; do not repeat that mistake. Run `ruff check` proactively
   before finishing.
6. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A78 formal-evaluation intrabar stop default and RESEARCH_BASELINE guard implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. **This is the last task in the
   entire A76-A78 roadmap** — after this reaches `done`, trigger a fresh third-party audit per the
   standing instruction (see A76's original Background for the full "keep iterating until score >
   75, no medium+ issues" instruction).

## Manual Verification

Natively-run acceptance results (current working tree):

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` → **702 passed, 4 deselected**.
- `python tools/sync_check.py` → **PASS** (vnpy version 4.4.0).
- `python tools/sync_check.py --root examples/czsc_strategy` → **PASS** (czsc_strategy VERSION file consistent with CHANGELOG).
- `examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight` → **191 passed**; live capture not requested.
- `ruff check examples/czsc_strategy/chan_strategy/backtest_engine.py examples/czsc_strategy/tests/unit/test_formal_evaluation.py` → **All checks passed**.
  - Note: `ruff check .` across the whole repository reports many pre-existing lint issues in unrelated local files (`docs/chanlunnew/`, `examples/czsc_strategy/_debug_zs.py`, notebooks, etc.); the A78-scoped files are clean.

## Decision Log

- 2026-07-16 - A78 promoted from `docs/design/a76-fourth-audit-remediation-roadmap.md`'s draft to
  an active HANDOFF task, immediately after A77 reached `done`. Third and final task of the fourth
  audit-remediation roadmap.
- 2026-07-16 (claude-code pre-promotion research) - Confirmed `stop_execution_model` default is
  `"close"` in `config.py:63`, with `"intrabar"` behavior gated in `positions.py:886`/`:901`.
- 2026-07-16 (kimi-code dev) - Implemented A78: added `stop_execution_model="intrabar"` to
  `formal_evaluation_config()` (save/restore on both success and exception paths); added
  `assert_not_research_baseline(report: dict)` guard in the same module so the formal-evaluation
  surface stays together; extended `tests/unit/test_formal_evaluation.py` to cover the override,
  restore, entry-point report field, and guard behavior; bumped `examples/czsc_strategy/VERSION` and
  recorded the change in `CHANGELOG.md`. No SimNow order/cancel/send paths were touched; no threshold tuning.
- 2026-07-16 (claude-code independent verification, before triggering codex review) - Read the
  full diff: `formal_evaluation_config()`'s keys/overrides tuples both extended consistently with
  the existing pattern; `assert_not_research_baseline()` is a simple, correct guard. Confirmed
  `stop_execution_model` was already present in `generate_report()`'s output dict (from before
  A70), so the new test assertion on `report["stop_execution_model"]` needed no additional wiring.
  Re-ran everything independently, matching kimi-code's recorded counts exactly: full unit suite
  `702 passed, 4 deselected`; `ruff check` clean; both `sync_check.py` gates passed;
  `run_next_work.ps1 -Preflight` passed. Scope was clean (only A78-scoped files committed by
  kimi-code, unrelated concurrent-workstream files untouched).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-16 | claude-code → kimi-code | design → dev | A78 (formal-evaluation intrabar stop default + RESEARCH_BASELINE guard) promoted from fourth third-party audit remediation roadmap; handoff design->dev |
| 2026-07-16 | kimi-code → codex | dev → review | A78 formal-evaluation intrabar stop default and RESEARCH_BASELINE guard implemented |
| 2026-07-16 | codex → codex | review → done | A78 review passed: formal-evaluation intrabar stop override and RESEARCH_BASELINE guard verified |
