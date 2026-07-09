# A38 Design: Chan Strategy Improvement Roadmap (Win-Rate & Profitability)

**Task:** Convert the 2026-07-09 futures-trading review action checklist into a phased, gated
strategy-improvement program, and specify Phase 1 (touch-based stop execution) in
implementable detail for dev.

**Scope of this document:**

- Part I is design-only: the full roadmap (P1-P8) that maps every action-checklist item to a
  gated, independently reviewable task. It does not itself change trading behavior.
- Part II is the dev contract for **A38 only**: Phase 1 (gap-aware / intrabar touch-based
  stop-loss execution), gated behind a config switch that defaults to byte-identical legacy
  behavior. Later phases (P2-P8) are deferred to follow-on tasks (A39+).

**Authorization note:** Unlike the A34 remediation line (diagnostics-only, "do not optimize
profitability"), A38 is explicitly authorized by the user (2026-07-09) to modify strategy code
in the root `vnpy` workflow. The A34-style guardrails (no OOS tuning, research-only banner, no
SimNow order changes, gated default-off switches, diagnostic-first) still apply and are the
acceptance backbone below.

---

## 0. Background

The 2026-07-09 review ("期货交易专家 + agent 设计" audit) reached three load-bearing conclusions:

1. **Reported returns are not tradeable PnL.** `Position` is signal-research mode: `pos ∈
   {-1,0,1}`, `volume ≡ 1`, PnL as a percentage, equity weighted post-hoc by fixed weights
   (`backtest_engine.py:322-359`). No contract multiplier, margin, integer lots, or compounding.
2. **No demonstrated edge.** Full-sample 2022-2026: AP +6.5%, RB -8.0%, SC -10.9%, A -0.2%,
   ZN +1.6%; 43-123 trades per symbol over 4.3 years; profit factors mostly < 1.5; large
   in-sample -> out-of-sample decay on RB/SC.
3. **The stop mechanism is the biggest single bleed.** Per the A37 background attribution
   (358 trades): `stop_loss` = 155 trades, 0% win, cumulative ~`-489%`; `trailing_stop` = 114
   trades, 99.1% win, ~`+411%`. A35 further showed close-based stops overshoot the nominal stop
   up to ~4.2x (worst single loss ~`-12.60%` on a 3% stop).

The review's action checklist has three tiers:

- **Tier A (foundation, "make the numbers real"):** touch-based stops; 888 rollover handling +
  trading-calendar daily; real position sizing; frozen honest baseline.
- **Tier B (win rate):** MACD-area divergence; multi-level resonance filter; remove/hard-gate
  二买; ATR/volatility chop filter.
- **Tier C (profitability):** symmetric regime-gated shorts; exit overhaul (structural stop +
  ATR trailing + 中枢 partial take-profit); risk-parity sizing + correlation-cluster exposure
  cap + daily loss limit.

Prior work (A34-A37) already handled the audit-remediation slice of Tier A as *diagnostics*:
M1 cost single-source (done), H1 declassification (done), A35 stop-loss stress diagnostic
(done, reviewed), A37 exit-event restructure (done). What remains un-built:

- H2 **implementation** (touch-based stops in `Position`) — A35 only measured it.
- H4 rollover-pollution diagnostic — not started.
- The entire Tier B / Tier C edge program — never designed.

A38 sequences all of it and ships the first, highest-certainty piece.

---

## Part I - Full Improvement Roadmap (design-only)

Each phase is a separate handoff task. Common discipline for every phase (reject-on-violation):

- **Gated:** every behavior change hides behind a `STRATEGY_CONFIG` switch whose default
  reproduces current behavior byte-for-byte; the default path must pass an equivalence test
  (empty before/after trade-pair diff on >=2 symbols x 1 year long, plus >=1 symbol x 1 year
  with `enable_short=True`), mirroring A37.
- **Diagnostic-first:** where a phase claims an effect, a read-only diagnostic quantifies the
  effect before the switch is turned on by default.
- **No selection on stale data:** no parameter is chosen using pre-2026-04-24 history;
  promotion evidence requires the post-2026-04-24 + SimNow stream (A34 H1 policy).
- **Research-only + safety:** every generated report carries `Diagnostic only, not a trading
  recommendation.`; no `GOAL PASSED`; no `send_order`/`cancel_order`/`buy`/`sell`/`short`/
  `cover` additions; no secret fields.

| Phase | Task | Tier | Review item | Depends on | Default gate |
|------|------|------|-------------|-----------|--------------|
| **P1** | Gap-aware / intrabar touch-based stop execution | A | A1 (#2 priority) | A35 diagnostic | `stop_execution_model="close"` |
| P2 | Rollover-pollution diagnostic + trading-calendar daily aggregation | A | A2 (H4) | - | `daily_agg="natural"` |
| P3 | Real position sizing (ATR-risk units + contract multiplier + margin) | A | A3 | P1 | `sizing_model="research"` |
| P4 | MACD-area divergence signal (replace `_bi_power` proxy) | B | #5; resolves H3 deferral | P1 | `divergence_model="amplitude"` |
| P5 | Multi-level resonance entry filter | B | #6 | P4 | `resonance_filter=off` |
| P6 | 二买 removal / hard-gate + ATR chop filter | B | #7, #8 | P4, P5 | `second_buy_mode="baseline"` |
| P7 | Symmetric regime-gated shorts | C | #9 | P3, P5 | `enable_short=False` (unchanged) |
| P8 | Exit overhaul + portfolio risk (risk parity, correlation cap, daily loss limit) | C | #10, #11 | P3, P7 | `exit_model="legacy"`, `portfolio_risk=off` |

### P1 - Touch-based stop execution (this task; detailed in Part II)

Rationale for going first: highest certainty (pure execution-accuracy fix, no signal-semantics
change), highest leverage (the stop path is where all the loss concentrates), and a prerequisite
for every later measurement — win-rate/PnL deltas from Tiers B/C are meaningless while stops
fill at an unrealistic price. A35 already produced the acceptance oracle.

### P2 - Rollover-pollution diagnostic + trading-calendar daily

- Read-only `rollover_exclusion_report_YYYY-MM-DD.{json,md}` per A34 H4: detect 888 contract
  transitions, remove signals/trades within transition +/- 1 trading day, report
  `trade_count`, `return`, `drawdown`, `stop_loss_overshoot` before/after.
- Then a gated `daily_agg="trading_calendar"` path that assigns night-session bars (21:00->)
  to the next trading day before daily resample (`data_adapter.resample_bars`), replacing the
  natural-day cut that currently splits a futures trading day (`data_adapter.py:61-83`).
- Boundary: does not rebuild the vendor data feed; documents 888 as `found_spliced`.

### P3 - Real position sizing

- Add `sizing_model="risk"`: `volume = floor( (equity * risk_per_trade) / (stop_distance *
  contract_multiplier * price_tick_value) )`, with `stop_distance` from P1's structural/ATR
  stop, plus a margin-usage cap and integer-lot rounding.
- Requires a per-symbol contract spec table (multiplier, tick, margin rate) added to config.
- Default `sizing_model="research"` reproduces the current direction-only, post-hoc-weight
  equity curve exactly.
- Boundary: backtest-only; no live order routing.

### P4 - MACD-area divergence

- New `signal_divergence_macd` computing DIF/DEA and comparing the MACD area (or peak
  histogram) of the leaving segment vs the entering segment across the center, replacing the
  raw-amplitude proxy `_bi_power` (`signals.py:55`) that drives 一买/一卖.
- Gated `divergence_model="amplitude"` (current) vs `"macd"`.
- This is also the clean resolution of the A34 H3 deferral: the `背驰=失效` classification is
  redefined on a real (MACD) basis instead of the unreachable adjacent-same-direction stroke
  comparison; acceptance requires real signal-history replay count > 0 for the repaired class,
  or the class is deleted.

### P5 - Multi-level resonance filter

- Gated entry filter requiring the 30m buy point to align with a higher-level (daily or a new
  4H level) buy structure — not merely "daily direction != down" (the current boolean gate,
  `positions.py:17-38`), but "higher level is at/above its own center / at a buy point".
- Diagnostic first: report win-rate and trade-count with vs without resonance on the honest
  (post-P1) baseline.

### P6 - 二买 gate + ATR chop filter

- `second_buy_mode`: `baseline` (current) | `gated` (require P4 divergence + P5 resonance +
  ATR expansion) | `off`. Motivated by measured negative expectancy (RB 二买 0/6; SC 二买
  PF 0.36; recurring -3% to -12.6% stops in `key_trade_behavior_review.md`).
- ATR chop filter: block entries when trade-frequency ATR percentile is below a configured
  floor (range compression -> false buy points).

### P7 - Symmetric regime-gated shorts

- Enable the existing short sub-strategies (`create_first_sell_position` ...) under a daily
  regime router, with the same confirmed-structure and (post-P4) MACD-divergence rigor as the
  long side. Motivated by RB/SC structural downtrends where long-only bleeds.
- Default `enable_short=False` (unchanged); turning it on is a measured, gated experiment.

### P8 - Exit overhaul + portfolio risk

- Exit: replace the laggy "confirmed-structure reversal" exit with structural stop + ATR
  trailing + partial take-profit at the next center boundary; `key_trade_behavior_review.md`
  shows exits are the dominant PnL lever.
- Portfolio: risk-parity weights (replace fixed 10/20/30 that overweight the worst-performing
  三买), a correlation-cluster gross-exposure cap (RB/ZN/SC co-move), and an equity-based daily
  loss limit / de-risk switch.

---

## Part II - Phase 1 Dev Contract: Touch-Based Stop Execution

### 2.1 Problem

`Position._check_stop_loss` (`chan_strategy/positions.py:478-488`) compares the nominal stop
against `price`, and the risk block in `Position.update` (`:392-415`) passes `price = bar.close`
and fills the stop at `bar.close`. On 30-minute futures bars with night sessions and limit
moves, price can gap through the stop between closes, so the realized loss exceeds the nominal
stop (A35: up to ~4.2x; worst ~`-12.60%` on a 3% stop). The fix is execution accuracy, not a
threshold change.

### 2.2 Config switch

Add to `STRATEGY_CONFIG` (`chan_strategy/config.py`):

```python
"stop_execution_model": "close",   # "close" (legacy) | "intrabar"
"stop_penalty_bp": 0,              # extra adverse slippage applied to an intrabar stop fill
```

- `"close"` is the default and MUST reproduce current behavior byte-for-byte.
- `stop_penalty_bp` default `0` keeps the intrabar model unpenalized unless explicitly set; it
  is not tuned in this task.

### 2.3 Intrabar trigger + fill semantics

Thread the current bar's `high` and `low` into the risk check (new optional params on
`Position.update`, defaulting to `None` -> falls back to `price`, preserving old call sites).
Under `stop_execution_model == "intrabar"`, for an open position:

- **Long:** `trigger = cost * (1 - stop_loss_bp / 10000)`; stop fires when `bar_low <= trigger`;
  fill price = `min(trigger, bar_close)` then worsened by `stop_penalty_bp`
  (`fill *= (1 - stop_penalty_bp/10000)`).
- **Short:** `trigger = cost * (1 + stop_loss_bp / 10000)`; stop fires when `bar_high >= trigger`;
  fill price = `max(trigger, bar_close)` then worsened by `stop_penalty_bp`
  (`fill *= (1 + stop_penalty_bp/10000)`).

Trailing-stop and timeout keep their current price basis in this task (P8 revisits exits);
only the fixed stop-loss path gains intrabar semantics. Priority order in `Position.update`
(trailing > stop > timeout) is unchanged.

### 2.4 No-lookahead constraint

The risk check must use **only the current bar's** OHLC — the same bar whose close already
drives the existing risk block. `BacktestEngine.run` ordering (pending-signal fill at next-bar
open, then CZSC update, then signal generation) is otherwise untouched. Wiring: in the risk
branch of the loop (`backtest_engine.py:271-284`), pass `bar.high` / `bar.low` alongside
`bar.close` into `strategy.update(...)`. No future bar is read.

### 2.5 Cross-check against A35

A35's `stop_loss_stress_report` computed the `intrabar_trigger` scenario independently from
saved pairs. Phase 1 must produce a backtest under `stop_execution_model="intrabar"` whose
recomputed stop-loss `worst_loss_pct`, `overshoot_count`, and `max_overshoot_multiple` agree
with A35's `intrabar_trigger` scenario within tolerance on at least one symbol — two independent
implementations converging is the correctness proof.

### 2.6 Expected file changes

- `examples/czsc_strategy/chan_strategy/config.py` (two keys + doc)
- `examples/czsc_strategy/chan_strategy/positions.py` (`update`, `_check_stop_loss`, `_close_*`)
- `examples/czsc_strategy/chan_strategy/backtest_engine.py` (thread bar high/low; header print)
- `examples/czsc_strategy/tests/unit/test_positions.py` (or a new
  `test_stop_execution_model.py`): intrabar long/short trigger, fill = min/max(trigger, close),
  penalty direction, and legacy equivalence
- `examples/czsc_strategy/chan_strategy/validation.py` if a new signal/report key is registered
  (not expected for P1)

---

## 3. Acceptance Criteria (A38 = Phase 1)

These are copied verbatim into `HANDOFF.md` as the dev/review contract.

- [ ] `STRATEGY_CONFIG["stop_execution_model"]` exists with values `"close"` (default) and
      `"intrabar"`, plus `stop_penalty_bp` (default `0`); both documented in `config.py`.
- [ ] **Legacy equivalence:** with `"close"`, before/after trade-pair diff is empty on >=2
      symbols x 1 year (long baseline) AND >=1 symbol x 1 year with `enable_short=True`.
- [ ] **Intrabar trigger:** unit tests prove long fires on `bar_low <= cost*(1-bp)` and fills
      `min(trigger, close)`; short fires on `bar_high >= cost*(1+bp)` and fills
      `max(trigger, close)`; `stop_penalty_bp` worsens the fill in the correct direction.
- [ ] **No-lookahead:** the intrabar check reads only the current bar's high/low; a test
      asserts no future bar is consulted, and `BacktestEngine.run` step ordering is unchanged.
- [ ] **A35 cross-check:** an `"intrabar"` backtest's recomputed stop-loss `worst_loss_pct` /
      `overshoot_count` / `max_overshoot_multiple` agree with A35's `intrabar_trigger` scenario
      within a stated tolerance on >=1 symbol (evidence tracked, not only regenerated-on-disk).
- [ ] Backtest report header prints the active `stop_execution_model` and `stop_penalty_bp`.
- [ ] No stop-loss threshold tuned (`stop_loss_*bp` unchanged); no pre-2026-04-24 data used for
      any selection; every generated report carries the RESEARCH-ONLY disclaimer; no
      `GOAL PASSED`.
- [ ] No SimNow order/cancel/send paths changed; no new `send_order`/`cancel_order`/`buy`/
      `sell`/`short`/`cover`; no secret fields in output.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight`
      passes.
- [ ] Part I roadmap present in this doc: all Tier A/B/C review items mapped to P1-P8, each with
      a default-off gate and boundaries.
- [ ] `python tools/handoff.py next --actor kimi-code --summary "A38 phase 1 touch-based stop execution implemented"`
      advances to review.

---

## 4. Boundaries (what A38 does NOT do)

- Does not implement P2-P8 (rollover, sizing, MACD divergence, resonance, 二买 gate, shorts,
  exit overhaul, portfolio risk) — those are follow-on tasks A39+.
- Does not change trailing-stop or timeout price basis (P8 owns exits).
- Does not tune any threshold, weight, or interval; does not enable shorts.
- Does not change SimNow connectivity or any order path.
- Does not rebuild the 888 data feed or claim the strategy is now profitable — P1 makes the
  loss side honest; profitability claims require the post-2026-04-24 + SimNow stream.

---

## 5. Dev Handoff Prompt

```text
Read HANDOFF.md and docs/design/a38-strategy-improvement-roadmap.md. Implement A38 = Phase 1
only (touch-based stop execution). Do not implement P2-P8.

1. Add STRATEGY_CONFIG["stop_execution_model"] ("close" default | "intrabar") and
   stop_penalty_bp (0 default) to config.py, documented.
2. In positions.py, make _check_stop_loss / the risk block honor the switch: under "intrabar",
   long fires on bar_low <= cost*(1-bp) filling min(trigger, close); short fires on
   bar_high >= cost*(1+bp) filling max(trigger, close); apply stop_penalty_bp adversely.
   Thread bar high/low via new optional Position.update params (default None -> current price).
   Trailing/timeout unchanged. "close" path must stay byte-identical.
3. In backtest_engine.py, pass bar.high/bar.low into strategy.update in the risk branch (current
   bar only, no lookahead) and print the active stop_execution_model/stop_penalty_bp in the
   report header.
4. Tests: intrabar long/short trigger + fill, penalty direction, legacy equivalence (empty
   before/after pair diff, >=2 symbols x 1yr long + >=1 symbol x 1yr enable_short=True), and an
   A35 cross-check that intrabar-backtest overshoot metrics match the A35 intrabar_trigger
   scenario within tolerance on >=1 symbol. Track the cross-check evidence artifact.

Do not tune thresholds, do not use pre-2026-04-24 data for selection, do not touch SimNow
order/cancel paths, do not claim GOAL PASSED. Reports carry the RESEARCH-ONLY banner.

Run:
- python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
- python tools/sync_check.py
- python tools/sync_check.py --root examples/czsc_strategy
- powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
- python tools/handoff.py next --actor kimi-code --summary "A38 phase 1 touch-based stop execution implemented"
```

---

## 6. Review Checklist

Reject if:

- the `"close"` path is not byte-identical to the current baseline (non-empty equivalence diff);
- the intrabar trigger/fill math differs from Part II 2.3, or applies to trailing/timeout;
- the risk check reads any bar other than the current one, or `BacktestEngine.run` ordering
  changed beyond threading high/low;
- any stop threshold, weight, or interval was tuned; any selection used pre-2026-04-24 data;
- the A35 cross-check is missing, or its evidence exists only as a git-ignored regenerated file;
- any SimNow order/cancel path changed, or a report claims `GOAL PASSED`;
- `python tools/sync_check.py` (root or child) fails.

Accept if all Section 3 boxes are checked and the handoff advances to review.
```
