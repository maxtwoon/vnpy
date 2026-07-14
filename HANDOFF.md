---
task: A63 - Daily Brief: Surface Window Fields
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-14
deliverables:
  - HANDOFF.md
  - docs/design/a61-simnow-observation-window-hardening.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

Third task of the 2026-07-14 SimNow-observation-window-hardening roadmap
(`docs/design/a61-simnow-observation-window-hardening.md` §"A63"), promoted immediately after A62
reached `done` (codex accepted the round-2 fix directly).

**Finding #3 (re-verified 2026-07-14 by claude-code):** `simnow_daily_brief.py`'s daily-brief
renderer (lines 196-205, confirmed) reads `ledger_summary` and prints only
`valid_observation_days`, `consecutive_valid_days`, `ready_to_expand`, and `promotion_blockers`.
Confirmed via direct read of `simnow_run_summary.py:21-41`'s `SAFE_LEDGER_SUMMARY_FIELDS` whitelist
that `observation_start_date`, `excluded_before_start_count`, and `next_action` are **already
present** in the `ledger_summary` dict the brief reads from — they are simply not rendered. This
makes the machine-readable JSON correct but the human-facing report insufficiently clear about
window basis, risking a human reviewer misjudging whether a given day counts toward the 20-day
window.

Full contract: `docs/design/a61-simnow-observation-window-hardening.md` §"A63 — Daily Brief:
Surface Window Fields" (the authoritative design — this HANDOFF summarizes it).

## Goal

Add `observation_start_date`, `excluded_before_start_count`, and `next_action` to
`simnow_daily_brief.py`'s rendered brief output, in the existing 20-day-observation summary section
(near the existing `valid_observation_days`/`ready_to_expand` lines, around line 196-205). No new
config key; purely additive report content. Handle gracefully when these fields are absent from an
older-shaped `ledger_summary` (no crash — omit the line or show a placeholder).

## Acceptance Criteria

- [x] A fixture summary with `observation_start_date`/`excluded_before_start_count`/`next_action`
      set in `ledger_summary` produces a brief that includes all three values (unit-tested).
- [x] A fixture summary without these fields (e.g. an older-shaped payload) renders without
      KeyError — graceful fallback, not a crash (unit-tested).
- [x] Existing daily-brief tests pass byte-identical for their existing assertions.
- [x] No threshold tuning; no pre-2026-04-24 data; no SimNow order/cancel/send path changed; no
      `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

## Manual verification (claude-code's independent re-run, dev-round output not self-reported by kimi-code)

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` — 596 passed, 4
  deselected in 33.06s (up from A62's 594 baseline by exactly the 2 new tests this task adds:
  `test_render_daily_brief_includes_window_fields`,
  `test_render_daily_brief_missing_window_fields_no_crash`).
- `ruff check diagnostics/simnow_daily_brief.py tests/unit/test_simnow_daily_brief.py` — pass.
- `python tools/sync_check.py` — pass (version 4.4.0).
- `python tools/sync_check.py --root examples/czsc_strategy` — pass (version 0.2.2). synccheck:ignore
- `run_next_work.ps1 -Preflight` — 174 passed; preflight complete.
- Diff scope confirmed minimal: three additive lines in `build_daily_brief` render
  `observation_start_date`/`excluded_before_start_count`/`next_action` from `ledger_summary` with a
  `"无"` placeholder fallback (no crash) when absent. No changes to `simnow_run_summary.py` or
  `SAFE_LEDGER_SUMMARY_FIELDS` — purely a rendering fix, as scoped.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a61-simnow-observation-window-hardening.md` §"A63". Third task of
   the A61-A64 roadmap — read the design doc's Background for the full finding.
2. **Scope:** `examples/czsc_strategy/diagnostics/simnow_daily_brief.py` only (the
   `ledger_summary`-rendering block around lines 196-205). Do not touch
   `simnow_run_summary.py`/`SAFE_LEDGER_SUMMARY_FIELDS` (already correct — the fields are already in
   the whitelist and already flow into `ledger_summary`; this task is purely about rendering them),
   `chan_strategy/*.py`, or any SimNow order/cancel/send path.
3. **The fields already exist in the data** — this is purely a rendering gap, not a data-plumbing
   gap. Do not add new fields to `SAFE_LEDGER_SUMMARY_FIELDS` or `build_20d_report`; just read what's
   already there (`ledger_summary.get("observation_start_date")`, etc.) and print it.
4. **Test file:** `tests/unit/test_simnow_daily_brief.py` already exists — add cases there, do not
   create a duplicate.
5. **Guardrails (reject-on-violation):** no threshold tuning; no pre-2026-04-24 data; no SimNow
   order/cancel/send paths touched; no `GOAL PASSED`; existing brief tests' assertions must stay
   byte-identical (purely additive lines, not a reformat of existing ones).
6. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing.**
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A63 daily brief window fields implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-14 - A63 promoted from `docs/design/a61-simnow-observation-window-hardening.md`'s draft to
  an active HANDOFF task, started immediately after A62 reached `done` (codex accepted the round-2
  fix directly).
- 2026-07-14 - claude-code re-verified `simnow_daily_brief.py`'s rendering gap and confirmed via
  `simnow_run_summary.py`'s `SAFE_LEDGER_SUMMARY_FIELDS` whitelist that all three fields
  (`observation_start_date`, `excluded_before_start_count`, `next_action`) are already present in
  the `ledger_summary` data — this is purely a rendering fix, no data-plumbing change needed.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-14 | codex → claude-code | done → dev | A63 (daily brief window fields) promoted from SimNow-observation-window-hardening roadmap; handoff design->dev |
| 2026-07-14 | kimi-code → codex | dev → review | A63 daily brief window fields implemented |
| 2026-07-14 | codex → codex | review → done | A63 review accepted: daily brief window fields rendered; sandbox-sensitive unit/preflight items covered by recorded manual verification |
