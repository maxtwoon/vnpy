---
task: A75 - Legacy Signal-Path Import Hygiene Guard Test
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a73-third-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

Third and FINAL task of the third third-party audit remediation roadmap
(`docs/design/a73-third-audit-remediation-roadmap.md`), promoted after A74 reached `done` (codex
accepted on the first review round). Completing this task finishes the entire A73-A75 roadmap.

A72 (done in the second roadmap) already renamed `chan_strategy/signals.py`'s `get_all_signals()`
to `get_legacy_signals()` and added a thin `DeprecationWarning`-emitting wrapper at the old name.
The third audit still flagged residual risk: the legacy implementation physically still lives in
`chan_strategy/signals.py`, so future code could still accidentally import the deprecated wrapper.
The audit suggested either physically relocating it or adding an import-guard test; the design doc
(§"A75") already picked the guard-test option as more cost-effective.

**claude-code's own pre-promotion research (2026-07-15)**: re-ran a repo-wide grep for
`get_all_signals`/`get_legacy_signals` references. The result set is much broader than the two
"real callers" originally named by earlier audits — it includes many `tests/unit/*.py` files that
import `sell_signals.get_all_signals` (the PRODUCTION function, a legitimate reference, not a
violation) as well as `chan_strategy/signals.py`/`sell_signals.py`/`validation.py`/`__init__.py`
themselves. **This task's guard test must distinguish "imports the production
`sell_signals.get_all_signals`" (fine) from "imports the deprecated `chan_strategy.signals`
module's `get_all_signals` directly, without going through the `get_legacy_signals as
get_all_signals` rename pattern A72 established" (the thing to flag)** — dev must design the
detection carefully, not just grep for the string `get_all_signals` everywhere.

**Full contract**: `docs/design/a73-third-audit-remediation-roadmap.md` §"A75" (this HANDOFF
summarizes it — read the full Rationale/Semantics there before writing code).

## Goal

Add a guard test (e.g. `tests/unit/test_signal_path_hygiene.py`) that statically scans
production/execution-path files (excluding `chan_strategy/signals.py` itself and test files that
deliberately exercise the legacy implementation) and fails if any of them contain
`from chan_strategy.signals import get_all_signals` as a **direct, unrenamed** import — i.e. NOT
matching the already-accepted `from chan_strategy.signals import get_legacy_signals as
get_all_signals` pattern A72 introduced in `skill_build/build_mapping.py` and
`skill_build/scripts/analyze_symbol.py`'s `except ImportError` fallback branches.

## Acceptance Criteria

- [ ] New guard test implemented that detects "direct unrenamed" imports of
      `chan_strategy.signals.get_all_signals` across the scanned file set, and asserts none exist
      today (the test should currently PASS, proving the codebase is currently clean).
- [ ] The guard correctly EXCLUDES: `chan_strategy/signals.py` itself (defines the deprecated
      name, doesn't "import" it); the already-accepted `get_legacy_signals as get_all_signals`
      rename pattern in `skill_build/build_mapping.py`/`skill_build/scripts/analyze_symbol.py`;
      test files that deliberately test the legacy implementation directly via `get_legacy_signals`
      (post-A72, these should already be using the new name, not the deprecated one — verify this
      is still true).
- [ ] A reverse/self-test proves the guard's detection logic actually works: construct a minimal
      violating example (e.g. a string of source text containing the banned import pattern) and
      assert the guard's scanning function flags it — do NOT insert an actual violating import into
      real production code just to test the detector; test the detector function directly against
      a synthetic string/fixture.
- [ ] No changes to `chan_strategy/signals.py`, `sell_signals.py`, or any signal-calculation logic.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped (new enforced hygiene rule is a user-visible addition).

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a73-third-audit-remediation-roadmap.md` §"A75". Third and FINAL
   task of the A73-A75 roadmap — completing this closes out the entire third audit remediation
   wave.
2. **Read claude-code's pre-promotion research above carefully** — the naive approach of grepping
   for the literal string `get_all_signals` will produce a huge false-positive list (many test
   files legitimately import `sell_signals.get_all_signals`, the production function). Your
   detector must specifically target imports FROM `chan_strategy.signals` (or
   `chan_strategy/signals.py`, however you resolve module paths) of the name `get_all_signals`
   that are NOT renamed to something else (i.e. no `as get_legacy_signals` or similar) — a plain
   AST-based scan of `ImportFrom` nodes is more reliable than regex here, but a well-anchored regex
   is also acceptable if it correctly handles the `as` rename case.
3. **Scope:** new test file(s) under `tests/unit/`. Do not touch `chan_strategy/signals.py`,
   `sell_signals.py`, `skill_build/*.py`, or any signal-calculation logic — this task only adds a
   detection/guard test, it does not change any existing import.
4. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A75-scoped files are staged.**
5. **Guardrails (reject-on-violation):** no changes to signal-calculation logic; no SimNow
   order/cancel/send paths touched; no `GOAL PASSED`; the guard test must not produce false
   positives on the existing, already-accepted `get_legacy_signals as get_all_signals` pattern (if
   it does, the review will reject).
6. **Include a Manual-verification block with natively-run counts**, and run `ruff check`
   proactively before finishing.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A75 legacy signal-path import hygiene guard implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. **This is the last task in the
   entire A73-A75 roadmap** — after this reaches `done`, trigger a fresh third-party audit per the
   standing instruction (see A73's original Background for the full "keep iterating until score >
   75, no medium+ issues" instruction, and its honest caveat that 3 of the current 6 findings may
   not be resolvable through bounded dev tasks alone).

## Decision Log

- 2026-07-15 - A75 promoted from `docs/design/a73-third-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task, immediately after A74 reached `done`. Third and final task of the third
  audit-remediation roadmap.
- 2026-07-15 (claude-code pre-promotion research) - Re-grepped the full repo for
  `get_all_signals`/`get_legacy_signals` references; found a much broader reference set than
  previously scoped (many test files legitimately reference the production
  `sell_signals.get_all_signals`). Recorded the precise distinction the guard test must make
  (direct unrenamed `chan_strategy.signals.get_all_signals` import vs. the already-accepted rename
  pattern vs. legitimate production-path references) so dev doesn't naively grep and produce noise.
- 2026-07-15 (kimi-code dev) - Implemented an AST-based detector (`ast.ImportFrom` node scan,
  checking `alias.name == "get_all_signals"` from module `chan_strategy.signals`), correctly
  independent of any local `as` rename on the importing side. Excluded `chan_strategy/signals.py`
  itself and all `tests/` files. Self-test parametrized over 8 synthetic import patterns (banned
  direct import, banned import with a local alias, the accepted `get_legacy_signals as
  get_all_signals` rename, production `sell_signals` import, plain module import, multi-name
  import statements) to prove the detector's precision.
- 2026-07-15 (claude-code independent verification, before triggering codex review) - Read the
  full detector logic: confirmed it correctly flags `get_all_signals as old_get_all_signals` (the
  banned NAME being imported, regardless of local alias) and correctly excludes
  `get_legacy_signals as get_all_signals` (a different name being renamed on import). Confirmed
  scope was clean (only A75-scoped files staged). Re-ran everything independently, matching
  kimi-code's recorded expectations: full unit suite `692 passed, 4 deselected`; `ruff check`
  clean; both `sync_check.py` gates passed; `run_next_work.ps1 -Preflight` passed.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | claude-code → kimi-code | design → dev | A75 (legacy signal-path import hygiene guard) promoted from third third-party audit remediation roadmap; handoff design->dev |
| 2026-07-15 | kimi-code → codex | dev → review | A75 legacy signal-path import hygiene guard implemented |
| 2026-07-15 | codex → codex | review → done | A75 review accepted: guard test, version/changelog, sync gates, and scoped diff verified; unit/preflight sandbox WinError 5 matched documented limitation, using recorded independent counts |
