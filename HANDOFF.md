---
task: A62 - Consistency Provenance Floor for Ledger Records
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-14
deliverables:
  - HANDOFF.md
  - docs/design/a61-simnow-observation-window-hardening.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

Second task of the 2026-07-14 SimNow-observation-window-hardening roadmap
(`docs/design/a61-simnow-observation-window-hardening.md` §"A62"), promoted immediately after A61
reached `done` (codex accepted on the first review round).

**Finding #2 (re-verified 2026-07-14 by claude-code):** `simnow_daily_monitor.py`'s
`compare_simnow_replay` (lines 286-355, confirmed unchanged) already gates on
`consistency_source_mode="require_captured"` (default, lines 290/303) — a real, existing safeguard
that returns `status="unavailable"` unless `source == "captured_session"`. But this only controls
what `compare_simnow_replay` itself computes at call time. `is_valid_observation`
(`diagnostics/simnow_observation_rules.py:6-18`, confirmed — full function read, only 13 lines)
simply checks `record.get("consistency", {}).get("matched") is True` with no way to verify that
`matched` value actually came from a `compare_simnow_replay` call under the safe mode, as opposed to
a hand-edited, legacy-format, or otherwise irregularly-produced ledger row
(`upsert_ledger`/`append_ledger`, `simnow_daily_monitor.py:568-594` — confirmed these have no
schema/provenance validation at write time; they just append/replace whatever dict is passed in). A
future manual or legacy-format record could set `consistency.matched=True` directly without ever
passing through the `require_captured` gate, and `build_20d_report`
(`simnow_daily_monitor.py:619-685`) would count it as a valid day with no way to detect the
provenance gap.

Full contract: `docs/design/a61-simnow-observation-window-hardening.md` §"A62 — Consistency
Provenance Floor for Ledger Records" (the authoritative design — this HANDOFF summarizes it).

## Goal

Add a provenance marker that `compare_simnow_replay` sets on every one of its return paths (lines
304, 318, 323, 332, 355 — confirmed the 5 return statements in the function body) — e.g.
`"verified": True` only when the comparison genuinely ran under `consistency_source_mode=
"require_captured"` with `source == "captured_session"` producing a real matched/mismatched
verdict (the "unavailable" early-return at line 304 should NOT set `verified=True`, since it didn't
actually compare anything). Then update `is_valid_observation`
(`diagnostics/simnow_observation_rules.py`) to require this marker in addition to
`consistency.matched is True` — a record missing the marker must not count as
`valid_observation` even if `matched=True`, and should be distinguishable from a genuine mismatch
(e.g. via a distinct reason string like `"consistency_provenance_unverified"`, not conflated with
`"event_surface_mismatch"` or other existing mismatch reasons). No new config key.

## Acceptance Criteria

- [x] A fixture record with `consistency.matched=True` but lacking the provenance marker is excluded
      from `valid_observation`/`matched_days` counting, with a distinct, identifiable reason
      (unit-tested).
- [x] A fixture record produced through `compare_simnow_replay`'s normal `require_captured` path
      counts as `valid_observation` exactly as before (byte-identical for this case).
- [x] Existing 20-day-report/ledger tests pass byte-identical for all previously-valid records.
- [x] No threshold tuning; no pre-2026-04-24 data; no SimNow order/cancel/send path changed; no
      `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a61-simnow-observation-window-hardening.md` §"A62". Second task of
   the A61-A64 roadmap — read the design doc's Background section for the full finding.
2. **Scope:** `examples/czsc_strategy/diagnostics/simnow_daily_monitor.py`
   (`compare_simnow_replay`'s 5 return points; `is_valid_observation` is actually in
   `simnow_observation_rules.py`, a separate file — check both). Do not touch
   `chan_strategy/*.py`, any SimNow order/cancel/send path, or `consistency_source_mode`'s own
   existing default/semantics (this task adds a floor ON TOP of it, not a replacement).
3. **`is_valid_observation` is short and fully readable** — it's at
   `diagnostics/simnow_observation_rules.py:6-18`, only 13 lines, already quoted in full above in
   the Background section. Read it directly rather than guessing its shape.
4. **`compare_simnow_replay`'s 5 return statements** are at lines 304 (unavailable —
   `consistency_source_mode` gate rejected the source), 318 (matched=True, no-actionable-events
   short-circuit after a `replay_unavailable` check), 323 (matched=False, replay unavailable), 332
   (matched=True, no-actionable-events-on-either-side), and 355 (the main comparison result). Only
   304 represents "never actually compared" — the marker should reflect that distinction, not just
   blindly set `verified=True` on every return.
5. **Distinguish "provenance unverified" from "genuine mismatch" in the reason text** — a human or
   downstream agent reading the ledger should be able to tell "this day never proved consistency
   through the safe path" apart from "this day proved inconsistency." Do not reuse
   `"event_surface_mismatch"` or other existing mismatch reason strings for this new case.
6. **Guardrails (reject-on-violation):** no threshold tuning; no pre-2026-04-24 data; no SimNow
   order/cancel/send paths touched; no `GOAL PASSED`; a record produced through the normal
   `require_captured` path must count as valid exactly as before (no false negatives introduced).
7. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing** — please do NOT omit this section; every prior task in this new
   roadmap (A61) and most of the previous A55-A60 wave omitted it in their first dev round, needing
   claude-code to add it before review — including it yourself saves a round-trip.
8. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A62 consistency provenance floor implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Review Findings (codex, 2026-07-14)

Reject back to dev:

1. `build_20d_report` still counts an unverified `consistency.matched=True` ledger row in
   `consistency_matched_days`. The A62 acceptance criterion requires a fixture record with
   `consistency.matched=True` but no provenance marker to be excluded from both
   `valid_observation` and `matched_days` counting. Current behavior excludes it from
   `valid_observation_days` but still increments `consistency_matched_days`.
   Reproduction:
   `build_20d_report([verified matched row, unverified matched row], min_days=2)` returns
   `valid_observation_days == 1` and `consistency_matched_days == 2`.
   Update report counting and tests so unverified matched rows do not count as matched days for
   the A62 floor.

Review notes:

- `python tools/sync_check.py`, `python tools/sync_check.py --root examples/czsc_strategy`, and
  the scoped `ruff check` command all passed in codex review.
- The focused pytest command hit the documented sandbox limitation:
  `PermissionError [WinError 5]` while pytest scanned
  `C:\Users\Admin\AppData\Local\Temp\pytest-of-Admin`; per `.synccheck.yml`, use the Manual
  Verification block below for the unit/preflight acceptance items unless the environment has been
  relogged/rebooted and pytest tmp-path setup succeeds.

## Manual Verification (natively-run)

```text
.venv_new\Scripts\python.exe -m pytest examples\czsc_strategy\tests\unit -q -m "not realdb"
# 594 passed, 4 deselected, 2 warnings in 31.50s

.venv_new\Scripts\python.exe tools\sync_check.py
# [SYNC-CHECK] PASS: 版本与文档一致。

.venv_new\Scripts\python.exe tools\sync_check.py --root examples\czsc_strategy
# [SYNC-CHECK] PASS: 版本与文档一致。

powershell -ExecutionPolicy Bypass -File examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
# Preflight complete; live SimNow capture was not requested

ruff check examples\czsc_strategy\diagnostics\simnow_daily_monitor.py examples\czsc_strategy\diagnostics\simnow_observation_rules.py examples\czsc_strategy\diagnostics\simnow_action_summary.py examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py examples\czsc_strategy\tests\unit\test_simnow_ledger_summary.py
# All checks passed!
```

Guardrails held: no threshold tuning; no pre-2026-04-24 data; no SimNow order/cancel/send paths
modified; no `GOAL PASSED`.

## Decision Log

- 2026-07-14 - A62 promoted from `docs/design/a61-simnow-observation-window-hardening.md`'s draft to
  an active HANDOFF task, started immediately after A61 reached `done` (codex accepted on the first
  review round).
- 2026-07-14 - claude-code re-verified `is_valid_observation` (13 lines, fully read) and
  `compare_simnow_replay`'s 5 return statements (lines 304/318/323/332/355) — all unchanged since
  the roadmap was designed. Identified that only the line-304 early return represents "no real
  comparison happened," informing the marker's exact semantics for dev.
- 2026-07-14 - kimi-code implemented the provenance floor: `compare_simnow_replay` now emits
  `consistency.verified`, and `is_valid_observation`/`valid_observation_reason` require it for any
  `matched=True` record. `_pass_gaps` surfaces the distinct reason
  `consistency_provenance_unverified` in action recommendations.
- 2026-07-14 - codex review rejected the first dev round because `build_20d_report` still counted
  unverified `consistency.matched=True` rows in `consistency_matched_days`. kimi-code fixed
  `build_20d_report` to require `consistency.verified is True` for the matched-day count and
  updated `test_20d_report_excludes_unverified_matched_record` accordingly.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-14 | codex → claude-code | done → dev | A62 (consistency provenance floor) promoted from SimNow-observation-window-hardening roadmap; handoff design->dev |
| 2026-07-14 | kimi-code → codex | dev → review | A62 consistency provenance floor implemented |
| 2026-07-14 | codex → kimi-code | review → dev | 打回: unverified matched rows still count in consistency_matched_days |
| 2026-07-14 | kimi-code → codex | dev → review | A62 consistency provenance floor implemented |
