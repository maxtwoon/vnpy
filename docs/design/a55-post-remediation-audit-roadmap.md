# A55 Design: 2026-07-13 Post-Remediation Re-Audit Roadmap

**Task:** Convert `docs/review/ai_trading_review_2026-07-13.md`'s 6 new medium findings (plus 7
low findings) into a phased, dev-ready remediation sequence with explicit gates, continuing the
same design→dev→review→done discipline used for A38-A54.

**Scope:** Design only. Do not implement any fix in this document. Do not tune parameters, do not
use pre-2026-04-24 data to select any new value, do not present any historical result as a fresh
profitability proof.

**Status:** DRAFT — not yet started as a HANDOFF task. Produced 2026-07-13 immediately after the
post-remediation re-audit completed (which scored the strategy 68/100, up from 56/100, with no
fatal dimension). This document assigns the next task IDs (**A55-A60**) but does not promote any
of them; promote and start each phase individually, in the sequence below, following the
established one-task-at-a-time house rule.

---

## 1. Background

`docs/review/ai_trading_review_2026-07-13.md` (an independent read-only re-audit by a
general-purpose subagent, spot-verified by claude-code against the actual current code — every
citation below was independently re-confirmed 2026-07-13, not merely relayed) found that all 13
findings from the 2026-07-12 audit are genuinely addressed (8 fully fixed, 3 fixed-with-residual,
1 partially fixed and already relapsing, 1 reasonably deferred) — the A49-A54 remediation was
real engineering, not cosmetic. However, the remediation's OWN new code (A47's partial-TP/ATR
trailing chain, A48's portfolio replay, A51's limit tagging) introduced **6 new medium-severity
findings**, plus 7 low-severity ones. No finding is 🔴 high or fatal.

The 6 new medium findings, all independently re-verified against current code 2026-07-13:

1. **Partial-TP transaction cost double-scaling** (`positions.py:867`, in `_scale_out`):
   `transaction_cost = full_transaction_cost * scale_fraction` — but `full_transaction_cost`
   (`2 * commission_rate + slippage`) is already a per-unit round-trip rate that gets multiplied
   by `scale_volume` in the `pnl_currency` formula (confirmed at `positions.py:869-871`); dividing
   the *rate itself* by `scale_fraction` on top of that double-discounts the cost. Compare against
   `_close_long` (`positions.py:970-971`), which correctly uses the undivided
   `2 * self.commission_rate + self.slippage` rate. This systematically understates costs for any
   trade that goes through a partial-TP leg, biasing `exit_model="structural_atr"` vs `"legacy"`
   A/B comparisons in `structural_atr`'s favor.
2. **No profit-side protection before the first partial-TP event fires** (`positions.py:688-698`,
   the `structural_atr` `elif` chain in `Position.update`): `elif self._check_atr_trailing_stop(...)`
   is only reached once `_partial_tp_done is True`. A49 fixed the specific case where a lot-floor
   skip left the flag permanently `False`; it did not change the structural fact that ATR trailing
   is gated behind partial-TP firing at all. A position whose directional target never fires has
   zero profit-side protection under `structural_atr` for its entire life (only stop-loss/timeout
   remain) — a materially different risk profile than `"legacy"`'s trailing-from-open behavior,
   undocumented in `config.py`'s comment or the A47 design.
3. **Case-sensitive `SYMBOL_LIMIT_CONFIG` lookup silently fails open** (`backtest_engine.py:314`):
   `SYMBOL_LIMIT_CONFIG.get(self.symbol, {}).get("limit_pct")` — `SYMBOL_LIMIT_CONFIG`'s keys are
   all uppercase (`limit_config.py:19-55`), but the data layer explicitly supports lowercase
   symbol codes (`data_adapter.py:317`'s `COLLATE NOCASE`) and position/weight code normalizes via
   `_research_symbol_key()` (`positions.py:302-304`) — only the limit lookup doesn't. A lowercase
   `self.symbol` silently produces `limit_pct=None`, and every `pairs` entry gets
   `is_entry_at_limit=False`/`is_exit_at_limit=False` with no warning — a false-negative tag that
   looks like "checked, not at limit" but was never actually checked.
4. **No guard on the `sizing_model="risk"` + `portfolio_risk="on"` combination**
   (`portfolio_engine.py:516-527`): the portfolio replay's ledger unconditionally uses
   `pnl_pct * abs(weight) * initial_capital` (proportional-weight accounting) and never consumes
   risk-mode's `pnl_currency`/integer-lot/margin fields — `portfolio_engine.py` contains zero
   references to `sizing_model`. When both gates are on, the per-symbol report is currency-based
   and the portfolio report is weight-based simultaneously, and `daily_loss_limit_pct`'s trigger
   check uses a synthetic equity disconnected from real lot counts. With 10 config gates now
   stacked (`exit_model`, `sizing_model`, `limit_halt_model`, `rollover_stat_tagging`,
   `resonance_filter`, `second_buy_mode`, `atr_chop_filter`, `regime_model`, `portfolio_risk`,
   `weighting`), there is no combination-legality matrix anywhere.
5. **Daily-loss-limit flatten pairs booked gross of costs** (`portfolio_engine.py:547`):
   `gross_pnl = sign * (flat_price - pos["open_price"]) / pos["open_price"]` is written directly
   as `pnl_pct` with no `2*commission+slippage` deduction, while every other `pairs` entry
   (sourced from `Position`) is net-of-cost — the same `coordinated_pairs` list silently mixes
   gross and net entries, one-sidedly flattering `portfolio_risk="on"` outcomes that hit the daily
   loss limit.
6. **Limit-band basis has three undocumented simplifications** (`limit_config.py:66-86`'s
   `_daily_prev_close_map`, `backtest_engine.py:313,323-326`):
   - (a) Night-session pollution: `_bar_date` buckets by calendar date, so RB/SC's 21:00-23:00
     night-session bars (which the exchange attributes to the *next* trading day) get bucketed
     into the current calendar day — "previous close" can self-referentially include bars from the
     day being evaluated. A39 already solved exactly this class of problem for daily aggregation
     (`daily_agg="trading_calendar"`); that logic was not reused here.
   - (b) Settlement-vs-close basis: `SYMBOL_LIMIT_CONFIG`'s cited sources all say "previous
     trading day's **settlement price** ± x%", but the implementation uses the last bar's close —
     a real, acknowledged-in-methodology-text but unquantified basis mismatch.
   - (c) Temporary widening windows (AP to 8% from 2026-05-06, RB to 5% from 2026-05-19 — both
     inside A50/A51's own measurement window, first surfaced during A50's review) are nowhere
     recorded in `SYMBOL_LIMIT_CONFIG` or any shipped report — steady-state percentages are
     applied blindly across dates where the real exchange limit was different.
   - Additionally, `_bar_at_limit` doesn't distinguish upper-touch from lower-touch, so a long
     open on a limit-DOWN bar (genuinely unexecutable) and a long open on a limit-UP bar (the
     asymmetric, actually-problematic case) get the identical tag.

Full contract: `docs/review/ai_trading_review_2026-07-13.md` §四 for complete evidence citations.

**Task-ID note:** continues sequentially from **A55**, the next unused ID as of 2026-07-13
(A38-A48 = P1-P8 roadmap, A49-A54 = first audit remediation wave).

---

## 2. Task Sequence

| ID | Title | Findings covered | Depends on |
|----|-------|-------------------|------------|
| A55 | Partial-TP transaction-cost double-scaling fix | 🟠#1 | none — start first (small, high-value correctness fix, mirrors A49) |
| A56 | `structural_atr` profit-protection gap — decide and document | 🟠#2 | none |
| A57 | Limit-config case normalization + fail-loud | 🟠#3 | none |
| A58 | Gate-combination guards + portfolio flatten cost fix | 🟠#4, 🟠#5 | none |
| A59 | Limit-band basis accuracy (trading-calendar reuse, temporary-widening registry, directional touch) | 🟠#6 | A50/A51 already done (no new dependency, but conceptually extends them) |
| A60 | Project-level VERSION/CHANGELOG gate + banner-exemption config cleanup | 🟢#8, 🟢#9 | none |

All six tasks are independent of each other — no hard dependency chain this round (unlike
A50→A51's diagnostic-then-enforcement pairing). Per the standing house rule, only one task is
promoted/active at a time; the order above is recommended priority (correctness bugs first,
then fail-open/guard gaps, then measurement-accuracy refinement, then process hygiene), not a
hard requirement.

**Backlog, not scheduled as formal tasks** (🟢 low-severity, non-blocking — pick up
opportunistically or bundle into whichever of A55-A60 touches the same file):
- 🟢#7 `TradeRecord.volume` always logs `1` on close in risk mode (`positions.py:995-1006`,
  `1058-1069` — `self.volume = 1` reset runs before the `TradeRecord` append that reads it).
  `pairs` is unaffected (correct), only the raw `trades` audit log is wrong. Natural fit inside
  A55 (same file/method family) if not scheduled separately.
- 🟢#10 `weighting="risk_parity"` is echoed in the `portfolio_risk="off"` report even though
  `_build_off_report` is unconditionally equal-weight (`portfolio_engine.py:361-369,422`) —
  cosmetic but misleading field. Natural fit inside A58.
- 🟢#11 `REASON_CODE_MAP` contains a GBK-mojibake-decoded key
  (`positions.py:279-284`) tolerating a historical encoding-corruption artifact instead of fixing
  the root cause — flag for investigation, not a fix task on its own.
- 🟢#12 `signals.get_all_signals` (still assembling the deprecated 二买/三买 implementations, no
  deprecation marker itself) is consumed by two live `skill_build/` scripts
  (`skill_build/build_mapping.py:47`, `skill_build/scripts/analyze_symbol.py:61`) — the A53
  deprecation marking didn't reach every consumer. Natural fit inside a future signals.py cleanup
  task if one is scheduled; otherwise a standalone tiny task.
- 🟢#13 `_research_short_open_allowed` requires a MACD/amplitude divergence signal for 三卖
  (third-sell) opens too (`positions.py:414-444`), even though 三卖 is chan-theory a trend-
  continuation point, not a divergence point like 一卖/二卖 — an asymmetric gate vs. the long-side
  三买 (which has no such divergence requirement) that may be suppressing legitimate 三卖 sample
  size. This is a signal-logic judgment call requiring domain review, not a mechanical fix —
  flagged for a human trading-logic decision before scheduling any code change.

---

## A55 — Partial-TP Transaction-Cost Double-Scaling Fix

### Rationale
`_scale_out` (`positions.py:865-872`) computes `transaction_cost = full_transaction_cost *
scale_fraction` where `full_transaction_cost = 2 * self.commission_rate + self.slippage` is
already a per-unit round-trip cost RATE (confirmed identical to `_close_long`'s
`transaction_cost = 2 * self.commission_rate + self.slippage`, `positions.py:970-971`, which
applies it undivided). Multiplying the rate by `scale_fraction` and THEN multiplying the
currency-PnL formula by `scale_volume` (`positions.py:869-871`) double-discounts the cost —
verified arithmetically: with `volume=1`, `partial_tp_frac=0.5`, rate `f`, a full lifecycle (0.5
lot partial-TP + 0.5 lot final close) pays `0.25f + 0.5f = 0.75f` total instead of the correct
`~1.0f` two one-way-not-cheaper trades should cost. This systematically understates
`structural_atr`'s reported costs relative to `"legacy"`, biasing every A/B comparison
(`diagnostics/exit_model_report_*.md`) in `structural_atr`'s favor.

### Semantics
No new config key — straight correctness fix. In `_scale_out`, use the undivided
`full_transaction_cost` as the rate (matching `_close_long`/`_close_short`'s convention exactly);
do not multiply the rate itself by `scale_fraction`. The currency formula's existing
`* scale_volume` term already correctly scales the cost to the portion actually closed.

### No-lookahead & correctness
Purely a same-bar arithmetic fix; no new data read, no timing change.

### Expected files
- `chan_strategy/positions.py` (`_scale_out`)
- `chan_strategy/tests/unit/test_exit_model.py` (new case: a full partial-TP-then-final-close
  lifecycle's TOTAL cost must be `>=` what an equivalent single-lot full close would have cost —
  a "partial exits are never cheaper than one exit" conservation assertion; also unit-test the
  exact corrected formula against a hand-computed fixture)
- Optionally bundle 🟢#7 (`TradeRecord.volume` always `1` on close) if convenient — same file,
  same review round, but call it out explicitly as a separate fix in the commit/HANDOFF if bundled

### Acceptance (decidable)
- [ ] `_scale_out`'s cost rate no longer multiplies `full_transaction_cost` by `scale_fraction`;
      a fixture with known `commission_rate`/`slippage`/`partial_tp_frac` reproduces a
      hand-computed exact `pnl_currency`/`pnl_pct` for the partial leg.
- [ ] A conservation test: total cost paid across a partial-TP-then-final-close lifecycle is `>=`
      the cost a single full close of the same total volume would have paid (never cheaper to
      exit in two pieces than one).
- [ ] `exit_model="legacy"` and `sizing_model="research"` paths are provably unaffected (existing
      golden-snapshot/equivalence tests still pass byte-identical — this bug only exists in the
      risk-mode partial-TP currency path).
- [ ] Existing `test_structural_atr_partial_tp_long`/`_short` tests updated if their expected
      values assumed the old (wrong) formula — call out explicitly in the PR/commit if any
      expected value changes, since a changing test value for a "fix" needs its own scrutiny.
- [ ] No threshold tuning; no pre-2026-04-24 data used for any parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not change `full_transaction_cost`'s definition (`2 * commission_rate + slippage`) itself —
only removes the erroneous second scaling. Does not touch `exit_model="legacy"`'s cost formula
(already correct) or `sizing_model="research"`'s path (bug only manifests under `sizing_model=
"risk"` + `exit_model="structural_atr"`, both already opt-in).

### Dev prompt
```text
Read A55. Fix _scale_out (positions.py:865-872): stop multiplying full_transaction_cost by
scale_fraction -- use the undivided rate, matching _close_long/_close_short's convention. Add a
conservation test proving a partial-TP-then-final-close lifecycle never costs less in total than
an equivalent single full close. Verify exit_model="legacy"/sizing_model="research" are untouched.
No tuning, no SimNow paths, no GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: the rate is still scaled by `scale_fraction` anywhere; the conservation test doesn't
actually assert total-cost-not-decreasing; `exit_model="legacy"`'s golden snapshot changes at all;
any existing test's expected value is silently changed without being called out explicitly.

---

## A56 — `structural_atr` Profit-Protection Gap: Decide and Document

### Rationale
Under `exit_model="structural_atr"`, `Position.update`'s `elif` chain (`positions.py:688-698`)
only reaches `self._check_atr_trailing_stop(...)` once `self._partial_tp_done is True`. A49 fixed
the specific bug where a lot-floor skip left this flag permanently unset; it did not change the
underlying structural fact that ATR trailing is *gated behind partial-TP firing at all*. A
position whose directional target (the partial-TP trigger condition) never fires has **zero
profit-side protection** for its entire life under `structural_atr` — only the fixed stop-loss and
timeout remain, meaning a large unrealized gain can fully round-trip back to the stop-loss level
with no intermediate defense. This is a materially different risk profile from `"legacy"`'s
percentage-giveback trailing (active from the moment `trailing_start` is crossed, independent of
any other event), and neither `config.py`'s `exit_model` comment nor the original A47 design
document states this difference.

### Semantics (two options — this task's own design step must pick one, informed by re-reading
A47's original intent, not pre-decided here)

**Option A (behavior change, needs a new sub-gate or redefined default):** make ATR trailing
independent of `_partial_tp_done` — track `_peak_price` from open (already done,
`positions.py:722-728`) and evaluate `_check_atr_trailing_stop` on every bar regardless of
partial-TP state, with partial-TP as an *additional*, non-blocking action rather than a
prerequisite. This changes `structural_atr`'s observed behavior (more positions would exit via ATR
trailing before ever reaching a partial-TP event) — requires a NEW equivalence test proving
`exit_model="legacy"` is still untouched, and likely a fresh comparison report showing the
before/after effect on `structural_atr`'s own numbers (not a claim of superiority, just honest
measurement of the behavior change).

**Option B (no behavior change, documentation-only):** leave the `elif` chain as-is, but add an
explicit, prominent comment in `config.py`'s `exit_model` key, the A47 design section, and
`diagnostics/exit_model_report.py`'s Methodology text, stating plainly: "under `structural_atr`,
ATR trailing-stop protection is not active until a partial take-profit event has fired; positions
that never reach a directional target rely solely on the fixed stop-loss and timeout." This
requires NO code/behavior change, only honest disclosure — lower risk, ships faster.

This task's design step (do this analysis BEFORE writing code) should pick one based on: (1)
whether A47's original design intent was "trailing only protects the *remainder* after partial
profit-taking" (in which case Option B, just document it) or "trailing should protect the whole
position from open" (in which case Option A is the actual bug-fix). Re-read
`docs/design/a38-phase-contracts-p2-p8.md`'s P8a section and any earlier design notes before
deciding — do not guess.

### No-lookahead & correctness
Option A: no new data read, purely a same-bar dispatch-order change. Option B: no code change.

### Expected files
- If Option A: `chan_strategy/positions.py` (`Position.update`'s `structural_atr` branch
  restructured so ATR trailing is evaluated independently of `_partial_tp_done`), plus new/updated
  tests and a fresh comparison-report run.
- If Option B: `chan_strategy/config.py` (comment), `docs/design/a38-phase-contracts-p2-p8.md`
  (P8a section addendum or a new dated note), `diagnostics/exit_model_report.py` (Methodology
  text addition).

### Acceptance (decidable — adjust to the chosen option during promotion/dev)
- [ ] A clear, recorded design decision (Option A or B) with rationale citing A47's original
      intent, documented in this task's own HANDOFF Decision Log.
- [ ] If Option A: `exit_model="legacy"` byte-identical (existing test unaffected); a new test
      proves ATR trailing now fires even when no partial-TP event has occurred; the
      `exit_model_report.py` comparison is re-run and the before/after behavior change for
      `structural_atr` is reported honestly (not framed as an improvement claim).
- [ ] If Option B: the documentation change is present in all three locations (config comment,
      design doc, report Methodology); no code/test changes; existing test suite untouched.
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow paths; no `GOAL PASSED`.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not touch `exit_model="legacy"`'s own trailing logic. Does not touch `sizing_model`,
`limit_halt_model`, `rollover_stat_tagging`, or any P8b/portfolio code. If Option A is chosen, does
not retune `atr_trail_mult`/`partial_tp_frac`'s values — only changes *when* the trailing check is
evaluated, not its parameters.

### Dev prompt
```text
Read A56. First, re-read A47's original design intent (docs/design/a38-phase-contracts-p2-p8.md
P8a section) to decide: should ATR trailing protect the whole position from open (Option A, real
behavior change), or only the remainder after partial-TP fires as originally intended (Option B,
documentation only)? Record the decision and rationale in HANDOFF's Decision Log BEFORE writing
any code. Then implement the chosen option per its acceptance criteria. No tuning, no SimNow
paths, no GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: no clear decision rationale is recorded; Option A is implemented without a fresh
before/after comparison report; Option A changes `exit_model="legacy"` at all; Option B leaves any
of the three documentation locations unedited.

---

## A57 — Limit-Config Case Normalization + Fail-Loud

### Rationale
`backtest_engine.py:314`'s `SYMBOL_LIMIT_CONFIG.get(self.symbol, {}).get("limit_pct")` does not
normalize `self.symbol`'s case before lookup, while `SYMBOL_LIMIT_CONFIG`'s keys
(`limit_config.py:19-55`) are all uppercase and the data layer explicitly accepts lowercase symbol
codes (`data_adapter.py:317`, `COLLATE NOCASE`) and position/weight code already normalizes via
`_research_symbol_key()` (`positions.py:302-304`). A lowercase `self.symbol` under
`limit_halt_model="aware"` silently produces `limit_pct=None`, and every `pairs` entry still gets
tagged `is_entry_at_limit=False`/`is_exit_at_limit=False` — a false-negative that looks identical
to "genuinely checked, not at limit" with no warning.

### Semantics
No new config key. In `backtest_engine.py`'s limit-lookup call site, normalize `self.symbol`
through the same `_research_symbol_key()` helper already used elsewhere before the
`SYMBOL_LIMIT_CONFIG.get(...)` lookup. When `limit_halt_model="aware"` AND the normalized symbol
still isn't found in `SYMBOL_LIMIT_CONFIG` (a genuinely-unconfigured symbol, not a case mismatch),
fail loud: either raise, or write `is_entry_at_limit=None`/`is_exit_at_limit=None` (never silently
`False`) so downstream readers can distinguish "not checked" from "checked, clear."

### No-lookahead & correctness
Pure lookup-key normalization; no data-flow or timing change.

### Expected files
- `chan_strategy/backtest_engine.py` (the `limit_pct` lookup call site)
- `chan_strategy/tests/unit/test_limit_halt_aware.py` (new case: lowercase `symbol=` input under
  `limit_halt_model="aware"` produces the SAME tagging result as the uppercase equivalent; a case
  for a genuinely-unconfigured symbol produces `None` tags, not `False`)

### Acceptance (decidable)
- [ ] A fixture with `BacktestEngine(symbol="sc888", ...)` and `limit_halt_model="aware"` produces
      identical `is_entry_at_limit`/`is_exit_at_limit` values to the equivalent `symbol="SC888"`
      run (unit-tested).
- [ ] A fixture with a symbol genuinely absent from `SYMBOL_LIMIT_CONFIG` under `"aware"` produces
      `None` (not `False`) for both tag fields, or raises — dev's choice, but must not silently
      write `False` (unit-tested).
- [ ] `limit_halt_model="off"` behavior is completely unaffected (existing golden-snapshot
      equivalence test still passes byte-identical).
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow paths; no `GOAL PASSED`.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not add new symbols to `SYMBOL_LIMIT_CONFIG` or change any existing cited percentage — purely
a lookup-key-normalization and fail-loud fix.

### Dev prompt
```text
Read A57. Normalize the symbol via _research_symbol_key() before SYMBOL_LIMIT_CONFIG lookup in
backtest_engine.py. When limit_halt_model="aware" and the symbol is genuinely unconfigured (not a
case mismatch), tag fields must be None, never a silent False. Add tests for lowercase-symbol
equivalence and unconfigured-symbol fail-loud behavior. No tuning, no SimNow paths, no GOAL
PASSED. Handoff next.
```

### Review checklist
Reject if: the lowercase-vs-uppercase fixture doesn't produce identical results; an unconfigured
symbol still silently produces `False` tags instead of `None`/a raise; `"off"` mode's equivalence
snapshot changes at all.

---

## A58 — Gate-Combination Guards + Portfolio Flatten Cost Fix

### Rationale
Two related portfolio-accounting integrity gaps in A48's `portfolio_engine.py`:

1. **No guard on `sizing_model="risk"` + `portfolio_risk="on"`**: the portfolio replay ledger
   (`portfolio_engine.py:516-527`) unconditionally uses proportional-weight accounting
   (`pnl_pct * abs(weight) * initial_capital`) and never reads risk-mode's `pnl_currency`/lot/
   margin fields — `portfolio_engine.py` contains zero references to `sizing_model`. When both
   gates are on simultaneously, per-symbol reports are currency-denominated while the portfolio
   report is weight-denominated, and `daily_loss_limit_pct`'s trigger uses synthetic equity
   disconnected from real position sizes.
2. **Daily-loss-limit flatten pairs booked gross of costs** (`portfolio_engine.py:547`):
   `gross_pnl = sign * (flat_price - pos["open_price"]) / pos["open_price"]` is written directly
   as `pnl_pct` with no cost deduction, while every other `coordinated_pairs` entry (sourced from
   `Position`) is net-of-cost.

### Semantics
No new config key for #1 — add an explicit compatibility check at `PortfolioEngine.run()`'s entry
point: if `STRATEGY_CONFIG.get("sizing_model") == "risk"` and `portfolio_risk == "on"`, either (a)
raise a clear `NotImplementedError`/`ValueError` stating the combination isn't supported yet, or
(b) if dev's design step determines the currency-based accounting can be correctly threaded
through the replay (a larger change — read `portfolio_engine.py`'s `_build_on_report` fully before
committing to this), implement it properly. Given roadmap discipline (small, reviewable
increments), **default expectation is (a) — raise/warn, not silently produce numbers**; escalate
to (b) only if the fix turns out to be small once actually attempted. For #2, add
`2*commission_rate + slippage` deduction to the flatten `gross_pnl` computation, matching every
other `pairs` entry's net-of-cost convention.

### No-lookahead & correctness
Neither change reads new data or affects timing — pure accounting-consistency and guard logic.

### Expected files
- `chan_strategy/portfolio_engine.py` (`PortfolioEngine.run()` entry guard; `_flatten_all`/
  flatten-pair cost deduction)
- `chan_strategy/tests/unit/test_portfolio_risk.py` (new cases: the incompatible-combination
  guard fires with a clear message; the flatten pair's `pnl_pct` includes cost deduction matching
  a hand-computed fixture)
- Bundle 🟢#10 (`weighting="risk_parity"` echoed but ignored under `portfolio_risk="off"`) if
  convenient — same file: either stop echoing the config value when it has no effect, or echo
  `"fixed"` explicitly regardless of the config value under `"off"` mode, whichever is clearer.

### Acceptance (decidable)
- [ ] `sizing_model="risk"` + `portfolio_risk="on"` produces a clear, immediate error (or, if
      option (b) was chosen, produces correctly-threaded currency accounting — unit-tested either
      way) instead of silently running with mismatched accounting conventions.
- [ ] A fixture with known `flat_price`/`open_price`/`commission_rate`/`slippage` proves the
      daily-loss-limit flatten pair's `pnl_pct` is net-of-cost, matching a hand-computed value.
- [ ] `portfolio_risk="off"`'s existing equivalence test still passes byte-identical.
- [ ] (If bundled) `weighting` field in `_build_off_report`'s output no longer misleadingly
      implies `risk_parity` is active when it isn't.
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow paths; no `GOAL PASSED`.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not add a combination-legality matrix for ALL 10 stacked gates in this task — scoped strictly
to the one confirmed-broken combination (`sizing_model="risk"` + `portfolio_risk="on"`) and the
one confirmed cost-accounting bug (flatten pairs). A broader gate-compatibility audit is a
separate, larger future task if warranted.

### Dev prompt
```text
Read A58. Add an entry guard in PortfolioEngine.run() for sizing_model="risk" + portfolio_risk="on"
(default: raise/warn clearly, do not silently run with mismatched accounting -- escalate to a real
fix only if trivially small once you look). Add cost deduction to the daily-loss-limit flatten
pair's pnl_pct, matching Position's net-of-cost convention. No tuning, no SimNow paths, no GOAL
PASSED. Handoff next.
```

### Review checklist
Reject if: the incompatible combination still silently produces numbers with no warning/error; the
flatten-pair cost fix doesn't match a hand-computed fixture; `portfolio_risk="off"`'s equivalence
snapshot changes at all.

---

## A59 — Limit-Band Basis Accuracy

### Rationale
Three related, currently-undocumented simplifications in the A50/A51 limit-band computation:

1. **Night-session pollution**: `_daily_prev_close_map`'s `_bar_date` (`limit_config.py:66-86`)
   buckets bars by calendar date; RB/SC's 21:00-23:00 night-session bars belong to the *next*
   trading day per exchange convention, but get bucketed into the current calendar day, so
   "previous close" can self-referentially include same-evaluation-day night-session data. A39
   already solved this exact class of problem for daily aggregation
   (`daily_agg="trading_calendar"`, `night_session_start_hour` config) — that logic was not reused
   here.
2. **Settlement-vs-close basis**: `SYMBOL_LIMIT_CONFIG`'s cited sources say "previous trading
   day's **settlement price** ± x%"; the implementation uses the last bar's close. Acknowledged in
   the report Methodology text but never quantified.
3. **Temporary widening windows undocumented**: AP888 widened to 8% from 2026-05-06, RB888 to 5%
   from 2026-05-19 (both within A50/A51's own measurement window) — nowhere recorded in
   `SYMBOL_LIMIT_CONFIG` or any shipped report.
4. **No directional distinction**: `_bar_at_limit` returns a single boolean without distinguishing
   upper-touch (limit-up) from lower-touch (limit-down), so a long open on a limit-down bar
   (genuinely unexecutable in that direction) and a long open on a limit-up bar get identical tags.

### Semantics
- Reuse A39's trading-calendar logic (`daily_agg="trading_calendar"`/`night_session_start_hour`)
  for `_daily_prev_close_map`'s date bucketing — do not reimplement a second night-session
  boundary rule.
- Add a documented, dated registry of known temporary-widening windows to `SYMBOL_LIMIT_CONFIG`
  (e.g. a list of `{start_date, end_date, limit_pct}` overrides per symbol, falling back to the
  steady-state percentage outside any registered window) for at least AP888 and RB888's
  already-identified windows; cite the same exchange-notice sources found during A50's review.
  This is not a hardcoded blind guess — every entry must carry a citation, same discipline as the
  steady-state percentages.
- Change `_bar_at_limit` to return a directional result (e.g. `(touched_upper, touched_lower)`
  instead of a single `at_limit` bool), and have the entry/exit tagging consume the direction that
  actually matters for that side of the trade (a long entry cares about touched_upper being
  unexecutable-favorable-direction vs touched_lower being the adverse/plausible direction — decide
  and document the exact semantic during this task's own design step, informed by what "at limit"
  is actually meant to signal for risk purposes).
- Settlement-vs-close: at minimum, quantify the typical settlement-vs-close gap for the 5 default
  symbols (a short read-only measurement) and record the finding — full settlement-price sourcing
  may be a larger follow-up if the gap turns out to be material.

### No-lookahead & correctness
The trading-calendar reuse and directional-touch changes use the same already-known-safe
bars/dates — no new lookahead risk. The widening-window registry uses only historical, already-
past dates (not live/future dates).

### Expected files
- `chan_strategy/limit_config.py` (`_daily_prev_close_map` reuses A39's calendar logic;
  `_bar_at_limit` returns directional touch; widening-window registry added to
  `SYMBOL_LIMIT_CONFIG`)
- `chan_strategy/backtest_engine.py` (consume the directional result correctly per entry/exit
  side)
- `chan_strategy/tests/unit/test_limit_halt_aware.py` (new cases: night-session bar doesn't
  pollute prev-close; a widening-window date uses the overridden percentage; directional touch is
  correctly distinguished)
- `diagnostics/limit_halt_exposure_report.py` (re-run on the full post-2026-04-24 window with the
  corrected basis; report the settlement-vs-close gap measurement)

### Acceptance (decidable)
- [ ] A fixture with a night-session bar proves `_daily_prev_close_map` no longer includes
      same-evaluation-day night-session data in "previous close" (unit-tested, mirroring A39's own
      `test_daily_no_lookahead`-style fixture).
- [ ] AP888 and RB888's known temporary-widening windows are registered with cited sources; a
      fixture proves a date inside the window uses the overridden percentage, a date outside uses
      the steady-state percentage.
- [ ] `_bar_at_limit`'s directional result is unit-tested for both upper-touch and lower-touch
      cases, and the entry/exit consumption logic correctly maps direction to trade side.
- [ ] `limit_halt_exposure_report.py` re-run with the corrected basis on the full post-2026-04-24
      window; the settlement-vs-close gap for the 5 default symbols is measured and reported
      (even if the conclusion is "gap is small/immaterial" — that must be a measured conclusion,
      not an assumption).
- [ ] `limit_halt_model="off"` equivalence test still passes byte-identical.
- [ ] No threshold tuning; no pre-2026-04-24 data used for any NEW parameter choice (the widening
      windows are historical facts being registered, not tuned parameters); no SimNow paths; no
      `GOAL PASSED`.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not implement live/future widening-window detection (a static, cited, dated registry for
already-known historical windows only). Does not pursue full settlement-price data sourcing unless
the measured settlement-vs-close gap in this task turns out to be material enough to warrant it
(a follow-up decision, not pre-committed here). Does not change `limit_halt_model`'s tagging-only
scope into enforcement (still A51's/a future task's boundary).

### Dev prompt
```text
Read A59. Reuse A39's trading-calendar logic for _daily_prev_close_map's date bucketing (don't
reimplement). Add a cited, dated temporary-widening-window registry to SYMBOL_LIMIT_CONFIG for
AP888/RB888's already-identified windows. Make _bar_at_limit return directional touch
(upper/lower) instead of one bool, and correctly consume direction per trade side. Measure and
report the settlement-vs-close basis gap for the 5 default symbols. Re-run
limit_halt_exposure_report.py on the corrected basis. No tuning, no SimNow paths, no GOAL PASSED.
Handoff next.
```

### Review checklist
Reject if: A39's calendar logic is reimplemented instead of reused; any widening-window entry
lacks a cited source; directional touch isn't actually consumed differently per trade side (same
result as before, just renamed); the settlement-vs-close gap claim isn't backed by an actual
measurement; `"off"` mode's equivalence snapshot changes at all.

---

## A60 — Project-Level VERSION/CHANGELOG Gate + Banner-Exemption Config Cleanup

### Rationale
Two related process-hygiene findings:

1. **VERSION/CHANGELOG drift already relapsed**: A51 bumped `examples/czsc_strategy/VERSION` to
   0.2.0 with a CHANGELOG entry, closing the original #11 finding — but A52 (new
   `rollover_stat_tagging` key), A53 (5 new config keys), and A54 (new `sync_check` gate) are all
   externally-visible changes that shipped with zero VERSION bump or CHANGELOG entry (confirmed
   via `git show --stat` on their commits). Root cause: the root `.synccheck.yml` only guards
   `vnpy/__init__.py`'s version string; the project-level `examples/czsc_strategy/VERSION` has no
   gate requiring it to move when the project's own config surface changes.
2. **Banner-exemption list is half-declared, half-hardcoded**: `.synccheck.yml`'s
   `diagnostics_banner_check.skip` list covers most exemptions, but
   `tools/sync_guardian/sync_check.py:626`'s `audit_issue_diagnostics_*` prefix exemption is
   hardcoded in the checker itself, not declared in config; `diagnostics/archive/` isn't included
   in the banner-check glob at all (non-recursive `*.md`), leaving at least one archived file
   unchecked.

### Semantics
For #1: add a new `sync_check.py` check (or extend the existing version-consistency check) that
requires `examples/czsc_strategy/VERSION`/`CHANGELOG.md` to be touched whenever a commit modifies
`chan_strategy/config.py` (a reasonable proxy for "externally-visible config surface changed") —
mirroring the spirit of A42's deliverables-freshness check. Exact trigger heuristic (e.g. "if
`config.py` diff touches a top-level `STRATEGY_CONFIG`/`BACKTEST_CONFIG` key and `VERSION`/
`CHANGELOG.md` aren't in the same commit's diff, warn or fail") is this task's own design detail
to finalize — read A42's `_check_deliverables_are_tracked_and_fresh` for the established pattern
before designing a new heuristic from scratch.

For #2: move the `audit_issue_diagnostics_*` prefix exemption into `.synccheck.yml`'s `skip`
list (as a glob pattern, not just exact filenames — confirm the check supports patterns, extend it
minimally if not) so all exemptions are declared in one place; extend the banner-check glob to
recurse into `diagnostics/archive/` (or explicitly declare `archive/` itself as an exempt
directory in config, if that's the intended semantics — decide and document either way).

### No-lookahead & correctness
Not applicable — pure tooling/process, no trading logic or data flow.

### Expected files
- `tools/sync_guardian/sync_check.py` (new/extended version-freshness check; banner-check glob
  extended to cover `archive/`; `audit_issue_diagnostics_*` exemption moved to config-driven)
- `.synccheck.yml` (root) and `examples/czsc_strategy/.synccheck.yml` (new check config;
  `audit_issue_diagnostics_*` pattern added to `skip`)
- `examples/czsc_strategy/VERSION`/`CHANGELOG.md` (bump/backfill entries for A52-A54's
  already-shipped changes, closing the immediate gap this task discovers)
- `tests/test_sync_guardian.py` (new tests: a config.py change without a VERSION/CHANGELOG touch
  fails the new check with teeth, mirroring A42's/A54's established fixture-test pattern; the
  `audit_issue_diagnostics_*` pattern is honored from config, not a hardcoded checker string)

### Acceptance (decidable)
- [ ] A new `sync_check.py` check fails (non-zero exit, clear message) for a fixture commit that
      changes `chan_strategy/config.py`'s top-level keys without touching `VERSION`/
      `CHANGELOG.md`; passes when both are touched together (unit-tested with real teeth,
      mirroring A42's/A54's fixture-test pattern).
- [ ] `examples/czsc_strategy/VERSION`/`CHANGELOG.md` backfilled with entries for A52 (rollover
      tagging), A53 (5 config keys + equity_mode resolution), A54 (sizing_caveat + banner gate) —
      the immediate gap this task discovers, closed as part of shipping the new gate.
- [ ] `audit_issue_diagnostics_*` exemption is declared in `.synccheck.yml`'s `skip` config (as a
      pattern, not a hardcoded string in the checker), verified by a test that changes the config
      pattern and confirms the checker honors the new value.
- [ ] `diagnostics/archive/` is either included in the banner-check scan (recursive glob) or
      explicitly, deliberately declared exempt in config with a documented reason — not silently
      unscanned.
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow paths; no `GOAL PASSED`; does not
      fork a second copy of `sync_check.py`'s logic.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not retroactively enforce version bumps for A38-A51 (already shipped, already reviewed under
the discipline that existed at the time) — this task's gate applies going forward from its own
landing point, same "not retroactive" boundary A42 set for its own deliverables-freshness check.
Does not change the root `.synccheck.yml`'s `vnpy/__init__.py`-based version-truth mechanism — adds
a parallel, project-scoped check for `examples/czsc_strategy/VERSION` specifically.

### Dev prompt
```text
Read A60. Add a sync_check gate requiring examples/czsc_strategy/VERSION and CHANGELOG.md to be
touched whenever chan_strategy/config.py's top-level keys change, following A42's deliverables-
freshness check pattern -- with real teeth (fixture test). Backfill VERSION/CHANGELOG for A52-A54's
already-shipped changes. Move the audit_issue_diagnostics_* banner exemption from hardcoded checker
logic into .synccheck.yml's skip config. Resolve whether diagnostics/archive/ is scanned or
explicitly exempt. No tuning, no SimNow paths, no GOAL PASSED, no forked sync_check.py copy.
Handoff next.
```

### Review checklist
Reject if: the new version-freshness check doesn't actually fail on a fixture missing the
VERSION/CHANGELOG touch (no teeth); A52-A54's backfill is incomplete or inaccurate; the
`audit_issue_diagnostics_*` exemption remains hardcoded in the checker; `diagnostics/archive/`'s
scan status is left ambiguous/undocumented; a duplicate `sync_check.py` is created.

---

## 3. Cross-Task Notes

- **No hard dependencies this round** — A55-A60 may be resequenced if priorities change, unlike
  A50→A51's diagnostic-then-enforcement pairing in the previous wave.
- **A56 requires a design decision before code** (Option A vs B) — do not let dev guess; if the
  promoted HANDOFF task doesn't clearly resolve this during promotion, the design step must be
  completed as the first action of the dev round, with the decision recorded in the Decision Log
  before any code is written.
- **A59 depends conceptually on A57** (both touch `limit_config.py`/the limit-tagging path) — not
  a hard sequencing requirement, but consider promoting A57 before A59 to avoid rebase friction if
  both are active in close succession (though the standing rule is still one-task-at-a-time).
- **Promotion discipline unchanged**: no task in this roadmap may claim `GOAL PASSED` or
  profitability from pre-2026-04-24 data. Each task is its own handoff task (design → dev → review
  → done); do not batch multiple A55-A60 items into one dev handoff.
- **Lessons from A49-A54 carried forward explicitly in each task's Notes section**: proactive
  Manual-verification blocks + `ruff check` runs correlate strongly with one-round review
  acceptance (A52, A53's second round); omitting either wasted a round (A49, A50, A51, A53's first
  round, A54's manual-verification omission). Every A55-A60 HANDOFF should carry this reminder.
