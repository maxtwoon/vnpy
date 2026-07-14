---
task: A62 - Consistency Provenance Floor for Ledger Records
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

- [ ] A fixture record with `consistency.matched=True` but lacking the provenance marker is excluded
      from `valid_observation`/`matched_days` counting, with a distinct, identifiable reason
      (unit-tested).
- [ ] A fixture record produced through `compare_simnow_replay`'s normal `require_captured` path
      counts as `valid_observation` exactly as before (byte-identical for this case).
- [ ] Existing 20-day-report/ledger tests pass byte-identical for all previously-valid records.
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow order/cancel/send path changed; no
      `GOAL PASSED`.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

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

## Decision Log

- 2026-07-14 - A62 promoted from `docs/design/a61-simnow-observation-window-hardening.md`'s draft to
  an active HANDOFF task, started immediately after A61 reached `done` (codex accepted on the first
  review round).
- 2026-07-14 - claude-code re-verified `is_valid_observation` (13 lines, fully read) and
  `compare_simnow_replay`'s 5 return statements (lines 304/318/323/332/355) — all unchanged since
  the roadmap was designed. Identified that only the line-304 early return represents "no real
  comparison happened," informing the marker's exact semantics for dev.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-14 | codex → claude-code | done → dev | A62 (consistency provenance floor) promoted from SimNow-observation-window-hardening roadmap; handoff design->dev |
