# Risk Note: 888 Continuous Contract is a Raw Splice

**Scope:** All backtests and diagnostics under `examples/czsc_strategy` that use `{symbol}888_1M_raw` tables.

**Status:** `found_spliced` (confirmed by `diagnostics/audit_issue_diagnostics.py`).

## What we know

- The raw 888 continuous-contract tables are a **multi-contract splice**: the underlying contract changes at each rollover.
- The raw tables carry a **`real_symbol` column** (e.g. `sc888_1M_raw.real_symbol = "sc2202"`), and that column changes at each rollover. This makes rollover transitions detectable **exactly** from `real_symbol`.
- No column, table, or metadata in the database indicates a back-adjustment, front-adjustment, or spread-smoothing step.

## What we do NOT do

- **No cross-rollover price adjustment** is applied to live bars used by the strategy or backtest engine.
- **No gating** of live opens around rollover days is applied.
- The rollover window is **only excluded in read-only diagnostics** (e.g. `diagnostics/rollover_exclusion_report.py`) to measure its pollution impact; it is not removed from production signal paths.

## Consequences

- Rollover gaps are read as real price moves by the 笔/分型/中枢 machinery and can produce fake breakouts, fake gap stops, and fake divergence signals.
- `SC888` is the worst-performing, most parameter-sensitive symbol in the current universe, consistent with the largest rollover spreads.

## Evidence

- `diagnostics/audit_issue_diagnostics.py` — H4 continuous-contract audit.
- `diagnostics/rollover_exclusion_report_*.json` and `diagnostics/rollover_exclusion_report_*.md` — before/after metrics when rollover windows are excluded.

## RESEARCH-ONLY

This note and the associated diagnostics are **research-only** and do not constitute a trading recommendation. Any decision to adjust live prices or gate trades around rollovers must be made separately and validated out-of-sample.
