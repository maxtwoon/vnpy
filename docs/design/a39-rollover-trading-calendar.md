# A39 Design: Rollover-Pollution Diagnostic + Trading-Calendar Daily Aggregation (P2)

**Task:** Roadmap phase **P2** (from `docs/design/a38-phase-contracts-p2-p8.md`). Two data-hygiene
changes for the 888 continuous contracts: (Phase 0) a read-only rollover-pollution diagnostic,
and (Phase 1) a gated trading-calendar daily aggregation that stops splitting a futures trading
day across the night-session/midnight boundary.

**Scope:** Phase 0 is read-only. Phase 1 changes daily-bar construction **behind a config switch
that defaults to the current natural-day behavior (byte-identical)**. No signal semantics, no
stop logic, no SimNow order paths.

**Authorization:** Same as A38 — user-authorized strategy-adjacent changes in the root `vnpy`
workflow, under the A34 guardrails (gated default-off, diagnostic-first, no OOS tuning,
research-only, no SimNow order changes).

---

## 1. Background

- **H4 (audit) / review item A2.** The 888 tables are a raw multi-contract splice
  (`found_spliced`). Rollover gaps are read by the 笔/分型/中枢 machinery as real moves →
  fake breakouts (三买 / 结构失效), fake gap stops, fake divergence. SC (largest roll spread) is
  the worst-performing, most parameter-sensitive symbol.
- **Confirmed data fact (2026-07-10).** The raw tables carry a **`real_symbol` column** that
  holds the underlying contract (e.g. `sc888_1M_raw.real_symbol = "sc2202"`), and it changes at
  each rollover. So rollover dates are detectable **exactly** from `real_symbol` transitions — a
  price-gap heuristic is only a fallback when the column is absent.
- **Session boundary.** `data_adapter.resample_bars` builds daily bars by **natural calendar
  date** (`data_adapter.py:61-83`). Chinese-futures night sessions (start ~21:00, run past
  midnight) belong to the **next trading day**, so natural-day grouping splits one trading day
  into two "daily" bars — the daily trend filter then consumes a structure that does not match
  the exchange trading day.

A34's H4 treatment is "risk declaration + rollover diagnostic before any data rebuild." A39
delivers that diagnostic and, additionally, the trading-calendar daily fix behind a gate.

---

## 2. Config switches

Add to `STRATEGY_CONFIG` (`chan_strategy/config.py`):

```python
"daily_agg": "natural",            # "natural" (legacy) | "trading_calendar"
"night_session_start_hour": 20,    # bars with hour >= this are evening-session -> next trading day
```

`"natural"` is the default and MUST reproduce current daily bars byte-for-byte.

---

## 3. Phase 0 — Rollover-Pollution Diagnostic (read-only; ship first)

New `examples/czsc_strategy/diagnostics/rollover_exclusion_report.py` (+ test). Read-only; must
mark missing data explicit, never silently pass.

### 3.1 Transition detection

- **Primary:** load the raw table's `real_symbol` (or `symbol`-vs-underlying) column; a
  transition day = the first `datetime`'s date where `real_symbol` differs from the previous
  row's. Emit the ordered list of `(date, from_contract, to_contract)`.
- **Fallback (only if no such column):** flag day-boundary close→open jumps exceeding a stated
  multiple of trailing ATR; label `detection_method = "price_gap"` in the report.

### 3.2 Exclusion comparison

Run the existing backtest (close-model baseline; `stop_execution_model="close"`) per symbol, then
recompute the same run's metrics after **removing signals/trades whose open OR close falls within
`transition_date ± 1 trading day`**. Report per symbol:

- `transition_dates` (with contracts), `detection_method`
- `trade_count_before` / `trade_count_after`
- `return_before` / `return_after`
- `drawdown_before` / `drawdown_after`
- `stop_loss_overshoot_before` / `stop_loss_overshoot_after` (worst stop loss + overshoot count,
  reusing the A38/A35 overshoot definition)
- `unavailable` reason if the symbol's contract column or bars are missing.

### 3.3 Output

`rollover_exclusion_report_YYYY-MM-DD.{json,md}`, both carrying
`Diagnostic only, not a trading recommendation.`; no `GOAL PASSED`; evidence **git-tracked**
(diagnostics/ is git-ignored → `git add -f`, per the A37/A38 lesson).

---

## 4. Phase 1 — Trading-Calendar Daily Aggregation (gated)

Change the daily path of `resample_bars` (and its caller in `backtest_engine.py`) so that under
`daily_agg="trading_calendar"` bars are grouped by **trading day**, not natural date.

### 4.1 Trading-day mapping (deterministic, no external calendar)

Let `day_session = [8, 16)` hours (used only to derive trading dates). Define
`trading_dates` = sorted set of distinct dates `D` that have >=1 bar with `hour in day_session`.
For a bar at date `D`, hour `H`:

- **evening bar** (`H >= night_session_start_hour`): `trading_day = min{ t in trading_dates : t > D }`
  (the next trading date strictly after `D`). This rolls Mon-night 21:00-23:59 onto Tue, and
  Fri-night onto Mon.
- **non-evening bar** (`H < night_session_start_hour`, i.e. 00:00-day-session): `trading_day = D`
  if `D in trading_dates` else `min{ t in trading_dates : t >= D }` (post-midnight night bars on a
  non-trading calendar date, e.g. Saturday, roll to the next trading date).
- **fallback:** an evening bar with no later trading date (tail of data) keeps `trading_day = D`
  and is counted in a `notes` field.

Group by `trading_day`; the daily bar is OHLC over the group (open = first, close = last,
high/low = extremes, vol/amount summed); **timestamp = the last constituent bar's `dt`** (so the
no-lookahead property is preserved).

### 4.2 No-lookahead

The daily-bar timestamp remains the last constituent 1-minute bar, and the main loop advances the
daily CZSC by `dt <=` exactly as today; the existing `test_daily_no_lookahead` must pass under
both modes. Full exchange holiday calendar is a documented later refinement — the
"nearest-following-trading-date" rule is the first cut.

---

## 5. Expected file changes

- `examples/czsc_strategy/chan_strategy/config.py` (two keys + doc)
- `examples/czsc_strategy/chan_strategy/data_adapter.py` (trading-day mapping in the daily path;
  the intraday minute path is unchanged)
- `examples/czsc_strategy/diagnostics/rollover_exclusion_report.py` (tracked)
- `examples/czsc_strategy/tests/unit/test_rollover_exclusion_report.py`
- `examples/czsc_strategy/tests/unit/test_data_adapter.py` (trading-calendar grouping cases)
- a short Chan-strategy risk note documenting 888 `found_spliced` + `real_symbol` as the rollover
  source and that price adjustment across rollovers is **not** applied (declaration, per H4)
- `rollover_exclusion_report_YYYY-MM-DD.{json,md}` (tracked evidence)

---

## 6. Acceptance Criteria (decidable)

- [ ] `STRATEGY_CONFIG["daily_agg"]` (`"natural"` default | `"trading_calendar"`) and
      `night_session_start_hour` exist and are documented.
- [ ] **Natural equivalence:** with `daily_agg="natural"`, the daily-bar sequence (dt, OHLC,
      vol) is byte-identical to the current output on >=2 symbols x 1 year (unit + a resample
      golden test).
- [ ] **Trading-calendar grouping (unit):** a fixture with an evening session crossing midnight
      (e.g. bars at 22:00 and 01:00 plus next day-session 10:00 of the same trading day)
      aggregates into ONE daily bar keyed to the trading day; a Friday-night bar rolls to the
      next present trading date (not Saturday); a post-midnight bar on a non-trading date rolls
      forward.
- [ ] `test_daily_no_lookahead` passes under both `daily_agg` modes; daily-bar timestamps are the
      last constituent 1-minute bar.
- [ ] **Rollover diagnostic:** `rollover_exclusion_report_*.{json,md}` generated; AP/RB/SC/A/ZN
      each have `transition_dates` (with `from`/`to` contracts from `real_symbol`) or an explicit
      `unavailable` reason; `detection_method` stated (`real_symbol` primary); before/after
      `trade_count` / `return` / `drawdown` / `stop_loss_overshoot` all present.
- [ ] Both reports carry the RESEARCH-ONLY disclaimer; no `GOAL PASSED`; evidence git-tracked
      (not only regenerated on disk).
- [ ] 888 `found_spliced` + no-cross-rollover-adjustment declaration written to a tracked doc.
- [ ] No threshold tuned; no pre-2026-04-24 data used for any selection; no SimNow order/cancel/
      send paths changed; no new `send_order`/`cancel_order`/`buy`/`sell`/`short`/`cover`.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight`
      passes.

---

## 7. Boundaries

- No vendor data-feed rebuild; no back-adjusted / spread-smoothed price reconstruction — A39
  **declares** the splice and **excludes** rollover windows only in the diagnostic; it does not
  alter live prices.
- A39 does **not** gate live opens around rollover days (whether to do so is a separate future
  decision informed by this diagnostic).
- Full exchange holiday calendar is deferred; the trading-date set is derived from present
  day-session dates.
- `daily_agg` changes only the **daily filter** level; the 30-minute trade level and all signal
  logic are untouched.

---

## 8. Dev Handoff Prompt (dev = kimi-code)

```text
Read HANDOFF.md and docs/design/a39-rollover-trading-calendar.md. Implement A39 in order.

Phase 0 (read-only) first:
- Add diagnostics/rollover_exclusion_report.py: detect 888 rollover dates from the raw table's
  real_symbol column (fallback: ATR-scaled day-boundary gap, labelled). For each of
  AP/RB/SC/A/ZN, run the close-model baseline backtest and recompute metrics excluding
  signals/trades within transition_date +/- 1 trading day; report trade_count/return/drawdown/
  stop_loss_overshoot before/after + transition contracts. Mark missing data unavailable.
  RESEARCH-ONLY banner; git add -f the script and the report JSON/MD.
- Write a tracked risk note: 888 is found_spliced, real_symbol is the rollover source, no
  cross-rollover price adjustment is applied.

Phase 1 (gated) next:
- Add STRATEGY_CONFIG["daily_agg"] ("natural" default | "trading_calendar") and
  night_session_start_hour (20). "natural" must be byte-identical (golden resample test).
- In data_adapter.resample_bars daily path, under "trading_calendar" map each bar to a trading
  day per design 4.1 (evening bar hour>=night_start -> next trading date; non-evening -> its own
  trading date else next; timestamp = last constituent bar). Preserve no-lookahead
  (test_daily_no_lookahead passes both modes).

Do not tune thresholds, do not use pre-2026-04-24 data for selection, do not touch SimNow order
paths, no GOAL PASSED. Run:
- python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
- python tools/sync_check.py ; python tools/sync_check.py --root examples/czsc_strategy
- powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
- python tools/handoff.py next --actor kimi-code --summary "A39 P2 rollover diagnostic + trading-calendar daily implemented"
```

---

## 9. Review Checklist (review = codex)

Reject if: `"natural"` daily bars are not byte-identical (non-empty golden diff); the
trading-day mapping reads future bars or changes the daily timestamp rule; transition detection
does not use `real_symbol` when present (or the fallback is unlabelled); any before/after report
field is missing or hidden by aggregation; proof lives only in a git-ignored file; any threshold
tuned or pre-2026-04-24 data used for selection; any SimNow order path changed; a report claims
`GOAL PASSED`; `sync_check` (root or child) fails.

Accept if all Section 6 boxes are checked and the handoff advances to review.
