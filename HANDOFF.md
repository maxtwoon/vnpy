---
task: A61 - Captured-Session Surface: Workflow-Owned Filter + account_contamination Wiring
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

First task of the 2026-07-14 SimNow-observation-window-hardening roadmap
(`docs/design/a61-simnow-observation-window-hardening.md` §"A61"), started immediately after the
sub-agent's second SimNow-observation audit (74/100, "conditional go") found 4 open findings, none
individually blocking but the first two directly affecting whether a day can be trusted as a valid
observation day.

**Finding #1 (re-verified 2026-07-14 by claude-code, line numbers confirmed unchanged since the
design doc was written minutes earlier):** `simnow_daily_capture.py`'s capture payload separates
`raw.*` (full CTP account callbacks, unfiltered — comment at lines 293-296 explicitly says
`raw.positions` "must not be compared directly with replay portfolio exposures") from `captured.*`
(intended to be "the only trades/positions/orders that may be used to prove live-session agreement
with replay," per the comment at lines 299-301) — but `captured.positions`/`captured.trades`
themselves (lines 302-306) are simply `list(state.positions.values())` / the raw trade list, **not
filtered to workflow-owned symbols**. `simnow_strategy_surface.py`'s
`build_strategy_surface_from_captured_session` (lines 85-107, confirmed) converts
`captured.trades`/`captured.positions` into the comparison surface unchanged — any position or
trade on a symbol the workflow doesn't itself trade (genuine external SimNow-account activity)
flows straight into `compare_simnow_replay`'s `positions`/`trades` comparison categories
(`simnow_daily_monitor.py:337-354`) and can produce a false `extra_in_simnow` mismatch, incorrectly
failing consistency for a day the strategy itself behaved correctly.
`extract_account_contamination` (`simnow_run_summary.py:107-129`) already exists and correctly
reports external activity as "external audit evidence only, not strategy PnL" — but it reads from
`raw.*` independently; it is not currently wired as the destination for symbols filtered *out* of
the captured-session surface.

Full contract: `docs/design/a61-simnow-observation-window-hardening.md` §"A61 — Captured-Session
Surface: Workflow-Owned Filter + `account_contamination` Wiring" (the authoritative design — this
HANDOFF summarizes it).

## Goal

In `build_strategy_surface_from_captured_session` (or a helper it calls), filter
`captured["trades"]`/`captured["positions"]` to only those rows whose `symbol` matches a
workflow-owned contract — the set of `contract["symbol"]` values from
`capture["meta"]["contract_map"]` (already available on the capture payload). Rows that don't match
must NOT enter the comparison surface's `trades`/`positions`; route the filtered-out rows so they
remain visible via the existing `account_contamination` reporting path (`simnow_run_summary.py`'s
`extract_account_contamination`), not silently dropped — every captured event must be accounted for
as either "workflow-owned, compared" or "external, contamination-only." No new config key.

## Acceptance Criteria

- [x] A fixture with a captured position on a symbol NOT in `contract_map` produces a comparison
      surface (`positions`) that does not include that row, and `account_contamination`'s
      `active_positions`/`position_symbols` count reflects it instead (unit-tested).
- [x] The same fixture for a captured trade (not just position) on a non-workflow symbol.
- [x] A fixture with only workflow-owned positions/trades is completely unaffected — existing
      `test_simnow_strategy_surface.py` tests still pass byte-identical.
- [x] `compare_simnow_replay`'s existing consistency-matching behavior for workflow-owned events is
      unchanged (no new false negatives introduced by the filter itself).
- [x] No threshold tuning; no pre-2026-04-24 data; no SimNow order/cancel/send path changed; no
      `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

## Manual verification (claude-code's independent re-run, dev-round output not self-reported by kimi-code)

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` — 589 passed, 4
  deselected in 31.80s (up from A60's 586 baseline by exactly the 3 new tests this task adds:
  `test_build_strategy_surface_filters_external_position_to_contamination`,
  `test_build_strategy_surface_filters_external_trade_to_contamination`,
  `test_build_strategy_surface_workflow_owned_events_unaffected`).
- `ruff check diagnostics/simnow_strategy_surface.py tests/unit/test_simnow_strategy_surface.py` —
  pass.
- `python tools/sync_check.py` — pass (version 4.4.0).
- `python tools/sync_check.py --root examples/czsc_strategy` — pass (version 0.2.2). synccheck:ignore
- `run_next_work.ps1 -Preflight` — 167 passed; preflight complete.
- Diff scope confirmed minimal and correct: `_workflow_owned_symbols` extracts the enabled-contract
  symbol set from `capture["meta"]["contract_map"]` (returns `None` — "keep everything" — when the
  key is absent, a safe backward-compatible fallback for pre-A61 captures); `_filter_captured_events`
  splits `captured.trades`/`captured.positions` into owned/external before they reach the
  comparison surface. Filtered rows are NOT dropped: `account_contamination`
  (`simnow_run_summary.py`) already independently scans `raw.*` (the same unfiltered source
  `captured.*` is derived from), so external symbols are automatically counted there — no direct
  code-level wiring was needed between the two, and the new tests explicitly prove this by setting
  `capture["raw"][...]` to include the external row and asserting `account_contamination` reports
  it. `filtered_trades_count`/`filtered_positions_count`/`filtered_symbols` were added to the
  surface's own `meta` for direct traceability. Symbol matching is case-insensitive (tested with
  lowercase contract-map entries against uppercase captured rows) and correctly excludes
  `enabled: False` contract-map entries. `chan_strategy/*.py` and all SimNow order/cancel/send paths
  are untouched.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a61-simnow-observation-window-hardening.md` §"A61". First task of a
   new 4-task roadmap (A61-A64) triaging the 2026-07-14 sub-agent SimNow-observation audit's open
   findings — read the design doc's full Background section for context.
2. **Scope:** `examples/czsc_strategy/diagnostics/simnow_strategy_surface.py` (the filter) and
   possibly `simnow_daily_capture.py`/`simnow_run_summary.py` (wiring the filtered-out rows to
   `account_contamination` if the current call graph needs a small adjustment to pass them
   through). Do not touch `chan_strategy/*.py` (no trading logic here — this is purely a
   diagnostics/monitoring-script fix), any SimNow order/cancel/send path, or `raw.*`'s own contents.
3. **`contract_map` structure:** `capture["meta"]["contract_map"]` is
   `{research_symbol: {"symbol": "AP888", "exchange": "CZCE", "enabled": True, ...}}` (built by
   `load_contract_map`/`contract_subscriptions` in `simnow_daily_capture.py`). The workflow-owned
   symbol set is the `item["symbol"]` values across enabled entries. Confirm the exact vt_symbol
   format used in captured CTP position/trade rows (may need case-insensitive or exchange-suffix-
   aware matching — read `_research_symbol_key`-style precedent elsewhere in the codebase if a
   normalization mismatch surfaces during testing, but do not import trading-logic modules into
   this diagnostics script unnecessarily).
4. **Every captured event must be traceable** — do not just drop external rows; route them so
   `account_contamination`'s reporting reflects them. If the current call graph makes direct wiring
   awkward, a minimal, clearly-commented adjustment to how `enrich_capture_json`/`make_record`/
   `extract_account_contamination` connect is acceptable, but keep the change scoped to this one
   concern.
5. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection; no
   pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; workflow-owned event comparison behavior must stay byte-identical.
6. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing** — this consistently correlates with one-round review acceptance
   across the A55-A60 wave.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A61 captured-session workflow-owned filter implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-14 - A61 promoted from `docs/design/a61-simnow-observation-window-hardening.md`'s draft to
  an active HANDOFF task, started immediately after the roadmap was designed. First task of the
  A61-A64 SimNow-observation-window-hardening wave, prioritized first per the user's own instruction
  (directly affects whether a valid-observation day can be trusted).
- 2026-07-14 - claude-code re-verified all cited line numbers in
  `simnow_strategy_surface.py`/`simnow_daily_capture.py` are unchanged since the design doc was
  written minutes earlier — no drift.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-14 | codex → claude-code | done → dev | A61 (captured-session workflow-owned filter) promoted from SimNow-observation-window-hardening roadmap; handoff design->dev |
| 2026-07-14 | kimi-code → codex | dev → review | A61 captured-session workflow-owned filter implemented |
| 2026-07-14 | codex → codex | review → done | A61 review passed |
