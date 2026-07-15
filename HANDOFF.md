---
task: A72 - Deprecate signals.py Legacy get_all_signals()
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a70-second-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

Third and FINAL task of the second third-party audit remediation roadmap
(`docs/design/a70-second-audit-remediation-roadmap.md`), promoted after A71 reached `done` (codex
accepted on the first review round). Completing this task finishes the entire A70-A72 roadmap.

A66 (README rewrite) already established that the production signal path is
`chan_strategy/sell_signals.py::get_all_signals()`. `chan_strategy/signals.py` still has its own,
separate `get_all_signals()` (line 857) that calls deprecated second/third-buy implementations, and
the second audit flagged this as a risk: new code could accidentally import the wrong one.

**Correction to the design doc's claim (found during this promotion, 2026-07-15)**: the design
doc's Rationale section says the two real callers (`skill_build/build_mapping.py:47`,
`skill_build/scripts/analyze_symbol.py:61`) "both import `get_all_signals` from
`chan_strategy.signals` rather than `chan_strategy.sell_signals`" — **this is no longer accurate,
if it ever fully was**. Both files actually already do:
```python
try:
    from chan_strategy.sell_signals import get_all_signals
except ImportError:  # pragma: no cover
    from chan_strategy.signals import get_all_signals
```
i.e. they already prefer the production path and only fall back to the legacy module on
`ImportError` — which in practice never fires, since `chan_strategy.sell_signals` always exists in
this repo. So the real remaining risk is narrower than the design doc states: it's not that these
two callers are misusing the legacy path today, it's that (a) `signals.py` still exposes a fully
duplicate, directly-importable `get_all_signals()` that some *future* code could pick up by
mistake, and (b) the `except ImportError` fallback branches in these two files are dead-code safety
nets that would silently switch to the legacy implementation if `sell_signals.py` ever became
unimportable for an unrelated reason (e.g. a syntax error introduced elsewhere in that module) —
which is itself a subtle behavior worth tightening while we're in here.

**Full contract**: `docs/design/a70-second-audit-remediation-roadmap.md` §"A72" (this HANDOFF
corrects and summarizes it — the design doc's Semantics section for the rename/deprecation-warning
mechanism is still accurate and should be followed; only the "two real callers" factual claim in
its Rationale is superseded by the correction above).

## Goal

1. Rename `chan_strategy/signals.py`'s `get_all_signals()` (line 857) to `get_legacy_signals()`
   (function body unchanged, docstring gains a note that it's superseded by
   `chan_strategy.sell_signals.get_all_signals`).
2. Add a thin wrapper at the old name `get_all_signals` that emits `warnings.warn(...,
   DeprecationWarning, stacklevel=2)` and forwards to `get_legacy_signals()` — do not delete the old
   entry point (avoids breaking any caller not yet discovered), but any new code path should never
   call it directly.
3. Update `skill_build/build_mapping.py` and `skill_build/scripts/analyze_symbol.py`'s
   `except ImportError: from chan_strategy.signals import get_all_signals` fallback lines to call
   `get_legacy_signals()` instead of `get_all_signals()` — this both avoids triggering the new
   deprecation warning on the (dead-code-in-practice) fallback path, and makes the fallback's intent
   explicit (if `sell_signals` is ever genuinely unimportable, falling back to the *named* legacy
   function is clearer than silently hitting a deprecation-warning wrapper).
4. Update the two test files that intentionally exercise the legacy implementation itself
   (`tests/unit/test_remaining_coverage.py:155`'s `base_signals.get_all_signals(...)` and
   `test_second_buy_real_path.py:19`'s `from chan_strategy.signals import get_all_signals`) to call
   `get_legacy_signals()` directly, so they don't trigger warning noise for behavior they're
   deliberately testing.
5. Add a new test asserting the old name still works but emits `DeprecationWarning`
   (`pytest.warns(DeprecationWarning)`) and returns the same result as `get_legacy_signals()`.

## Acceptance Criteria

- [ ] `chan_strategy/signals.py` has `get_legacy_signals()` (original function body) and a thin
      `get_all_signals()` wrapper that warns `DeprecationWarning` and forwards to it.
- [ ] `skill_build/build_mapping.py` and `skill_build/scripts/analyze_symbol.py`'s `except
      ImportError` fallback branches call `get_legacy_signals()`, not `get_all_signals()`.
- [ ] `tests/unit/test_remaining_coverage.py` and `test_second_buy_real_path.py` (the two files
      deliberately testing the legacy implementation) call `get_legacy_signals()` directly — no
      unexpected `DeprecationWarning` noise in normal test runs.
- [ ] New test: calling `get_all_signals()` (the old name) emits `DeprecationWarning` and returns a
      result identical to calling `get_legacy_signals()` with the same arguments.
- [ ] No signal-calculation logic changes anywhere — this is a rename + deprecation-warning wrapper
      + caller update only. Every existing test's numeric/structural assertions on signal output
      stay byte-identical.
- [ ] If pytest is configured to treat warnings as errors anywhere in this repo's config, the new
      `DeprecationWarning` must not break unrelated existing tests — check
      `pytest.ini`/`pyproject.toml`/`conftest.py` for `filterwarnings` settings under
      `examples/czsc_strategy/` and add a scoped `filterwarnings` marker/ini entry only if needed
      (do not blanket-suppress all `DeprecationWarning`s repo-wide).
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped (user-visible behavior addition: a new deprecation warning path).

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a70-second-audit-remediation-roadmap.md` §"A72", but **read this
   HANDOFF's Background correction above first** — the design doc's claim about the two real
   callers already misusing the legacy path is outdated; the accurate current state is the
   try/except-preferring-production pattern described above. Verify this yourself by reading both
   files before writing code, per usual practice (design docs can drift from code).
2. **Scope:** `chan_strategy/signals.py`, `skill_build/build_mapping.py`,
   `skill_build/scripts/analyze_symbol.py`, and the two test files named above (plus a new test for
   the deprecation warning). Do not touch `chan_strategy/sell_signals.py`, any SimNow order/cancel/
   send path, or any signal-calculation logic.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A72-scoped files are staged** — both A70 and A71
   got this right by checking status before committing; keep doing that.
4. **Guardrails (reject-on-violation):** no signal-calculation logic changes; no pre-2026-04-24
   data for any new parameter choice (not applicable here, but stated for consistency); no SimNow
   order/cancel/send paths touched; no `GOAL PASSED`.
5. **Include a Manual-verification block with natively-run counts** (claude-code will also
   independently re-run everything before triggering review), and run `ruff check` proactively
   before finishing.
6. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A72 signals.py legacy get_all_signals deprecation implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. **This is the last task in the
   A70-A72 roadmap** — after this reaches `done`, trigger a fresh third-party audit per the standing
   instruction (see A70's original Background for the full "keep iterating until score > 75, no
   medium+ issues" instruction).

## Decision Log

- 2026-07-15 - A72 promoted from `docs/design/a70-second-audit-remediation-roadmap.md`'s draft to
  an active HANDOFF task, immediately after A71 reached `done` (codex accepted on the first review
  round). Third and final task of the second audit-remediation roadmap.
- 2026-07-15 (claude-code pre-promotion research) - Corrected the design doc's claim about the two
  real callers: both already prefer `sell_signals.get_all_signals` via try/except, falling back to
  `signals.get_all_signals` only on `ImportError` (dead-code-in-practice, since `sell_signals.py`
  always exists). Narrowed this task's real scope accordingly (see Background above). This
  correction is recorded here rather than by editing the design doc in place, to preserve the
  design doc as the historical record of what was believed at roadmap-creation time.
- 2026-07-15 (claude-code independent verification, before triggering codex review) - Confirmed
  scope was clean before committing (only A72-scoped files staged; unrelated concurrent-workstream
  files left untouched). Read every diff: `signals.py`'s rename+wrapper is exactly as specified;
  both `skill_build` callers' `except ImportError` fallback now names `get_legacy_signals`
  explicitly; both test files updated correctly, including a new
  `test_base_get_all_signals_emits_deprecation_warning` asserting `pytest.warns(DeprecationWarning)`
  and exact result equality with `get_legacy_signals`. Confirmed the 21 pre-existing ruff errors in
  `test_second_buy_real_path.py` (unused `typing.List`/`Optional` imports, `E702` semicolons, etc.)
  are unchanged before/after this diff — not a regression introduced here. Re-ran everything
  independently: full unit suite `666 passed, 4 deselected`; both `sync_check.py` gates passed;
  `run_next_work.ps1 -Preflight` passed.

## Manual Verification

```text
pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
# 666 passed, 4 deselected

python tools/sync_check.py
# PASS

python tools/sync_check.py --root examples/czsc_strategy
# PASS

powershell -ExecutionPolicy Bypass -File examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight
# Preflight complete

python -c "import test_second_buy_real_path"  # (from examples/czsc_strategy/) confirms rename didn't break import
# OK
```

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | claude-code → kimi-code | design → dev | A72 (signals.py legacy get_all_signals deprecation) promoted from second third-party audit remediation roadmap; handoff design->dev |
| 2026-07-15 | kimi-code → codex | dev → review | A72 signals.py legacy get_all_signals deprecation implemented |
| 2026-07-15 | codex → codex | review → done | A72 review passed: legacy get_all_signals deprecation verified |
