<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

# A92 — Forced-Liquidation Real-Data Stress Check (Tightened Threshold)

**Date:** 2026-07-21
**Artifact under check:** A90 forced liquidation — the flatten driver in
  `PortfolioEngine._build_joint_report()` (`sizing_model="risk"` + `portfolio_risk="on"`)
**Stress checker:** `diagnostics/joint_replay_flatten_stress_check.py`
**Check output:** `diagnostics/joint_replay_flatten_stress_check.json`
**Symbols:** AP888, RB888, SC888, A888, ZN888 (identical to A83/A84/A88/A90)
**Window:** 2022-01-01 ~ 2026-04-24 (identical to A83/A84/A88/A90)
**Sizing model:** `risk`; **portfolio_risk:** `on`; **initial capital:** 1,000,000
**Stress threshold:** `daily_loss_limit_pct=0.005` (temporary runtime override
  for this diagnostic run only — **not** a config default change; the production
  default stays `0.03`)

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> This artifact validates a risk-mechanism wiring on real historical data. It is
> not a claim of trading discovery, not a trading recommendation, and not
> evidence of profitability.

---

## Why this exists (audit H3)

A90's forced liquidation was unit-tested with constructed fixtures, but on the
real 5-symbol window the production default (`0.03`) triggers exactly once
(2022-03-30 09:29, day PnL −3.004%) at a moment when every symbol was already
flat — so `flat_events` had **never** been non-empty on real data. The
cross-symbol deferred-flatten timing logic (a lagging symbol must flatten at
**its own tick's** `bar.close`, never the trigger tick's price —
`docs/design/a89-forced-liquidation-design.md` §3) had therefore never been
exercised by real market data with real timestamp skew.

## Threshold search (exploratory, all values recorded)

A shadow run (`.tmp/a92_shadow_probe.py`) mapped the joint replay's full
daily-PnL trajectory in ONE pass with the limit disarmed
(`daily_loss_limit_pct=10.0`, 358.8s, 68,223 check samples), then for each
candidate threshold found its **first** crossing tick and cross-referenced the
shadow run's trade pairs for symbols holding a genuinely open position
(`open_dt <= t < close_dt`) at that moment:

| Threshold | First crossing | Open positions at first crossing | Verdict |
|-----------|----------------|----------------------------------|---------|
| 0.025 | 2022-03-30 09:29 (−3.004%) | none | re-exercises the known empty-flatten case only |
| 0.02  | 2022-03-30 09:29 (−3.004%) | none | same |
| 0.015 | 2022-03-30 09:29 (−3.004%) | none | same |
| 0.01  | 2022-03-30 09:29 (−3.004%) | none | same |
| 0.0075 | 2022-03-30 09:29 (−3.004%) | none | same |
| **0.005** | **2022-01-14 22:29 (−0.515%)** | **ZN888 一买多头 (opened 2022-01-13 09:29)** | **first trigger flattens a real open position** |

0.005 (0.5% daily loss) is a plausible risk parameter (the A87/A90 unit
fixtures themselves use 0.4–0.5%), not an absurd value chosen to force a green
checkmark. A real run at 0.005 was then executed and independently verified.

## Real-run results @ `daily_loss_limit_pct=0.005`

* **49 loss-limit triggers**, **101 flat events** across 4 symbols
  (ZN888: 31, AP888: 30, RB888: 22, A888: 18; SC888: 0 — it never held an open
  position at any trigger moment).
* **68 immediate** events (triggering symbol flattened at the trigger tick) +
  **33 deferred** events (lagging symbols flattened at their own next
  `"pre_open"` tick) — the deferred path **is** exercised on real data.
* **All 101 `flat_price`s match that symbol's OWN trade-bar `close` at the
  event's own `dt`** — verified against bar data independently re-loaded from
  the same DB through the same `resample_bars()` pipeline (no strategy logic),
  not against the report's own numbers.
* **No event closes before it opened** (`open_dt <= flat_dt` for all 101).
* `overall_accepted: true` in `joint_replay_flatten_stress_check.json`.
* No bug found in the flatten mechanism; `portfolio_ledger.py` and the flatten
  driver are untouched.

### The cross-symbol deferred-flatten price invariant, proven with real skew

Trigger **2022-04-22 21:59** (night session, Friday):

* **A888 一买多头** (triggering symbol): flattened **immediately** at the
  trigger tick at **its own** close **6115.0** ✔
* **AP888 一买多头** (lagging symbol, opened 2022-04-22 13:59): had no 21:59
  tick — flattened **3,570 minutes later** at its own next pre_open
  **2022-04-25 09:29** (Monday) at **its own** close **8561.0** ✔ — NOT 6115,
  NOT any price from the trigger tick.

The largest observed deferred skew in the run is exactly this 3,570-minute
(weekend-spanning) case — precisely the multi-symbol timing scenario unit
fixtures can only simulate by hand.

### Edge case documented (not a bug): same-bar open-then-flatten

Exactly 1 of 101 events has `open_dt == flat_dt`:
**ZN888 一买多头 @ 2024-09-05 13:59** (the trigger tick itself, immediate
kind). ZN888 opened the position at that bar's own `pre_open` (bar open
23030.0 — the limit was not yet active, so the open was allowed), the breach
was detected post-bar, and the position was flattened at the same bar's close
(22900.0). The sequence is causally ordered within the bar (open at bar open →
flatten at bar close) with no lookahead; the checker therefore gates
`open_dt <= flat_dt` and additionally requires any `open_dt == flat_dt` event
to be of the immediate (triggering-symbol) kind — which holds.

This is why the checker's ordering gate is `open_dt <= flat_dt` rather than
the stricter "predates" phrasing from the task design: the design's intent
("never close before the position exists") is fully preserved; the strict `<`
form would falsely flag this legitimate same-bar sequence. Recorded in the
A92 Decision Log.

### First trigger matches the shadow-run prediction exactly

2022-01-14 22:29 (day PnL −0.5148%): ZN888 一买多头 (opened 2022-01-13 09:29)
flattened immediately at its own close 24460.0 — the exact symbol/position the
shadow trajectory predicted would be open at that crossing.

## Honest scope statement

* This run uses an **artificially tightened** `daily_loss_limit_pct=0.005`
  for stress-testing purposes. It is **not** the production default and does
  **not** imply `daily_loss_limit_pct=0.03` triggers this often on real data —
  A88 established the real 0.03 default triggers once in ~4 years for this
  symbol set (2022-03-30).
* Nothing here changes `chan_strategy/config.py`, `portfolio_ledger.py`, or
  the flatten driver in `_build_joint_report()`. The mechanism being validated
  was not modified.
