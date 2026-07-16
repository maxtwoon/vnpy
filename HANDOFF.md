---
task: A86 - BacktestEngine per-bar generator extraction (external equity/margin injection point)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-17
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/backtest_engine.py
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

Per the user's explicit go-ahead ("按照建议执行", 2026-07-17) after reviewing claude-code's scope/effort
estimate for A85's Phase 2 implementation, the work is split into three tasks: **A86** (this task,
lowest-risk first step), **A87** (joint-clock driver + `PortfolioLedger` + gating, built on A86), **A88**
(real-data acceptance check, mirroring A84's pattern). This task is A86 only — do not attempt A87/A88.

`docs/design/a85-joint-replay-design.md` (accepted, `done`) decided the joint clock must drive multiple
symbols' bar processing in lockstep, feeding each symbol a *shared, portfolio-level* `equity`/
`total_open_margin` at each tick instead of each symbol's own 100%-capital view. Today,
`BacktestEngine.run()` (`chan_strategy/backtest_engine.py:393-758`) is a single monolithic per-bar loop
(`for i in range(warmup_bars, len(trade_bars)):` at line 536) that always computes its own
`equity_at_entry`/`total_open_margin` via `self._compute_equity_and_margin()` (line 760) at exactly two
points: line 569 (pre-open, using `bar.open`) and line 649 (post-signal, using `bar.close`, only inside
`if risk_mode:`). `Position._size_open()` (`positions.py:1004`) already accepts `equity_at_entry`/
`total_open_margin` as parameters and already rejects opens when the injected equity/margin implies
insufficient headroom — so once a *shared* value can be fed in at those two points, the existing
position-sizing/margin-cap logic in `positions.py` will organically enforce joint gating **without any
change to `positions.py` itself**. claude-code confirmed this by reading `_open_long`/`_open_short`/
`_size_open` directly.

**The missing piece is purely mechanical**: `run()`'s loop currently cannot be paused/resumed bar-by-bar
by an external driver — it runs start-to-finish in one call. A87's joint-clock driver needs to advance
multiple `BacktestEngine` instances in lockstep (process symbol A's bar at timestamp T, then symbol B's
bar at timestamp T, before either moves to T+1), computing the shared ledger state between each step.
That requires `run()`'s loop to become **externally steppable**.

## Goal

Convert the per-bar loop body currently inside `run()` (lines 536-757) into a **generator**, with **two
`yield` points** — one right before each of the two existing `self._compute_equity_and_margin(...)` calls
(line 569 and line 649) — so an external driver can `.send()` in a `(equity, total_open_margin)` override
tuple instead of letting the engine compute its own. `run()` itself becomes a thin wrapper that fully
drains the generator with `gen.send(None)` at every step (meaning "no override, compute internally as
before") — this must reproduce **exactly** today's behavior, byte-for-byte, since nothing outside this
task changes how `run()` is called.

### Precise implementation shape (do not deviate — this specific shape avoids the biggest risk)

- **Do NOT extract the loop into a separate class method with an explicit parameter list.** The loop body
  currently closes over ~15 local variables from `run()`'s setup section (`trade_bars`, `czsc_trade`,
  `czsc_daily`, `czsc_4h`, `daily_bars`, `daily_bar_idx`, `h4_bars`, `h4_bar_idx`, `trade_freq_name`,
  `filter_freq_name`, `sizing_model`, `risk_mode`, `limit_active`, `prev_close_map`, `symbol_limit`,
  `rollover_gating_active`, `excluded_dates`, `pending_signals`, etc.). Hoisting all of these into method
  parameters or instance attributes is exactly the kind of large, error-prone refactor that risks a subtle
  behavior change in the project's most heavily-tested code path. Instead:
- **Define the generator as a nested function inside `run()`** (e.g. `def _bar_loop():` defined after line
  535, before the current `for i in range(...)` statement), so it captures all of `run()`'s existing
  locals via normal Python closure — no parameter list needed, no local variable renamed or moved.
  Convert the existing `for i in range(warmup_bars, len(trade_bars)):` loop (currently at module level
  inside `run()`) to live inside this nested function, unchanged internally except for the two inserted
  `yield` statements described below.
- **Yield point 1** (replaces line 569's direct call): where the code currently does
  `equity_at_entry, total_open_margin = self._compute_equity_and_margin(bar.open)` inside `if risk_mode:`,
  change to:
  ```python
  equity_at_entry, total_open_margin = self._compute_equity_and_margin(bar.open)
  override = yield ("pre_open", bar.dt, bar.open, equity_at_entry, total_open_margin)
  if override is not None:
      equity_at_entry, total_open_margin = override
  ```
- **Yield point 2** (replaces line 649's direct call): where the code currently does
  `equity, total_open_margin_now = self._compute_equity_and_margin(bar.close)` inside `if risk_mode:`,
  apply the same pattern with a `"post_bar"` tag instead of `"pre_open"`.
- **`run()`'s driving loop** (replaces the old bare `for i in range(...)` at the top level of `run()`):
  ```python
  gen = _bar_loop()
  try:
      to_send = None
      while True:
          gen.send(to_send)
          to_send = None  # default drain: no override, ever — behavior must be identical to today
  except StopIteration:
      pass
  ```
  This is the **default-drain wrapper**; it must produce byte-identical output to the current code for
  every existing test, since `to_send` is always `None`.
- **Public step interface for a future external driver (A87)**: expose the generator itself via a new
  method, e.g. `BacktestEngine.bar_generator(self, warmup_bars=100)` that does everything `run()`'s setup
  currently does (lines 393-535, unchanged) and then `return`s the nested generator object instead of
  draining it — so A87's future joint-clock driver can call `engine.bar_generator()`, get the generator,
  and manually alternate `.send(...)` calls across multiple engines. **Do not implement the joint driver
  itself in this task** — just expose this generator-returning method; `run()` should internally call it
  and drain it for its own use, so there is exactly one code path for the loop, not two copies.
- Everything before line 536 (data loading, CZSC init, config resolution) and everything after line 757
  (post-loop rollover tagging, `generate_report()`) stays **completely unchanged** — only the loop body
  itself becomes a generator with two yield points.

## Acceptance Criteria

- [ ] `BacktestEngine.run()` produces byte-identical `equity_curve`/`trades`/report output to before this
      change, on every existing test and on a real-data smoke run (compare a report field-by-field, not
      just "tests still green" — equity_curve values must match to full float precision, not just
      approximately).
- [ ] A new `bar_generator()` (or equivalently named) method exists that returns the same generator
      `run()` uses internally, exposing exactly two yield points (`"pre_open"` and `"post_bar"`) tagged
      with `(kind, dt, price, computed_equity, computed_margin)`, accepting an optional
      `(equity, total_open_margin)` override via `.send()`.
- [ ] A new test file demonstrates: (a) fully-draining the generator with `.send(None)` throughout
      reproduces the exact same `equity_curve`/report as calling `run()` directly on the same engine
      config; (b) sending a deliberately different `(equity, total_open_margin)` override at a `pre_open`
      yield changes the resulting `Position._size_open()` lot sizing for that bar (proving the injection
      point actually reaches position sizing, not just a dead parameter).
- [ ] No change to `positions.py`, `portfolio_engine.py`, or any existing test's assertions.
- [ ] No change to the `sizing_model="risk" + portfolio_risk="on"` `NotImplementedError` gate in
      `portfolio_engine.py:610-615` — this task does not touch portfolio-level code at all, only
      `BacktestEngine`.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes with the exact same
      pass count as before this change plus the new test file's tests (no existing test's outcome changes).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped.
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **This is the highest-risk task in the current A85/A86/A87/A88 sequence** — it touches the single most
   heavily-tested code path in the project (every existing acceptance/regression test depends on
   `BacktestEngine.run()`'s exact numeric output). Go slowly. Diff the generated `equity_curve` against a
   pre-change baseline run on at least one real symbol before considering this done, not just "pytest is
   green" — pytest fixtures may not exercise every code branch (e.g. `risk_mode=False` legacy path,
   `resonance_filter="daily_4h"`, `limit_active`, `rollover_gating_active` all have separate branches
   inside the loop that must all still work identically inside the generator).
2. **Follow the exact nested-generator-closure shape described above.** Do not hoist loop-local variables
   into method parameters or instance attributes — that's a bigger, riskier refactor than necessary and
   is explicitly NOT what this task asks for.
3. **Do not implement A87's joint-clock driver or `PortfolioLedger` in this task.** This task's only job
   is making `BacktestEngine`'s loop externally steppable and proving the injection point reaches position
   sizing. The actual multi-symbol coordination is A87, not yet promoted.
4. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to a
   concurrent, unrelated SimNow-observation workstream. **Before committing, run `git status --short`
   and confirm only your own A86-scoped files are staged.**
5. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
6. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A86 BacktestEngine generator extraction completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the transactional command itself
   crashes for environment reasons (this has happened before on this machine), do not manually hand-edit
   HANDOFF.md's stage/owner fields to bypass it — leave the working tree with your changes uncommitted
   and note the failure in the Decision Log; claude-code will verify and commit properly.

## Decision Log

- 2026-07-17 - User reviewed claude-code's A85-implementation scope/effort estimate and explicitly said
  to proceed per the recommended 3-task split (A86 → A87 → A88), starting now.
- 2026-07-17 (claude-code, design) - Read `BacktestEngine.run()` in full (lines 393-758) to scope A86
  precisely. Confirmed the two exact call sites needing injection (line 569 pre-open, line 649 post-bar)
  and confirmed `Position._size_open()` already honors injected `equity_at_entry`/`total_open_margin` for
  margin-cap rejection, meaning A87 will not need to touch `positions.py` at all once this injection point
  exists. Chose nested-generator-closure over method-parameter-hoisting specifically to minimize risk to
  the most heavily-tested code path in the project — hoisting ~15 loop-local variables into an explicit
  parameter list was assessed as needlessly increasing surface area for a subtle regression.

## Manual Verification

(dev to fill in with actual command output before requesting review)

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-17 | claude-code → kimi-code | design → dev | A86 (BacktestEngine generator extraction) promoted; handoff design->dev |
