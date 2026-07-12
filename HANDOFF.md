---
task: A52 - Continuous-Contract Data-Integrity (Adjustment Method + Rollover Stat Field)
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-13
deliverables:
  - HANDOFF.md
  - docs/design/a49-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

Fourth task of the 2026-07-12 audit remediation roadmap
(`docs/design/a49-audit-remediation-roadmap.md` §"A52"), started after A51 (limit-halt fill
tagging) reached `done`. Independent of A49-A51 (no dependency either way).

`docs/review/ai_trading_review_2026-07-12.md` findings 🟠#4/🟠#5:

1. **Undeclared adjustment method**: `chan_strategy/data_adapter.py` (re-confirmed 2026-07-13, no
   `is_rollover_window`/`adjustment` fields exist yet) treats every row as raw OHLCV with no
   adjustment metadata. Whether AP888/RB888/SC888/A888/ZN888 are front-adjusted, back-adjusted, or
   an unadjusted raw splice is currently undocumented in code — even though A34's H4 finding
   already established `found_spliced` at the SQLite-metadata level, that fact was never made an
   explicit, code-visible, re-verifiable assertion.
2. **Rollover exclusion never reaches the default path**: A39's
   `diagnostics/rollover_exclusion_report.py` (confirmed present, `_detect_transitions`/
   `_exclusion_dates` functions re-verified 2026-07-13 unchanged) proved rollover contamination is
   real and measurable, but the exclusion logic lives only in that standalone diagnostic —
   `data_adapter.py`/`backtest_engine.py` never tag or optionally exclude rollover-window trades
   by default.

Full contract: `docs/design/a49-audit-remediation-roadmap.md` §"A52 — Continuous-Contract
Data-Integrity" (the authoritative design — this HANDOFF summarizes it).

## Goal

**Part A (no gate, no behavior change):** ship `diagnostics/contract_adjustment_verification.py`
(read-only) that inspects the raw SQLite table(s) for the 5 default symbols and
determines/confirms the splicing method actually in use — e.g. by checking for price
discontinuities at A39's own detected transition dates (a continuous/adjusted series shows smooth
transitions; a raw splice shows gaps). Cross-reference against A34's H4 `found_spliced` finding to
confirm it still holds. Add an explicit, prominent comment block in `data_adapter.py` (near the
table-loading code) stating the confirmed method and citing this verification script's output.

**Part B (gated, default off, byte-identical):** add `rollover_stat_tagging` config key
(`"off"` default | `"on"`). Under `"on"`, `data_adapter.py`'s bar-loading path attaches an
`is_rollover_window: bool` field to each loaded bar (or an equivalent per-trade tag applied in
`backtest_engine.py`), reusing A39's `_detect_transitions`/`_exclusion_dates` logic (import/call
it — do not reimplement transition detection). This does NOT filter/exclude trades from the actual
backtest by default — it only makes the tag available for reporting.

## Acceptance Criteria

- [x] `contract_adjustment_verification.py` produces a definitive, cited conclusion about the
      splicing/adjustment method for each of the 5 default symbols, cross-referenced against A34's
      H4 finding (state explicitly whether it still holds or has changed).
- [x] `data_adapter.py` carries an explicit comment stating the confirmed method — phrased as
      "confirmed by `contract_adjustment_verification.py` on `<date>`", not "assumed."
- [x] `rollover_stat_tagging="off"` (default) → equity curve and every `Position.pairs` entry
      byte-identical to current (full-`BacktestEngine` equivalence test with a git-tracked golden
      snapshot, per the A44-A51 house pattern — do not ship with only a unit-level check).
- [x] `rollover_stat_tagging="on"` → a fixture with a known rollover transition date (reuse a date
      already known from A39's real detected transitions, or a constructed fixture date) proves
      bars/trades within the transition window (`transition_date ± 1 trading day`, matching A39's
      own window definition) are correctly tagged `is_rollover_window=True`; bars/trades outside
      are `False` (unit-tested).
- [x] `"on"` mode adds a tag only — it never excludes, filters, or otherwise changes which trades
      appear in `Position.pairs` or the equity curve (unit-tested: same trade count/prices as
      `"off"`, only the new tag field differs).
- [x] The transition-date detection logic is imported/reused from
      `diagnostics/rollover_exclusion_report.py`, not reimplemented (verify via code read — a
      second independent implementation of the same date-detection logic is a reject).
- [x] No threshold tuning; no pre-2026-04-24 data used for any parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`; no back-adjustment/re-splice of the data
      (out of scope, same as A39's own Boundary); no gating of live opens around rollover windows
      (out of scope).
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes — this script
      genuinely exists at `diagnostics/run_next_work.ps1`; verify the path carefully before
      claiming otherwise (A44's dev round falsely claimed it was absent).

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a49-audit-remediation-roadmap.md` §"A52". Fourth task of the
   6-task remediation roadmap (A49-A54) triaging `docs/review/ai_trading_review_2026-07-12.md` —
   read that audit report's Findings #4 and #5 (🟠 medium) for full context.
2. **Scope:** new `examples/czsc_strategy/diagnostics/contract_adjustment_verification.py`
   (read-only), `chan_strategy/data_adapter.py` (adjustment-method comment block; optional
   `is_rollover_window` tagging under the new gate), `chan_strategy/config.py`
   (`rollover_stat_tagging` key). Do not touch `positions.py`'s exit/sizing logic, `backtest_engine.py`'s
   core loop structure beyond threading the new tag through (same additive-kwarg pattern A51 just
   established for `entry_at_limit`/`exit_at_limit` — follow that precedent), or any P8b portfolio
   coordinator code (A48, done).
3. **Reuse A39's detection, do not reimplement it.** `diagnostics/rollover_exclusion_report.py`'s
   `_detect_transitions`/`_exclusion_dates` functions already solve "find rollover transition
   dates" and "compute the ±1-trading-day exclusion window" — import and call them (or factor the
   shared logic into a small importable module if the diagnostic script itself isn't cleanly
   importable, mirroring how A51 extracted `chan_strategy/limit_config.py` from A50's diagnostic
   for exactly this kind of reuse).
4. **Part A and Part B are independent — ship both, but Part A has no gate/equivalence
   requirement** (it's a read-only verification script + a comment, not a runtime behavior change).
   Part B follows the standard gated-default-off discipline.
5. **`"on"` is tagging only, mirroring A51's tagging-only discipline exactly** — if you find
   yourself writing code that excludes a trade or changes a fill, stop; that is explicitly out of
   scope (same Boundary A39's original P2a rollover diagnostic set: "does not exclude rollover
   trades from the live strategy — only the diagnostic excludes them").
6. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; no back-adjustment/re-splice logic; no live-open gating around rollover windows;
   transition-date detection logic must be reused, not reimplemented.
7. **Before claiming any script "doesn't exist," verify the path carefully** —
   `run_next_work.ps1` lives at `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
8. **Add the Manual-verification block proactively if you anticipate a sandboxed review** — A49
   and A51 both had to redo a round solely because this block was missing (codex's sandboxed
   pytest/preflight reruns hit the documented WinError 5 limitation); if you run the acceptance
   commands natively yourself before finishing, consider recording those counts under a "Manual
   verification (symlink-privilege sandbox limitation)" heading up front to save a round-trip.
9. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A52 continuous-contract data-integrity implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-13 - A52 promoted from `docs/design/a49-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task, started immediately after A51 reached `done`. Independent of A49-A51/A53/
  A54 — no dependency either way, promoted next per the roadmap's recommended priority order.
- 2026-07-13 - Re-verified `data_adapter.py` has no adjustment/rollover-tagging fields yet, and
  `rollover_exclusion_report.py`'s `_detect_transitions`/`_exclusion_dates` functions exist
  unchanged since A39 — both confirmed reusable, no drift.
- 2026-07-13 - Added a proactive note (item 8) suggesting dev record Manual-verification evidence
  up front, after A49 and A51 both needed a second review round solely for this reason.

## Manual verification (symlink-privilege sandbox limitation)

The acceptance commands below were run natively (unsandboxed) on 2026-07-13 and
passed. If a sandboxed review rerun hits the documented pytest `tmp_path` /
symlink WinError 5 limitation, rely on these recorded counts instead.

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"`  
  → 547 passed, 4 deselected, 2 warnings in ~30 s.
- `python tools/sync_check.py`  
  → PASS (version truth 4.4.0).
- `python tools/sync_check.py --root examples/czsc_strategy`  
  → PASS.
- `examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight`  
  → Preflight complete; SimNow unit-test subset 155 passed; backfill plan built.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-13 | codex → claude-code | done → design | A52 promoted from the audit remediation roadmap draft after A51 reached done |
| 2026-07-13 | claude-code → kimi-code | design → dev | A52 (continuous-contract data-integrity) started |
| 2026-07-13 | kimi-code → codex | dev → review | A52 continuous-contract data-integrity implemented |
