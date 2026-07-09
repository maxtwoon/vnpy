# A38 Phase 1 - Stop Execution Model Cross-Check (2026-07-09)

Diagnostic only, not a trading recommendation.

**Task:** A38 Phase 1 - `stop_execution_model` `"close"` vs `"intrabar"`.
**Window:** 2024-01-01 ~ 2024-12-31. **`stop_penalty_bp`:** 0.
**Reproduce:** `python diagnostics/stop_execution_model_crosscheck.py`
(reads the local SQLite DB; read-only).

## 1. Close-model byte-identical to baseline (equivalence gate)

Method: `git stash` the three changed source files
(`config.py` / `positions.py` / `backtest_engine.py`), run the baseline close-model,
then diff the close-model stats (`stop_trades`, `worst_loss_pct`, `max_overshoot_x`,
`total_return_pct`, `total_trades`).

| Symbol | Leg | close byte-identical vs baseline |
|---|---|---|
| sc888 | long | PASS |
| rb888 | long | PASS |
| sc888 | enable_short=True | PASS |

Also unit-proven by `test_close_model_byte_identical_with_and_without_bar_extremes`
and `test_close_model_ignores_intrabar_low`.

## 2. Intrabar bounds the stop-loss tail (A35 cross-check direction)

| Symbol / leg | worst loss (close -> intrabar) | max overshoot x (close -> intrabar) |
|---|---|---|
| sc888 long | -3.965% -> -3.570% | 1.410x -> 1.406x |
| rb888 long | -3.684% -> -3.570% | 1.305x -> **1.099x** |
| sc888 short | **-5.545% -> -3.570%** | **2.773x -> 1.406x** |

The short leg is the clearest: a close-based stop overshot the 2% nominal by 2.77x
(-5.55%); intrabar caps it near nominal (1.41x, -3.57%). Direction matches the A35
`stop_loss_stress_report_2026-07-04` `intrabar_trigger` scenario (tail bounded closer
to the nominal stop).

## 3. Honest caveat

Intrabar triggers earlier (on the bar low/high piercing the stop), so it can raise
stop frequency and slightly worsen net return in some symbol/windows
(e.g. sc888 long -1.034% -> -1.310%). This is why the switch **defaults to `close`**
and enabling `intrabar` is a measured decision, not an automatic improvement. No
threshold was tuned; no pre-2026-04-24 data selected any parameter.
