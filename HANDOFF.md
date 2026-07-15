---
task: A74 - Formal-Evaluation Entry Point Defaulting to risk+enforce
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a73-third-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
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
the shared `STRATEGY_CONFIG` dict itself (save old values → set new values → run → restore old
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

- [ ] A new, explicit entry point exists that runs backtests with `sizing_model="risk"` and
      `limit_halt_model="enforce"` active, WITHOUT modifying `STRATEGY_CONFIG`'s default dict
      values in `config.py`.
- [ ] The override mechanism is verified to fully restore the original config values afterward,
      even if the backtest run raises an exception (e.g. via `try/finally` or a context manager) —
      a test must prove this (run the new entry point, then assert `STRATEGY_CONFIG["sizing_model"]`
      /`STRATEGY_CONFIG["limit_halt_model"]` are back to their pre-call values, including after a
      simulated failure).
- [ ] The new entry point's output includes A70's `mode_label` field, and it correctly reflects the
      non-default state (i.e. NOT `"RESEARCH_BASELINE"`) when running through this path.
- [ ] Every existing caller of `BacktestEngine`/`run_chan_backtest.py`/existing `diagnostics/*.py`
      scripts that does NOT use the new entry point has completely unchanged behavior — all existing
      tests pass unmodified, with no changes to their assertions.
- [ ] New unit tests cover: the new entry point produces `risk`+`enforce` behavior; config is fully
      restored after both success and failure; `mode_label` is correct.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a73-third-audit-remediation-roadmap.md` §"A74". Second of three
   A73-A75 tasks.
2. **Read the "Important technical fact" in Goal above before designing your approach** — verify
   the cited line numbers yourself (`backtest_engine.py:342`, `:346`, `:669-671`, `:699`) since
   design docs can drift from code; this repo's established practice is to re-verify cited lines,
   not trust them blindly.
3. **Scope:** likely `run_chan_backtest.py` (or a new script) plus possibly a small addition to
   `chan_strategy/backtest_engine.py` if a context-manager helper is added there. Do NOT modify
   `STRATEGY_CONFIG`'s or `BACKTEST_CONFIG`'s default dict VALUES in `config.py` — adding a new
   entry-point mechanism is fine; changing what the dict defaults to is not.
4. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A74-scoped files are staged.**
5. **Guardrails (reject-on-violation):** no changes to `STRATEGY_CONFIG`/`BACKTEST_CONFIG` default
   dict values; no threshold tuning; no pre-2026-04-24 data for any new parameter choice; no SimNow
   order/cancel/send paths touched; no `GOAL PASSED`; the override MUST be provably restored even on
   exception — an override that leaks into subsequent unrelated test runs (test-pollution) is a
   reject-worthy bug, test for it explicitly.
6. **Include a Manual-verification block with natively-run counts**, and run `ruff check`
   proactively before finishing.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A74 formal-evaluation risk+enforce entry point implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-15 - A74 promoted from `docs/design/a73-third-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task, immediately after A73 reached `done`. Second of three tasks in the third
  audit-remediation roadmap.
- 2026-07-15 (claude-code pre-promotion research) - Confirmed `BacktestEngine` has no per-instance
  override for `sizing_model`/`limit_halt_model` — all reads are direct `STRATEGY_CONFIG.get(...)`
  calls at multiple points in `backtest_engine.py`. Recorded this as the key implementation
  constraint dev must design around (save/restore context manager, or thread constructor params
  through with justification).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | claude-code → kimi-code | design → dev | A74 (formal-evaluation risk+enforce entry point) promoted from third third-party audit remediation roadmap; handoff design->dev |
