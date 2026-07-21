<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

# A88 — Joint-Clock Replay Real-Data Acceptance / Sanity-Check

**Date:** 2026-07-17
**Artifact under check:** A87 joint-clock replay — `PortfolioEngine._build_joint_report()` with
  shared `PortfolioLedger` (`sizing_model="risk"` + `portfolio_risk="on"`)
**Acceptance checker:** `diagnostics/joint_replay_acceptance_check.py`
**Check output:** `diagnostics/joint_replay_acceptance_check.json`
**DB path:** `D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db` (from `chan_strategy/config.py`)
**Symbols:** AP888, RB888, SC888, A888, ZN888
**Window:** 2022-01-01 ~ 2026-04-24 (identical to A83/A84)
**Sizing model:** `risk`; **portfolio_risk:** `on`; **initial capital:** 1,000,000

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> This artifact evaluates a research backtest replay mechanism. It is not a claim of trading
> discovery, not a trading recommendation, and not evidence of profitability.

---

## Methodology Statement

The acceptance script runs the A87 joint-clock replay end-to-end on the real historical DB:
one `BacktestEngine.bar_generator()` per symbol stepped through a single merged clock, with a
shared `PortfolioLedger` tracking currency-based equity/margin and blocking new opens via the
existing `Position._size_open()` formula (true shared values normally; deliberately saturated
values when a gate is breached). It then re-runs each symbol **independently** through its own
`BacktestEngine` with `sizing_model="risk"` — the exact methodology A84 used and validated —
and compares the two. No parameters were introduced or tuned; the symbol set, window, and all
config defaults are exactly what A83/A84 already established.

Two consecutive executions of the checker produced byte-identical check JSON, confirming the
joint driver is deterministic on real data.

---

## Sanity Check Results

### 1. No crash / no data errors across all 5 symbols

**Result: PASS**

`symbol_errors` is empty and no `symbol_reports` entry contains an error. All five symbols
loaded their `{symbol}_1M_raw` tables (via the `_infer_table_names()` fix from A84) and ran to
completion: 242 total closed trade pairs in the joint report.

### 2. Equity/margin arithmetic sanity on the joint equity curve

**Result: PASS**

| Metric | Value |
|--------|------:|
| Joint equity-curve rows (unique merged-clock ticks) | **19,470** |
| First tick | 2022-01-11 13:59:00 |
| Last tick | 2026-04-24 23:59:00 |
| Min equity | 885,950.40 |
| Max equity | 1,005,958.56 |
| Final equity | 949,526.41 |
| Max total open margin | 56,140.55 |
| Final total open margin | 0.00 |
| Max margin utilization | **6.21%** |
| Max bar-over-bar utilization jump | 3.44 pp |

- `equity > 0` at every tick; `total_open_margin >= 0` at every tick; all values finite.
- Utilization stays in [0, 1] and is never wildly discontinuous (max jump 3.44 pp).
- The row count **19,470 exactly matches A83's independent-aggregation ledger row count** for
  the same symbols/window, and the first/last ticks match the earliest/latest per-symbol data
  ranges recorded by A84 — the merged clock covers the same timestamp union.
- Final equity reconciliation: 1,000,000 + (−57,473.59 realized) + 7,000.00 unrealized
  (RB888's still-open position valued at its final bar close; A83 likewise recorded RB888 with
  non-zero final margin) = 949,526.41. ✓

### 3. `blocked_opens` coherence — **non-empty, and that is the coherent outcome**

**Result: PASS (58 entries, all coherent)**

`blocked_opens` was **not empty**: 58 entries, **all** with reason `daily_loss_limit`, **all**
dated 2022-03-30, every `dt` inside the run window. Distribution:

| Symbol | Blocked pre_open ticks (2022-03-30) |
|--------|------------------------------------:|
| AP888 | 7 |
| A888 | 11 |
| RB888 | 12 |
| SC888 | 14 |
| ZN888 | 14 |

The ledger recorded exactly **one** daily-loss-limit trigger in the 4.3-year window:

```
2022-03-30 09:29:00  trading_day=2022-03-30  equity=972,346.63  day_pnl_pct=-3.0044% (limit -3%)
```

From that tick until the end of that calendar day, every symbol's `pre_open` was gated
(portfolio-wide block, as designed). Entries span 09:29 → 23:59 on 2022-03-30 and stop at each
symbol's own session end (AP888 last at 14:59 — no night session; A888/RB888 last at 22:59;
SC888/ZN888 last at 23:59). Under the configured `daily_agg="natural"` semantics the evening
session belongs to calendar day 2022-03-30, so the block persisted through the night session
and lifted at the 2022-03-31 trading-day rollover — matching the A87 unit-test behavior ("the
block clears at the next trading day").

**Why no margin-cap blocks occurred:** zero entries of `symbol_margin_cap` or
`cluster_gross_cap:*`. This is the expected outcome the design stage anticipated: A84 measured
peak portfolio margin utilization of only ~6.49% for this symbol set (the joint replay measured
6.21%), versus `max_margin_pct=0.50`, `max_symbol_margin_pct=1.0`, `cluster_gross_cap=1.0` —
no margin cap ever comes close to binding on this real data, so margin gating correctly never
fired. The daily loss limit is a different gate (day PnL ≤ −3%), and it fired exactly once
during the March 2022 commodity volatility spike. An empty `blocked_opens` would have been
valid; the observed non-empty list is equally coherent and exercises the gating path on real
data. Nothing was manufactured to force this outcome.

### 4. Comparison against A83/A84's independent-aggregation ledger

**Result: PASS (divergence present, fully explained by the gating event)**

Per-symbol trade-sequence comparison, joint replay vs independent re-run (A84 methodology):

| Symbol | Trades (joint / indep) | Timing | Volume diffs | Joint PnL | Independent PnL |
|--------|:---------------------:|:-------|-------------:|----------:|----------------:|
| AP888 | 73 / 73 | identical | 10 | +27,225.67 | +33,595.59 |
| RB888 | 43 / 43 | identical | 3 | −75,824.73 | −74,395.27 |
| SC888 | 0 / 0 | identical | 0 | 0.00 | 0.00 |
| A888 | 48 / 48 | identical | 12 | −16,139.29 | −15,113.73 |
| ZN888 | 78 / 78 | **diverged at index 5** | 15 | +7,264.77 | −9,550.17 |
| **Total** | **242 / 242** | | | **−57,473.59** | **−65,463.57** |

A83's recorded portfolio total: **−65,463.57** — the fresh independent re-run reproduces it
exactly. The joint total differs by +7,989.99 (12.2% relative, within the pre-set 20%
tolerance), with two identified, design-intended causes:

1. **ZN888's sequence diverges exactly at its first blocked open** — the expected behavior per
   the task design. Trade index 5 (`三买多头`): the independent run opened 2022-03-30 22:59 @
   26,875; that `pre_open` fell inside the daily-loss-limit window (the 22:59 tick appears in
   `blocked_opens_full`), so the joint replay rejected the open. The strategy re-signalled on a
   later bar and the joint run entered 2022-03-31 00:29 @ 27,005 — the first execution bar
   after the trading-day rollover lifted the block. Both versions closed identically
   (2022-04-13 14:59 @ 28,405). The delayed re-entry changed ZN888's equity trajectory and,
   with it, the lot counts of 15 of its 78 trades; the combined effect is ZN888's +16,814.94
   PnL swing. Trades 0–4 are timing-identical; nothing diverged before the first blocked open.
2. **Volume differences on timing-identical trades are intended shared-equity sizing, not
   gating.** The joint replay sizes each open off the *shared portfolio* equity
   (`risk_amount = equity * risk_per_trade_pct`), whereas A83/A84's independent runs size off
   each symbol's *standalone* equity. The two bases differ by the other symbols' cumulative
   PnL, so integer-lot counts differ on some trades (AP888 10/73, RB888 3/43, A888 12/48,
   ZN888 15/78). This is the documented A87 design (`PortfolioLedger` feeds the true shared
   `equity` into the existing `_size_open()`), not an anomaly.

The other four symbols attempted no opens during the blocked window, so their sequences stayed
timing-identical to A83/A84's independent runs despite the 58 speculative gating-pressure
records.

### 5. Case-insensitive cluster membership on real symbol names

**Result: PASS**

`_symbol_clusters()` maps uppercase and lowercase symbol lists identically (`AP888`/`A888` → no
cluster; `RB888`/`SC888`/`ZN888` → `industrial_energy`). A live `PortfolioLedger` fed 1.0
margin per symbol reports `margin_by_cluster = {"industrial_energy": 3.0}`, confirming the
three real symbols group under the cluster in the joint-replay ledger itself.

---

## Verdict

**The A87 joint-clock replay runs correctly end-to-end on real data and its gating mechanism
is coherent.**

- All five requested sanity checks passed against the real historical DB (`overall_accepted:
  true` in the check JSON; the same JSON was reproduced byte-identically on a second run).
- No bugs were found; no production code was changed (the only new code is the read-only
  diagnostics checker itself). Nothing architecturally significant surfaced.
- The gating mechanism fired for real exactly once (daily loss limit on 2022-03-30), behaved
  exactly as the unit tests specify (portfolio-wide, same-day, auto-reset next trading day),
  and ZN888's trade sequence diverged from its independent run exactly at the first blocked
  open, as the design predicted.

**Scope boundary (unchanged, reinforced):** this confirms correctness of the replay and its
block-new-opens gating on one real dataset. It does **not** constitute a trading
recommendation or promotion evidence; forced liquidation on a daily-loss breach is **not**
implemented (A89, not yet scoped — the joint report carries
`flatten_on_breach="not_implemented_see_A89"`); and this does **not** prove the joint replay is
"production-ready".

---

## Manual Verification

Commands run natively for this acceptance:

```bash
# 1. Joint replay on real DB + all sanity checks (run twice, identical JSON)
python examples/czsc_strategy/diagnostics/joint_replay_acceptance_check.py

# 2. Unit tests
python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"

# 3. Sync gates
python tools/sync_check.py
python tools/sync_check.py --root examples/czsc_strategy

# 4. Preflight
powershell -ExecutionPolicy Bypass -File examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight
```

Counts from the joint replay run:

- Symbols run: 5 (zero errors)
- Joint equity-curve rows: 19,470 (matches A83 ledger row count)
- Total closed pairs: 242
- Total realized PnL (joint): −57,473.59 vs −65,463.57 (A83/A84 independent sum)
- Max margin utilization (joint): 6.21% (A83: 6.49%)
- `blocked_opens`: 58, all `daily_loss_limit`, all 2022-03-30 (1 trigger, −3.0044%)
- Daily-loss-limit forced liquidations: 0 (not implemented, A89 scope)

Test results:

- Unit tests (`not realdb`): **751 passed, 4 deselected**
- `python tools/sync_check.py`: **PASS**
- `python tools/sync_check.py --root examples/czsc_strategy`: **PASS**
- `run_next_work.ps1 -Preflight`: **Preflight complete; 192 SimNow unit tests passed**

---

## A90 Addendum (2026-07-20): Forced-Liquidation Wiring + Acceptance-Script Fix

**What changed since the A88 acceptance above:** A90 implemented the forced liquidation that
A88 explicitly scoped out (`flatten_on_breach` was `"not_implemented_see_A89"`). Per
`docs/design/a89-forced-liquidation-design.md`, the joint driver now flattens the triggering
symbol at the trigger tick and every other symbol at its own next `"pre_open"` yield (using
that symbol's own current-tick `bar.close`), via the pre-existing
`ChanTimingStrategy.flatten_all_positions()` primitive. The joint report now carries a
`flat_events` list and `flatten_on_breach="implemented_see_A90"`.

**Honest headline: `flat_events` is EMPTY on this real-data run — and that is the correct
outcome, not a wiring failure.** Root cause (independently confirmed by claude-code during
mid-dev due diligence, via a monkeypatch tracing every `flatten_all_positions` call — 0 calls
traced): the single real trigger (2022-03-30 09:29:00, day PnL −3.0044%) lands on the exact
bar where AP888's own stop-loss fired (`2022-03-24 14:29:00 -> 2022-03-30 09:29:00 止损`).
The strategy's exit logic runs inside `strategy.update()`, *before* the post-bar
`check_daily_loss_limit()` for that tick, so by the time the breach is detected AP888 already
has zero open positions; the other four symbols also had none open at that moment. The
driver's `if not open_before: return` guard correctly flattens nothing when there is nothing
to flatten. The full trade sequence and total realized PnL of the joint replay are unchanged
from the A88 baseline (−57,473.59), proving the A90 wiring has zero side effects on a
no-positions-at-trigger run.

**The actual bug found by this re-run was in this acceptance script, not the driver:** check
`flat_events_cover_trigger_days` previously assumed a trigger day must always produce a
non-empty `flat_events`, failing `overall_accepted` on this legitimate empty case. Fix
(applied to `joint_replay_acceptance_check.py`, check 6): trigger-day coverage is now
informational; instead, an empty `flat_events` is gated on being *explainable* — for every
trigger at least one pair must close exactly on the trigger tick (here: AP888's stop-loss at
`2022-03-30 09:29:00`, surfaced under `flat_events_trigger_explanations` /
`flat_events_non_empty_or_explained` in the check JSON). `_build_joint_report()` itself was
verified correct and was NOT modified as part of this fix.

**Where the flatten mechanism itself is proven:** the constructed-fixture unit tests in
`tests/unit/test_a87_joint_replay.py` — including
`test_daily_loss_limit_flattens_open_positions` (triggering symbol flattened at the trigger
tick; `flat_events` asserted field-by-field; fires exactly once at the False→True transition)
and `test_daily_loss_limit_lagging_symbol_flattens_at_own_price` (a lagging symbol is
flattened at its own next `pre_open` at its OWN close of 95.0, never the trigger tick's 91.0)
— are the actual proof the wiring fires correctly when positions exist at trigger time. This
real-data window simply never exercises a non-empty `flat_events`; we do not claim otherwise.

**A88 scope boundary update:** the sentence above saying forced liquidation "is **not**
implemented (A89, not yet scoped)" was accurate as of A88. As of A90 it is implemented and
unit-tested; on this specific real-data window it legitimately produced zero flat events.
Everything else in the A88 acceptance (gating coherence, cluster checks, determinism,
comparison vs independent runs) is unaffected and re-verified by the re-run.
