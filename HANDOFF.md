---
task: A48 P8b - Portfolio Risk (Cross-Symbol Coordinator)
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-12
deliverables:
  - HANDOFF.md
  - docs/design/a38-phase-contracts-p2-p8.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

Final task of the P1-P8 roadmap, started after A47 (P8a exit overhaul) reached `done` — the
design's own note explicitly required P8a ship and pass review before P8b even starts. P1-P7 and
P8a are all `done`.

**Task-ID renumbering (unchanged from A43-A47's note):** the phase-contracts doc's original
`Task mapping` (`P8=A45`) is stale — A45 is actually P6 under the 2026-07-12 renumbering.
Confirmed mapping: **P4=A43 (done), P5=A44 (done), P6=A45 (done), P7=A46 (done), P8a=A47 (done),
P8b=A48 (this task, final).**

`key_trade_behavior_review.md` found sub-strategies run fully independently (each symbol its own
`BacktestEngine` instance, confirmed 2026-07-12 — `BacktestEngine.__init__` takes a single
`symbol: str`, no cross-symbol state) with fixed weights (`pos_1buy=0.10`, `pos_2buy=0.20`,
`pos_3buy=0.30`, confirmed at `chan_strategy/config.py:20-22`, unchanged) that overweight the
worst-performing 三买 and no portfolio heat control across correlated symbols (RB/ZN/SC co-move).
Confirmed 2026-07-12: no `portfolio_risk` config, `corr_clusters`, `cluster_gross_cap`,
`daily_loss_limit_pct`, `weighting` key, or `portfolio_engine.py` file exists yet — no drift since
the phase-contracts draft was written.

Full contract: `docs/design/a38-phase-contracts-p2-p8.md` §"P8 (A45) - Exit Overhaul + Portfolio
Risk", specifically the **P8b** subsection (the section header still says A45 — that is the stale
label; this task's real ID is A48, content is otherwise authoritative and unchanged). This is the
LAST task in the P1-P8 roadmap — no further phase follows.

## Goal

Add `portfolio_risk` config gate (`"off"` default, current behavior | `"on"`). Introduce a
portfolio coordinator ABOVE the existing per-symbol `BacktestEngine` runs — either a new
`PortfolioEngine` class (in a new `chan_strategy/portfolio_engine.py`) or a cross-symbol pass over
existing per-symbol run outputs; dev's choice on implementation shape, but it must be
backtest-only (no live coordinator, no SimNow changes) and must not require rewriting
`BacktestEngine`'s existing single-symbol run loop.

Under `"on"`:
- `weighting="risk_parity"` (new key, `"fixed"` default = legacy `pos_1buy`/`pos_2buy`/`pos_3buy`
  weights unchanged): weights proportional to `1/vol` (or historical expectancy × `1/vol`)
  instead of the fixed 10/20/30 split.
- `corr_clusters` (new key, e.g. `{"industrial_energy": ["RB888","ZN888","SC888"]}`): summed
  gross weight within a cluster cannot exceed `cluster_gross_cap` (new key, default `1.0`); new
  opens that would breach it are blocked.
- `daily_loss_limit_pct` (new key, default `0.03`): if a day's portfolio PnL <=
  `-daily_loss_limit_pct`, flatten all positions and block new opens for the remainder of that
  trading day.

Add read-only `portfolio_heat_report.py`: cluster gross exposure over time, count of loss-limit
trigger days, risk-parity vs fixed weights, on the honest post-2026-04-24 baseline (report only,
not for in-task selection).

## Acceptance Criteria

- [ ] `portfolio_risk="off"` (default) -> equity curve and every `Position.pairs` entry
      byte-identical to current, per symbol AND in aggregate (full-`BacktestEngine` equivalence
      test with a git-tracked golden snapshot, per the A44-A47 house pattern — do not ship with
      only a signal-filter unit check). This is the ONE required equivalence proof for this task.
- [ ] `portfolio_risk="on"`: a fixture breaching `cluster_gross_cap` blocks the offending new
      open (asserted: post-open gross exposure within the cluster <= cap) — unit-tested with a
      constructed multi-symbol scenario.
- [ ] `portfolio_risk="on"`: a fixture where a day's cumulative portfolio PnL breaches
      `-daily_loss_limit_pct` flattens all open positions and blocks new opens for the remainder
      of that trading day (unit-tested); the next trading day resumes normally.
- [ ] `weighting="risk_parity"` -> weights are computed from real per-symbol volatility (not a
      hardcoded/tuned constant), unit-tested against a fixture with known relative volatilities
      (higher-vol symbol gets a smaller weight than lower-vol symbol, all else equal).
      `weighting="fixed"` (default) reproduces the exact legacy `pos_1buy`/`pos_2buy`/`pos_3buy`
      split.
- [ ] The portfolio coordinator does not read future bars for any symbol when making a
      cross-symbol decision — the cross-symbol pass aligns on trading-day boundaries (P2b/A39's
      `daily_agg="trading_calendar"` concept, or the natural daily boundary if `daily_agg` is
      still `"natural"`) without peeking ahead (unit/replay-tested no-lookahead check, mirroring
      the existing `test_daily_no_lookahead`/`test_4h_no_lookahead` pattern).
- [ ] `portfolio_heat_report.py` generated (report only, RESEARCH-ONLY banner
      `Diagnostic only, not a trading recommendation.`); NOT used to select/tune
      `cluster_gross_cap`/`daily_loss_limit_pct`/`corr_clusters` membership in-task. Must be
      regenerated with the script's own real default symbols on the post-2026-04-24 window
      (`WINDOW_START="2026-04-24"`, `WINDOW_END="2026-07-09"`, matching every A43-A47 report
      script's precedent) — verify the output before committing; do not ship a placeholder/empty
      report (A45's and A46's first dev rounds each shipped a broken report and had to be
      corrected after the fact; A47's got this right from the start — follow that precedent).
- [ ] No threshold tuning via backtest/capture-data selection; no pre-2026-04-24 data used for
      any parameter choice; no SimNow order/cancel/send path changed; no `GOAL PASSED`; the
      portfolio coordinator is backtest-only (no live order routing); does not touch exit logic
      (P8a/A47's scope, done) or position sizing's per-trade formula (P3/A40's scope, only the
      cross-symbol weighting layer is new here).
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes — this script
      genuinely exists at `diagnostics/run_next_work.ps1`; verify the path carefully before
      claiming otherwise (A44's dev round falsely claimed it was absent).

## Manual Verification / Notes for reviewer (claude-code, 2026-07-12)

Ran the full suite natively: `python -m pytest examples/czsc_strategy/tests/unit -q -m "not
realdb"` -> **521 passed, 4 deselected**. Both `sync_check` gates PASS. Diff scope confirmed
clean (no SimNow files, no changes to `_size_open`'s formula or the exit priority chains beyond
the new additive `flatten_all_positions` helper).

Found two issues while reading the diff that no existing test catches — flagging for the
reviewer's judgment rather than fixing myself (dev's job per role division):

1. **Daily-loss-limit flatten does not propagate into the reported portfolio pairs/equity.**
   `PortfolioCoordinator._flatten_all` (in `portfolio_engine.py`) clears the *coordinator's own*
   `self.open_positions` dict and logs `flat_events` for evidence — but `PortfolioEngine.
   _build_on_report` maintains a **separate, local** `open_positions` dict (used to build
   `coordinated_pairs` and the unrealized-PnL portion of the reported equity curve) that
   `_flatten_all` never touches. When the daily loss limit triggers mid-day, a still-open
   position keeps accruing unrealized PnL in the reported equity curve past the trigger bar, and
   its eventual `coordinated_pairs` entry reports the ORIGINAL close price/date from that
   symbol's independent, uncoordinated backtest — not a forced early close at the flatten bar.
   `test_daily_loss_limit_flattens_and_blocks_then_resets_next_day` only exercises
   `PortfolioCoordinator` in isolation (constructed `on_bar`/`allow_open`/`record_open` calls) and
   passes; there is no test that runs `PortfolioEngine._build_on_report`'s actual replay and
   asserts the reported pairs/equity reflect an early close at the trigger bar. This looks like a
   real gap against the acceptance criterion "flattens all open positions... for the remainder of
   that trading day" — as currently wired, the *report* does not reflect the flatten, only the
   coordinator's internal exposure bookkeeping does (which does correctly block new opens for the
   rest of the day — that part is real and tested).
2. **`BacktestEngine.run(..., coordinator=None)` and its `_filter_signals_for_coordinator`/
   `_update_coordinator_after_bar`/`self._coordinator` machinery (all new in this diff) appear to
   be dead code** — grepped the full `examples/czsc_strategy` tree (including tests) for
   `coordinator=` passed to `BacktestEngine.run(...)` or `.run(coordinator=`: zero hits outside
   the parameter's own definition. `PortfolioEngine._run_per_symbol` calls `engine.run()` with no
   `coordinator` argument every time; the actual coordination happens entirely via the separate
   post-hoc trade-replay in `PortfolioEngine._build_on_report`/`_build_on_report`. If this
   `BacktestEngine`-level wiring genuinely isn't used by the final design, it should probably be
   removed rather than shipped as unreachable code; if it *was* meant to be the real mechanism
   (which would also resolve finding #1, since a coordinator wired directly into the per-symbol
   run loop would make blocked opens genuinely never execute in that symbol's own state), that's
   a more substantial rework. Flagging for the reviewer/next dev round to decide which path to
   take — not a call I'm making myself.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

### Codex review reject findings (2026-07-12)

1. **Blocker: daily-loss-limit flatten is not reflected in `PortfolioEngine`'s reported pairs or
   equity.** `PortfolioCoordinator._flatten_all()` clears only the coordinator's own
   `open_positions`, but `PortfolioEngine._build_on_report()` keeps a separate local
   `open_positions` ledger for `coordinated_pairs`, `gross_exposure`, and unrealized PnL. A
   minimal in-memory replay produced one `flat_event` at `2024-01-02 09:00:00`, but the reported
   pair still closed at the original independent-backtest close `2024-01-03 09:00:00` with
   `close_price=120.0`, and the trigger-bar equity row still reported `gross_exposure=0.1`.
   This fails the acceptance item that a daily-loss breach flattens all open positions and blocks
   new opens for the rest of the day. Add an end-to-end `PortfolioEngine` replay test, not only a
   `PortfolioCoordinator` unit test, and make the report's pairs/equity reflect the forced close
   at the flatten bar.
2. **Related: daily-loss decisions are based on standalone per-symbol equity, not coordinated
   portfolio equity.** `_build_on_report()` calls `coordinator.on_bar(dt, prices,
   per_symbol_equity)` before recomputing the filtered/coordinated equity, so blocked trades from
   the independent per-symbol backtests can still influence the loss-limit trigger. The acceptance
   criterion says the day's cumulative *portfolio* PnL triggers flattening; compute this from the
   coordinated realized+unrealized ledger.
3. **Clean up or complete the unused `BacktestEngine.run(coordinator=...)` path.** The new
   `backtest_engine.py` wiring calls coordinator APIs named `can_open`, `get_weights`, and
   `update_after_bar`, but `PortfolioCoordinator` exposes `allow_open`, `_position_weight`, and
   `on_bar`. `PortfolioEngine._run_per_symbol()` never passes a coordinator, so this path is
   currently unreachable and would raise if used. Either remove it to keep the cross-symbol pass
   surgical, or implement and test the API if it is meant to be the real coordinator path.
4. **Before resubmitting review:** rerun the acceptance gates. In this Codex sandbox,
   `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` and
   `diagnostics/run_next_work.ps1 -Preflight` both hit the documented `PermissionError:
   [WinError 5]` temp-directory setup failure, so those sandbox failures were not treated as code
   defects. The handoff currently records a native unit-test pass (`521 passed, 4 deselected`) and
   sync-check passes, but no native preflight pass was recorded in the manual notes I found.

1. **Entry point:** `docs/design/a38-phase-contracts-p2-p8.md`, section "P8 (A45) - Exit Overhaul
   + Portfolio Risk", **P8b subsection only**. Ignore the stale `(A45)` label in the header, this
   task's real ID is **A48**. Full dev prompt and review checklist are in that section.
2. **Scope:** a new `chan_strategy/portfolio_engine.py` (or equivalent cross-symbol pass — dev's
   implementation choice) plus wiring in `backtest_engine.py` to run it when `portfolio_risk=
   "on"`, and `chan_strategy/config.py` (new keys). Do not touch `positions.py`'s exit logic
   (P8a/A47, done) or `_size_open`'s per-trade formula (P3/A40, done) — this phase adds a
   cross-symbol coordination LAYER on top of existing per-symbol sizing/exits, it does not modify
   them.
3. **This is the final task in the roadmap** — no further phase depends on this one; there is no
   P9. Take the time to get the equivalence proof and no-lookahead proof right, since there is no
   later phase that will catch a regression here.
4. **Gated + default-off discipline (standard house style):** `portfolio_risk="off"` must
   reproduce current behavior byte-for-byte, in aggregate across symbols too (not just
   per-symbol) — this is the ONE required full-`BacktestEngine` golden-snapshot equivalence proof
   for this task.
5. **No-lookahead is the highest-risk item this phase** — a cross-symbol pass must not use symbol
   B's end-of-day data to make a decision for symbol A earlier in the same day. Mirror the
   existing `test_daily_no_lookahead`/`test_4h_no_lookahead` pattern for whatever trading-day
   alignment mechanism you use.
6. **`corr_clusters`/`daily_loss_limit_pct` are conservative starting defaults, not tunable in
   this task** — the comparison report is read-only evidence only, reject-on-violation if used to
   pick these values in-task.
7. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched
   (backtest-only coordinator, no live routing); RESEARCH-ONLY banner on the new report; no
   `GOAL PASSED`; does not touch exit logic or per-trade sizing formula.
8. **Verify diagnostic report window and symbols before committing** — use
   `WINDOW_START="2026-04-24"`, `WINDOW_END="2026-07-09"` and the standard 5-symbol default list
   (copy constants from an existing A43-A47 report script). A47 got this right from the start;
   follow that precedent rather than A45/A46's first-attempt mistakes.
9. **Before claiming any script "doesn't exist," verify the path carefully** —
   `run_next_work.ps1` lives at `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
10. **If an acceptance item seems logically impossible to satisfy as written, stop and flag it
    rather than debug-looping** — re-read this HANDOFF.md's Acceptance Criteria for an internal
    contradiction before spending more than a few iterations stuck (this HANDOFF has been written
    carefully to avoid A46's self-contradiction incident, but if something still seems impossible,
    that's a signal, not a bug in your implementation).
11. Finish with the acceptance commands, then
    `python tools/handoff.py next --actor kimi-code --summary "A48 (P8b) portfolio risk coordinator implemented"`.
    Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Review Reject Notes

Codex review on 2026-07-12 rejects A48 back to dev. The submitted unit tests pass, but they only
exercise `PortfolioCoordinator` in isolation and miss failures in the actual `PortfolioEngine`
coordinated replay.

Required fixes:

1. **Daily-loss-limit flatten is not applied to the coordinated replay.** In
   `chan_strategy/portfolio_engine.py`, `PortfolioCoordinator.on_bar()` can call
   `_flatten_all()` and records `flat_events`, but `PortfolioEngine._build_on_report()` keeps its
   own separate `open_positions` dict. Those positions are not removed when the coordinator
   flattens, so coordinated equity continues carrying the trade until the original per-symbol
   close event, and `pairs` still shows the original close reason instead of
   `portfolio_daily_loss_limit`. Repro: a position opened at 2024-01-01 15:00, day-2 09:00 equity
   at -6% with `daily_loss_limit_pct=0.05` produced `loss_limit_triggers=1` and `flat_events=1`,
   but `pairs[0].close_dt` remained 2024-01-02 15:00 and `gross_exposure` stayed non-zero until
   the original close. Acceptance requires flatten all open positions and block new opens for the
   rest of the day in the actual portfolio report, not just in coordinator-local evidence.
2. **Short-side portfolio PnL and exposure signs are wrong.** `_build_on_report()` computes
   unrealized PnL as `(price - open_price) / open_price` and stores all weights as positive. A
   synthetic `一卖空头` trade from 100 to 90 reported equity 990,000 at the interim bar instead of
   1,010,000, and `net_exposure` was `+0.1` instead of negative. The replay must preserve trade
   direction for short strategies: realized/unrealized PnL, net exposure, and flatten accounting
   must use signed exposure while cluster gross exposure still uses absolute exposure.
3. **The public convenience entry point is broken.** `chan_strategy/portfolio_engine.py`
   `run_portfolio_backtest()` passes `table_name=...` to `PortfolioEngine(...)`, but the
   constructor accepts `table_names`, so the entry point immediately raises
   `TypeError: PortfolioEngine.__init__() got an unexpected keyword argument 'table_name'`.
4. **BacktestEngine coordinator wiring references methods that the coordinator does not provide.**
   `BacktestEngine.run(..., coordinator=...)` calls `get_weights()`, `can_open()`, and
   `update_after_bar()`, but `PortfolioCoordinator` exposes `allow_open()`, `record_open()`,
   `record_close()`, and `on_bar()`. Either remove the dead/broken wiring if A48's chosen design
   is pure post-run replay, or implement and test the wiring end-to-end.
5. Add regression tests that hit `PortfolioEngine._build_on_report()` (or the public
   `run_portfolio_backtest()` path), not only `PortfolioCoordinator`: one for daily-loss flatten
   producing a loss-limit close and zero post-trigger gross exposure, one for short trade signed
   PnL/net exposure, and one for the public entry point construction.

## Decision Log

- 2026-07-12 - P8b promoted from the pre-authored phase-contracts draft to an active HANDOFF task
  as **A48** (not A45 — A45 is P6 under the established renumbering), started immediately after
  A47 (P8a) reached `done`, satisfying the design's explicit P8a-before-P8b ship-order
  requirement (stronger than the general one-phase-at-a-time rule already used for P4-P7).
- 2026-07-12 - Re-verified fixed weights (`config.py:20-22`, unchanged) and single-symbol
  `BacktestEngine` architecture (`backtest_engine.py:59`, no cross-symbol state) — no drift from
  A43-A47, and confirmed no `portfolio_risk`/`corr_clusters`/`portfolio_engine.py` exists yet.
- 2026-07-12 - This is the final task in the P1-P8 roadmap (A38-A48 span the full roadmap once
  this completes) — flagged explicitly in the Notes for the Next Agent so dev treats the
  equivalence/no-lookahead proofs with the same rigor as every prior phase, since there is no
  subsequent task to catch a missed regression here.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-12 | codex → claude-code | done → design | P8b promoted from phase-contracts draft, confirmed A48 under the established renumbering |
| 2026-07-12 | claude-code → kimi-code | design → dev | A48 (P8b portfolio risk) started; re-verified no drift from A43-A47 |
| 2026-07-12 | kimi-code → codex | dev → review | A48 (P8b) portfolio risk coordinator implemented |
| 2026-07-12 | codex → kimi-code | review → dev | 打回: A48 portfolio replay does not apply daily-loss flatten and mis-signs short PnL/exposure |
| 2026-07-12 | kimi-code → codex | dev → review | A48 (P8b) portfolio risk coordinator implemented |
| 2026-07-12 | codex → codex | review → done | A48 review accepted after portfolio replay risk accounting fixes |
