---
task: A98 - Gate partial take-profit exits with limit_halt_model="enforce" (re-audit H-NEW-1)
version: 4.4.0
stage: design
owner: claude-code
updated: 2026-07-22
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/positions.py
  - examples/czsc_strategy/tests/unit/test_limit_halt_enforce.py
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
blockers: []
last_transition_kind: fix
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: design
last_transition_from_owner: claude-code
last_transition_to_owner: claude-code
---

## Background

`diagnostics_ai_stock_review_report_2026-07-22.md` (the post-A97 comprehensive re-audit, requested by the
project owner once the original 2026-07-21 audit's H1-H3/M1-M5 were fully closed) flagged one new
High-severity finding, **H-NEW-1**: under `exit_model="structural_atr"`, the partial take-profit exit path
(`Position._scale_out`, called only from `positions.py:779`) is the **only** exit branch in the whole file
that does not go through the `_reject_fill_at_limit(...)` guard that `limit_halt_model="enforce"` relies on.

**claude-code independently re-verified this by reading the code** (not just trusting the subagent's
report):

- `positions.py:717,725,740,748,755,765,771,781` — every other exit branch (signal exit, legacy trailing
  stop, fixed stop, timeout, structural-ATR fixed stop, structural-ATR timeout, structural-ATR ATR-trailing)
  wraps its close in `if not self._reject_fill_at_limit(exit_at_limit, self.pos, is_entry=False): ...`.
- `positions.py:776-779` (the partial-TP branch) does not:
  ```python
  elif not self._partial_tp_done:
      partial_event = self._get_partial_tp_event(signals_dict)
      if partial_event:
          self._scale_out(price, dt, f"部分止盈-{partial_event.name}")
  ```
- `_scale_out` (`positions.py:921-985`) never calls `_reject_fill_at_limit` and never reads/writes
  `_pending_fill_rejected_at_limit` itself — it just reads whatever stale value that attribute already
  holds into `pair["fill_rejected_at_limit"]` (`:981`). This is the audit's related Low finding
  (`L-NEW-1`) — fold it into this task's fix rather than opening a separate task, since fixing H-NEW-1 the
  standard way (routing through `_reject_fill_at_limit`) fixes L-NEW-1 as a natural side effect (that helper
  is what actually sets `_pending_fill_rejected_at_limit = True` on a real rejection).
- `_reject_fill_at_limit` (`positions.py:653-670`): returns `False` (never blocks) unless
  `STRATEGY_CONFIG["limit_halt_model"] == "enforce"`; when it does block, it sets
  `self._pending_fill_rejected_at_limit = True` and returns `True`. This is the single mechanism every
  other exit branch uses to decide whether a fill is blocked, and it's what needs to gate `_scale_out` too.
- `exit_model="structural_atr"` and `limit_halt_model="enforce"` are both real, independently-toggleable
  config knobs (`config.py`) — nothing marks them mutually exclusive, and `formal_evaluation_config()`
  (`backtest_engine.py:~55-90`) turns `limit_halt_model="enforce"` on for the project's "trustworthy"
  evaluation path, which is exactly the kind of run an operator would also plausibly combine with
  `structural_atr`'s partial-TP behavior.
- Confirmed via repo-wide search: no existing test constructs `exit_model="structural_atr"` together with
  `limit_halt_model="enforce"`. `test_exit_model.py` covers partial-TP without enforce.
  `test_limit_halt_enforce.py` covers enforce (including a structural_atr **timeout** exit rejection test,
  `test_enforce_rejects_structural_atr_timeout_exit_at_lower_limit`, `:251-270`) but not partial-TP.

## Goal

1. Wrap the `_scale_out` call at `positions.py:779` in the same guard every sibling branch uses:
   ```python
   elif not self._partial_tp_done:
       partial_event = self._get_partial_tp_event(signals_dict)
       if partial_event:
           if not self._reject_fill_at_limit(exit_at_limit, self.pos, is_entry=False):
               self._scale_out(price, dt, f"部分止盈-{partial_event.name}")
   ```
   Re-verify the exact surrounding indentation/branch structure yourself before editing (line numbers may
   have drifted from claude-code's read).
2. **Do not touch any other exit branch** — the fixed-stop, timeout, and ATR-trailing branches under
   `structural_atr` already have the guard; leave them exactly as-is. Do not touch the `legacy` exit-model
   branches either.
3. **Behavior when the fill IS rejected**: when `_reject_fill_at_limit` returns `True`, `_scale_out` is
   simply not called this bar — no partial-TP fill happens, `_partial_tp_done` stays `False`, and (per the
   existing `_reject_fill_at_limit` contract) `_pending_fill_rejected_at_limit` is set `True`. This mirrors
   exactly how every other rejected-exit branch behaves today (the position just tries again next bar) — do
   not invent new retry/backoff logic.
4. Add a regression test to `tests/unit/test_limit_halt_enforce.py`, modeled directly on the existing
   sibling test `test_enforce_rejects_structural_atr_timeout_exit_at_lower_limit` (`:251-270`) — same
   `STRATEGY_CONFIG["exit_model"] = "structural_atr"` + `STRATEGY_CONFIG["limit_halt_model"] = "enforce"`
   setup, same `exit_at_limit=(False, True)` fill-blocking pattern — but driving a partial-TP signal instead
   of a timeout, and asserting the partial-TP fill is rejected (`pos.pos` unchanged, `pos.pairs` empty or
   unchanged, `pos._partial_tp_done` still `False`). Look at `test_exit_model.py`'s
   `test_structural_atr_partial_tp_long` (`:81-107`) for how to construct the partial-TP-triggering signal
   fixture, and combine that setup style with the enforce-blocking style from `test_limit_halt_enforce.py`.
5. Add a second regression test (or extend the same test) confirming the **positive** case still works
   correctly: with `limit_halt_model="enforce"` and `exit_at_limit=(False, False)` (fill NOT at a blocked
   band), a partial-TP fill still executes normally and `pair["fill_rejected_at_limit"]` is `False` — so the
   fix doesn't accidentally suppress legitimate partial-TP fills under `enforce` when nothing is actually
   blocked.
6. This also naturally resolves the re-audit's `L-NEW-1` (stale `fill_rejected_at_limit` on partial-TP
   pairs) — once `_scale_out` is only reached after `_reject_fill_at_limit` has run for *this* fill attempt,
   `pair["fill_rejected_at_limit"]` reflects real state for the reasons described in Background. No
   additional code change needed for L-NEW-1 beyond the H-NEW-1 fix itself — just note in the Decision Log
   that it's resolved as a side effect, and if you want extra confidence, assert
   `pair["fill_rejected_at_limit"] is False` in the positive-case test from item 5 (rather than leaving it
   unchecked).

## Acceptance Criteria

- [ ] `_scale_out` at `positions.py:779` is only called when `_reject_fill_at_limit(exit_at_limit, self.pos,
      is_entry=False)` returns `False` — verified in the diff.
- [ ] No other exit branch (`structural_atr` fixed-stop/timeout/ATR-trailing, or any `legacy` branch)
      changed — verified in the diff.
- [ ] New regression test(s) in `test_limit_halt_enforce.py`: (a) a partial-TP fill IS rejected when
      `exit_at_limit` marks the exit side as blocked under `enforce` (position stays open, no new pair,
      `_partial_tp_done` stays `False`); (b) a partial-TP fill still executes normally under `enforce` when
      the exit side is NOT blocked, with `fill_rejected_at_limit is False` on the resulting pair.
- [ ] `test_exit_model.py`'s existing partial-TP tests (`test_structural_atr_partial_tp_long/short`, etc.)
      still pass unchanged — they don't set `limit_halt_model="enforce"`, so they must be completely
      unaffected by this change (verify, don't assume).
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes (count increases only
      by the new test(s) added — note the exact delta in the Decision Log).
- [ ] `-m realdb` equivalence gate still passes unchanged (this task touches `positions.py` — verify per
      AGENTS.md rule, don't assume it's unaffected just because the change is exit-model-scoped).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] `ruff check` clean on touched files.
- [ ] VERSION/CHANGELOG bumped — this is a real behavior change (partial-TP fills can now be rejected under
      `enforce` where they previously never were), so the CHANGELOG entry must state that plainly, not just
      "test coverage added."
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.
- [ ] **Remember the `synccheck:ignore` marker** for any version-like string in this task's own HANDOFF
      notes.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **This is a real behavior change** (a previously-unguarded fill path now can be rejected), not
   documentation — same discipline as A82/A97, not A94/A95/A96's doc-only tasks.
2. **Scope is exactly one call site** (`positions.py:779`'s `_scale_out` call). Resist any temptation to
   "also clean up" `_scale_out`'s internals, the other exit branches, or the `L-NEW-1` bookkeeping
   separately — the single guard addition is the whole fix; do not touch anything else in `positions.py`.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/WORK_LOG.md`, `diagnostics/simnow_20d_promotion_decision.md`, and any other SimNow-workstream
   files you see) — these belong to a concurrent, unrelated workstream. **Before committing, run
   `git status --short` and confirm only your own A98-scoped files are staged.**
4. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
5. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A98 partial-TP enforce gating completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times out
   for environment reasons, do not manually hand-edit HANDOFF.md's stage/owner fields to bypass it — leave
   the working tree with your changes uncommitted and note the failure in the Decision Log; claude-code will
   verify and commit properly.

## Decision Log

- 2026-07-22 (claude-code, design) - This is the first of three follow-up tasks from the 2026-07-22
  re-audit (1 High + 2 Medium). Scoping H-NEW-1 (this task) first since it's the only one with a clear,
  low-risk, unambiguous fix — the other two (M-NEW-1 Sharpe threshold inconsistency, M-NEW-2 divergence
  direction-matching) will be scoped as separate follow-up tasks once this one closes, keeping with this
  project's one-task-at-a-time discipline.
- 2026-07-22 (claude-code, design) - Deliberately folded the audit's related `L-NEW-1` (stale
  `fill_rejected_at_limit` bookkeeping on partial-TP pairs) into this task rather than opening a separate
  one, since the report itself notes L-NEW-1 "rides on High finding 1" and is naturally resolved by the same
  fix — opening a second task for it would be pure process overhead with no additional code change.
- 2026-07-22 (claude-code, design) - Confirmed via code reading (not just trusting the re-audit subagent)
  that `_scale_out` is the only call site missing the guard, and that `_reject_fill_at_limit` is a pure,
  side-effect-safe-to-call-again helper (it only sets state on an actual rejection) — so wrapping the call
  is a minimal, mechanical fix with no other ripple expected, unlike A97 which had a real behavior-change
  blast radius into a second test file.

## Manual Verification

(pending — dev fills in)

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-22 | claude-code → claude-code | design → design | A98 (partial-TP enforce gating, re-audit H-NEW-1) scoped; drafting design brief |
