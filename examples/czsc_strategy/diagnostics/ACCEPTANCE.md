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

The promotion decision report (`simnow_20d_promotion_decision.md`) must also contain an `## Action Summary` section with the same columns and reason-tiered actions as the daily report, so the promotion gate is reviewed with executable next steps rather than only a blocker list. Both reports source their Action Summary from the shared `simnow_action_summary.py` module so the daily report and promotion decision stay aligned.

## Run Summary Artifact

Every formal `-LiveCapture` run must produce a machine-readable summary at `simnow_run_summary_YYYY-MM-DD.json` in the output directory. The summary is generated by `simnow_run_summary.py`, which only reads existing daily artifacts and the formal ledger; it does not connect to SimNow, send orders, or access private config files.

The summary must expose enough information for an external automation platform to determine:

- whether the day is a valid observation (`record.valid_observation`);
- the daily status and primary reason (`record.status`, `record.reason`);
- SimNow environment capture status (`environment_capture`), including tick count, contract count, subscription count, read-only flag, and workflow order count;
- account contamination status (`account_contamination`), including external orders/trades/active positions captured from the SimNow account;
- delayed replay status (`delayed_replay`), including replay availability, DB lagged symbols, replay event counts, and replay-only risk source;
- kline coverage gaps (`kline.missing_symbols`, `kline.short_symbols`);
- risk threshold status (`record.threshold_status`);
- promotion readiness (`promotion.ready_to_expand`, `promotion.valid_observation_days`, `promotion.promotion_blockers`, `promotion.top_blocking_actions`).
- 20-day observation progress (`ledger_summary`) when available, including `valid_observation_days`, `consecutive_valid_days`, `ready_to_expand`, `promotion_blockers`, `reason_counts`, `latest_action`, and `next_action`.
- automation-platform status (`automation_status`), exit code (`automation_exit_code`), reason (`automation_reason`), and recommended action (`automation_action`).

Delayed replay accounting semantics:

- The local historical DB is the only strategy market-data source for strategy PnL.
- Strategy PnL comes only from delayed replay / the local virtual ledger.
- SimNow account balance, floating PnL, raw orders, raw trades, and raw positions are audit evidence only and must not be used as strategy PnL.
- A `valid` day means the delayed replay observation gates passed; it is not real SimNow order/trade reconciliation while the workflow remains read-only.

Automation status semantics:

- `valid` → exit code `0`: the day counts toward the 20-day gate.
- `skipped` → exit code `10`: no actionable data; re-run at the next valid session.
- `pending` → exit code `20`: an observation gate must be resolved before the day can count.
- `halt` → exit code `30`: stop automation and review manually.
- `failed` → exit code `40`: missing critical artifact or unknown status.

The recurring daily automation prompt (`AUTOMATION_PROMPT.md`) must treat the run summary as the single authoritative source for the final daily conclusion. The agent must read `automation_status`, `automation_exit_code`, `automation_reason`, and `automation_action` from `simnow_run_summary_YYYY-MM-DD.json` and must not require parsing multiple markdown reports to decide the daily outcome.

A daily brief generator (`simnow_daily_brief.py`) may be used to convert the run summary JSON into a fixed-format Chinese brief (`simnow_daily_brief_YYYY-MM-DD.md`) for the automation agent to copy into its daily report. The generator is read-only, does not connect to SimNow, and does not access private config.

A formal `run_next_work.ps1 -LiveCapture` run must generate the daily brief after the run summary. The brief must be produced in the same output directory as `simnow_run_summary_YYYY-MM-DD.json` and must reflect the same automation status, reason, and action.

The daily brief must also include a `## 20 日进度` section rendered from `ledger_summary` in the run summary JSON when available, showing `valid_observation_days`, `consecutive_valid_days`, `ready_to_expand`, and `promotion_blockers`.

The summary must never contain account IDs, passwords, auth codes, API keys, or the full masked broker setting object.

The run summary JSON embeds a safe aggregate copy of `simnow_ledger_summary.json` under `ledger_summary`. When the ledger summary file is missing, `ledger_summary.available` must be `false` and the summary must still be valid. External automation consumers may therefore read only `simnow_run_summary_YYYY-MM-DD.json` for both the daily conclusion and 20-day progress.

## Historical DB Update Artifact

The formal wrapper supports an optional pre-capture historical replay DB update through `run_next_work.ps1 -LiveCapture -UpdateHistoricalDb`. This step is read-only with respect to SimNow and must run before the SimNow capture when enabled.

Every formal `-LiveCapture` run must write `simnow_historical_db_update_YYYY-MM-DD.json`:

- when `-UpdateHistoricalDb` is set and the update command succeeds, the artifact must report `status=passed`, `exit_code=0`, and `started_at` / `ended_at`;
- when `-UpdateHistoricalDb` is not set, the artifact must report `status=skipped` and explain that the switch was not set;
- when the update command fails, the wrapper must write the failure artifact and stop before the SimNow capture; that run must not count as a valid observation day.

`simnow_run_summary_YYYY-MM-DD.json` must include a safe `historical_db_update` section with at least `status`, `exit_code`, `started_at`, and `ended_at`. The daily brief must include the same historical DB update status for human review. The update command must not contain secrets, and the run summary sensitive-data scanner must still reject passwords, auth codes, API keys, account IDs, or masked broker settings.

## External Automation Consumers

External automation consumers must treat `simnow_run_summary_YYYY-MM-DD.json` as the single machine-readable source of truth for both daily status and 20-day progress.

`simnow_daily_brief_YYYY-MM-DD.md` is the human-readable report artifact. It may be copied or summarized into the automation agent's daily report, but it must not be used as the machine-readable source of truth.

The observation report (`simnow_20d_observation_report.md`), promotion decision report (`simnow_20d_promotion_decision.md`), and ledger summary (`simnow_ledger_summary.json`) may be used for troubleshooting and deeper inspection, but they must not be used as the final source for deciding the daily automation status or 20-day promotion readiness.

## Ledger Summary Artifact

A ledger summary generator (`simnow_ledger_summary.py`) must produce a machine-readable aggregate summary at `simnow_ledger_summary.json` by reading only the formal observation ledger. It must not connect to SimNow, access private config, or send orders.

The ledger summary must expose:

- `generated_at`, `min_days`, `observation_start_date`, `excluded_before_start_count`, `total_rows`;
- `valid_observation_days`, `pending_days`, `skipped_days`, `halt_days`, `failed_days`;
- `latest_date`, `latest_valid_date`, `consecutive_valid_days` (trailing consecutive valid trading-day ledger rows; weekends/holidays do not break the streak);
- `ready_to_expand` (true only when `valid_observation_days >= 20` and no pending/skipped/halt/failed days);
- `promotion_blockers` including at least:
  - `need_N_more_valid_observation_days`
  - `pending_days_present`
  - `skipped_days_present`
  - `halt_days_present`
  - `failed_days_present`
- `reason_counts` derived from the shared `_record_reason` / action summary logic;
- `automation_status_counts`;
- `latest_record` with safe summary-level fields only;
- `latest_action` from `build_action_summary([latest_record])`;
- `next_action` mapped from the latest automation status.

The ledger summary must never contain account IDs, passwords, auth codes, API keys, raw capture payloads, or the full masked broker setting object.

A formal `run_next_work.ps1 -LiveCapture` run must regenerate `simnow_ledger_summary.json` after the observation ledger is written and before the promotion decision, run summary, and daily brief artifacts are generated.

## 20-Day Promotion Gate

The formal 20-day observation window is controlled by `simnow_observation_window.json`.
Rows before `observation_start_date` remain in `simnow_observation_ledger.jsonl` as audit history, but must be excluded from ledger summary, daily observation report, and promotion decision statistics.

The candidate can be considered for broader SimNow simulation only after:

- at least 20 valid trading-day rows exist on or after the configured `observation_start_date`;
- `valid_observation_days >= 20` in both the daily observation report and promotion decision report;
- every valid day has consistency status `matched`;
- no hard safety gate is breached;
- no risk fuse line is breached;
- all anomalies have written attribution in the daily report.

## Audit Issue Diagnostics

A read-only diagnostic report (`audit_issue_diagnostics_YYYY-MM-DD.json` and `audit_issue_diagnostics_YYYY-MM-DD.md`) must be available to quantify the H1/H2/H3/H4/M1 findings from `AUDIT_REPORT_YYYY-MM-DD.md`.

The diagnostic script must cover:

- **H1** — detect weight-like parameters with more than one decimal place; automatically collect evidence from diagnostics filenames and text (`sc_short_weight*`, `portfolio_goal_expanded_short_sc*`, `platform_optimization_round*`).
- **H2** — measure stop-loss overshoot when actual loss percentages exceed the nominal stop-loss percentage; automatically scan diagnostics JSON files for stop-loss trade records.
- **H3** — check whether the `背驰V260615_失效` signal classification is ever observed in the signal history; automatically scan diagnostics JSON files for signal records.
- **H4** — inspect DB/table metadata for continuous-contract rollover/adjustment evidence; automatically list diagnostics files that discuss continuous contracts when no DB metadata is provided; report `unknown` or `unavailable` when metadata is missing.
- **M1** — compare commission/slippage across `BACKTEST_CONFIG`, engine defaults, and position defaults; automatically introspect `chan_strategy/config.py`, `backtest_engine.py`, and `positions.py` when no explicit cost inputs are provided; flag any inconsistency and recommend `BACKTEST_CONFIG` as the single source of truth.

The diagnostic scripts and their tests must:

- remain read-only and never call `send_order`, `cancel_order`, `buy`, `sell`, `short`, or `cover`;
- never leak passwords, auth codes, API keys, account IDs, or masked broker settings;
- mark issues as `unknown` or `unavailable` when required input evidence is missing;
- never present the diagnostic output as `GOAL PASSED` or as proof of profitability;
- write outputs only to `examples\czsc_strategy\diagnostics`.
