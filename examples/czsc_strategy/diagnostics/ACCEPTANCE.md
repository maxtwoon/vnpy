# ACCEPTANCE - SimNow Observation Gates

This file defines the gates for moving from historical validation to SimNow observation readiness.

## Hard Safety Gates

- No automatic order placement. A formal capture must declare `meta.read_only=true`, `meta.orders_sent_by_workflow=0`, and an empty `meta.workflow_order_actions` list.
- Private config files and generated SimNow artifacts must remain git-ignored.
- All scripts must run from `D:\repo\vnpy` or resolve paths to absolute paths before VeighNa changes the runtime directory.
- A failure must produce an actionable message and non-zero exit code.

## Daily Observation Gates

A valid daily observation requires:

- SimNow read-only connection succeeds.
- Contract query succeeds.
- All enabled contracts in `simnow_contract_map.json` are subscribed.
- If any enabled research symbol is missing from `raw.subscribed`, the day must remain `pending` with reason `subscription_incomplete`.
- The capture JSON contains top-level keys: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- `raw.contracts_count > 0`.
- `raw.ticks` must be non-empty for a valid observation. If the connection/query snapshot is present but no ticks arrive, the day must be `skipped` with reason `simnow_no_ticks`.
- The kline update JSON is created from the same SimNow capture.
- Every enabled research symbol has at least one captured 1M bar for the observation date.
- If any enabled symbol is missing from `simnow_kline_update_YYYY-MM-DD.json`, the day must remain `pending` with reason `kline_coverage_incomplete`.
- Each enabled research symbol must meet the configured minimum 1M bar coverage threshold (`run_next_work.ps1 -MinKlineBarsPerSymbol`, default `30`).
- If any enabled symbol has fewer than the configured minimum bars, the day must remain `pending` with reason `kline_coverage_too_short`.
- `run_next_work.ps1 -LiveCapture` must reject `DurationSeconds < MinKlineBarsPerSymbol * 60` unless `-SkipKlineUpdate` is explicitly used for a non-observation smoke test.
- No unexpected orders are sent by the observation workflow. If `order_safety.status=halt`, the day must halt with reason `workflow_order_safety_breach`.
- Post-close replay JSON is available for the same trading day.
- SimNow and replay event surfaces are consistent:
  - signal direction consistency: 100%
  - position direction consistency: 100%
  - trade direction consistency: 100%

## Risk Gates

Use `simnow_risk_thresholds.json` as the single source for SimNow observation warning/halt lines.
The file is derived from the latest accepted historical/precheck report and must be reviewed whenever the candidate changes.

Initial reference thresholds:

- max single-day loss warning: around `-0.29%`
- max drawdown warning: around `-1.32%`
- max gross exposure warning: around `28%`
- multi-long-short same-symbol count: must be explained if non-zero
- top symbol concentration: must not breach configured threshold
- top sub-strategy concentration: must not breach configured threshold

## Daily Report Requirements

The daily `simnow_20d_observation_report.md` must contain an `## Action Summary` section that maps each observed date to:

- `date`: observation date.
- `status`: daily status (`pass`, `pending`, `skipped`, `halt`).
- `reason`: the primary skip/pending/halt reason.
- `severity`: recommendation severity (`ok`, `info`, `medium`, `warning`, `critical`).
- `action`: a concrete, human-readable next step tied to the reason tier.
- `counts_for_20d`: whether the row qualifies as a valid observation day.

Reason-tiered action examples:

- `skipped/simnow_no_ticks`: explain possible holiday/off-session/no-data cause and suggest re-running at the next valid session.
- `skipped/ctp_disconnect_097_no_snapshot`: explain CTP connection failure and suggest checking SimNow service, network, and account status.
- `pending/historical_db_lag`: explain historical DB coverage gap and suggest waiting or executing replay backfill.
- `pending/subscription_incomplete`: list missing symbols and suggest checking `simnow_contract_map.json` and subscription results.
- `pending/kline_coverage_incomplete`: list missing symbols and suggest re-collecting during an active trading session.
- `pending/kline_coverage_too_short`: list short symbols and the configured minimum bars, and suggest extending capture duration.
- `halt/workflow_order_safety_breach`: state that the observation workflow appears to have placed orders and must be stopped for manual review.
- `halt/threshold_breach`: list the risk metrics that triggered warning/halt lines.
- `pass/valid_observation=true`: confirm the day counts toward the 20-day gate.
- `pass/valid_observation=false`: list the remaining gate gaps even though the daily status is `pass`.

## 20-Day Promotion Gate

The candidate can be considered for broader SimNow simulation only after:

- at least 20 valid trading-day rows exist in `simnow_observation_ledger.jsonl`;
- `valid_observation_days >= 20` in both the daily observation report and promotion decision report;
- every valid day has consistency status `matched`;
- no hard safety gate is breached;
- no risk fuse line is breached;
- all anomalies have written attribution in the daily report.
