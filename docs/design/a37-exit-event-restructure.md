# A37 Design: Exit-Event Boolean Restructure (Structural Exit Reachability)

**Task:** Give losing positions a structural exit path that can fire before the fixed stop-loss, by fixing the boolean structure of exit events and the zhongshu-mode mismatch between risk-control and position signals.

**Scope:** Phased. Phase 0 is a read-only diagnostic. Phase 1 is a provably behavior-neutral dead-factor removal. Phase 2 is a config-gated semantics change that is OFF by default. No SimNow order/cancel/trading interface changes at any phase.

**Queue position:** A37 activates after A36 (SimNow replay backfill closure) reaches `done`. Do not overwrite the A36 HANDOFF state with this task while A36 is open.

---

## 1. Background

The 2026-07-07 win-rate audit found that the "structural exit" design intent is not reachable in the live backtest path. Evidence:

Exit-reason distribution over the full sample (`diagnostics/pnl_attribution_20220101_20260424.md`, 358 trades):

- `stop_loss`: 155 trades, 0% win rate, cumulative about `-489%` (pnl_pct sum);
- `trailing_stop`: 114 trades, 99.1% win rate, cumulative about `+411%`;
- `signal_exit`: only 88 trades, cumulative about `+8.4%`;
- `timeout`: 1 trade.

Losing trades effectively have no structural exit; the fixed stop absorbs all of them. Three structural causes, all confirmed at source level:

1. **AND semantics.** `Event.is_match` (`chan_strategy/positions.py:125-141`) requires event-level `signals_any` AND at least one matching factor. All six exit events are written as `(结构失效 [∨ 震荡超限]) ∧ (directional/position factor)`:
   - 一买平多 `positions.py:569-591`
   - 二买平多 `positions.py:668-696`
   - 三买平多 `positions.py:766-792`
   - 一卖平空 `positions.py:846-860` (`:852`)
   - 二卖平空 `positions.py:928-955` (`:934`)
   - 三卖平空 `positions.py:1011-1030` (`:1017`)
   A standalone `结构失效` never closes a position, contradicting the docstring promise "两者并存，先触发者执行" (`signals.py:680-683`).
2. **Zhongshu-mode mismatch.** `结构失效` is computed from the **segment**-mode center (`signals.py:696`; short side `sell_signals.py:237`), while the position factors (`位置V260615_中枢内/中枢下方`) are computed from the **recent**-mode center (`zhongshu.py:44-92`, default `recent`). The AND therefore combines conditions about two different centers; joint satisfaction is accidental rather than designed. In addition, `结构失效` requires price below `zd * (1 - 0.05)` (`signals.py:719-721`), i.e. 5%+ below the center bottom, while fixed stops are 2%-3.5% (`config.py:31-36`) and fire first.
3. **Dead factor (H3 downstream).** The 二买平多 factor "方向反转且在中枢内" (`positions.py:685-694`, signal `背驰V260615_失效` at `:690`) and its 二卖平空 counterpart (`positions.py:946-954`, signal at `:950`) depend on a classification that never occurs on real data (`audit_issue_diagnostics_2026-07-04.md`, H3 `count=0`). These factors are unreachable code inside exit events.

This design executes the A34 Phase-4 decision ("repair/delete/deprecate" for the H3 dead branch) on the **consumer side**: the dead exit factors are deleted. Whether `signal_divergence_status` itself gets a reachable 失效 classification is explicitly deferred and out of scope here.

---

## 2. Design Goals

Must:

1. Quantify, before any behavior change, how often `结构失效` fired while the exit event was blocked by the AND structure (Phase 0).
2. Remove the two dead exit factors with a machine-checkable proof of behavioral equivalence on real data (Phase 1).
3. Provide a restructured exit semantics behind a config switch, default OFF, so the baseline stays byte-identical (Phase 2).
4. Keep all six exit events (long and short side) symmetric in treatment; note that `enable_short=False` is the baseline (`config.py:23`).

Must not:

- tune any numeric threshold (`stop_loss_pct=0.05`, stop-loss BPs, trailing params) or select values on data before 2026-04-24;
- change `Position._check_stop_loss`, `_check_trailing_stop`, timeout logic, or `BacktestEngine.run` ordering;
- change SimNow order/cancel/trading interfaces;
- claim `GOAL PASSED` or regenerate promotion evidence from the old OOS window;
- delete or rewrite historical diagnostics reports.

---

## 3. Phase 0: Exit-Blocked Reachability Diagnostic (read-only)

Add:

- `examples/czsc_strategy/diagnostics/exit_event_reachability_report.py`
- `examples/czsc_strategy/tests/unit/test_exit_event_reachability_report.py`

Generate:

- `examples/czsc_strategy/diagnostics/exit_event_reachability_report_YYYY-MM-DD.json`
- `examples/czsc_strategy/diagnostics/exit_event_reachability_report_YYYY-MM-DD.md`

Method: replay real bars per symbol through the existing signal pipeline (reuse the `generate_signal_history.py` pattern; extend the recorded keys to `风控V260615` / `空头风控V260615` / `位置V260615` / `方向V260615`). For every bar, evaluate each exit event three ways:

- `legacy_fired`: current `Event.is_match` result;
- `struct_alone`: event-level `signals_any` matched but no factor matched (the blocked case);
- `factor_alone`: a factor matched but `signals_any` did not.

Report per symbol and per event:

- counts of the three outcomes and `blocked_ratio = struct_alone / (struct_alone + legacy_fired)`;
- for each `struct_alone` bar while a position was open (join against recorded trade pairs where available): the subsequent realized exit reason and pnl, so the report shows what actually happened to trades that a standalone structural exit would have closed earlier;
- dead-factor confirmation: occurrence count of `背驰V260615_失效` over the full replay (expected `0`, cross-checking H3 with the exit-consumer context).

Both outputs carry `Diagnostic only, not a trading recommendation.` Missing DB coverage is marked `unavailable` per symbol, never silently passed (same rule as A35).

---

## 4. Phase 1: Dead-Factor Removal (behavior-neutral)

Change:

- delete factor "方向反转且在中枢内" from 二买平多 (`positions.py:685-694`);
- delete the corresponding factor from 二卖平空 (`positions.py:946-954`);
- mark the `失效` branch in `signal_divergence_status` (`signals.py:268-280`) with a docstring note: "classification currently unreachable on real data (H3); exit consumers removed in A37; repair-or-delete decision deferred". Do not change its logic in this task.

Equivalence proof (acceptance-blocking):

1. Phase 0 report shows `背驰V260615_失效` count `= 0` on the replayed real-data window.
2. A before/after backtest replay on at least 2 symbols × 1 year of real data produces **identical trade pairs** (same open/close dt, price, reason). Reuse the `trade_difference_attribution.py` comparison pattern; the diff must be empty.
   **Short-side leg is mandatory:** the baseline has `enable_short=False` (`config.py:23`), so a default replay never exercises the 二卖平空 path and would vacuously "prove" the 二卖 removal safe. Add one replay leg with `enable_short=True` (research mode, at least 1 symbol × 1 year) whose before/after diff must also be empty.
3. Unit tests updated: the removed factors no longer appear; existing coverage-closure tests that fabricated consecutive same-direction BIs to reach the dead branch are updated or removed, and a domain invariant "confirmed BI directions must alternate" is asserted in the shared test fixtures (closes the fixture loophole noted in the 2026-07-03 audit, H3).

---

## 5. Phase 2: Restructured Exit Semantics (config-gated, default OFF)

Add to `STRATEGY_CONFIG` (`config.py`):

```python
"exit_event_semantics": "legacy",   # "legacy" | "restructured"; research switch, baseline unchanged
```

The six position factories read the switch. `legacy` emits exactly the current events (after Phase 1 removal). `restructured` emits, per position, **two independent exit events**:

1. **结构性平仓** — event-level `signals_any` = [`结构失效`] (一买平多 also keeps `震荡超限`), `factors` = [] so it fires standalone;
2. **方向反转平仓** — the existing directional factor(s) promoted to their own event with no `signals_any` gate.

Zhongshu-mode unification (restructured mode only): `结构失效` must be evaluated against the **recent**-mode center so it refers to the same structure as the position/direction factors. Implementation: add a parallel signal `{freq}_D1BSP_风控RV260615` (and `空头风控RV260615`) computed with `mode="recent"` and the unchanged `stop_loss_pct=0.05`; `震荡超限` stays on `segment` mode (its BI-counting rationale in `signals.py:694-696` still holds). Legacy signal keys are untouched. `validation.py` exhaustiveness sets must include the new keys.

Rationale for the two-event (OR) structure: it restores the **documented** exit intent — `signal_risk_control` promises "两者并存，先触发者执行" (`signals.py:682-683`) and the 三买 rule "回落入中枢即离场" — rather than optimizing anything on historical data. The choice is traceability-driven, not performance-driven.

Known risk (must be stated in the implementation report): confirmed BI directions strictly alternate, so a standalone directional event ("方向向下 ∧ 中枢内/下方") may fire far more often than under legacy AND, where `结构失效` gated it. Its true standalone frequency is unknown precisely because legacy never let it fire alone; Phase 0's `factor_alone` count quantifies this on the old window for mechanism understanding only.

Rules:

- the numeric threshold `0.05` is copied, not tuned;
- the switch default stays `legacy` in this task; flipping the default is a separate future promotion decision;
- backtest reports must print the active `exit_event_semantics` value in the header (same transparency rule as the M1 cost fix).

---

## 6. Validation and Promotion Discipline

- Old window (before 2026-04-24): only behavior-difference replays (exit-reason distribution shift, trade diff counts) are allowed, for mechanism understanding. No metric from this window may be used to select the switch value, thresholds, or event structure variants.
- Decision data: 2026-04-24+ incremental data and SimNow shadow observation (existing `simnow_*` tooling) with `restructured` running in research mode alongside the `legacy` baseline.
- Success is measured structurally, not by returns: the share of losing trades exiting via structural events instead of `stop_loss` should rise, and average loss per losing trade should not worsen. Any report stating results must carry the RESEARCH-ONLY banner; `GOAL PASSED` is forbidden.
- **Non-promotion (kill) criterion:** if `restructured` mode materially degrades holding structure on the new-data window — e.g. the directional standalone event dominates exits and median holding time collapses versus `legacy` (recall: trades holding 121-300 bars were the only profitable duration bucket) — the switch stays `legacy` and the finding is recorded as negative evidence. Churn explosion is a rejection outcome, not a tuning target.

---

## 7. Testing Plan

- Phase 0: pure-function tests for the three-way event evaluation; unavailable-DB handling; JSON/MD rendering; no `GOAL PASSED`; no trading-interface tokens (`send_order`, `cancel_order`, `buy(`, `sell(`, `short(`, `cover(`).
- Phase 1: trade-pair equivalence test (before/after removal, empty diff); fixture invariant "BI directions alternate"; full unit suite passes.
- Phase 2: factory tests asserting `legacy` emits identical event structures to Phase 1 output; `restructured` emits the two-event structure; new signal keys registered in `validation.py`; engine header prints the switch; full suite green:

```powershell
python -m pytest examples\czsc_strategy\tests\unit -q -m "not realdb"
python tools\sync_check.py
python tools\sync_check.py --root examples\czsc_strategy
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

---

## 8. Review Checklist

Reject if:

- any phase is implemented out of order, or Phase 2 ships before the Phase 1 equivalence diff is empty;
- baseline behavior changes with `exit_event_semantics="legacy"` (trade-pair diff non-empty);
- any threshold is retuned, or any selection is justified by pre-2026-04-24 metrics;
- `signal_risk_control` legacy keys change meaning, or `validation.py` exhaustiveness is left stale;
- SimNow order/cancel paths are touched; any report claims `GOAL PASSED`;
- the dead `失效` branch is "fixed" opportunistically in the same task (that is a separate decision).

Accept if:

- Phase 0 reports exist with blocked-exit counts per event and symbol;
- Phase 1 equivalence proof is machine-checkable and green;
- Phase 2 switch defaults to `legacy` and both structures are unit-tested;
- tests, sync_check (both roots), and preflight pass; handoff advances with stage/owner updated.

---

## 9. Dev Handoff Prompt

```text
Read HANDOFF.md and docs/design/a37-exit-event-restructure.md. Implement A37 in phase order.

Phase 0: add examples/czsc_strategy/diagnostics/exit_event_reachability_report.py (+ unit tests). Replay real bars, count legacy_fired / struct_alone / factor_alone per exit event, confirm 背驰V260615_失效 count is 0, emit JSON+MD with the standard disclaimer, mark missing DB data unavailable.

Phase 1: remove the two dead exit factors (positions.py 二买平多 "方向反转且在中枢内", 二卖平空 counterpart). Prove equivalence: empty before/after trade-pair diff on >=2 symbols x 1 year, plus updated tests with a "BI directions alternate" fixture invariant.

Phase 2: add STRATEGY_CONFIG["exit_event_semantics"] ("legacy" default). In "restructured" mode emit standalone structural-exit events plus standalone directional-exit events, with 结构失效 computed from a new recent-mode signal 风控RV260615 / 空头风控RV260615 (stop_loss_pct=0.05 copied, not tuned). Register new keys in validation.py. Print the active switch in backtest report headers.

Do not tune parameters, do not use pre-2026-04-24 data for selection, do not touch SimNow order/cancel interfaces, do not claim GOAL PASSED, do not modify Position stop/trailing/timeout logic or BacktestEngine ordering.

Run:
- python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
- python tools/sync_check.py
- python tools/sync_check.py --root examples/czsc_strategy
- powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
- python tools/handoff.py next --summary "A37 exit-event restructure implemented (phases 0-2)"
```
