---
task: A96 - Document signals.py's legacy signal system as independently-maintained, not a duplicate (audit M3)
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-21
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/signals.py
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
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

- [x] `signal_second_buy`/`signal_third_buy`'s docstrings explicitly state: (a) they belong to the
      self-contained legacy signal system used by `get_legacy_signals()`, (b) they are independently
      maintained and not guaranteed to match `sell_signals`'s same-named functions, (c) they have their own
      dedicated test coverage, (d) new code should use `sell_signals` instead.
- [x] `get_legacy_signals()`/`get_all_signals()`'s existing deprecation notes are strengthened with the
      same "independently-maintained system, not a duplicate" framing.
- [x] No change to any function's logic, signature, or return value in `signals.py` or `sell_signals.py`.
- [x] No change to any test's assertions; `test_second_buy_bug.py` and
      `tests/unit/test_remaining_coverage.py`'s second/third-buy tests still pass unchanged.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes, exact same pass count.
- [x] `-m realdb` equivalence gate still passes unchanged (comment-only change to `signals.py`, but verify
      rather than assume, same discipline as A94/A95).
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [x] `ruff check` clean on touched files.
- [x] VERSION/CHANGELOG bumped.
- [x] Include a literal `## Manual Verification` heading with natively-run command output.
- [x] **Remember the `synccheck:ignore` marker** for any version-like string mentioned in this task's own
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

- 2026-07-21 (kimi-code, dev) - Implemented A96 as scoped: docstring-only edits to `signals.py`
  (`signal_second_buy`, `signal_third_buy`, `get_legacy_signals`, `get_all_signals`), no logic/signature/
  return-value changes, `sell_signals.py` and all tests untouched. Small deviation recorded: the acceptance
  item says `run_next_work.ps1 -Preflight` "from `examples/czsc_strategy/`", but the script actually lives
  at `examples/czsc_strategy/diagnostics/run_next_work.ps1`; Preflight was run from there and passed
  (exit 0). czsc_strategy VERSION bumped to 0.2.34 with CHANGELOG entry (synccheck:ignore).

## Manual Verification

All commands run natively by kimi-code on 2026-07-21 (Windows PowerShell). VERSION bumped to
0.2.34 with a CHANGELOG entry (synccheck:ignore). `git diff` on `signals.py` shows 59 insertions /
6 deletions, all inside docstrings — no logic line touched; `sell_signals.py` untouched.

```
$ python -m pytest tests/unit -q -m "not realdb"        (cwd: examples/czsc_strategy)
761 passed, 4 deselected in 40.31s                      # same pass count as A95 baseline (761)

$ python -m pytest tests/unit -m realdb -q              (cwd: examples/czsc_strategy)
4 passed, 761 deselected in 81.71s (0:01:21)            # equivalence gate unchanged

$ python -m pytest tests/unit/test_remaining_coverage.py -k "second_buy or third_buy" -q
2 passed, 6 deselected in 0.09s                         # dedicated legacy second/third-buy tests

$ python tools/sync_check.py                            (repo root)
[SYNC-CHECK][OK] 版本单一真相 = 4.4.0  (source: vnpy/__init__.py::__version__)
[SYNC-CHECK] PASS: 版本与文档一致。  (exit 0)

$ python tools/sync_check.py --root examples/czsc_strategy
[SYNC-CHECK][OK] 版本单一真相 = 0.2.34  (source: VERSION::)   (synccheck:ignore)
[SYNC-CHECK] PASS: 版本与文档一致。  (exit 0)

$ ruff check examples/czsc_strategy/chan_strategy/signals.py
All checks passed!  (exit 0)

$ .\run_next_work.ps1 -Preflight                        (cwd: examples/czsc_strategy/diagnostics)
200 passed in 23.75s  (SimNow workflow unit tests)
==> Preflight complete; live SimNow capture was not requested   (exit 0)

$ git status --short                                    # only A96-scoped files + pre-existing
 M examples/czsc_strategy/CHANGELOG.md                  # unrelated SimNow-workstream modifications
 M examples/czsc_strategy/VERSION
 M examples/czsc_strategy/chan_strategy/signals.py
 M examples/czsc_strategy/diagnostics/WORK_LOG.md               (pre-existing, not touched by A96)
 M examples/czsc_strategy/diagnostics/simnow_20d_promotion_decision.md  (pre-existing, not touched)
```

Note: `run_next_work.ps1` actually lives under `examples/czsc_strategy/diagnostics/` (not the
`examples/czsc_strategy/` root as the acceptance item literally says), so Preflight was run from
there; it passed with exit 0.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-21 | claude-code → kimi-code | design → dev | A96 (document legacy signal system, audit M3) promoted; handoff design->dev |
| 2026-07-21 | kimi-code → codex | dev → review | A96 legacy signal system documented |
