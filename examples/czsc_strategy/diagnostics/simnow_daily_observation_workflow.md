# SimNow Daily Observation Workflow

This workflow promotes the final historical candidate into a 20-trading-day
SimNow observation process. The goal is not to optimize returns during this
stage; it is to verify that market data, signal generation, execution timing,
positions, fills, and attribution remain aligned with the replay/backtest
pipeline.

## Objective

Observe the final candidate for at least 20 trading days. Expansion is allowed
only when all 20 days satisfy:

- SimNow signals/trades/positions match replay output at 100%.
- Risk threshold status is not `halt`.
- No accepted baseline threshold is exceeded:
  - single-day loss
  - drawdown
  - gross exposure
  - net exposure
  - both-long-short symbol count
  - consecutive loss duration and magnitude
  - symbol top1 contribution concentration
  - strategy top1 contribution concentration

## Baseline

The threshold baseline is:

```text
examples/czsc_strategy/diagnostics/simnow_precheck_risk_report.json
```

The daily monitor derives warning and halt levels from this file:

- warning: 90% of the accepted historical baseline
- halt: baseline exceeded

## Daily Steps

1. Export the replay snapshot for the trading day under review.

```powershell
python examples\czsc_strategy\diagnostics\export_simnow_replay_snapshot.py `
  --date 2026-04-24 `
  --end 2026-04-24 `
  --out-json examples\czsc_strategy\diagnostics\replay_snapshot_2026-04-24.json
```

2. Export SimNow records into the same schema.

Expected fields:

```json
{
  "signals": [{"dt": "...", "symbol": "...", "strategy": "...", "operate": "..."}],
  "trades": [{"dt": "...", "symbol": "...", "strategy": "...", "operate": "..."}],
  "positions": [{"dt": "...", "symbol": "...", "strategy": "...", "operate": "..."}],
  "risk": {
    "daily_return_pct": -0.10,
    "drawdown_pct": -0.20,
    "gross_exposure": 0.10,
    "net_exposure": 0.10,
    "both_long_short_symbols": 0,
    "consecutive_loss": {"days": 1, "cumulative_return_pct": -0.01},
    "symbol_concentration": {"top1_abs_share": 0.20},
    "strategy_concentration": {"top1_abs_share": 0.20}
  }
}
```

3. Append the daily ledger and refresh the 20-day report.

```powershell
python examples\czsc_strategy\diagnostics\simnow_daily_monitor.py `
  --date 2026-04-24 `
  --simnow-json examples\czsc_strategy\diagnostics\simnow_export_2026-04-24.json `
  --replay-json examples\czsc_strategy\diagnostics\replay_snapshot_2026-04-24.json
```

Outputs:

```text
examples/czsc_strategy/diagnostics/simnow_observation_ledger.jsonl
examples/czsc_strategy/diagnostics/simnow_20d_observation_report.md
```

## Watch Buckets

The monitor highlights these buckets every day:

- `SC_SHORT`
- `AP_TRAILING`
- `A_TRAILING`
- `ZN_SHORT`
- `SECOND_BUY_LONG`

These are the known fragile or dominant contribution channels from the final
candidate review.

## Decision Rule

After 20 completed ledger rows:

- `ready_to_expand=True`: eligible for the next capital/symbol expansion review.
- Any `halt`: pause expansion and run attribution before the next SimNow day.
- Any consistency mismatch: fix data/export/execution alignment before trusting
  the observation day.
