# A38 Companion: Detailed Dev Contracts for Phases P2-P8

**Purpose:** Expand the P2-P8 roadmap from `docs/design/a38-strategy-improvement-roadmap.md`
(Part I) into full, implementable dev contracts at the same depth as A38 Phase 1 (Part II).

**Status:** These are pre-authored design specs for **future tasks A39-A45**. They do **not**
change A38's Phase-1 dev scope (touch-based stop execution), which remains the only active dev
contract. When each future task is started, its `design` stage adopts the matching section
below as its contract (or points to it).

**Task mapping:** P2=A39, P3=A40, P4=A41, P5=A42, P6=A43, P7=A44, P8=A45.

**Shared discipline (every phase, reject-on-violation).** Identical to A37/A38:

- **Gated + default-off:** each behavior change hides behind a `STRATEGY_CONFIG` switch whose
  default reproduces current behavior byte-for-byte; the default path passes an equivalence test
  (empty before/after trade-pair diff on >=2 symbols x 1 year long, plus >=1 symbol x 1 year
  with `enable_short=True`).
- **Diagnostic-first:** where a phase claims an effect, a read-only diagnostic quantifies it
  before the switch is turned on by default.
- **No selection on stale data:** no parameter chosen using pre-2026-04-24 history; promotion
  evidence needs the post-2026-04-24 + SimNow stream.
- **No-lookahead:** any new indicator/level reads only bars up to and including the current one;
  `BacktestEngine.run` step ordering is preserved.
- **Safety:** reports carry `Diagnostic only, not a trading recommendation.`; no `GOAL PASSED`;
  no new `send_order`/`cancel_order`/`buy`/`sell`/`short`/`cover`; no secret fields.

**Dependency order:** P1 -> P2 -> P3 gate the foundation; P4 -> P5 -> P6 build win-rate on top;
P7 -> P8 build the two-sided / portfolio layer. Do not start a phase before its `Depends on`
row (Part I table) is `done`.

---

## P2 (A39) - Rollover-Pollution Diagnostic + Trading-Calendar Daily Aggregation

### Rationale
888 continuous contracts are a raw splice (A34 H4 = `found_spliced`). Rollover gaps are read by
the 笔/分型/中枢 machinery as real moves -> fake breakouts (三买/结构失效), fake gap stops,
fake divergence. SC (largest roll spread) is the worst-performing, most parameter-sensitive
symbol. Separately, daily aggregation currently cuts on the natural date
(`data_adapter.py:61-83`), which splits a single futures trading day (night session 21:00 ->
next day) into two "daily" bars, so the daily trend filter consumes a structure that does not
match the exchange trading day.

### Config
```python
"daily_agg": "natural",            # "natural" (legacy) | "trading_calendar"
"night_session_start_hour": 20,    # bars with hour >= this roll to the next trading day
```

### Semantics
**P2a - rollover diagnostic (read-only, ship first).** New
`diagnostics/rollover_exclusion_report.py`:
- Detect transition dates per symbol. Primary: read the underlying-contract column in the raw
  table (the `real_symbol`/contract id that 888 switches) and mark the dates where it changes.
  Fallback (if no such column): flag day-boundary close-to-open jumps exceeding a stated
  multiple of trailing ATR and label the detection method in the report.
- Recompute baseline vs "exclude signals/trades within transition +/- 1 trading day".
- Emit `rollover_exclusion_report_YYYY-MM-DD.{json,md}` with per-symbol
  `transition_dates`, `trade_count_before/after`, `return_before/after`,
  `drawdown_before/after`, `stop_loss_overshoot_before/after`, plus `detection_method` and
  `unavailable` reasons where a symbol's contract column or bars are missing.

**P2b - trading-calendar daily (gated).** In `data_adapter.resample_bars` daily path, under
`daily_agg="trading_calendar"` map each bar to a **trading day** before grouping: a bar with
`dt.hour >= night_session_start_hour` belongs to the next trading day; "next trading day" = the
nearest following date that appears in the day-session set of that symbol (robust to
weekends/holidays without an external calendar). Group by trading-day key; bar timestamp stays
the last 1m bar of the group (no-lookahead preserved). `"natural"` default is unchanged.

### No-lookahead & correctness
- Daily bar timestamp = last constituent 1m bar; the main loop's `dt <=` advance is unchanged,
  so the daily filter still cannot see the future (existing `test_daily_no_lookahead` must pass).
- The rollover diagnostic is read-only and must not mutate strategy code or historical reports.

### Expected files
- `examples/czsc_strategy/diagnostics/rollover_exclusion_report.py` (tracked, not under an
  ignored path)
- `examples/czsc_strategy/tests/unit/test_rollover_exclusion_report.py`
- `examples/czsc_strategy/chan_strategy/data_adapter.py` (trading-day mapping in daily resample)
- `examples/czsc_strategy/chan_strategy/config.py` (two keys + doc)
- `examples/czsc_strategy/tests/unit/test_data_adapter.py`
- a Chan-strategy risk note documenting 888 `found_spliced` and that adjustment is unverified

### Acceptance (decidable)
- [ ] `rollover_exclusion_report_*.{json,md}` generated; AP/RB/SC/A/ZN each have
      `transition_dates` or an explicit `unavailable` reason; before/after trade_count, return,
      drawdown, stop_loss_overshoot all present; `detection_method` stated.
- [ ] Report carries the RESEARCH-ONLY banner; no `GOAL PASSED`; evidence artifact tracked.
- [ ] `daily_agg="natural"` -> daily-bar sequence byte-identical to current (equivalence test).
- [ ] `daily_agg="trading_calendar"` -> a fixture with a night session crossing midnight
      (e.g. 22:00, 01:00, 10:00 of the same trading day) aggregates into ONE daily bar keyed to
      the trading day; a Friday-night bar rolls to the next present trading date, not Saturday.
- [ ] `test_daily_no_lookahead` still passes under both modes.
- [ ] Root + child `sync_check` and `run_next_work.ps1 -Preflight` pass.

### Boundaries
No vendor data-feed rebuild; no back-adjusted price reconstruction; full exchange holiday
calendar is a documented later refinement (the "nearest following present trading date"
heuristic is the first cut). Does not exclude rollover trades from the live strategy - only the
diagnostic excludes them; whether to gate opens around rollover is a separate future decision.

### Dev prompt
```text
Read HANDOFF.md and docs/design/a38-phase-contracts-p2-p8.md P2. Ship P2a (read-only rollover
exclusion diagnostic) first, then P2b (gated trading-calendar daily aggregation, default
"natural" byte-identical). Track scripts/proof under non-ignored paths. Do not gate live opens,
do not tune, do not touch SimNow paths, no GOAL PASSED. Then handoff next.
```

### Review checklist
Reject if: the diagnostic changes strategy behavior; `"natural"` is not byte-identical; the
trading-day mapping reads future bars; proof lives only in a git-ignored file; any SimNow path
changed.

---

## P3 (A40) - Real Position Sizing (ATR-Risk Units + Contract Multiplier + Margin)

### Rationale
`Position` is direction-only (`pos in {-1,0,1}`, `volume==1`), equity weighted post-hoc
(`backtest_engine.py:322-359`). Reported returns are a signal-quality index, not tradeable PnL,
and fixed % stops ignore that SC has ~3-4x the volatility of AP. Real sizing makes PnL tradeable
and normalizes per-trade risk across symbols. This is a prerequisite for trusting any Tier B/C
profitability delta.

### Config
```python
"sizing_model": "research",        # "research" (legacy post-hoc weights) | "risk"
"risk_per_trade_pct": 0.005,       # fraction of equity risked to the stop distance
"max_margin_pct": 0.50,            # cap on total initial margin vs equity
"equity_mode": "fixed",            # "fixed" (initial capital) | "compound" (documented option)
"contract_specs": {                # ILLUSTRATIVE placeholders - dev MUST replace with cited
    # exchange spec (SHFE/INE/DCE/CZCE) and record the source; do not ship these numbers unverified.
    # "SC888": {"multiplier": 1000, "tick": 0.1, "margin_rate": 0.10},
    # "RB888": {"multiplier": 10,   "tick": 1.0, "margin_rate": 0.10},
    # ...
},
```

### Semantics (risk mode)
On open:
1. `stop_distance = |entry_price - stop_price|` where `stop_price` is the fixed/structural stop
   from P1 (`cost * stop_loss_bp/10000`, or the structural level if tighter).
2. `risk_amount = equity_at_entry * risk_per_trade_pct`.
3. `raw_volume = risk_amount / (stop_distance * multiplier)`.
4. `volume = floor(raw_volume)`; if `volume < 1` -> skip open, log `size_zero_skip` (do not
   force a 1-lot floor).
5. Margin cap: `required = volume * entry_price * multiplier * margin_rate`; if total open
   margin would exceed `equity * max_margin_pct`, reduce `volume` to the largest lot count that
   fits (>=1, else skip).

`Position` gains real `volume`, and PnL is computed in currency
(`(exit-entry) * volume * multiplier * sign - costs`). The equity engine switches from post-hoc
weighting to actual realized+unrealized currency PnL. `"research"` default preserves the exact
current equity curve.

### No-lookahead & correctness
- `equity_at_entry` uses running equity known at the entry bar (realized to date + open
  unrealized at that bar); never future equity.
- Integer-lot and margin checks use only entry-bar prices.

### Expected files
- `chan_strategy/config.py` (keys + contract_specs; dev cites the spec source in a comment)
- `chan_strategy/positions.py` (`Position` real volume + currency PnL; sizing on open)
- `chan_strategy/backtest_engine.py` (risk-mode equity from real position accounting; header
  prints `sizing_model` and, for risk mode, per-symbol contract spec used)
- `chan_strategy/tests/unit/test_position_sizing.py`

### Acceptance (decidable)
- [ ] `sizing_model="research"` -> equity curve and trade pairs byte-identical to current
      (equivalence test).
- [ ] `sizing_model="risk"`: given a fixture (equity, risk_per_trade_pct, multiplier,
      stop_distance), `volume == floor(risk_amount/(stop_distance*multiplier))`; a fixture that
      breaches `max_margin_pct` reduces volume to the margin-fitting lot count; `raw_volume < 1`
      produces `size_zero_skip` (no trade, no 1-lot floor).
- [ ] Currency PnL for a closed trade equals `(exit-entry)*volume*multiplier*sign - costs`
      (unit-tested both directions).
- [ ] `contract_specs` values carry a cited exchange-spec source in code comments; tests use
      fixtures, not real profitability claims.
- [ ] Report header prints active `sizing_model`; RESEARCH-ONLY banner retained.
- [ ] Root + child `sync_check`, unit suite, `run_next_work.ps1 -Preflight` pass.

### Boundaries
`equity_mode="fixed"` first cut (compounding documented, not shipped); initial-margin model only
(no maintenance margin / mark-to-market margin calls); no live order routing; single-symbol
equity (portfolio-level capital sharing is P8).

### Dev prompt
```text
Read P3. Add sizing_model gate; "research" default byte-identical. In "risk", size by
equity*risk_per_trade_pct / (stop_distance*multiplier), floor to lots, enforce max_margin_pct,
skip when <1 lot. Populate contract_specs from cited exchange specs (do not fabricate). Compute
currency PnL. Do not tune, no SimNow order paths, no GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: research mode not byte-identical; volume math deviates from the formula; a 1-lot
floor is forced; contract_specs shipped without a cited source; currency PnL ignores multiplier
or costs; any live order path touched.

---

## P4 (A41) - MACD-Area Divergence (Replace `_bi_power` Proxy)

### Rationale
背驰 is currently approximated by raw stroke amplitude `_bi_power = abs(high-low)`
(`signals.py:55`), a crude proxy that mislabels many 一买/一卖 -> low first-buy win rate
(26-37% on several symbols). Standard 缠论 背驰 compares MACD area/DIF between the entering and
leaving segments. This is the single highest-leverage win-rate lever.

### Config
```python
"divergence_model": "amplitude",   # "amplitude" (legacy) | "macd"
"macd_fast": 12, "macd_slow": 26, "macd_signal": 9,   # standard; NOT tuned in this task
```

### Semantics
Compute MACD on confirmed trade-frequency closes: `DIF = EMA(fast) - EMA(slow)`,
`DEA = EMA(DIF, signal)`, `hist = 2*(DIF - DEA)`. For a center with an entering stroke and a
leaving stroke, divergence strength compares the leaving segment's MACD magnitude (choose one and
fix it: summed `|hist|` area over the segment's bars, OR the DIF extreme) against the entering
segment's. Bottom divergence (一买): price lower low but leaving MACD magnitude < entering ->
divergence. Under `"macd"`, `signal_divergence_status`, `signal_first_buy`, and
`signal_first_sell` use this measure instead of `_bi_power`.

**H3 resolution.** A37 already removed the consumers of the unreachable `背驰=失效` class. P4
**deletes the now-orphaned amplitude `失效` branch** in `signal_divergence_status`
(`signals.py:270-286`) and its validation entry. Optionally, under `"macd"`, a MACD-based failure
class may be reintroduced ONLY if real signal-history replay shows count > 0; otherwise it stays
deleted. Do not keep an unreachable class.

### No-lookahead & correctness
MACD uses only confirmed bars up to the current one (via `_get_confirmed_bi_list` raw bars /
confirmed closes). No future bars; same discipline as existing signals.

### Expected files
- `chan_strategy/signals.py` (new `signal_divergence_macd` helper; gate in
  `signal_divergence_status`/`signal_first_buy`; delete orphan `失效` branch)
- `chan_strategy/sell_signals.py` (`signal_first_sell` MACD path)
- `chan_strategy/validation.py` (register/remove classes to keep exhaustiveness exact)
- `chan_strategy/config.py`
- `chan_strategy/tests/unit/test_signals.py`, `test_divergence_macd.py`
- `diagnostics/divergence_model_comparison_report.py` (read-only: 一买 win-rate amplitude vs
  macd on the honest post-P1 baseline; report only, not for selection)

### Acceptance (decidable)
- [ ] `divergence_model="amplitude"` -> byte-identical (equivalence test).
- [ ] `"macd"`: a fixture where amplitude flags divergence but MACD does not (and the reverse)
      yields the specified differing classifications; MACD params are exactly 12/26/9 and NOT
      tuned in-task.
- [ ] Orphan `背驰=失效` branch removed; no code references it; validation exhaustiveness sets
      updated; a test enforces confirmed-BI direction alternation (no adjacent same-direction
      fake structure as coverage).
- [ ] If a MACD `失效` class is added, real signal-history replay shows count > 0; else it is
      absent.
- [ ] Divergence-comparison diagnostic generated (report only, RESEARCH-ONLY banner).
- [ ] Root + child `sync_check`, unit suite, preflight pass.

### Boundaries
Single-level MACD (multi-level MACD resonance is P5); MACD params fixed at the standard, tuning
deferred; does not touch 二买/三买 structural definitions (only the divergence measure feeding
一买/一卖).

### Dev prompt
```text
Read P4. Add divergence_model gate; "amplitude" default byte-identical. In "macd", compute
DIF/DEA/hist (12/26/9, do not tune) and compare leaving vs entering MACD magnitude for
一买/一卖. Delete the orphaned 背驰=失效 branch (A37 already removed its consumers); keep
validation exhaustive; add the BI-alternation invariant test. Add a read-only amplitude-vs-macd
win-rate comparison. No tuning, no SimNow paths, no GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: amplitude mode not byte-identical; MACD params tuned; the orphan `失效` branch or an
unreachable MACD `失效` class remains; validation exhaustiveness broken; the comparison report
is used to select parameters in-task.

---

## P5 (A42) - Multi-Level Resonance Entry Filter

### Rationale
The daily filter is only a boolean gate ("direction != down", `positions.py:17-38`). The core
缠论 win-rate mechanism is 级别共振: take a 30m buy point only when a higher level (daily / 4H)
is itself constructive, not merely "not negative."

### Config
```python
"resonance_filter": "off",         # "off" (legacy) | "daily" | "daily_4h"
"resonance_freq_4h": "240分钟",
```

### Semantics
Add a 4H CZSC level (resample 1m -> 240min) built/updated in `backtest_engine` like the daily
level. Long-open resonance:
- `"daily"`: require daily `方向=向上` AND daily position in {中枢上方, 中枢内} (strictly
  positive, stricter than the current not-below gate).
- `"daily_4h"`: additionally require the 4H level constructive (same test on 4H).
Shorts symmetric (向下 + {中枢下方, 中枢内}). Encoded as extra `signals_all`/`signals_not` on the
open Events, consuming higher-level signal keys.

### No-lookahead & correctness
4H bar timestamp = last constituent 1m bar; the loop advances higher-level CZSC by `dt <=`
(same pattern as daily). Add a `test_4h_no_lookahead` mirroring `test_daily_no_lookahead`.

### Diagnostic-first
`diagnostics/resonance_filter_comparison_report.py`: trade_count, win_rate, PF for
off / daily / daily_4h on the honest post-P1 baseline (report only, not for selection).

### Expected files
- `chan_strategy/backtest_engine.py` (build/update 4H CZSC; inject 4H signals)
- `chan_strategy/positions.py` (resonance conditions on open events)
- `chan_strategy/config.py`
- `chan_strategy/tests/unit/test_resonance_filter.py`, `test_4h_no_lookahead.py`
- `diagnostics/resonance_filter_comparison_report.py`

### Acceptance (decidable)
- [ ] `"off"` -> byte-identical (equivalence test).
- [ ] `"daily"` blocks a long open when daily is 中枢下方 or 方向向下 even if 30m signal fires
      (unit-tested); requires strictly-positive daily, not just not-below.
- [ ] `"daily_4h"` additionally blocks when 4H is non-constructive (unit-tested).
- [ ] `test_4h_no_lookahead` passes; 4H bar timestamps are the last constituent 1m bar.
- [ ] Resonance comparison diagnostic generated (report only, RESEARCH-ONLY).
- [ ] Root + child `sync_check`, unit suite, preflight pass.

### Boundaries
Two higher levels only (daily, 4H); does not add weekly; resonance gates entries only (exits
unchanged - P8); thresholds for "constructive" are the existing categorical signals, not new
tuned numbers.

### Dev prompt
```text
Read P5. Add resonance_filter gate; "off" default byte-identical. Build a 4H CZSC level with no
lookahead. "daily" requires strictly-positive daily structure; "daily_4h" also requires 4H.
Add a read-only off/daily/daily_4h win-rate comparison. No tuning, no SimNow paths, no
GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: off mode not byte-identical; 4H level reads future bars; resonance changes exits;
new numeric thresholds introduced; comparison report used for in-task selection.

---

## P6 (A43) - 二买 Removal / Hard-Gate + ATR Chop Filter

### Rationale
二买 is measured negative expectancy: RB 二买 0/6 all losses, SC 二买 PF 0.36, recurring -3% to
-12.6% stops (`backtest_matrix`, `key_trade_behavior_review.md`). And 缠论 buy points inside a
compressed range are false; an ATR floor removes chop entries.

### Config
```python
"second_buy_mode": "baseline",     # "baseline" (legacy) | "gated" | "off"
"atr_chop_filter": "off",          # "off" (legacy) | "on"
"atr_period": 14, "atr_lookback": 100, "atr_percentile_floor": 0.30,
```

### Semantics
- `second_buy_mode`: `"off"` blocks all NEW 二买 opens (existing 二买 positions still receive
  exits/risk); `"gated"` opens 二买 only when P4 MACD divergence is present AND P5 resonance
  holds AND ATR is expanding (not in chop); `"baseline"` = current.
- `atr_chop_filter="on"`: compute ATR(atr_period) on trade-frequency bars; compute the current
  ATR's percentile vs the last `atr_lookback` bars; if percentile < `atr_percentile_floor`,
  block ALL new opens that bar (range compression). Applies to every sub-strategy.

### No-lookahead & correctness
ATR and its percentile use only bars up to the current one. The 二买 gate reads the same
current-bar signal dict already used for opens.

### Diagnostic-first
`diagnostics/second_buy_and_atr_report.py`: 二买 expectancy under baseline/gated/off, and
entry win-rate bucketed by ATR percentile, on the honest baseline (report only).

### Expected files
- `chan_strategy/positions.py` (二买 mode gate in the buy2 update path; ATR filter in the open
  path of `ChanTimingStrategy.update`)
- `chan_strategy/signals.py` or a util module (ATR + percentile helper)
- `chan_strategy/config.py`
- `chan_strategy/tests/unit/test_second_buy_mode.py`, `test_atr_chop_filter.py`
- `diagnostics/second_buy_and_atr_report.py`

### Acceptance (decidable)
- [ ] `second_buy_mode="baseline"` and `atr_chop_filter="off"` -> byte-identical (equivalence).
- [ ] `"off"` -> zero new 二买 opens across a replay; existing 二买 exits still fire
      (unit-tested).
- [ ] `"gated"` -> a 二买 signal without MACD divergence OR without resonance OR in chop does
      NOT open (unit-tested for each missing condition); with all three it opens.
- [ ] `atr_chop_filter="on"` -> an open is blocked when the current ATR percentile <
      `atr_percentile_floor` (unit-tested); allowed above.
- [ ] Diagnostic generated (report only, RESEARCH-ONLY); `atr_percentile_floor` not tuned via
      the report in-task.
- [ ] Root + child `sync_check`, unit suite, preflight pass.

### Boundaries
Does not delete the 二买 code path (kept behind `"off"`); ATR filter gates opens only, not
exits; the floor/period defaults are conservative starting points, tuning deferred to a future
holdout-validated task.

### Dev prompt
```text
Read P6. Add second_buy_mode ("baseline"|"gated"|"off") and atr_chop_filter with ATR percentile.
Baseline+off default byte-identical. "off" stops new 二买 opens (exits still fire). "gated"
requires P4 divergence + P5 resonance + ATR expansion. ATR filter blocks opens below the
percentile floor. Add a read-only 二买/ATR diagnostic. No in-task tuning, no SimNow paths, no
GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: baseline/off not byte-identical; "off" still opens 二买 or also blocks exits;
"gated" opens without all three conditions; ATR reads future bars; the floor is tuned via the
report in the same task.

---

## P7 (A44) - Symmetric Regime-Gated Shorts

### Rationale
Futures are two-sided; long-only bleeds through structural downtrends (RB, SC). The short
sub-strategies already exist (`create_first_sell_position` ...) but ship disabled. Enable them
with the same P4/P5 rigor and route by regime so the strategy trades the dominant side instead
of fighting it.

### Config
```python
"enable_short": False,             # master switch, unchanged default
"regime_model": "independent",     # "independent" (each side self-gated) | "router"
```

### Semantics
- `"independent"`: current behavior - long and short sub-strategies each gated by their own
  daily/resonance filter, can (in principle) both be active.
- `"router"`: a single regime decision per symbol from the higher level (daily trend + position)
  selects the allowed side: daily-up -> long-only, daily-down -> short-only, ambiguous
  (中枢内/无中枢 or conflicting) -> no new opens. Counter-trend opens on the wrong side are
  suppressed; existing positions still exit normally. This removes simultaneous long+short.
- Short opens additionally require the P4 MACD顶背驰 and P5 short-side resonance (向下 +
  {中枢下方,中枢内}), symmetric to the long side.

### No-lookahead & correctness
Regime uses only current higher-level signals (already lookahead-safe). The existing
`both_long_short_bars` equity metric is the router invariant.

### Diagnostic-first
`diagnostics/short_enable_report.py`: with `enable_short=True`, per-symbol short-side expectancy
and combined long+short vs long-only, on the honest baseline (report only). Focus RB/SC.

### Expected files
- `chan_strategy/positions.py` (regime router in `ChanTimingStrategy.update`; short opens gated
  by P4/P5)
- `chan_strategy/config.py`
- `chan_strategy/tests/unit/test_regime_router.py`
- `diagnostics/short_enable_report.py`

### Acceptance (decidable)
- [ ] `enable_short=False` -> byte-identical (unchanged default).
- [ ] `enable_short=True, regime_model="independent"` matches the existing enable_short=True
      behavior (equivalence vs pre-P7 short replay).
- [ ] `regime_model="router"` -> `both_long_short_bars == 0` across a replay (asserted); short
      opens require daily 向下 (unit-tested); long opens suppressed in daily-down (unit-tested).
- [ ] Short-enable diagnostic generated (report only, RESEARCH-ONLY), covering RB/SC.
- [ ] Root + child `sync_check`, unit suite, preflight pass.

### Boundaries
Backtest sub-strategies only - no SimNow short order routing; regime uses existing categorical
signals, no new tuned thresholds; does not change position sizing (P3 owns that) or exits (P8).

### Dev prompt
```text
Read P7. Keep enable_short=False default. Add regime_model ("independent"|"router"). Router
selects one side by daily regime (up->long, down->short, ambiguous->flat), suppresses
counter-trend opens, guarantees both_long_short_bars==0. Short opens require P4 顶背驰 + P5
short resonance. Add a read-only short-enable report (RB/SC focus). No SimNow order paths, no
tuning, no GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: default (enable_short=False) not byte-identical; router allows simultaneous
long+short; short opens lack P4/P5 gating; any SimNow order path touched; new numeric thresholds
introduced.

---

## P8 (A45) - Exit Overhaul + Portfolio Risk

**Note:** P8 is the heaviest phase; ship it as two sub-tasks - **P8a exits** then **P8b
portfolio** - each with its own gate and equivalence proof.

### Rationale
`key_trade_behavior_review.md` shows exits are the dominant PnL lever: the current fixed-giveback
trailing both exits winners too early and lets some give back, and the "confirmed-structure
reversal" exit lags. Separately, sub-strategies run fully independently (each symbol its own
engine) with fixed weights (10/20/30) that overweight the worst-performing 三买 and no portfolio
heat control across correlated symbols (RB/ZN/SC co-move).

### Config
```python
# P8a
"exit_model": "legacy",            # "legacy" | "structural_atr"
"atr_trail_mult": 3.0, "partial_tp_frac": 0.5,
# P8b
"portfolio_risk": "off",           # "off" | "on"
"corr_clusters": {"industrial_energy": ["RB888","ZN888","SC888"]},
"cluster_gross_cap": 1.0,          # max summed gross weight per cluster
"daily_loss_limit_pct": 0.03,      # flatten + block new opens for the day beyond this
"weighting": "fixed",              # "fixed" (legacy 10/20/30) | "risk_parity"
```

### Semantics
**P8a - exits (`"structural_atr"`):** replace the profit-side fixed-giveback trailing with an
ATR trailing stop (`trail = peak - atr_trail_mult * ATR`), keep the structural stop (center
break) as the hard structural exit, and add a partial take-profit: scale out `partial_tp_frac`
of the position at the next center boundary / measured target, then trail the remainder. The
fixed stop-loss (P1) and timeout are unchanged. `"legacy"` reproduces the current exit set.

**P8b - portfolio (`"on"`):** introduce a portfolio coordinator above the per-symbol strategies
(a new `PortfolioEngine` or a cross-symbol pass over the existing per-symbol runs):
- `weighting="risk_parity"`: weights proportional to `1/vol` (or historical expectancy x 1/vol)
  instead of fixed 10/20/30.
- cluster gross cap: summed gross weight within a `corr_clusters` group cannot exceed
  `cluster_gross_cap`; new opens that would breach it are blocked.
- daily loss limit: if a day's portfolio PnL <= `-daily_loss_limit_pct`, flatten and block new
  opens for the remainder of that trading day.

### No-lookahead & correctness
ATR trailing and vol/weights use only bars up to the current one; the daily loss limit uses
realized+unrealized equity known intraday, never future bars. The cross-symbol pass must align on
trading-day boundaries (P2b) without peeking ahead.

### Diagnostic-first
- `diagnostics/exit_model_report.py`: per-trade give-back (peak-to-exit) and early-exit
  (exit-to-subsequent-extreme) stats, legacy vs structural_atr, on the honest baseline.
- `diagnostics/portfolio_heat_report.py`: cluster gross exposure over time, count of
  loss-limit trigger days, risk-parity vs fixed weights.

### Expected files
- `chan_strategy/positions.py` (structural_atr exit model behind the gate)
- `chan_strategy/portfolio_engine.py` (new; P8b coordinator) + `backtest_engine.py` wiring
- `chan_strategy/config.py`
- `chan_strategy/tests/unit/test_exit_model.py`, `test_portfolio_risk.py`
- `diagnostics/exit_model_report.py`, `diagnostics/portfolio_heat_report.py`

### Acceptance (decidable)
- [ ] `exit_model="legacy"` and `portfolio_risk="off"` -> byte-identical (equivalence).
- [ ] `"structural_atr"`: partial TP scales out `partial_tp_frac` at the target and trails the
      remainder by `atr_trail_mult*ATR` (unit-tested); structural stop and P1 fixed stop still
      fire; timeout unchanged.
- [ ] `portfolio_risk="on"`: a fixture breaching `cluster_gross_cap` blocks the offending open
      (asserted gross <= cap); a day breaching `daily_loss_limit_pct` flattens and blocks new
      opens that day (fixture); `weighting="risk_parity"` weights computed from per-symbol vol.
- [ ] Exit-model and portfolio-heat diagnostics generated (report only, RESEARCH-ONLY).
- [ ] Root + child `sync_check`, unit suite, preflight pass.

### Boundaries
No live order routing / SimNow changes; the portfolio coordinator is backtest-only; ATR/vol
params are conservative starting points, tuning deferred to a holdout-validated task; P8a ships
and passes review before P8b.

### Dev prompt
```text
Read P8. Ship P8a (exit_model gate; "legacy" byte-identical; "structural_atr" = structural stop
+ ATR trailing + partial TP; P1 fixed stop and timeout unchanged) and pass review BEFORE P8b
(portfolio_risk gate; "off" byte-identical; cluster gross cap, daily loss limit, risk-parity
weighting via a backtest-only coordinator). Add read-only exit-model and portfolio-heat reports.
No SimNow order paths, no in-task tuning, no GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: legacy/off not byte-identical; structural_atr changes the P1 fixed stop or timeout;
partial-TP/trail math wrong; the cluster cap or loss limit is not enforced in the fixtures; the
coordinator reads future bars; P8b ships before P8a passes; any SimNow path touched.

---

## Cross-Phase Notes

- **Switch stacking:** all switches default to legacy, so any subset can be enabled for a gated
  experiment while the rest stay baseline. A combined "all-on" configuration is itself a future
  holdout-validated evaluation, not a per-phase acceptance criterion.
- **Promotion:** no phase may claim `GOAL PASSED` or profitability from pre-2026-04-24 data. A
  promotion decision uses the post-2026-04-24 + SimNow stream after the relevant switches are on.
- **Each phase is its own handoff task** (design -> dev -> review -> done) with the section above
  as the design contract; do not batch multiple phases into one dev handoff.
```
