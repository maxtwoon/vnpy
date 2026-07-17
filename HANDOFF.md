---
task: A87 - Joint-clock portfolio replay + PortfolioLedger + open-gating (block-new-opens scope)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-17
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/portfolio_engine.py
  - examples/czsc_strategy/chan_strategy/portfolio_ledger.py
  - examples/czsc_strategy/chan_strategy/config.py
  - examples/czsc_strategy/tests/unit/test_a87_joint_replay.py
  - examples/czsc_strategy/tests/unit/test_portfolio_risk.py
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

A86 (`done`) added `BacktestEngine.bar_generator()`: a generator exposing two yield points per bar
(`"pre_open"` at `bar.open`, `"post_bar"` at `bar.close`), each carrying `(kind, dt, price,
computed_equity, computed_margin)` and accepting an optional `(equity, total_open_margin)` override via
`.send()`. `run()` is unchanged (default-drains with `.send(None)` throughout). This task, A87, builds the
actual joint/coordinated portfolio replay on top of that injection point, replacing the
`NotImplementedError` at `portfolio_engine.py:610-615` (`sizing_model="risk"` + `portfolio_risk="on"`).

**Scope decision made with the user before promoting this task (2026-07-17)**: while designing this task,
claude-code found that A85's original decision ("daily loss limit breach → block new opens AND
immediately flatten all open positions") cannot be implemented purely through A86's equity/margin
injection point — forcing an already-open `Position` closed requires a new externally-triggerable
close primitive that doesn't exist yet (A86 only built an equity/margin read-and-override point, not a
force-close point). The user explicitly chose: **A87 implements block-new-opens only; forced liquidation
on breach is deferred to a separate future task (tentatively "A89")**, not implemented here. Do not
attempt to force-close positions in this task.

### The core mechanism (why no `positions.py` changes are needed)

`Position._size_open()` (`positions.py:1004-1050`) already computes:
```python
margin_cap = equity * max_margin_pct
...
if pre_open_margin + volume * required_margin_for_one > margin_cap:
    max_fit = floor((margin_cap - pre_open_margin) / required_margin_for_one)
    volume = max_fit if max_fit >= 1 else 0  # 0 means the open is skipped entirely
```
`equity` and `pre_open_margin` come directly from whatever `equity_at_entry`/`total_open_margin` the
caller injected. This means:
- Feeding the **true portfolio-wide** `equity` (currency, PnL-based) and `total_open_margin` (currency,
  sum of every symbol's occupied margin) at the `"pre_open"` yield makes the **existing**
  `max_margin_pct` config key act as a **total-portfolio margin cap** automatically — no new config key,
  no new logic, this falls out of feeding real shared numbers into code that already exists.
- To additionally enforce a **per-symbol cap** or **cluster cap** or **daily-loss-limit-active** block —
  none of which `_size_open()` natively distinguishes — feed a **deliberately saturated**
  `total_open_margin` value (`= equity * max_margin_pct`, i.e. "pretend the total cap is already fully
  used") instead of the true value, for exactly the symbols/ticks where one of those additional
  constraints is breached. `_size_open()`'s existing formula then rejects the open (`max_fit <= 0`)
  without needing to know *why* — the "why" is recorded separately in `blocked_opens` for diagnostics.
  This is the **entire gating mechanism** for this task: real numbers when nothing is breached, a
  saturated number when something is. No other code path is available or should be invented.

## Goal

### 1. New file: `chan_strategy/portfolio_ledger.py` — `PortfolioLedger` class

Tracks shared portfolio state across all symbols during the joint replay. Constructor takes `symbols`,
`initial_capital`, `corr_clusters` (reuse `STRATEGY_CONFIG["corr_clusters"]`, same case-insensitive
matching as A83's `_symbol_clusters()` — reuse that helper, don't reimplement), and reads
`max_margin_pct`, `max_symbol_margin_pct` (**new** config key, default `1.0`), `cluster_gross_cap`,
`daily_loss_limit_pct` from `STRATEGY_CONFIG`.

**Note on reusing `max_margin_pct`/`cluster_gross_cap`/`daily_loss_limit_pct`**: these keys are already
consumed by the *weight-based* `PortfolioCoordinator` (`portfolio_engine.py:84`) when
`portfolio_risk="on"` + `sizing_model!="risk"`. `PortfolioLedger` reinterprets the same key names in
*margin/currency* terms for the `sizing_model="risk"` + `portfolio_risk="on"` path. This is safe and
intentional, not an oversight: the two paths are strictly mutually exclusive (gated by `sizing_model`),
so at any given config snapshot only one interpretation is ever active. Document this explicitly in the
class docstring so a future reader isn't confused by the dual meaning.

State fields (updated once per symbol-tick, see driver algorithm below):
- `equity: float` — shared, currency-based: `initial_capital + sum_over_symbols(pnl_contribution)`
  where `pnl_contribution = computed_equity_from_yield - initial_capital` (each engine is constructed
  with the *same* `initial_capital` as the portfolio, matching A83/A84's already-verified methodology —
  do not divide capital per symbol).
- `margin_by_symbol: dict[symbol, float]` — each symbol's most recent `computed_margin` from its own
  `"post_bar"` yield (zero if the symbol hasn't started yet).
- `margin_total: float` — `sum(margin_by_symbol.values())`.
- `margin_by_cluster: dict[cluster, float]` — sum of `margin_by_symbol` for members of each cluster,
  using the case-insensitive membership map (reuse `_symbol_clusters()` from
  `diagnostics/portfolio_ledger_report.py` — import it, don't duplicate).
- `trading_day: date | None`, `day_start_equity: float`, `daily_loss_limit_active: bool` — day-rollover
  bookkeeping, using `_trading_day()` (`portfolio_engine.py:32`) with the existing `daily_agg` config,
  same as `PortfolioCoordinator._new_trading_day()`.

Methods:
- `update_trading_day(dt)`: call once per tick (before processing any symbol at that `dt`); if the
  trading day changed, reset `daily_loss_limit_active = False` and `day_start_equity = self.equity`
  (the equity as of the previous tick's close).
- `update_equity(pnl_contributions: dict[symbol, float])`: recompute `self.equity` from all known
  per-symbol pnl contributions (call after every symbol's `"post_bar"` yield in a tick, since `equity`
  is shared and any symbol's PnL affects it).
- `update_symbol_margin(symbol, margin)`: set `margin_by_symbol[symbol]`, recompute `margin_total` and
  `margin_by_cluster`.
- `check_daily_loss_limit()`: after `update_equity`, if `day_start_equity > 0` and
  `(equity - day_start_equity) / day_start_equity <= -daily_loss_limit_pct` and not already active, set
  `daily_loss_limit_active = True` and record the trigger (dt, equity, day_pnl_pct) in a
  `loss_limit_triggers: list[dict]` diagnostic list. **Do not flatten anything** — this task's scope is
  block-new-opens only (see Background).
- `pre_open_injection_for(symbol) -> tuple[float, float, str | None]`: returns
  `(equity, total_open_margin, blocked_reason)` to feed into that symbol's `"pre_open"` yield override.
  `blocked_reason` is `None` normally (feed real `self.equity`/`self.margin_total`). If
  `daily_loss_limit_active`, or `margin_by_symbol[symbol] > equity * max_symbol_margin_pct`, or any
  cluster containing `symbol` has `margin_by_cluster[cluster] > equity * cluster_gross_cap`, return
  `(self.equity, self.equity * max_margin_pct, <one short string identifying the specific reason>)` —
  the saturated value that forces `_size_open()` to reject. Check daily-loss-limit first, then
  per-symbol, then cluster (first true reason wins, for a deterministic `blocked_reason` string when
  multiple are simultaneously breached).

### 2. `PortfolioEngine._build_joint_report()` (new method in `portfolio_engine.py`)

Driver algorithm (implement exactly this shape):

1. Build one `BacktestEngine` per symbol (same constructor args as `_run_per_symbol()` uses today —
   reuse that construction logic, don't duplicate it). For each, call `engine.bar_generator(warmup_bars)`
   (default `warmup_bars=100`, matching `run()`'s default — do not hardcode a different value).
   If the result `isinstance(..., dict)` (data-load error), record it in `symbol_errors` exactly as
   `_run_per_symbol()` does today and exclude that symbol from the joint loop entirely.
2. For every successfully-started generator, prime it with `next(gen)` (equivalent to the first
   `.send(None)`) to get its first `"pre_open"` yield. Store `pending[symbol] = (kind, dt, price,
   computed_equity, computed_margin)` for each; store `None` for any symbol whose generator raised
   `StopIteration` immediately (should not happen in practice given the length checks in `run()`, but
   handle it defensively — treat as `symbol_errors[symbol] = "empty_bar_generator"`).
3. Instantiate one `PortfolioLedger(successful_symbols, self.initial_capital, corr_clusters)`.
4. Loop while any `pending[symbol]` is not `None`:
   a. `current_dt = min(item[1] for item in pending.values() if item is not None)`.
   b. `ledger.update_trading_day(current_dt)`.
   c. For each symbol with `pending[symbol][1] == current_dt`, **in sorted(symbol) order** (deterministic
      tie-break, same rationale as A85 §4 — dictionary order over the full processing unit, since this
      driver operates at bar granularity rather than per-signal granularity):
      - The pending item's `kind` must be `"pre_open"` here (a symbol only reaches `current_dt` freshly;
        if this invariant is ever violated, that's a bug — assert it).
      - `equity, margin, reason = ledger.pre_open_injection_for(symbol)`. If `reason is not None`,
        append `{"dt": current_dt, "symbol": symbol, "reason": reason}` to a `blocked_opens: list[dict]`
        diagnostic list (this is *speculative* — it does not guarantee an open was actually attempted
        this tick, only that *if* one was attempted it would have been forced to fail; that's fine, it
        mirrors how `PortfolioCoordinator.blocked_opens` already works — a record of gating pressure,
        not a proof of a specific rejected signal).
      - `item = gen.send((equity, margin))` — resumes the generator; it must yield `"post_bar"` for the
        *same* `current_dt` next (same-bar semantics, no waiting on other symbols in between the two
        yields of one bar).
      - At the `"post_bar"` yield: `ledger.update_symbol_margin(symbol, item[4])` (the *actual* resulting
        margin, reflecting whatever the pre_open injection allowed or blocked), then recompute pnl
        contribution `item[3] - engine.initial_capital` and call `ledger.update_equity(...)` with all
        symbols' latest known contributions (keep a `pnl_contributions: dict[symbol, float]` alongside
        the loop, update this symbol's entry, pass the full dict each time).
      - Send the *shared* `(ledger.equity, ledger.margin_total)` back at the `"post_bar"` yield too —
        `item2 = gen.send((ledger.equity, ledger.margin_total))` — so the engine's own recorded
        `equity_curve` entry reflects the portfolio view, not this symbol's standalone 100%-capital view
        (this is what makes the joint replay's reported equity curve meaningfully different from A83's
        independent-aggregation ledger).
      - `ledger.check_daily_loss_limit()`.
      - The generator now either yields `"pre_open"` for this symbol's *next* bar (store it in
        `pending[symbol]`) or raises `StopIteration` (its `.value` is that symbol's final report dict —
        store it in `symbol_reports[symbol]`, set `pending[symbol] = None`).
5. After the loop, assemble the joint report: `portfolio_risk="on"`, `sizing_model="risk"`,
   `initial_capital`, `period`, `symbols`, `symbol_reports`, `symbol_errors`, a combined `equity_curve`
   (one entry per unique `current_dt` processed, using `ledger.equity`/`ledger.margin_total` as recorded
   at the *last* symbol processed for that tick — since `ledger.equity` is shared/converged by the end of
   each tick's symbol loop, this is well-defined), `pairs` (every symbol's `get_combined_trades()`,
   tagged with `symbol`, sorted by `open_dt` — same shape as `_build_off_report()`/`_build_on_report()`
   already produce, for downstream compatibility), `blocked_opens`, `loss_limit_triggers` (from the
   ledger). **Do not include a `flat_events` field** — there is nothing to report since this task doesn't
   flatten anything; if useful, note in the report that forced liquidation is out of scope
   (`"flatten_on_breach": "not_implemented_see_A89"` or similar — dev's call on exact key name, just
   don't imply flattening happened).

### 3. Wire into `run()`

Replace the `NotImplementedError` block at `portfolio_engine.py:610-615` with:
```python
if sizing_model == "risk" and portfolio_risk == "on":
    return self._build_joint_report()
```
Keep the two existing branches (`_run_per_symbol()` + `_build_off_report()`/`_build_on_report()`)
completely unchanged for every other config combination.

### 4. Config

Add `max_symbol_margin_pct` to `STRATEGY_CONFIG` in `chan_strategy/config.py` with default `1.0`
(matching A85 §3's justification: a new constraint defaults to the least restrictive value — "a symbol
may use up to 100% of equity," i.e. no tighter than today's single-symbol behavior — until a user
explicitly configures it tighter; do not invent a stricter default not requested by any user).

## Acceptance Criteria

- [ ] `PortfolioLedger` correctly aggregates `equity` (currency, from PnL contributions, not
      double-counting `initial_capital`) and `margin_total`/`margin_by_cluster` (currency sums),
      verified with constructed fixtures (same `FakeEngine`-less style as A86's tests — drive real
      `bar_generator()` calls on small synthetic bar fixtures, not pre-computed curves, since this task
      tests the *live* injection interaction, not post-hoc aggregation like A83/A84 did).
- [ ] Feeding true shared `equity`/`margin_total` at `"pre_open"` makes `max_margin_pct` act as a
      total-portfolio cap: construct a fixture where two symbols' combined margin would exceed
      `equity * max_margin_pct` and confirm the second symbol's open is reduced/rejected by the existing
      `_size_open()` logic (no `positions.py` change, just confirm the existing formula does this).
- [ ] Per-symbol cap (`max_symbol_margin_pct`) rejects a symbol's own new opens once its own margin share
      exceeds the configured fraction of equity, even when total portfolio margin has headroom.
- [ ] Cluster cap (`cluster_gross_cap`) rejects a new open when the symbol's cluster's combined margin
      would exceed the cap, using case-insensitive cluster membership (reuse, don't reimplement, A83's
      `_symbol_clusters()`).
- [ ] Daily-loss-limit: once breached, new opens are blocked for the remainder of that trading day for
      *every* symbol (not just the one that triggered it); the block clears at the next trading-day
      rollover (`_trading_day()`); **no position is force-closed** (explicitly test that existing open
      positions are left alone — this proves the scope boundary is respected, not just "tests pass").
- [ ] Forward-fill/zero-outside-range semantics for a symbol's margin contribution are correct when that
      symbol has fewer bars than others (mirrors A83's `test_margin_not_carried_past_symbol_end`, applied
      to the live joint driver instead of a post-hoc ledger).
- [ ] `sizing_model="risk"` + `portfolio_risk="off"`, and `sizing_model!="risk"` + `portfolio_risk="on"`
      (the pre-existing weight-based path) are both **byte-identical** to before this task — this task
      only adds a new branch, it does not touch the other two.
- [ ] No changes to `positions.py`, `backtest_engine.py`, or any existing test's assertions.
- [ ] No forced position closure anywhere in this task's code (per the scope decision above).
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes, existing pass count
      unchanged plus new tests.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped.
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **This is the most novel/complex task in the A85→A88 sequence.** Read A86's actual implementation
   (`chan_strategy/backtest_engine.py`'s `bar_generator()`/`run()`) and its test file
   (`tests/unit/test_a86_bar_generator.py`) first, to understand exactly what the two yield points give
   you before writing the driver — do not guess at `bar_generator()`'s behavior from this HANDOFF alone.
2. **The gating mechanism is entirely "feed true numbers, or feed a saturated number to force reject."**
   Do not invent a second gating mechanism (e.g. don't try to intercept `strategy.update()` calls or
   modify `positions.py`) — everything routes through the two numbers `_size_open()` already consumes.
3. **Do not implement forced liquidation / flatten-on-breach** — this was explicitly descoped by the user
   for this task (see Background). If you find yourself needing to close a position from outside an
   engine, stop and record the gap in the Decision Log rather than inventing a new close primitive —
   that's a signal this task's scope was misunderstood.
4. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to a
   concurrent, unrelated SimNow-observation workstream. **Before committing, run `git status --short`
   and confirm only your own A87-scoped files are staged.**
5. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
6. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A87 joint-clock replay + PortfolioLedger completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes for
   environment reasons (this has happened on this machine on both A85 and A86), do not manually
   hand-edit HANDOFF.md's stage/owner fields to bypass it — leave the working tree with your changes
   uncommitted and note the failure in the Decision Log; claude-code will verify and commit properly.

## Decision Log

- 2026-07-17 - User authorized proceeding with the A86→A87→A88 implementation sequence.
- 2026-07-17 (claude-code, design) - While scoping A87, found that A85's original "block new opens AND
  flatten all positions" daily-loss-limit action cannot be built purely on A86's equity/margin injection
  point — forced position closure needs a new close primitive A86 did not build. Flagged this to the user
  via AskUserQuestion rather than silently descoping. User chose: A87 implements block-new-opens only;
  forced liquidation is a separate future task (tentatively "A89"), not attempted here.
- 2026-07-17 (claude-code, design) - Confirmed `Position._size_open()`'s existing margin-cap formula
  (`positions.py:1038-1048`) needs no changes: feeding true shared equity/margin makes `max_margin_pct`
  act as a total-portfolio cap "for free," and feeding a deliberately saturated `total_open_margin` value
  is sufficient to implement per-symbol cap, cluster cap, and daily-loss-limit rejection without touching
  `positions.py` at all. Designed `PortfolioLedger` and the joint-clock driver algorithm around this
  single mechanism to keep the implementation surface as small as possible for a task already carrying
  meaningful complexity/risk.
- 2026-07-17 (kimi-code, dev) - A87 implemented per the design. Implementation decisions, all inside
  the design's constraints:
  (a) `PortfolioLedger` takes an optional `config` param defaulting to `STRATEGY_CONFIG` (mirrors
  `PortfolioCoordinator`) for test isolation; cluster membership reuses
  `diagnostics.portfolio_ledger_report._symbol_clusters()` via a **lazy import** (a top-level import
  would be circular: diagnostics -> portfolio_engine -> portfolio_ledger); `_trading_day` is lazily
  imported from `portfolio_engine` for the same reason.
  (b) Symbol-end margin zeroing timing: the HANDOFF driver sketch did not state *when* an ended
  symbol's margin stops counting. Implemented A83's exact semantics: the symbol's own final bar still
  records its real margin, and the margin is zeroed from the first joint tick *after* its final bar
  (pinned by `test_symbol_margin_not_carried_past_symbol_end`). Its PnL contribution stays frozen at
  the last known value — equivalent to the A85 design's "mark to last price, then treat as realized"
  rule, without inventing any close primitive.
  (c) `blocked_opens` / `loss_limit_triggers` entries use `dt.isoformat(sep=" ")` strings (the sketch
  wrote raw `current_dt`); this matches `PortfolioCoordinator`'s existing diagnostic lists and is
  JSON-safe. The flatten scope-marker key is `"flatten_on_breach": "not_implemented_see_A89"`
  (dev's-call key name per Goal §5); there is deliberately no `flat_events` field.
  (d) **Only existing-test change (unavoidable, design-sanctioned)**:
  `test_run_rejects_risk_sizing_with_portfolio_risk_on` asserted the exact `NotImplementedError` this
  task removes by design (Goal §3). Keeping it unchanged would leave a permanently failing test, so it
  was replaced by `test_run_routes_risk_sizing_with_portfolio_risk_on_to_joint_replay` asserting the new
  routing. No other existing test's assertions were touched; `positions.py` and `backtest_engine.py`
  are untouched.
  (e) Extracted `_make_symbol_engine()` from `_run_per_symbol()` (pure extraction, behavior-identical)
  to satisfy "reuse that construction logic, don't duplicate it" — the `off`/weight-`on` branches route
  through the same construction code as before (covered by the existing snapshot/regression tests plus
  the new `test_run_routes_all_config_combinations`).

## Manual Verification

(kimi-code's dev round completed the implementation and got all gates green, but its final
`handoff.py next` transaction hit the pipeline's 3600s timeout right at the finish line while rewriting
this section — same environment-timing issue seen on A85/A86. claude-code independently re-ran every
command below from a clean shell before committing.)

```text
$ python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
751 passed, 4 deselected in 45.41s

$ ruff check examples/czsc_strategy/chan_strategy/portfolio_engine.py \
             examples/czsc_strategy/chan_strategy/portfolio_ledger.py \
             examples/czsc_strategy/chan_strategy/config.py \
             examples/czsc_strategy/tests/unit/test_a87_joint_replay.py \
             examples/czsc_strategy/tests/unit/test_portfolio_risk.py
All checks passed!

$ python tools/sync_check.py
[SYNC-CHECK][OK] 版本单一真相 = 4.4.0  (source: vnpy/__init__.py::__version__)
[SYNC-CHECK] PASS: 版本与文档一致。

$ python tools/sync_check.py --root examples/czsc_strategy
[SYNC-CHECK][OK] 版本单一真相 = 0.2.23  (source: VERSION::) <!-- synccheck:ignore -->
[SYNC-CHECK] PASS: 版本与文档一致。

$ powershell -ExecutionPolicy Bypass -File examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight
==> Run SimNow workflow unit tests
192 passed in 16.95s
==> Preflight complete; live SimNow capture was not requested
```

Independent code review by claude-code before committing: read `portfolio_ledger.py` (187 lines) and the
`_build_joint_report()` driver in full; confirmed the gating mechanism uses only the documented
true-vs-saturated equity/margin injection (no `positions.py` changes, no force-close anywhere); confirmed
the one existing-test change (`test_run_rejects_risk_sizing_with_portfolio_risk_on` →
`test_run_routes_risk_sizing_with_portfolio_risk_on_to_joint_replay`) is the unavoidable, design-sanctioned
update the Decision Log describes, using a monkeypatched sentinel rather than re-testing the full joint
report inline; confirmed `git status --short` shows only A87-scoped files.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-17 | claude-code → kimi-code | design → dev | A87 (joint-clock replay + PortfolioLedger, block-new-opens scope) promoted; handoff design->dev |
