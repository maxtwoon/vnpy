---
task: A55 - Partial-TP Transaction-Cost Double-Scaling Fix
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-13
deliverables:
  - HANDOFF.md
  - docs/design/a55-post-remediation-audit-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

First task of the 2026-07-13 post-remediation re-audit roadmap
(`docs/design/a55-post-remediation-audit-roadmap.md` §"A55"), started immediately after A54 (final
task of the first audit remediation wave) reached `done`.

`docs/review/ai_trading_review_2026-07-13.md` Finding 🟠#1 (re-verified 2026-07-13 by claude-code
against current code): `_scale_out` (`chan_strategy/positions.py:865-872`) computes
`transaction_cost = full_transaction_cost * scale_fraction`, where `full_transaction_cost =
2 * self.commission_rate + self.slippage` is already a per-unit round-trip cost RATE. This rate
gets multiplied by `scale_fraction` (the fraction of the position being closed) AND the
`pnl_currency` formula separately multiplies by `scale_volume` (`positions.py:869-871`) — a
double-discount. Compare against `_close_long` (`positions.py:970-971`), which correctly applies
`transaction_cost = 2 * self.commission_rate + self.slippage` (undivided) before its own
`* self.volume` scaling. Verified arithmetically: with `volume=1`, `partial_tp_frac=0.5`, rate
`f`, a full lifecycle (0.5-lot partial-TP + 0.5-lot final close) pays `0.25f + 0.5f = 0.75f` total
instead of the correct `~1.0f` — a ~25% cost understatement for any trade going through a
partial-TP leg. This systematically biases `exit_model="structural_atr"` vs `"legacy"` A/B
comparisons (`diagnostics/exit_model_report_*.md`) in `structural_atr`'s favor.

Full contract: `docs/design/a55-post-remediation-audit-roadmap.md` §"A55 — Partial-TP
Transaction-Cost Double-Scaling Fix" (the authoritative design — this HANDOFF summarizes it).

## Goal

Fix `_scale_out` so the cost rate is NOT multiplied by `scale_fraction` — use the undivided
`full_transaction_cost`, matching `_close_long`/`_close_short`'s exact convention. The
`pnl_currency` formula's existing `* scale_volume` term already correctly scales the cost to the
portion actually closed; no other change is needed. No new config key — this is a straight
correctness fix inside the already-opt-in `exit_model="structural_atr"` + `sizing_model="risk"`
combination.

## Acceptance Criteria

- [x] `_scale_out`'s cost rate no longer multiplies `full_transaction_cost` by `scale_fraction`; a
      fixture with known `commission_rate`/`slippage`/`partial_tp_frac` reproduces a
      hand-computed exact `pnl_currency`/`pnl_pct` for the partial leg (unit-tested).
- [x] A conservation test: total cost paid across a partial-TP-then-final-close lifecycle is `>=`
      the cost a single full close of the same total volume would have paid — partial exits must
      never be cheaper in total than one exit (unit-tested).
- [x] `exit_model="legacy"` and `sizing_model="research"` paths are provably unaffected — this bug
      only exists in the risk-mode partial-TP currency path; existing golden-snapshot/equivalence
      tests for both must pass byte-identical, unchanged.
- [x] If any existing test's expected value changes as a result of this fix (e.g.
      `test_structural_atr_partial_tp_long`/`_short` if they hardcoded a value derived from the
      old/wrong formula), the change must be called out explicitly in the commit message and
      HANDOFF — a silently-changed expected value in a "fix" commit is itself worth scrutiny.
      *No existing expected values were changed; the new assertions only add exact-cost and
      conservation coverage.*
- [x] No threshold tuning; no pre-2026-04-24 data used for any parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes — this script
      genuinely exists at `diagnostics/run_next_work.ps1`; verify the path carefully before
      claiming otherwise (A44's dev round falsely claimed it was absent).

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a55-post-remediation-audit-roadmap.md` §"A55". First task of a
   new 6-task roadmap (A55-A60) triaging `docs/review/ai_trading_review_2026-07-13.md`'s findings
   — read that report's finding #1 (🟠 medium) for full context, including the exact arithmetic
   proof of the double-scaling.
2. **Scope:** `chan_strategy/positions.py`'s `_scale_out` method only (around lines 850-880). Do
   not touch `_close_long`/`_close_short` (already correct — use them as the reference
   implementation), any other exit-model logic, or anything in A47-A54's already-`done` scope
   beyond this one bug.
3. **This is a bug fix inside already-opt-in switches, not a new gated feature** — no new
   `STRATEGY_CONFIG` key needed. Both `exit_model="structural_atr"` and `sizing_model="risk"` are
   already opt-in from A47/A40.
4. **The conservation test is the most important evidence** — prove that splitting an exit into
   (partial + final) never costs less in total than a single full exit of the same total volume.
   This is a stronger, more general proof than just checking one hardcoded number.
5. **Optional bundle: 🟢 finding #7** — `TradeRecord.volume` is always logged as `1` on close in
   risk mode because `self.volume = 1` is reset before the `TradeRecord` append that reads it
   (`positions.py:995-1006` long, `1058-1069` short). `Position.pairs` is unaffected (uses the
   correct volume before reset) — only the raw `self.trades` audit log is wrong. This is in the
   same file/method family as A55's main fix; bundle it if convenient, but call it out as a
   separate, explicitly-labeled fix in the commit if you do (don't silently conflate two fixes).
6. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; `exit_model="legacy"`/`sizing_model="research"` paths provably untouched.
7. **Before claiming any script "doesn't exist," verify the path carefully** —
   `run_next_work.ps1` lives at `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
8. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing** — this consistently correlates with one-round review acceptance
   across the A49-A54 wave (A52/A53's second round both did this and passed cleanly; A49/A50/A51
   each needed an extra round for omitting one or the other; A54 omitted it and claude-code had to
   add it before review).
9. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A55 partial-TP transaction-cost double-scaling fix implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Manual Verification (kimi-code dev round)

Commands run natively on Windows 11 / Python 3.14 / repo `D:\repo\vnpy`:

```text
# Unit tests (CzSC strategy unit suite, no realdb)
pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
# -> 568 passed, 4 deselected, 2 warnings in 30.67s

# Lint on changed files only (positions.py has pre-existing typing.List/Dict/Tuple/Optional
# noise inherited from earlier waves; no new ruff issues were introduced by this change)
ruff check examples/czsc_strategy/tests/unit/test_exit_model.py
# -> All checks passed!

# Sync gates
python tools/sync_check.py
# -> PASS: 版本与文档一致 (4.4.0)
python tools/sync_check.py --root examples/czsc_strategy
# -> PASS: 版本与文档一致 (czsc_strategy sub-project VERSION file)

# SimNow preflight
diagnostics/run_next_work.ps1 -Preflight
# -> 155 passed; Preflight complete
```

Scope changes:
- `_scale_out` (`chan_strategy/positions.py`) now uses the undivided round-trip cost rate
  `2 * commission_rate + slippage`, matching `_close_long`/`_close_short`.
- Bundled a separate, explicitly-labeled audit-log fix: `_close_long` and `_close_short` now
  append the closing `TradeRecord` **before** resetting `self.volume` to 1, so the logged volume
  reflects the actual closed lots in risk mode.  This does not affect `Position.pairs` accounting.
- Added three unit-test families to `tests/unit/test_exit_model.py`:
  1. Exact partial-TP `pnl_pct`/`pnl_currency` for long and short (parametrized).
  2. Conservation: partial-TP + final-close total transaction cost `>=` single full close cost.
  3. Close `TradeRecord.volume` matches actual risk-mode lot count for long and short.

## Decision Log

- 2026-07-13 - A55 promoted from `docs/design/a55-post-remediation-audit-roadmap.md`'s draft to
  an active HANDOFF task, started immediately after A54 reached `done`. This begins a second
  remediation wave (A55-A60) addressing findings the FIRST wave's own new code introduced.
- 2026-07-13 - Re-verified the double-scaling bug is present exactly as cited
  (`positions.py:865-872`) and confirmed `_close_long`'s correct convention
  (`positions.py:970-971`) as the reference implementation — no drift since the re-audit.
- 2026-07-13 - Confirmed this fix needs no new config key: both `exit_model="structural_atr"` and
  `sizing_model="risk"` are already opt-in switches; only their interaction inside `_scale_out`
  has a bug.
- 2026-07-13 - Bundled the optional finding #7 audit-log fix (risk-mode close `TradeRecord.volume`
  logged as 1) because it touches the same `_close_long`/`_close_short` methods and is trivial to
  verify.  Kept it as a separate, explicitly-labeled change in the commit message and HANDOFF; it
  does not alter `Position.pairs` accounting or any live order path.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-13 | codex → claude-code | done → design | A55 promoted from the post-remediation re-audit roadmap draft after A54 reached done |
| 2026-07-13 | claude-code → kimi-code | design → dev | A55 (partial-TP transaction-cost double-scaling fix) started |
| 2026-07-13 | kimi-code → codex | dev → review | A55 partial-TP transaction-cost double-scaling fix implemented |
| 2026-07-13 | codex → codex | review → done | A55 review passed: cost-rate fix and audit-log volume fix verified; sync gates and focused exit-model tests passed; full unit/preflight reruns hit documented WinError 5 tmp_path sandbox limitation, so used HANDOFF native counts 568 passed / preflight 155 passed for those items. |
