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
| A11 | DONE | Reject too-short live captures for observation runs | `run_next_work.ps1` defaults to 1800 seconds and rejects `DurationSeconds < MinKlineBarsPerSymbol * 60` unless `-SkipKlineUpdate` is used |
| A12 | DONE | Freeze the daily automation prompt | `AUTOMATION_PROMPT.md` documents the official 1800-second observation command and separates 300-second smoke tests |
| A13 | DONE | Promote subscription completeness to a formal gate | Daily records store `subscription_coverage`; reports show `subscription_missing`; missing subscriptions stay `pending` with reason `subscription_incomplete` |
| A14 | DONE | Promote read-only order safety to a formal gate | Capture exports declare `meta.read_only=true` and `orders_sent_by_workflow=0`; monitor writes `order_safety` and halts on workflow order actions |
| A15 | DONE | Add explicit valid-observation counting | Daily records include `valid_observation`; 20-day and promotion reports show `valid_observation_days`, counted only when safety, replay, kline, subscription, and risk gates all pass |
| A16 | DONE | Simplify live workflow to one formal monitor write | `run_next_work.ps1 -LiveCapture` runs `simnow_daily_monitor.py` once for the formal ledger upsert, avoiding duplicate dry-run/append monitor passes |
| A17 | DONE | Standardize no-tick captures as skipped | Connected captures with no ticks are recorded as `skipped/simnow_no_ticks`, so holidays, off-session runs, and no-market-data windows do not pollute pending replay/kline queues |
| A18 | DONE | Add action summary with reason-tiered recommendations to the 20-day report | `simnow_20d_observation_report.md` contains an `## Action Summary` table mapping each day's status/reason to a severity and actionable recommendation; unit tests cover skipped/pending/halt/pass cases |

## Commands

Preflight, no live connection:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Read-only live capture for a valid observation attempt:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 1800 -MinKlineBarsPerSymbol 30
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
- `AUTOMATION_PROMPT.md` is the copy/paste prompt for recurring Codex automation. It uses the formal 1800-second observation command and keeps 300-second runs as non-observation smoke tests.
- Subscription coverage is a formal daily gate. A day with missing enabled research symbols in `raw.subscribed` remains `pending/subscription_incomplete`.
- Order safety is a formal hard gate. A capture produced by this workflow must declare `meta.read_only=true` and `meta.orders_sent_by_workflow=0`; explicit workflow order actions halt the day with `workflow_order_safety_breach`.
- `valid_observation_days` is the official 20-day progress denominator. A row counts only when `status=pass`, replay consistency is matched, thresholds pass, order safety passes, subscriptions are complete, and kline coverage is complete/non-short.
- The live wrapper performs one monitor write per run: the daily record is produced and upserted into the formal ledger in the same call.
- A capture with zero ticks is not a valid observation attempt. If the gateway produced a snapshot but no ticks, the day is recorded as `skipped` with reason `simnow_no_ticks`.
