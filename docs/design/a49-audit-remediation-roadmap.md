# A49 Design: 2026-07-12 Audit Remediation Roadmap

**Task:** Convert `docs/review/ai_trading_review_2026-07-12.md`'s 13 findings (2 high / 7 medium /
3 low, overall 56/100) into a phased, dev-ready remediation sequence with explicit gates,
following the same design→dev→review→done discipline used for A38-A48.

**Scope:** Design only. Do not implement any fix in this document. Do not tune parameters, do not
use pre-2026-04-24 data to select any new value, do not present any historical result as a fresh
profitability proof.

**Status:** DRAFT — not yet started as a HANDOFF task. Produced 2026-07-12 immediately after the
independent audit completed. This document assigns the next task IDs (**A49-A54**) but does not
promote any of them; promote and start each phase individually, in the sequence below, following
the established one-task-at-a-time house rule.

---

## 1. Background

`docs/review/ai_trading_review_2026-07-12.md` (an independent read-only audit by a
general-purpose subagent acting under the `ai-stock-trading-reviewer` skill, spot-verified by
claude-code) scored the strategy 56/100 (C). No dimension scored ≤2 (no single "fatal" defect),
but two dimensions are "major issue" tier and gate live/semi-automated use:

- **D2 风控完整性 (risk control) = 4/10** — a real, reproducible bug: `_scale_out` can silently
  return without setting `_partial_tp_done`, which permanently blocks the ATR trailing-stop
  branch from ever being evaluated for that position (an `elif`-chain short-circuit).
- **D5 数据假设处理 (data assumptions) = 3/10** — no limit-up/limit-down/halt handling anywhere
  in the fill path; unstated/unverified continuous-contract adjustment method; rollover exclusion
  exists only as a read-only diagnostic, never applied to the default backtest path.

The remaining findings (D3/D6/D8/D10 territory) are config/documentation hygiene and
single-source-of-truth gaps — real, but lower urgency than the two above.

This roadmap triages all 13 findings into six tasks (A49-A54), ordered by the audit's own "修复
优先级建议" section, each independently testable per the established house discipline:

- **Gated + default-off** for anything that changes observed backtest output (equivalence test
  required on the legacy path) — *except* A49, which is a straight correctness fix inside an
  already-opt-in switch (`exit_model="structural_atr"`), not a new behavior needing its own gate.
- **Diagnostic-first** where a fix's effect size is unknown (limit-up/down impact must be
  quantified before any fill-constraint enforcement ships).
- **No selection on stale data**: no pre-2026-04-24 data for any new parameter choice.
- **No-lookahead**: any new field/check reads only bars up to and including the current one.
- **Safety**: `Diagnostic only, not a trading recommendation.` banner on every report; no
  `GOAL PASSED`; no new `send_order`/`cancel_order`/`buy`/`sell`/`short`/`cover`.

**Task-ID note:** this repo's task numbering is now A38-A48 for the P1-P8 roadmap (with A41/A42
consumed by an earlier unrelated detour, per the renumbering already recorded in
`docs/design/a38-phase-contracts-p2-p8.md`). This document continues sequentially from **A49**,
the next unused ID as of 2026-07-12.

---

## 2. Task Sequence

| ID | Title | Audit findings covered | Depends on |
|----|-------|------------------------|------------|
| A49 | ATR trailing-stop reachability fix | 🔴#1 | none — start first |
| A50 | Limit-up/down/halt impact diagnostic (read-only) | 🔴#2 (part 1) | none |
| A51 | Limit-up/down/halt fill-constraint enforcement (gated) | 🔴#2 (part 2) | A50 done |
| A52 | Continuous-contract data-integrity (adjustment method + rollover stat field) | 🟠#4, 🟠#5 | none |
| A53 | Config/signal single-source-of-truth cleanup | 🟠#6, 🟠#7, 🟠#8, 🟢#10 | none |
| A54 | Report-disclaimer hygiene + sync_check gate | 🟠#3, 🟠#9 | none |

A50→A51 is the only hard dependency (mirrors the P2a→P2b diagnostic-then-enforcement pattern
already used for rollover exclusion in A39). A49, A52, A53, A54 are independent of each other and
of A50/A51 — they may be sequenced in any order, but per the standing house rule **only one task
is promoted/active at a time**; the order in the table above is the recommended priority order,
not a hard requirement.

**Backlog, not scheduled as formal tasks** (🟢 low-severity, non-blocking — pick up opportunistically
or bundle into whichever of A49-A54 touches the same file):
- 🟢#11 `VERSION`/`CHANGELOG.md` catch-up (15 tasks, A34-A48, with no changelog entries) — first
  verify whether `tools/sync_check.py`'s actual version-bump trigger rule requires an entry for
  default-unchanged optional-switch tasks before treating this as a real gap.
- 🟢#12 Archive `HANDOFF.md`'s now-resolved A48 "Review Reject Notes" section (already-fixed
  defects left in place, cosmetic-only staleness risk) — natural fit inside whichever of A49-A54
  next touches `HANDOFF.md`'s Decision Log conventions, or its own tiny task if none do.
- 🟢#13 Per-symbol slippage calibration (flat 0.05% across heterogeneous-liquidity contracts) —
  a research task requiring real historical spread/impact data, not a code defect; defer until
  there's a concrete data source, not part of this remediation wave.

---

## A49 — ATR Trailing-Stop Reachability Fix

### Rationale
`_scale_out` (`chan_strategy/positions.py:832-846`) returns early without setting
`self._partial_tp_done = True` when `sizing_model="risk"` and the fractional scale-out volume
floors to `< 1` lot or `>= self.volume`. Because `Position.update`'s `structural_atr` branch
(`positions.py:680-688`) is an `elif` chain — `elif not self._partial_tp_done: ... elif
self._check_atr_trailing_stop(...): ...` — every subsequent bar re-enters the `not
self._partial_tp_done` branch (does nothing, since `_get_partial_tp_event` still returns a match
or not) and the ATR trailing-stop check on the next line is **never evaluated** for the rest of
that position's life. Under `exit_model="structural_atr"` + `sizing_model="risk"`, this silently
removes the only profit-side risk control (fixed stop-loss and timeout still fire; ATR trailing
does not) for any position whose lot count doesn't cleanly support the configured
`partial_tp_frac` split — a common case for small accounts, low-multiplier symbols, or any
already-1-lot position.

### Semantics
No new config key. Fix `_scale_out`: when the risk-sizing floor makes a partial scale-out
impossible (`scale_volume < 1` or `scale_volume >= self.volume`), treat this as "partial TP
skipped, not pending" — set `self._partial_tp_done = True` before returning (optionally log/record
a `reason_code="partial_tp_skipped_lot_floor"` marker for diagnostics, but do not fabricate a
`pairs` entry — no trade actually happened). This makes the `elif self._check_atr_trailing_stop`
branch reachable on the very next bar, exactly as if the partial TP had "already happened" (with
zero volume scaled out).

### No-lookahead & correctness
Purely a same-bar state-flag fix; no new data read, no timing change to any existing exit check.

### Expected files
- `chan_strategy/positions.py` (`_scale_out`)
- `chan_strategy/tests/unit/test_exit_model.py` (new case: `sizing_model="risk"` + single-lot
  position + `exit_model="structural_atr"` — assert the ATR trailing-stop branch is reached and
  can fire on a subsequent bar, where before the fix it provably could not)

### Acceptance (decidable)
- [ ] A fixture with `sizing_model="risk"`, a position sized to exactly 1 lot, and
      `exit_model="structural_atr"` proves: before the fix, `_check_atr_trailing_stop` is never
      called after the skipped partial-TP bar (test written to fail against the pre-fix code, e.g.
      via a spy/call-count on the check); after the fix, it is called on the very next bar.
- [ ] `_partial_tp_done` is `True` immediately after a skipped-partial-TP bar in this scenario.
- [ ] No `pairs` entry is fabricated for the skipped partial TP (zero volume actually changed
      hands).
- [ ] `sizing_model="research"` (fractional volume, no lot flooring) behavior is unaffected —
      existing `test_structural_atr_partial_tp_long`/`_short` still pass unchanged.
- [ ] `exit_model="legacy"` behavior is completely unaffected (this bug only exists inside the
      `structural_atr` branch) — the existing legacy-equivalence golden-snapshot test still passes
      byte-identical.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not change `partial_tp_frac`'s value or the partial-TP trigger condition itself — only fixes
the state-flag bug that blocks the *subsequent* ATR-trailing check. Does not touch
`sizing_model="research"`'s partial-TP path (which has no lot-flooring, so the bug cannot occur
there).

### Dev prompt
```text
Read A49. Fix _scale_out (positions.py:832-846) so that when a risk-mode partial-TP scale-out is
skipped due to lot flooring (scale_volume < 1 or >= self.volume), self._partial_tp_done is set
True before returning -- do not fabricate a pairs entry. Add a regression test proving the ATR
trailing-stop branch becomes reachable on the next bar in this scenario, and that it provably was
NOT reachable before the fix. Do not touch exit_model="legacy" or sizing_model="research" paths.
No tuning, no SimNow paths, no GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: `_partial_tp_done` is not set in the skipped-scale-out path; a fake `pairs` entry is
created for zero actual volume; the fix changes `exit_model="legacy"` or
`sizing_model="research"` behavior at all; no regression test proves the bug existed before the
fix (a test that only asserts post-fix behavior, without demonstrating the pre-fix blockage, is
insufficient evidence this was a real fix and not a coincidental pass).

---

## A50 — Limit-Up/Down/Halt Impact Diagnostic (Read-Only)

### Rationale
Zero limit-up/limit-down/trading-halt handling exists anywhere in `data_adapter.py`/
`backtest_engine.py`/`positions.py` (confirmed by the audit via full-repo grep). Entries fill at
next-bar open, stops fill at current-bar close/high/low — with no check for whether that bar was
actually tradable. AP888 (苹果) and RB888 (螺纹钢) both carry real daily price-limit bands. Per
house discipline ("diagnostic-first: where a phase claims an effect, a read-only diagnostic
quantifies it before the switch is turned on by default" — same pattern as A39's P2a rollover
diagnostic before P2b's enforcement), this task ships the read-only measurement first; A51 (fill
enforcement) does not start until this diagnostic has run and been reviewed.

### Config
No new `STRATEGY_CONFIG`/`BACKTEST_CONFIG` keys — read-only diagnostic only.

### Semantics
New `diagnostics/limit_halt_exposure_report.py`:
- For each symbol in the standard default set (AP888/RB888/SC888/A888/ZN888), compute a daily
  price-limit band from the contract's limit-percentage (cite the source — exchange-published
  daily limit percentage per product, same sourcing discipline as A40's `contract_specs`; do NOT
  fabricate a percentage) and the previous trading day's settlement/close.
- For every historical trade (from the honest post-2026-04-24 baseline replay, `exit_model`/
  `sizing_model` at their defaults), flag whether the **open** (entry fill bar) or the **exit**
  fill bar's price sits at or beyond the computed limit band.
- Report: `trades_at_limit_open_count`, `trades_at_limit_exit_count`, `pct_of_total_trades`,
  per-symbol breakdown, and (if the raw table exposes any volume/turnover column) a secondary
  "zero-volume bar" cross-check as a proxy for halted/no-liquidity conditions.
- This is a measurement only — it does not change what the default backtest reports, does not
  block or adjust any fill, and is not consulted by `BacktestEngine`/`PortfolioEngine`.

### No-lookahead & correctness
Uses only each trade's own recorded open/close prices and the previous day's close for the limit
band — no future data. Read-only; cannot mutate strategy behavior by construction.

### Expected files
- `examples/czsc_strategy/diagnostics/limit_halt_exposure_report.py` (tracked, not under an
  ignored path — or force-added per house convention)
- `examples/czsc_strategy/tests/unit/test_limit_halt_exposure_report.py`
- A cited-source comment block for each symbol's daily limit percentage (exchange rule, same
  citation bar as A40's `contract_specs`)

### Acceptance (decidable)
- [ ] Report generated for all 5 default symbols on the post-2026-04-24 window (or an explicit
      `unavailable`/error reason per symbol, matching A43-A48's report precedent).
- [ ] Each symbol's daily limit percentage carries an inline cited exchange-rule source comment.
- [ ] Report distinguishes entry-at-limit vs. exit-at-limit counts; totals reconcile with the
      symbol's total trade count from the same baseline replay.
- [ ] RESEARCH-ONLY banner present; report is evidence only, never wired into
      `BacktestEngine`/`PortfolioEngine`'s actual fill logic (that is A51's job, gated).
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow paths; no `GOAL PASSED`.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not implement any fill-constraint enforcement (A51's scope). Does not claim the current
backtest results are wrong by any specific amount — only measures exposure so A51 (or a future
decision not to pursue A51 at all, if exposure turns out to be negligible) can be scoped with
real evidence instead of assumption.

### Dev prompt
```text
Read A50. Ship a read-only diagnostic quantifying how many historical trades' entry/exit fills
land at or beyond each symbol's daily price-limit band. Cite the limit-percentage source per
symbol (exchange rule, do not fabricate). Report only -- do not touch backtest_engine.py,
positions.py, or data_adapter.py's actual behavior. No tuning, no SimNow paths, no GOAL PASSED.
Handoff next.
```

### Review checklist
Reject if: any limit percentage lacks a cited source; the diagnostic is wired into any code path
that affects backtest output; report is generated against placeholder/wrong-window data (verify
against the A45/A46 report-generation mistakes already caught this cycle); no RESEARCH-ONLY
banner.

---

## A51 — Limit-Up/Down/Halt Fill-Constraint Enforcement (Gated)

**Depends on A50 reaching `done`.** Do not promote this task until A50's report exists and has
been reviewed — the exposure percentage it measures should inform whether this task's scope is
"add a statistics-only flag" or "actually block/reprice fills," per the diagnostic-first
discipline.

### Rationale
Once A50 quantifies exposure, decide (as part of this task's design refinement, informed by real
numbers, not assumption) whether to: (a) simply tag affected trades in reports (lowest-risk,
statistics-only), or (b) actually constrain fills (no fill possible on a bar priced at the limit
in the position's adverse direction; favorable-direction limit bars are assumed fillable). Do not
finalize this task's exact `Semantics` section until A50's numbers are in — this section is
intentionally left as a placeholder contract shape, to be completed as part of A51's own design
step, using A50's output.

### Config (placeholder shape — finalize after A50)
```python
"limit_halt_model": "off",   # "off" (legacy, default, byte-identical) | "aware"
```

### Semantics (to be finalized using A50's evidence)
Under `"aware"`: at minimum, tag every fill (`pairs` entry) with whether it landed on a
limit-band bar; if A50's measured exposure is material (threshold to be judged, not
pre-committed, when this task is actually scoped), additionally suppress/reprice fills that would
require adverse-direction liquidity at the limit.

### No-lookahead & correctness
Uses only the current bar's own OHLC and the previous day's close/settlement for the limit band —
same no-lookahead guarantee as A50.

### Expected files
- `chan_strategy/data_adapter.py` and/or `chan_strategy/backtest_engine.py`/`positions.py`
  (exact touch points to be finalized once A50's evidence determines scope)
- `chan_strategy/config.py` (`limit_halt_model` key)
- Full-`BacktestEngine` golden-snapshot equivalence test for `"off"` (mandatory — do not repeat
  A44's mistake of shipping a gated default without this proof from the start)
- `diagnostics/limit_halt_exposure_report.py` updated (or a new comparison report) to show
  off-vs-aware impact

### Acceptance (decidable)
- [ ] `limit_halt_model="off"` (default) → byte-identical to current (full-`BacktestEngine`
      golden-snapshot equivalence test, present from the first dev round).
- [ ] `"aware"` mode's exact behavior is unit-tested per whatever scope A50's evidence justified.
- [ ] No threshold/percentage is tuned via backtest selection; the limit-percentage sourcing is
      cited (reuse A50's citations, do not re-derive).
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Do not touch position sizing (P3/A40's scope) or exit-model logic beyond fill feasibility (P8a/
A47's scope). This is a fill-feasibility layer only.

### Dev prompt
```text
Read A51 (finalize Semantics using A50's report numbers before writing code). Add limit_halt_model
gate, "off" default byte-identical (equivalence test from the start, per the A44 lesson). Scope
"aware" mode's actual enforcement per A50's measured exposure. No tuning, no SimNow paths, no
GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: `"off"` is not byte-identical from the first dev round; the enforcement logic
introduces lookahead; limit percentages are uncited or re-derived without citation; A50 was not
`done` before this task started.

---

## A52 — Continuous-Contract Data-Integrity (Adjustment Method + Rollover Stat Field)

### Rationale
Two related, previously-unaddressed data-assumption gaps in the "888" continuous-contract series:

1. **Undeclared adjustment method** (audit finding 🟠#5): `data_adapter.py` treats every row as
   raw OHLCV with no adjustment metadata; contrast `run_baostock_backtest.py:242`'s explicit
   `adjustflag="2"  # 前复权` for the equity script. Whether AP888/RB888/SC888/A888/ZN888 are
   front-adjusted, back-adjusted, or an unadjusted raw splice is currently undocumented in code,
   even though A34's H4 finding (`found_spliced`) already established the series is a raw splice
   at the SQLite-metadata level — this task makes that assumption an explicit, code-visible,
   verified fact rather than tribal knowledge in a design doc.
2. **Rollover exclusion never reaches the default path** (audit finding 🟠#4): A39's
   `rollover_exclusion_report.py` proved rollover contamination is real and measurable, but the
   exclusion logic lives only in that standalone diagnostic — `data_adapter.py`/
   `backtest_engine.py` never tag or optionally exclude rollover-window trades by default.

### Config
```python
"rollover_stat_tagging": "off",   # "off" (legacy, default, byte-identical) | "on"
```
No config key needed for the adjustment-method declaration itself — that is a code comment +
one-time verification script, not a runtime behavior switch (there is nothing to gate; it's
documentation of an existing, unchanging fact about the data).

### Semantics
**Part A — adjustment-method declaration (no gate, no behavior change):**
- Add a one-time verification script (`diagnostics/contract_adjustment_verification.py`,
  read-only) that inspects the raw SQLite table(s) for AP888/RB888/SC888/A888/ZN888 and
  determines/confirms the splicing method actually in use (e.g. by checking for price
  discontinuities at known rollover dates from A39's own transition-date detection — a
  continuous/adjusted series should show smooth transitions, a raw splice should show gaps).
  Cross-reference against A34's H4 `found_spliced` finding to confirm it still holds.
- Add an explicit, prominent comment block in `data_adapter.py` (near the table-loading code)
  stating the confirmed method and citing this verification script's output.

**Part B — rollover stat tagging (gated, default off, byte-identical):**
- Under `"on"`, `data_adapter.py`'s bar-loading path attaches an `is_rollover_window: bool` field
  to each loaded bar (or an equivalent per-trade tag applied in `backtest_engine.py`), using
  A39's already-proven transition-date detection logic (reuse it — do not reimplement). Reports
  can then split "including rollover-window trades" vs. "excluding" without needing to invoke the
  standalone diagnostic separately. This does NOT filter/exclude trades from the actual backtest
  by default — it only makes the tag available for reporting. A future task may decide whether to
  gate live opens around rollover windows; that decision is explicitly out of scope here (mirrors
  A39 P2's own stated Boundary).

### No-lookahead & correctness
Rollover-window tagging uses only the already-detected transition dates (known from the data
itself, not the future) — same no-lookahead property as A39's original diagnostic.

### Expected files
- `examples/czsc_strategy/diagnostics/contract_adjustment_verification.py` (new, read-only)
- `chan_strategy/data_adapter.py` (adjustment-method comment block; optional
  `is_rollover_window` tagging under the new gate)
- `chan_strategy/config.py` (`rollover_stat_tagging` key)
- `chan_strategy/tests/unit/test_data_adapter.py` (new cases for the tagging field)
- Full-`BacktestEngine` equivalence test for `rollover_stat_tagging="off"` (mandatory from the
  start)

### Acceptance (decidable)
- [ ] `contract_adjustment_verification.py` produces a definitive, cited conclusion about the
      splicing/adjustment method for each of the 5 default symbols, cross-referenced against
      A34's H4 finding.
- [ ] `data_adapter.py` carries an explicit comment stating the confirmed method (not "assumed" —
      "confirmed by `contract_adjustment_verification.py` on `<date>`").
- [ ] `rollover_stat_tagging="off"` (default) → byte-identical to current (full-`BacktestEngine`
      equivalence test, present from the first dev round).
- [ ] `rollover_stat_tagging="on"` → a fixture with a known rollover date proves bars/trades
      within the transition window are correctly tagged `is_rollover_window=True`; bars outside
      are `False`.
- [ ] No new trade-filtering behavior — `"on"` only adds a tag, never excludes a trade from the
      default backtest (that remains the standalone diagnostic's exclusive behavior, per A39's
      original Boundary, unless a future task explicitly revisits this).
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not implement back-adjustment or re-splice the data (out of scope, same as A39's original
Boundary: "no back-adjusted price reconstruction"). Does not gate live opens around rollover
windows. Does not change any existing report's numbers under the default `"off"` tagging mode.

### Dev prompt
```text
Read A52. Part A: ship a read-only verification script confirming AP/RB/SC/A/ZN888's continuous-
contract splicing method, cross-referenced against A34's H4 finding; add a cited comment block to
data_adapter.py. Part B: add rollover_stat_tagging gate ("off" default byte-identical), reusing
A39's transition-date detection to tag bars/trades with is_rollover_window under "on" -- tagging
only, never filtering. Equivalence test for "off" from the start. No tuning, no SimNow paths, no
GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: the adjustment-method conclusion is asserted without verification-script evidence;
`"off"` is not byte-identical from the first dev round; `"on"` mode filters/excludes any trade
(scope creep beyond tagging); the rollover-date detection logic is reimplemented instead of reused
from A39.

---

## A53 — Config/Signal Single-Source-of-Truth Cleanup

### Rationale
Three related dead-config/dead-code findings, all "the code reads or presents something that
cannot actually change behavior," bundled because they're all small, mechanical, and
zero-behavior-change once fixed correctly:

1. **🟠#6 Orphan config keys**: `_research_first_buy_allowed`/`_daily_trend_filter_signals` (or
   their neighbors) read `enable_1buy_symbols`, `block_1buy_daily_down`,
   `block_1buy_daily_not_up`, `block_1buy_daily_below_zs` via `STRATEGY_CONFIG.get(...)` —
   none of these keys exist in `config.py`, so these gates are permanently no-op regardless of
   any config edit.
2. **🟠#7 Duplicated `stop_loss_pct=0.05`**: hardcoded as a function-signature default in 4
   places (`signals.py:726,793`, `sell_signals.py:235,261`) for the *structural-invalidation*
   concept (price breaking 5% past a center edge), confusingly named identically to but distinct
   from the *position stop-loss* concept (`config.py`'s `stop_loss_1buy=200`/`stop_loss_2buy=300`/
   `stop_loss_3buy=350`, in basis points).
3. **🟠#8 Orphaned legacy signal implementation**: `signals.py`'s original
   `signal_second_buy`/`signal_third_buy` (superseded by `sell_signals.py`'s corrected versions,
   per that module's own docstring) remain defined and near `get_all_signals`'s import surface,
   even though the current production pipeline imports the corrected versions from
   `sell_signals.py`.
4. **🟢#10 `equity_mode` dead config**: declared in `config.py` with `"fixed"`/`"compound"`
   documented options, but no code anywhere branches on this key — it is read only by a tautological
   test assertion (`test_position_sizing.py:24,55`), never by `positions.py`/`backtest_engine.py`/
   `portfolio_engine.py`.

### Config
```python
# Either fill in real defaults (False, matching current no-op behavior) so the keys become
# genuinely readable/settable, or delete the dead .get() calls entirely -- dev's choice per
# item, but the outcome must not be "key still doesn't exist and code still silently no-ops."
"enable_1buy_symbols": None,          # None = all symbols (matches today's de-facto behavior)
"block_1buy_daily_down": False,
"block_1buy_daily_not_up": False,
"block_1buy_daily_below_zs": False,
"structural_invalidation_pct": 0.05,  # was hardcoded 4x; now single-sourced
```
`equity_mode`: either delete the key entirely, or make `"compound"` raise `NotImplementedError`
at the one call site that would need to branch on it (explicit "not implemented" beats silent
no-op, per the audit's own recommendation) — dev's choice, but pick one, don't leave it decorative.

### Semantics
- The four orphan keys: once added to `config.py` with defaults matching today's de-facto no-op
  behavior (`None`/`False`), the existing `positions.py` gating code becomes genuinely
  controllable — this is a **behavior-enabling** change (previously-inert code becomes live), so
  it needs the same equivalence discipline as any new gate: defaults must reproduce current
  output exactly, and each gate's *actual* on-behavior needs its own unit test (most of this
  logic already exists and is presumably correct — it was just unreachable — so the main new work
  is the equivalence proof plus verifying the pre-existing conditional logic is correct now that
  it's reachable).
- `stop_loss_pct` → `structural_invalidation_pct`: single-source the value in `STRATEGY_CONFIG`,
  update all 4 call sites to read from config instead of a hardcoded default, with an inline
  comment distinguishing it from the position stop-loss tiers.
- `signals.py`'s superseded `signal_second_buy`/`signal_third_buy`: either delete them (if
  confirmed truly unreferenced outside `sell_signals.py`'s own corrected versions — verify via
  grep/import-graph before deleting) or add an unmistakable module-level comment/deprecation
  marker pointing to the `sell_signals.py` versions as the sole authoritative implementation.
- `equity_mode`: per above.

### No-lookahead & correctness
None of these changes touch bar-by-bar data flow — pure config/dead-code hygiene. The
newly-reachable orphan-key gating logic must be re-verified for no-lookahead as part of testing it
for the first time (it was previously unreachable, so it has never actually been exercised against
real data).

### Expected files
- `chan_strategy/config.py` (new keys, `structural_invalidation_pct`, `equity_mode` resolution)
- `chan_strategy/positions.py` (now-reachable orphan-key gates — verify correctness; possible
  deletion of superseded `signals.py` functions is cross-file)
- `chan_strategy/signals.py`, `chan_strategy/sell_signals.py` (`structural_invalidation_pct`
  call-site updates; legacy-signal deprecation/deletion)
- `chan_strategy/tests/unit/test_positions.py`, `test_signals.py` (equivalence + new-gate
  behavior tests)
- Full-`BacktestEngine` equivalence test for the orphan-key defaults (mandatory)

### Acceptance (decidable)
- [ ] All four orphan keys exist in `config.py` with defaults matching today's de-facto behavior;
      a full-`BacktestEngine` equivalence test proves default output is byte-identical to before
      this task.
- [ ] Each orphan key's actual on-behavior (`True`/non-`None` value) is unit-tested and confirmed
      to behave as its variable name implies (e.g. `block_1buy_daily_down=True` genuinely blocks a
      一买 open when daily direction is 向下).
- [ ] `structural_invalidation_pct` is read from `STRATEGY_CONFIG` at all 4 former hardcode sites;
      changing the config value changes all 4 call sites' behavior identically (unit-tested); a
      comment at the config key distinguishes it from `stop_loss_1buy`/`2buy`/`3buy`.
- [ ] `signals.py`'s superseded 二买/三买 signal functions are either deleted (with an
      import-graph check proving nothing outside `sell_signals.py`'s own corrected versions
      referenced them) or carry an explicit deprecation comment pointing to the authoritative
      version.
- [ ] `equity_mode` either no longer exists, or `"compound"` raises `NotImplementedError` at a
      real call site (unit-tested) — not a decorative unread key either way.
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow paths; no `GOAL PASSED`.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not change the *semantics* of any of the four orphan gates' existing conditional logic
(only makes them reachable) — if that logic turns out to be buggy once actually exercised, that's
a new finding for a future task, not silently fixed here without review visibility. Does not touch
`structural_atr`/P8a exit logic (A47/done) or the P8b portfolio coordinator (A48/done).

### Dev prompt
```text
Read A53. Fill in the four orphan config keys (enable_1buy_symbols, block_1buy_daily_down,
block_1buy_daily_not_up, block_1buy_daily_below_zs) with today's de-facto no-op defaults; prove
equivalence, then unit-test each gate's actual on-behavior. Single-source stop_loss_pct as
structural_invalidation_pct in STRATEGY_CONFIG across all 4 call sites. Delete or deprecate-mark
signals.py's superseded 二买/三买 implementations (verify import graph first). Resolve equity_mode
(delete or NotImplementedError on "compound"). No tuning, no SimNow paths, no GOAL PASSED.
Handoff next.
```

### Review checklist
Reject if: any orphan key's default doesn't reproduce current behavior byte-identical; an
orphan gate's on-behavior test doesn't actually verify the variable name matches real behavior;
`structural_invalidation_pct` still has any hardcoded duplicate; a superseded `signals.py`
function is deleted without an import-graph check proving safety; `equity_mode` is left as a
silently-unread decorative key.

---

## A54 — Report-Disclaimer Hygiene + `sync_check` Gate

### Rationale
Two related reporting-integrity findings:

1. **🟠#3**: `sizing_model="research"`'s "not tradable PnL" caveat
   (`backtest_engine.py:721-722`) is only `print()`-ed to console, never written into the
   `diagnostics/*.md`/`*.json` report body — a reader opening only the report file has no way to
   know the numbers aren't real tradable PnL.
2. **🟠#9**: ~90 of 130 `diagnostics/*.md` reports lack the RESEARCH-ONLY banner, despite
   `declassify_historical_reports.py` already existing specifically to backfill this — it has
   evidently never been run against the full current report set.

### Config
No new `STRATEGY_CONFIG` key. This is a reporting-pipeline and CI-gate change, similar in kind to
A42's sync-guardian hardening (tooling/process, not trading logic).

### Semantics
- **Part A**: every report-writing function in `chan_strategy/backtest_engine.py`/
  `chan_strategy/portfolio_engine.py` that currently only `print()`s the `sizing_model="research"`
  caveat must also write it into the returned report `dict` under a stable key (e.g.
  `"sizing_caveat"`), and every `diagnostics/*.py` script that serializes a `BacktestEngine`/
  `PortfolioEngine` report to JSON/MD must surface that field in the file body when present (not
  just the console).
- **Part B**: run `declassify_historical_reports.py` against the full current
  `diagnostics/*.md` set (not just the ones it's already covered) and commit the results (force-add,
  since `diagnostics/` is git-ignored — same mechanism used throughout A40-A48). Add a new
  `sync_check.py` check (extending A42's vendored `sync_check.py`, reuse — do not fork a second
  copy) that fails when a **newly added** `diagnostics/*.md` file lacks the RESEARCH-ONLY banner
  string, so this gap cannot silently reopen.

### No-lookahead & correctness
Not applicable — this task touches reporting/metadata only, no trading logic or data flow.

### Expected files
- `chan_strategy/backtest_engine.py`, `chan_strategy/portfolio_engine.py` (`sizing_caveat` field
  in report dict)
- Every `diagnostics/*.py` report-serialization script that reads a `sizing_caveat`-bearing
  report needs a one-line update to surface it in JSON/MD output (grep for
  `sizing_model.*research` consumers to find the full list — do not guess)
- `examples/czsc_strategy/diagnostics/declassify_historical_reports.py` — run against the full
  current report set; commit results
- `tools/sync_guardian/sync_check.py` (new check: new `diagnostics/*.md` files must contain the
  RESEARCH-ONLY banner string)
- `examples/czsc_strategy/tests/unit/test_sync_guardian.py` or equivalent (new-report-banner-gate
  test, mirroring A42's `no_auto_advance`/deliverables-freshness test pattern)

### Acceptance (decidable)
- [ ] `sizing_caveat` field present in every report `dict` returned by `BacktestEngine.run()`/
      `PortfolioEngine.run()` when `sizing_model="research"`; absent (or `null`) under
      `sizing_model="risk"`.
- [ ] At least one diagnostics report script demonstrably surfaces `sizing_caveat` in its output
      MD/JSON when present (unit-tested).
- [ ] `declassify_historical_reports.py` run against the full current `diagnostics/*.md` set;
      before/after counts of "reports missing RESEARCH-ONLY" reported and committed as evidence
      (e.g. `declassify_run_2026-XX-XX.json`); the after-count is `0` for every currently-tracked
      report file.
- [ ] A new `sync_check.py` check fails (non-zero exit, named file in the error) for a fixture new
      `diagnostics/*.md` file lacking the banner string; passes once the banner is present
      (unit-tested, mirroring A42's deliverables-freshness test pattern).
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow paths; no `GOAL PASSED`.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not retroactively re-score or re-evaluate any historical report's trading conclusions —
purely a disclaimer/labeling pass. Does not change any report's numeric content, only adds/backfills
metadata fields and banner text. Does not create a second, forked copy of `sync_check.py`'s logic
— extends the existing vendored copy from A42.

### Dev prompt
```text
Read A54. Add a sizing_caveat field to BacktestEngine/PortfolioEngine reports when
sizing_model="research", surfaced by at least one diagnostics report script's output. Run
declassify_historical_reports.py against the full current diagnostics/*.md set and commit results
showing 0 reports missing the RESEARCH-ONLY banner afterward. Extend tools/sync_guardian/
sync_check.py with a new-report-must-have-banner check, tested per A42's deliverables-freshness
pattern. No tuning, no SimNow paths, no GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: `sizing_caveat` is added to the report dict but no consumer script actually surfaces
it anywhere; the declassify re-run leaves any currently-tracked report without the banner; the new
`sync_check` gate doesn't actually fail on a fixture missing the banner (no teeth, mirroring the
lesson from A42's own "prove the gate has teeth" acceptance criterion); a duplicate/forked
`sync_check.py` is created instead of extending the vendored one.

---

## 3. Cross-Task Notes

- **Switch stacking**: A49 is a bug fix (no switch). A51/A52/A53 each add independently-gated
  switches, all defaulting to today's exact behavior — any subset may be enabled together for a
  gated experiment. A54 adds no runtime switch (pure reporting/CI).
- **Promotion discipline unchanged**: no task in this roadmap may claim `GOAL PASSED` or
  profitability from pre-2026-04-24 data. Any future decision to actually enable `limit_halt_model`,
  `rollover_stat_tagging`, or the orphan 一买 gates by default is a separate, future,
  holdout-validated promotion decision — not an acceptance criterion of A49-A54.
- **Each task is its own handoff task** (design → dev → review → done) with the section above as
  the design contract; do not batch multiple A49-A54 items into one dev handoff, matching the
  discipline already used throughout A38-A48.
- **Recommended order**: A49 (quick, high-value bug fix) → A50 → A51 (diagnostic-then-enforcement
  pair) → A52 → A53 → A54, but A52/A53/A54 have no hard dependency on each other or on A50/A51 and
  may be resequenced if priorities change.

## 4. A54 Dev Completion Note

2026-07-13: A54 dev completed — `sizing_caveat` added to `BacktestEngine`/`PortfolioEngine`
report dicts, surfaced in `run_position_sizing_report.py`,
`declassify_historical_reports.py` run against all eligible diagnostics reports
(103 missing banners → 0 missing), and `tools/sync_guardian/sync_check.py`
extended with a `diagnostics_banner_check` gate.
