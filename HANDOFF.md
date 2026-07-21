---
task: A96 - Document signals.py's legacy signal system as independently-maintained, not a duplicate (audit M3)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-21
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/signals.py
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

`diagnostics_ai_stock_review_report.md` (2026-07-21 full project audit) flagged **M3**: `signal_second_buy`
(`signals.py:488`) and `signal_third_buy` (`signals.py:629`) are marked `.. deprecated::` in favor of the
"authoritative" implementations in `sell_signals.py` (same names, same signatures), and any code still
calling `signals.get_all_signals()` (a deprecated wrapper, `signals.py:881`) or `signals.get_legacy_signals()`
(`signals.py:858`) would get "semantically similar but differently-implemented" second/third-buy results —
flagged as a "same name, different meaning" risk plus dead code coexisting with authoritative rules.

**claude-code re-investigated this before promoting the task and found the situation is more nuanced than
the audit's suggested fixes ("forward to sell_signals, or remove entirely and centralize imports") assumed
— read this before touching anything:**

1. `get_legacy_signals()` (`signals.py:858-878`) calls `signals.py`'s OWN `signal_second_buy`/
   `signal_third_buy` directly (`signals.py:873-874`) — NOT the `sell_signals` versions. This is not two
   redundant copies of the same logic; it is a complete, self-contained "legacy signal system"
   (`get_legacy_signals` assembling `signal_bi_direction`/`signal_zs_position`/`signal_first_buy`/
   `signal_second_buy`/`signal_third_buy`/etc., all from `signals.py` itself) that exists specifically to
   preserve historical-script compatibility, distinct from the current authoritative
   `sell_signals.get_all_signals()` path.
2. `tests/unit/test_remaining_coverage.py::test_base_second_buy_edge_branches` and
   `::test_base_third_buy_edge_branches` (and a standalone `test_second_buy_bug.py` at the repo root)
   directly exercise `signals.signal_second_buy`/`signal_third_buy`'s own behavior with hand-built `CZSC`
   fixtures, including `monkeypatch.setattr(base_signals, "build_zhongshu_from_bis", ...)` — patching
   `signals.py`'s own module-level reference. **If `signal_second_buy`/`signal_third_buy` were rewritten to
   forward to `sell_signals`'s implementations, these monkeypatches would silently stop taking effect**
   (they'd be patching a reference `sell_signals`'s code path never reads), and the tests would either break
   outright or silently stop testing what they claim to test. This is a real, concrete regression risk that
   the audit's suggested fixes did not account for.
3. **Conclusion: do NOT forward `signal_second_buy`/`signal_third_buy` to `sell_signals`, and do NOT delete
   them** — both would break `get_legacy_signals()` (which depends on the `signals.py`-local versions) and
   the existing unit tests that specifically validate this implementation's own behavior. This task is
   scoped to **documentation only**, same pattern as M4 (A94) and M1 (A95): make the "these are two
   independently-maintained systems, not a copy that should be reconciled" fact explicit and impossible to
   miss, so a future reader isn't misled into thinking it's simple dead code or an accidental duplicate.

## Goal

1. Strengthen the `.. deprecated::` docstring notes on `signal_second_buy` (`signals.py:488-495`) and
   `signal_third_buy` (`signals.py:629-633`ish, re-read the current file for the exact line) to state
   explicitly:
   - This is part of a self-contained "legacy signal system" (`get_legacy_signals()`), not a stray
     duplicate of `sell_signals`'s implementation.
   - It is independently maintained and **not guaranteed to produce the same result** as
     `sell_signals.signal_second_buy`/`signal_third_buy` for the same input — the two have diverged and may
     continue to diverge, since they are maintained as separate code paths.
   - It has its own dedicated unit test coverage (name the test file:
     `tests/unit/test_remaining_coverage.py`) validating its own behavior, independent of `sell_signals`.
   - New code should use `sell_signals`'s implementation; this legacy path exists only for backward
     compatibility with historical callers of `get_legacy_signals()`/`signals.get_all_signals()`.
2. Add or strengthen a similar clarifying note on `get_legacy_signals()` itself (`signals.py:858-865`) and
   on the deprecated `get_all_signals()` wrapper (`signals.py:881-894`) — the existing `.. deprecated::` /
   `.. note::` blocks are a good start but should make the "two independently-maintained systems, not
   redundant duplicates" point as explicit as the point above, since that's the actual audit concern.
3. **Do not change any function's logic, do not forward/delegate to `sell_signals`, do not delete
   anything, do not touch `sell_signals.py` at all.** This task is documentation only, on `signals.py`.
4. **Do not touch `test_second_buy_bug.py` or `tests/unit/test_remaining_coverage.py`** — they should
   continue passing completely unchanged, since no logic changes.

## Acceptance Criteria

- [ ] `signal_second_buy`/`signal_third_buy`'s docstrings explicitly state: (a) they belong to the
      self-contained legacy signal system used by `get_legacy_signals()`, (b) they are independently
      maintained and not guaranteed to match `sell_signals`'s same-named functions, (c) they have their own
      dedicated test coverage, (d) new code should use `sell_signals` instead.
- [ ] `get_legacy_signals()`/`get_all_signals()`'s existing deprecation notes are strengthened with the
      same "independently-maintained system, not a duplicate" framing.
- [ ] No change to any function's logic, signature, or return value in `signals.py` or `sell_signals.py`.
- [ ] No change to any test's assertions; `test_second_buy_bug.py` and
      `tests/unit/test_remaining_coverage.py`'s second/third-buy tests still pass unchanged.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes, exact same pass count.
- [ ] `-m realdb` equivalence gate still passes unchanged (comment-only change to `signals.py`, but verify
      rather than assume, same discipline as A94/A95).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] `ruff check` clean on touched files.
- [ ] VERSION/CHANGELOG bumped.
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.
- [ ] **Remember the `synccheck:ignore` marker** for any version-like string mentioned in this task's own
      HANDOFF notes — this has bitten nearly every task in this session.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **Read the Background section above carefully before touching anything.** The audit's original
   suggested fixes ("forward to sell_signals, or remove and centralize") were re-evaluated by claude-code
   and found to carry real regression risk once the full picture was understood (`get_legacy_signals()`'s
   dependency on the local implementations, and the dedicated test coverage that monkeypatches
   `signals.py`'s own module-level references). Do not re-attempt those suggested fixes — this task is
   scoped to documentation only for a reason.
2. **If you find yourself wanting to forward, delete, or otherwise change behavior here — stop and
   escalate in the Decision Log instead.** That would be a real architectural decision (does the project
   want to keep two independently-maintained signal systems long-term, or actually retire the legacy one?)
   that needs its own design conversation, not something to decide inside a documentation task.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to a
   concurrent, unrelated SimNow-observation workstream. **Before committing, run `git status --short`
   and confirm only your own A96-scoped files are staged.**
4. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
5. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A96 legacy signal system documented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times
   out for environment reasons (this has happened repeatedly on this machine), do not manually hand-edit
   HANDOFF.md's stage/owner fields to bypass it — leave the working tree with your changes uncommitted and
   note the failure in the Decision Log; claude-code will verify and commit properly.

## Decision Log

- 2026-07-21 - Continuing the M-series from the audit report after M1 (A95) closed. This task (A96) is M3.
- 2026-07-21 (claude-code, design) - Re-investigated M3 before promoting and found the audit's suggested
  fixes ("forward to sell_signals, or remove") carry real regression risk: `get_legacy_signals()` depends
  on `signals.py`'s own `signal_second_buy`/`signal_third_buy` (not `sell_signals`'s), and
  `tests/unit/test_remaining_coverage.py` has dedicated tests that `monkeypatch.setattr(base_signals,
  "build_zhongshu_from_bis", ...)` against `signals.py`'s own module reference — forwarding would silently
  break these monkeypatches without necessarily failing loudly. Confirmed via `python -m pytest
  tests/unit/test_remaining_coverage.py -k "second_buy or third_buy" -v`: `2 passed` on current code.
  Re-scoped the task to documentation-only, matching the M4(A94)/M1(A95) pattern, and explicitly flagged
  that any future decision to actually unify or retire the legacy system is a real architectural decision
  needing its own design conversation, not something to resolve inside this task.

## Manual Verification

(dev to fill in with actual command output before requesting review)

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-21 | claude-code → kimi-code | design → dev | A96 (document legacy signal system, audit M3) promoted; handoff design->dev |
