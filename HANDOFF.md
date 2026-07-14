---
task: A64 - Run-Summary promotion Sub-Section: Carry Window-Filter Metadata
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-14
deliverables:
  - HANDOFF.md
  - docs/design/a61-simnow-observation-window-hardening.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

Fourth and final task of the 2026-07-14 SimNow-observation-window-hardening roadmap
(`docs/design/a61-simnow-observation-window-hardening.md` §"A64"), promoted immediately after A63
reached `done` (codex accepted on the first review round). Completing this task finishes the entire
A61-A64 roadmap.

**Finding #4 (re-verified 2026-07-14 by claude-code, exact function/field names confirmed by direct
read, per the design doc's own requirement not to guess):** `simnow_run_summary.py`'s
`build_run_summary` function (lines 230-271) builds a `"promotion"` sub-section (lines 263-269)
from its `promotion_summary` parameter — which is populated at the CLI entry point (line 324) by
`decide_promotion(ledger_records, observation_start_date=start_date)`, imported from
`simnow_promotion_decision.py`. `decide_promotion`'s own output dict already carries
`observation_start_date`/`excluded_before_start_count` (confirmed present in that module's
`write_report`/summary-building logic, consumed by the A63-fixed daily brief via the separate
`ledger_summary` path). But `build_run_summary`'s `"promotion"` sub-section only copies 5 specific
fields from `promotion_summary` — `ready_to_expand`, `valid_observation_days`, `observed_days`,
`promotion_blockers`, `top_blocking_actions` — and does NOT include
`observation_start_date`/`excluded_before_start_count`, even though `promotion_summary` (the
`decide_promotion` return value) already has them available. A future agent reading only the
narrower `promotion` sub-section (a plausible read, since it most directly answers "can we promote
yet") could lose the window basis entirely and misinterpret `valid_observation_days` counts without
knowing they already exclude pre-window rows — the `ledger_summary` sub-section (fixed by A63) has
this context, but `promotion` does not.

Full contract: `docs/design/a61-simnow-observation-window-hardening.md` §"A64 — Run-Summary
`promotion` Sub-Section: Carry Window-Filter Metadata" (the authoritative design — this HANDOFF
summarizes it).

## Goal

Add `observation_start_date`/`excluded_before_start_count` to `build_run_summary`'s `"promotion"`
sub-section (lines 263-269), sourced from the same `promotion` (i.e. `promotion_summary`) dict
already available in that function — no new parameter, no new config key, purely additive metadata
propagation mirroring the existing `_safe_ledger_summary` pattern's spirit (copy known-safe fields
from an already-available dict).

## Acceptance Criteria

- [ ] A fixture `promotion_summary` (i.e. what `decide_promotion` would return) with
      `observation_start_date`/`excluded_before_start_count` set produces a `build_run_summary`
      output whose `"promotion"` sub-section also carries them (unit-tested).
- [ ] Existing run-summary tests pass byte-identical for their existing assertions.
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow order/cancel/send path changed; no
      `GOAL PASSED`.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a61-simnow-observation-window-hardening.md` §"A64". Fourth and
   FINAL task of the A61-A64 roadmap — completing this closes out the entire
   SimNow-observation-window-hardening wave.
2. **Scope:** `examples/czsc_strategy/diagnostics/simnow_run_summary.py`'s `build_run_summary`
   function only (the `"promotion"` dict literal at lines 263-269). Do not touch
   `simnow_promotion_decision.py`/`decide_promotion` (already correct — it already produces these
   fields; this task only widens what `build_run_summary` copies from it),
   `simnow_daily_brief.py`/`ledger_summary` (already fixed by A63, separate path), `chan_strategy/
   *.py`, or any SimNow order/cancel/send path.
3. **Exact field names confirmed by direct read** (per this roadmap's own standing instruction not
   to guess): the function is `build_run_summary` (not some other name), the sub-section key is
   literally `"promotion"`, and the source is the `promotion` local variable (from the
   `promotion_summary` parameter, defaulting to `{}`). Add
   `promotion.get("observation_start_date", "")`/`promotion.get("excluded_before_start_count", 0)`
   (or similar sensible defaults matching the existing fields' style in that same dict literal).
4. **Test file:** `tests/unit/test_simnow_run_summary.py` already exists — add cases there, do not
   create a duplicate.
5. **Guardrails (reject-on-violation):** no threshold tuning; no pre-2026-04-24 data; no SimNow
   order/cancel/send paths touched; no `GOAL PASSED`; existing run-summary tests' assertions must
   stay byte-identical (purely additive fields, not a reformat of existing ones).
6. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing** — please do NOT omit this section; most tasks in this roadmap
   (A61, A63) omitted it in their first dev round, needing claude-code to add it before review —
   A62 included it proactively and it helped nothing go unnoticed there either way, but including it
   yourself still saves a round-trip on the mechanical side.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A64 run-summary promotion window metadata implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. **This is the last task in the
   roadmap** — after this reaches `done`, the entire A61-A64 wave is complete.

## Decision Log

- 2026-07-14 - A64 promoted from `docs/design/a61-simnow-observation-window-hardening.md`'s draft to
  an active HANDOFF task, started immediately after A63 reached `done` (codex accepted on the first
  review round). This is the final task of the A61-A64 roadmap.
- 2026-07-14 - claude-code confirmed the exact function/field names by direct read (per the design
  doc's own instruction not to guess): `build_run_summary` (`simnow_run_summary.py:230-271`)
  produces the `"promotion"` sub-section (lines 263-269) from its `promotion` local variable
  (sourced from `promotion_summary`, populated at the CLI entry point by `decide_promotion` from
  `simnow_promotion_decision.py`). The sub-section currently copies only 5 fields, omitting
  `observation_start_date`/`excluded_before_start_count` which `decide_promotion`'s own output
  already carries.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-14 | codex → claude-code | done → dev | A64 (run-summary promotion window metadata) promoted from SimNow-observation-window-hardening roadmap; handoff design->dev |
