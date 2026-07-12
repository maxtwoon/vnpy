---
task: A49 - ATR Trailing-Stop Reachability Fix
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-13
deliverables:
  - HANDOFF.md
  - docs/design/a49-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

First task of the 2026-07-12 audit remediation roadmap (`docs/design/a49-audit-remediation-roadmap.md`
§"A49"), started immediately after A48 (P8b, final task of the P1-P8 roadmap) reached `done`. This
is a new, separate line of work — not part of the P1-P8 phase sequence.

`docs/review/ai_trading_review_2026-07-12.md` (an independent audit, spot-verified by claude-code)
found a real, reproducible bug: `_scale_out` (`chan_strategy/positions.py:832-846`, re-verified
2026-07-12, lines unchanged since the audit) returns early without setting
`self._partial_tp_done = True` when `sizing_model="risk"` and the risk-mode lot-floored
`scale_volume` is `< 1` or `>= self.volume`. Because `Position.update`'s `structural_atr` exit
branch (`positions.py:680-688`, re-verified unchanged) is an `elif` chain —

```python
elif not self._partial_tp_done:
    partial_event = self._get_partial_tp_event(signals_dict)
    if partial_event:
        self._scale_out(price, dt, f"部分止盈-{partial_event.name}")
elif self._check_atr_trailing_stop(price, atr):
    ...
```

— every subsequent bar re-enters the `not self._partial_tp_done` branch (does nothing useful,
since the flag was never flipped) and the ATR trailing-stop check on the next line is **never
evaluated** for the rest of that position's life. Under `exit_model="structural_atr"` (A47) +
`sizing_model="risk"` (A40), this silently removes the only profit-side risk control for any
position whose lot count doesn't cleanly support the configured `partial_tp_frac` split — a common
case for small accounts, low-multiplier symbols, or any already-1-lot position.

Full contract: `docs/design/a49-audit-remediation-roadmap.md` §"A49 — ATR Trailing-Stop
Reachability Fix" (the authoritative design — this HANDOFF summarizes it).

## Goal

Fix `_scale_out` so that when a risk-mode partial-TP scale-out is skipped due to lot flooring
(`scale_volume < 1` or `scale_volume >= self.volume`), `self._partial_tp_done` is set `True`
before returning — treating "partial TP impossible this lifecycle" as equivalent to "partial TP
already resolved," making the ATR trailing-stop branch reachable on the very next bar. Do NOT
fabricate a `pairs` entry for the skipped scale-out (zero volume actually changed hands). No new
config key — this is a correctness fix inside the already-opt-in `exit_model="structural_atr"`
switch, not a new behavior needing its own gate.

## Acceptance Criteria

- [x] A fixture with `sizing_model="risk"`, a position sized to exactly 1 lot, and
      `exit_model="structural_atr"` proves the bug existed before the fix: `_check_atr_trailing_stop`
      is never called after the skipped-partial-TP bar (e.g. via a call-count spy asserted against
      the pre-fix code path, or by asserting the position never exits via ATR trailing even when
      price crosses the trail level) — and is reachable/callable after the fix.
- [x] `_partial_tp_done` is `True` immediately after a skipped-partial-TP bar in this scenario
      (unit-tested directly on the `Position` object's state).
- [x] No `pairs` entry is fabricated for the skipped partial TP — `len(self.pairs)` unchanged by
      the skip itself (unit-tested).
- [x] `sizing_model="research"` (fractional volume, no lot flooring — the bug cannot occur here
      since `scale_volume` is never floored to an integer) is completely unaffected: existing
      `test_structural_atr_partial_tp_long`/`_short` in `test_exit_model.py` still pass unchanged,
      byte-for-byte.
- [x] `exit_model="legacy"` is completely unaffected (the bug only exists inside the
      `structural_atr` branch) — `test_exit_model_legacy_full_engine_equivalence`'s existing golden
      snapshot still passes unchanged.
- [x] No threshold tuning; no pre-2026-04-24 data used for any parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes — this script
      genuinely exists at `diagnostics/run_next_work.ps1`; verify the path carefully before
      claiming otherwise (A44's dev round falsely claimed it was absent).

## Manual verification (symlink-privilege sandbox limitation)

Run natively (outside the codex sandbox) by claude-code 2026-07-13, in response to codex's
review-round finding that its own sandboxed run hit the documented `tmp_path`/
`PermissionError [WinError 5]` symlink-privilege limitation (see the NOTE above the review
command in `.synccheck.yml`):

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` -> **526 passed, 4
  deselected**, no WinError 5.
- `run_next_work.ps1 -Preflight` -> **155 passed** (SimNow workflow unit tests), preflight
  completed cleanly, no WinError 5.
- `python tools/sync_check.py` -> PASS (root). `python tools/sync_check.py --root
  examples/czsc_strategy` -> PASS (child).

Reviewer (codex, sandboxed) may trust these counts for the two sandbox-blocked acceptance items
instead of re-running them; everything else should still be verified normally. codex's own review
found no implementation defect in `_scale_out` itself — the diff, focused regression test, and
both sync_check gates all passed in its sandboxed run; only the broad unit/preflight gates were
blocked by the sandbox limitation.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a49-audit-remediation-roadmap.md` §"A49". This is the first task
   of a new 6-task remediation roadmap (A49-A54) triaging `docs/review/ai_trading_review_2026-07-12.md`'s
   findings — read that audit report's Finding #1 (🔴 high) for full context if the design section
   alone isn't enough.
2. **Scope:** `chan_strategy/positions.py`'s `_scale_out` method only (lines ~825-878). Do not
   touch any other exit-model logic, `exit_model="legacy"`'s priority chain, `sizing_model="research"`'s
   path, or anything in A47's/A48's already-`done` scope beyond this one method.
3. **This is a bug fix inside an existing opt-in switch, not a new gated feature** — no new
   `STRATEGY_CONFIG` key is needed. `exit_model="structural_atr"` and `sizing_model="risk"` are
   both already opt-in (both default to the legacy/research values), so there is no new
   "default-off" equivalence proof required for THIS fix — but you MUST prove `exit_model="legacy"`
   and `sizing_model="research"` remain completely untouched by re-running their existing tests
   unchanged (see Acceptance Criteria).
4. **The most important test is proving the bug existed** — a regression test that only asserts
   post-fix behavior, without demonstrating the pre-fix code path was actually blocked, is weak
   evidence. Use a call-count spy on `_check_atr_trailing_stop` (e.g. via `monkeypatch` wrapping
   the method to count calls) in a fixture that would trigger it, and assert the count is 0 before
   understanding-the-fix and >0 after — or structure the test so it would fail if run against a
   reverted version of the fix (a `git stash` sanity check before finalizing is a good idea, though
   not itself part of the deliverable).
5. **Do not fabricate a trade record**: when `scale_volume < 1` or `>= self.volume`, no actual
   scale-out happens — `self.pairs` must not grow, `self.volume` must not change. Only the internal
   `_partial_tp_done` flag changes.
6. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; `exit_model="legacy"`/`sizing_model="research"` paths provably untouched.
7. **Before claiming any script "doesn't exist," verify the path carefully** —
   `run_next_work.ps1` lives at `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
8. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A49 ATR trailing-stop reachability fix implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

### Review rejection - 2026-07-12

Codex review did not find an A49 implementation defect in `_scale_out`: the focused regression
test passes, both sync gates pass, and the diff is scoped to `positions.py`, `test_exit_model.py`,
and the handoff. However, the broad unit-test and preflight acceptance items could not be accepted:
review reruns hit the documented Windows sandbox `PermissionError [WinError 5]` tmp_path/temp-dir
signature, and the current task file does not contain the required `Manual verification
(symlink-privilege sandbox limitation)` block with pass/fail counts. Add that block with the
unsandboxed verification evidence, or otherwise make those two gates runnable in review, then send
back to review.

## Decision Log

- 2026-07-12 - A49 promoted from `docs/design/a49-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task, started immediately after A48 reached `done`. This begins a new
  remediation roadmap (A49-A54) separate from the completed P1-P8 phase sequence (A38-A48).
- 2026-07-12 - Re-verified `_scale_out` (positions.py:832-846) and the `elif` chain in
  `Position.update` (positions.py:680-688) are unchanged since the audit — the bug is confirmed
  still present at the exact cited lines.
- 2026-07-12 - Confirmed this fix needs no new config key: both `exit_model="structural_atr"` and
  `sizing_model="risk"` are already opt-in switches from A47/A40; only their interaction has a
  bug, not their existence.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-12 | codex → claude-code | done → design | A49 promoted from the audit remediation roadmap draft after A48 reached done |
| 2026-07-12 | claude-code → kimi-code | design → dev | A49 (ATR trailing-stop reachability fix) started |
| 2026-07-12 | kimi-code → codex | dev → review | A49 ATR trailing-stop reachability fix implemented |
| 2026-07-12 | codex → kimi-code | review → dev | 打回: Review cannot accept broad-gate evidence: unit/preflight reruns hit documented WinError 5 tmp_path sandbox limitation, but HANDOFF lacks the required Manual verification block with pass/fail counts. |
| 2026-07-13 | kimi-code → codex | dev → review | A49 ATR trailing-stop reachability fix implemented |
| 2026-07-13 | codex → codex | review → done | A49 review passed: focused regression/equivalence tests and sync gates passed; broad unit/preflight accepted via documented manual verification block |
