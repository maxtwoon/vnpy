# A35 Design: Stop-Loss Stress Diagnostics

**Task:** Design a read-only diagnostic that quantifies stop-loss overshoot under realistic stress assumptions.

**Scope:** Diagnostic only. Do not change trading logic, stop-loss execution, strategy parameters, SimNow connectivity, gateway interfaces, order submission, or cancellation paths.

---

## 1. Background

A34 closed the methodology cleanup for M1 and H1. The next unresolved high-risk audit item is H2: fixed stop-loss checks are performed at the bar-close price. The current evidence shows observed stop-loss losses can be much larger than the nominal stop budget:

- nominal example: `300bp` / `-3.0%`;
- observed worst stop-loss loss: about `-12.60%`;
- observed max overshoot multiple: about `4.20x`;
- observed overshoot count: `12`.

This is a risk-measurement problem before it is an execution-rule problem. The project needs a reproducible report that answers: how bad are stop-loss exits under the current model, and how much would the numbers change under intrabar trigger, gap-open, and penalty-slippage assumptions?

---

## 2. Design Goals

The diagnostic must:

1. Preserve the current strategy behavior as the baseline.
2. Recompute stop-loss stress scenarios without mutating strategy code or report history.
3. Make missing data explicit instead of silently passing.
4. Produce machine-readable JSON and human-readable Markdown.
5. Be deterministic enough for unit tests and review.

The diagnostic must not:

- tune stop-loss thresholds;
- change `Position._check_stop_loss`;
- change `BacktestEngine.run`;
- change SimNow order/cancel/trading interfaces;
- claim profitability or `GOAL PASSED`;
- overwrite historical reports.

---

## 3. Proposed Artifact

Add:

- `examples/czsc_strategy/diagnostics/stop_loss_stress_report.py`
- `examples/czsc_strategy/tests/unit/test_stop_loss_stress_report.py`

Generate:

- `examples/czsc_strategy/diagnostics/stop_loss_stress_report_YYYY-MM-DD.json`
- `examples/czsc_strategy/diagnostics/stop_loss_stress_report_YYYY-MM-DD.md`

Both reports must include:

```text
Diagnostic only, not a trading recommendation.
```

---

## 4. Inputs

### Baseline Stop-Loss Pairs

Primary source:

- scan existing diagnostics JSON files for stop-loss trade records, reusing or mirroring `collect_stop_loss_pairs_from_diagnostics()` from `audit_issue_diagnostics.py`.

Minimum fields:

- `symbol`
- `strategy`
- `open_dt`
- `close_dt`
- `pnl_pct`
- `exit_reason` or `reason_code`
- `source_file`

Some existing records do not contain `open_price` or `close_price`; the baseline scenario must still work from `pnl_pct`.

### Optional K-Line Data

For intrabar/gap scenarios, the script may load 1M or trade-frequency bars from the configured SQLite DB.

Required bar fields:

- `dt`
- `open`
- `high`
- `low`
- `close`

If DB path is absent, the table is missing, or a trade window cannot be reconstructed, mark the affected scenario as `unavailable` with a reason. Do not drop the trade silently.

---

## 5. Stress Scenarios

### Scenario A: `observed_close`

This is the baseline from existing pair records.

For each stop-loss pair:

- use the recorded `pnl_pct`;
- compare against the nominal stop-loss percentage;
- compute overshoot if `pnl_pct < -stop_loss_bp / 10000`.

### Scenario B: `intrabar_trigger`

This scenario asks whether the stop could have been triggered inside the holding window before the close-based exit.

For long trades:

- trigger level = `open_price * (1 - stop_loss_bp / 10000)`;
- trigger when any bar `low <= trigger_level`;
- stressed exit price = trigger level minus optional penalty slippage.

For short trades:

- trigger level = `open_price * (1 + stop_loss_bp / 10000)`;
- trigger when any bar `high >= trigger_level`;
- stressed exit price = trigger level plus optional penalty slippage.

If `open_price` is missing, derive it from the first bar at or after `open_dt` when DB data is available. If it cannot be derived, mark that trade as `unavailable` for this scenario.

### Scenario C: `gap_open_exit`

This scenario models overnight or session-gap risk.

For each trade, inspect the first available bar at or after the current close-based stop trigger time or the first bar after a date/session break inside the holding window. If the open price has already passed the stop level, use that open price as the stressed exit.

If session boundaries cannot be inferred from available bars, fall back to detecting time gaps larger than the expected intraday interval and mark the method in the report.

### Scenario D: `penalty_slippage`

This is an overlay rather than a separate trigger model.

For each available stressed exit:

- long stop: worsen exit by `penalty_bp`;
- short stop: worsen exit by `penalty_bp`;
- default `penalty_bp` should be conservative and configurable, for example `10bp`.

The report should show both unpenalized and penalized scenario summaries.

---

## 6. Output Schema

Top-level JSON:

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "...",
  "disclaimer": "Diagnostic only, not a trading recommendation.",
  "status": "ok|partial|unavailable",
  "stop_loss_bp": 300,
  "data_source": {
    "pairs": "diagnostics_json_scan",
    "bars": "sqlite|unavailable"
  },
  "scenarios": {
    "observed_close": {},
    "intrabar_trigger": {},
    "gap_open_exit": {},
    "penalty_slippage": {}
  },
  "worst_trades": [],
  "unavailable_trades": [],
  "notes": []
}
```

Each scenario summary must include:

- `status`
- `trade_count`
- `affected_trade_count`
- `affected_symbols`
- `worst_loss_pct`
- `overshoot_count`
- `max_overshoot_multiple`
- `avg_loss_pct`
- `sample_trades`
- `unavailable_count`
- `unavailable_reasons`

Markdown report must include:

- one executive summary table;
- one table per scenario;
- a worst-trades section;
- unavailable data section;
- explicit statement that this does not fix stop-loss logic.

---

## 7. Testing Plan

Add unit tests for pure calculations:

- long stop below open price;
- short stop above open price;
- observed close overshoot count and max multiple;
- penalty slippage worsens loss in the correct direction;
- missing `open_price` with no bars returns unavailable;
- missing DB does not silently pass;
- Markdown contains disclaimer and required metrics;
- JSON contains all required fields;
- no generated report contains `GOAL PASSED`;
- no script contains `send_order`, `cancel_order`, `buy(`, `sell(`, `short(`, or `cover(`.

Suggested test command:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_stop_loss_stress_report.py -q
```

Project preflight must still pass:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

---

## 8. Review Checklist

Reject the implementation if:

- the diagnostic changes strategy or Position behavior;
- any SimNow trading interface changes;
- missing DB/K-line data is treated as success;
- baseline overshoot metrics disappear;
- reports omit `worst_loss_pct`, `overshoot_count`, or `max_overshoot_multiple`;
- generated reports claim `GOAL PASSED`;
- stress outputs are used to tune parameters in the same task.

Accept the implementation if:

- baseline H2 remains visible;
- stress scenarios are either computed or explicitly marked unavailable;
- JSON and Markdown are generated;
- tests and preflight pass;
- handoff advances to review.

---

## 9. Dev Handoff Prompt

Use this prompt for the dev agent:

```text
Read HANDOFF.md and docs/design/a35-stop-loss-stress-diagnostics.md. Implement A35 exactly as a read-only diagnostic.

Add examples/czsc_strategy/diagnostics/stop_loss_stress_report.py and tests in examples/czsc_strategy/tests/unit/test_stop_loss_stress_report.py.

The script must generate stop_loss_stress_report_YYYY-MM-DD.json and .md, compare observed_close, intrabar_trigger, gap_open_exit, and penalty_slippage scenarios, and explicitly mark missing DB/K-line data as unavailable instead of silently passing.

Do not change Position, BacktestEngine, strategy parameters, SimNow order/cancel/trading interfaces, or historical promotion reports. Do not claim GOAL PASSED.

Run:
- python -m pytest examples/czsc_strategy/tests/unit/test_stop_loss_stress_report.py -q
- python -m pytest examples/czsc_strategy/tests/unit/test_audit_issue_diagnostics.py -q
- powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
- python tools/handoff.py next --summary "A35 stop-loss stress diagnostics implemented"
```
