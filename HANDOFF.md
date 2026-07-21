---
task: A98 - Gate partial take-profit exits with limit_halt_model="enforce" (re-audit H-NEW-1)
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-22
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/positions.py
  - examples/czsc_strategy/tests/unit/test_limit_halt_enforce.py
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
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

- 2026-07-22 (kimi-code, dev) - Fix applied exactly as designed: the partial-TP branch in
  `Position.update` (`examples/czsc_strategy/chan_strategy/positions.py`, structural_atr elif-chain)
  now wraps `self._scale_out(...)` in `if not self._reject_fill_at_limit(exit_at_limit, self.pos,
  is_entry=False):`. Re-verified surrounding branch structure before editing — line numbers had not
  drifted (branch at :776-779). Diff confirmed: 1 file changed, 2 insertions(+), 1 deletion(-), no
  other exit branch (structural_atr fixed-stop/timeout/ATR-trailing, or any legacy branch) touched,
  and `_scale_out`'s internals untouched per the one-call-site scope rule.
- 2026-07-22 (kimi-code, dev) - Added two regression tests to `tests/unit/test_limit_halt_enforce.py`
  (file went 12 -> 14 tests): `test_enforce_rejects_structural_atr_partial_tp_at_lower_limit`
  (blocked band: `pos.pos`/`volume` unchanged, no new pair, `_partial_tp_done is False`,
  `_pending_fill_rejected_at_limit is True`) and
  `test_enforce_allows_structural_atr_partial_tp_when_not_at_limit` (positive case under enforce:
  partial-TP fills normally, volume halves, `pair["fill_rejected_at_limit"] is False`). Fixture
  style combines `test_exit_model.py::test_structural_atr_partial_tp_long`'s directional-target
  partial-TP event with this file's enforce-blocking pattern, per the design.
- 2026-07-22 (kimi-code, dev) - L-NEW-1 resolved as a side effect of the H-NEW-1 fix, exactly as the
  design predicted: `_scale_out` is now only reachable after `_reject_fill_at_limit` has run for the
  current fill attempt, so `pair["fill_rejected_at_limit"]` reflects real state. No additional code
  change made; the positive-case test pins `fill_rejected_at_limit is False` for extra confidence.
- 2026-07-22 (kimi-code, dev) - Unit-test count delta: 766 -> 768 passed (not-realdb), i.e. exactly
  +2 (the two new tests). `test_exit_model.py` partial-TP tests pass unchanged (joint run of
  `test_limit_halt_enforce.py` + `test_exit_model.py`: 30 passed).
- 2026-07-22 (kimi-code, dev) - **Pre-existing `-m realdb` gate failure (NOT caused by A98),
  documented per the "verify, don't assume" rule**: `test_position_sizing_research_equivalence.py::
  test_research_mode_equivalence_to_baseline` fails on a last-ULP float diff in SC888's
  `sharpe_ratio` (baseline=0.8091974663759458 vs actual=0.809197466375945). All trade `pairs`,
  `equity_curve`, and `sub_strategies` match the stored baseline byte-for-byte. Proven pre-existing
  by temporarily reverting the A98 guard (plain file edit, no git mutation) and re-running: the
  identical failure reproduces on the pristine tree. The guard was then re-applied and re-verified.
  Root cause is numeric-stack drift vs the 2026-07-21 snapshot regeneration, in the same Sharpe
  problem area as the re-audit's already-known M-NEW-1 — left for that follow-up task; out of A98's
  one-call-site scope. A98 is behavior-inert in this test's configuration (`limit_halt_model="off"`
  per the test's config echo, so `_reject_fill_at_limit` always returns `False`).
- 2026-07-22 (kimi-code, dev) - VERSION bumped 0.2.35 -> 0.2.36 (synccheck:ignore) with a CHANGELOG
  entry stating the behavior change plainly (partial-TP fills can now be rejected under
  `limit_halt_model="enforce"` where they previously never were). No git commit performed —
  unrelated SimNow-workstream files (`diagnostics/WORK_LOG.md`,
  `diagnostics/simnow_20d_promotion_decision.md`) sit modified in the working tree and were not
  touched; `git status --short` shows only the four A98-scoped files as my changes.

## Manual Verification

All commands run natively on Windows PowerShell from `D:\repo\vnpy` (or the noted subdirectory)
with `D:\repo\vnpy\.venv_new\Scripts\python.exe` (pytest 9.1.1 — synccheck:ignore) and system `ruff`.

1. Scope check — one call site only:

   ```text
   PS> git diff examples/czsc_strategy/chan_strategy/positions.py
   @@ -776,7 +776,8 @@ class Position:
                    elif not self._partial_tp_done:
                        partial_event = self._get_partial_tp_event(signals_dict)
                        if partial_event:
   -                        self._scale_out(price, dt, f"部分止盈-{partial_event.name}")
   +                        if not self._reject_fill_at_limit(exit_at_limit, self.pos, is_entry=False):
   +                            self._scale_out(price, dt, f"部分止盈-{partial_event.name}")
                    elif self._check_atr_trailing_stop(price, atr):
   ...
    examples/czsc_strategy/chan_strategy/positions.py | 3 ++-
    1 file changed, 2 insertions(+), 1 deletion(-)
   ```

2. New regression tests (from `examples/czsc_strategy/`):

   ```text
   PS> python -m pytest tests/unit/test_limit_halt_enforce.py -q -m "not realdb"
   ..............                                                           [100%]
   14 passed, 2 warnings in 0.30s
   ```

3. Full unit suite (from `examples/czsc_strategy/`):

   ```text
   PS> python -m pytest tests/unit -q -m "not realdb"
   768 passed, 4 deselected, 2 warnings in 52.04s
   ```

   (Baseline before A98 was 766 passed; delta = exactly the 2 new tests.)

4. `test_exit_model.py` unaffected (from `examples/czsc_strategy/`):

   ```text
   PS> python -m pytest tests/unit/test_limit_halt_enforce.py tests/unit/test_exit_model.py -q -m "not realdb"
   30 passed, 2 warnings in 0.20s
   ```

5. `-m realdb` equivalence gate (from `examples/czsc_strategy/`) — **pre-existing failure, proven
   unrelated to A98**:

   ```text
   PS> python -m pytest tests/unit -m realdb -q
   FAILED tests\unit\test_position_sizing_research_equivalence.py::test_research_mode_equivalence_to_baseline
   1 failed, 3 passed, 768 deselected, 2 warnings in 72.14s
   ```

   Failure detail (`--tb=long`): `AssertionError: SC888: computed (Bucket-B) report fields differ
   from baseline: sharpe_ratio: baseline=0.8091974663759458 actual=0.809197466375945` — last-ULP
   float noise only; `pairs`, `equity_curve`, `sub_strategies` asserts all passed. Control run with
   the A98 guard temporarily reverted (then re-applied):

   ```text
   PS> python -m pytest tests/unit/test_position_sizing_research_equivalence.py::test_research_mode_equivalence_to_baseline -q
   FAILED tests\unit\test_position_sizing_research_equivalence.py::test_research_mode_equivalence_to_baseline
   1 failed, 2 warnings in 32.35s            # identical failure on the pristine tree
   ```

6. ruff on touched files (from repo root):

   ```text
   PS> ruff check examples/czsc_strategy/chan_strategy/positions.py examples/czsc_strategy/tests/unit/test_limit_halt_enforce.py
   All checks passed!
   ```

7. sync_check, both roots (from repo root):

   ```text
   PS> python tools/sync_check.py
   [SYNC-CHECK][OK] 版本单一真相 = 4.4.0  (source: vnpy/__init__.py::__version__)
   [SYNC-CHECK] PASS: 版本与文档一致

   PS> python tools/sync_check.py --root examples/czsc_strategy
   [SYNC-CHECK][OK] 版本单一真相 = 0.2.36  (source: VERSION::)   # synccheck:ignore
   [SYNC-CHECK] PASS: 版本与文档一致
   ```

8. Preflight (from `examples/czsc_strategy/diagnostics/`, where `run_next_work.ps1` lives):

   ```text
   PS> powershell -ExecutionPolicy Bypass -File .\run_next_work.ps1 -Preflight
   ==> Compile SimNow capture script
   ==> Run SimNow workflow unit tests
   205 passed in 31.29s
   ==> Build pending replay backfill plan
   ==> Preflight complete; live SimNow capture was not requested
   ```

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-22 | claude-code → claude-code | design → design | A98 (partial-TP enforce gating, re-audit H-NEW-1) scoped; drafting design brief |
| 2026-07-22 | claude-code → kimi-code | design → dev | A98 promoted design->dev |
| 2026-07-22 | kimi-code → codex | dev → review | A98 partial-TP enforce gating completed |
| 2026-07-22 | codex → codex | review → done | A98 review passed: one-call-site partial-TP enforce guard verified; focused tests, ruff, and sync gates pass; sandbox tmp_path/preflight and external realdb access limitations handled per recorded native verification |
