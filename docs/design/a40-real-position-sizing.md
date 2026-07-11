# A40 Design: Real Position Sizing (P3 — ATR-Risk Units + Contract Multiplier + Margin)

**Task:** Roadmap phase **P3** (from `docs/design/a38-phase-contracts-p2-p8.md` §P3), promoted to
a standalone task after A39 (P2) reached `done`. Replaces the pre-authored placeholder
`contract_specs` with real, cited exchange contract specs and grounds the design against the
current `Position`/`BacktestEngine` code (which has moved on since A38: `stop_execution_model`,
`daily_agg` were added by A38/A39).

**Scope:** Backtest-only. Makes `Position.pos`/PnL tradeable (real integer lots, currency PnL)
behind a gated switch that defaults to byte-identical current (post-hoc-weighted, direction-only)
behavior. No live order routing, no SimNow changes.

**Authorization:** Same standing authorization as A38/A39 — user-authorized strategy-adjacent
changes in the root `vnpy` workflow, under the A34 guardrails (gated default-off, diagnostic-first
where applicable, no OOS tuning, research-only, no SimNow order changes).

---

## 1. Background

`Position` is currently direction-only: `pos ∈ {-1, 0, 1}`, no `volume` field at all — PnL is
recorded as a percentage (`pnl_pct`) per pair, and turned into money only in
`BacktestEngine.run`'s post-hoc weighting loop (`backtest_engine.py:329-364`), which multiplies
each pair's `pnl_pct` by a **fixed, hand-picked weight** (`pos_1buy=0.10`, `pos_2buy=0.20`,
`pos_3buy=0.30`, ...) times `initial_capital`, regardless of the symbol's actual volatility, the
trade's actual stop distance, or the contract's actual value.

This means every reported return/drawdown/Sharpe number in every prior diagnostic (A31-A39) is a
**signal-quality index**, not tradeable PnL:

- SC (crude oil, ~1000 CNY/point-equivalent contract value swings) and AP (apples, much smaller
  contract value) get the same weight-based sizing regardless of how many CNY of risk that
  actually represents.
- The fixed weights (三买 gets 30%, the largest) don't reflect that 三买 has repeatedly shown the
  *worst* profit factor in the A38-era `backtest_matrix` report — the current sizing scheme sizes
  up the worst-performing sub-strategy.
- No margin, no integer-lot rounding, no capital exhaustion check — a portfolio-level analysis
  (P8) cannot be built on this foundation, and no Tier B/C profitability claim (P4-P8) can be
  trusted until PnL is real money.

A40 fixes this at the `Position`/`BacktestEngine` level only — it does not change any signal or
risk-exit logic (P1's touch-based stop and P8's future exit overhaul are untouched).

---

## 2. Config

Add to `STRATEGY_CONFIG` (`chan_strategy/config.py`):

```python
"sizing_model": "research",        # "research" (legacy, default) | "risk"
"risk_per_trade_pct": 0.005,       # fraction of equity risked per trade (0.5%), risk mode only
"max_margin_pct": 0.50,            # cap on total open initial margin vs equity, risk mode only
"equity_mode": "fixed",            # "fixed" (uses initial_capital as equity_at_entry basis) |
                                    # "compound" (documented, NOT implemented this task — see 6)
"contract_specs": {
    # Multiplier (合约乘数, contract units per lot), tick (最小变动价位), margin_rate (交易所
    # 最低交易保证金率 — the EXCHANGE minimum; a live/production margin_rate would typically be
    # higher after a broker markup, which this research-mode sizing does not model — see 6).
    # Sourced 2026-07-11 from the exchanges' own published contract rules:
    "AP888": {"multiplier": 10,   "tick": 1.0, "margin_rate": 0.07},
    # source: CZCE 苹果期货合约规则 (czce.com.cn/cn/rootfiles/2021/09/09/1605597612939463-...)
    "RB888": {"multiplier": 10,   "tick": 1.0, "margin_rate": 0.05},
    # source: SHFE 螺纹钢期货合约(修订版) (shfe.com.cn/products/futures/metal/...rb_f/...)
    "SC888": {"multiplier": 1000, "tick": 0.1, "margin_rate": 0.05},
    # source: INE/SHFE 原油期货标准合约(SC) (ine.com.cn/products/futures/.../standard_sc_f/...)
    "A888":  {"multiplier": 10,   "tick": 1.0, "margin_rate": 0.05},
    # source: DCE 黄大豆1号(A)期货合约及交割要素 (dce.com.cn ... 附件3:各品种合约)
    "ZN888": {"multiplier": 5,    "tick": 5.0, "margin_rate": 0.05},
    # source: SHFE 锌期货合约(修订版) (shfe.com.cn/products/futures/metal/...zn_f/...)
},
```

`"research"` is the default and MUST reproduce the current equity curve and `pos.pairs` exactly
(no `volume`/currency-PnL fields consulted). `contract_specs` keys use the raw table-name-style
symbol (`AP888`, not `ap`) to match `BacktestEngine.table_name`/`self.symbol` conventions already
used elsewhere in the codebase (e.g. `_apply_symbol_position_overrides`).

---

## 3. Semantics (`sizing_model="risk"`)

### 3.1 On open (`Position._open_long` / `_open_short`)

1. **Stop distance.** `stop_distance = price * stop_loss / 10000` (i.e. the same nominal
   `stop_loss` BP the `Position` is already constructed with — P1's fixed/structural stop
   distance in price terms at the entry price; trailing/timeout are not sizing inputs). This
   keeps sizing consistent with the P1 touch-based stop that actually bounds the loss.
2. **Risk budget.** `risk_amount = equity_at_entry * STRATEGY_CONFIG["risk_per_trade_pct"]`.
   `equity_at_entry` is supplied by `BacktestEngine` (see 3.3) — the running equity known at the
   entry bar (realized-to-date + open unrealized at that bar), never a future value.
3. **Raw size.** `raw_volume = risk_amount / (stop_distance * multiplier)`, where `multiplier`
   comes from `STRATEGY_CONFIG["contract_specs"][symbol]["multiplier"]`.
4. **Integer lots.** `volume = floor(raw_volume)`. If `volume < 1`: **skip the open** (no trade
   is opened this bar; do not floor up to a forced 1-lot minimum) and record the skip reason
   `"size_zero_skip"` (a new `Position` counter/log field — not a `pairs` entry, since no trade
   happened).
5. **Margin cap.** `required_margin = volume * price * multiplier * margin_rate`. If
   `total_open_margin_across_all_positions + required_margin` would exceed
   `equity_at_entry * STRATEGY_CONFIG["max_margin_pct"]`, reduce `volume` to the largest integer
   lot count that fits under the cap; if that's `< 1`, skip the open (`"margin_cap_skip"`).
   `total_open_margin_across_all_positions` is tracked by `ChanTimingStrategy`/`BacktestEngine`
   (sum of `volume * cost * multiplier * margin_rate` across all currently-open sub-strategy
   positions for that symbol — cross-symbol margin sharing is out of scope, see 6).

`Position` gains a `volume` field (default `1` under `"research"`, computed as above under
`"risk"`) and a `contract_multiplier` field (`1` under `"research"`, from `contract_specs` under
`"risk"`).

### 3.2 On close (`Position._close_long` / `_close_short`)

Currency PnL is computed **alongside** the existing `pnl_pct` (not replacing it — `pnl_pct`
remains the percentage-return field every existing diagnostic/report already keys off of):

```
gross_pnl_currency = (exit_price - entry_price) * volume * multiplier * direction_sign
                      - (commission_rate * 2 + slippage) * entry_price * volume * multiplier
```

(`direction_sign = +1` long, `-1` short — mirrors the existing `pnl_pct` sign convention.) Add
`pnl_currency` to each `pairs` entry. Under `"research"`, `volume=1, multiplier=1`, so
`pnl_currency` numerically equals `pnl_pct * entry_price` — present but not used by anything
(byte-identical `pnl_pct`/report behavior is what equivalence actually checks).

### 3.3 Equity accounting (`BacktestEngine.run`)

Under `"risk"`, replace the post-hoc fixed-weight loop (`backtest_engine.py:329-364`) with real
accounting:

- `equity_at_entry` for a given bar = `initial_capital + sum(closed pair pnl_currency to date)
  + sum(open positions' unrealized currency pnl at this bar's price)`. This is exactly the
  existing realized+unrealized pattern already in the loop, just in currency instead of
  weight-scaled percentage.
- `total_open_margin` = `sum(volume * cost * multiplier * margin_rate)` over currently-open
  positions (for the margin-cap check in 3.1, and to report in the equity curve).
- Report header and equity-curve rows gain `sizing_model` and (`risk` mode only)
  `total_open_margin`, `margin_utilization_pct` (`total_open_margin / equity`).

Under `"research"`, this whole block is **untouched** — the existing fixed-weight loop stays
exactly as-is, byte for byte.

---

## 4. No-lookahead & correctness

- `equity_at_entry` is computed from information available **strictly before or at** the entry
  bar's execution price (same bar whose `execution_price` — the delayed next-bar-open fill —
  already drives `_open_long`/`_open_short`); it never reads a later bar's price or PnL.
- Integer-lot and margin-cap checks use only the entry bar's `price`/`stop_distance`/margin state
  at that instant — no forward-looking optimization of lot size.
- `BacktestEngine.run`'s step ordering (delayed-fill signal execution → CZSC update → signal
  generation → equity snapshot) is unchanged; sizing is computed inside the existing
  `_open_long`/`_open_short` call, not by reordering the loop.

---

## 5. Expected file changes

- `examples/czsc_strategy/chan_strategy/config.py` — new keys, `contract_specs` with inline
  source citations as shown in §2.
- `examples/czsc_strategy/chan_strategy/positions.py` — `Position` gains `volume`,
  `contract_multiplier`, `pnl_currency` on pairs, `size_zero_skip`/`margin_cap_skip` counters;
  sizing logic in `_open_long`/`_open_short` gated on `STRATEGY_CONFIG["sizing_model"]`.
- `examples/czsc_strategy/chan_strategy/backtest_engine.py` — `equity_at_entry`/margin-cap
  plumbing into `Position.update`/open calls (new optional params, `None` default preserving
  `"research"`); real-money equity curve computation under `"risk"`; report header additions.
- `examples/czsc_strategy/tests/unit/test_position_sizing.py` — new, per §7.
- `docs/design/a38-phase-contracts-p2-p8.md` — mark P3's placeholder `contract_specs` superseded
  by this document (one-line pointer edit, not a rewrite).

---

## 6. Boundaries (what A40 does NOT do)

- **No production margin markup.** `contract_specs.margin_rate` is the exchange **minimum**;
  live/production trading uses a broker-marked-up rate (commonly higher). This task does not add
  a markup config — a future task should if this sizing model is ever used for anything beyond
  backtest research, and the citation comment in §2 makes the exchange-minimum caveat explicit so
  nobody mistakes it for a production-ready margin figure.
- **No cross-symbol margin sharing / capital allocation.** Each symbol's `BacktestEngine` run is
  independent (matches the existing per-symbol architecture); a shared-capital portfolio view is
  P8's job.
- **`equity_mode="compound"` is not implemented** — the config value is accepted and documented
  as a future option, but only `"fixed"` (equity_at_entry basis = running realized+unrealized off
  `initial_capital`, not reinvested compounding assumptions beyond that) ships this task.
- **Does not change exits** (fixed/trailing stop, timeout) — P1's stop distance is read as a
  sizing *input*, not modified. P8 owns any future exit-model change.
- **No live order routing, no SimNow changes**, no signal/entry-condition changes.
- **No parameter tuning** — `risk_per_trade_pct=0.005` and `max_margin_pct=0.50` are conservative
  starting defaults, not selected via any backtest; a future task may tune them against the
  post-2026-04-24 + SimNow validation stream only.

---

## 7. Acceptance Criteria (decidable)

- [ ] `STRATEGY_CONFIG["sizing_model"]` (`"research"` default | `"risk"`),
      `risk_per_trade_pct` (0.005), `max_margin_pct` (0.50), `equity_mode` (`"fixed"`), and
      `contract_specs` (AP888/RB888/SC888/A888/ZN888, each with `multiplier`/`tick`/
      `margin_rate` and an inline source citation comment) exist in `config.py`.
- [ ] **Research equivalence:** with `sizing_model="research"`, the equity curve
      (`BacktestEngine.equity_curve`) and every `Position.pairs` entry's `pnl_pct`/`open_price`/
      `close_price`/`bars_held`/`reason` are byte-identical to the pre-A40 baseline on >=2 symbols
      x 1 year (equivalence test: before/after diff empty). `volume`/`pnl_currency` may be present
      but must equal `1`/`pnl_pct * entry_price` respectively and must not be read by any existing
      report/diagnostic code path.
- [ ] **Risk sizing (unit):** given a fixture (`equity_at_entry`, `risk_per_trade_pct`,
      `multiplier`, `stop_distance`), `volume == floor(risk_amount / (stop_distance * multiplier))`
      exactly, for both a long and a short fixture.
- [ ] **Zero-size skip:** a fixture where `raw_volume < 1` skips the open entirely (`Position.pos`
      stays `0`, no `pairs`/`trades` entry added) and increments a `size_zero_skip` counter — no
      forced 1-lot floor.
- [ ] **Margin cap:** a fixture where the raw sized `volume`'s `required_margin` would push
      `total_open_margin` over `equity_at_entry * max_margin_pct` gets reduced to the largest
      lot count that fits (>=1); a fixture where even 1 lot doesn't fit skips the open
      (`margin_cap_skip` counter increments).
- [ ] **Currency PnL:** for a closed trade (long and short fixtures), `pnl_currency` equals
      `(exit-entry)*volume*multiplier*sign - (2*commission_rate+slippage)*entry*volume*multiplier`
      within floating-point tolerance.
- [ ] **No-lookahead:** a test asserts `equity_at_entry`/margin-cap decisions read only bars up to
      and including the entry bar; `BacktestEngine.run`'s step ordering is unchanged beyond the
      new optional sizing parameters threaded into the existing open call.
- [ ] Backtest report header (and equity-curve rows under `"risk"`) print the active
      `sizing_model`, and (risk mode only) `total_open_margin`/`margin_utilization_pct`.
- [ ] No threshold tuned via backtest selection; no pre-2026-04-24 data used for any parameter
      choice; no SimNow order/cancel/send paths changed; no new `send_order`/`cancel_order`/
      `buy`/`sell`/`short`/`cover` calls; every generated report keeps the RESEARCH-ONLY
      disclaimer where applicable.

### 7a. Addendum (2026-07-11, post independent read-only audit)

Closes the gap between "sizing math is unit-tested" and "A40 done means the full observable
chain — sizing, the P1 stop that bounds the loss, and any SimNow risk observation — is jointly
reconciled in one regenerable report, and that report cannot be fooled by a known-zero
placeholder." See the audit's Finding #2 (`simnow_daily_capture.py`'s `build_risk()` emits an
all-zero risk block that `simnow_daily_monitor.py:380` can silently prioritize over a real
replay-computed risk figure) — A41 will fix that root cause; this addendum only makes sure A40's
own new report can't be undermined by it in the meantime.

- [ ] **AC-A40-9 (unified regenerated report).** One new command (e.g.
      `python examples/czsc_strategy/diagnostics/run_position_sizing_report.py --symbols
      AP888,RB888 --sizing-model risk`) produces a single git-tracked report (`git add -f`'d,
      since `diagnostics/` is git-ignored) that shows, for the same backtest run: (a)
      `sizing_model="risk"` position sizes and `pnl_currency` per closed trade, (b) the
      `stop_execution_model` in effect and a count of touch-based vs close-based stop exits
      (A38), and (c) whether a SimNow replay-derived risk caliber was consulted — if A41 has not
      landed yet, this field must read `"status": "not_available_pending_A41"`, never a
      fabricated number.
- [ ] **AC-A40-10 (no zero-placeholder risk in any risk-derived judgment).** Any judgment this
      report derives from `simnow_daily_capture.py`'s `build_risk()` output must not treat its
      hardcoded-zero fields (`daily_return_pct`, `drawdown_pct`, `gross_exposure`,
      `net_exposure`, `both_long_short_symbols`, `consecutive_loss`, `symbol_concentration`,
      `strategy_concentration`) as a real "0.0 observed" measurement. A risk figure sourced from
      `simnow.risk` must be labelled (`"risk_source": "simnow_capture_placeholder"` vs
      `"replay_computed"`) and a placeholder-sourced zero must never silently satisfy a
      warning/halt threshold. A40 does not need to fix the root cause (A41's job) — only ensure
      its own new report isn't fooled by it.
- [ ] **AC-A40-11 (contract-spec cross-check against A38 stop distance).** A test/report section
      confirms that for every `contract_specs` symbol, the risk-mode sizing denominator
      `stop_distance = price * stop_loss / 10000` is the *same* value A38's
      `stop_execution_model="intrabar"` actually uses to trigger an exit — catching future drift
      if `stop_loss` defaults change in one code path but not the other.
- [ ] **AC-A40-12 (`sizing_model="risk"` × `stop_execution_model="intrabar"` interaction test).**
      A dedicated test exercises both simultaneously (long and short fixtures), asserting
      `pnl_currency` on a touch-based stop exit uses the actual touched stop price — not
      `bar.close` — times the sized `volume`/`multiplier`. Without this, A38 and A40 could each
      pass their own unit tests while never being exercised together.
- [ ] **AC-A40-13 (unified report banner and scope statement).** The AC-A40-9 report carries the
      `Diagnostic only, not a trading recommendation.` (RESEARCH-ONLY) banner and its header
      states that `pnl_currency`/`total_open_margin`/`margin_utilization_pct` are backtest
      research outputs under `contract_specs`' exchange-*minimum* margin rates (§6), not
      production-ready capital-allocation numbers.

- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight`
      passes (or the current Manual-verification accommodation in `.synccheck.yml`/HANDOFF.md
      applies, if the codex-sandbox symlink limitation is still unresolved at review time).

---

## 8. Dev Handoff Prompt (dev = kimi-code)

```text
Read HANDOFF.md and docs/design/a40-real-position-sizing.md. Implement A40 (P3 real position
sizing) exactly as specified.

1. Add STRATEGY_CONFIG["sizing_model"] ("research" default | "risk"), risk_per_trade_pct (0.005),
   max_margin_pct (0.50), equity_mode ("fixed"), and contract_specs (AP888/RB888/SC888/A888/ZN888
   with multiplier/tick/margin_rate exactly as cited in design doc S2 -- do not alter these
   numbers, they are sourced from the exchanges' own published contract rules).
2. In positions.py, give Position a volume field (default 1) and contract_multiplier (default 1).
   Under "risk" mode, size on open per design S3.1: stop_distance = price*stop_loss/10000,
   risk_amount = equity_at_entry*risk_per_trade_pct, raw_volume = risk_amount/(stop_distance*
   multiplier), volume = floor(raw_volume), skip (no forced 1-lot floor) if <1, apply the margin
   cap (S3.1 step 5), reducing volume or skipping if it still doesn't fit. Under "research", none
   of this runs -- volume stays 1, output byte-identical to baseline.
3. Add pnl_currency to closed pairs (both modes, formula in S3.2); under "research" it's present
   but numerically trivial (volume=multiplier=1) and unused by existing report code.
4. In backtest_engine.py, thread equity_at_entry and margin-cap state into the open call under
   "risk" mode only (S3.3); "research" mode's existing fixed-weight equity loop stays untouched.
   Add sizing_model / total_open_margin / margin_utilization_pct to the report header and (risk
   mode) equity-curve rows.
5. Tests per design S7: research-mode equivalence (empty diff on >=2 symbols x 1yr), risk-mode
   sizing formula (long+short fixtures), zero-size skip (no forced floor), margin cap reduction
   and skip, currency PnL formula (long+short), no-lookahead assertion.

Do not tune risk_per_trade_pct/max_margin_pct via backtest results, do not use pre-2026-04-24 data
for any selection, do not touch SimNow order paths, no GOAL PASSED. If the pytest/preflight
acceptance commands hit the documented codex-sandbox symlink limitation during review, that's
covered by the existing Manual verification accommodation in .synccheck.yml -- not a code defect.

Run:
- python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
- python tools/sync_check.py ; python tools/sync_check.py --root examples/czsc_strategy
- powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
- python tools/handoff.py next --actor kimi-code --summary "A40 P3 real position sizing implemented"
```

---

## 9. Review Checklist (review = codex)

Reject if: `"research"` mode is not byte-identical (non-empty equivalence diff, or
`volume`/`pnl_currency` leak into any existing report field); the sizing formula deviates from
§3.1 (e.g. a forced 1-lot floor, or margin check using a future bar); `contract_specs` numbers
were altered from the cited exchange values without a new citation; currency PnL formula is wrong
in either direction; any threshold/weight tuned via backtest results; pre-2026-04-24 data used for
any selection; any SimNow order/cancel/send path changed; `sync_check` (root or child) fails.

Accept if all §7 boxes are checked and the handoff advances to review.

**Sources for §2 contract_specs (fetched 2026-07-11):**
- RB (螺纹钢): [SHFE 螺纹钢期货合约(修订版)](https://www.shfe.com.cn/products/futures/metal/ferrousandpreciousmetal/rb_f/standard_rb_f/202312/t20231205_327324.html)
- SC (原油): [INE/SHFE 原油期货标准合约(SC)](https://www.ine.com.cn/products/futures/energyandchemical/sc_f/standard_sc_f/202312/t20231205_802540.html)
- A (豆一): [DCE 黄大豆1号期货合约及交割要素](https://www.glqh.com/u/cms/www/202206/13145931v8jv.pdf), [DCE 附件3:各品种合约](http://www.dce.com.cn/dalianshangpin/ywfw/jystz/ywtz/8592608/)
- ZN (沪锌): [SHFE 锌期货合约(修订版)](https://www.shfe.com.cn/products/futures/metal/nonferrousmetal/zn_f/standard_zn_f/202312/t20231205_309038.html)
- AP (苹果): [CZCE 苹果期货合约规则介绍](https://www.czce.com.cn/cn/rootfiles/2021/09/09/1605597612939463-1605597612959828.pdf)
