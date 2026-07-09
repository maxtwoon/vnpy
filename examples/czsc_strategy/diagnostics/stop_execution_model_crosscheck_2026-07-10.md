# A38 Phase 1 - A35 vs A38 Intrabar Cross-Check (2026-07-10, well-posed)

Diagnostic only, not a trading recommendation.

**Task:** A38 Phase 1 - `stop_execution_model` A35 `intrabar_trigger` model vs A38 intrabar fill.
**Window:** 2022-01-01 ~ 2024-12-31. **Population:** `一买多头` (long, 200bp) stop-loss trades.
**Reproduce:** `python diagnostics/stop_execution_model_crosscheck.py` (reads local SQLite DB).

## Why this shape (design 2.5, revised after the 2026-07-10 review)

A35 `scenario_intrabar_trigger` fills a touched stop **at the trigger** (never overshoots).
A38 fills at **`min(trigger, close)`** (long) / `max(trigger, close)` (short) - deliberately more
conservative on a gap-through bar. They are different fill models, so blanket numeric agreement is
ill-posed. This cross-check instead runs **both models on the same stop-loss population** at the
engine's 30m trade-bar granularity, reusing A35's `scenario_intrabar_trigger` (via a 30m loader)
and `_scenario_summary` (so the metric definitions are A35's), and checks two properties.

## Close-model equivalence (byte-identical baseline)

Separately proven by a `git stash` before/after diff of the three source files, running the
baseline close-model and diffing `stop_trades / worst_loss_pct / max_overshoot_x /
total_return_pct / total_trades` (window 2024): **PASS** on sc888 (long), rb888 (long), sc888
(`enable_short=True`) - all equal. Also unit-proven by
`test_close_model_byte_identical_with_and_without_bar_extremes`.

## Result (A35 vs A38 intrabar, same population)

| Symbol | stop trades | A35 worst / overshoot / maxx | A38 worst / overshoot / maxx | non-gap exact (tol 1e-6) | gap trades | gap invariant A38>=A35 loss | pass |
|---|---:|---|---|:--:|---:|:--:|:--:|
| sc888 | 22 | -2.00% / 0 / 0.0 | **-4.599% / 14 / 2.299** | yes (max diff 0.0) | 14 | yes | **PASS** |
| rb888 | 14 | -2.00% / 0 / 0.0 | **-2.394% / 9 / 1.197** | yes (max diff 0.0) | 9 | yes | **PASS** |

Metrics (`worst_loss_pct` / `overshoot_count` / `max_overshoot_multiple`) are computed by A35's
own `_scenario_summary` for both models.

## Interpretation

- **Convergence proof:** on every non-gap trade the A38 fill equals the A35 fill to `1e-6`
  (`max_non_gap_exit_diff = 0.0`). Two independent implementations of the touch-trigger agree,
  which validates the live `Position._stop_fill` math.
- **The modeling improvement:** A35's fill-at-trigger reports `overshoot_count = 0` (it cannot
  overshoot by construction). A38 fills at the worse close on gap-through bars, so it surfaces the
  real tail: 14 (sc888) / 9 (rb888) gap trades with `overshoot_count` and `max_overshoot_multiple`
  up to 2.30x. This is the point of Phase 1 - the close-based model was hiding gap risk.
- **A35 full-sample reference:** the committed `stop_loss_stress_report_2026-07-04.json`
  `intrabar_trigger` scenario is itself `unavailable` (A35's 1-minute `BarLoader` cannot reach the
  per-symbol tables in this DB), so the numeric reference is A35's scenario **functions** re-run
  with a working 30m loader on the same population, not the stale JSON values.

## Guardrails

No stop threshold tuned; no pre-2026-04-24 data selected any parameter; RESEARCH-ONLY; makes no
promotion / pass claim; no SimNow order path touched.
