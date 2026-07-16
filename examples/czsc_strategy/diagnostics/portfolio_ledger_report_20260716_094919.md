# Portfolio Margin/PnL Ledger Report (Phase 1)

**Generated at:** 2026-07-16T09:55:58.313182+00:00
**Window:** 2022-01-01 ~ 2026-04-24
**Symbols:** AP888, RB888, SC888, A888, ZN888
**Initial capital:** 1,000,000.00

> <!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> This report was produced using the historical out-of-sample window `2022-01-01~2026-04-24`, which was repeatedly used for parameter selection. High-precision weights such as `0.847` and any bare `GOAL PASSED` rows are gate-fitting signatures, not evidence of a robust trading discovery. This artifact is retained as negative / contaminated evidence only.
>
> - `is_promotion_evidence`: False
> - `research_only`: True
> - `used_data_windows`: `["2022-01-01~2026-04-24"]`
> - `decision_data_windows`: ['2026-04-24~present', 'SimNow observation']
> - `note`: Future validation must use post-2026-04-24 incremental data and SimNow observation before any promotion claim can be considered.

## Methodology

- Each symbol is run independently through its own ``BacktestEngine`` with ``sizing_model='risk'``.
- Portfolio-level figures are aggregated by timestamp across the per-symbol ``equity_curve`` entries.
- Realized currency PnL is the sum of closed-trade ``pnl_currency`` values from ``strategy.get_combined_trades()``.
- Cluster breakdowns reuse ``STRATEGY_CONFIG['corr_clusters']``; no new clustering mechanism is introduced.
- **This is a measurement-only aggregation of independent per-symbol runs, NOT a true joint/coordinated portfolio replay.**

## Portfolio Summary

- **Total realized currency PnL:** -65,463.57
- **Max portfolio total open margin:** 64,913.25
- **Final portfolio total open margin:** 0.00
- **Max margin utilization:** 6.49%

## Per-Symbol Breakdown

| Symbol | Trades | Realized PnL | Max Margin | Final Margin |
|--------|-------:|-------------:|-----------:|-------------:|
| AP888 | 73 | 33,595.59 | 34,807.50 | 0.00 |
| RB888 | 43 | -74,395.27 | 20,116.00 | 10,825.50 |
| SC888 | 0 | 0.00 | 0.00 | 0.00 |
| A888 | 48 | -15,113.73 | 22,824.00 | 0.00 |
| ZN888 | 78 | -9,550.17 | 22,413.75 | 0.00 |

## Per-Cluster Breakdown

| Cluster | Symbols | Max Margin | Final Margin |
|---------|---------|-----------:|-------------:|
| industrial_energy | RB888, SC888, ZN888 | 37,012.75 | 0.00 |
| _uncategorized | AP888, A888 | 42,749.50 | 0.00 |

## Ledger Sample

The full timestamp-level ledger contains 19470 rows. The first and last rows are shown below.

| Timestamp | Total Open Margin | Margin Utilization |
|-----------|------------------:|-------------------:|
| 2022-01-11 13:59:00 | 0.00 | 0.00% |
| 2026-04-24 23:59:00 | 0.00 | 0.00% |

## Manual Verification

Run the report natively and inspect the generated JSON/Markdown files:

```bash
python diagnostics/portfolio_ledger_report.py --verbose
```

Counts from the report run:

- Symbols run: 5
- Portfolio ledger rows: 19470
- Total realized currency PnL: -65,463.57
- Max margin utilization (%): 6.49

