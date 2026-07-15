---
task: A74 - Formal-Evaluation Entry Point Defaulting to risk+enforce
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a73-third-audit-remediation-roadmap.md
  - examples/czsc_strategy/chan_strategy/backtest_engine.py
  - examples/czsc_strategy/run_formal_evaluation.py
  - examples/czsc_strategy/tests/unit/test_formal_evaluation.py
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

Second of three tasks (A73-A75) from the third third-party audit remediation roadmap
(`docs/design/a73-third-audit-remediation-roadmap.md`), promoted after A73 reached `done` (codex
accepted on the first review round).

The audit (67/100) found that the default `sizing_model="research"` + `limit_halt_model="off"`
means the default backtest path doesn't reflect real contract-multiplier/margin-constrained P&L or
limit/halt fill rejection, and recommended defaulting "formal evaluation" to `risk`+`enforce`.
**We are NOT changing `chan_strategy/config.py`'s `STRATEGY_CONFIG` default dict values** — that
would violate this entire project's "gated config defaults to byte-identical legacy behavior" house
style and would require re-auditing every existing equivalence-snapshot test that assumes
`research`/`off` defaults. Instead: add a new, explicit "formal evaluation" entry point that
overrides these two knobs only within its own run, leaving every existing caller's behavior
untouched.

**Full contract**: `docs/design/a73-third-audit-remediation-roadmap.md` §"A74" (this HANDOFF
summarizes it — read the full Rationale/Semantics there before writing code).

## Goal

Add a new, explicit entry point for "formal evaluation" that runs with `sizing_model="risk"` and
`limit_halt_model="enforce"` by default, without touching `STRATEGY_CONFIG`'s actual default dict
values in `config.py`.

**Important technical fact, verified by claude-code before writing this HANDOFF**:
`BacktestEngine` reads `sizing_model`/`limit_halt_model`/`portfolio_risk` directly from the
module-level `STRATEGY_CONFIG` dict at multiple points at runtime (`backtest_engine.py:342`,
`:346`, `:669-671`, `:699` — confirmed via direct grep) — **there is no per-instance constructor
parameter to override these**. This means the override mechanism must be a temporary mutation of
the shared `STRATEGY_CONFIG` dict itself (save old values → set new values → restore old
values in a `finally` block, e.g. a context manager), not a constructor argument. Any implementation
that tries to pass these as `BacktestEngine(...)` kwargs will not work without also modifying
`BacktestEngine.__init__`/`generate_report` to accept overrides — if dev judges that constructor-
parameter threading is actually cleaner than a save/restore context manager, that's an acceptable
alternative, but it touches more of `BacktestEngine`'s surface and must be justified in the Decision
Log; the context-manager approach is recommended as the smaller, safer diff.

The specific form of the new entry point (a CLI flag on `run_chan_backtest.py`, e.g.
`--formal-eval`, or a new standalone script e.g. `run_formal_evaluation.py`) is dev's call — record
the choice and reasoning in the Decision Log.

## Acceptance Criteria

- [x] A new, explicit entry point exists that runs backtests with `sizing_model="risk"` and
      `limit_halt_model="enforce"` active, WITHOUT modifying `STRATEGY_CONFIG`'s default dict
      values in `config.py`.
- [x] The override mechanism is verified to fully restore the original config values afterward,
      even if the backtest run raises an exception (e.g. via `try/finally` or a context manager) —
      a test must prove this (run the new entry point, then assert `STRATEGY_CONFIG["sizing_model"]`
      /`STRATEGY_CONFIG["limit_halt_model"]` are back to their pre-call values, including after a
      simulated failure).
- [x] The new entry point's output includes A70's `mode_label` field, and it correctly reflects the
      non-default state (i.e. NOT `"RESEARCH_BASELINE"`) when running through this path.
- [x] Every existing caller of `BacktestEngine`/`run_chan_backtest.py`/existing `diagnostics/*.py`
      scripts that does NOT use the new entry point has completely unchanged behavior — all existing
      tests pass unmodified, with no changes to their assertions.
- [x] New unit tests cover: the new entry point produces `risk`+`enforce` behavior; config is fully
      restored after both success and failure; `mode_label` is correct.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/diagnostics/`) passes.
- [x] VERSION/CHANGELOG bumped.

## Manual Verification (natively-run counts)

- `python -m ruff check examples/czsc_strategy/chan_strategy/backtest_engine.py examples/czsc_strategy/run_formal_evaluation.py examples/czsc_strategy/tests/unit/test_formal_evaluation.py` — All checks passed.
- `python -m pytest examples/czsc_strategy/tests/unit/test_formal_evaluation.py -q -m "not realdb"` — 6 passed.
- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` — 683 passed, 4 deselected.
- `python tools/sync_check.py` — PASS.
- `python tools/sync_check.py --root examples/czsc_strategy` — PASS.
- `examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight` — Preflight complete; 191 SimNow workflow unit tests passed.

## Notes for the Next Agent

(review = codex must read this before reviewing)

1. **Entry point:** `docs/design/a73-third-audit-remediation-roadmap.md` §"A74". Second of three
   A73-A75 tasks.
2. **Scope of changes:** `chan_strategy/backtest_engine.py` adds `formal_evaluation_config()` and
   `run_formal_evaluation()`; `run_formal_evaluation.py` is the standalone CLI entry point;
   `tests/unit/test_formal_evaluation.py` covers the new behavior. `config.py` defaults are
   untouched.
3. **Guardrails checked:** no `STRATEGY_CONFIG`/`BACKTEST_CONFIG` default dict values changed;
   no threshold tuning; no SimNow order/cancel/send paths touched; no `GOAL PASSED`.
4. **Before committing, run `git status --short`** and confirm only A74-scoped files are staged
   (the unrelated SimNow-observation files remain modified in the working tree and must not be
   committed with this task).

## Decision Log

- 2026-07-15 - A74 promoted from `docs/design/a73-third-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task, immediately after A73 reached `done`. Second of three tasks in the third
  audit-remediation roadmap.
- 2026-07-15 (claude-code pre-promotion research) - Confirmed `BacktestEngine` has no per-instance
  override for `sizing_model`/`limit_halt_model` — all reads are direct `STRATEGY_CONFIG.get(...)`
  calls at multiple points in `backtest_engine.py`. Recorded this as the key implementation
  constraint dev must design around (save/restore context manager, or thread constructor params
  through with justification).
- 2026-07-15 (kimi-code dev) - Re-verified `STRATEGY_CONFIG.get("sizing_model")` / `limit_halt_model`
  reads at `backtest_engine.py:342`, `:346`, `:669-671`, `:699`. Confirmed no per-instance override
  exists; adopted the recommended save/restore context-manager approach as the smaller, safer diff.
- 2026-07-15 (kimi-code dev) - Entry point form: added both a reusable context manager
  `formal_evaluation_config()`, a helper `run_formal_evaluation()`, and a standalone script
  `run_formal_evaluation.py`. Rationale: the context manager makes the override/restore contract
  explicit and testable; the helper lets scripts and tests call it without duplicating the override
  logic; the standalone script is the explicit user-facing entry point requested by the audit.
- 2026-07-15 (claude-code independent verification, before triggering codex review) - Read the full
  diff: `formal_evaluation_config()` correctly saves/restores both keys including the edge case of
  pre-existing non-default values (verified via the dedicated test
  `test_formal_evaluation_config_restores_non_default_original_values`); `run_formal_evaluation()`
  wraps `run_single_backtest()` inside the context manager so `generate_report()`'s `mode_label`
  computation (A70) correctly sees the overridden values. Confirmed `config.py`'s
  `sizing_model`/`limit_halt_model` default dict values are unchanged (still `"research"`/`"off"`).
  Re-ran everything independently, matching kimi-code's recorded counts exactly: full unit suite
  `683 passed, 4 deselected`; `ruff check` clean; both `sync_check.py` gates passed;
  `run_next_work.ps1 -Preflight` passed. Scope was clean (only A74-scoped files staged).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | claude-code → kimi-code | design → dev | A74 (formal-evaluation risk+enforce entry point) promoted from third third-party audit remediation roadmap; handoff design->dev |
| 2026-07-15 | kimi-code → codex | dev → review | A74 formal-evaluation risk+enforce entry point implemented |
