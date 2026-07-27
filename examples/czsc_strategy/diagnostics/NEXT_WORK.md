# NEXT_WORK - SimNow Observation Automation

This file is the authoritative task queue for continuing the SimNow observation work.
When the user says "继续", read this file first, execute the first unfinished item,
verify it, then update `WORK_LOG.md` and this file.

## Current Stage Goal

Move the current candidate from "historical acceptance passed" to "SimNow observation ready":
record daily SimNow observations and post-close replay checks for at least 20 trading days,
with 100% consistency between SimNow and replay event surfaces and no risk-threshold breach.

## Safety Rules

- Default workflow is read-only.
- Do not send orders unless the user gives explicit written authorization in the current turn.
- Do not print or commit private SimNow config, account IDs, passwords, auth codes, or API keys.
- Treat generated SimNow JSON/ledger/report files as local artifacts only.
- If connection, account, contract mapping, or trading-session availability blocks progress, record it and ask the user only after attempting local diagnosis.

## Task Queue

| ID | Status | Task | Acceptance Evidence |
| --- | --- | --- | --- |
| A1 | DONE | Build daily run wrapper for SimNow observation | `run_next_work.ps1 -Preflight` passes; `-LiveCapture` completes the read-only workflow and creates daily capture/record/report artifacts |
| A2 | DONE | Add replay JSON production into the daily workflow | `run_next_work.ps1 -LiveCapture` exports `simnow_replay_YYYY-MM-DD.json`, passes it to monitor, and avoids false matches when replay data is unavailable |
| A3 | DONE | Freeze risk thresholds into a config file | `simnow_risk_thresholds.json` is read by monitor and daily wrapper; fallback baseline generation remains available |
| A4 | DONE | Write one formal ledger row per trading day | Ledger writes are date-idempotent upserts; repeated daily runs replace the same date instead of duplicating rows |
| A5 | DONE | Generate/update 20-day observation report | Report includes pass/pending/skipped counts, reason summaries, latest valid date, clean streak, and promotion blockers |
| A6 | DONE | Decide whether candidate can expand beyond observation | `simnow_promotion_decision.py` reads the formal ledger and `run_next_work.ps1` emits `simnow_20d_promotion_decision.md` |
| A7 | DONE | Add pending replay backfill plan | `simnow_backfill_pending_replays.py` finds `historical_db_lag` days, waits for DB coverage, and can re-run replay+monitor with `--execute` |
| A8 | DONE | Build SimNow tick-to-1M local kline update | `simnow_tick_bars.py` aggregates captured CTP ticks into `{symbol}_1M_raw` bars and `run_next_work.ps1` writes them before replay readiness |
| A9 | DONE | Promote kline coverage to a formal daily gate | Daily records store `kline_coverage`; reports show `kline_missing`; incomplete coverage stays `pending` with reason `kline_coverage_incomplete` |
| A10 | DONE | Add minimum kline coverage threshold | `run_next_work.ps1 -MinKlineBarsPerSymbol` defaults to `30`; reports show `kline_short`; short coverage stays `pending` with reason `kline_coverage_too_short` |
| A11 | DONE | Reject too-short explicit live captures for observation runs | `run_next_work.ps1` rejects explicit `DurationSeconds < MinKlineBarsPerSymbol * 60` unless `-SkipKlineUpdate` is used; formal runs compute duration from the active start window |
| A12 | DONE | Freeze the daily automation prompt | `AUTOMATION_PROMPT.md` documents the formal auto-window observation command and separates 300-second smoke tests |
| A13 | DONE | Promote subscription completeness to a formal gate | Daily records store `subscription_coverage`; reports show `subscription_missing`; missing subscriptions stay `pending` with reason `subscription_incomplete` |
| A14 | DONE | Promote read-only order safety to a formal gate | Capture exports declare `meta.read_only=true` and `orders_sent_by_workflow=0`; monitor writes `order_safety` and halts on workflow order actions |
| A15 | DONE | Add explicit valid-observation counting | Daily records include `valid_observation`; 20-day and promotion reports show `valid_observation_days`, counted only when safety, replay, kline, subscription, and risk gates all pass |
| A16 | DONE | Simplify live workflow to one formal monitor write | `run_next_work.ps1 -LiveCapture` runs `simnow_daily_monitor.py` once for the formal ledger upsert, avoiding duplicate dry-run/append monitor passes |
| A17 | DONE | Standardize no-tick captures as skipped | Connected captures with no ticks are recorded as `skipped/simnow_no_ticks`, so holidays, off-session runs, and no-market-data windows do not pollute pending replay/kline queues |
| A18 | DONE | Add action summary with reason-tiered recommendations to the 20-day report | `simnow_20d_observation_report.md` contains an `## Action Summary` table mapping each day's status/reason to a severity and actionable recommendation; unit tests cover skipped/pending/halt/pass cases |
| A19 | DONE | Sync Action Summary into promotion decision report | `simnow_20d_promotion_decision.md` reuses the same `action_recommendation`/`build_action_summary` logic and includes an `## Action Summary` table; promotion JSON stdout includes `valid_observation_days`, `action_summary_count`, and `top_blocking_actions` |
| A20 | DONE | Extract Action Summary into a standalone utility module | `simnow_action_summary.py` contains `_record_reason`, `_pass_gaps`, `action_recommendation`, and `build_action_summary`; both `simnow_daily_monitor.py` and `simnow_promotion_decision.py` import from it and no longer define/depend on each other for action summaries |
| A21 | DONE | Add machine-readable run summary JSON for `-LiveCapture` | `run_next_work.ps1 -LiveCapture` emits `simnow_run_summary_YYYY-MM-DD.json` aggregating capture/kline/record/promotion results; `simnow_run_summary.py` is a pure read-only script and its tests verify no sensitive fields leak |
| A22 | DONE | Add automation-platform status layer to run summary | `simnow_run_summary_YYYY-MM-DD.json` now contains `automation_status`, `automation_exit_code`, `automation_reason`, and `automation_action`; `classify_automation_status()` maps record status/reason to valid/skipped/pending/halt/failed |
| A23 | DONE | Freeze daily automation prompt to read run summary automation layer | `AUTOMATION_PROMPT.md` now instructs the daily automation agent to run `run_next_work.ps1 -LiveCapture` and use `simnow_run_summary_YYYY-MM-DD.json` as the authoritative source for final status and daily report fields |
| A24 | DONE | Add daily brief generator from run summary | `simnow_daily_brief.py` reads `simnow_run_summary_YYYY-MM-DD.json` and writes `simnow_daily_brief_YYYY-MM-DD.md` with a fixed Chinese format; unit tests cover valid/pending/halt/failed cases and CLI output |
| A25 | DONE | Wire daily brief into `run_next_work.ps1 -LiveCapture` | Formal `-LiveCapture` runs now generate `simnow_daily_brief_YYYY-MM-DD.md` after the run summary; preflight compiles the brief script and runs its unit tests |
| A26 | DONE | Add ledger summary generator | `simnow_ledger_summary.py` reads `simnow_observation_ledger.jsonl` and writes `simnow_ledger_summary.json` with aggregate progress, reason counts, latest action, and next action; unit tests cover empty/mixed/ready/consecutive/sensitive-data cases |
| A27 | DONE | Wire ledger summary into `run_next_work.ps1 -LiveCapture` | Formal `-LiveCapture` runs regenerate `simnow_ledger_summary.json` after the observation ledger is written and before promotion/run summary/daily brief artifacts |
| A28 | DONE | Embed ledger summary into run summary JSON | `simnow_run_summary_YYYY-MM-DD.json` contains a safe `ledger_summary` section so automation consumers only need the run summary for daily status and 20-day progress; daily brief renders a `## 20 日进度` section from it |
| A29 | DONE | Update automation prompt to run summary + daily brief split | `AUTOMATION_PROMPT.md` now instructs the daily automation agent to treat `simnow_run_summary_YYYY-MM-DD.json` as the single machine-readable source of truth and `simnow_daily_brief_YYYY-MM-DD.md` as the human-readable report source |
| A31 | DONE | Audit issue diagnostics for H1/H2/H3/H4/M1 | `audit_issue_diagnostics.py` produces `audit_issue_diagnostics_YYYY-MM-DD.json` and `.md`; tests verify H1/H2/H3/H4/M1 detection and no trading calls or sensitive data leaks |
| A32 | DONE | Wire real project inputs into audit issue diagnostics | `audit_issue_diagnostics.py` now auto-collects cost inputs from `chan_strategy` config/engine/position defaults, stop-loss pairs and signal records from diagnostics JSON, and continuous-contract evidence from diagnostics filenames; M1 and H2 are now quantified on real project data |
| A34 | DONE | Restart formal 20-day observation window from 2026-07-14 | `simnow_observation_window.json` defines `observation_start_date=2026-07-14`; ledger summary, 20-day report, and promotion decision preserve older ledger rows but exclude them from the new 20-day progress |
| A35 | DONE | Add optional historical DB auto-update to the read-only observation wrapper | `run_next_work.ps1 -LiveCapture -UpdateHistoricalDb` runs the configured DB update before capture, writes `simnow_historical_db_update_YYYY-MM-DD.json`, and run summary / daily brief expose `historical_db_update` status |
| A36 | DONE | Add risk-halt manual review pack | `simnow_risk_halt_review.py` reads `simnow_run_summary_YYYY-MM-DD.json` and writes `simnow_risk_halt_review_YYYY-MM-DD.json` / `.md` with automation status, safety snapshot, threshold diagnostics, and risk-source breakdown |
| A37 | DONE | Add risk-halt decision record template and validator | `simnow_risk_halt_decision.py` writes `simnow_risk_halt_decision_YYYY-MM-DD.json` / `.md`; defaults to `pending_decision`, requires a complete signed decision, and keeps `next_formal_observation_allowed=false` until reviewed |
| A38 | DONE | Block live capture while a risk-halt decision is pending | `run_next_work.ps1 -LiveCapture` scans prior `simnow_risk_halt_decision_*.json` files and rejects live capture before SimNow connection when any pending risk halt decision is incomplete, invalid, or not explicitly allowed |

## Commands

Preflight, no live connection:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Read-only live capture for a valid observation attempt:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Formal live capture must start inside one of the allowed Asia/Shanghai windows:
`09:05`, `13:35`, or `21:05`. Do not pass a fixed `DurationSeconds` for a formal
observation; the wrapper computes the capture length from the current formal
window to its close.

Read-only live capture with the formal historical replay DB update skipped:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -MinKlineBarsPerSymbol 30 -SkipHistoricalDbUpdate
```

Short read-only smoke test that is not eligible for a valid daily observation:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

Dry-run pending replay backfill:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_backfill_pending_replays.py
```

Execute replay backfill after the historical DB covers the pending dates:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_backfill_pending_replays.py --execute
```

## Current Known Baseline

- SimNow CTP read-only connection has passed with `柜台环境=实盘`.
- First 5-minute capture smoke passed on 2026-06-22.
- Current capture script does not send orders.
- First workflow status without replay JSON is expected to be `pending`, not `matched`.
- Replay snapshots now include `meta.replay_available`. If the historical DB has no bars for the observation day, monitor status must remain `pending` instead of treating empty replay events as a match.
- Risk thresholds are centralized in `simnow_risk_thresholds.json`. Daily monitor uses this config by default, and `run_next_work.ps1` passes it explicitly.
- Formal ledger writes are idempotent by `date`. Re-running the same day updates/replaces that day; it does not append duplicate rows.
- Pending/skipped rows are kept in the formal ledger for auditability, but promotion requires `pass` + matched consistency for all required days.
- `simnow_promotion_decision.py` is the explicit promotion gate. It reads the formal ledger and reports `ready_to_expand`, blockers, and the last valid observation date. The daily wrapper emits the promotion markdown automatically.
- `simnow_replay_readiness.py` checks whether the historical DB covers the observation date before expensive replay export.
- Current configured historical DB only covers up to `2026-04-25`, so June 2026 observations are expected to remain `historical_db_lag` until the DB is refreshed.
- Pending `historical_db_lag` days can be dry-run or backfilled with `simnow_backfill_pending_replays.py`; the command is safe by default and only mutates artifacts/ledger when `--execute` is passed.
- SimNow does not provide the missing historical minute DB automatically. The daily workflow now updates the local replay DB from actually captured SimNow ticks by aggregating them into 1M bars. This only covers the captured window and received symbols; missing ticks remain missing instead of being synthesized.
- Kline coverage is a formal daily gate. A day with missing enabled symbols is not a valid observation day and is not eligible for historical DB backfill unless the missing bars can be produced from captured SimNow ticks.
- Minimum kline coverage is configurable through `run_next_work.ps1 -MinKlineBarsPerSymbol` and defaults to `30` 1M bars per enabled symbol.
- `run_next_work.ps1` rejects live capture when `DurationSeconds < MinKlineBarsPerSymbol * 60`, unless `-SkipKlineUpdate` is used for an explicit smoke test.
- `AUTOMATION_PROMPT.md` is the copy/paste prompt for recurring Codex automation. It uses the formal auto-window observation command and keeps 300-second runs as non-observation smoke tests.
- Subscription coverage is a formal daily gate. A day with missing enabled research symbols in `raw.subscribed` remains `pending/subscription_incomplete`.
- Order safety is a formal hard gate. A capture produced by this workflow must declare `meta.read_only=true` and `meta.orders_sent_by_workflow=0`; explicit workflow order actions halt the day with `workflow_order_safety_breach`.
- `valid_observation_days` is the official 20-day progress denominator. A row counts only when `status=pass`, replay consistency is matched, thresholds pass, order safety passes, subscriptions are complete, and kline coverage is complete/non-short.
- The live wrapper performs one monitor write per run: the daily record is produced and upserted into the formal ledger in the same call.
- A capture with zero ticks is not a valid observation attempt. If the gateway produced a snapshot but no ticks, the day is recorded as `skipped` with reason `simnow_no_ticks`.
- The daily automation prompt (`AUTOMATION_PROMPT.md`) is the copy/paste prompt for recurring automation. The agent's final conclusion must come from the `automation_status`/`automation_exit_code`/`automation_reason`/`automation_action` fields in `simnow_run_summary_YYYY-MM-DD.json`, not from parsing markdown reports.
- The daily brief generator (`simnow_daily_brief.py`) produces a fixed-format Chinese brief (`simnow_daily_brief_YYYY-MM-DD.md`) directly from the run summary JSON. It does not connect to SimNow or read private config.
- A formal `run_next_work.ps1 -LiveCapture` run generates the daily brief automatically after the run summary, in addition to the existing capture/record/report/promotion/summary artifacts.
- The ledger summary generator (`simnow_ledger_summary.py`) produces a machine-readable aggregate summary (`simnow_ledger_summary.json`) from the formal ledger. It exposes total rows, valid/pending/skipped/halt/failed counts, reason counts, consecutive valid trading-day rows, latest action, and next action without exposing raw capture fields.
- A formal `run_next_work.ps1 -LiveCapture` run regenerates the ledger summary automatically after the daily record is upserted into the formal ledger and before the promotion decision, run summary, and daily brief are generated.
- The run summary JSON embeds a safe subset of `simnow_ledger_summary.json` under `ledger_summary`. External automation consumers should read only `simnow_run_summary_YYYY-MM-DD.json` for both the daily conclusion and 20-day observation progress.

- The automation prompt now uses `simnow_run_summary_YYYY-MM-DD.json` as the single machine-readable source of truth and `simnow_daily_brief_YYYY-MM-DD.md` as the human-readable report. The agent must not parse multiple markdown reports to decide the final daily status.

- A31 added read-only audit issue diagnostics for H1/H2/H3/H4/M1. The diagnostics are diagnostic-only, do not modify strategy parameters or trading logic, and mark issues as `unknown`/`unavailable` when evidence is missing.

- A32 wired real project inputs into audit issue diagnostics. M1 is now detected from project config introspection, H2 from diagnostics JSON scan, H1 from diagnostics filename/text scan, and H4 from SQLite metadata (with diagnostics file evidence when no DB is provided). Missing evidence still reports `unknown`/`unavailable`.

- A33 upgrades SimNow observation semantics to read-only environment capture plus delayed replay accounting. `simnow_run_summary_YYYY-MM-DD.json` now separates `environment_capture`, `account_contamination`, and `delayed_replay`; strategy PnL comes only from delayed replay, and SimNow account activity is contamination/audit evidence only.

- A34 restarts the formal 20-day observation cycle from `2026-07-14`. Existing ledger rows are preserved as audit evidence, but `simnow_ledger_summary.py`, `simnow_daily_monitor.py`, and `simnow_promotion_decision.py` count only rows on or after the configured `observation_start_date`.

- A35 adds a formal historical replay DB update step to the read-only wrapper. Formal `-LiveCapture` runs now update the configured DB by default before SimNow capture and write `simnow_historical_db_update_YYYY-MM-DD.json`; `-SkipHistoricalDbUpdate` keeps an explicit opt-out path. The run summary and daily brief expose this status, but SimNow remains read-only and no account PnL is used as strategy PnL.

- A36 adds a risk-halt review pack. When `automation_status=halt`, the wrapper writes `simnow_risk_halt_review_YYYY-MM-DD.json` and `.md` so the halt reason, threshold diagnostics, safety snapshot, and delayed-replay risk source are reviewable from read-only artifacts.

- A37 adds a risk-halt decision record. `simnow_risk_halt_decision_YYYY-MM-DD.json` defaults to `decision_status=pending_decision` and `next_formal_observation_allowed=false`; a human must fill a selected decision, operator, rationale, observation-window reset flag, and explicit allow flag before the record validates.

- A38 blocks live capture when any prior `simnow_risk_halt_decision_*.json` remains pending or invalid. This gate runs before SimNow connection and reports `pending risk halt decision`; `-Preflight` and `-PostProcessOnly` remain available for safe validation/repair.
