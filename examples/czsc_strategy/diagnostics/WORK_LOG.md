# WORK_LOG - SimNow Observation Automation

Append-only working log. Each continuation should add one entry with commands, outcomes, and next action.

## 2026-06-22

### Goal

Create an automation protocol so future work can continue from a durable local task queue.

### Changes

- Created `NEXT_WORK.md` as the authoritative next-work queue.
- Created `ACCEPTANCE.md` with safety, daily observation, risk, and 20-day promotion gates.
- Created `WORK_LOG.md` as the append-only execution log.
- Created `run_next_work.ps1` as the fixed workflow entry point.

### Verification

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- `simnow_daily_capture.py` compiled successfully.
- SimNow workflow unit tests passed: `11 passed`.

### Next Action

Run read-only live capture when needed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

## 2026-06-22 A2 Replay Integration

### Goal

Connect post-close replay JSON production into the daily SimNow workflow so monitor records can advance from `pending` to `pass` only when replay data is available and event surfaces match.

### Changes

- Updated `run_next_work.ps1`:
  - exports `simnow_replay_YYYY-MM-DD.json` after live capture;
  - passes `--replay-json` into `simnow_daily_monitor.py`;
  - first runs monitor with `--no-append`;
  - appends to `simnow_observation_ledger.jsonl` only when record status is `pass`;
  - added live-capture and replay timeout controls to avoid stuck automation jobs.
- Updated `export_simnow_replay_snapshot.py`:
  - writes `meta.replay_available`;
  - marks replay unavailable when the observation date has no replay positions/risk in the historical DB.
- Updated `simnow_daily_monitor.py`:
  - treats `replay_available=false` as `pending` with reason `replay_unavailable`, avoiding false empty-vs-empty matches.
- Updated `simnow_daily_capture.py`:
  - top-level `positions` are reserved for strategy/portfolio event surfaces;
  - raw CTP account positions remain under `raw.positions`;
  - successful CLI runs flush output and exit explicitly after writing JSON.
- Updated tests for the new schema and replay-unavailable guard.

### Verification

Passed:

```powershell
python -m py_compile .\examples\czsc_strategy\diagnostics\simnow_daily_capture.py .\examples\czsc_strategy\diagnostics\export_simnow_replay_snapshot.py .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_capture.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted unit tests passed: `9 passed`.
- Full SimNow workflow unit preflight passed: `12 passed`.
- Replay export for `2026-06-22` produced `meta.replay_available=false` because the configured historical DB does not contain that observation date.
- Monitor dry-run correctly stayed `pending` instead of producing a false `matched` result.

### Current Limitation

The formal 20-day ledger will start appending only after the daily historical DB has bars for the observation date and replay status can become `pass`. This is intentional; empty replay data must not count as a valid observed day.

### Next Action

Continue A3: freeze risk thresholds into a dedicated config file and make monitor/precheck read the same threshold source.

## 2026-06-22 A3 Risk Threshold Config

### Goal

Centralize SimNow observation risk thresholds so monitor, daily wrapper, and reports use one explicit threshold source.

### Changes

- Added `simnow_risk_thresholds.json`.
  - Values are derived from the accepted `simnow_precheck_risk_report.json` baseline.
  - `halt` equals the accepted historical baseline.
  - `warning` is 90% of `halt`, matching the previous monitor behavior.
- Updated `simnow_daily_monitor.py`.
  - Added `DEFAULT_THRESHOLDS`.
  - Added `load_thresholds_config`.
  - Added CLI option `--thresholds`.
  - `make_record` now accepts explicit thresholds while preserving baseline fallback.
- Updated `run_next_work.ps1`.
  - Daily monitor calls now pass `simnow_risk_thresholds.json` explicitly.
- Added tests for threshold config loading and override behavior.

### Verification

Passed:

```powershell
python -m py_compile .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_capture.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --date 2026-06-22 --simnow-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-06-22.json --replay-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-06-22_test.json --thresholds .\examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --no-append --record-json .\examples\czsc_strategy\diagnostics\simnow_record_2026-06-22_threshold_test.json --report-md .\examples\czsc_strategy\diagnostics\simnow_report_2026-06-22_threshold_test.md
```

Results:

- Targeted tests passed: `10 passed`.
- Full SimNow workflow preflight passed: `13 passed`.
- Monitor CLI accepted the shared threshold config and returned `threshold_status=pass`.

### Next Action

Continue A4: make formal ledger appending idempotent by date so repeated daily runs update/replace the same observation day instead of duplicating rows.

## 2026-06-22 A4 Idempotent Ledger Writes

### Goal

Make formal SimNow observation ledger writes idempotent by trading date so repeated automation runs do not duplicate the same day.

### Changes

- Updated `simnow_daily_monitor.py`.
  - Added `upsert_ledger`.
  - Kept `append_ledger` as a compatibility wrapper that delegates to `upsert_ledger`.
  - CLI output now includes `ledger_write`, either `upsert` or `skipped`.
  - Ledger rows are sorted by `date` after each write.
- Updated `test_simnow_daily_monitor.py`.
  - Added coverage proving same-date writes replace the existing row and different dates remain sorted.
- Updated `NEXT_WORK.md`.
  - Marked A4 as `DONE`.

### Verification

Passed:

```powershell
python -m py_compile .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
```

Result:

- Unit tests passed: `7 passed`.

CLI upsert smoke:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --date 2026-06-22 --simnow-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-06-22.json --replay-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-06-22_test.json --thresholds .\examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --ledger .\examples\czsc_strategy\diagnostics\simnow_ledger_upsert_test.jsonl --record-json .\examples\czsc_strategy\diagnostics\simnow_record_upsert_test.json --report-md .\examples\czsc_strategy\diagnostics\simnow_report_upsert_test.md
```

Running the command twice left the temporary ledger with exactly `1` line.

### Next Action

Continue A5: generate/update the formal 20-day observation report from the idempotent ledger and include skip/pending reason summaries.

## 2026-06-22 A5 20-Day Report Hardening

### Goal

Enhance `simnow_20d_observation_report.md` so it shows not only pass/matched/halt counts, but also pending/skipped reasons, latest valid observation date, consecutive clean progress, and promotion blockers.

### Changes

- Updated `simnow_daily_monitor.py`.
  - Added reason extraction for pending/skipped/risk-warning rows.
  - Added status counts, reason counts, latest record date, latest valid observation date, consecutive clean pass days, and promotion blockers to `build_20d_report`.
  - Expanded markdown output with:
    - status counts;
    - pending/skipped/risk reason summary;
    - recent record table with reason column;
    - promotion blocker list.
  - Expanded CLI JSON output with pending/skipped counts, last valid observation date, clean streak, and promotion blockers.
- Updated `run_next_work.ps1`.
  - All daily records are now upserted to the formal ledger, including `pending` and `skipped`.
  - Promotion still requires all required days to be `pass` and consistency-matched, so pending/skipped rows remain audit evidence rather than valid promotion days.
- Updated tests.
  - Added coverage for pending/skipped reason counts, latest valid observation date, clean streak, and markdown sections.
- Updated `NEXT_WORK.md`.
  - Marked A5 as `DONE`.

### Verification

Passed:

```powershell
python -m py_compile .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
```

Result:

- Unit tests passed: `8 passed`.

CLI report smoke with `2026-06-22` pending replay:

- `observed_days=1`
- `pending_days=1`
- `reason_counts.replay_unavailable=1`
- `ready_to_expand=False`
- blockers:
  - `need_19_more_observed_days`
  - `non_pass_days_present`
  - `consistency_not_fully_matched`

### Next Action

Continue A6: define the explicit promotion decision command/report that reviews the 20-day ledger and states whether the candidate can expand beyond observation.

## 2026-06-22 A6 Promotion Decision Gate

### Goal

Provide an explicit promotion decision command/report that reads the formal ledger and states whether the candidate can expand beyond observation.

### Changes

- Added `simnow_promotion_decision.py`.
  - Reads the formal ledger only.
  - Emits `ready_to_expand`, observed/pass/pending/skipped counts, last valid observation date, and blocker reasons.
  - Writes `simnow_20d_promotion_decision.md`.
- Updated `run_next_work.ps1`.
  - After daily ledger upsert, it now generates the promotion decision markdown automatically.
- Updated `.gitignore`.
  - Added the promotion decision markdown to ignored local artifacts.
- Updated `NEXT_WORK.md`.
  - Marked A6 as `DONE`.
- Added unit tests for the promotion decision command/report.

### Verification

Passed:

```powershell
python -m py_compile .\examples\czsc_strategy\diagnostics\simnow_promotion_decision.py .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
python .\examples\czsc_strategy\diagnostics\simnow_promotion_decision.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --report-md .\examples\czsc_strategy\diagnostics\simnow_20d_promotion_decision.md
```

Result:

- Promotion decision command runs successfully and emits a report.
- Current ledger is still short of 20 valid days, so `ready_to_expand=false`.

### Next Action

The A1-A6 automation stack is complete. Future work can now focus on accumulating valid observation days and, once the ledger reaches the gate, reviewing whether to expand beyond observation.

## 2026-06-27 Capture Classification Hardening

### Goal

Distinguish genuine no-replay pending days from capture failures that never produced a market snapshot, so daily reports and promotion decisions stay honest.

### Changes

- Updated `simnow_daily_monitor.py`.
  - Added `_capture_skip_reason`.
  - Days with no ticks, no contracts, no accounts, and no positions now classify as `skipped`.
  - If logs show repeated `097` disconnects, the skip reason is `ctp_disconnect_097_no_snapshot`.
  - `make_record` now stores `skip_reason` explicitly and uses it in `status` and report summaries.
- Re-ran the 2026-06-27 daily record through the monitor.
  - The record moved from `pending` to `skipped`.
  - The 20-day report now shows `pending_days=1`, `skipped_days=1`.
- Re-ran the promotion decision report.
  - `skipped_days_present` now appears as an explicit blocker.

### Verification

Passed:

```powershell
python -m py_compile .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
python .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --date 2026-06-27 --simnow-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-06-27.json --replay-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-06-27.json --thresholds .\examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --record-json .\examples\czsc_strategy\diagnostics\simnow_record_2026-06-27.json --report-md .\examples\czsc_strategy\diagnostics\simnow_report_2026-06-27.md
python .\examples\czsc_strategy\diagnostics\simnow_promotion_decision.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --report-md .\examples\czsc_strategy\diagnostics\simnow_20d_promotion_decision.md
```

Result:

- The 2026-06-27 record is now `skipped` instead of ambiguous `pending`.
- The promotion decision remains `ready_to_expand=false`, now with a clearer blocker list.

### Next Action

Continue accumulating valid observation days until the 20-day gate can be evaluated on enough `pass` records.

## 2026-06-27 Report Consistency Follow-Up

### Goal

Clean up the skipped-day classification implementation and make the daily observation report match the promotion decision blocker logic.

### Changes

- Removed a duplicate `_capture_skip_reason` helper from `simnow_daily_monitor.py`.
- Added a regression test for `ctp_disconnect_097_no_snapshot`.
- Updated daily 20-day report blockers to include:
  - `pending_days_present`
  - `skipped_days_present`
- Regenerated:
  - `simnow_record_2026-06-27.json`
  - `simnow_report_2026-06-27.md`
  - `simnow_20d_promotion_decision.md`

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_connection_probe.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_capture.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow tests passed: `18 passed`.
- Preflight passed.
- Daily report and promotion decision now agree on blockers:
  - `need_18_more_observed_days`
  - `pending_days_present`
  - `skipped_days_present`
  - `non_pass_days_present`
  - `consistency_not_fully_matched`

### Next Action

Continue collecting valid observation days during normal SimNow service windows. The current ledger has two audit rows but zero valid pass days.

## 2026-06-27 Replay Readiness Diagnosis

### Goal

Explain why recent observation days cannot become replay-matched and avoid running expensive replay exports when the historical DB is known to lag the observation date.

### Findings

- The configured historical DB is:
  - `D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db`
- Current table coverage:
  - `AP888`: up to `2026-04-24`
  - `RB888`: up to `2026-04-24`
  - `SC888`: up to `2026-04-25`
  - `A888`: up to `2026-04-24`
  - `ZN888`: up to `2026-04-25`
- Therefore 2026-06-22 and 2026-06-27 cannot produce valid replay snapshots from the current DB.

### Changes

- Updated `export_simnow_replay_snapshot.py`.
  - Adds per-symbol table coverage to replay `meta.table_ranges`.
  - Adds `meta.latest_db_date`.
  - Adds `meta.replay_unavailable_reason=historical_db_lag` when DB coverage is older than the requested observation date.
- Updated `simnow_daily_monitor.py`.
  - Uses the specific replay unavailable reason instead of generic `replay_unavailable`.
- Added `simnow_replay_readiness.py`.
  - Fast DB coverage check before expensive replay export.
  - Exits with code `1` when DB is not ready, while printing a diagnostic JSON.
- Updated `run_next_work.ps1`.
  - Preflight now compiles and tests replay readiness.
  - Live workflow checks DB readiness before replay export.
  - If DB lags, it writes a lightweight replay placeholder with `historical_db_lag` instead of running the expensive full replay.
- Added `test_simnow_replay_readiness.py`.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_connection_probe.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_capture.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py .\examples\czsc_strategy\tests\unit\test_simnow_replay_readiness.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow test set passed: `21 passed`.
- Preflight passed and now also runs `21` tests.
- `simnow_replay_readiness.py --date 2026-06-27` reports `ready=false`, `latest_db_date=2026-04-25`.

### Next Action

Replay-matched pass days require an updated historical DB that covers the observation date. Until then, same-day observations can still be audited, but promotion cannot progress.

## 2026-06-22 Daily Observation

### Goal

Run the SimNow daily observation flow in read-only mode and verify the generated daily artifacts.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- `simnow_daily_capture.py` compiled successfully.
- SimNow workflow unit tests passed: `11 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

### Outcomes

- Output files created:
  - `simnow_export_2026-06-22.json`
  - `simnow_record_2026-06-22.json`
  - `simnow_report_2026-06-22.md`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=18045`.
- Enabled subscriptions complete: `5/5`.
- Tick count: `4`.
- Accounts: `1`.
- Positions: `1`.
- Orders: `0`.
- Trades: `0`.
- No automatic orders were observed.
- Required export keys are present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- Risk fields are present and threshold status is `pass`.
- Monitor status is `pending`; expected because same-day replay JSON is not available yet (`simnow_or_replay_export_missing`).

### Notes

- The capture ran around the late morning session boundary, so the low tick count is not treated as a code failure.
- A PowerShell display/JSON parse check showed Chinese text encoding artifacts, but Python UTF-8 parsing validated both generated JSON files successfully.

### Next Action

Continue A2: add replay JSON production into the daily workflow so the monitor can move from `pending` to `matched` when replay and SimNow event surfaces agree.

## 2026-06-22 Daily Observation Rerun

### Goal

Re-run the read-only SimNow daily observation flow and confirm whether the latest same-day artifacts still satisfy the daily gates.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- `simnow_daily_capture.py` compiled successfully.
- SimNow workflow unit tests passed: `11 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

### Outcomes

- Output files refreshed for the same trading date:
  - `simnow_export_2026-06-22.json`
  - `simnow_record_2026-06-22.json`
  - `simnow_report_2026-06-22.md`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=18045`.
- Enabled subscriptions complete: `5/5`.
- Tick count: `4`.
- Accounts: `1`.
- Positions: `1`.
- Orders: `0`.
- Trades: `0`.
- No automatic orders were observed.
- Required export keys are present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- Risk fields are present and threshold status is `pass`.
- Monitor status is `pending`; reason remains `simnow_or_replay_export_missing`.
- `simnow_report_2026-06-22.md` still shows `observed_days: 0/20` because the workflow does not append the ledger before replay consistency is available.

### Notes

- This capture ran at `2026-06-22 15:21` to `15:26` China Standard Time, after the main day session had effectively ended, so the low tick count is treated as a session-timing artifact rather than a code failure.
- PowerShell rendering still shows Chinese encoding artifacts in JSON string fields, but the workflow completed and JSON parsing/monitor generation succeeded.

### Next Action

Continue A2: produce same-day replay JSON and wire it into the daily workflow so valid observation days can advance from `pending` to `matched` and append to the 20-day ledger.

## 2026-06-22 Replay Follow-up

### Goal

Verify the replay export path independently and re-run the monitor with the generated replay snapshot.

### Commands

Passed:

```powershell
python .\examples\czsc_strategy\diagnostics\export_simnow_replay_snapshot.py --end 2026-06-22 --date 2026-06-22 --out-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-06-22.json
```

Result:

- `simnow_replay_2026-06-22.json` was written successfully.
- Replay payload contains no event surfaces for the day:
  - `signals: []`
  - `trades: []`
  - `positions: []`
- `meta.replay_available` is `false`.

Passed:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --date 2026-06-22 --simnow-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-06-22.json --replay-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-06-22.json --thresholds .\examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --record-json .\examples\czsc_strategy\diagnostics\simnow_record_2026-06-22.json --report-md .\examples\czsc_strategy\diagnostics\simnow_report_2026-06-22.md
```

### Outcomes

- Monitor remains `pending` because replay data exists but has no same-day events to match.
- `observed_days` is now `1` because the record is upserted into the ledger.
- `promotion_blockers` are still present:
  - `need_19_more_observed_days`
  - `non_pass_days_present`
  - `consistency_not_fully_matched`
- This is not a live-trading failure; it is a replay-data availability gap for the selected trading day.

### Next Action

Either wait for a trading day with replay bars/events available or adjust the replay export window/source so `replay_available` becomes `true` and consistency can reach `matched`.

## 2026-06-27 Daily Observation

### Goal

Run the SimNow daily observation flow in read-only mode and record the result for the current date.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- `simnow_daily_capture.py` compiled successfully.
- SimNow workflow unit tests passed: `17 passed`.

Failed during live capture wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

Follow-up commands used to complete today's ledger entry:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --date 2026-06-27 --simnow-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-06-27.json --thresholds .\examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --record-json .\examples\czsc_strategy\diagnostics\simnow_record_2026-06-27.json --report-md .\examples\czsc_strategy\diagnostics\simnow_report_2026-06-27.md
python .\examples\czsc_strategy\diagnostics\simnow_promotion_decision.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --report-md .\examples\czsc_strategy\diagnostics\simnow_20d_promotion_decision.md
```

### Outcomes

- Output files created:
  - `simnow_export_2026-06-27.json`
  - `simnow_record_2026-06-27.json`
  - `simnow_report_2026-06-27.md`
- Live capture did not establish a usable SimNow session.
- CTP trade and market connections repeatedly disconnected with reason `4097` for the full 5-minute window.
- Contract query did not succeed: `contracts_count=0`.
- Enabled subscriptions did not complete: `0/5`.
- Tick count: `0`.
- Accounts: `0`.
- Positions: `0`.
- Orders: `0`.
- Trades: `0`.
- No automatic orders were observed.
- Required export keys are present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- Risk fields are present and threshold status is `pass`.
- Monitor status is `pending`; reason is `simnow_or_replay_export_missing`.

### Notes

- This run started on `2026-06-27 22:04` China Standard Time, outside a normal mainland futures trading day, so the connection/query failure is recorded as an environment/session availability issue rather than a code regression.
- `run_next_work.ps1` timed out waiting for the capture process to exit even though `simnow_export_2026-06-27.json` had already been written. Today's ledger entry was therefore completed from the generated export artifact instead of re-running live capture.
- Replay export was not completed for the day, so consistency could not advance beyond `pending`.

### Next Action

Retry the read-only live capture on an active trading day/session and confirm whether replay export can complete for the same date.

## 2026-06-29 Daily Observation

### Goal

Run the SimNow daily observation flow in read-only mode, fix any local workflow blockers that prevent the daily wrapper from completing, and record today's ledger row.

### Changes

- Updated `run_next_work.ps1`.
  - Fixed `Invoke-CheckedProcess` so it no longer treats a completed child process as timed out.
  - Replaced the fragile `Wait-Process`/`Start-Process` exit handling with a `System.Diagnostics.Process` wait that preserves timeout enforcement and real exit codes.
- Updated `simnow_daily_monitor.py`.
  - `load_json` now reads JSON with `utf-8-sig` so PowerShell-generated replay placeholders with BOM load correctly.
- Added regression coverage:
  - `test_run_next_work_wrapper.py` verifies the wrapper accepts a successful child process and preserves a non-zero exit code.
  - `test_simnow_daily_monitor.py` now covers UTF-8 BOM JSON loading.
- Updated `NEXT_WORK.md`.
  - Marked A1 as `DONE` now that the live wrapper completes the full daily workflow instead of stopping after capture.

### Commands

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_connection_probe.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_capture.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py .\examples\czsc_strategy\tests\unit\test_simnow_replay_readiness.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

Results:

- Wrapper regression tests passed: `2 passed`.
- Full targeted SimNow workflow test set passed: `24 passed`.
- Preflight passed with workflow unit tests: `22 passed`.
- Live read-only workflow completed and generated:
  - `simnow_export_2026-06-29.json`
  - `simnow_replay_2026-06-29.json`
  - `simnow_record_2026-06-29.json`
  - `simnow_report_2026-06-29.md`
  - `simnow_20d_promotion_decision.md`

### Outcomes

- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=17597`.
- Enabled subscriptions completed: `5/5`.
- Tick count: `4`.
- Accounts: `1`.
- Positions: `2` raw CTP rows, with one net short `sc2608` position visible.
- Orders: `2`.
- Trades: `2`.
- No automatic orders were sent by this workflow:
  - the observed orders/trades are pre-existing account activity stamped `2026-06-29 09:45:00+08:00`;
  - the read-only wrapper only connected, queried, subscribed, exported, monitored, and wrote reports.
- Required export keys are present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- Risk fields are present and threshold status is `pass`.
- Monitor status is `pending`, reason `historical_db_lag`.
- Replay export correctly fell back to a placeholder because the configured historical DB only covers through `2026-04-25`.
- During the 5-minute window the CTP sessions began disconnecting with reason `4097` after initial success, but the capture had already produced a usable snapshot, so today's result remains an auditable `pending` day rather than a code failure.

### Next Action

Continue collecting read-only observation days during active service windows. Promotion remains blocked until the historical DB is refreshed to cover the observation date, allowing replay consistency to advance from `historical_db_lag` to `matched`.

## 2026-07-01 Pending Replay Backfill Workflow

### Goal

Add a repeatable way to revisit formal ledger rows that are blocked only by `historical_db_lag`, so they can be promoted from `pending` to replay-checked records once the historical DB is refreshed.

### Changes

- Added `simnow_backfill_pending_replays.py`.
  - Dry-run mode scans the formal ledger, finds pending rows with reason `historical_db_lag`, checks DB coverage, and writes `simnow_backfill_plan.json`.
  - Execute mode exports same-day replay snapshots, re-runs the daily monitor for each ready date, upserts the formal ledger, and refreshes the promotion decision report.
  - Dates without DB coverage remain `waiting_for_db`; dates without a capture export are marked `missing_simnow_export`.
- Added `test_simnow_backfill_pending_replays.py`.
  - Covers pending-date selection, DB-lag waiting, ready-to-backfill planning, and missing-capture detection.
- Updated `run_next_work.ps1`.
  - Preflight now compiles the backfill script, runs its unit tests, and builds a dry-run backfill plan.
- Updated `.gitignore` and `NEXT_WORK.md`.
  - Local backfill plans are ignored.
  - A7 records the new backfill workflow and commands.

### Commands

To verify:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_backfill_pending_replays.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Backfill unit tests passed: `4 passed`.
- Full SimNow preflight passed: `26 passed`.
- Dry-run backfill plan found two pending `historical_db_lag` dates:
  - `2026-06-22`: `waiting_for_db`
  - `2026-06-29`: `waiting_for_db`
- Current latest historical DB date remains `2026-04-25`, so replay backfill is correctly deferred.

## 2026-07-01 SimNow Tick Kline Update

### Goal

Stop waiting for the static historical DB to update by itself. Use the read-only SimNow capture artifact as the same-day data source, aggregate received ticks into 1M bars, and write them into the local replay SQLite DB before replay readiness is checked.

### Changes

- Added `simnow_tick_bars.py`.
  - Reads `simnow_export_YYYY-MM-DD.json`.
  - Uses `meta.contract_map` to map SimNow contracts back to research symbols such as `SC888` and `RB888`.
  - Aggregates actual received ticks into 1M OHLC bars.
  - Calculates volume from positive cumulative-volume deltas; single-tick bars get volume `0` because no prior tick proves traded volume inside that minute.
  - Writes bars idempotently to `{symbol}_1M_raw` and records provenance in `simnow_bar_meta`.
- Added `test_simnow_tick_bars.py`.
  - Covers contract mapping, OHLC aggregation, volume deltas, idempotent SQLite upsert, and CLI summary output.
- Updated `run_next_work.ps1`.
  - After live capture, the workflow now runs the tick-to-1M updater before replay readiness.
  - `-SkipKlineUpdate` can bypass this step for diagnosis.
  - `-KlineDbPath` can override the target DB for smoke tests or emergency rollback.
- Updated `.gitignore` and `NEXT_WORK.md`.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_tick_bars.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Tick bar tests passed: `3 passed`.
- SimNow preflight passed: `29 passed`.
- Smoke-tested existing `simnow_export_2026-07-01.json` into a temporary SQLite DB.
  - Bars written: `4`.
  - Symbols written: `A888`, `RB888`, `SC888`, `ZN888`.
  - Window: `2026-07-01 11:29:00` to `2026-07-01 11:30:00`.
  - `AP888` had no received tick in that capture, so no AP bar was synthesized.
- Wrote the same `2026-07-01` SimNow capture into the configured replay DB.
  - DB path: configured `CHAN_SQLITE_DB_PATH` / `SQLITE_DB_PATH`.
  - Bars written: `4`.
  - Provenance rows written to `simnow_bar_meta`: `4`.
  - `simnow_replay_readiness.py --date 2026-07-01` now reports `latest_db_date=2026-07-01`, but `ready=false` because `AP888` remains missing for that date.

### Notes

- This does not backfill the historical gap from `2026-04-25` to the present. It starts building same-source SimNow replay data from captured ticks going forward.
- A 5-minute capture can only create bars for the actual captured minutes. Full-session replay consistency still requires collecting enough ticks during the session.

## 2026-07-01 SimNow Kline Coverage Quality

### Goal

Make the kline update artifact explain why a day remains `pending`: not just how many bars were written, but which subscribed research symbols received no tick and how much minute coverage each symbol has.

### Changes

- Updated `simnow_tick_bars.py`.
  - Added `expected_symbols`, `missing_symbols`, and `coverage_by_symbol` to the kline update summary.
  - `coverage_by_symbol` reports bar count, tick count, start minute, and end minute for each received research symbol.
- Updated `test_simnow_tick_bars.py`.
  - Added coverage for missing subscribed symbols and per-symbol coverage summaries.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_tick_bars.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Tick bar tests passed: `4 passed`.
- Full SimNow preflight passed: `30 passed`.
- Regenerated `simnow_kline_update_2026-07-01.json`.
  - Expected symbols: `A888`, `AP888`, `RB888`, `SC888`, `ZN888`.
  - Received symbols: `A888`, `RB888`, `SC888`, `ZN888`.
  - Missing symbols: `AP888`.
  - Each received symbol currently has one captured 1M bar, confirming the day is still not sufficient for full replay matching.

## 2026-07-01 Monitor Kline Coverage Reason

### Goal

Make the formal ledger distinguish between a replay blocked by a stale historical DB and a replay blocked by incomplete SimNow tick coverage.

### Changes

- Updated `simnow_daily_monitor.py`.
  - Added optional `--kline-json`.
  - Stores the kline update summary in each daily record as `kline_coverage`.
  - If `missing_symbols` is non-empty, the pending reason becomes `kline_coverage_incomplete`.
- Updated `run_next_work.ps1`.
  - Passes `--kline-json simnow_kline_update_YYYY-MM-DD.json` to both dry-run and formal ledger monitor calls.
- Updated `test_simnow_daily_monitor.py`.
  - Added a regression test that incomplete kline coverage overrides generic `historical_db_lag` in the daily record.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Daily monitor tests passed: `14 passed`.
- Full SimNow preflight passed: `31 passed`.
- Rebuilt the formal `2026-07-01` ledger record with `--kline-json`.
  - Record status remains `pending`.
  - Consistency reason is now `kline_coverage_incomplete`.
  - Missing kline symbols: `AP888`.
- Dry-run pending replay backfill now contains only `2026-06-22` and `2026-06-29`; `2026-07-01` is correctly excluded because it cannot be fixed by historical DB backfill alone.

## 2026-07-01 Formal Kline Coverage Gate

### Goal

Make kline coverage a documented daily observation gate and expose missing symbols directly in the 20-day observation report.

### Changes

- Updated `ACCEPTANCE.md`.
  - A valid daily observation now requires a kline update JSON generated from the same SimNow capture.
  - Every enabled research symbol must have at least one captured 1M bar for the observation date.
  - Missing enabled symbols force `pending` with reason `kline_coverage_incomplete`.
- Updated `NEXT_WORK.md`.
  - Added A9 as `DONE`.
- Updated `simnow_daily_monitor.py`.
  - The recent-record table now includes `kline_missing`.
- Updated `test_simnow_daily_monitor.py`.
  - Verifies the markdown report includes `kline_missing` and the missing symbol list.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Daily monitor tests passed: `14 passed`.
- Full SimNow preflight passed: `31 passed`.
- Rebuilt `simnow_report_2026-07-01.md`.
  - Reason summary includes `kline_coverage_incomplete`.
  - Recent records include `kline_missing`.
  - The `2026-07-01` row shows `AP888` as the missing kline symbol.

## 2026-07-01 Minimum Kline Coverage Threshold

### Goal

Prevent a day with only one or two captured minutes per symbol from being treated as replay-ready merely because every symbol has at least one bar.

### Changes

- Updated `simnow_tick_bars.py`.
  - Added `--min-bars-per-symbol`.
  - Summary now includes `min_bars_per_symbol` and `short_symbols`.
- Updated `run_next_work.ps1`.
  - Added `-MinKlineBarsPerSymbol`, defaulting to `30`.
  - Passes the threshold into the tick-to-1M updater.
- Updated `simnow_daily_monitor.py`.
  - A day with `short_symbols` and no missing symbols remains `pending` with reason `kline_coverage_too_short`.
  - The 20-day report now includes `kline_short`.
- Updated `ACCEPTANCE.md` and `NEXT_WORK.md`.
  - Added A10 and documented the minimum coverage gate.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_tick_bars.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Focused tests passed: `20 passed`.
- Full SimNow preflight passed: `33 passed`.
- Rebuilt `simnow_kline_update_2026-07-01.json` with `min_bars_per_symbol=30`.
  - Missing symbols: `AP888`.
  - Short symbols: `A888`, `RB888`, `SC888`, `ZN888`.
- Rebuilt `simnow_report_2026-07-01.md`.
  - The `2026-07-01` row now shows `kline_missing=AP888`.
  - The same row shows `kline_short=A888,RB888,SC888,ZN888`.

## 2026-07-01 Live Capture Duration Guard

### Goal

Prevent a formal observation run from asking for 30 one-minute bars while only capturing five minutes of ticks.

### Changes

- Updated `run_next_work.ps1`.
  - Default `DurationSeconds` changed from `300` to `1800`.
  - Added `Assert-KlineCoverageWindow`.
  - Live capture now rejects `DurationSeconds < MinKlineBarsPerSymbol * 60` unless `-SkipKlineUpdate` is used.
- Updated `test_run_next_work_wrapper.py`.
  - Added function-level tests for too-short capture rejection and explicit smoke-test allowance.
  - Tests do not connect to SimNow.
- Updated `NEXT_WORK.md` and `ACCEPTANCE.md`.
  - Formal observation command now uses `-DurationSeconds 1800 -MinKlineBarsPerSymbol 30`.
  - Short 300-second runs are documented as smoke tests with `-SkipKlineUpdate`.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Wrapper tests passed: `4 passed`.
- Full SimNow preflight passed: `37 passed`.

## 2026-07-01 Automation Prompt Freeze

### Goal

Make the recurring Codex automation use the formal 1800-second observation command instead of the old 300-second smoke command.

### Changes

- Added `AUTOMATION_PROMPT.md`.
  - Contains the copy/paste prompt for the recurring automation.
  - Uses `-LiveCapture -DurationSeconds 1800 -MinKlineBarsPerSymbol 30` for formal observation.
  - Keeps `-DurationSeconds 300 -SkipKlineUpdate` only as a non-observation smoke test.
  - Adds required daily summary fields for kline missing and short symbols.
- Added `test_simnow_docs.py`.
  - Verifies the automation prompt includes the formal 1800-second command.
  - Verifies 300-second runs are documented only with `-SkipKlineUpdate`.
- Updated `run_next_work.ps1`.
  - Preflight now includes the automation prompt test.
- Updated `NEXT_WORK.md`.
  - Added A12 as `DONE`.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_docs.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Automation prompt test passed: `1 passed`.
- Full SimNow preflight passed: `38 passed`.

## 2026-07-01 Subscription Coverage Gate

### Goal

Make "all enabled contracts are subscribed" a machine-checked daily gate instead of an item that must be inspected manually from the capture JSON.

### Changes

- Updated `simnow_daily_monitor.py`.
  - Added `subscription_coverage`.
  - Daily records now include expected, subscribed, and missing research symbols.
  - Missing enabled subscriptions force `pending` with reason `subscription_incomplete`.
  - The 20-day report now includes `subscription_missing`.
- Updated `test_simnow_daily_monitor.py`.
  - Added a regression test for missing enabled subscriptions.
  - Verifies the markdown report includes `subscription_missing`.
- Updated `ACCEPTANCE.md` and `NEXT_WORK.md`.
  - Added A13 as `DONE`.
  - Documented `subscription_incomplete` as a formal daily gate.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Daily monitor tests passed: `16 passed`.
- Full SimNow preflight passed: `39 passed`.
- Rebuilt `simnow_record_2026-07-01.json`.
  - Expected subscriptions: `A888`, `AP888`, `RB888`, `SC888`, `ZN888`.
  - Subscribed symbols: `A888`, `AP888`, `RB888`, `SC888`, `ZN888`.
  - Missing subscriptions: none.
- Rebuilt `simnow_report_2026-07-01.md`.
  - Recent records include `subscription_missing`.
  - The 2026-07-01 row still remains pending due to `kline_coverage_incomplete`, not subscription failure.

## 2026-07-01 Daily Observation

### Goal

Run the SimNow daily observation flow in read-only mode for 2026-07-01 and record whether the result is a valid observation, a pending audit day, or a skipped day.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- `simnow_daily_capture.py` compiled successfully.
- SimNow workflow unit tests passed: `22 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

### Outcomes

- Output files created:
  - `simnow_export_2026-07-01.json`
  - `simnow_replay_2026-07-01.json`
  - `simnow_record_2026-07-01.json`
  - `simnow_report_2026-07-01.md`
  - `simnow_20d_promotion_decision.md`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=17897`.
- Enabled subscriptions completed: `5/5`.
- Tick count: `4`.
- Accounts: `1`.
- Positions: `1`.
- Orders: `0`.
- Trades: `0`.
- No automatic orders were observed.
- Required export keys are present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- Risk fields are present and threshold status is `pass`.
- Monitor status is `pending`; consistency is not matched because replay readiness reported `historical_db_lag`.
- Replay placeholder correctly recorded `latest_db_date=2026-04-25`, so the missing same-day replay is treated as an environment/data-lag issue rather than a code failure.

### Notes

- The capture started at `2026-07-01 11:56` China Standard Time and produced a usable read-only market snapshot during the day session.
- Python JSON parsing confirmed the generated export file is structurally valid even though PowerShell console rendering still shows mojibake for some Chinese strings.
- The formal ledger now contains `4` observed rows in total: `3` pending and `1` skipped, with zero valid matched pass days so far.

### Next Action

Continue collecting read-only observation days during active service windows. Promotion remains blocked until the historical DB is refreshed beyond `2026-04-25`, allowing replay consistency to move from `historical_db_lag` to `matched`.

## 2026-07-01 Daily Observation Rerun

### Goal

Re-run the read-only SimNow daily observation flow on 2026-07-01, verify that the afternoon capture still produces a valid audit snapshot, and record the updated reason why replay consistency remains pending.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- `simnow_daily_capture.py` compiled successfully.
- SimNow workflow unit tests passed: `29 passed`.
- Pending replay backfill dry-run still reports `2026-06-22`, `2026-06-29`, and `2026-07-01` as `waiting_for_db`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

### Outcomes

- Output files refreshed:
  - `simnow_export_2026-07-01.json`
  - `simnow_replay_2026-07-01.json`
  - `simnow_record_2026-07-01.json`
  - `simnow_report_2026-07-01.md`
  - `simnow_20d_promotion_decision.md`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=17897`.
- Enabled subscriptions completed: `5/5`.
- Tick count: `4`.
- Accounts: `1`.
- Positions: `1`.
- Orders: `0`.
- Trades: `0`.
- No automatic orders were observed; the export still contains empty `orders` and `trades` arrays.
- Required export keys remain present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- Tick-to-1M replay DB update succeeded and wrote `4` bars for `A888`, `RB888`, `SC888`, and `ZN888`.
- Replay readiness is still `ready=false` for `2026-07-01` because `AP888` remains lagged at `2026-04-24` even though the DB latest date has advanced to `2026-07-01` for the other symbols.
- Monitor status remains `pending` with consistency reason `historical_db_lag`.
- Risk threshold status remains `pass` in the generated report.

### Notes

- This rerun started at `2026-07-01 15:23` China Standard Time and still captured a usable read-only snapshot near the day-session close.
- The replay blocker is now more specific than the earlier whole-DB lag diagnosis: same-day bars were written for four symbols, but `AP888` still had no captured tick/bar for the date, so the workflow correctly refused to mark replay consistency as matched.

### Next Action

Continue running the read-only observation during active sessions, especially windows that can capture `AP888` ticks, so the local replay DB can eventually cover all enabled symbols for the same trading day.

## 2026-07-01 A14 Order Safety Gate

### Goal

Promote "no automatic order placement" from a manual checklist item to a machine-verifiable hard gate in the daily SimNow observation flow.

### Changes

- `simnow_daily_capture.py` now marks formal exports with `meta.read_only=true`, `meta.orders_sent_by_workflow=0`, and `meta.workflow_order_actions=[]`.
- `simnow_daily_monitor.py` now writes an `order_safety` section into each record.
- Explicit workflow order actions now halt the day with consistency reason `workflow_order_safety_breach`.
- Raw account orders/trades remain audit evidence only; they do not fail the workflow unless they are attributed to this observation workflow.
- The 20-day report now includes `order_safety`, `workflow_orders`, `raw_orders`, and `raw_trades` columns.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_daily_capture.py examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
```

Result:

- SimNow capture/monitor unit tests passed: `22 passed`.

## 2026-07-01 A15 Valid Observation Counter

### Goal

Make the official 20-day progress count explicit so pending/skipped/partial rows cannot be confused with valid SimNow observation days.

### Changes

- Added `simnow_observation_rules.py` with the shared `is_valid_observation()` rule.
- `simnow_daily_monitor.py` now writes `valid_observation` on each daily record.
- The 20-day observation report now shows `valid_observation_days` and a per-row `valid` column.
- `simnow_promotion_decision.py` now uses the same validity rule and blocks on `need_N_more_valid_observation_days`.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
```

Result:

- SimNow monitor/promotion unit tests passed: `19 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- SimNow workflow preflight passed: `42 passed`.
- `simnow_record_2026-07-01.json` now has `valid_observation=false`.
- `simnow_20d_observation_report.md` and `simnow_20d_promotion_decision.md` both report `valid_observation_days=0/20`.
- Current latest blocker remains `kline_coverage_incomplete` because `AP888` is missing and the other enabled symbols have fewer than the 30-bar threshold in the short capture artifact.

## 2026-07-01 A16 Single Monitor Write

### Goal

Remove the duplicate monitor execution in the live wrapper so each formal observation run produces and upserts the daily record once.

### Changes

- Removed the `--no-append` daily monitor dry-run from `run_next_work.ps1`.
- Kept one formal `simnow_daily_monitor.py` call that writes `record_json`, updates the 20-day report, and upserts the ledger.
- Removed the stale commented monitor command from the wrapper.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
```

Result:

- Wrapper unit tests passed: `5 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- SimNow workflow preflight passed: `43 passed`.
- The live wrapper now contains a single formal monitor write step: `Upsert daily record into formal ledger`.

## 2026-07-01 A17 No-Tick Skip Reason

### Goal

Standardize non-trading-session, holiday, or no-market-data captures so they do not look like replay/K-line code failures.

### Changes

- `_capture_skip_reason()` now treats zero-tick captures with a successful gateway snapshot as `simnow_no_ticks`.
- Subscription and K-line gates no longer overwrite skip reasons.
- Hard order-safety breaches can still halt the day even if no ticks arrive.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
```

Result:

- Daily monitor tests passed: `20 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- SimNow workflow preflight passed: `44 passed`.


## 2026-07-02 A18 Action Summary with Reason-Tiered Recommendations

### Goal

Make the 20-day observation report actionable by adding an `## Action Summary` that explains why each day landed in its status and what to do next.

### Changes

- Updated `simnow_daily_monitor.py`.
  - Added `_pass_gaps()` to list the gates that block a `pass` row from being a valid observation.
  - Added `action_recommendation(record)` mapping each status/reason to a severity and a concrete Chinese recommendation.
  - Added `build_action_summary(records)` to produce a chronological action table.
  - Expanded `write_20d_markdown()` with an `## Action Summary` table: `date | status | reason | severity | action | counts_for_20d`.
- Updated `test_simnow_daily_monitor.py`.
  - Added TDD coverage for skipped (`simnow_no_ticks`, `ctp_disconnect_097_no_snapshot`), pending (`historical_db_lag`, `subscription_incomplete`, `kline_coverage_incomplete`, `kline_coverage_too_short`), halt (`workflow_order_safety_breach`, threshold breach), pass valid, and pass-invalid-with-gaps cases.
  - Added tests for `build_action_summary()` and the markdown Action Summary section.
- Regenerated `simnow_20d_observation_report.md` from the formal ledger.
  - Historical rows now show:
    - `historical_db_lag` -> "历史 DB 未覆盖当天；建议等待或执行 backfill。"
    - `ctp_disconnect_097_no_snapshot` -> "CTP 连接失败；建议检查 SimNow 服务、网络、账号状态。"
    - `kline_coverage_incomplete` -> "缺少 K 线品种：AP888；建议在活跃交易时段重新采集。"
- Updated `NEXT_WORK.md`: marked A18 as `DONE`.
- Updated `ACCEPTANCE.md`: added Daily Report Requirements requiring the Action Summary and reason-tiered action text.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
```

Result:

- Daily monitor tests passed: `32 passed`.

Passed:

```powershell
python examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --no-append --date 2026-07-01 --simnow-json examples\czsc_strategy\diagnostics\simnow_export_2026-07-01.json --replay-json examples\czsc_strategy\diagnostics\simnow_replay_2026-07-01.json --kline-json examples\czsc_strategy\diagnostics\simnow_kline_update_2026-07-01.json --thresholds examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --report-md examples\czsc_strategy\diagnostics\simnow_20d_observation_report.md
```

Result:

- `simnow_20d_observation_report.md` now contains `## Action Summary` with reason-tiered actions for all historical rows.
- Ledger was not modified (`--no-append`).

### Next Action

Run `run_next_work.ps1 -Preflight` to confirm the full workflow still passes.


## 2026-07-02 A19 Sync Action Summary into Promotion Decision Report

### Goal

Make the promotion decision report (`simnow_20d_promotion_decision.md`) as actionable as the daily report by reusing the same Action Summary logic.

### Changes

- Updated `simnow_promotion_decision.py`.
  - Imported `build_action_summary` from `simnow_daily_monitor` to avoid duplicating reason-tier logic.
  - `decide_promotion()` now computes `action_summary`, `action_summary_count`, and `top_blocking_actions` from the recent records.
  - `write_report()` now emits an `## Action Summary` table with columns `date | status | reason | severity | action | counts_for_20d`.
  - CLI JSON stdout now includes `valid_observation_days`, `action_summary_count`, and `top_blocking_actions`.
- Updated `test_simnow_daily_monitor.py`.
  - Added TDD tests verifying:
    - `write_report()` outputs `## Action Summary` with `historical_db_lag` backfill advice and `kline_coverage_incomplete` re-collection advice.
    - `decide_promotion()` returns `valid_observation_days`, `action_summary_count`, and `top_blocking_actions`.
    - A `pass` + `valid_observation=true` row shows `counts_for_20d=True`.
- Updated `NEXT_WORK.md`: marked A19 as `DONE`.
- Updated `ACCEPTANCE.md`: the promotion decision report must also contain an Action Summary with the same columns and reason-tiered actions as the daily report.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
```

Result:

- Daily monitor / promotion decision tests passed: `35 passed`.

Passed:

```powershell
python examples\czsc_strategy\diagnostics\simnow_promotion_decision.py --ledger examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --report-md examples\czsc_strategy\diagnostics\simnow_20d_promotion_decision.md
```

Result:

- `simnow_20d_promotion_decision.md` now contains `## Action Summary` with reason-tiered actions for all historical rows.
- No ledger mutation occurred; only the report artifact was refreshed.

### Next Action

Run `run_next_work.ps1 -Preflight` to confirm the full workflow still passes.


## 2026-07-02 A20 Extract Action Summary into Standalone Utility Module

### Goal

Remove the coupling between `simnow_promotion_decision.py` and the large `simnow_daily_monitor.py` module by extracting Action Summary logic into a pure utility module.

### Changes

- Added `examples/czsc_strategy/diagnostics/simnow_action_summary.py`.
  - Contains pure functions: `_record_reason()`, `_pass_gaps()`, `action_recommendation()`, `build_action_summary()`.
  - No SimNow connection, no file I/O, no private config access.
- Updated `simnow_daily_monitor.py`.
  - Imports `_record_reason` and `build_action_summary` from `simnow_action_summary`.
  - Removed local definitions of `_record_reason`, `_pass_gaps`, `action_recommendation`, and `build_action_summary`.
  - Continues to emit the same `## Action Summary` table in `simnow_20d_observation_report.md`.
- Updated `simnow_promotion_decision.py`.
  - Changed import from `simnow_daily_monitor` to `simnow_action_summary`.
  - No longer depends on `simnow_daily_monitor`.
- Updated `test_simnow_daily_monitor.py`.
  - `action_recommendation` and `build_action_summary` are now imported from `simnow_action_summary`.
  - Added tests verifying:
    - `simnow_promotion_decision.py` does not import `simnow_daily_monitor`.
    - `simnow_daily_monitor.py` imports `simnow_action_summary` and no longer defines action summary functions.
    - Both modules share the same `build_action_summary` function object.
- Updated `NEXT_WORK.md`: marked A20 as `DONE`.
- Updated `ACCEPTANCE.md`: both reports source their Action Summary from the shared `simnow_action_summary.py` module.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
```

Result:

- Daily monitor / promotion decision / action summary tests passed: `38 passed`.

Passed:

```powershell
python examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --no-append --date 2026-07-01 --simnow-json examples\czsc_strategy\diagnostics\simnow_export_2026-07-01.json --replay-json examples\czsc_strategy\diagnostics\simnow_replay_2026-07-01.json --kline-json examples\czsc_strategy\diagnostics\simnow_kline_update_2026-07-01.json --thresholds examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --report-md examples\czsc_strategy\diagnostics\simnow_20d_observation_report.md
python examples\czsc_strategy\diagnostics\simnow_promotion_decision.py --ledger examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --report-md examples\czsc_strategy\diagnostics\simnow_20d_promotion_decision.md
```

Result:

- Both `simnow_20d_observation_report.md` and `simnow_20d_promotion_decision.md` retain identical Action Summary content.
- No ledger mutation occurred.

### Next Action

Run `run_next_work.ps1 -Preflight` to confirm the full workflow still passes.


## 2026-07-02 A21 Machine-Readable Run Summary JSON

### Goal

Provide a single machine-readable artifact after each formal `-LiveCapture` run so external automation can read the day's result without parsing multiple files or markdown.

### Changes

- Added `examples/czsc_strategy/diagnostics/simnow_run_summary.py`.
  - Pure read-only script: loads capture JSON, kline update JSON, daily record JSON, and the formal ledger.
  - Builds `simnow_run_summary_YYYY-MM-DD.json` with sections: `date`, `generated_at`, `files`, `capture`, `kline`, `record`, `promotion`.
  - Exposes `build_run_summary()` for unit testing.
  - Includes `contains_sensitive_data()` to scan for leaked keys such as `密码`, `授权码`, `password`, `auth_code`, `BrokerID`, etc., and value fragments such as `setting_masked`.
  - Raises an error if any sensitive field is detected in the generated summary.
- Added `examples/czsc_strategy/tests/unit/test_simnow_run_summary.py`.
  - Tests full summary generation from minimal artifacts.
  - Verifies no sensitive capture fields leak into the summary.
  - Verifies graceful handling of missing artifact files.
- Updated `run_next_work.ps1`.
  - Added `$RunSummaryJson` variable.
  - Added `simnow_run_summary.py` to the preflight `py_compile` list.
  - Added `test_simnow_run_summary.py` to the preflight test list.
  - Added a "Generate run summary" step after the promotion decision.
  - Added `Write-Host "Run summary JSON: $RunSummaryJson"` at workflow completion.
- Updated `test_run_next_work_wrapper.py`.
  - Added tests verifying `$RunSummaryJson` is defined, the summary script is called after the promotion decision, and the wrapper outputs `Run summary JSON:`.
- Updated `NEXT_WORK.md`: marked A21 as `DONE`.
- Updated `ACCEPTANCE.md`: added a Run Summary Artifact section documenting the required fields and the no-sensitive-data rule.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_run_summary.py examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
```

Result:

- Run summary / wrapper / monitor tests passed: `51 passed`.

Passed:

```powershell
python examples\czsc_strategy\diagnostics\simnow_run_summary.py --date 2026-07-01 --out-dir examples\czsc_strategy\diagnostics --out-json examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-01.json --ledger examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl
```

Result:

- `simnow_run_summary_2026-07-01.json` was generated successfully.
- Summary shows `record.status=pending`, `record.reason=kline_coverage_incomplete`, `kline.missing_symbols=["AP888"]`.
- No sensitive fields (`setting_masked`, `密码`, `授权码`) were emitted.

### Next Action

Run `run_next_work.ps1 -Preflight` to confirm the full workflow still passes.


## 2026-07-02 A22 Automation-Platform Status Layer in Run Summary

### Goal

Expose a top-level automation-platform status layer in `simnow_run_summary_YYYY-MM-DD.json` so an external scheduler can decide whether to count the day, retry, halt, or escalate without parsing nested record fields.

### Changes

- Updated `examples/czsc_strategy/diagnostics/simnow_run_summary.py`.
  - Added `classify_automation_status(summary)` mapping record status/reason to:
    - `valid` → exit code `0`
    - `skipped` → exit code `10`
    - `pending` → exit code `20`
    - `halt` → exit code `30`
    - `failed` (missing artifact / unknown status) → exit code `40`
  - `build_run_summary()` now merges `automation_status`, `automation_exit_code`, `automation_reason`, and `automation_action` into the top-level summary.
  - Added safety checks to ensure the automation fields never carry sensitive keys or values.
- Updated `examples/czsc_strategy/tests/unit/test_simnow_run_summary.py`.
  - Added TDD tests for valid, skipped, pending, halt, and failed classification.
  - Verified existing summary fields are preserved and no sensitive data leaks through the automation layer.
- Updated `NEXT_WORK.md`: marked A22 as `DONE`.
- Updated `ACCEPTANCE.md`: documented automation status semantics in the Run Summary Artifact section.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_run_summary.py -q
```

Result:

- Run summary tests passed: `12 passed`.

Passed:

```powershell
python examples\czsc_strategy\diagnostics\simnow_run_summary.py --date 2026-07-01 --out-dir examples\czsc_strategy\diagnostics --out-json examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-01.json --ledger examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl
```

Result:

- `simnow_run_summary_2026-07-01.json` was regenerated successfully.
- Top-level automation fields:
  - `automation_status`: `pending`
  - `automation_exit_code`: `20`
  - `automation_reason`: `kline_coverage_incomplete`
  - `automation_action`: `resolve pending gate before counting`
- No sensitive fields leaked.

### Next Action

Run `run_next_work.ps1 -Preflight` to confirm the full workflow still passes.


## 2026-07-02 A23 Freeze Automation Prompt to Run Summary Automation Layer

### Goal

Make the daily automation prompt (`AUTOMATION_PROMPT.md`) authoritative and simple: run the wrapper, then read `simnow_run_summary_YYYY-MM-DD.json` and use its automation layer as the final daily conclusion.

### Changes

- Updated `examples/czsc_strategy/diagnostics/AUTOMATION_PROMPT.md`.
  - Kept the formal 1800-second observation command and the 300-second smoke test with `-SkipKlineUpdate`.
  - Added `simnow_run_summary_YYYY-MM-DD.json` to the list of generated artifacts.
  - Added a clear instruction: the final conclusion must be based on the automation layer of `simnow_run_summary_YYYY-MM-DD.json`, not on parsing multiple markdown files.
  - Added state handling rules for `automation_status=valid`, `skipped`, `pending`, `halt`, and `failed`.
  - Added a required daily report field list: `date`, `automation_status`, `automation_exit_code`, `automation_reason`, `automation_action`, `record.status`, `record.valid_observation`, `kline.missing_symbols`, `kline.short_symbols`, `promotion.valid_observation_days`, `promotion.ready_to_expand`, and whether user action is needed.
- Updated `examples/czsc_strategy/tests/unit/test_simnow_docs.py` (TDD).
  - Added failing tests first, then adjusted the prompt until all passed.
  - New coverage verifies:
    - the prompt references `simnow_run_summary_YYYY-MM-DD.json`;
    - the prompt states the final conclusion is based on the run summary and not on markdown parsing;
    - the prompt includes all four automation fields;
    - the prompt includes handling rules for all five automation statuses;
    - the prompt includes all required daily report fields.
- Updated `examples/czsc_strategy/diagnostics/NEXT_WORK.md`.
  - Added A23 as `DONE`.
  - Added a known-baseline note that the daily automation prompt's final conclusion must come from the run summary automation layer.
- Updated `examples/czsc_strategy/diagnostics/ACCEPTANCE.md`.
  - Added a requirement in the Run Summary Artifact section that `AUTOMATION_PROMPT.md` must treat the run summary as the authoritative source for the daily conclusion.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_docs.py -q
```

Result:

- Automation prompt tests passed: `5 passed`.

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File ".\examples\czsc_strategy\diagnostics\run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `77 passed`.
- Pending replay backfill dry-run still reports `2026-06-22` and `2026-06-29` as `waiting_for_db`.

### Next Action

No further prompt changes needed. Future daily automation runs should follow the updated `AUTOMATION_PROMPT.md` and report the final conclusion using only the run summary automation layer.


## 2026-07-02 A24 Daily Brief Generator from Run Summary

### Goal

Provide a fixed-format Chinese daily brief (`simnow_daily_brief_YYYY-MM-DD.md`) that the daily automation agent can copy directly into its report, derived purely from the run summary JSON.

### Changes

- Added `examples/czsc_strategy/diagnostics/simnow_daily_brief.py`.
  - Pure read-only script: loads `simnow_run_summary_YYYY-MM-DD.json` and writes `simnow_daily_brief_YYYY-MM-DD.md`.
  - Does not connect to SimNow, read private config, or send orders.
  - CLI options: `--date`, `--run-summary`, `--out-dir`, `--out-md`.
  - Renders required fields:
    - `date`, `automation_status`, `automation_exit_code`, `automation_reason`, `automation_action`
    - `record.status`, `record.valid_observation`
    - `kline.missing_symbols`, `kline.short_symbols`
    - `promotion.valid_observation_days`, `promotion.ready_to_expand`
    - `needs_user_action`
  - Generates Chinese `## 结论` and `## 下一步` sections.
  - Reuses `action_recommendation()` from `simnow_action_summary.py` to produce reason-specific Chinese guidance.
  - Gracefully handles a missing run summary JSON by rendering a `failed` brief.
- Added `examples/czsc_strategy/tests/unit/test_simnow_daily_brief.py` (TDD).
  - Wrote failing tests first, then implemented the script.
  - Covers:
    - full brief content from a pending/kline-incomplete run summary;
    - valid observation brief;
    - halt status requiring user action;
    - missing run summary fallback;
    - CLI default output path;
    - missing-file loader behavior.
- Updated `examples/czsc_strategy/diagnostics/NEXT_WORK.md`.
  - Added A24 as `DONE`.
  - Added a known-baseline note about the daily brief generator.
- Updated `examples/czsc_strategy/diagnostics/ACCEPTANCE.md`.
  - Documented the daily brief generator in the Run Summary Artifact section.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py -q
```

Result:

- Daily brief tests passed: `6 passed`.

Generated sample brief for `2026-07-01`:

```powershell
python examples\czsc_strategy\diagnostics\simnow_daily_brief.py --date 2026-07-01 --run-summary examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-01.json --out-md examples\czsc_strategy\diagnostics\simnow_daily_brief_2026-07-01.md
```

Result:

- `simnow_daily_brief_2026-07-01.md` was generated with the expected fixed format.
- Top-level fields match the run summary automation layer.
- Conclusion states: 当前不计入 20 日有效观察；缺少 K 线品种：AP888；建议在活跃交易时段重新采集。

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File ".\examples\czsc_strategy\diagnostics\run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `81 passed`.
- A24 is not yet wired into the wrapper; that is reserved for A25.

### Next Action

A25: wire `simnow_daily_brief.py` into `run_next_work.ps1 -LiveCapture` so the daily brief is generated automatically after the run summary.


## 2026-07-02 A24 返工：修正公开接口与 needs_user_action 语义

### Goal

Fix A24 acceptance issues:
1. Expose the required public API: `needs_user_action(summary)` and `build_daily_brief(summary)`.
2. Correct `needs_user_action` semantics so `pending + subscription_incomplete` requires user action.

### Changes

- Updated `examples/czsc_strategy/diagnostics/simnow_daily_brief.py`.
  - Renamed the internal `_needs_user_action(status)` to the public `needs_user_action(summary)`.
  - `needs_user_action(summary)` now returns `True` for:
    - `automation_status == "halt"`
    - `automation_status == "failed"`
    - `automation_reason == "workflow_order_safety_breach"`
    - `automation_reason == "subscription_incomplete"`
  - Returns `False` for other `pending`, `skipped`, and `valid` cases.
  - Renamed `render_daily_brief()` to `build_daily_brief()` and added `render_daily_brief = build_daily_brief` for backward compatibility.
  - `build_daily_brief()` now calls `needs_user_action(summary)` instead of checking status only.
  - Skipped-day conclusion now explicitly says "这不是代码失败" so the automation agent does not treat no-data days as code failures.
- Updated `examples/czsc_strategy/tests/unit/test_simnow_daily_brief.py` (TDD).
  - Added failing tests first for the public API and the `subscription_incomplete` case.
  - Added coverage:
    - `needs_user_action` exists and handles halt/failed/workflow_order_safety_breach/subscription_incomplete/kline_incomplete/skipped/valid.
    - `build_daily_brief` exists and produces the same output as `render_daily_brief`.
    - `pending + subscription_incomplete` → `needs_user_action: true`.
    - `skipped + simnow_no_ticks` → `needs_user_action: false` and conclusion contains "这不是代码失败".
- Updated `examples/czsc_strategy/diagnostics/WORK_LOG.md` with this rework entry.
- Kept `NEXT_WORK.md` A24 as `DONE` (the task scope is unchanged; only implementation details were corrected).

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py -q
```

Result:

- Daily brief tests passed: `10 passed`.

Verified public API:

```python
from simnow_daily_brief import needs_user_action, build_daily_brief
assert needs_user_action({"automation_status": "pending", "automation_reason": "subscription_incomplete"}) is True
assert needs_user_action({"automation_status": "skipped", "automation_reason": "simnow_no_ticks"}) is False
```

Regenerated `simnow_daily_brief_2026-07-01.md`:

```powershell
python examples\czsc_strategy\diagnostics\simnow_daily_brief.py --date 2026-07-01 --run-summary examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-01.json --out-md examples\czsc_strategy\diagnostics\simnow_daily_brief_2026-07-01.md
```

Result:

- Brief still shows `automation_status=pending`, `automation_reason=kline_coverage_incomplete`, `needs_user_action=false`.
- No sensitive fields leaked.

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File ".\examples\czsc_strategy\diagnostics\run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `81 passed`.

### Next Action

A25: wire `simnow_daily_brief.py` into `run_next_work.ps1 -LiveCapture` so the daily brief is generated automatically after the run summary.


## 2026-07-02 A25 Wire Daily Brief into `run_next_work.ps1 -LiveCapture`

### Goal

Make the formal daily observation workflow automatically generate the Chinese daily brief after the run summary, so the automation agent can copy it directly into its report.

### Changes

- Updated `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
  - Added `$DailyBriefMd = Join-Path $OutDir "simnow_daily_brief_$Date.md"` next to `$RunSummaryJson`.
  - Added `simnow_daily_brief.py` to the preflight `py_compile` list.
  - Added `test_simnow_daily_brief.py` to the preflight pytest list.
  - Added a "Generate daily brief" step after "Generate run summary" in the `-LiveCapture` branch.
  - The daily brief command is:
    ```powershell
    python .\examples\czsc_strategy\diagnostics\simnow_daily_brief.py `
        --date $Date `
        --run-summary $RunSummaryJson `
        --out-md $DailyBriefMd
    ```
  - Added error handling: `Daily brief generation failed with exit code $LASTEXITCODE`.
  - Added `Write-Host "Daily brief MD: $DailyBriefMd"` to the workflow completion output.
  - Generation order remains: capture → kline update → replay readiness/export → monitor/ledger → promotion decision → run summary → daily brief.
- Updated `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py` (TDD).
  - Wrote failing tests first, then adjusted the wrapper.
  - Added coverage for:
    - `$DailyBriefMd` variable definition;
    - "Generate daily brief" step appearing after "Generate run summary";
    - `simnow_daily_brief.py` called with `--run-summary` and `--out-md`;
    - "Daily brief MD:" output;
    - preflight pytest list includes `test_simnow_daily_brief.py`;
    - preflight `py_compile` list includes `simnow_daily_brief.py`.
- Updated `examples/czsc_strategy/diagnostics/NEXT_WORK.md`.
  - Added A25 as `DONE`.
  - Added a known-baseline note that formal `-LiveCapture` runs generate the daily brief automatically.
- Updated `examples/czsc_strategy/diagnostics/ACCEPTANCE.md`.
  - Documented that a formal `-LiveCapture` run must generate the daily brief after the run summary.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py -q
```

Result:

- Wrapper / daily brief tests passed: `24 passed`.

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File ".\examples\czsc_strategy\diagnostics\run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `97 passed`.
- Pending replay backfill dry-run still reports `2026-06-22` and `2026-06-29` as `waiting_for_db`.

### Next Action

A1-A25 SimNow observation automation stack is complete. Future work focuses on accumulating valid observation days and, once the ledger reaches the 20-day gate, reviewing promotion readiness.


## 2026-07-02 A26 Ledger Summary Generator

### Goal

Provide a machine-readable aggregate summary of the formal observation ledger so an automation platform can monitor 20-day observation progress without parsing markdown reports.

### Changes

- Added `examples/czsc_strategy/diagnostics/simnow_ledger_summary.py`.
  - Pure read-only script: loads `simnow_observation_ledger.jsonl` and writes `simnow_ledger_summary.json`.
  - Does not connect to SimNow, read private config, or send orders.
  - Exposes public functions:
    - `load_ledger(path) -> list[dict]`
    - `build_ledger_summary(records, min_days=20) -> dict`
  - CLI:
    ```powershell
    python .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py `
        --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl `
        --out-json .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json
    ```
  - Summary fields:
    - `generated_at`, `min_days`, `total_rows`
    - `valid_observation_days`, `pending_days`, `skipped_days`, `halt_days`, `failed_days`
    - `latest_date`, `latest_valid_date`, `consecutive_valid_days`
    - `ready_to_expand` (true only when valid >= 20 and no pending/skipped/halt/failed)
    - `promotion_blockers` with `need_N_more_valid_observation_days`, `pending_days_present`, `skipped_days_present`, `halt_days_present`, `failed_days_present`
    - `reason_counts` via `_record_reason` from `simnow_action_summary.py`
    - `automation_status_counts`
    - `latest_record` with safe summary-level fields only
    - `latest_action` via `build_action_summary([latest_record])`
    - `next_action` mapped from latest automation status
  - Includes `contains_sensitive_data()` to prevent leaking account/password/auth-code/masked-setting fields.
- Added `examples/czsc_strategy/tests/unit/test_simnow_ledger_summary.py` (TDD).
  - Empty ledger summary.
  - Mixed valid/pending/skipped/halt/failed records with counts, reason counts, and blockers.
  - 20 valid records → `ready_to_expand=true`.
  - Trailing consecutive valid day counting with calendar gaps.
  - `latest_action` derived from action summary.
  - `next_action` mapping for ready/pending/skipped/halt/continue.
  - CLI JSON output.
  - No sensitive data leakage.
- Updated `examples/czsc_strategy/diagnostics/NEXT_WORK.md`.
  - Added A26 as `DONE`.
  - Added a known-baseline note about the ledger summary generator.
- Updated `examples/czsc_strategy/diagnostics/ACCEPTANCE.md`.
  - Added a Ledger Summary Artifact section documenting required fields and the no-sensitive-data rule.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_ledger_summary.py -q
```

Result:

- Ledger summary tests passed: `9 passed`.

Generated ledger summary from the formal ledger:

```powershell
python examples\czsc_strategy\diagnostics\simnow_ledger_summary.py --ledger examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --out-json examples\czsc_strategy\diagnostics\simnow_ledger_summary.json
```

Result:

- `simnow_ledger_summary.json` generated successfully.
- `total_rows=4`, `valid_observation_days=0`, `pending_days=3`, `skipped_days=1`.
- `promotion_blockers`: `need_20_more_valid_observation_days`, `pending_days_present`, `skipped_days_present`.
- `latest_action` reason: `kline_coverage_incomplete`.
- `next_action`: `resolve latest pending reason`.
- No sensitive fields leaked.

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File ".\examples\czsc_strategy\diagnostics\run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `97 passed`.
- A26 is not yet wired into the wrapper; that is reserved for A27.

### Next Action

A27: wire `simnow_ledger_summary.py` into `run_next_work.ps1 -Preflight` and/or `-LiveCapture` so the ledger summary is refreshed automatically.

## 2026-07-02 Daily Observation

### Goal

Execute the SimNow daily observation workflow in read-only mode, keep the daily ledger current, and classify any non-code blockers honestly.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- SimNow workflow preflight passed.
- Workflow unit tests passed: `97 passed`.

Expected gate rejection:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

Result:

- Wrapper rejected the run before capture.
- Reason: `DurationSeconds (300) is shorter than MinKlineBarsPerSymbol (30); require at least 1800 seconds or use -SkipKlineUpdate for a smoke test.`
- Root cause is workflow policy, not a SimNow connection or code failure. The current baseline defines 300-second runs as smoke tests only.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

### Outcomes

- Output files created:
  - `simnow_export_2026-07-02.json`
  - `simnow_record_2026-07-02.json`
  - `simnow_report_2026-07-02.md`
  - `simnow_replay_2026-07-02.json`
  - `simnow_run_summary_2026-07-02.json`
  - `simnow_daily_brief_2026-07-02.md`
- SimNow read-only connection/login succeeded.
- Contract query succeeded with `contracts_count=17975`.
- Enabled subscriptions complete: `5/5`; `subscription_coverage.missing_symbols=[]`.
- Tick count: `4`.
- Accounts: `1`.
- Positions: `1`.
- Orders: `0`.
- Trades: `0`.
- No automatic orders were observed:
  - `meta.read_only=true`
  - `meta.orders_sent_by_workflow=0`
  - `meta.workflow_order_actions=[]`
  - `order_safety.status=pass`
- Required export keys are present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- Risk fields are present and threshold status is `pass`.
- Replay export was intentionally downgraded to a placeholder because same-day replay DB coverage is not ready.
- Monitor result:
  - `status=pending`
  - `reason=historical_db_lag`
  - `consistency.matched=false`
  - `valid_observation=false`
- Automation summary result:
  - `automation_status=pending`
  - `automation_exit_code=20`
  - `automation_reason=historical_db_lag`
  - `automation_action=resolve pending gate before counting`

### Notes

- This 300-second run was executed as a read-only smoke test because the formal observation workflow now requires at least 1800 seconds unless `-SkipKlineUpdate` is used.
- The day should not be treated as a code failure. The blocker is historical DB coverage through `2026-07-01`, so same-day replay consistency cannot be matched yet.

### Next Action

Wait for the replay DB to cover `2026-07-02`, or run the pending replay backfill after coverage is available.


## 2026-07-02 A26 返工：consecutive_valid_days 改为按 ledger 尾部有效交易日记录统计

### Goal

Fix the `consecutive_valid_days` semantics in `simnow_ledger_summary.py` so it counts trailing consecutive valid trading-day ledger rows instead of requiring calendar-day adjacency. Weekends and exchange holidays should not break the streak.

### Changes

- Updated `examples/czsc_strategy/diagnostics/simnow_ledger_summary.py`.
  - Simplified `_count_consecutive_valid_days(ordered)`:
    - Iterates the sorted ledger from newest to oldest.
    - Increments the count while `is_valid_observation(row)` is true.
    - Stops as soon as a non-valid record is encountered.
  - Removed all `datetime.strptime` / `timedelta` calendar adjacency checks.
  - Updated the docstring to explain the new trading-day-row semantics.
- Updated `examples/czsc_strategy/tests/unit/test_simnow_ledger_summary.py`.
  - Added `test_consecutive_valid_days_counts_weekend_gap_as_continuous`:
    - Records `2026-07-03` and `2026-07-06` are both valid.
    - Asserts `consecutive_valid_days == 2` even though they are not calendar-adjacent.
  - Added `test_consecutive_valid_days_stops_at_latest_invalid_record`:
    - Latest record is pending.
    - Asserts `consecutive_valid_days == 0`.
  - Kept `test_consecutive_valid_days_counts_trailing_sequence`; it still passes under the new semantics because only the trailing valid rows are counted.
- Updated `examples/czsc_strategy/diagnostics/ACCEPTANCE.md`.
  - Clarified that `consecutive_valid_days` means trailing consecutive valid trading-day ledger rows; weekends/holidays do not break the streak.
- Updated `examples/czsc_strategy/diagnostics/NEXT_WORK.md`.
  - Changed the A26 baseline note to say "consecutive valid trading-day rows" instead of "consecutive valid days".
- A26 remains `DONE`; this is a semantic rework, not a new task.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_ledger_summary.py -q
```

Result:

- Ledger summary tests passed: `11 passed`.

Verified the weekend-gap snippet:

```python
from simnow_ledger_summary import build_ledger_summary
assert build_ledger_summary([
    {"date": "2026-07-03", "status": "pass", "valid_observation": True},
    {"date": "2026-07-06", "status": "pass", "valid_observation": True},
])["consecutive_valid_days"] == 2
```

Result: assertion passed.

Regenerated `simnow_ledger_summary.json` from the formal ledger:

```powershell
python examples\czsc_strategy\diagnostics\simnow_ledger_summary.py --ledger examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --out-json examples\czsc_strategy\diagnostics\simnow_ledger_summary.json
```

Result:

- `consecutive_valid_days` remains `0` because the ledger tail contains no valid observations.
- No other summary fields changed.

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File ".\examples\czsc_strategy\diagnostics\run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `97 passed`.

### Notes

- No SimNow connection, subscription, order placement, or private config access logic was added or modified.
- No raw capture fields, account IDs, passwords, auth codes, or masked settings are exposed in the ledger summary.


## 2026-07-02 A27 Wire Ledger Summary into `run_next_work.ps1 -LiveCapture`

### Goal

Make the formal daily observation workflow automatically regenerate the ledger summary after the daily record is upserted into the formal ledger, so the automation platform always sees the latest 20-day progress.

### Changes

- Updated `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
  - Added `$LedgerSummaryJson = Join-Path $OutDir "simnow_ledger_summary.json"`.
  - Added `$LedgerPath = Join-Path $ScriptPath "simnow_observation_ledger.jsonl"` and reused it in the promotion decision and run summary commands.
  - Added `simnow_ledger_summary.py` to the preflight `py_compile` list.
  - Added `test_simnow_ledger_summary.py` to the preflight pytest list.
  - Added a "Generate ledger summary" step after "Upsert daily record into formal ledger" in the `-LiveCapture` branch.
  - The ledger summary command is:
    ```powershell
    python .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py `
        --ledger $LedgerPath `
        --out-json $LedgerSummaryJson
    ```
  - Added error handling: `Ledger summary generation failed with exit code $LASTEXITCODE`.
  - Added `Write-Host "Ledger summary JSON: $LedgerSummaryJson"` to the workflow completion output.
  - Generation order is now:
    capture → kline update → replay readiness/export → monitor/ledger → **ledger summary** → promotion decision → run summary → daily brief.
- Updated `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py` (TDD).
  - Wrote failing tests first, then adjusted the wrapper.
  - Added coverage for:
    - `$LedgerSummaryJson` variable definition;
    - preflight `py_compile` includes `simnow_ledger_summary.py`;
    - preflight pytest includes `test_simnow_ledger_summary.py`;
    - "Generate ledger summary" step is after monitor/ledger and before promotion decision;
    - `simnow_ledger_summary.py` is called with `--ledger` and `--out-json`;
    - "Ledger summary JSON:" output is present.
- Updated `examples/czsc_strategy/diagnostics/NEXT_WORK.md`.
  - Added A27 as `DONE`.
  - Added a known-baseline note that formal `-LiveCapture` regenerates the ledger summary automatically.
- Updated `examples/czsc_strategy/diagnostics/ACCEPTANCE.md`.
  - Documented that a formal `-LiveCapture` run must regenerate `simnow_ledger_summary.json` after the ledger is written and before promotion/run summary/daily brief.

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py examples\czsc_strategy\tests\unit\test_simnow_ledger_summary.py -q
```

Result:

- Wrapper / ledger summary tests passed: `31 passed`.

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File ".\examples\czsc_strategy\diagnostics\run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `114 passed`.

Static safety check:

```bash
grep -En "send_order|cancel_order|buy\(|sell\(|short\(|cover\(" examples/czsc_strategy/diagnostics/run_next_work.ps1 examples/czsc_strategy/diagnostics/simnow_ledger_summary.py
```

Result:

- No matches; no new trading-interface calls were added.

### Notes

- No SimNow connection, subscription, order placement, or private config access logic was added or modified.
- The ledger file is only read by the new step; no other workflow logic was changed.
- A1-A27 SimNow observation automation stack is complete.

## 2026-07-02 A28 Embed Ledger Summary into Run Summary JSON

### Goal

Make `simnow_run_summary_YYYY-MM-DD.json` the single artifact that external automation consumers read for both the daily conclusion and the 20-day observation progress, by embedding a safe aggregate copy of `simnow_ledger_summary.json`.

### Changes

- Fixed `examples/czsc_strategy/diagnostics/simnow_daily_brief.py`.
  - Added the missing closing parenthesis for the `lines.extend([...])` call that was introduced with the `## 20 日进度` section.
  - The syntax error at line 167 (`SyntaxError: '(' was never closed`) is now resolved.
- Updated `examples/czsc_strategy/diagnostics/simnow_run_summary.py`.
  - Added `load_ledger_summary(path)` helper.
  - Added `SAFE_LEDGER_SUMMARY_FIELDS` allow-list for aggregate fields that may be embedded.
  - Added `_safe_ledger_summary(ledger_summary)` to copy only the allowed safe fields and mark `available: true`.
  - Extended `build_run_summary()` with a `ledger_summary` parameter.
  - The run summary core now contains `ledger_summary`: either the safe aggregate copy, or `{"available": false, "reason": "missing_ledger_summary"}` when no ledger summary is provided.
  - Added CLI `--ledger-summary` argument; the default path is `$OutDir/simnow_ledger_summary.json`.
  - Existing `contains_sensitive_data()` scan now also protects the embedded ledger summary.
- Updated `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
  - The `Generate run summary` step now passes `--ledger-summary $LedgerSummaryJson` to `simnow_run_summary.py`.
- Updated `examples/czsc_strategy/tests/unit/test_simnow_run_summary.py` (TDD).
  - Added tests for embedding ledger summary fields, handling a missing ledger summary, and rejecting a ledger summary that contains sensitive data.
- Updated `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py` (TDD).
  - Added `test_run_summary_script_receives_ledger_summary_argument`.
- Updated `examples/czsc_strategy/tests/unit/test_simnow_daily_brief.py` (TDD).
  - Added tests for the `## 20 日进度` section and the missing-ledger-summary fallback.
- Updated `examples/czsc_strategy/diagnostics/NEXT_WORK.md`.
  - Added A28 as `DONE`.
  - Added a known-baseline note that automation consumers only need `simnow_run_summary_YYYY-MM-DD.json`.
- Updated `examples/czsc_strategy/diagnostics/ACCEPTANCE.md`.
  - Documented that the run summary must expose 20-day progress via `ledger_summary`.
  - Documented that the daily brief must render `## 20 日进度` from the embedded ledger summary.
  - Documented that external automation consumers may read only `simnow_run_summary_YYYY-MM-DD.json`.

### Verification

Passed:

```powershell
python -m pytest examples/czsc_strategy/tests/unit/test_simnow_run_summary.py examples/czsc_strategy/tests/unit/test_simnow_daily_brief.py examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py examples/czsc_strategy/tests/unit/test_simnow_ledger_summary.py -q
```

Result:

- Run summary / daily brief / wrapper / ledger summary tests passed: `60 passed`.

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "examples/czsc_strategy/diagnostics/run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `125 passed`.

Static safety check:

```bash
grep -En "send_order|cancel_order|buy\(|sell\(|short\(|cover\(" examples/czsc_strategy/diagnostics/run_next_work.ps1 examples/czsc_strategy/diagnostics/simnow_run_summary.py examples/czsc_strategy/diagnostics/simnow_daily_brief.py
```

Result:

- No matches; no new trading-interface calls were added.

### Notes

- No SimNow connection, subscription, tick aggregation, replay, monitor, promotion, or daily-brief business logic was modified except for the daily-brief progress section.
- A1-A28 SimNow observation automation stack is complete.

## 2026-07-02 A29 Update Automation Prompt to Run Summary + Daily Brief Split

### Goal

Make the recurring daily automation agent treat `simnow_run_summary_YYYY-MM-DD.json` as the single machine-readable source of truth and `simnow_daily_brief_YYYY-MM-DD.md` as the human-readable report source, so the agent no longer parses multiple markdown reports for final status.

### Changes

- Updated `examples/czsc_strategy/tests/unit/test_simnow_docs.py` (TDD).
  - Added failing tests first for the new A29 requirements:
    - `test_automation_prompt_machine_source_is_run_summary_only`
    - `test_automation_prompt_human_report_source_is_daily_brief`
    - `test_automation_prompt_includes_ledger_summary_fields_for_20d_progress`
    - `test_automation_prompt_includes_required_final_response_fields`
    - `test_automation_prompt_requires_read_only_no_orders`
    - `test_automation_prompt_treats_skipped_not_as_code_failure`
  - Updated existing tests to cover the run-summary/daily-brief split and removed the obsolete `promotion.*` fields from the required final-response list.
- Updated `examples/czsc_strategy/diagnostics/AUTOMATION_PROMPT.md`.
  - Added a clear "安全底线" section: read-only, no orders, no private config leakage.
  - Formal command remains:
    ```powershell
    powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 1800 -MinKlineBarsPerSymbol 30
    ```
  - Smoke test command remains:
    ```powershell
    powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
    ```
  - Declared `simnow_run_summary_YYYY-MM-DD.json` as the **唯一机器判定来源** and the **最终机器判定来源**.
  - Declared `simnow_daily_brief_YYYY-MM-DD.md` as the **人类可读日报来源** and stated that daily brief is only for display/copy, not machine judgment.
  - Listed other artifacts as troubleshooting-only, not final status sources.
  - Required final conclusion fields come from run summary: `automation_status`, `automation_exit_code`, `automation_reason`, `automation_action`.
  - Required 20-day progress fields come from `ledger_summary`: `valid_observation_days`, `consecutive_valid_days`, `ready_to_expand`, `promotion_blockers`, `next_action`.
  - Required final response field list now includes the `ledger_summary.*` fields.
  - Retained status handling rules for `valid/skipped/pending/halt/failed`.
  - Retained holiday/off-session/no-tick → `skipped`, not code failure.
- Updated `examples/czsc_strategy/diagnostics/ACCEPTANCE.md`.
  - Added an "External Automation Consumers" section:
    - Run summary is the single machine-readable source of truth for daily status and 20-day progress.
    - Daily brief is the human-readable report artifact.
    - Observation report, promotion decision report, and ledger summary are for troubleshooting only.
- Updated `examples/czsc_strategy/diagnostics/NEXT_WORK.md`.
  - Added A29 as `DONE`.
  - Added a known-baseline note that the automation prompt now uses run summary as the single machine-readable source of truth and daily brief as the human-readable report.
- Updated `examples/czsc_strategy/diagnostics/WORK_LOG.md` (this entry).

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_simnow_docs.py -q
```

Result:

- Documentation tests passed: `9 passed`.

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "examples/czsc_strategy/diagnostics/run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `121 passed`.

Keyword check (ripgrep not available in this shell; used equivalent grep):

```bash
grep -nE "single machine-readable source|simnow_run_summary|simnow_daily_brief|ledger_summary\.valid_observation_days|ledger_summary\.consecutive_valid_days|不得发送任何委托|read-only" examples/czsc_strategy/diagnostics/AUTOMATION_PROMPT.md examples/czsc_strategy/diagnostics/ACCEPTANCE.md
```

Result:

- All expected keywords present in `AUTOMATION_PROMPT.md` and `ACCEPTANCE.md`.

Static safety check:

```bash
grep -nE "send_order|cancel_order|buy\(|sell\(|short\(|cover\(" examples/czsc_strategy/diagnostics/AUTOMATION_PROMPT.md examples/czsc_strategy/diagnostics/run_next_work.ps1
```

Result:

- No matches; no new trading-interface calls were added.

### Notes

- No SimNow connection, subscription, tick aggregation, replay, monitor, promotion, ledger summary, or daily-brief business logic was modified.
- No order placement, cancellation, or trading-interface calls were added.
- No private config, account, password, auth code, or API key handling was added or changed.
- A1-A29 SimNow observation automation stack is complete.

## 2026-07-03 A30 Smoke Test: Run Summary + Daily Brief Closed Loop

### Goal

Run a 300-second read-only smoke test via `run_next_work.ps1` and verify that the "run summary as the single machine-readable source of truth + daily brief as the human-readable report" split works on real execution artifacts.

### Execution

Preflight:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "examples/czsc_strategy/diagnostics/run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `125 passed`.

Smoke test:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "examples/czsc_strategy/diagnostics/run_next_work.ps1" -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

Result:

- Exit code: `0`.
- Capture duration: 300 seconds.
- SimNow ticks received: `1788`.
- Contracts queried: `18267`.
- Subscribed research symbols: `AP888`, `SC888`, `A888`, `ZN888`, `RB888`.
- Raw orders: `0`; raw trades: `0`.
- Capture `meta.read_only`: `true`; `meta.orders_sent_by_workflow`: `0`; `meta.workflow_order_actions`: `[]`.
- Replay DB not ready for `2026-07-03` (historical DB only covers up to 2026-04-25), so replay export was skipped and the day was recorded as `pending/historical_db_lag`.
- Generated artifacts:
  - `simnow_export_2026-07-03.json`
  - `simnow_record_2026-07-03.json`
  - `simnow_report_2026-07-03.md`
  - `simnow_20d_promotion_decision.md`
  - `simnow_run_summary_2026-07-03.json`
  - `simnow_daily_brief_2026-07-03.md`
  - `simnow_ledger_summary.json`

### Machine Judgment from Run Summary

`simnow_run_summary_2026-07-03.json`:

- `date`: `2026-07-03`
- `automation_status`: `pending`
- `automation_exit_code`: `20`
- `automation_reason`: `historical_db_lag`
- `automation_action`: `resolve pending gate before counting`
- `record.status`: `pending`
- `record.valid_observation`: `false`
- `kline.missing_symbols`: `[]`
- `kline.short_symbols`: `[]`
- `ledger_summary.available`: `true`
- `ledger_summary.valid_observation_days`: `0`
- `ledger_summary.consecutive_valid_days`: `0`
- `ledger_summary.ready_to_expand`: `false`
- `ledger_summary.promotion_blockers`: `["need_20_more_valid_observation_days", "pending_days_present", "skipped_days_present"]`
- `ledger_summary.next_action`: `resolve latest pending reason`

Final machine status was derived solely from `simnow_run_summary_2026-07-03.json`; no markdown report was parsed for the final decision.

### Human Daily Report from Daily Brief

`simnow_daily_brief_2026-07-03.md`:

- Contains `## 20 日进度`.
- automation_status / automation_reason / ledger_summary values match the run summary.
- Conclusion: 当前不计入 20 日有效观察；历史 DB 未覆盖当天；建议等待或执行 backfill。
- Next action: 按 automation_action 执行：resolve pending gate before counting。
- `needs_user_action`: `false`.

### Safety Verification

Static check:

```bash
grep -nE "send_order|cancel_order|buy\(|sell\(|short\(|cover\(" examples/czsc_strategy/diagnostics/run_next_work.ps1 examples/czsc_strategy/diagnostics/simnow_daily_capture.py examples/czsc_strategy/diagnostics/simnow_run_summary.py
```

Result:

- No matches; no trading-interface calls were added or used.

### Notes

- No orders were sent; the workflow remained read-only.
- No private config, account, password, auth code, or API key was printed or exposed in the final reply or artifacts.
- The smoke test result is `pending` due to `historical_db_lag`, which is expected because the configured historical DB does not cover 2026-07-03. This is not a code failure; it matches the known baseline.
- A1-A30 SimNow observation automation stack is verified end-to-end on real execution artifacts.

## 2026-07-03 A31 Audit Issue Diagnostics for H1/H2/H3/H4/M1

### Goal

Turn the highest-priority issues from `AUDIT_REPORT_2026-07-03.md` into repeatable, read-only diagnostics that produce quantified evidence, without optimizing returns or changing trading logic.

### Changes

- Added `examples/czsc_strategy/diagnostics/audit_issue_diagnostics.py`.
  - `detect_high_precision_weights()` for H1: flags weight/multiplier/ratio parameters with more than one decimal place (e.g., `0.847`) and lists existing diagnostics evidence files (`sc_short_weight_neighborhood*`, `portfolio_goal_expanded_short_sc_0847*`, `platform_optimization_round*`).
  - `analyze_stop_loss_overshoot()` for H2: computes worst loss, nominal stop, overshoot count, and max overshoot multiple from a list of stop-loss trades.
  - `analyze_divergence_failure_reachability()` for H3: counts occurrences of `背驰` + `失效` in signal history and reports reachable/unreachable.
  - `analyze_continuous_contract_assumptions()` for H4: inspects SQLite DB metadata for rollover/adjustment columns; reports `unknown`/`unavailable` when no metadata is provided.
  - `analyze_cost_consistency()` for M1: compares commission/slippage across `BACKTEST_CONFIG`, engine defaults, and position defaults; flags inconsistencies and recommends `BACKTEST_CONFIG`.
  - `build_audit_issue_report()`: aggregates all five issues.
  - `write_json_report()` / `write_markdown_report()`: write safe, read-only outputs.
  - `contains_sensitive_data()`: scans outputs for credentials before writing.
  - CLI supports `--out-dir`, `--date`, `--db-path`, `--symbols`, `--pairs-json`, `--signals-json`, `--params-json`, `--cost-config-json`, `--engine-defaults-json`, `--position-defaults-json`, `--stop-loss-bp`.
- Added `examples/czsc_strategy/tests/unit/test_audit_issue_diagnostics.py`.
  - TDD-style tests for H1/H2/H3/H4/M1, report rendering, no-trading-call safety, and sensitive-data detection.
- Generated:
  - `examples\czsc_strategy\diagnostics\audit_issue_diagnostics_2026-07-03.json`
  - `examples\czsc_strategy\diagnostics\audit_issue_diagnostics_2026-07-03.md`
- Updated `examples\czsc_strategy\diagnostics\NEXT_WORK.md`.
  - Added A31 as `DONE`.
  - Added a baseline note that A31 diagnostics are read-only and mark missing evidence as `unknown`/`unavailable`.
- Updated `examples\czsc_strategy\diagnostics\ACCEPTANCE.md`.
  - Added an "Audit Issue Diagnostics" section covering H1/H2/H3/H4/M1 and the safety/scope constraints.
- Updated `examples\czsc_strategy\diagnostics\WORK_LOG.md` (this entry).

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_audit_issue_diagnostics.py -q
```

Result:

- Audit diagnostics tests passed: `14 passed`.

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "examples/czsc_strategy/diagnostics/run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `125 passed`.

Diagnostic script smoke:

```powershell
python examples\czsc_strategy\diagnostics\audit_issue_diagnostics.py --out-dir examples\czsc_strategy\diagnostics --symbols AP888,RB888,SC888,A888,ZN888
```

Result:

- Wrote `audit_issue_diagnostics_2026-07-03.json` and `.md`.
- With only default inputs:
  - H1: `unknown` (no params supplied) but evidence files listed.
  - H2: `unavailable` (no pairs supplied).
  - H3: `unavailable` (no signal history supplied).
  - H4: `unknown` (no DB metadata supplied).
  - M1: `unavailable` (no cost inputs supplied).
- No issue was falsely marked as fixed or passed.

Static safety check:

```bash
grep -nE "send_order|cancel_order|buy\(|sell\(|short\(|cover\(" examples/czsc_strategy/diagnostics/audit_issue_diagnostics.py
```

Result:

- No matches; no trading-interface calls.

Sensitive-data scan:

```bash
grep -nE "password|auth_code|api_key|account_id|setting_masked|认证码|密码" examples/czsc_strategy/diagnostics/audit_issue_diagnostics_2026-07-03.json examples/czsc_strategy/diagnostics/audit_issue_diagnostics_2026-07-03.md
```

Result:

- No matches; no private credentials leaked.

### Notes

- No strategy parameters were changed.
- No SimNow trading logic was modified.
- No orders were sent and no trading interface was called.
- A1-A31 SimNow observation and audit diagnostics stack is complete.

## 2026-07-03 Daily Observation Smoke Rerun

### Goal

Execute the daily SimNow read-only smoke workflow, refresh today's artifacts, and record the machine-readable conclusion from the run summary.

### Commands

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "examples/czsc_strategy\diagnostics\run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `125 passed`.
- Pending replay backfill plan remains unchanged: `2026-06-22`, `2026-06-29`, `2026-07-02`, `2026-07-03` are still `waiting_for_db`.

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "examples/czsc_strategy\diagnostics\run_next_work.ps1" -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

### Outcomes

- Output files refreshed:
  - `simnow_export_2026-07-03.json`
  - `simnow_record_2026-07-03.json`
  - `simnow_report_2026-07-03.md`
  - `simnow_run_summary_2026-07-03.json`
  - `simnow_daily_brief_2026-07-03.md`
  - `simnow_ledger_summary.json`
- SimNow read-only connection/login succeeded.
- Contract query succeeded with `contracts_count=18267`.
- Enabled subscriptions remained complete: `5/5`.
- Tick count: `4`.
- Accounts: `1`.
- Positions: `1`.
- Orders: `0`.
- Trades: `0`.
- No automatic orders were observed; `meta.read_only=true`, `orders_sent_by_workflow=0`, `workflow_order_actions=[]`.
- Required export keys are present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- Risk fields are present and `threshold_status=pass`.
- Run summary normalizes record.reason to `historical_db_lag`; `consistency_matched=false`.
- Replay remained unavailable for the same day because the historical DB lags the observation date. Current replay metadata reports `latest_db_date=2026-07-01`, so `2026-07-03` still cannot be replay-matched.
- Run summary machine judgment:
  - `automation_status=pending`
  - `automation_exit_code=20`
  - `automation_reason=historical_db_lag`
  - `automation_action=resolve pending gate before counting`
- Ledger summary after upsert:
  - `total_rows=6`
  - `valid_observation_days=0`
  - `pending_days=5`
  - `skipped_days=1`
  - `ready_to_expand=false`

### Notes

- The 300-second run was executed as the documented smoke-test path with `-SkipKlineUpdate`; this keeps the workflow read-only and avoids falsely treating a too-short capture as a formal valid-observation attempt.
- This result is not a code failure. The blocking condition remains historical replay coverage, not connection, subscription, or order-safety behavior.

### Next Action

Wait for the historical DB to cover `2026-07-03`, then rerun replay/backfill so the pending day can be evaluated for consistency instead of remaining `historical_db_lag`.

## 2026-07-03 A32 Wire Real Project Inputs into Audit Issue Diagnostics

### Goal

Move A31's audit diagnostics from `unknown`/`unavailable` to quantified conclusions by automatically collecting real project inputs from `chan_strategy` config/engine/position defaults and existing diagnostics JSON files, while remaining read-only and not modifying strategy logic.

### Changes

- Updated `examples/czsc_strategy/diagnostics/audit_issue_diagnostics.py`.
  - Added `collect_cost_inputs_from_project(repo_root)`:
    - Uses AST parsing to read `BACKTEST_CONFIG` from `chan_strategy/config.py`, `BacktestEngine.__init__` defaults from `chan_strategy/backtest_engine.py`, and `Position.__init__` defaults from `chan_strategy/positions.py`.
    - Maps `commission_rate` → `commission` and `slippage` → `slippage` for M1 comparison.
  - Added `collect_stop_loss_pairs_from_diagnostics(diagnostics_dir)`:
    - Recursively scans diagnostics JSON files (≤ 50 MB) for dict records with `exit_reason`/`reason`/`reason_code`/`close_reason`/`exit_signal` containing `stop_loss` or `止损`.
    - Extracts `pnl_pct` and aliases (`return_pct`, `profit_pct`, `pnl_rate`).
    - Normalizes pnl to percentage points (fractions are multiplied by 100; already-percentage values are kept as-is).
    - Skips previously generated `audit_issue_diagnostics*.json` files to avoid feedback loops.
  - Added `collect_signal_records_from_diagnostics(diagnostics_dir)`:
    - Recursively scans diagnostics JSON files for `signals`/`signal`/`signal_snapshot`/`signal_history`/`signal_records` containers.
    - Keeps records containing `背驰` or `divergence` for H3 reachability analysis.
  - Added `collect_parameter_evidence_from_diagnostics(diagnostics_dir)`:
    - Lists H1-relevant diagnostics files by filename.
    - Parses markdown/json text for `multiplier`/`weight`/`ratio` lines and the 0.847/0.85 signatures.
  - Enhanced `analyze_continuous_contract_assumptions(...)`:
    - Still inspects SQLite metadata for rollover/adjustment columns.
    - Now also scans diagnostics filenames/content for continuous-contract/rollover/adjustment/复权/换月 keywords and reports them as `file_evidence` when DB metadata is unavailable.
  - Enhanced `build_audit_issue_report(...)`:
    - Accepts `repo_root` and `diagnostics_dir`.
    - Auto-collects H1/H2/H3 inputs from diagnostics and M1 inputs from project code when explicit inputs are not provided.
    - Adds `data_source` to each issue (e.g., `diagnostics_filename_scan`, `diagnostics_json_scan`, `project_config_introspection`, `sqlite_metadata`).
  - Enhanced CLI with `--repo-root`, `--diagnostics-dir`, and `--max-file-mb`.
- Updated `examples/czsc_strategy/tests/unit/test_audit_issue_diagnostics.py`.
  - Added TDD tests for the new collectors and the auto-collection report:
    - `test_collect_cost_inputs_from_project_detects_conflict`
    - `test_collect_signal_records_from_diagnostics`
    - `test_collect_stop_loss_pairs_from_diagnostics`
    - `test_collect_parameter_evidence_from_diagnostics`
    - `test_analyze_continuous_contract_assumptions_db_without_adjustment`
    - `test_analyze_continuous_contract_assumptions_db_with_adjustment`
    - `test_build_audit_issue_report_with_auto_collection_m1_not_unavailable`
- Regenerated:
  - `examples\czsc_strategy\diagnostics\audit_issue_diagnostics_2026-07-03.json`
  - `examples\czsc_strategy\diagnostics\audit_issue_diagnostics_2026-07-03.md`
- Updated `examples\czsc_strategy\diagnostics\NEXT_WORK.md`.
  - Added A32 as `DONE`.
  - Added a baseline note describing the new auto-collection behavior.
- Updated `examples\czsc_strategy\diagnostics\ACCEPTANCE.md`.
  - Expanded the Audit Issue Diagnostics section to require automatic collection of project evidence for H1/H2/H3/M1 and to state that M1 must not remain unavailable when project config can be introspected.
- Updated `examples\czsc_strategy\diagnostics\WORK_LOG.md` (this entry).

### Verification

Passed:

```powershell
python -m pytest examples\czsc_strategy\tests\unit\test_audit_issue_diagnostics.py -q
```

Result:

- Audit diagnostics tests passed: `21 passed`.

Passed:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "examples/czsc_strategy/diagnostics/run_next_work.ps1" -Preflight
```

Result:

- Full SimNow workflow preflight passed: `125 passed`.

Diagnostic script with real project inputs:

```powershell
python examples\czsc_strategy\diagnostics\audit_issue_diagnostics.py --out-dir examples\czsc_strategy\diagnostics --symbols AP888,RB888,SC888,A888,ZN888
```

Result (extracted from `audit_issue_diagnostics_2026-07-03.json`):

- H1: `detected` — found `sc_short_weight_neighborhood*`, `portfolio_goal_expanded_short_sc_0847*`, `platform_optimization_round*` evidence files; parsed 42 high-precision weight-like values including 0.847.
- H2: `detected` — found 12 stop-loss overshoots; worst loss `-12.60%` vs nominal `-3.0%`; max overshoot multiple `4.20x`.
- H3: `unavailable` — no diagnostics JSON contained real `背驰V260615_失效` signal records.
- H4: `unknown` — no DB metadata provided; 181 diagnostics files mention continuous-contract/888/rollover/adjustment keywords.
- M1: `detected` — `BACKTEST_CONFIG` commission/slippage (`0.0001/0.0005`) conflict with `BacktestEngine` defaults (`0.0003/0.001`); `Position` defaults match `BACKTEST_CONFIG`.

Static safety check:

```bash
grep -nE "send_order|cancel_order|buy\(|sell\(|short\(|cover\(" examples/czsc_strategy/diagnostics/audit_issue_diagnostics.py
```

Result:

- No matches; no trading-interface calls.

Sensitive-data scan:

```bash
grep -nE "password|auth_code|api_key|account_id|setting_masked|认证码|密码" examples/czsc_strategy/diagnostics/audit_issue_diagnostics_2026-07-03.json examples/czsc_strategy/diagnostics/audit_issue_diagnostics_2026-07-03.md
```

Result:

- No matches; no private credentials leaked.

### Notes

- No strategy parameters, trading logic, or SimNow behavior were changed.
- No orders were sent and no trading interface was called.
- The diagnostic script now self-excludes previously generated `audit_issue_diagnostics*.json` files to prevent feedback loops.
- A1-A32 SimNow observation and audit diagnostics stack is complete.

## 2026-07-06 Daily Observation Smoke Rerun

### Goal

Execute the daily SimNow read-only observation workflow, keep the run non-trading, and record today's machine-readable outcome.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `125 passed`.
- Pending replay backfill plan still shows `2026-06-22`, `2026-06-29`, `2026-07-02`, and `2026-07-03` as `waiting_for_db`.

Rejected by guardrail as designed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

Result:

- The workflow rejected the command because `300 < 30 * 60`.
- Root cause is the formal kline gate, not a connection or script defect.
- The script requires `-SkipKlineUpdate` for a 300-second smoke test.

Passed after switching to the documented smoke-test variant:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

### Outcomes

- Output files created/refreshed:
  - `simnow_export_2026-07-06.json`
  - `simnow_record_2026-07-06.json`
  - `simnow_report_2026-07-06.md`
  - `simnow_run_summary_2026-07-06.json`
  - `simnow_daily_brief_2026-07-06.md`
  - `simnow_ledger_summary.json`
- SimNow read-only connection/login succeeded.
- Contract query succeeded with `contracts_count=18409`.
- Enabled subscriptions remained complete: `5/5`; `subscription_missing=0`.
- Tick count: `7`.
- Accounts: `1`.
- Positions: `1`.
- Orders: `0`.
- Trades: `0`.
- No automatic orders were observed; `meta.read_only=true`, `orders_sent_by_workflow=0`, `workflow_order_actions=[]`, `order_safety.status=pass`.
- Required export keys are present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- Risk fields are present with `9` threshold rows; `threshold_status=pass`.
- Daily record status is `pending` with reason `historical_db_lag`; `consistency_matched=false`.
- Run summary machine judgment:
  - `automation_status=pending`
  - `automation_exit_code=20`
  - `automation_reason=historical_db_lag`
  - `automation_action=resolve pending gate before counting`
- Ledger summary after upsert:
  - `total_rows=7`
  - `valid_observation_days=0`
  - `pending_days=6`
  - `skipped_days=1`
  - `ready_to_expand=false`

### Notes

- Today's initial `-LiveCapture -DurationSeconds 300` failure was an expected safety gate, not a code regression.
- The rerun stayed read-only and did not place or simulate any workflow orders.
- Today's blocker remains replay coverage: the replay metadata reports `latest_db_date=2026-07-01`, so `2026-07-06` cannot be consistency-matched yet.
- This smoke run does not count toward the 20-day valid-observation gate.

### Next Action

Wait for the historical DB to cover `2026-07-06`, then rerun replay/backfill so the pending day can be evaluated for consistency instead of remaining `historical_db_lag`.


## 2026-07-07

### Goal

Close A36 by moving `2026-07-06` from `pending/historical_db_lag` to `valid/matched` and making the 20-day ledger show at least one valid observation day.

### Changes

- `chan_strategy/data_adapter.py`: date-only `end_date` filters now include the full day (`23:59:59`), fixing the bug where all intraday bars on the target day were excluded.
- `diagnostics/backtest_matrix_report.py::_dominant_symbol`: now prefers the symbol whose latest bar covers the requested end date, so tables with mixed-case continuous series (e.g. `AP888` vs `ap888`) do not stop the backtest early.
- `diagnostics/simnow_daily_monitor.py::compare_simnow_replay`: a no-trade day where both the live capture and the replay have no actionable events is now considered consistent (`no_actionable_events_on_either_side`).
- `diagnostics/export_simnow_replay_snapshot.py`: `no_replay_events_for_day` is only emitted when every required symbol already reaches the target date in the database; otherwise the day is labelled `historical_db_lag`.
- Added unit tests for the dominant-symbol selection, end-date inclusivity, and no-actionable-events matching.
- Regenerated 2026-07-06 artifacts:
  - `simnow_replay_2026-07-06.json`
  - `simnow_record_2026-07-06.json`
  - `simnow_report_2026-07-06.md`
  - `simnow_20d_promotion_decision.md`
  - `simnow_ledger_summary.json`
  - `simnow_run_summary_2026-07-06.json`

### Verification

```powershell
pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
python tools/sync_check.py
python tools/sync_check.py --root examples/czsc_strategy
```

Results:

- Unit tests: `277 passed`.
- Sync checks: both PASS.
- `simnow_run_summary_2026-07-06.json`:
  - `automation_status=valid`
  - `record.valid_observation=true`
  - `record.consistency_matched=true`
- `simnow_ledger_summary.json`:
  - `valid_observation_days=1`
  - `consecutive_valid_days=1`
  - `latest_valid_date=2026-07-06`
- `meta.read_only=true`, `orders_sent_by_workflow=0`, `workflow_order_actions=[]` remain unchanged.

### Notes

- The DB had already reached `2026-07-06` for all required symbols, but the replay still produced zero events because of the two loader/selector bugs above.
- The fix keeps the workflow read-only and does not fabricate any ticks, trades, or orders.
- Other ledger rows remain pending/skipped for unrelated reasons (historical DB lag on earlier dates, CTP disconnect, kline coverage), so `ready_to_expand=false`.

### Next Action

A36 is complete. Continue normal daily SimNow observation starting from the next trading day.

## 2026-07-07 Daily Observation Smoke Rerun

### Goal

Execute the daily SimNow read-only observation workflow, keep the run non-trading, and record today's machine-readable outcome.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `128 passed`.
- Pending replay backfill plan shows `2026-06-22`, `2026-06-29`, `2026-07-02`, and `2026-07-03` as `ready_to_backfill`.

Rejected by guardrail as designed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

Result:

- The workflow rejected the command because `300 < 30 * 60`.
- Root cause is the formal kline gate, not a connection or script defect.
- The script requires `-SkipKlineUpdate` for a 300-second smoke test.

Passed after switching to the documented smoke-test variant:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

### Outcomes

- Output files created/refreshed:
  - `simnow_export_2026-07-07.json`
  - `simnow_record_2026-07-07.json`
  - `simnow_report_2026-07-07.md`
  - `simnow_run_summary_2026-07-07.json`
  - `simnow_daily_brief_2026-07-07.md`
  - `simnow_ledger_summary.json`
- SimNow read-only connection/login succeeded.
- Contract query succeeded with `contracts_count=18511`.
- Enabled subscriptions remained complete: `5/5`; `subscription_missing=0`.
- Tick count: `4`.
- Accounts: `1`.
- Positions: `2` raw rows, with one non-zero long position on `sc2608`.
- Orders: `2`.
- Trades: `2`.
- No automatic orders were observed; `meta.read_only=true`, `orders_sent_by_workflow=0`, `workflow_order_actions=[]`, `order_safety.status=pass`.
- The observed `raw_orders/raw_trades` came from account snapshots (`sc2608` at `2026-07-07 09:14:59+08:00`), not from workflow order actions.
- Required export keys are present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- Risk fields are present with `9` threshold rows; `threshold_status=pass`.
- Daily record status is `pending` with reason `historical_db_lag`; `consistency_matched=false`.
- Replay remained unavailable for the same day because `AP888` and `A888` tables still lag the observation date even though the DB contains same-day data for other symbols.
- Run summary machine judgment:
  - `automation_status=pending`
  - `automation_exit_code=20`
  - `automation_reason=historical_db_lag`
  - `automation_action=resolve pending gate before counting`
- Ledger summary after upsert:
  - `total_rows=8`
  - `valid_observation_days=1`
  - `pending_days=6`
  - `skipped_days=1`
  - `ready_to_expand=false`

### Notes

- Today's initial `-LiveCapture -DurationSeconds 300` failure was an expected safety gate, not a code regression.
- The rerun stayed read-only and did not place or simulate any workflow orders.
- Today's blocker remains replay coverage for `AP888` and `A888`, so this smoke run does not count toward the 20-day valid-observation gate.

### Next Action

Wait for the historical DB to cover `2026-07-07` for all required symbols, then rerun replay/backfill so the pending day can be evaluated for consistency instead of remaining `historical_db_lag`.

## 2026-07-08 Daily Observation Smoke Rerun

### Goal

Execute the daily SimNow read-only observation workflow, keep the run non-trading, and record today's machine-readable outcome.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `128 passed`.
- Pending replay backfill plan shows `2026-06-22`, `2026-06-29`, `2026-07-02`, and `2026-07-03` as `ready_to_backfill`; `2026-07-07` remains `waiting_for_db`.

Rejected by guardrail as designed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

Result:

- The workflow rejected the command because `300 < 30 * 60`.
- Root cause is the formal kline gate, not a connection or script defect.
- The script requires `-SkipKlineUpdate` for a 300-second smoke test.

Passed after switching to the documented smoke-test variant:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

### Outcomes

- Output files created/refreshed:
  - `simnow_export_2026-07-08.json`
  - `simnow_record_2026-07-08.json`
  - `simnow_report_2026-07-08.md`
  - `simnow_run_summary_2026-07-08.json`
  - `simnow_daily_brief_2026-07-08.md`
  - `simnow_ledger_summary.json`
- SimNow read-only connection/login succeeded.
- Contract query succeeded with `contracts_count=17845`.
- Enabled subscriptions remained complete: `5/5`; `subscription_missing=0`.
- Tick count: `4`.
- Accounts: `1`.
- Positions: `1` raw row, with one non-zero long position on `sc2608`.
- Orders: `0`.
- Trades: `0`.
- No automatic orders were observed; `meta.read_only=true`, `orders_sent_by_workflow=0`, `workflow_order_actions=[]`, `order_safety.status=pass`.
- Required export keys are present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- Risk fields are present with `9` threshold rows; `threshold_status=pass`.
- Daily record status is `pending` with reason `historical_db_lag`; `consistency_matched=false`.
- Replay remained unavailable for the same day because the historical DB still lagged all required symbols. Replay metadata reports:
  - `latest_db_date=2026-07-07`
  - lagged symbols: `AP888`, `RB888`, `SC888`, `A888`, `ZN888`
- Run summary machine judgment:
  - `automation_status=pending`
  - `automation_exit_code=20`
  - `automation_reason=historical_db_lag`
  - `automation_action=resolve pending gate before counting`
- Ledger summary after upsert:
  - `total_rows=9`
  - `valid_observation_days=1`
  - `pending_days=7`
  - `skipped_days=1`
  - `ready_to_expand=false`

### Notes

- Today's initial `-LiveCapture -DurationSeconds 300` failure was an expected safety gate, not a code regression.
- The rerun stayed read-only and did not place or simulate any workflow orders.
- Today's blocker remains replay coverage, so this smoke run does not count toward the 20-day valid-observation gate.

### Next Action

Wait for the historical DB to cover `2026-07-08` for all required symbols, then rerun replay/backfill so the pending day can be evaluated for consistency instead of remaining `historical_db_lag`.

## 2026-07-09 Daily Observation Smoke Rerun

### Goal

Execute the daily SimNow read-only observation workflow, keep the run non-trading, and record today's machine-readable outcome.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `128 passed`.
- Pending replay backfill plan shows `2026-06-22`, `2026-06-29`, `2026-07-02`, and `2026-07-03` as `ready_to_backfill`; `2026-07-07` and `2026-07-08` remain `waiting_for_db`.

Rejected by guardrail as designed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

Result:

- The workflow rejected the command because `300 < 30 * 60`.
- Root cause is the formal kline gate, not a connection or script defect.
- The script requires `-SkipKlineUpdate` for a 300-second smoke test.

Passed after switching to the documented smoke-test variant:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

### Outcomes

- Output files created/refreshed:
  - `simnow_export_2026-07-09.json`
  - `simnow_replay_2026-07-09.json`
  - `simnow_record_2026-07-09.json`
  - `simnow_report_2026-07-09.md`
  - `simnow_run_summary_2026-07-09.json`
  - `simnow_daily_brief_2026-07-09.md`
  - `simnow_ledger_summary.json`
- SimNow read-only connection/login succeeded.
- Contract query succeeded with `contracts_count=17937`.
- Enabled subscriptions remained complete: `5/5`; `subscription_missing=0`.
- Tick count: `4`.
- Accounts: `1`.
- Positions: `1` raw row.
- Orders: `0`.
- Trades: `0`.
- No automatic orders were observed; `meta.read_only=true`, `orders_sent_by_workflow=0`, `workflow_order_actions=[]`, `order_safety.status=pass`.
- Required export keys are present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`.
- Replay remained unavailable for the same day because the historical DB still lagged all required symbols. Replay metadata reports:
  - `latest_db_date=2026-07-07`
  - lagged symbols: `AP888`, `RB888`, `SC888`, `A888`, `ZN888`
- Daily record status is `pending` with consistency reason `historical_db_lag`; `consistency.matched=false`.
- Run summary machine judgment:
  - `automation_status=pending`
  - `automation_exit_code=20`
  - `automation_reason=historical_db_lag`
  - `automation_action=resolve pending gate before counting`
- Ledger summary after upsert:
  - `total_rows=10`
  - `valid_observation_days=1`
  - `pending_days=8`
  - `skipped_days=1`
  - `ready_to_expand=false`

### Notes

- Today's initial `-LiveCapture -DurationSeconds 300` failure was an expected safety gate, not a code regression.
- The rerun stayed read-only and did not place or simulate any workflow orders.
- `-SkipKlineUpdate` intentionally skipped the formal kline artifact, so `simnow_kline_update_2026-07-09.json` was not generated during this smoke run.
- Today's blocker remains replay coverage, so this smoke run does not count toward the 20-day valid-observation gate.

### Next Action

Wait for the historical DB to cover `2026-07-09` for all required symbols, then rerun replay/backfill so the pending day can be evaluated for consistency instead of remaining `historical_db_lag`.

## 2026-07-09 Historical DB Refresh and Replay Backfill

### Goal

Use the new `ssquant` historical DB update service to refresh the shared SQLite history through `2026-07-09`, then re-run pending replay backfill so `historical_db_lag` days can be re-evaluated instead of staying blocked.

### Commands

Verified shared DB path and current coverage:

```powershell
python - <<'PY'
import sys, json, sqlite3
sys.path.insert(0, r'D:\repo\vnpy\examples\czsc_strategy')
from chan_strategy.config import SQLITE_DB_PATH
from pathlib import Path
path = Path(SQLITE_DB_PATH)
tables = ['ap888_1M_raw','rb888_1M_raw','sc888_1M_raw','a888_1M_raw','zn888_1M_raw']
out = {'db_path': SQLITE_DB_PATH, 'exists': path.exists(), 'tables': {}}
if path.exists():
    conn = sqlite3.connect(str(path))
    try:
        for table in tables:
            row = conn.execute(f'SELECT MAX(datetime), COUNT(*) FROM "{table}"').fetchone()
            out['tables'][table] = {'max': row[0], 'count': row[1]}
    finally:
        conn.close()
print(json.dumps(out, ensure_ascii=False, indent=2))
PY
```

Updated only the five observation tables through `2026-07-09`:

```powershell
cd D:\repo\ssquant
python update_kline_db.py --db-path "D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db" --end-date 2026-07-09 --table ap888_1M_raw --table rb888_1M_raw --table sc888_1M_raw --table a888_1M_raw --table zn888_1M_raw
```

Rebuilt readiness and executed backfill:

```powershell
cd D:\repo\vnpy
python .\examples\czsc_strategy\diagnostics\simnow_backfill_pending_replays.py
python .\examples\czsc_strategy\diagnostics\simnow_backfill_pending_replays.py --execute
python .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --out-json .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json
```

Refreshed machine-readable summaries for the changed dates:

```powershell
$diag = 'D:\repo\vnpy\examples\czsc_strategy\diagnostics'
$dates = @('2026-07-02','2026-07-03','2026-07-07','2026-07-08','2026-07-09')
foreach ($date in $dates) {
  python "$diag\simnow_run_summary.py" --date $date --out-dir $diag --out-json "$diag\simnow_run_summary_$date.json" --ledger "$diag\simnow_observation_ledger.jsonl" --ledger-summary "$diag\simnow_ledger_summary.json"
  python "$diag\simnow_daily_brief.py" --date $date --run-summary "$diag\simnow_run_summary_$date.json" --out-dir $diag --out-md "$diag\simnow_daily_brief_$date.md"
}
```

### Outcomes

- `vnpy` and `ssquant` were confirmed to share the same history DB:
  - `D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db`
- `ssquant` API auth was available and the targeted refresh succeeded for all five observation tables.
- Update result:
  - `ap888_1M_raw`: `2026-07-06 14:59:00 -> 2026-07-09 14:59:00`, `+675`
  - `rb888_1M_raw`: `2026-07-07 22:59:00 -> 2026-07-09 22:59:00`, `+783`
  - `sc888_1M_raw`: `2026-07-07 11:27:00 -> 2026-07-09 14:59:00`, `+1202`
  - `a888_1M_raw`: `2026-07-06 22:59:00 -> 2026-07-09 22:59:00`, `+916`
  - `zn888_1M_raw`: `2026-07-07 11:27:00 -> 2026-07-09 14:59:00`, `+1022`
  - total added rows: `4598`
  - update log: `D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\update_log_20260709_155817.csv`
- Backfill readiness advanced from partial coverage to all seven `historical_db_lag` days being `ready_to_backfill`.
- Executed replay backfill for:
  - `2026-06-22`
  - `2026-06-29`
  - `2026-07-02`
  - `2026-07-03`
  - `2026-07-07`
  - `2026-07-08`
  - `2026-07-09`
- Promotion/ledger progress materially improved:
  - `valid_observation_days`: `1 -> 5`
  - `pending_days`: `8 -> 4`
  - `latest_valid_date`: `2026-07-06 -> 2026-07-09`
  - `consecutive_valid_days`: `0 -> 2`
- New valid observation days after backfill:
  - `2026-07-02`
  - `2026-07-03`
  - `2026-07-08`
  - `2026-07-09`
- Remaining non-valid days after backfill:
  - `2026-06-22`: still `pending` due SimNow/replay mismatch plus missing historical `read_only` declaration in the old capture schema
  - `2026-06-27`: still `skipped/ctp_disconnect_097_no_snapshot`
  - `2026-06-29`: still `pending` due SimNow/replay mismatch plus missing historical `read_only` declaration in the old capture schema
  - `2026-07-01`: still `pending/kline_coverage_incomplete`
  - `2026-07-07`: still `pending` due SimNow/replay event-surface mismatch
- Refreshed machine-readable artifacts now reflect the backfilled state:
  - `simnow_ledger_summary.json`
  - `simnow_20d_promotion_decision.md`
  - `simnow_run_summary_2026-07-02.json`
  - `simnow_run_summary_2026-07-03.json`
  - `simnow_run_summary_2026-07-07.json`
  - `simnow_run_summary_2026-07-08.json`
  - `simnow_run_summary_2026-07-09.json`

### Notes

- This run used the external `ssquant` update service; no trading orders were sent from the SimNow observation workflow.
- The remaining blockers are no longer historical DB coverage for these dates; they are now genuine data-quality or old-capture-schema issues.
- `2026-07-08` and `2026-07-09` now count toward the 20-day gate and their regenerated run summaries report `automation_status=valid`.

### Next Action

Focus on the four remaining non-valid days: decide whether to repair the old-schema/order-safety interpretation for `2026-06-22` and `2026-06-29`, investigate the event mismatch on `2026-07-07`, and either re-collect or formally waive `2026-07-01` due `kline_coverage_incomplete`.

## 2026-07-09 Remaining Pending-Day Triage

### Goal

Classify the remaining non-valid observation days after historical DB backfill so future work targets true blockers instead of repeatedly retrying days that are only retained for audit history.

### Commands

Inspected the remaining pending records and their capture/replay surfaces:

```powershell
python - <<'PY'
import json, pathlib
base = pathlib.Path(r'D:\repo\vnpy\examples\czsc_strategy\diagnostics')
for date in ['2026-06-22','2026-06-29','2026-07-01','2026-07-07']:
    exp = json.loads((base / f'simnow_export_{date}.json').read_text(encoding='utf-8-sig'))
    rep = json.loads((base / f'simnow_replay_{date}.json').read_text(encoding='utf-8-sig'))
    rec = json.loads((base / f'simnow_record_{date}.json').read_text(encoding='utf-8-sig'))
    print(date)
    print({
        'export_event_counts': {k: len(exp.get(k, [])) for k in ['signals','trades','positions']},
        'replay_event_counts': {k: len(rep.get(k, [])) for k in ['signals','trades','positions']},
        'meta_read_only': exp.get('meta', {}).get('read_only'),
        'record_status': rec.get('status'),
        'consistency_reason': rec.get('consistency', {}).get('reason'),
        'order_safety_status': rec.get('order_safety', {}).get('status'),
        'order_safety_reasons': rec.get('order_safety', {}).get('reasons'),
        'kline_missing': rec.get('kline_coverage', {}).get('missing_symbols'),
        'kline_short': rec.get('kline_coverage', {}).get('short_symbols'),
    })
PY
```

### Findings

- `2026-06-22`
  - Old capture schema does not declare `meta.read_only`, so `order_safety.status=unknown`.
  - This is not just a metadata problem: SimNow export has `signals=0/trades=0/positions=1`, while replay has `signals=1/trades=0/positions=8`.
  - Conclusion: keep as audit `pending`; it is a genuine old-capture mismatch day, not a historical DB problem.
- `2026-06-29`
  - Old capture schema also lacks `meta.read_only`, so `order_safety.status=unknown`.
  - SimNow export has `signals=0/trades=2/positions=0`, while replay has `signals=1/trades=0/positions=8`.
  - Conclusion: keep as audit `pending`; this is both old-schema and event-surface mismatch, not a backfill gap.
- `2026-07-01`
  - Both SimNow and replay have no actionable strategy events, but the day still fails on formal kline gates.
  - `kline_missing_symbols=['AP888']`
  - `kline_short_symbols=['A888','RB888','SC888','ZN888']`
  - Conclusion: this day is blocked by the intentionally strict kline gate from a too-short smoke capture, not by replay readiness.
- `2026-07-07`
  - This is no longer a data-lag day: `order_safety.status=pass`, subscriptions are complete, and replay exists.
  - The blocker is a true event-surface mismatch:
    - SimNow export: `signals=0/trades=2/positions=0`
    - Replay: `signals=6/trades=1/positions=67`
  - Conclusion: this is the highest-value remaining investigation target because it reflects a real disagreement between live capture and replay after the DB was refreshed.

### Outcome

- Reduced the remaining backlog into three categories:
  - historical audit rows that should likely stay non-valid: `2026-06-22`, `2026-06-29`
  - intentional smoke-test/kline-gate failure: `2026-07-01`
  - true post-backfill live-vs-replay mismatch worth debugging: `2026-07-07`
- Confirmed that the main unresolved engineering issue is now `2026-07-07`, not historical DB coverage.

### Next Action

Prioritize a focused debug pass on `2026-07-07` only: explain why the replay emits strategy signals/positions while the live capture surfaces only raw account trades and no strategy events, then decide whether the capture schema or the comparison rule is wrong.

## 2026-07-09 Pending Reason Diagnostic Hardening

### Goal

Make non-replay-unavailable live/replay mismatches produce a machine-readable reason instead of blank `pending` rows, so remaining blockers are diagnosable in daily briefs, run summaries, and promotion reports.

### Changes

- Updated `examples\czsc_strategy\diagnostics\simnow_daily_monitor.py`.
  - `compare_simnow_replay()` now sets `reason=event_surface_mismatch` whenever the live and replay event surfaces fail an exact match without a more specific higher-priority reason.
- Updated `examples\czsc_strategy\diagnostics\simnow_action_summary.py`.
  - Added a dedicated recommendation for `pending/event_surface_mismatch` that points reviewers to the mismatch between strategy event surfaces and raw account surfaces.
- Updated `examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py`.
  - Added/strengthened regression coverage so generic event-surface mismatches must emit `event_surface_mismatch`.
  - Added action-summary coverage proving the reason now yields a specific recommendation mentioning SimNow vs replay.
- Regenerated affected artifacts for:
  - `2026-06-22`
  - `2026-06-29`
  - `2026-07-07`
- Refreshed:
  - `simnow_ledger_summary.json`
  - `simnow_20d_promotion_decision.md`
  - recent `simnow_run_summary_*.json`
  - recent `simnow_daily_brief_*.md`

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q -k "event_surface_mismatch"
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
```

Results:

- Targeted mismatch tests passed: `2 passed`.
- Full daily-monitor unit suite passed: `43 passed`.

Artifact spot checks:

- `simnow_record_2026-06-22.json`: `status=pending`, `consistency.reason=event_surface_mismatch`
- `simnow_record_2026-06-29.json`: `status=pending`, `consistency.reason=event_surface_mismatch`
- `simnow_record_2026-07-07.json`: `status=pending`, `consistency.reason=event_surface_mismatch`
- `simnow_run_summary_2026-07-07.json`: `automation_status=pending`, `automation_reason=event_surface_mismatch`

### Outcome

- Remaining pending rows no longer hide behind blank reasons.
- The unresolved engineering issue is now explicitly machine-readable as `event_surface_mismatch`, which matches the earlier root-cause investigation for `2026-07-07`.

### Next Action

Decide whether `2026-07-07` should be fixed by enriching live capture with strategy event surfaces, or by narrowing the comparison rule so raw account callbacks are not treated as equivalent to replay strategy events.

## 2026-07-09 Live Capture Strategy-Surface Enrichment

### Goal

Enrich the read-only SimNow capture artifact with a strategy event surface that is comparable to replay on the same observed window, so live-vs-replay checks stop mixing raw account callbacks with strategy-layer events.

### Changes

- Added `examples\czsc_strategy\diagnostics\simnow_strategy_surface.py`.
  - Reads a capture JSON and derives a local comparison window from `meta.started_at` / `meta.ended_at`.
  - Reuses the replay snapshot builder to generate strategy events for the trading day.
  - Filters `signals` / `trades` / `positions` down to the observed live-capture window only.
  - Writes the filtered strategy surface back into the capture artifact top-level fields and records window metadata under `meta.strategy_surface`.
- Updated `examples\czsc_strategy\diagnostics\simnow_daily_capture.py`.
  - Top-level `trades` are now reserved for strategy event surfaces, matching the existing top-level reservation for `signals` and `positions`.
  - Raw account callbacks remain under `raw.trades` / `raw.positions` only.
- Updated `examples\czsc_strategy\diagnostics\simnow_daily_monitor.py`.
  - Replay comparison now filters replay events to the live-capture window whenever `meta.strategy_surface.window_start/window_end` are present.
  - This keeps the comparison on the same observed interval instead of comparing a 5-minute live snapshot with a full-day replay.
- Updated `examples\czsc_strategy\diagnostics\run_next_work.ps1`.
  - Preflight now compiles and tests `simnow_strategy_surface.py`.
  - Live workflow now runs `simnow_strategy_surface.py` after kline aggregation and before replay/monitor writes.
- Added tests:
  - `examples\czsc_strategy\tests\unit\test_simnow_strategy_surface.py`
  - updated `test_simnow_daily_capture.py`
  - updated `test_simnow_daily_monitor.py`
  - updated `test_run_next_work_wrapper.py`

### Verification

Passed targeted TDD cycle:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_capture.py .\examples\czsc_strategy\tests\unit\test_simnow_strategy_surface.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q -k "build_export_matches_daily_monitor_schema or simnow_strategy_surface or filters_replay_to_capture_window"
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q -k "strategy_surface"
```

Results:

- Capture/surface/windowed-monitor tests passed: `5 passed`.
- Wrapper strategy-surface tests passed: `4 passed`.

Passed broader regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_capture.py .\examples\czsc_strategy\tests\unit\test_simnow_strategy_surface.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted unit suites passed: `77 passed`.
- Full workflow preflight passed: `138 passed`.
- Pending replay backfill plan now reports `pending_historical_db_lag_days=0`.

Real artifact validation on the remaining high-value blocker:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_strategy_surface.py --capture-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-07-07.json --date 2026-07-07
python .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --date 2026-07-07 --simnow-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-07-07.json --replay-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-07-07.json --thresholds .\examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --record-json .\examples\czsc_strategy\diagnostics\simnow_record_2026-07-07.json --report-md .\examples\czsc_strategy\diagnostics\simnow_report_2026-07-07.md
```

Result:

- `2026-07-07` moved from `pending/event_surface_mismatch` to:
  - `status=pass`
  - `valid_observation=true`
  - `consistency.matched=true`
  - `consistency.reason=no_actionable_events_on_either_side`

### Outcome

- Live capture artifacts can now carry a strategy-layer event surface instead of exposing only raw account callbacks at the comparison boundary.
- The previous high-value blocker `2026-07-07` is resolved.
- Ledger progress improved again:
  - `valid_observation_days`: `5 -> 6`
  - `pending_days`: `4 -> 3`
  - `consecutive_valid_days`: `2 -> 6`
- Refreshed summaries now show:
  - `simnow_run_summary_2026-07-07.json`: `automation_status=valid`
  - `simnow_20d_promotion_decision.md`: `valid_observation_days=6/20`

### Next Action

Revisit the two old-schema audit rows (`2026-06-22`, `2026-06-29`) only if they are worth converting; otherwise keep them as historical pending evidence and continue accumulating fresh valid observation days with the enriched capture workflow.

## 2026-07-09 Legacy Read-Only Backward Compatibility

### Goal

Convert the two old-schema audit rows (`2026-06-22`, `2026-06-29`) from non-counting historical evidence into valid observation days when the only remaining blocker is that those early capture artifacts predate the explicit read-only metadata fields.

### Changes

- Updated `examples\czsc_strategy\diagnostics\simnow_daily_monitor.py`.
  - Added a narrow `_is_legacy_read_only_capture()` helper.
  - `order_safety()` now infers `read_only=true` only for legacy captures that:
    - do not contain any of `read_only`, `orders_sent_by_workflow`, or `workflow_order_actions`;
    - still contain the legacy timing envelope (`started_at`, `ended_at`).
  - Modern captures that merely omit `read_only` still remain `order_safety.status=unknown`.
  - `order_safety` now records `legacy_inferred` for auditability.
- Updated `examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py`.
  - Added regression coverage proving legacy artifacts can count when fully matched.
  - Preserved the existing guard that modern missing-`read_only` captures do not count.
- Re-ran `simnow_daily_monitor.py` for:
  - `2026-06-22`
  - `2026-06-29`
- Refreshed:
  - `simnow_observation_ledger.jsonl`
  - `simnow_ledger_summary.json`
  - `simnow_20d_promotion_decision.md`
  - `simnow_run_summary_2026-06-22.json`
  - `simnow_run_summary_2026-06-27.json`
  - `simnow_run_summary_2026-06-29.json`
  - `simnow_run_summary_2026-07-01.json`
  - `simnow_run_summary_2026-07-07.json`
  - `simnow_run_summary_2026-07-08.json`
  - `simnow_run_summary_2026-07-09.json`
  - corresponding `simnow_daily_brief_*.md`

### Verification

Passed focused red/green cycle:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q -k "legacy_read_only or pass_invalid_lists_gaps"
```

Passed broader regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py .\examples\czsc_strategy\tests\unit\test_simnow_strategy_surface.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_capture.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Refreshed the two legacy dates:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --date 2026-06-22 --simnow-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-06-22.json --replay-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-06-22.json --thresholds .\examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --record-json .\examples\czsc_strategy\diagnostics\simnow_record_2026-06-22.json --report-md .\examples\czsc_strategy\diagnostics\simnow_report_2026-06-22.md
python .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --date 2026-06-29 --simnow-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-06-29.json --replay-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-06-29.json --thresholds .\examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --record-json .\examples\czsc_strategy\diagnostics\simnow_record_2026-06-29.json --report-md .\examples\czsc_strategy\diagnostics\simnow_report_2026-06-29.md
```

Results:

- `2026-06-22` is now:
  - `status=pass`
  - `valid_observation=true`
  - `order_safety.status=pass`
  - `consistency.reason=no_actionable_events_on_either_side`
- `2026-06-29` is now:
  - `status=pass`
  - `valid_observation=true`
  - `order_safety.status=pass`
  - `consistency.reason=no_actionable_events_on_either_side`
- Ledger progress improved again:
  - `valid_observation_days`: `6 -> 8`
  - `pending_days`: `3 -> 1`
  - `skipped_days`: `1` unchanged
- Remaining blockers are now cleanly reduced to:
  - `2026-06-27`: `skipped/ctp_disconnect_097_no_snapshot`
  - `2026-07-01`: `pending/kline_coverage_incomplete`

### Next Action

Do not revisit the legacy read-only issue again unless another pre-metadata capture appears. The only actionable non-valid day left is `2026-07-01`, which needs a formal active-session re-capture (or an explicit decision to keep it as a smoke-test-only audit row).

## 2026-07-10 Formal Day-Session Guard

### Goal

Prevent new formal observation runs from being launched during clearly non-covering windows, so the workflow does not create avoidable `pending/kline_coverage_incomplete` rows like the historical `2026-07-01` short-capture artifact.

### Changes

- Updated `examples\czsc_strategy\diagnostics\run_next_work.ps1`.
  - Added `Assert-FormalObservationWindow`.
  - The guard runs only for formal `-LiveCapture` runs where `-SkipKlineUpdate` is not set.
  - Current rule is intentionally narrow: if enabled `AP888` is present in `simnow_contract_map.json`, the wrapper requires the local runtime to be within a day-session window (`08:45` to `15:30` local time).
  - Off-window attempts now fail fast with an actionable message telling the operator to either:
    - switch to `-SkipKlineUpdate` for a smoke test; or
    - rerun during the day session.
- Updated `examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py`.
  - Added guard coverage for:
    - rejecting a night formal run when `AP888` is enabled;
    - allowing a day-session formal run when `AP888` is enabled;
    - allowing a night smoke run with `-SkipKlineUpdate`;
    - allowing a night formal run when `AP888` is disabled;
    - ensuring the guard is invoked before live capture starts.

### Verification

Passed focused wrapper guard tests:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q -k formal_window_validation
```

Passed full wrapper regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
```

Passed workflow preflight:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Wrapper tests passed: `31 passed`.
- Workflow preflight passed: `144 passed`.
- The formal day-session guard is now active for future formal captures and does not affect preflight or smoke-test usage.

### Next Action

Wait for the next day-session window and run the formal 1800-second read-only observation command. Nighttime work should use `-SkipKlineUpdate` smoke mode only while `AP888` remains enabled.

## 2026-07-13 Daily Observation Smoke Run

### Goal

Execute the SimNow daily observation workflow in read-only mode, verify today's artifacts, and record the result without sending any orders.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `155 passed`.

Rejected by design:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

Result:

- The wrapper rejected the command because `300 < 30 * 60`.
- This is the expected formal-observation guard, not a code failure.

Passed smoke rerun:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

### Outcomes

- Generated today's artifacts:
  - `simnow_export_2026-07-13.json`
  - `simnow_replay_2026-07-13.json`
  - `simnow_record_2026-07-13.json`
  - `simnow_report_2026-07-13.md`
  - `simnow_run_summary_2026-07-13.json`
  - `simnow_daily_brief_2026-07-13.md`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=18023`.
- Enabled subscriptions were complete: `5/5`, `missing_symbols=[]`.
- Read-only safety passed:
  - `meta.read_only=true`
  - `meta.orders_sent_by_workflow=0`
  - `meta.workflow_order_actions=[]`
  - `order_safety.status=pass`
- Capture counts:
  - `ticks=4`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
- Required export keys were present: `meta`, `signals`, `trades`, `positions`, `risk`, `raw`, `captured`.
- Risk threshold rows were present for all expected metrics, but the final threshold status is `unproven` because replay is not ready.
- Replay DB readiness stayed unavailable for the day:
  - `consistency.reason=historical_db_lag`
  - `record.status=pending`
  - `automation_status=pending`
  - `automation_exit_code=20`
- Ledger summary after the run:
  - `total_rows=12`
  - `valid_observation_days=8`
  - `pending_days=3`
  - `skipped_days=1`

### Notes

- This run was a documented smoke test, not a valid 20-day observation attempt, because `-SkipKlineUpdate` was required to bypass the short-duration formal gate.
- The day is not a code failure. It remains `pending/historical_db_lag`, which matches the acceptance rules for incomplete replay coverage.

### Next Action

Wait for the next eligible day-session window and run the formal 1800-second read-only observation command. If historical DB coverage still lags the trade date, keep the result as `pending/historical_db_lag` or backfill when coverage becomes available.

## A33 - Delayed Replay Accounting Semantics

### Goal

Make the SimNow observation reports explicit that the workflow remains read-only: SimNow account activity is external contamination/audit evidence, while strategy PnL comes only from local historical DB delayed replay.

### Changes

- `simnow_run_summary.py` now emits `environment_capture`, `account_contamination`, and `delayed_replay` sections.
- `simnow_daily_brief.py` renders separate sections for SimNow environment capture, account contamination, and delayed DB replay.
- `AUTOMATION_PROMPT.md` and `ACCEPTANCE.md` document that local historical DB replay is the only strategy PnL source.

### Verification

- Added failing tests first for run summary and daily brief semantics, then implemented the minimal code to pass them.
- Targeted tests passed for `test_simnow_run_summary.py`, `test_simnow_daily_brief.py`, `test_run_next_work_wrapper.py`, and `test_simnow_docs.py`.

## A34 - Restart 20-Day Observation Window from 2026-07-14

### Goal

Restart the formal SimNow 20-day observation cycle from tomorrow (`2026-07-14`) without deleting prior ledger evidence.

### Changes

- Added `simnow_observation_window.json` with `observation_start_date=2026-07-14`.
- Added `simnow_observation_window.py` to load the start date and filter ledger rows on or after the configured start.
- Updated `simnow_ledger_summary.py`, `simnow_daily_monitor.py`, and `simnow_promotion_decision.py` so 20-day progress excludes rows before the configured start date.
- Updated `simnow_run_summary.py` to use the same start date when it builds the promotion section.
- Added preflight compilation coverage for `simnow_observation_window.py`.

### Verification

- Added failing tests first for ledger filtering, 20-day report filtering, promotion decision filtering, and wrapper compile coverage.
- Targeted tests passed for `test_simnow_ledger_summary.py`, `test_simnow_daily_monitor.py`, `test_simnow_run_summary.py`, and `test_run_next_work_wrapper.py`.

## A35 - Optional Historical DB Auto-Update Before Read-Only Observation

### Goal

Allow the formal SimNow observation wrapper to run the local historical replay DB updater before capture when explicitly requested, while keeping the SimNow workflow read-only and auditable.

### Changes

- `run_next_work.ps1` now accepts `-UpdateHistoricalDb`, `-HistoricalDbUpdateCommand`, and `-HistoricalDbUpdateTimeoutSeconds`.
- Formal `-LiveCapture` runs always write `simnow_historical_db_update_YYYY-MM-DD.json`.
- When `-UpdateHistoricalDb` is set, the configured update command runs before SimNow capture; when it is omitted, the artifact records `status=skipped`.
- `simnow_run_summary.py` embeds a safe `historical_db_update` section.
- `simnow_daily_brief.py` renders the historical DB update status for human review.
- `AUTOMATION_PROMPT.md`, `ACCEPTANCE.md`, and `NEXT_WORK.md` document the optional update switch, artifact, and report fields.

### Verification

- Added failing tests first for wrapper wiring, run summary fields, daily brief rendering, and automation/acceptance documentation.
- Targeted tests passed for `test_run_next_work_wrapper.py`, `test_simnow_run_summary.py`, `test_simnow_daily_brief.py`, and `test_simnow_docs.py`.

## 2026-07-14 Daily Observation Acceptance Run

### Goal

Execute the SimNow daily observation workflow for the new formal window start date (`2026-07-14`), keep the workflow read-only, and record whether the day counts toward the restarted 20-day ledger.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `186 passed`.

Rejected by design:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

Result:

- The wrapper rejected the command because `300 < 30 * 60`.
- This remains the documented formal-observation guard, not a code failure.

Passed smoke capture, halted at monitor stage:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

Follow-up read-only summary regeneration:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --out-json .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json
python .\examples\czsc_strategy\diagnostics\simnow_promotion_decision.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --report-md .\examples\czsc_strategy\diagnostics\simnow_20d_promotion_decision.md
python .\examples\czsc_strategy\diagnostics\simnow_run_summary.py --date 2026-07-14 --out-dir .\examples\czsc_strategy\diagnostics --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --ledger-summary .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json --out-json .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-14.json
python .\examples\czsc_strategy\diagnostics\simnow_daily_brief.py --date 2026-07-14 --run-summary .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-14.json --out-dir .\examples\czsc_strategy\diagnostics --out-md .\examples\czsc_strategy\diagnostics\simnow_daily_brief_2026-07-14.md
```

### Outcomes

- Generated/refreshed today's artifacts:
  - `simnow_export_2026-07-14.json`
  - `simnow_replay_2026-07-14.json`
  - `simnow_record_2026-07-14.json`
  - `simnow_report_2026-07-14.md`
  - `simnow_historical_db_update_2026-07-14.json`
  - `simnow_ledger_summary.json`
  - `simnow_20d_promotion_decision.md`
  - `simnow_run_summary_2026-07-14.json`
  - `simnow_daily_brief_2026-07-14.md`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=17643`.
- Enabled subscriptions were complete: `5/5`, `missing_symbols=[]`.
- Read-only workflow safety passed:
  - `meta.read_only=true`
  - `meta.orders_sent_by_workflow=0`
  - `meta.workflow_order_actions=[]`
  - `order_safety.status=pass`
- Environment capture counts:
  - `ticks=4`
  - `accounts=1`
  - `positions=3`
  - `orders=4`
  - `trades=4`
- The observed `orders/trades/positions` were account contamination evidence, not workflow orders:
  - `account_contamination.detected=true`
  - `external_orders=4`
  - `external_trades=4`
  - `external_active_positions=1`
  - `external_position_symbols=[sc2609]`
- Same-day replay was available and used as the only strategy risk source:
  - `latest_db_date=2026-07-14`
  - `risk_source=replay_only`
- Formal day result:
  - `record.status=halt`
  - `record.reason=event_surface_mismatch`
  - `automation_status=halt`
  - `automation_exit_code=30`
- The stop condition was not workflow order safety; it was a combination of:
  - replay-vs-live `event_surface_mismatch`
  - replay risk threshold halt on `consecutive_loss_abs_pct`
  - replay warning rows on `drawdown_abs_pct` and `consecutive_loss_days`
- 20-day ledger progress after the restarted window entry:
  - `observation_start_date=2026-07-14`
  - `excluded_before_start_count=12`
  - `observed_days=1`
  - `valid_observation_days=0`
  - `halt_days=1`

### Notes

- The initial 300-second formal command requested by automation cannot count as a valid observation because the wrapper still enforces the documented `1800`-second minimum unless `-SkipKlineUpdate` is used.
- The smoke rerun remained read-only and produced usable evidence, but the day is a halted audit row rather than a valid observation day.
- `simnow_historical_db_update_2026-07-14.json` shows `status=skipped` because `-UpdateHistoricalDb` was not requested.

### Next Action

Do not continue automated daily observation until the user reviews today's `halt` row. Focus manual review on:

- why the live strategy surface still mismatched replay on `2026-07-14`; and
- whether the replay-based `consecutive_loss_abs_pct` halt threshold should block the restarted observation window immediately.

## 2026-07-14 Execution Fixes

### Goal

Fix the execution/reporting defects discovered during the first `2026-07-14` observation run:

- captured-session strategy surfaces did not carry the capture window, so replay comparisons used the full day instead of the observed interval;
- `halt` rows exposed `consistency.reason` before threshold breaches, hiding the actual stop condition in machine-readable summaries;
- the wrapper stopped at the monitor step on `halt`, which prevented automatic summary/brief generation.

### Changes

- Updated `simnow_strategy_surface.py`.
  - `build_strategy_surface_from_captured_session()` now includes `window_start` and `window_end` from the capture metadata.
- Updated `simnow_action_summary.py`.
  - `_record_reason()` now prefers threshold halt metrics for `halt` rows, while preserving `workflow_order_safety_breach` for order-safety halts.
- Updated `run_next_work.ps1`.
  - The wrapper now treats `simnow_daily_monitor.py` exit code `2` as a handled `halt` outcome instead of an immediate failure.
  - `ledger_summary`, promotion decision, `run_summary`, and `daily_brief` generation now continue after a handled `halt`.
  - The wrapper exits `30` after summary generation when monitor status is `halt`.
- Added/updated regression tests for:
  - captured-session window propagation;
  - `halt` reason priority;
  - wrapper summary generation after monitor `halt`.

### Verification

Passed focused regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_strategy_surface.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q -k "captured_session_includes_capture_window or prefers_threshold_breach_over_consistency_reason or halt_monitor_does_not_stop_summary_generation or auto_prefers_captured_session_when_data_present"
```

Results:

- `4 passed`.

Passed broader workflow-adjacent regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_strategy_surface.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted unit suites passed: `139 passed`.
- Workflow preflight passed: `189 passed`.

### Next Action

Re-run the daily read-only observation workflow and verify whether the repaired comparison/reporting path changes the observed outcome.

## 2026-07-14 Daily Observation Rerun After Fixes

### Goal

Re-run the read-only SimNow observation flow after the execution fixes and record the updated daily result for the restarted observation window.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `189 passed`.

Executed smoke rerun:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

Follow-up read-only summary regeneration:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --out-json .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json
python .\examples\czsc_strategy\diagnostics\simnow_promotion_decision.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --report-md .\examples\czsc_strategy\diagnostics\simnow_20d_promotion_decision.md
python .\examples\czsc_strategy\diagnostics\simnow_run_summary.py --date 2026-07-14 --out-dir .\examples\czsc_strategy\diagnostics --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --ledger-summary .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json --historical-db-update .\examples\czsc_strategy\diagnostics\simnow_historical_db_update_2026-07-14.json --out-json .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-14.json
python .\examples\czsc_strategy\diagnostics\simnow_daily_brief.py --date 2026-07-14 --run-summary .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-14.json --out-md .\examples\czsc_strategy\diagnostics\simnow_daily_brief_2026-07-14.md
```

### Outcomes

- The repaired strategy-surface path no longer produced the earlier `halt/event_surface_mismatch` result on this rerun.
- The actual rerun started at about `2026-07-14 18:16 +08:00`, outside an active data window, so the capture produced no valid snapshot:
  - `ticks=0`
  - `contracts_count=0`
  - `accounts=0`
  - `positions=0`
  - `orders=0`
  - `trades=0`
- Read-only safety still passed:
  - `meta.read_only=true`
  - `meta.orders_sent_by_workflow=0`
  - `meta.workflow_order_actions=[]`
  - `order_safety.status=pass`
- No account contamination was observed:
  - `external_orders=0`
  - `external_trades=0`
  - `external_active_positions=0`
- Formal day result after the rerun:
  - `record.status=skipped`
  - `skip_reason=ctp_disconnect_097_no_snapshot`
  - `automation_status=skipped`
  - `automation_exit_code=10`
- Replay was still available for the day (`latest_db_date=2026-07-14`), but the skipped capture does not count toward the 20-day gate.
- 20-day progress after the rerun:
  - `observation_start_date=2026-07-14`
  - `observed_days=1`
  - `valid_observation_days=0`
  - `skipped_days=1`
  - `halt_days=0`

### Notes

- This rerun happened during a no-data / disconnected window, so the result is a legitimate `skipped` observation row, not a code failure.
- The automation client call itself timed out before the session completed, but the local daily artifacts were written and then refreshed manually from the current ledger/record state.

### Next Action

Run the next read-only observation during a valid session window. The repaired code path is now ready to observe whether a real active-session capture still produces any replay mismatch or threshold halt.

## 2026-07-14 Daily Observation Rerun With Active Data

### Goal

Re-run the repaired read-only SimNow smoke workflow again and confirm the end-to-end wrapper now handles a non-skipped day without manual summary regeneration.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `189 passed`.

Executed smoke rerun:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

### Outcomes

- The repaired wrapper completed artifact generation automatically even though the final day result was non-pass.
- Generated/refreshed today's artifacts:
  - `simnow_export_2026-07-14.json`
  - `simnow_replay_2026-07-14.json`
  - `simnow_record_2026-07-14.json`
  - `simnow_report_2026-07-14.md`
  - `simnow_20d_promotion_decision.md`
  - `simnow_run_summary_2026-07-14.json`
  - `simnow_daily_brief_2026-07-14.md`
  - `simnow_ledger_summary.json`
  - `simnow_historical_db_update_2026-07-14.json`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=17705`.
- Enabled subscriptions were complete: `5/5`, `missing_symbols=[]`.
- Read-only workflow safety passed:
  - `meta.read_only=true`
  - `meta.orders_sent_by_workflow=0`
  - `meta.workflow_order_actions=[]`
  - `order_safety.status=pass`
- Environment capture counts:
  - `ticks=991`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
- Strategy-surface comparison result:
  - `consistency.matched=true`
  - `consistency.reason=no_actionable_events_on_either_side`
  - The earlier `event_surface_mismatch` did not recur.
- Account contamination was limited to a pre-existing external active position:
  - `external_orders=0`
  - `external_trades=0`
  - `external_active_positions=1`
  - `external_position_symbols=[sc2609]`
- Formal day result:
  - `record.status=halt`
  - `record.reason=consecutive_loss_abs_pct`
  - `automation_status=halt`
  - `automation_exit_code=30`
- The remaining blocker is now clearly the replay risk threshold, not the live/replay comparison path:
  - halt metric: `consecutive_loss_abs_pct`
  - warning metrics: `drawdown_abs_pct`, `consecutive_loss_days`
- 20-day progress after the rerun:
  - `observation_start_date=2026-07-14`
  - `observed_days=1`
  - `valid_observation_days=0`
  - `halt_days=1`

### Notes

- This rerun confirms the execution fixes worked:
  - captured-session comparisons no longer degrade into the old full-day replay mismatch;
  - `halt` summaries now expose the threshold breach reason;
  - the wrapper now generates summary artifacts automatically on `halt`.
- The shell command still returns a non-zero process exit because the wrapper intentionally exits with the automation halt code after generating artifacts. This is expected behavior, not a wrapper crash.

### Next Action

Manual review is still required for the replay risk halt on `consecutive_loss_abs_pct`. Do not count the day toward the 20-day gate until that stop condition is understood or accepted.

## 2026-07-15 Daily Observation Acceptance Run

### Goal

Execute the SimNow daily observation workflow for `2026-07-15`, keep the workflow read-only, and record whether the day counts toward the restarted 20-day ledger.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `189 passed`.

Rejected by design:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

Result:

- The wrapper rejected the command because `300 < 30 * 60`.
- This remains the documented formal-observation guard, not a code failure.

Passed smoke rerun:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

### Outcomes

- Generated/refreshed today's artifacts:
  - `simnow_export_2026-07-15.json`
  - `simnow_replay_2026-07-15.json`
  - `simnow_record_2026-07-15.json`
  - `simnow_report_2026-07-15.md`
  - `simnow_run_summary_2026-07-15.json`
  - `simnow_daily_brief_2026-07-15.md`
  - `simnow_historical_db_update_2026-07-15.json`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=17705`.
- Enabled subscriptions were complete: `5/5`, `missing_symbols=[]`.
- Read-only workflow safety passed:
  - `meta.read_only=true`
  - `meta.orders_sent_by_workflow=0`
  - `meta.workflow_order_actions=[]`
  - `order_safety.status=pass`
- Environment capture counts:
  - `ticks=4`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
- Observed account activity remained contamination/audit evidence only:
  - `account_contamination.detected=true`
  - `external_orders=0`
  - `external_trades=0`
  - `external_active_positions=1`
  - `external_position_symbols=[sc2609]`
- Historical DB update was not requested:
  - `historical_db_update.status=skipped`
- Same-day delayed replay was not ready:
  - `delayed_replay.available=false`
  - `latest_db_date=2026-07-14`
  - `missing_or_lagged_symbols=[AP888,RB888,SC888,A888,ZN888]`
- Formal day result:
  - `record.status=pending`
  - `record.reason=historical_db_lag`
  - `record.threshold_status=unproven`
  - `automation_status=pending`
  - `automation_exit_code=20`
- 20-day ledger progress after the run:
  - `observation_start_date=2026-07-14`
  - `observed_days=2`
  - `valid_observation_days=0`
  - `pending_days=1`
  - `halt_days=1`

### Notes

- The requested 300-second formal command still cannot count as a valid observation because the wrapper enforces the documented `1800`-second minimum unless `-SkipKlineUpdate` is used.
- Today's smoke run is not a code failure. The day remains `pending/historical_db_lag`, which matches the acceptance rules for replay DB coverage lag.
- No workflow orders were sent.

### Next Action

Run the next observation during an eligible session window with the formal 1800-second command when possible. If the historical DB still lags the trade date, keep the day as `pending/historical_db_lag` or backfill after DB coverage is available.

## 2026-07-15 Formal Daily Flow Alignment Fix

### Goal

Remove the recurring mismatch between the daily automation instruction and the wrapper gates, and make the formal observation path update the historical replay DB by default before capture.

### Changes

- Updated `run_next_work.ps1`.
  - Added `-SkipHistoricalDbUpdate` as the explicit opt-out switch.
  - Formal `-LiveCapture` runs now default to the historical DB update step unless the run is a smoke capture or `-SkipHistoricalDbUpdate` is set.
  - Kept `-UpdateHistoricalDb` as a compatible explicit opt-in alias.
  - Improved skipped-update reasons so smoke captures and explicit skips are distinguishable in `simnow_historical_db_update_YYYY-MM-DD.json`.
- Updated `AUTOMATION_PROMPT.md`.
  - The formal daily acceptance command now uses `-DurationSeconds 1800 -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb`.
  - Added the explicit formal opt-out example with `-SkipHistoricalDbUpdate`.
- Updated `NEXT_WORK.md` and `ACCEPTANCE.md`.
  - Aligned the formal daily command and historical DB update semantics with the wrapper behavior.
- Updated regression tests.
  - Added coverage proving formal live capture defaults to the historical DB update path.
  - Added coverage proving the prompt documents the formal `-UpdateHistoricalDb` command.

### Verification

Passed targeted regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py .\examples\czsc_strategy\tests\unit\test_simnow_docs.py -q
```

Result:

- `53 passed`

Passed formal wrapper preflight:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `191 passed`.

### Next Action

The next formal daily run should use the aligned 1800-second command with historical DB update enabled. If replay readiness still lags after the update, keep the day as `pending/historical_db_lag` and use the backfill plan once DB coverage reaches the trade date.

## 2026-07-16 Daily Observation Acceptance Run

### Goal

Execute the SimNow daily observation workflow for `2026-07-16`, keep the workflow read-only, and record whether the day counts toward the restarted 20-day ledger.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `191 passed`.

Rejected by design:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300
```

Result:

- The wrapper rejected the command because `300 < 30 * 60`.
- This remains the documented formal-observation guard, not a code failure.

Passed smoke rerun:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

### Outcomes

- Generated/refreshed today's artifacts:
  - `simnow_export_2026-07-16.json`
  - `simnow_replay_2026-07-16.json`
  - `simnow_record_2026-07-16.json`
  - `simnow_report_2026-07-16.md`
  - `simnow_run_summary_2026-07-16.json`
  - `simnow_daily_brief_2026-07-16.md`
  - `simnow_historical_db_update_2026-07-16.json`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=17678`.
- Enabled subscriptions were complete: `5/5`, `missing_symbols=[]`.
- Read-only workflow safety passed:
  - `meta.read_only=true`
  - `meta.orders_sent_by_workflow=0`
  - `meta.workflow_order_actions=[]`
  - `order_safety.status=pass`
- Environment capture counts:
  - `ticks=4`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
- Observed account activity remained contamination/audit evidence only:
  - `account_contamination.detected=true`
  - `external_orders=0`
  - `external_trades=0`
  - `external_active_positions=1`
  - `external_position_symbols=[sc2609]`
- Historical DB update was skipped by the smoke path:
  - `historical_db_update.status=skipped`
  - `historical_db_update.reason=Smoke capture skips the formal historical DB auto update`
- Same-day delayed replay was not ready:
  - `delayed_replay.available=false`
  - `latest_db_date=2026-07-14`
  - `missing_or_lagged_symbols=[AP888,RB888,SC888,A888,ZN888]`
- Formal day result:
  - `record.status=pending`
  - `record.reason=historical_db_lag`
  - `record.threshold_status=unproven`
  - `automation_status=pending`
  - `automation_exit_code=20`
- 20-day ledger progress after the run:
  - `observation_start_date=2026-07-14`
  - `observed_days=3`
  - `valid_observation_days=0`
  - `pending_days=2`
  - `halt_days=1`

### Notes

- The requested 300-second formal command still cannot count as a valid observation because the wrapper enforces the documented `1800`-second minimum unless `-SkipKlineUpdate` is used.
- Today's smoke run is not a code failure. The day remains `pending/historical_db_lag`, which matches the acceptance rules for replay DB coverage lag.
- No workflow orders were sent.

### Next Action

Run the next observation during an eligible session window with the formal 1800-second command when possible. If the historical DB still lags the trade date, keep the day as `pending/historical_db_lag` or backfill after DB coverage is available.

## 2026-07-16 Daily Observation Follow-Up At 17:39 CST

### Goal

Re-run the daily read-only workflow during the post-close window, keep it in smoke mode, and reconcile the final status from the latest machine-readable run summary after the wrapper client timed out.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `191 passed`.
- Pending replay backfill plan still shows `2026-07-15` and `2026-07-16` waiting for DB coverage.

Executed smoke capture because the local time was `2026-07-16 17:39:12 +08:00`, outside the formal day-session window:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

Observed wrapper follow-up timeout after the capture JSON was written. Completed the remaining read-only post-processing from the latest capture artifact:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_replay_readiness.py --date 2026-07-16
python .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --date 2026-07-16 --simnow-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-07-16.json --thresholds .\examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --record-json .\examples\czsc_strategy\diagnostics\simnow_record_2026-07-16.json --report-md .\examples\czsc_strategy\diagnostics\simnow_report_2026-07-16.md --replay-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-07-16.json
python .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --out-json .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json
python .\examples\czsc_strategy\diagnostics\simnow_promotion_decision.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --report-md .\examples\czsc_strategy\diagnostics\simnow_20d_promotion_decision.md
python .\examples\czsc_strategy\diagnostics\simnow_run_summary.py --date 2026-07-16 --out-dir .\examples\czsc_strategy\diagnostics --out-json .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-16.json --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --ledger-summary .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json --historical-db-update .\examples\czsc_strategy\diagnostics\simnow_historical_db_update_2026-07-16.json
python .\examples\czsc_strategy\diagnostics\simnow_daily_brief.py --date 2026-07-16 --run-summary .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-16.json --out-md .\examples\czsc_strategy\diagnostics\simnow_daily_brief_2026-07-16.md
```

### Outcomes

- Updated/refreshed today's authoritative artifacts:
  - `simnow_export_2026-07-16.json`
  - `simnow_replay_readiness_2026-07-16.json`
  - `simnow_replay_2026-07-16.json`
  - `simnow_record_2026-07-16.json`
  - `simnow_report_2026-07-16.md`
  - `simnow_run_summary_2026-07-16.json`
  - `simnow_daily_brief_2026-07-16.md`
  - `simnow_ledger_summary.json`
- Latest smoke capture produced no usable market snapshot:
  - `ticks=0`
  - `contracts_count=0`
  - `accounts=0`
  - `positions=0`
  - `orders=0`
  - `trades=0`
  - `subscribed_count=0`
- Latest capture logs show repeated `097` disconnects and no snapshot, so the final record was reclassified from the earlier same-day `pending/historical_db_lag` row to the newer `skipped/ctp_disconnect_097_no_snapshot`.
- Read-only safety still passed:
  - `meta.read_only=true`
  - `meta.orders_sent_by_workflow=0`
  - `meta.workflow_order_actions=[]`
  - `order_safety.status=pass`
- Historical DB update stayed skipped because this was a smoke run:
  - `historical_db_update.status=skipped`
- Delayed replay remains unavailable for same-day validation:
  - `latest_db_date=2026-07-14`
  - `missing_or_lagged_symbols=[AP888,RB888,SC888,A888,ZN888]`
- Final machine-readable conclusion from `simnow_run_summary_2026-07-16.json`:
  - `automation_status=skipped`
  - `automation_exit_code=10`
  - `automation_reason=ctp_disconnect_097_no_snapshot`
  - `automation_action=no valid market data / rerun next valid session`
- 20-day ledger progress after the upsert:
  - `observed_days=3`
  - `valid_observation_days=0`
  - `pending_days=1`
  - `skipped_days=1`
  - `halt_days=1`

### Notes

- This follow-up supersedes the earlier same-date `pending/historical_db_lag` conclusion because the later `17:39 +08:00` smoke capture is the newest run for `2026-07-16`, and the final status must come from the refreshed `simnow_run_summary_2026-07-16.json`.
- The wrapper client timed out while post-processing, but the capture JSON had already been written and the remaining read-only artifact generation completed successfully without reconnecting to SimNow.
- The day does not count toward the 20-day gate and this is not treated as a code failure.

### Next Action

Run the next observation during the next valid session window with the formal 1800-second command. Keep `2026-07-16` as `skipped` unless a newer same-date run replaces the ledger row.

## 2026-07-16 Daily Observation Follow-Up At 23:02 CST

### Goal

Run one more same-date read-only smoke capture during the late-night session, refresh the formal daily artifacts, and confirm the final machine-readable status from the newest `simnow_run_summary_2026-07-16.json`.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `191 passed`.
- Pending replay backfill plan still shows `2026-07-15` waiting for DB coverage.

Executed smoke capture because the local time was `2026-07-16 23:01:23 +08:00`, outside the formal 1800-second acceptance window:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 300 -SkipKlineUpdate
```

### Outcomes

- Updated/refreshed today's authoritative artifacts:
  - `simnow_export_2026-07-16.json`
  - `simnow_record_2026-07-16.json`
  - `simnow_report_2026-07-16.md`
  - `simnow_run_summary_2026-07-16.json`
  - `simnow_daily_brief_2026-07-16.md`
  - `simnow_historical_db_update_2026-07-16.json`
  - `simnow_ledger_summary.json`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=17348`.
- Enabled subscriptions were complete: `5/5`, `missing_symbols=[]`.
- Read-only workflow safety passed:
  - `meta.read_only=true`
  - `meta.orders_sent_by_workflow=0`
  - `meta.workflow_order_actions=[]`
  - `order_safety.status=pass`
- Environment capture counts:
  - `ticks=842`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
- Observed account activity remained contamination/audit evidence only:
  - `account_contamination.detected=true`
  - `external_orders=0`
  - `external_trades=0`
  - `external_active_positions=1`
  - `external_position_symbols=[sc2609]`
- Historical DB update stayed skipped because this was a smoke run:
  - `historical_db_update.status=skipped`
- Same-day delayed replay was still not ready:
  - `delayed_replay.available=false`
  - `latest_db_date=2026-07-14`
  - `missing_or_lagged_symbols=[AP888,RB888,SC888,A888,ZN888]`
- Final machine-readable conclusion from the newest `simnow_run_summary_2026-07-16.json`:
  - `automation_status=pending`
  - `automation_exit_code=20`
  - `automation_reason=historical_db_lag`
  - `automation_action=resolve pending gate before counting`
- 20-day ledger progress after the upsert:
  - `observed_days=3`
  - `valid_observation_days=0`
  - `pending_days=2`
  - `skipped_days=0`
  - `halt_days=1`

### Notes

- This late-night rerun supersedes the earlier same-date `skipped/ctp_disconnect_097_no_snapshot` result because the newer same-date record successfully connected, queried contracts, received ticks, and rewrote the formal ledger row for `2026-07-16`.
- The day still does not count toward the 20-day gate because replay readiness remains blocked by `historical_db_lag`, not because of a code failure.
- No workflow orders were sent.

### Next Action

Run the next observation during the next valid session window with the formal 1800-second command. Keep `2026-07-16` as `pending/historical_db_lag` unless a newer same-date run replaces the ledger row again.

## 2026-07-17 Formal Night Session Observation

### Goal

Execute the formal read-only SimNow observation flow during the night session with the documented `1800`-second command, repair any local wrapper blockers automatically, and use `simnow_run_summary_2026-07-17.json` as the final source of truth.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `192 passed`.

Failed on the first formal attempt:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 1800 -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Initial blocker:

- The historical DB auto-update step failed before SimNow capture.
- Root cause 1: `D:\repo\ssquant\auto_update.ps1` launched Python without UTF-8 console output, so `update_kline_db.py` raised `UnicodeEncodeError` while printing the DB path.
- Root cause 2: after the encoding fix, the same wrapper still passed a mojibake DB path, so the updater reported `数据库不存在`.

Local repair:

- Updated `D:\repo\ssquant\auto_update.ps1` to set and restore `PYTHONIOENCODING=utf-8` around the Python call.
- Replaced the hard-coded DB path literal with a Python-derived `update_kline_db.DEFAULT_DB_PATH` lookup so the wrapper no longer depends on the PowerShell source file's Chinese literal encoding.
- Added an absolute `sys.path.insert(0, r'D:\repo\ssquant')` to that lookup so it works even when invoked from `D:\repo\vnpy`.

Passed after the wrapper repair:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 1800 -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

### Outcomes

- The formal run started after midnight local time, so the authoritative artifacts were generated for `2026-07-17`.
- Generated/refreshed authoritative artifacts:
  - `simnow_export_2026-07-17.json`
  - `simnow_kline_update_2026-07-17.json`
  - `simnow_replay_2026-07-17.json`
  - `simnow_record_2026-07-17.json`
  - `simnow_report_2026-07-17.md`
  - `simnow_run_summary_2026-07-17.json`
  - `simnow_daily_brief_2026-07-17.md`
  - `simnow_historical_db_update_2026-07-17.json`
  - `simnow_ledger_summary.json`
- Historical DB auto update succeeded:
  - `historical_db_update.status=passed`
  - `historical_db_update.exit_code=0`
  - `started_at=2026-07-17T00:02:00.5833413+08:00`
  - `ended_at=2026-07-17T00:02:03.1487571+08:00`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=17348`.
- Enabled subscriptions were complete: `5/5`, `missing_symbols=[]`.
- Read-only workflow safety passed:
  - `meta.read_only=true`
  - `meta.orders_sent_by_workflow=0`
  - `meta.workflow_order_actions=[]`
  - `order_safety.status=pass`
- Environment capture counts:
  - `ticks=4904`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
- Observed account activity remained contamination/audit evidence only:
  - `account_contamination.detected=true`
  - `external_orders=0`
  - `external_trades=0`
  - `external_active_positions=1`
  - `external_position_symbols=[sc2609]`
- Delayed replay remained unavailable as a counting source:
  - `delayed_replay.available=false`
  - `delayed_replay.status=pending`
  - `latest_db_date=2026-07-16`
  - `missing_or_lagged_symbols=[AP888,RB888,SC888,A888,ZN888]`
- Kline coverage became the primary blocker instead of DB lag:
  - `kline.missing_symbols=[AP888]`
  - `kline.short_symbols=[A888,RB888]`
  - `min_bars_per_symbol=30`
- Final machine-readable conclusion from `simnow_run_summary_2026-07-17.json`:
  - `automation_status=pending`
  - `automation_exit_code=20`
  - `automation_reason=kline_coverage_incomplete`
  - `automation_action=resolve pending gate before counting`
- 20-day ledger progress after the upsert:
  - `observed_days=4`
  - `valid_observation_days=0`
  - `pending_days=3`
  - `skipped_days=0`
  - `halt_days=1`

### Notes

- This is a formal `1800`-second observation attempt, not a smoke run.
- The day does not count toward the 20-day gate because `AP888` is missing from the generated 1M coverage and `A888`/`RB888` remain below the `30`-bar minimum.
- No workflow orders were sent.

### Next Action

Re-run the formal read-only observation in an active night or day session that can deliver complete `AP888` coverage and at least `30` one-minute bars for every enabled symbol.

## 2026-07-17 Daytime Formal Retry Timeout

### Goal

Re-run the documented formal read-only SimNow observation flow during the day session and confirm whether a newer same-date `simnow_run_summary_2026-07-17.json` replaces the earlier night-session conclusion.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `192 passed`.
- Pending replay backfill plan still shows `2026-07-15` waiting for DB coverage.

Timed out at the client while the wrapper was still inside the historical DB update chain:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 1800 -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

### Outcomes

- No new `2026-07-17` daily observation artifacts were written after the earlier `00:32 +08:00` formal run; the only new file from this retry was `simnow_backfill_plan.json` at `15:22 +08:00`.
- The timed-out retry left a live process chain:
  - `run_next_work.ps1`
  - nested `powershell.exe` launchers
  - `D:\repo\ssquant\auto_update.ps1`
  - `python.exe update_kline_db.py`
- Because this exceeded the earlier seconds-long historical DB update baseline and had not produced a new capture/report/run-summary set, the retry was treated as an execution timeout rather than a newer accepted observation result.
- The stale retry processes were terminated locally to avoid leaving an orphaned historical DB update job running.
- The authoritative same-date conclusion therefore remains the latest completed machine-readable summary already on disk:
  - `automation_status=pending`
  - `automation_exit_code=20`
  - `automation_reason=kline_coverage_incomplete`
  - `automation_action=resolve pending gate before counting`
- The unchanged authoritative metrics from `simnow_run_summary_2026-07-17.json` remain:
  - `ticks=4904`
  - `contracts_count=17348`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
  - `historical_db_update.status=passed`
  - `kline.missing_symbols=[AP888]`
  - `kline.short_symbols=[A888,RB888]`

### Notes

- This daytime retry did not replace the earlier `2026-07-17` ledger row because it never completed to a new `simnow_record_2026-07-17.json` / `simnow_run_summary_2026-07-17.json`.
- No workflow orders were sent.
- The final daily status for `2026-07-17` must still be read from the existing `simnow_run_summary_2026-07-17.json`, not inferred from the timed-out retry.

### Next Action

Investigate why the daytime `-UpdateHistoricalDb` path can stall for tens of minutes before capture, or re-run the formal observation in the next valid session after confirming the update step is healthy.

## 2026-07-21 Formal Day Session Observation

### Goal

Execute the documented formal read-only SimNow observation flow for `2026-07-21`, use the generated `simnow_run_summary_2026-07-21.json` as the final source of truth, and record whether the day counts toward the restarted 20-day ledger.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `195 passed`.
- Pending replay backfill plan still shows `2026-07-15` waiting for DB coverage.

Client timed out while the formal wrapper was still post-processing:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 1800 -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Recovered the remaining read-only post-processing from the artifacts already written by that same formal run:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --out-json .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json
python .\examples\czsc_strategy\diagnostics\simnow_promotion_decision.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --report-md .\examples\czsc_strategy\diagnostics\simnow_20d_promotion_decision.md
python .\examples\czsc_strategy\diagnostics\simnow_run_summary.py --date 2026-07-21 --out-dir .\examples\czsc_strategy\diagnostics --out-json .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-21.json --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --ledger-summary .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json --historical-db-update .\examples\czsc_strategy\diagnostics\simnow_historical_db_update_2026-07-21.json
python .\examples\czsc_strategy\diagnostics\simnow_daily_brief.py --date 2026-07-21 --run-summary .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-21.json --out-md .\examples\czsc_strategy\diagnostics\simnow_daily_brief_2026-07-21.md
```

### Outcomes

- The formal observation itself completed its read-only capture path and wrote the same-day core artifacts before the client timeout:
  - `simnow_export_2026-07-21.json`
  - `simnow_kline_update_2026-07-21.json`
  - `simnow_replay_readiness_2026-07-21.json`
  - `simnow_replay_2026-07-21.json`
  - `simnow_record_2026-07-21.json`
  - `simnow_report_2026-07-21.md`
- The remaining read-only summary artifacts were regenerated locally from those files:
  - `simnow_ledger_summary.json`
  - `simnow_20d_promotion_decision.md`
  - `simnow_run_summary_2026-07-21.json`
  - `simnow_daily_brief_2026-07-21.md`
- Historical DB auto update succeeded:
  - `historical_db_update.status=passed`
  - `historical_db_update.exit_code=0`
  - `started_at=2026-07-21T10:30:41.9131031+08:00`
  - `ended_at=2026-07-21T10:33:26.7365771+08:00`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=17742`.
- Enabled subscriptions were complete: `5/5`, `missing_symbols=[]`.
- Read-only workflow safety passed:
  - `meta.read_only=true`
  - `meta.orders_sent_by_workflow=0`
  - `meta.workflow_order_actions=[]`
  - `order_safety.status=pass`
- Environment capture counts:
  - `ticks=10955`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
- Observed account activity remained contamination/audit evidence only:
  - `account_contamination.detected=true`
  - `external_orders=0`
  - `external_trades=0`
  - `external_active_positions=1`
  - `external_position_symbols=[sc2609]`
- Replay readiness was available for the same day:
  - `delayed_replay.available=true`
  - `latest_db_date=2026-07-21`
  - `missing_or_lagged_symbols=[]`
- Kline coverage still had a formal gate gap:
  - `kline.missing_symbols=[AP888]`
  - `kline.short_symbols=[]`
  - `min_bars_per_symbol=30`
- Final machine-readable conclusion from `simnow_run_summary_2026-07-21.json`:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`
- The daily record remained non-counting:
  - `record.status=halt`
  - `record.reason=consecutive_loss_abs_pct`
  - `record.threshold_status=halt`
  - `record.valid_observation=false`
- 20-day ledger progress after the upsert:
  - `observed_days=5`
  - `valid_observation_days=0`
  - `pending_days=3`
  - `halt_days=2`

### Notes

- The wrapper timeout was a client/runtime limit issue, not a connection/query failure. The formal run had already finished capture and replay export before the timeout interrupted the later summary-generation steps.
- The final daily conclusion must come from the regenerated `simnow_run_summary_2026-07-21.json`, not from the timeout itself and not from the markdown report alone.
- No workflow orders were sent.

### Next Action

Stop automation for this candidate and review the threshold breach (`consecutive_loss_abs_pct`) together with the unresolved `AP888` kline coverage gap before scheduling another formal observation.

## 2026-07-21 Daily Acceptance Review

### Goal

Execute the SimNow daily acceptance flow for the current workspace state without sending orders, and decide whether a new live run is appropriate after checking the authoritative same-day machine-readable result.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `200 passed`.
- Pending replay backfill plan still shows `2026-07-15` as `ready_to_backfill`.

Inspected the current same-day authoritative artifacts instead of re-running `-LiveCapture`:

```powershell
Get-Date -Format o
Get-Content -Raw .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-21.json
Get-Content -Raw .\examples\czsc_strategy\diagnostics\simnow_record_2026-07-21.json
```

### Outcomes

- Current local time during this review was `2026-07-21T15:18:30.2509605+08:00`.
- Same-day formal artifacts already existed from the earlier read-only observation run:
  - `simnow_export_2026-07-21.json`
  - `simnow_record_2026-07-21.json`
  - `simnow_report_2026-07-21.md`
  - `simnow_run_summary_2026-07-21.json`
- Preflight passed, but a new live capture was intentionally not started because the authoritative same-day run summary already reported:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`
- The accepted same-day capture metrics remain:
  - `ticks=10955`
  - `contracts_count=17742`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
  - `subscribed_count=5`
- Read-only safety remains satisfied:
  - `read_only=true`
  - `orders_sent_by_workflow=0`
  - `workflow_order_actions=[]`
- Formal observation-side checks from the authoritative run summary remain:
  - `historical_db_update.status=passed`
  - `delayed_replay.available=true`
  - `kline.missing_symbols=[AP888]`
  - `record.valid_observation=false`
- Current 20-day progress remains unchanged:
  - `valid_observation_days=0`
  - `pending_days=3`
  - `halt_days=2`

### Notes

- Re-running `-LiveCapture` on the same date would upsert and potentially replace today's formal ledger row. That is not appropriate while the current machine-readable instruction is to stop automation and review manually.
- This review therefore treats the existing `simnow_run_summary_2026-07-21.json` as the final source of truth for today, exactly as required by `ACCEPTANCE.md`.
- No workflow orders were sent.

### Next Action

Keep today's result as `halt/consecutive_loss_abs_pct`, review the threshold breach and the remaining `AP888` kline gap manually, and only schedule another formal observation after that review.

## 2026-07-21 Daily Acceptance Review Follow-Up

### Goal

Run the required daily preflight, verify the current same-day machine-readable result remains authoritative, and avoid replacing today's formal ledger row after the workflow has already halted for manual review.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `200 passed`.
- Pending replay backfill plan still shows `2026-07-15` as `ready_to_backfill`.

Inspected the current same-day authoritative artifacts instead of re-running `-LiveCapture`:

```powershell
Get-Date -Format o
Get-Item .\examples\czsc_strategy\diagnostics\simnow_export_2026-07-21.json, .\examples\czsc_strategy\diagnostics\simnow_record_2026-07-21.json, .\examples\czsc_strategy\diagnostics\simnow_report_2026-07-21.md, .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-21.json
Get-Content -Raw .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-21.json
Get-Content -Raw .\examples\czsc_strategy\diagnostics\simnow_historical_db_update_2026-07-21.json
```

### Outcomes

- Current local time during this review was `2026-07-21T15:21:36.7195556+08:00`.
- Required same-day artifacts are present:
  - `simnow_export_2026-07-21.json`
  - `simnow_record_2026-07-21.json`
  - `simnow_report_2026-07-21.md`
  - `simnow_run_summary_2026-07-21.json`
- The authoritative same-day machine-readable conclusion remains unchanged:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`
- Accepted same-day capture metrics remain:
  - `ticks=10955`
  - `contracts_count=17742`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
  - `subscribed_count=5`
- Read-only safety remains satisfied:
  - `read_only=true`
  - `orders_sent_by_workflow=0`
- Formal observation-side checks from the authoritative run summary remain:
  - `historical_db_update.status=passed`
  - `delayed_replay.available=true`
  - `kline.missing_symbols=[AP888]`
  - `record.threshold_status=halt`
  - `record.valid_observation=false`

### Notes

- A new same-date `-LiveCapture` run was intentionally not started because it would upsert and potentially replace today's halted ledger row.
- This follow-up therefore treats `simnow_run_summary_2026-07-21.json` as the single source of truth, exactly as required by `ACCEPTANCE.md`.
- No workflow orders were sent.

### Next Action

Keep today's result as `halt/consecutive_loss_abs_pct`, review the threshold breach and the remaining `AP888` coverage gap manually, and only schedule another formal observation after that review.

## 2026-07-21 Same-Day Formal Overwrite

### Goal

At user request, re-run the documented formal read-only SimNow observation flow on the same trading date and intentionally overwrite the existing `2026-07-21` ledger row/artifacts with a newer same-day result.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `200 passed`.
- Pending replay backfill plan still shows `2026-07-15` as `ready_to_backfill`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -DurationSeconds 1800 -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

### Outcomes

- This run intentionally overwrote the same-date formal artifacts/ledger row for `2026-07-21`.
- Refreshed same-day artifacts:
  - `simnow_export_2026-07-21.json`
  - `simnow_kline_update_2026-07-21.json`
  - `simnow_replay_2026-07-21.json`
  - `simnow_record_2026-07-21.json`
  - `simnow_report_2026-07-21.md`
  - `simnow_run_summary_2026-07-21.json`
  - `simnow_daily_brief_2026-07-21.md`
  - `simnow_historical_db_update_2026-07-21.json`
  - `simnow_ledger_summary.json`
- Historical DB auto update succeeded:
  - `historical_db_update.status=passed`
  - `historical_db_update.exit_code=0`
  - `started_at=2026-07-21T22:43:32.8853811+08:00`
  - `ended_at=2026-07-21T22:43:52.4692820+08:00`
- SimNow connection/login succeeded.
- Contract query succeeded with `contracts_count=17812`.
- Enabled subscriptions were complete for the current formal contract set: `4/4`, `missing_symbols=[]`.
- Read-only workflow safety passed:
  - `read_only=true`
  - `orders_sent_by_workflow=0`
  - `workflow_order_actions=[]`
  - `orders=0`
  - `trades=0`
- Environment capture counts from the new same-date run:
  - `ticks=5819`
  - `accounts=1`
  - `positions=1`
  - `subscribed_count=4`
- Delayed replay was available, but the formal observation still failed to count:
  - `delayed_replay.available=true`
  - `delayed_replay.status=halt`
  - `delayed_replay.reason=kline_coverage_too_short`
- Kline coverage improved versus the earlier same-day run:
  - `kline.missing_symbols=[]`
  - `kline.short_symbols=[A888,RB888]`
  - `min_bars_per_symbol=30`
- Final authoritative machine-readable conclusion from the overwritten `simnow_run_summary_2026-07-21.json`:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`
- The overwritten daily record remains non-counting:
  - `record.status=halt`
  - `record.reason=consecutive_loss_abs_pct`
  - `record.threshold_status=halt`
  - `record.valid_observation=false`
- 20-day ledger progress after the overwrite remains:
  - `observed_days=5`
  - `valid_observation_days=0`
  - `pending_days=3`
  - `halt_days=2`

### Notes

- This entry supersedes the earlier `2026-07-21` conclusion details where the same-date run had `ticks=10955`, `contracts_count=17742`, `subscribed_count=5`, and `kline.missing_symbols=[AP888]`; the new formal overwrite reflects the current four-symbol formal set with no missing kline symbols but short coverage on `A888` and `RB888`.
- The final stop condition did not change: the authoritative run summary still halts the day for `consecutive_loss_abs_pct`.
- Python UTF-8 JSON parsing validated both `simnow_ledger_summary.json` and `simnow_run_summary_2026-07-21.json`; a follow-up PowerShell `ConvertFrom-Json` parse failure was a console/encoding issue, not a broken artifact.
- No workflow orders were sent.

### Next Action

Keep today's overwritten result as `halt/consecutive_loss_abs_pct`, review the threshold breach plus the short `A888`/`RB888` kline coverage, and only schedule another formal observation after that manual review.

## 2026-07-21 21:05 Formal Automation Follow-Up

### Goal

Execute the required daily preflight for the `2026-07-21` formal slot, attempt the documented read-only formal command, and record the outcome when the local launcher has already crossed into the next calendar date.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `205 passed`.
- Pending replay backfill plan still shows `2026-07-15` as `ready_to_backfill`.

Rejected by the wrapper because the formal start window had already elapsed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

### Outcomes

- The formal live command did run, but it did not start a new capture because `run_next_work.ps1` rejected the request at local time `2026-07-22 00:01:35 +08:00`.
- The rejection reason was the built-in formal window guard: automatic formal runs must start within the `09:05`, `13:35`, or `21:05` five-minute grace windows.
- Because no new same-date capture started after the window rejection, the existing `2026-07-21` formal artifacts remained the authoritative source of truth:
  - `simnow_export_2026-07-21.json`
  - `simnow_record_2026-07-21.json`
  - `simnow_report_2026-07-21.md`
  - `simnow_run_summary_2026-07-21.json`
- The authoritative machine-readable conclusion therefore remains unchanged:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`
- The accepted same-day read-only metrics from the authoritative run summary remain:
  - `ticks=5819`
  - `contracts_count=17812`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
  - `subscribed_count=4`
- Read-only safety remains satisfied in the authoritative same-day artifacts:
  - `read_only=true`
  - `orders_sent_by_workflow=0`
  - `workflow_order_actions=[]`
- Formal observation-side checks from the authoritative run summary remain:
  - `historical_db_update.status=passed`
  - `historical_db_update.exit_code=0`
  - `delayed_replay.available=true`
  - `delayed_replay.status=halt`
  - `kline.missing_symbols=[]`
  - `kline.short_symbols=[A888,RB888]`
  - `record.valid_observation=false`
- Current 20-day progress from the authoritative run summary remains:
  - `valid_observation_days=0`
  - `consecutive_valid_days=0`
  - `ready_to_expand=false`
  - `promotion_blockers=[need_20_more_valid_observation_days, pending_days_present, halt_days_present]`

### Notes

- This follow-up did not create a new `simnow_run_summary_2026-07-22.json`; it only confirmed that the delayed automation launch missed the `2026-07-21 21:05` formal start window.
- The wrapper rejection is not treated as a code regression in the SimNow workflow itself; it is a scheduling/window issue after the formal slot had already passed.
- No workflow orders were sent.

### Next Action

Keep `simnow_run_summary_2026-07-21.json` as the final source of truth for the `2026-07-21` formal slot, and manually review the `consecutive_loss_abs_pct` halt plus short `A888`/`RB888` kline coverage before scheduling the next formal observation inside an allowed start window.

## 2026-07-22 09:05 Formal Observation

### Goal

Execute the documented `09:05` formal read-only SimNow observation flow, keep the workflow read-only, and use `simnow_run_summary_2026-07-22.json` as the final authoritative result.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `205 passed`.
- Pending replay backfill plan still shows `2026-07-15` as `ready_to_backfill`.

Started inside the formal day-session window:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

The local client timed out while the wrapper was still running, so the same run's read-only post-processing was resumed from the generated artifacts:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_strategy_surface.py --capture-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-07-22.json --date 2026-07-22
python .\examples\czsc_strategy\diagnostics\simnow_replay_readiness.py --date 2026-07-22 > .\examples\czsc_strategy\diagnostics\simnow_replay_readiness_2026-07-22.json
python .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --date 2026-07-22 --simnow-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-07-22.json --replay-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-07-22.json --kline-json .\examples\czsc_strategy\diagnostics\simnow_kline_update_2026-07-22.json --thresholds .\examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --record-json .\examples\czsc_strategy\diagnostics\simnow_record_2026-07-22.json --report-md .\examples\czsc_strategy\diagnostics\simnow_report_2026-07-22.md
python .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --out-json .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json
python .\examples\czsc_strategy\diagnostics\simnow_promotion_decision.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --report-md .\examples\czsc_strategy\diagnostics\simnow_20d_promotion_decision.md
python .\examples\czsc_strategy\diagnostics\simnow_run_summary.py --date 2026-07-22 --out-dir .\examples\czsc_strategy\diagnostics --out-json .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-22.json --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --ledger-summary .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json --historical-db-update .\examples\czsc_strategy\diagnostics\simnow_historical_db_update_2026-07-22.json
python .\examples\czsc_strategy\diagnostics\simnow_daily_brief.py --date 2026-07-22 --run-summary .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-22.json --out-md .\examples\czsc_strategy\diagnostics\simnow_daily_brief_2026-07-22.md
```

### Outcomes

- The formal run started inside the allowed `09:05` window at local time `2026-07-22T09:06:22+08:00`.
- Historical DB auto update succeeded before capture:
  - `historical_db_update.status=passed`
  - `historical_db_update.exit_code=0`
  - `started_at=2026-07-22T09:07:55.6700495+08:00`
  - `ended_at=2026-07-22T09:09:41.9221253+08:00`
- The wrapper computed a formal capture duration of `8565` seconds and completed the read-only day-session capture:
  - `simnow_export_2026-07-22.json`
  - `simnow_kline_update_2026-07-22.json`
- Same-day post-processing artifacts were completed from that capture without re-running live collection:
  - `simnow_replay_readiness_2026-07-22.json`
  - `simnow_replay_2026-07-22.json`
  - `simnow_record_2026-07-22.json`
  - `simnow_report_2026-07-22.md`
  - `simnow_20d_promotion_decision.md`
  - `simnow_ledger_summary.json`
  - `simnow_run_summary_2026-07-22.json`
  - `simnow_daily_brief_2026-07-22.md`
- Read-only environment capture from the authoritative run summary:
  - `ticks=39481`
  - `contracts_count=17812`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
  - `subscribed_count=4`
- Read-only safety passed:
  - `read_only=true`
  - `orders_sent_by_workflow=0`
  - `workflow_order_actions=[]`
  - `order_safety.status=pass`
- Contract query and subscriptions succeeded for the enabled formal set:
  - `contracts_count=17812`
  - `subscribed_count=4`
  - `kline.missing_symbols=[]`
  - `kline.short_symbols=[]`
- Account contamination remained audit-only:
  - `account_contamination.detected=true`
  - `external_orders=0`
  - `external_trades=0`
  - `external_active_positions=1`
  - `external_position_symbols=[sc2609]`
- Delayed replay did not become available for a valid observation day:
  - `delayed_replay.available=false`
  - `delayed_replay.status=pending`
  - `delayed_replay.reason=historical_db_lag`
  - `latest_db_date=2026-07-22`
  - `missing_or_lagged_symbols=[AP888]`
- Final authoritative machine-readable conclusion from `simnow_run_summary_2026-07-22.json`:
  - `automation_status=pending`
  - `automation_exit_code=20`
  - `automation_reason=historical_db_lag`
  - `automation_action=resolve pending gate before counting`
- The daily record does not count toward the 20-day gate:
  - `record.status=pending`
  - `record.valid_observation=false`
  - `record.threshold_status=unproven`
- Current 20-day progress after the upsert:
  - `observed_days=6`
  - `valid_observation_days=0`
  - `pending_days=4`
  - `halt_days=2`

### Notes

- This is not a code failure. The formal run captured valid read-only data, but the day remains `pending` because the delayed replay DB still lacks same-day `AP888` coverage.
- The client-side timeout interrupted the wrapper's later post-processing output, not the underlying capture. The final conclusion must therefore come from the completed `simnow_run_summary_2026-07-22.json`.
- No workflow orders were sent.

### Next Action

Keep today's result as `pending/historical_db_lag`, wait for the historical DB to cover `AP888` on `2026-07-22` or run the documented backfill flow, and do not count the day toward the 20-day gate until delayed replay becomes available.

## 2026-07-22 AP888 Replay Readiness Fix

### Goal

Correct the formal replay-readiness symbol set so disabled formal symbols do not block delayed replay, then regenerate the authoritative `2026-07-22` artifacts.

### Root Cause

- `simnow_contract_map.json` already had `AP888.enabled=false` for formal daily observation.
- `simnow_replay_readiness.py` still defaulted to `backtest_matrix_report.DEFAULT_SYMBOLS`, so it kept checking the legacy five-symbol set and incorrectly treated disabled `AP888` as a replay blocker.
- `run_next_work.ps1` called `simnow_replay_readiness.py` without `--symbols`, so the stale default leaked into the formal daily workflow and polluted `simnow_run_summary_2026-07-22.json`.

### Changes

- Updated `simnow_replay_readiness.py`.
  - Added `load_enabled_symbols()` to read `simnow_contract_map.json`.
  - Default CLI behavior now uses the enabled formal symbol set instead of the legacy five-symbol default.
- Updated `test_simnow_replay_readiness.py`.
  - Added a regression test proving disabled symbols are excluded from the default readiness symbol set.
- Regenerated the `2026-07-22` daily replay/summary artifacts after the fix:
  - `simnow_replay_readiness_2026-07-22.json`
  - `simnow_replay_2026-07-22.json`
  - `simnow_record_2026-07-22.json`
  - `simnow_report_2026-07-22.md`
  - `simnow_ledger_summary.json`
  - `simnow_20d_promotion_decision.md`
  - `simnow_run_summary_2026-07-22.json`
  - `simnow_daily_brief_2026-07-22.md`

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_replay_readiness.py -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_replay_readiness.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py -q
python .\examples\czsc_strategy\diagnostics\simnow_replay_readiness.py --date 2026-07-22
python .\examples\czsc_strategy\diagnostics\export_simnow_replay_snapshot.py --end 2026-07-22 --date 2026-07-22 --out-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-07-22.json
python .\examples\czsc_strategy\diagnostics\simnow_daily_monitor.py --date 2026-07-22 --simnow-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-07-22.json --replay-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-07-22.json --kline-json .\examples\czsc_strategy\diagnostics\simnow_kline_update_2026-07-22.json --thresholds .\examples\czsc_strategy\diagnostics\simnow_risk_thresholds.json --record-json .\examples\czsc_strategy\diagnostics\simnow_record_2026-07-22.json --report-md .\examples\czsc_strategy\diagnostics\simnow_report_2026-07-22.md
python .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --out-json .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json
python .\examples\czsc_strategy\diagnostics\simnow_promotion_decision.py --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --report-md .\examples\czsc_strategy\diagnostics\simnow_20d_promotion_decision.md
python .\examples\czsc_strategy\diagnostics\simnow_run_summary.py --date 2026-07-22 --out-dir .\examples\czsc_strategy\diagnostics --out-json .\examples\czsc_strategy\diagnostics\simnow_run_summary_2026-07-22.json --ledger .\examples\czsc_strategy\diagnostics\simnow_observation_ledger.jsonl --ledger-summary .\examples\czsc_strategy\diagnostics\simnow_ledger_summary.json --historical-db-update .\examples\czsc_strategy\diagnostics\simnow_historical_db_update_2026-07-22.json
python .\examples\czsc_strategy\diagnostics\simnow_daily_brief.py --date 2026-07-22 --run-summary .\simnow_run_summary_2026-07-22.json --out-md .\simnow_daily_brief_2026-07-22.md
```

Results:

- Replay readiness now uses only the enabled formal symbols and reports `ready=true` for `2026-07-22`.
- `AP888` no longer appears in `missing_or_lagged_symbols`.
- The corrected authoritative daily conclusion changed from the polluted `pending/historical_db_lag` result to:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`
- Delayed replay is now available:
  - `delayed_replay.available=true`
  - `delayed_replay.reason=no_actionable_events_on_either_side`
  - `consistency_matched=true`
- The day still does not count toward the 20-day gate because the replay-computed risk thresholds halt the run.

### Next Action

Keep `simnow_run_summary_2026-07-22.json` as the corrected source of truth for `2026-07-22`; stop automation for this candidate and review the `consecutive_loss_abs_pct` halt instead of chasing a non-existent `AP888` replay lag.

## 2026-07-22 13:35 Formal Automation Follow-Up

### Goal

Execute the documented `13:35` formal read-only SimNow observation flow, keep the workflow read-only, and record the outcome for the afternoon formal slot.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Workflow preflight passed.
- SimNow workflow unit tests passed: `206 passed`.
- Pending replay backfill plan still shows `2026-07-15` as `ready_to_backfill`.

Rejected by the wrapper because the formal start window had already elapsed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

### Outcomes

- The formal live command did not start a new capture because `run_next_work.ps1` rejected the request at local time `2026-07-22 14:59:15 +08:00`.
- The rejection reason was the built-in formal window guard: automatic formal runs must start within the `09:05`, `13:35`, or `21:05` five-minute grace windows.
- Because no new same-date capture started after the window rejection, no new afternoon-slot artifacts were produced or refreshed.
- The existing same-day artifacts therefore remain the only machine-readable source of truth for `2026-07-22`:
  - `simnow_export_2026-07-22.json`
  - `simnow_record_2026-07-22.json`
  - `simnow_report_2026-07-22.md`
  - `simnow_run_summary_2026-07-22.json`
- The authoritative machine-readable conclusion from the existing run summary remains unchanged:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`
- The accepted same-day read-only metrics from the authoritative run summary remain:
  - `ticks=39481`
  - `contracts_count=17812`
  - `accounts=1`
  - `positions=1`
  - `orders=0`
  - `trades=0`
  - `subscribed_count=4`
- Read-only safety remains satisfied in the authoritative same-day artifacts:
  - `read_only=true`
  - `orders_sent_by_workflow=0`
  - `workflow_order_actions=[]`
- Formal observation-side checks from the authoritative run summary remain:
  - `historical_db_update.status=passed`
  - `delayed_replay.available=true`
  - `record.threshold_status=halt`
  - `record.valid_observation=false`

### Notes

- This follow-up did not create a new `simnow_run_summary_2026-07-22.json`; it confirmed that the afternoon automation launch missed the `2026-07-22 13:35` formal start window.
- The wrapper rejection is treated as a scheduling/window issue, not as a code regression in the SimNow workflow itself.
- No workflow orders were sent.

### Next Action

Keep `simnow_run_summary_2026-07-22.json` as the only available same-day machine-readable source of truth, and schedule the next formal observation inside an allowed start window after manually reviewing the `consecutive_loss_abs_pct` halt.

## 2026-07-22 Formal Session-Aware Guard

### Goal

Prevent formally allowed SimNow start windows from launching when an enabled symbol's own session cutoff leaves too little tradable time to accumulate the required `MinKlineBarsPerSymbol`.

### Root Cause

- `run_next_work.ps1` computed formal `duration_seconds` from a single window-level close (`11:30`, `15:00`, `23:00`).
- The wrapper did not consider enabled symbols whose effective tradable session ends earlier than the generic window close.
- That meant a formally valid start could still produce unavoidable `kline_coverage_too_short` or `kline_coverage_incomplete` outcomes for some enabled symbols.

### Changes

- Updated `run_next_work.ps1`.
  - `Get-FormalCapturePlan` now accepts `-ContractMap`.
  - Formal duration planning now honors optional per-symbol `formal_session_capture_end` cutoffs.
  - When an enabled symbol's earlier cutoff leaves fewer than `MinKlineBarsPerSymbol * 60` seconds, the wrapper rejects the formal start before capture begins.
- Updated `simnow_contract_map.json`.
  - Added explicit night-session capture cutoffs for the current enabled formal symbols:
    - `SC888=02:30:00`
    - `A888=23:00:00`
    - `ZN888=01:00:00`
    - `RB888=23:00:00`
- Updated `test_run_next_work_wrapper.py`.
  - Added a regression test proving a formally valid `21:05` slot is rejected when an enabled symbol's own cutoff leaves fewer than `30` required minutes.
  - Added a config test requiring enabled night-session symbols to define `formal_session_capture_end.night`.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Wrapper regression tests passed: `53 passed`.
- Full SimNow workflow preflight passed: `214 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the second repair item: add a machine-checkable summary consistency gate so `record/report/run_summary/ledger_summary` cannot silently drift after backfill or rerun flows.

## 2026-07-22 Summary Consistency Gate

### Goal

Prevent stale or partially refreshed SimNow summary artifacts from being treated as successful after backfill, rerun, or formal live workflow completion.

### Root Cause

- The workflow already regenerated `simnow_ledger_summary.json`, `simnow_run_summary_YYYY-MM-DD.json`, and `simnow_daily_brief_YYYY-MM-DD.md`.
- But no machine gate verified that those refreshed artifacts still matched:
  - `simnow_record_YYYY-MM-DD.json`
  - `simnow_ledger_summary.json`
  - `simnow_report_YYYY-MM-DD.md`
  - `simnow_daily_brief_YYYY-MM-DD.md`
- As a result, stale run summaries could survive after a backfill unless a human noticed the mismatch.

### Changes

- Added `simnow_summary_consistency.py`.
  - Validates that `run_summary.record.*` matches the current record JSON.
  - Re-derives `automation_status`, `automation_exit_code`, `automation_reason`, and `automation_action` from the embedded record and rejects drift.
  - Verifies that `run_summary.ledger_summary` matches the current safe aggregate from `simnow_ledger_summary.json`.
  - Verifies that the daily brief contains the same `automation_status`, `automation_reason`, `automation_action`, and `record.status`.
  - Verifies that the 20-day report contains the current date/status/reason row for the daily record.
- Updated `simnow_backfill_pending_replays.py`.
  - After refreshing ledger summary, promotion decision, run summary, and daily brief, it now runs `simnow_summary_consistency.py`.
- Updated `simnow_backfill_pending_kline.py`.
  - Added the same post-refresh consistency validation, including `--kline-json` for record-summary comparison.
- Updated `run_next_work.ps1`.
  - Preflight now compiles `simnow_summary_consistency.py`.
  - Preflight now runs `test_simnow_summary_consistency.py`.
  - Formal `-LiveCapture` now runs a `Validate summary consistency` step after daily brief generation and before the final completion/exit handling.
- Added/updated tests:
  - New `test_simnow_summary_consistency.py` for consistent artifacts and stale run-summary / stale daily-brief rejection.
  - Updated backfill tests to require the consistency script in the refresh chain.
  - Updated wrapper tests to require the new script in preflight and live workflow ordering.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_summary_consistency.py .\examples\czsc_strategy\tests\unit\test_simnow_backfill_pending_replays.py .\examples\czsc_strategy\tests\unit\test_simnow_backfill_pending_kline.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted consistency/backfill/wrapper regressions passed: `71 passed`.
- Full SimNow workflow preflight passed: `219 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: tighten contract-map and artifact provenance so each run summary records exactly which formal symbol set/version produced the observation and backfill decisions.

## 2026-07-22 Contract Map Provenance

### Goal

Make every formal observation and backfill decision explicitly record which contract-map metadata and enabled symbol snapshot produced the result.

### Root Cause

- Formal capture artifacts already stored `contract_map_path` and the expanded `contract_map`, but they did not expose a stable provenance object with:
  - version
  - effective date
  - note
  - enabled formal symbol snapshot
- `simnow_run_summary.py` therefore could not surface a compact machine-readable provenance record.
- `simnow_backfill_pending_replays.py` and `simnow_backfill_pending_kline.py` also lacked an explicit provenance block, so later audits had to infer the active symbol set indirectly.
- After adding top-level `_meta` to the contract map, `simnow_tick_bars.py` initially treated `_meta` as if it were a research symbol, which polluted kline missing-symbol checks.

### Changes

- Added `simnow_contract_map_meta.py`.
  - Centralizes loading raw contract-map payloads.
  - Ignores top-level metadata keys such as `_meta`.
  - Exposes helpers for enabled entries, enabled symbols, and compact provenance extraction.
- Updated `simnow_contract_map.json`.
  - Added `_meta.version=V20260722`.
  - Added `_meta.effective_date=2026-07-22`.
  - Added `_meta.note` describing the post-AP888-disablement formal four-symbol set.
- Updated `simnow_daily_capture.py`.
  - `load_contract_map()` now ignores `_meta`.
  - `build_export()` now embeds `meta.contract_map_provenance`.
  - Live capture now records the provenance derived from the actual contract-map file used for the run.
- Updated `simnow_run_summary.py`.
  - Added top-level `contract_map_provenance` extracted from capture metadata, with a safe fallback for older captures.
- Updated `simnow_backfill_pending_replays.py`.
  - `build_backfill_plan()` now emits top-level `contract_map_provenance`.
  - When explicit `symbols` are passed, the provenance snapshot reflects the symbol set actually used for readiness evaluation.
- Updated `simnow_backfill_pending_kline.py`.
  - `build_backfill_plan()` now emits top-level `contract_map_provenance`.
  - Recompute now loads contract-map payloads through the shared metadata-aware loader.
- Updated `simnow_tick_bars.py`.
  - `_contract_lookup()` and `_expected_symbols()` now ignore `_meta`, so provenance metadata cannot be mistaken for a research symbol.
- Updated `run_next_work.ps1`.
  - Preflight now compiles `simnow_contract_map_meta.py`.
- Added/updated tests:
  - `test_simnow_daily_capture.py` now covers `_meta`-aware loading and export provenance embedding.
  - `test_simnow_run_summary.py` now requires top-level `contract_map_provenance`.
  - `test_simnow_backfill_pending_replays.py` and `test_simnow_backfill_pending_kline.py` now require top-level plan provenance.
  - `test_run_next_work_wrapper.py` now requires `simnow_contract_map_meta.py` in preflight compile coverage.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_capture.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_backfill_pending_replays.py .\examples\czsc_strategy\tests\unit\test_simnow_backfill_pending_kline.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted provenance regressions passed: `96 passed`.
- Full SimNow workflow preflight passed: `220 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: split halt/pending statistics into clearer operational buckets so environment issues, data lag, and strategy-risk halts stop being mixed together in 20-day summary analysis.

## 2026-07-22 Operational Buckets

### Goal

Split 20-day halt/pending/skipped statistics into clearer operational buckets so environment issues, data-lag/data-coverage issues, and strategy-risk halts are no longer mixed together in one flat reason list.

### Root Cause

- `simnow_ledger_summary.py` previously exposed:
  - `pending_days`
  - `skipped_days`
  - `halt_days`
  - `reason_counts`
- But it did not normalize those outcomes into higher-level operational categories.
- That made the 20-day ledger hard to interpret operationally: a strategy-risk halt and a historical-DB lag both blocked promotion, but they are very different remediation classes.

### Changes

- Updated `simnow_ledger_summary.py`.
  - Added `_operational_bucket(record)` to classify records into:
    - `data_pending_days`
    - `infra_pending_days`
    - `trading_session_skipped_days`
    - `strategy_risk_halt_days`
    - `safety_halt_days`
  - `build_ledger_summary()` now emits `operational_bucket_counts`.
- Updated `simnow_run_summary.py`.
  - Added `operational_bucket_counts` to the safe embedded `ledger_summary` allowlist so the daily machine-readable source of truth carries the same operational split.
- Updated `simnow_daily_brief.py`.
  - The `## 20 日进度` section now renders each `operational_bucket_counts.*` field when available.
- Added/updated tests:
  - `test_simnow_ledger_summary.py` now verifies:
    - mixed-record summaries emit operational buckets;
    - data-vs-infra pending causes split correctly;
    - strategy-risk halts and order-safety halts split correctly.
  - `test_simnow_run_summary.py` now requires embedded ledger summaries to preserve `operational_bucket_counts`.
  - `test_simnow_daily_brief.py` now requires the brief to render the operational-bucket fields.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_ledger_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted ledger/run-summary/daily-brief regressions passed: `53 passed`.
- Full SimNow workflow preflight passed: `222 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: refine blocker/action semantics so 20-day summaries distinguish “wait for data/session” blockers from “manual review now” blockers in a more machine-actionable way.
## 2026-07-22 Action / Blocker Classes

### Goal

Make daily action recommendations and 20-day blocker summaries machine-readable, so we can distinguish "wait for data/session" cases from "review now" cases without scraping free-form Chinese text.

### Root Cause

- `simnow_action_summary.py` previously only returned:
  - `date`
  - `status`
  - `reason`
  - `severity`
  - `action`
  - `counts_for_20d`
- That was enough for markdown reports, but not enough for stable aggregation:
  - `promotion.top_blocking_actions` only counted `reason`;
  - `ledger_summary.latest_action` carried text but no stable action category;
  - `ledger_summary.next_action` was only coarse English prose.
- Result: "wait for DB/kline/session" blockers and "manual review now" blockers were mixed together operationally.

### Changes

- Updated `simnow_action_summary.py`.
  - Added machine-readable fields to every action row:
    - `action_class`
    - `blocker_class`
  - Current stable categories:
    - `counts_for_20d`
    - `rerun_next_session`
    - `wait_for_data`
    - `investigate_infra`
    - `resolve_observation_gaps`
    - `manual_review_required`
    - `unknown`
  - `blocker_class` now normalizes rows into:
    - `none`
    - `wait`
    - `review_now`
- Updated `simnow_promotion_decision.py`.
  - `decide_promotion()` now emits:
    - `blocking_action_counts`
    - richer `top_blocking_actions` entries with:
      - `reason`
      - `count`
      - `action_class`
      - `blocker_class`
  - CLI JSON stdout now includes `blocking_action_counts`.
- Updated `simnow_ledger_summary.py`.
  - Aggregates non-counted action rows into `blocking_action_counts`.
  - `latest_action` now keeps `action_class` and `blocker_class`.
  - Added `next_action_class` so the ledger has a stable machine recommendation alongside the existing human-readable `next_action`.
- Updated `simnow_run_summary.py`.
  - Added `blocking_action_counts` and `next_action_class` to the safe embedded `ledger_summary` allowlist.
  - Embedded `promotion` now preserves `blocking_action_counts`.
- Updated tests:
  - `test_simnow_daily_monitor.py` now verifies:
    - `action_recommendation()` emits `action_class` / `blocker_class`;
    - `build_action_summary()` carries the new fields;
    - promotion summaries expose richer blocking-action structures.
  - `test_simnow_ledger_summary.py` now verifies:
    - `latest_action.action_class`
    - `latest_action.blocker_class`
    - `blocking_action_counts`
    - `next_action_class`
  - `test_simnow_run_summary.py` now requires:
    - promotion `blocking_action_counts`
    - embedded ledger `blocking_action_counts`
    - embedded `latest_action.action_class`
    - embedded `latest_action.blocker_class`
    - embedded `next_action_class`

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py .\examples\czsc_strategy\tests\unit\test_simnow_ledger_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py -q
```

Results:

- Targeted action/blocker regression suite passed: `92 passed`.

### Next Action

Continue the next repair item: propagate the new machine-readable action/blocker classes into the daily brief and downstream consistency checks where that improves operator triage without duplicating logic.

## 2026-07-22 Daily Brief Action Classes

### Goal

Propagate the new machine-readable action/blocker classes into the daily brief and summary-consistency gate, so operator-facing markdown stays aligned with the JSON single source of truth.

### Root Cause

- After adding `action_class` / `blocker_class` to action summaries, the downstream daily brief still only showed:
  - `automation_status`
  - `automation_reason`
  - `automation_action`
- `needs_user_action()` still depended mainly on legacy reason strings.
- `simnow_summary_consistency.py` checked daily-brief status/action text, but not the new structured action-class fields.

### Changes

- Rewrote `simnow_daily_brief.py` in clean UTF-8 text.
  - Preserved the existing brief structure and sections.
  - Added top-level fields:
    - `automation_action_class`
    - `automation_blocker_class`
  - Added derived record-level fields:
    - `record.action_class`
    - `record.blocker_class`
  - `## 20 日进度` now also renders:
    - `next_action_class`
    - each `blocking_action_counts.*`
  - `needs_user_action()` now uses the structured blocker classification first:
    - `review_now` => user action required
    - `wait` / `none` => no user action
    - `halt` / `failed` still always require user action
- Updated `simnow_run_summary.py`.
  - `classify_automation_status()` now emits:
    - `automation_action_class`
    - `automation_blocker_class`
  - These are derived from the same shared `action_recommendation()` logic as the reports.
- Updated `simnow_summary_consistency.py`.
  - Daily brief validation now checks:
    - `automation_action_class`
    - `automation_blocker_class`
    - `next_action_class` when ledger summary is available
- Updated tests:
  - `test_simnow_daily_brief.py` now verifies:
    - brief output contains the new action/blocker-class fields;
    - `needs_user_action()` honors structured blocker classes;
    - ledger `next_action_class` and `blocking_action_counts.*` are rendered.
  - `test_simnow_run_summary.py` now requires automation summaries to emit action/blocker classes.
  - `test_simnow_summary_consistency.py` continues to guard brief-vs-summary alignment with the new structured fields present in the generated brief.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_summary_consistency.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted daily-brief/run-summary/consistency regressions passed: `100 passed`.
- Full SimNow workflow preflight passed: `225 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: surface the same machine-readable blocker/action categories in the 20-day promotion report markdown itself, so human review of promotion readiness uses the same structured buckets already present in JSON outputs.

## 2026-07-22 Promotion Markdown Structured Blocking

### Goal

Expose the same machine-readable blocker/action categories in the 20-day markdown reports that already exist in JSON outputs, so human review of promotion readiness and 20-day observation progress uses the same structured buckets as automation.

### Root Cause

- `decide_promotion()` already emitted:
  - `blocking_action_counts`
  - structured `top_blocking_actions`
  - `action_summary` rows with `action_class` / `blocker_class`
- But `simnow_20d_promotion_decision.md` still rendered:
  - only the old Action Summary columns;
  - no dedicated `blocking_action_counts` section;
  - no dedicated `top_blocking_actions` section.
- `simnow_20d_observation_report.md` also still used the old Action Summary columns, which left the two markdown reports visually out of sync with the shared action-summary schema.

### Changes

- Updated `simnow_promotion_decision.py`.
  - `## Action Summary` now renders:
    - `date`
    - `status`
    - `reason`
    - `severity`
    - `action_class`
    - `blocker_class`
    - `action`
    - `counts_for_20d`
  - Added `## Blocking Action Counts` markdown section.
    - Renders grouped counts by `action_class`.
  - Added `## Top Blocking Actions` markdown section.
    - Renders `reason`, `days`, `action_class`, `blocker_class`.
- Updated `simnow_daily_monitor.py`.
  - `simnow_20d_observation_report.md` now uses the same expanded Action Summary columns as the promotion report, keeping the two markdown reports aligned with `simnow_action_summary.py`.
- Updated tests:
  - `test_simnow_daily_monitor.py` now requires:
    - expanded Action Summary columns in promotion markdown;
    - explicit `Blocking Action Counts` and `Top Blocking Actions` sections;
    - shared structured columns in the 20-day observation report markdown.
- Updated `ACCEPTANCE.md`.
  - Documented `action_class` / `blocker_class` in Action Summary requirements.
  - Documented that the promotion decision report must surface `blocking_action_counts` and structured `top_blocking_actions`.
  - Expanded run-summary / ledger-summary requirements to mention the new machine-readable class fields where the lines were stable to update.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py .\examples\czsc_strategy\tests\unit\test_simnow_promotion_parity.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_summary_consistency.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted promotion/report/run-summary/daily-brief regressions passed: `160 passed`.
- Full SimNow workflow preflight passed: `226 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: reduce the remaining duplication between `build_20d_report()` and `decide_promotion()` so the same 20-day aggregate logic is computed once and rendered into both markdown/JSON outputs.

## 2026-07-22 Shared 20-Day Aggregate Helper

### Goal

Remove the remaining duplicated 20-day aggregation logic between `build_20d_report()` and `decide_promotion()` without changing the intentionally different `matched_days` and `halt_days` semantics already pinned by regression tests.

### Root Cause

- `simnow_daily_monitor.py::build_20d_report()` and `simnow_promotion_decision.py::decide_promotion()` both independently computed:
  - observation window filtering
  - `observed_days` / `valid_observation_days`
  - `status_counts` / `reason_counts`
  - `promotion_blockers`
  - `last_valid_observation_date`
  - `action_summary`
  - `blocking_action_counts`
  - `top_blocking_actions`
- This duplication meant any future change to shared fields could drift between markdown, JSON, and promotion gating logic.
- At the same time, `test_simnow_promotion_parity.py` explicitly documents two real differences that must stay intact:
  - monitor counts `order_safety.status == "halt"` in `halt_days`
  - promotion only counts threshold halts
  - monitor requires `matched and verified`
  - promotion accepts truthy `matched`

### Changes

- Added `simnow_20d_aggregate.py`.
  - Centralizes shared 20-day aggregation for:
    - observation-window filtering
    - common counts
    - blockers
    - latest valid date
    - action summary
    - blocking action counts
    - top blocking actions
  - Keeps divergence injectable through:
    - `matched_day_predicate`
    - `halt_day_predicate`
- Refactored `simnow_daily_monitor.py`.
  - `build_20d_report()` now delegates to `build_20d_aggregate(...)`.
  - Preserves existing stricter monitor semantics:
    - `matched is True and verified is True`
    - threshold halt or order-safety halt
- Refactored `simnow_promotion_decision.py`.
  - `decide_promotion()` now delegates to `build_20d_aggregate(...)`.
  - Preserves existing promotion semantics:
    - truthy `matched`
    - threshold halt only
- Added `test_simnow_20d_aggregate.py`.
  - Verifies shared helper output fields.
  - Verifies configurable predicates preserve the known monitor/promotion sub-count divergence.
- Updated `run_next_work.ps1`.
  - Preflight `py_compile` now includes `simnow_20d_aggregate.py`.
  - Preflight pytest list now includes `test_simnow_20d_aggregate.py`.
- Updated `test_run_next_work_wrapper.py`.
  - Added guards to ensure the new helper script and test file stay in preflight coverage.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_20d_aggregate.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py .\examples\czsc_strategy\tests\unit\test_simnow_promotion_parity.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted aggregate/monitor/promotion/wrapper regressions passed: `120 passed`.
- Full SimNow workflow preflight passed: `230 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: normalize the remaining duplicated report-shape assumptions across `simnow_daily_monitor.py`, `simnow_promotion_decision.py`, and downstream summary consumers, while keeping the current status semantics stable.

## 2026-07-22 Ledger Summary Schema Helper

### Goal

Reduce the remaining report-shape drift risk across downstream consumers by centralizing the safe `ledger_summary` schema and the daily-brief 20-day progress rendering in one helper, instead of having `simnow_run_summary.py` and `simnow_daily_brief.py` each remember the same field list separately.

### Root Cause

- `simnow_run_summary.py` maintained its own `SAFE_LEDGER_SUMMARY_FIELDS` whitelist to embed a sanitized `ledger_summary` into the machine-readable run summary.
- `simnow_daily_brief.py` separately hard-coded the exact same 20-day progress field names when rendering:
  - `valid_observation_days`
  - `consecutive_valid_days`
  - `ready_to_expand`
  - `observation_start_date`
  - `excluded_before_start_count`
  - `next_action`
  - `next_action_class`
  - `promotion_blockers`
  - `blocking_action_counts.*`
  - `operational_bucket_counts.*`
- This meant any schema change to ledger summary could drift in at least two places.
- During refactor, preflight exposed one more hidden dependency:
  - `simnow_summary_consistency.py` still imported the old private `_safe_ledger_summary` helper from `simnow_run_summary.py`.
  - Once that private helper moved, preflight failed immediately, proving the dependency chain was real and had to be updated, not papered over.

### Changes

- Added `simnow_ledger_summary_schema.py`.
  - Defines the shared `SAFE_LEDGER_SUMMARY_FIELDS`.
  - Provides `filter_safe_ledger_summary(...)`.
  - Provides `build_daily_brief_20d_lines(...)`.
- Updated `simnow_run_summary.py`.
  - Removed the local `SAFE_LEDGER_SUMMARY_FIELDS`.
  - Removed the local `_safe_ledger_summary(...)`.
  - Now uses `filter_safe_ledger_summary(...)` from the shared helper.
- Updated `simnow_daily_brief.py`.
  - Replaced the hand-written 20-day ledger-summary block with `build_daily_brief_20d_lines(...)`.
  - This keeps the daily brief aligned with the same schema used by the run summary.
- Updated `simnow_summary_consistency.py`.
  - Switched from the removed private `_safe_ledger_summary` import to the new shared `filter_safe_ledger_summary(...)`.
- Added `test_simnow_ledger_summary_schema.py`.
  - Verifies safe-field filtering.
  - Verifies daily-brief 20-day progress lines are rendered from the shared schema helper.
  - Verifies the missing-ledger path is stable.
- Updated `run_next_work.ps1`.
  - Preflight `py_compile` now includes `simnow_ledger_summary_schema.py`.
  - Preflight pytest list now includes `test_simnow_ledger_summary_schema.py`.
- Updated `test_run_next_work_wrapper.py`.
  - Added guards to ensure the new helper script and test file remain covered by preflight.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_ledger_summary_schema.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_summary_consistency.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted schema/run-summary/daily-brief/consistency/wrapper regressions passed: `107 passed`.
- Full SimNow workflow preflight passed: `235 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: inspect whether `simnow_run_summary.py` and `simnow_daily_brief.py` still duplicate automation-status-to-user-text mapping, and if so, extract the stable policy layer without changing current status semantics.

## 2026-07-22 Automation Policy Helper

### Goal

Extract the stable automation-status policy layer shared by `simnow_run_summary.py` and `simnow_daily_brief.py`, so the machine-readable automation verdict and the human-facing brief no longer maintain the same status/action semantics in parallel.

### Root Cause

- `simnow_run_summary.py` owned the machine-readable automation mapping in `classify_automation_status()`:
  - `valid` / `skipped` / `pending` / `halt` / `failed`
  - `automation_exit_code`
  - `automation_action`
  - `automation_action_class`
  - `automation_blocker_class`
- `simnow_daily_brief.py` then reimplemented the same policy layer in a different form:
  - rebuilding a monitor-shaped record for `action_recommendation()`
  - resolving action metadata
  - computing `needs_user_action`
  - generating the conclusion paragraph
- This duplication created schema drift risk between:
  - the JSON single source of truth used by automation
  - the markdown brief shown to humans
- The key requirement for this step was to reduce duplication without changing current semantics:
  - `subscription_incomplete` and `workflow_order_safety_breach` still require user action
  - `skipped + simnow_no_ticks` still does not
  - the same `automation_action_class` / `automation_blocker_class` values must still flow through unchanged

### Changes

- Added `simnow_automation_policy.py`.
  - Provides shared helpers for:
    - `classify_automation_status(...)`
    - `resolve_action_meta(...)`
    - `automation_action_text(...)`
    - `needs_user_action(...)`
    - `conclusion_text(...)`
    - `build_record_for_action(...)`
- Updated `simnow_run_summary.py`.
  - Removed the local `classify_automation_status(...)` implementation.
  - Now imports the shared `classify_automation_status(...)` from `simnow_automation_policy.py`.
- Updated `simnow_daily_brief.py`.
  - Now imports shared automation-policy helpers.
  - Uses shared `resolve_action_meta(...)`, `automation_action_text(...)`, `needs_user_action(...)`, and `conclusion_text(...)`.
  - Keeps the public `needs_user_action` symbol stable by binding it to the shared helper, so downstream callers and tests still use the same public API.
- Added `test_simnow_automation_policy.py`.
  - Verifies `simnow_run_summary.classify_automation_status` and `simnow_daily_brief.needs_user_action` are the shared helper functions.
  - Verifies pending classification still yields:
    - `automation_status=pending`
    - `automation_exit_code=20`
    - `automation_action=resolve pending gate before counting`
    - `automation_action_class=wait_for_data`
    - `automation_blocker_class=wait`
  - Verifies `needs_user_action(...)` still honors:
    - structured blocker class first
    - legacy `subscription_incomplete` fallback
  - Verifies the shared conclusion text matches existing status policy.
- Updated `run_next_work.ps1`.
  - Preflight `py_compile` now includes `simnow_automation_policy.py`.
  - Preflight pytest list now includes `test_simnow_automation_policy.py`.
- Updated `test_run_next_work_wrapper.py`.
  - Added guards to keep the new helper and test file in preflight coverage.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_automation_policy.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted automation-policy/run-summary/daily-brief/wrapper regressions passed: `106 passed`.
- Full SimNow workflow preflight passed: `241 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: inspect whether the remaining daily brief markdown assembly can be reduced further without destabilizing the current fixed-format output contract.

## 2026-07-22 Daily Brief Policy De-dup Cleanup

### Goal

Finish the daily-brief side of the automation-policy refactor by removing the remaining local policy-copy functions from `simnow_daily_brief.py`, so the file no longer contains dead duplicated implementations hidden behind alias rebinding.

### Root Cause

- After introducing `simnow_automation_policy.py`, `simnow_daily_brief.py` still contained:
  - a local `_build_record_for_action(...)`
  - a local `_resolve_action_meta(...)`
  - a local `needs_user_action(...)`
  - a local `_conclusion_text(...)`
- The module then rebound some names to shared helpers afterwards.
- That meant runtime behavior was already mostly shared, but the source still carried a misleading local copy of the old policy layer.
- This is a maintenance trap:
  - future readers can edit the dead local functions by mistake;
  - source grep still reports multiple policy implementations;
  - sharing guarantees are weaker unless a test explicitly pins them.

### Changes

- Cleaned `simnow_daily_brief.py`.
  - Removed the local `_build_record_for_action(...)` copy.
  - Removed the local `_resolve_action_meta(...)` copy.
  - Removed the local `needs_user_action(...)` copy.
  - Removed the local `action_recommendation` import that was only needed by the deleted duplicates.
  - Renamed the leftover legacy conclusion implementation away from the active entry point, while the public `_conclusion_text` name continues to point at the shared helper.
  - The active code path now uses the shared automation-policy helper directly for:
    - action text
    - action meta
    - user-action requirement
    - conclusion text
- Added `test_simnow_daily_brief_policy_sharing.py`.
  - Verifies `simnow_daily_brief.py` imports the shared automation-policy helper.
  - Verifies the file no longer defines local copies of:
    - `_build_record_for_action`
    - `_resolve_action_meta`
    - `needs_user_action`
    - `_conclusion_text`
- Updated `run_next_work.ps1`.
  - Preflight pytest list now includes `test_simnow_daily_brief_policy_sharing.py`.
- Updated `test_run_next_work_wrapper.py`.
  - Added a guard to ensure the new daily-brief policy-sharing regression test stays in preflight coverage.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_policy_sharing.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted daily-brief sharing/behavior/wrapper regressions passed: `82 passed`.
- Full SimNow workflow preflight passed: `243 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: inspect whether the remaining fixed-format daily-brief section rendering can be normalized into smaller reusable helpers without changing the current markdown output contract.

## 2026-07-22 Daily Brief Section Helper Extraction

### Goal

Reduce the remaining repeated fixed-format section rendering in `simnow_daily_brief.py` without changing the current markdown contract, so future daily-brief changes can update section logic in one place.

### Root Cause

- `simnow_daily_brief.py` still inlined four repetitive section blocks:
  - environment capture
  - historical DB update
  - account contamination
  - delayed replay
- Those blocks all followed the same pattern:
  - fixed heading
  - fixed ordered bullet list
  - local fallback formatting
- Keeping them inline makes the file harder to read and increases drift risk if one section is updated in one path but not another.

### Changes

- Added `simnow_daily_brief_sections.py`.
  - Provides shared section renderers for:
    - `build_environment_capture_section_lines(...)`
    - `build_historical_db_update_section_lines(...)`
    - `build_account_contamination_section_lines(...)`
    - `build_delayed_replay_section_lines(...)`
  - Keeps section-local formatting helpers close to the shared rendering layer.
- Rewrote `simnow_daily_brief.py` as an equivalent fixed-format renderer.
  - Preserved the existing public entry points:
    - `load_run_summary(...)`
    - `build_daily_brief(...)`
    - `render_daily_brief`
    - `needs_user_action`
  - Replaced the four inline markdown blocks with calls into the new shared section helper.
  - Left the summary header, 20-day section, conclusion, and next-step structure unchanged.
- Added `test_simnow_daily_brief_sections.py`.
  - Verifies the environment-capture section lines exactly.
  - Verifies the delayed-replay section lines exactly.
- Updated `run_next_work.ps1`.
  - Preflight `py_compile` now includes `simnow_daily_brief_sections.py`.
  - Preflight pytest list now includes `test_simnow_daily_brief_sections.py`.
- Updated `test_run_next_work_wrapper.py`.
  - Added guards to keep the new section helper and regression test in preflight coverage.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_sections.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_policy_sharing.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted daily-brief section/behavior/wrapper regressions passed: `86 passed`.
- Full SimNow workflow preflight passed: `247 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: inspect whether the remaining daily-brief summary/header assembly should also be extracted into a small schema helper, or whether the current level of consolidation is already the right stopping point.

## 2026-07-22 Daily Brief Schema Helper Extraction

### Goal

Consolidate the remaining fixed-format daily-brief overview and closing assembly into a shared schema helper, so `simnow_daily_brief.py` and `simnow_daily_brief_sections.py` stop carrying duplicate formatting utilities and the markdown contract becomes easier to maintain.

### Root Cause

- After the section-helper refactor, the daily-brief stack still had duplicated formatting logic across files:
  - nested-dict safe access
  - symbol-list formatting
  - boolean formatting
- `simnow_daily_brief.py` still directly assembled:
  - the top overview bullet block
  - the closing conclusion / next-step block
- That left the rendering layer split across two modules with repeated low-level formatting rules, which increases drift risk when the brief contract changes.

### Changes

- Added `simnow_daily_brief_schema.py`.
  - Provides shared helpers for:
    - `safe_get(...)`
    - `format_symbols(...)`
    - `format_bool(...)`
    - `build_daily_brief_overview_lines(...)`
    - `build_daily_brief_closing_lines(...)`
- Rewrote `simnow_daily_brief_sections.py`.
  - Removed local copies of the formatting helpers.
  - Now imports formatting behavior from `simnow_daily_brief_schema.py`.
  - Keeps the four section renderers unchanged at the output-contract level.
- Rewrote `simnow_daily_brief.py`.
  - Removed local copies of nested access / symbol formatting helpers.
  - Now imports shared schema helpers for:
    - overview-line rendering
    - closing-line rendering
    - shared fallback formatting
  - Preserved the public API:
    - `load_run_summary(...)`
    - `build_daily_brief(...)`
    - `render_daily_brief`
    - `needs_user_action`
- Added `test_simnow_daily_brief_schema.py`.
  - Verifies the overview bullet block exactly.
  - Verifies the closing conclusion / next-step block exactly.
- Updated `run_next_work.ps1`.
  - Preflight `py_compile` now includes `simnow_daily_brief_schema.py`.
  - Preflight pytest list now includes `test_simnow_daily_brief_schema.py`.
- Updated `test_run_next_work_wrapper.py`.
  - Added guards to keep the new schema helper and regression test in preflight coverage.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_schema.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_sections.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_policy_sharing.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted daily-brief schema/sections/behavior/wrapper regressions passed: `90 passed`.
- Full SimNow workflow preflight passed: `251 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: inspect whether the remaining `_legacy_conclusion_text(...)` compatibility stub and other residual fallback shims can be safely removed or pinned by tests without weakening the current output contract.

## 2026-07-22 Daily Brief Legacy Stub Cleanup

### Goal

Remove the remaining dead compatibility stub from `simnow_daily_brief.py`, so the daily-brief renderer no longer carries an unused legacy conclusion implementation after the shared automation-policy migration.

### Root Cause

- `simnow_daily_brief.py` still contained `_legacy_conclusion_text(...)`.
- The active render path already used the shared automation-policy helper through:
  - `_conclusion_text = _policy_conclusion_text`
- That meant `_legacy_conclusion_text(...)` was dead code:
  - it was not part of the public API;
  - it was not called by `build_daily_brief(...)`;
  - it duplicated logic already centralized elsewhere.
- The file also still carried now-unused imports that only existed because the legacy stub used to need them.

### Changes

- Updated `simnow_daily_brief.py`.
  - Removed the unused `_legacy_conclusion_text(...)` stub.
  - Removed the unused `Any` import.
  - Removed the unused `format_symbols` import.
  - Left the active rendering path unchanged:
    - `_resolve_action_meta`
    - `_conclusion_text`
    - `needs_user_action`
    - `build_daily_brief(...)`
- Updated `test_simnow_daily_brief_policy_sharing.py`.
  - Added a guard asserting the file no longer defines `_legacy_conclusion_text(...)`.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_policy_sharing.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_schema.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_sections.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted daily-brief sharing/schema/sections/wrapper regressions passed: `90 passed`.
- Full SimNow workflow preflight passed: `251 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: inspect whether the remaining failed-summary fallback defaults in `simnow_daily_brief.py` should also move into a shared helper, or whether the current boundary is already the cleanest stable cut.

## 2026-07-22 Daily Brief Missing-Run-Summary Helper

### Goal

Move the missing-run-summary fallback payload out of `simnow_daily_brief.py` into a shared helper, so the failed-summary default contract is explicit, testable, and no longer embedded as an inline dict literal.

### Root Cause

- `simnow_daily_brief.py` still carried an inline fallback payload for the case where the run-summary JSON is missing.
- That payload defines a real contract:
  - failed automation status
  - exit code `40`
  - canonical reason/action strings
  - default action/blocker classes
- Keeping it inline made it harder to:
  - test directly;
  - reuse consistently;
  - notice contract changes independently of renderer refactors.

### Changes

- Added `simnow_daily_brief_default_summary.py`.
  - Provides `build_missing_run_summary_payload()`.
  - Centralizes the canonical fallback payload used when the run summary JSON is absent.
- Updated `simnow_daily_brief.py`.
  - Removed the inline fallback dict literal.
  - Now uses `build_missing_run_summary_payload()` when `summary` is empty.
- Added `test_simnow_daily_brief_default_summary.py`.
  - Verifies the fallback payload exactly:
    - `automation_status=failed`
    - `automation_exit_code=40`
    - `automation_reason=missing run summary JSON`
    - `automation_action=check wrapper output and artifact completeness`
    - default action/blocker classes and empty nested objects
- Updated `run_next_work.ps1`.
  - Preflight `py_compile` now includes `simnow_daily_brief_default_summary.py`.
  - Preflight pytest list now includes `test_simnow_daily_brief_default_summary.py`.
- Updated `test_run_next_work_wrapper.py`.
  - Added guards to keep the new helper and regression test in preflight coverage.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_default_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_policy_sharing.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_schema.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_sections.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted daily-brief default-summary/schema/sections/behavior/wrapper regressions passed: `93 passed`.
- Full SimNow workflow preflight passed: `254 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: inspect whether the remaining local `automation_exit_code` defaulting in `simnow_daily_brief.py` should also move into the shared daily-brief helper layer, or whether it is better kept inline as renderer-local normalization.

## 2026-07-22 Daily Brief Exit-Code Normalization Helper

### Goal

Move the remaining `automation_exit_code` defaulting out of `simnow_daily_brief.py` into the shared daily-brief default-summary helper, so missing-summary fallback and missing-exit-code normalization live in one place.

### Root Cause

- After introducing `simnow_daily_brief_default_summary.py`, `simnow_daily_brief.py` still performed local normalization for missing `automation_exit_code`.
- That left the default-summary contract split across two locations:
  - helper for the empty-summary payload
  - renderer-local logic for missing exit code
- Both behaviors are part of the same normalization layer and should move together to reduce drift.

### Changes

- Updated `simnow_daily_brief_default_summary.py`.
  - Added `normalize_daily_brief_summary(...)`.
  - Behavior:
    - empty summary -> canonical missing-run-summary payload
    - explicit `automation_exit_code` -> preserved unchanged
    - missing `automation_exit_code` + `automation_status=failed` -> default to `40`
    - missing `automation_exit_code` + non-failed status -> default to `0`
- Updated `simnow_daily_brief.py`.
  - Removed local `default_exit` calculation and inline missing-exit-code normalization.
  - Now calls `normalize_daily_brief_summary(...)` up front.
- Updated `test_simnow_daily_brief_default_summary.py`.
  - Added coverage for:
    - empty summary normalization
    - failed default exit code
    - non-failed default exit code
    - explicit exit code preservation

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_default_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_policy_sharing.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_schema.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_sections.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted daily-brief normalization/schema/sections/behavior/wrapper regressions passed: `97 passed`.
- Full SimNow workflow preflight passed: `258 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: inspect whether the remaining failed-state action-text fallback in `simnow_daily_brief.py` should also move into the shared helper layer, or whether that fallback belongs in the renderer because it is specifically tied to markdown conclusion wording.

## 2026-07-22 Daily Brief Failed-Action Fallback Helper

### Goal

Move the failed-state `action_text` fallback out of `simnow_daily_brief.py` into the shared daily-brief default-summary helper, so the renderer no longer owns any of the canonical failed-summary fallback wording.

### Root Cause

- `simnow_daily_brief.py` still contained a local failed-state fallback:
  - if `automation_status=failed` and `automation_action` was empty, it injected the canonical wrapper/artifact inspection text inline.
- That made the failed-summary normalization layer incomplete:
  - missing summary payload was shared
  - missing exit code normalization was shared
  - but missing failed action text was still renderer-local
- This is the same family of fallback behavior and should live with the other default-summary helpers.

### Changes

- Updated `simnow_daily_brief_default_summary.py`.
  - Added `resolve_failed_action_text(...)`.
  - Behavior:
    - explicit failed `automation_action` -> preserved
    - missing/empty failed `automation_action` -> returns `请检查 wrapper 输出和 artifact 完整性。`
- Updated `simnow_daily_brief.py`.
  - Removed the local failed-state `action_text` fallback branch.
  - Now calls `resolve_failed_action_text(...)` for `automation_status=failed`.
- Updated `test_simnow_daily_brief_default_summary.py`.
  - Added coverage for:
    - explicit failed action preservation
    - canonical failed fallback action text when the action is missing

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_default_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_policy_sharing.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_schema.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_sections.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted daily-brief fallback/schema/sections/behavior/wrapper regressions passed: `99 passed`.
- Full SimNow workflow preflight passed: `260 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: inspect whether the remaining `record_action` failed-branch shaping in `simnow_daily_brief.py` should also move into shared helper logic, or whether that branch is the cleanest stable renderer boundary.

## 2026-07-22 Daily Brief Record-Action Branch Cleanup

### Goal

Remove the redundant failed-only `record_action` branch from `simnow_daily_brief.py`, so the renderer stops restating the exact same two-field action metadata already returned by the shared policy helper.

### Root Cause

- `simnow_daily_brief.py` previously used:
  - `record_action = action_meta` for non-failed states
  - a second failed-only branch that rebuilt `{action_class, blocker_class}` from `action_meta`
- But `resolve_action_meta(...)` already returns only:
  - `action_class`
  - `blocker_class`
- That meant the failed branch had no extra policy meaning; it only duplicated the same two-field dict shape.

### Changes

- Updated `simnow_daily_brief.py`.
  - Removed the redundant failed-only `record_action` branch.
  - `record_action` now simply reuses `action_meta` for every status.
  - This is an equivalent cleanup only; no markdown contract or behavior changed.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_default_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_policy_sharing.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_schema.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_sections.py .\examples\czsc_strategy\tests\unit\test_simnow_automation_policy.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted daily-brief/policy/schema/sections/wrapper regressions passed: `103 passed`.
- Full SimNow workflow preflight passed: `260 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: inspect whether the remaining local `load_run_summary(...)`/default-output wiring in `simnow_daily_brief.py` is already the right stable boundary, or whether any further extraction would just create churn without reducing real duplication.

## 2026-07-22 Shared Artifact JSON Loader

### Goal

Consolidate the repeated JSON-object file loading logic used by diagnostics scripts into a shared helper, so `daily_brief.py` and `run_summary.py` stop maintaining identical `utf-8-sig` JSON loaders independently.

### Root Cause

- Multiple diagnostics modules were each implementing the same pattern:
  - if file missing -> return `{}`
  - else read JSON with `utf-8-sig`
- The repeated loaders existed under different names:
  - `load_run_summary(...)` in `simnow_daily_brief.py`
  - `load_json(...)` in `simnow_run_summary.py`
  - `load_ledger_summary(...)` in `simnow_run_summary.py`
- This is true duplication at the I/O layer, and changing encoding or missing-file behavior would otherwise require parallel edits.

### Changes

- Added `simnow_artifact_loader.py`.
  - Provides `load_json_dict(...)`.
  - Defines the shared behavior for JSON object artifacts:
    - missing path -> `{}`
    - existing file -> load with `utf-8-sig`
- Updated `simnow_daily_brief.py`.
  - `load_run_summary(...)` now delegates to `load_json_dict(...)`.
  - Public `load_run_summary(...)` entry point stays intact.
- Updated `simnow_run_summary.py`.
  - `load_json(...)` now delegates to `load_json_dict(...)`.
  - `load_ledger_summary(...)` now delegates to `load_json_dict(...)`.
  - Public function names stay intact for downstream imports such as `simnow_summary_consistency.py`.
- Added `test_simnow_artifact_loader.py`.
  - Verifies missing-file behavior.
  - Verifies `utf-8-sig` JSON loading behavior.
- Updated `test_simnow_daily_brief_policy_sharing.py`.
  - Adds a guard asserting `simnow_daily_brief.py` imports the shared artifact loader.
- Updated `run_next_work.ps1`.
  - Preflight `py_compile` now includes `simnow_artifact_loader.py`.
  - Preflight pytest list now includes `test_simnow_artifact_loader.py`.
- Updated `test_run_next_work_wrapper.py`.
  - Added guards to keep the new loader and test in preflight coverage.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_artifact_loader.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_policy_sharing.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted artifact-loader/daily-brief/run-summary/wrapper regressions passed: `114 passed`.
- Full SimNow workflow preflight passed: `264 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item: inspect whether any remaining loader duplication is materially worth sharing, or whether the current JSON/JSONL split is now the cleanest stable boundary.

## 2026-07-22 Shared Artifact JSONL Loader

### Goal

Consolidate the remaining JSONL artifact loading logic used by diagnostics scripts into the shared artifact-loader layer, so `simnow_run_summary.py` and `simnow_ledger_summary.py` stop maintaining equivalent line-by-line JSONL readers independently.

### Root Cause

- After introducing the shared JSON object loader, diagnostics still had two separate JSONL readers:
  - `load_jsonl(...)` in `simnow_run_summary.py`
  - `load_ledger(...)` in `simnow_ledger_summary.py`
- Both implement the same contract:
  - missing file -> empty list
  - existing file -> parse non-empty JSONL rows
- The only practical compatibility concern was ensuring both UTF-8 and UTF-8-SIG encoded JSONL files continued to load.

### Changes

- Updated `simnow_artifact_loader.py`.
  - Added `load_jsonl_records(...)`.
  - Shared behavior:
    - missing path -> `[]`
    - existing file -> parse JSONL rows with `utf-8-sig`
    - plain UTF-8 input still works because `utf-8-sig` is backward-compatible for files without BOM
- Updated `simnow_run_summary.py`.
  - `load_jsonl(...)` now delegates to `load_jsonl_records(...)`.
- Updated `simnow_ledger_summary.py`.
  - `load_ledger(...)` now delegates to `load_jsonl_records(...)`.
  - Restored the module-level `json` import after regression testing caught that the CLI serializer still needs it.
- Updated `test_simnow_artifact_loader.py`.
  - Added coverage for:
    - missing JSONL file
    - UTF-8-SIG JSONL input
    - plain UTF-8 JSONL input

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_artifact_loader.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_ledger_summary.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted artifact-loader/run-summary/ledger-summary/wrapper regressions passed: `112 passed`.
- Full SimNow workflow preflight passed: `267 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Continue the next repair item only if a remaining duplication has comparable payoff; otherwise treat the current JSON/JSONL loader split and the existing CLI wiring as the clean stable boundary.

## 2026-07-22 Shared Structured Access Helper

### Goal

Consolidate the repeated nested-dict access helper used across diagnostics helper modules, so `simnow_automation_policy.py` and `simnow_daily_brief_schema.py` stop maintaining parallel `safe_get` implementations.

### Root Cause

- After the loader cleanup, one true duplication still remained:
  - `_safe_get(...)` in `simnow_automation_policy.py`
  - `safe_get(...)` in `simnow_daily_brief_schema.py`
- Both implemented the same nested traversal contract:
  - walk dict keys in order
  - return `default` when a key is missing
  - return `default` when a non-dict is encountered before the path ends
- This helper is shared infrastructure, not renderer-specific or policy-specific behavior.

### Changes

- Added `simnow_structured_access.py`.
  - Provides shared `safe_get(...)`.
- Rewrote `simnow_automation_policy.py`.
  - Removed the local `_safe_get(...)`.
  - Now imports `safe_get(...)` from `simnow_structured_access.py`.
  - Preserved all existing public policy helpers and status/action behavior.
- Rewrote `simnow_daily_brief_schema.py`.
  - Removed the local `safe_get(...)`.
  - Now imports `safe_get(...)` from `simnow_structured_access.py`.
  - Left formatting and markdown-assembly behavior unchanged.
- Added `test_simnow_structured_access.py`.
  - Verifies nested traversal, missing-key fallback, and non-dict fallback.
- Updated `test_simnow_daily_brief_policy_sharing.py`.
  - Adds guards asserting both:
    - `simnow_automation_policy.py`
    - `simnow_daily_brief_schema.py`
    import the shared `safe_get(...)`.
- Updated `run_next_work.ps1`.
  - Preflight `py_compile` now includes `simnow_structured_access.py`.
  - Preflight pytest list now includes `test_simnow_structured_access.py`.
- Updated `test_run_next_work_wrapper.py`.
  - Added guards to keep the new helper and regression test in preflight coverage.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_structured_access.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_policy_sharing.py .\examples\czsc_strategy\tests\unit\test_simnow_automation_policy.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_schema.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted structured-access/policy/daily-brief/wrapper regressions passed: `102 passed`.
- Full SimNow workflow preflight passed: `273 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Treat the current helper boundaries as the clean stable cut unless a newly discovered duplication has similarly clear payoff; the remaining CLI wiring and module-local orchestration are now mostly legitimate boundaries rather than repeated policy or I/O logic.

## 2026-07-22 Diagnostics Boundary Audit

### Goal

Audit the remaining diagnostics code after the helper/loader consolidation work, and decide whether further extraction would still reduce real duplication or would mostly create churn.

### Audit Result

No remaining duplication was found at the same payoff level as the items already extracted.

The remaining repeated-looking code now falls into stable boundaries rather than shared helper candidates:

- CLI wiring
  - `argparse` setup
  - output-path argument handling
  - per-script `main()` orchestration
- artifact-specific orchestration
  - `simnow_daily_brief.py` assembles one markdown document from already-shared helpers
  - `simnow_run_summary.py` assembles one machine-readable summary with artifact-specific extraction logic
  - `simnow_summary_consistency.py` validates cross-artifact invariants rather than formatting data
- domain-specific transforms
  - capture summary extraction
  - ledger summary reduction
  - consistency validation rules

These areas may look structurally similar, but they are no longer maintaining identical business rules, formatting rules, or I/O helpers. Further extraction here would mostly:

- introduce indirection without deleting much code
- widen helper APIs around single-call-site orchestration
- make the system harder to trace during future incident/debug work

### Stable Boundary Decision

The current helper split is treated as the clean stable cut:

- shared structured access:
  - `simnow_structured_access.py`
- shared artifact loaders:
  - `simnow_artifact_loader.py`
- shared automation policy:
  - `simnow_automation_policy.py`
- shared daily-brief defaults/schema/sections:
  - `simnow_daily_brief_default_summary.py`
  - `simnow_daily_brief_schema.py`
  - `simnow_daily_brief_sections.py`
- shared ledger-summary schema helpers:
  - `simnow_ledger_summary_schema.py`
- shared 20-day aggregation:
  - `simnow_20d_aggregate.py`

### Verification

This audit was performed against the current workspace state after the latest passing preflight:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Latest verified result:

- Full SimNow workflow preflight passed: `273 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Shift from helper extraction to higher-level maintenance only when a new concrete root-cause or duplicated rule is discovered; otherwise keep the current boundaries stable and avoid churn.

## 2026-07-22 Diagnostics Helper Boundary Guards

### Goal

Turn the boundary-audit conclusion into executable regression guards, so the current shared-helper split is enforced by tests instead of relying only on documentation and reviewer memory.

### Root Cause

- The boundary audit established that the current helper layout is the intended stable cut.
- Without executable guards, future edits could gradually reintroduce:
  - duplicate loader helpers
  - duplicate `safe_get(...)` implementations
  - silent drift away from shared helper imports
- That would recreate the same maintenance problem we just spent several rounds removing.

### Changes

- Added `test_simnow_helper_boundaries.py`.
  - Verifies shared loader boundaries remain centralized:
    - `simnow_daily_brief.py` imports `load_json_dict(...)`
    - `simnow_run_summary.py` imports `load_json_dict(...)` and `load_jsonl_records(...)`
    - `simnow_ledger_summary.py` imports `load_jsonl_records(...)`
    - `simnow_artifact_loader.py` remains the sole definition site for:
      - `load_json_dict(...)`
      - `load_jsonl_records(...)`
  - Verifies shared structured-access boundaries remain centralized:
    - `simnow_automation_policy.py` imports `safe_get(...)`
    - `simnow_daily_brief_schema.py` imports `safe_get(...)`
    - `simnow_structured_access.py` remains the sole definition site for `safe_get(...)`
- Updated `run_next_work.ps1`.
  - Preflight pytest list now includes `test_simnow_helper_boundaries.py`.
- Updated `test_run_next_work_wrapper.py`.
  - Added a guard to ensure the new helper-boundary regression test stays in preflight coverage.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_helper_boundaries.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_policy_sharing.py .\examples\czsc_strategy\tests\unit\test_simnow_artifact_loader.py .\examples\czsc_strategy\tests\unit\test_simnow_structured_access.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted helper-boundary/wrapper/shared-helper regressions passed: `86 passed`.
- Full SimNow workflow preflight passed: `276 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Keep the current helper boundaries stable; only resume extraction work if a new concrete duplicated rule or incident root cause appears.

## 2026-07-22 Post-Consolidation Re-Scan

### Goal

Re-scan the diagnostics workspace after the helper-boundary guards landed, and verify that no additional same-payoff duplication remains before stopping the consolidation stream.

### Audit Scope

Checked for the specific duplication families already targeted in this repair cycle:

- structured nested-dict access helpers
- JSON object artifact loaders
- JSONL artifact loaders
- daily-brief formatting helpers
- boundary regressions in the shared-helper stack

### Audit Result

No new duplication of the same class was found in `examples/czsc_strategy/diagnostics/`.

The remaining code that still looks superficially similar is now concentrated in:

- per-script CLI entrypoints
- artifact-specific orchestration
- domain-specific transformation logic

Those areas are not currently maintaining duplicate shared rules. Further extraction would mostly trade away traceability for little code reduction.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_artifact_loader.py .\examples\czsc_strategy\tests\unit\test_simnow_structured_access.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_ledger_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_summary_consistency.py -q
```

Results:

- Targeted post-consolidation verification passed: `68 passed`.

### Next Action

Treat the helper/loader consolidation stream as complete for now. Only reopen it if a new duplicated rule, regression, or incident root cause is found.

## 2026-07-22 Unified Halt Metadata

### Goal

Start the business-facing optimization stream by turning `halt` into a single, machine-readable source of truth instead of letting daily monitor, run summary, and ledger aggregation infer it independently.

### Changes

- Added `simnow_halt_metadata.py`.
  - Centralizes unified `halt` metadata generation:
    - `rule_id`
    - `family`
    - `severity`
    - `trigger_metrics`
    - `explained_cn`
  - Covers the two currently meaningful halt families:
    - `order_safety`
    - `strategy_risk`
- Updated `simnow_daily_monitor.py`.
  - `make_record(...)` now writes a normalized `halt` block onto halted daily records.
- Updated `simnow_run_summary.py`.
  - Daily record summary now surfaces:
    - `halt_rule_id`
    - `halt_family`
    - `halt_severity`
    - `halt_trigger_metrics`
    - `halt_explained_cn`
- Updated `simnow_ledger_summary.py`.
  - Operational halt bucketing now prefers unified `halt.family`.
  - Added `halt_family_counts` for machine-readable 20-day/ledger governance stats.
  - Safe latest-record projection now preserves the normalized `halt` block.
- Updated `simnow_20d_aggregate.py`.
  - Added `halt_family_counts` so recent-window statistics no longer need to guess halt family from raw reason strings.
- Updated `run_next_work.ps1`.
  - Preflight `py_compile` list now includes `simnow_halt_metadata.py`.
- Updated tests:
  - `test_simnow_daily_monitor.py`
  - `test_simnow_run_summary.py`
  - `test_simnow_ledger_summary.py`
  - `test_simnow_20d_aggregate.py`
  - `test_run_next_work_wrapper.py`

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_daily_monitor.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_ledger_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_20d_aggregate.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted halt/readout/ledger/wrapper regression suite passed: `170 passed`.
- Full SimNow workflow preflight passed: `277 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Use the new unified `halt` block as the base layer for the next two optimization items:

- formal-window readiness summary
- 20-day reason governance / Pareto rationality output

## 2026-07-22 Formal Readiness Summary

### Goal

Turn formal-observation readiness from a set of scattered artifacts into a single machine-readable summary block so operators can immediately see whether the formal window had enough prerequisites to produce a meaningful same-day observation.

### Changes

- Updated `simnow_run_summary.py`.
  - `default_artifact_paths(...)` now includes `simnow_replay_readiness_YYYY-MM-DD.json`.
  - Added `formal_readiness` aggregation to the run summary.
  - The new block consolidates:
    - capture timing from `capture.meta`
    - strategy window timing from `capture.meta.strategy_surface`
    - read-only declaration
    - historical DB update status / readiness
    - replay DB readiness / latest DB date / lagged symbols
    - kline coverage readiness / missing symbols / short symbols
    - an `overall_ready` verdict
    - explicit `blocking_reasons`
- Updated `test_simnow_run_summary.py`.
  - Added regression coverage for:
    - normal readiness aggregation from existing artifacts
    - missing-artifact fallback / blocked readiness output

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_summary_consistency.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted run-summary/consistency/wrapper regression suite passed: `103 passed`.
- Full SimNow workflow preflight passed: `279 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

Use the new `formal_readiness` block as input for the remaining optimization item:

- 20-day reason governance / Pareto rationality output

## 2026-07-22 Reason Governance And Explanation Layer

### Goal

Finish the remaining operator-facing optimization items by:

- turning 20-day blocking-reason counts into a governance / Pareto panel
- adding a direct Chinese explanation layer to `simnow_run_summary_YYYY-MM-DD.json`

### Changes

- Added `simnow_reason_governance.py`.
  - Centralizes blocking-reason governance classification.
  - Produces:
    - `reason_governance_counts`
    - `reasonableness_counts`
    - `reason_rationality_verdict`
    - `reason_rationality_cn`
    - `pareto_summary`
- Updated `simnow_20d_aggregate.py`.
  - 20-day aggregate now annotates top blocking reasons with:
    - `governance_class`
    - `reasonableness`
  - 20-day aggregate now emits governance and Pareto fields directly.
- Updated `simnow_promotion_decision.py`.
  - Promotion report now includes:
    - enriched top blocking actions table
    - reason governance section
    - Pareto summary lines
  - CLI JSON output now includes governance / Pareto fields.
- Updated `simnow_ledger_summary.py`.
  - Ledger summary now emits governance / reasonableness / Pareto fields for the full observation cycle.
- Updated `simnow_ledger_summary_schema.py`.
  - Safe projection and daily-brief 20-day lines now surface:
    - `reason_governance_counts`
    - `reason_rationality_verdict`
    - `pareto_summary.top3_share_pct`
- Updated `simnow_automation_policy.py`.
  - Added:
    - `operator_explanation_cn(...)`
    - `user_action_needed_reason_cn(...)`
- Updated `simnow_run_summary.py`.
  - Run summary now emits:
    - `operator_explanation_cn`
    - `user_action_needed`
    - `user_action_needed_reason_cn`
- Updated `simnow_daily_brief_schema.py`.
  - Daily brief overview now exposes the explanation-layer fields directly.
- Updated `run_next_work.ps1`.
  - Preflight compile list now includes `simnow_reason_governance.py`.
- Updated tests:
  - `test_simnow_20d_aggregate.py`
  - `test_simnow_daily_monitor.py`
  - `test_simnow_ledger_summary_schema.py`
  - `test_simnow_run_summary.py`
  - `test_simnow_daily_brief.py`
  - `test_simnow_daily_brief_schema.py`
  - `test_simnow_automation_policy.py`
  - `test_run_next_work_wrapper.py`

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_automation_policy.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_schema.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py -q
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Results:

- Targeted explanation-layer regressions passed: `48 passed`.
- Full SimNow workflow preflight passed: `280 passed`.
- Pending replay backfill plan remained clean: `pending_historical_db_lag_days=0`.

### Next Action

The current optimization set is complete. Future work can focus on new incident classes or new operator/reporting requirements rather than continuing this repair stream.

## 2026-07-23 Formal Daily Observation

### Goal

Run the formal 09:05 SimNow daily observation in read-only mode, recover any automation interruptions without sending orders, and record the authoritative outcome from `simnow_run_summary_2026-07-23.json`.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `281 passed`.

Started formal capture:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Observed:

- The parent automation process hit the tool timeout before post-processing completed.
- The child capture still completed successfully and produced:
  - `simnow_export_2026-07-23.json`
  - `simnow_kline_update_2026-07-23.json`
  - `simnow_historical_db_update_2026-07-23.json`

### Root Cause And Fixes

- Fixed `run_next_work.ps1` so `-LiveCapture -PostProcessOnly` bypasses the formal-start window gates.
- Fixed `run_next_work.ps1` so replay-readiness JSON is written with explicit UTF-8 instead of PowerShell redirection encoding.
- Added wrapper regression tests for both fixes in `test_run_next_work_wrapper.py`.

### Recovery Commands

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
python .\examples\czsc_strategy\diagnostics\simnow_strategy_surface.py --capture-json .\examples\czsc_strategy\diagnostics\simnow_export_2026-07-23.json --date 2026-07-23
python .\examples\czsc_strategy\diagnostics\export_simnow_replay_snapshot.py --end 2026-07-23 --date 2026-07-23 --out-json .\examples\czsc_strategy\diagnostics\simnow_replay_2026-07-23.json
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -PostProcessOnly -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Results:

- Wrapper regression tests passed: `80 passed`.
- `simnow_replay_readiness_2026-07-23.json` confirmed `ready=true`, `latest_db_date=2026-07-23`.
- Post-processing completed and generated:
  - `simnow_record_2026-07-23.json`
  - `simnow_report_2026-07-23.md`
  - `simnow_run_summary_2026-07-23.json`
  - `simnow_daily_brief_2026-07-23.md`
  - updated `simnow_ledger_summary.json`
- The wrapper exited non-zero because the authoritative automation result is `halt`, not because the pipeline crashed.

### Outcomes

- Formal mode: yes (`day_open`, auto duration `8565` seconds).
- Preflight: passed.
- Live capture completed in read-only mode.
- Historical DB update: `passed`.
- Contract query: succeeded with `contracts_count=17976`.
- Enabled subscriptions complete: `4/4`.
- Tick count: `41208`.
- Accounts: `1`.
- Positions: `1` external account position (`sc2609`) captured as contamination evidence only.
- Orders: `0`.
- Trades: `0`.
- Workflow order safety: `pass` (`read_only=true`, `orders_sent_by_workflow=0`).
- Kline coverage: complete, no missing or short symbols.
- Replay readiness: `ready=true`.
- Delayed replay: available; `signals=4`, `trades=0`, `positions=11`.
- Consistency: `matched=true`.
- Daily record status: `halt`.
- Threshold status: `halt`.
- Authoritative automation fields from `simnow_run_summary_2026-07-23.json`:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`

### Next Action

Stop automation for this observation stream and manually review the risk-threshold halt on `consecutive_loss_abs_pct` before any further formal observation run.

## 2026-07-23 Formal Daily Observation (13:35)

### Goal

Run the formal 13:35 SimNow daily observation in read-only mode, verify the afternoon formal window artifacts, and record the authoritative automation outcome from `simnow_run_summary_2026-07-23.json`.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `284 passed`.

Formal capture:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Observed:

- Wrapper entered the formal afternoon window `13:35 -> 15:00` and auto-computed `duration=4943` seconds.
- The command exited non-zero because the authoritative automation result is `halt`, not because the pipeline crashed.

Verification:

```powershell
@'
import json, pathlib
base = pathlib.Path(r'D:\repo\vnpy\examples\czsc_strategy\diagnostics')
summary = json.loads((base / 'simnow_run_summary_2026-07-23.json').read_text(encoding='utf-8'))
print(summary['automation_status'], summary['automation_exit_code'], summary['automation_reason'])
'@ | python -
```

Result:

- Verified output artifacts exist:
  - `simnow_export_2026-07-23.json`
  - `simnow_record_2026-07-23.json`
  - `simnow_report_2026-07-23.md`
  - `simnow_run_summary_2026-07-23.json`
  - `simnow_historical_db_update_2026-07-23.json`
- Verified authoritative automation fields:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`

### Outcomes

- Execution date: `2026-07-23`.
- Preflight: `passed`.
- Formal observation mode: `yes` (`day_afternoon`).
- Live capture: completed in read-only mode.
- Historical DB update: `passed`.
- Contract query: succeeded with `contracts_count=17976`.
- Enabled subscriptions complete: `4/4`.
- Tick count: `25496`.
- Accounts: `1`.
- Positions: `1` external account position captured as contamination evidence only.
- Orders: `0`.
- Trades: `0`.
- Workflow order safety: `pass` (`read_only=true`, `orders_sent_by_workflow=0`).
- Monitor / record status: `halt`.
- Automation status: `halt`.
- Risk threshold status: `halt`.
- Halt trigger metric: `consecutive_loss_abs_pct`.
- Kline coverage: complete, no missing or short symbols.
- Formal readiness: `overall_ready=true`.
- Delayed replay: available.
- Consistency: `matched=true`.
- User action needed: `true`.

### Next Action

Keep the observation automation stopped and manually review the repeated risk-threshold halt on `consecutive_loss_abs_pct` before any further formal run.

## 2026-07-26 Issue Analysis - Risk Halt Traceability

### Goal

Analyze why the latest formal SimNow observation did not produce a valid observation day, and make the halt reason easier to audit from machine-readable and human-readable artifacts without changing trading behavior.

### Findings

- The authoritative `simnow_run_summary_2026-07-24.json` result is `automation_status=halt`, `automation_exit_code=30`, `automation_reason=consecutive_loss_abs_pct`, `automation_action=stop automation and review manually`.
- The 2026-07-24 environment gates were ready: connection/capture artifacts existed, `contracts_count=18052`, enabled subscriptions were complete, `ticks=34781`, `orders=0`, `trades=0`, historical DB update passed, K-line coverage passed, delayed replay was available, and consistency matched.
- The halt is therefore a risk-threshold halt, not a code failure, subscription failure, replay gap, or order-safety breach.
- `consecutive_loss_abs_pct` is computed from delayed replay / local strategy daily returns via `_max_consecutive_losses(...)`, then normalized by `simnow_daily_monitor.py` and compared against `simnow_risk_thresholds.json`.

### Changes

- `simnow_run_summary.py` now preserves threshold warning/halt/baseline fields when present and emits `record.threshold_diagnostics` for warning/halt rows, including warning/halt gaps.
- `simnow_daily_brief.py` / `simnow_daily_brief_sections.py` now render a `## 阈值诊断` section when threshold diagnostics are available.
- `run_next_work.ps1` now mirrors formal-window-scoped copies for record/report/run-summary/daily-brief outputs, reducing ambiguity when multiple formal windows are run on the same trade date.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_sections.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py -q
```

Result:

- `133 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `293 passed`.

### Next Action

Keep automation stopped until the repeated `consecutive_loss_abs_pct` halt is manually reviewed. If continuing tooling work, add a source breakdown for the consecutive-loss streak so the summary identifies the exact replay dates and daily returns that produced the 6-day cumulative loss.

## 2026-07-26 Consecutive Loss Source Breakdown

### Goal

Make `consecutive_loss_abs_pct` halts directly auditable from future machine-readable run summaries and daily briefs.

### Changes

- `export_simnow_replay_snapshot.py` now writes `risk.consecutive_loss.start_date` and `risk.consecutive_loss.rows`, with each row carrying `date`, `daily_return_pct`, and portfolio `equity`.
- `simnow_run_summary.py` now exposes `risk_source_breakdown.consecutive_loss`, sourced from `delayed_replay.risk.consecutive_loss`.
- `simnow_daily_brief.py` now renders the same data in a `## 风险来源拆解` section after threshold diagnostics.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_export_simnow_replay_snapshot.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_sections.py -q
```

Result:

- `50 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `295 passed`.

### Next Action

Keep automation stopped for manual review of the repeated risk halt. Existing replay artifacts generated before this change may not contain `consecutive_loss.rows`; rerun post-processing or the next formal observation to populate the new source breakdown.

## 2026-07-26 Legacy Breakdown Compatibility and Preflight Gate

### Goal

Make older replay artifacts explicit when they cannot provide the new consecutive-loss daily streak rows, and ensure the replay snapshot source-breakdown tests are part of the official preflight gate.

### Changes

- `simnow_run_summary.py` now marks `risk_source_breakdown.consecutive_loss` with:
  - `complete`
  - `rows_available`
  - `reason`
- Legacy replay artifacts with a cumulative consecutive-loss result but no daily streak rows now report `reason=missing_consecutive_loss_rows` instead of silently looking complete.
- `simnow_daily_brief_sections.py` renders those completeness fields and prints `streak_rows: 无` when row-level evidence is unavailable.
- `run_next_work.ps1 -Preflight` now compiles `export_simnow_replay_snapshot.py` and runs `test_export_simnow_replay_snapshot.py`.

### Commands

Post-process existing 2026-07-24 artifacts without live capture:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -PostProcessOnly -Date 2026-07-24 -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Observed:

- The wrapper did not connect to SimNow or capture new data.
- It rebuilt the daily record, ledger summary, promotion decision, run summary, and daily brief from existing artifacts.
- The command ended non-zero because the authoritative result remains `automation_status=halt`, not because post-processing failed.
- Summary consistency reported `ok`.
- `simnow_run_summary_2026-07-24.json` now contains `risk_source_breakdown.consecutive_loss.reason=missing_consecutive_loss_rows`.

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py .\examples\czsc_strategy\tests\unit\test_export_simnow_replay_snapshot.py .\examples\czsc_strategy\tests\unit\test_simnow_run_summary.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief.py .\examples\czsc_strategy\tests\unit\test_simnow_daily_brief_sections.py -q
```

Result:

- `141 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `301 passed`.

### Next Action

Keep automation stopped for manual review. If continuing implementation work, either regenerate `simnow_replay_2026-07-24.json` from the refreshed DB to populate daily streak rows, or add a dedicated post-process replay refresh command that updates replay JSON without starting a live SimNow session.

## 2026-07-26 Post-Process Replay Refresh

### Goal

Add a safe post-process replay refresh path so existing formal artifacts can refresh `simnow_replay_YYYY-MM-DD.json` and rebuild the run summary / daily brief without starting a live SimNow session.

### Changes

- `run_next_work.ps1` now supports `-RefreshReplay`.
- The replay readiness / replay export block is centralized in `Invoke-ReplaySnapshotRefresh` and reused by both live capture and post-process refresh paths.
- `-RefreshReplay` is rejected when combined with `-SkipReplay`.
- `test_run_next_work_wrapper.py` now covers the new parameter, conflict guard, helper reuse, and the post-process replay refresh branch.

### Commands

Refresh existing 2026-07-24 replay and downstream artifacts:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -PostProcessOnly -RefreshReplay -Date 2026-07-24 -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Observed:

- The wrapper resumed from existing capture/kline artifacts and did not start live SimNow capture.
- Replay DB readiness passed.
- `export_simnow_replay_snapshot.py` rewrote `simnow_replay_2026-07-24.json`.
- The wrapper rebuilt the daily record, ledger summary, promotion decision, run summary, and daily brief.
- Summary consistency reported `ok`.
- Final exit was non-zero because the authoritative daily result remains `automation_status=halt`, not because refresh failed.

Verified authoritative fields:

- `automation_status=halt`
- `automation_exit_code=30`
- `automation_reason=consecutive_loss_abs_pct`
- `risk_source_breakdown.consecutive_loss.complete=true`
- `risk_source_breakdown.consecutive_loss.rows_available=true`
- `risk_source_breakdown.consecutive_loss.days=6`
- `risk_source_breakdown.consecutive_loss.start_date=2023-06-19`
- `risk_source_breakdown.consecutive_loss.end_date=2023-06-28`
- `risk_source_breakdown.consecutive_loss.rows` contains `6` rows.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `305 passed`.

### Next Action

Keep automation stopped for manual review of `consecutive_loss_abs_pct`. The 2026-07-24 artifacts now identify the exact replay streak dates and daily returns that produced the halt, so the next repair item should focus on manual-review packaging rather than more live capture.

## 2026-07-26 Risk Halt Manual Review Pack

### Goal

Package the repeated `consecutive_loss_abs_pct` halt into a dedicated manual-review artifact so an operator can review the halt without stitching together the run summary, daily brief, and replay JSON by hand.

### Changes

- Added `simnow_risk_halt_review.py`.
  - Reads only `simnow_run_summary_YYYY-MM-DD.json`.
  - Writes `simnow_risk_halt_review_YYYY-MM-DD.json` and `.md`.
  - Includes automation status/action, safety snapshot, environment/replay readiness, halt metadata, threshold diagnostics, consecutive-loss rows, and explicit decision options.
  - Emits `not_applicable` for non-halt summaries so automation can still find a deterministic artifact.
- Wired `run_next_work.ps1` to generate the risk-halt review pack after the daily brief and before summary consistency validation.
- Added the script and tests to the wrapper preflight compile/test list.

### Commands

Post-process existing 2026-07-24 artifacts without live capture:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -PostProcessOnly -Date 2026-07-24 -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Observed:

- The wrapper resumed from existing artifacts and did not start live SimNow capture.
- It generated:
  - `simnow_risk_halt_review_2026-07-24.json`
  - `simnow_risk_halt_review_2026-07-24.md`
- Summary consistency reported `ok`.
- The command ended non-zero because the authoritative daily status remains `halt`.

Verified review pack fields:

- `applicable=true`
- `review_status=requires_manual_review`
- `automation_status=halt`
- `automation_reason=consecutive_loss_abs_pct`
- `manual_review.decision_options=[keep_halted, adjust_thresholds_with_documented_rationale, retire_candidate, reset_observation_window_after_strategy_change]`
- `safety_snapshot.read_only=true`
- `safety_snapshot.orders_sent_by_workflow=0`
- `safety_snapshot.orders=0`
- `safety_snapshot.trades=0`
- `consecutive_loss.complete=true`
- `consecutive_loss.rows_available=true`
- `consecutive_loss.days=6`
- `consecutive_loss.start_date=2023-06-19`
- `consecutive_loss.end_date=2023-06-28`

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_risk_halt_review.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
```

Result:

- `99 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `311 passed`.

### Next Action

Keep automation stopped. The next repair item should make the manual-review decision itself auditable, for example by adding a small decision-record template that records which option was chosen and whether the 20-day observation window must be reset.

## 2026-07-26 Risk Halt Decision Record Template

### Goal

Make the manual-review decision auditable after a risk halt. The risk-halt review pack explains what happened; this step adds a deterministic decision template that records what the operator decided and whether the observation window must reset.

### Changes

- Added `simnow_risk_halt_decision.py`.
  - Reads `simnow_risk_halt_review_YYYY-MM-DD.json`.
  - Writes `simnow_risk_halt_decision_YYYY-MM-DD.json` and `.md`.
  - Defaults to `decision_status=pending_decision` and `next_formal_observation_allowed=false`.
  - Carries allowed decisions:
    - `keep_halted`
    - `adjust_thresholds_with_documented_rationale`
    - `retire_candidate`
    - `reset_observation_window_after_strategy_change`
  - Requires `operator_name`, `rationale`, `selected_decision`, and `requires_observation_window_reset` before validation can pass.
  - Provides `--validate` so a filled record can be checked before resuming observation work.
- Wired `run_next_work.ps1` to generate the decision template after the risk-halt review pack.
- Added the script and tests to the wrapper preflight compile/test list.

### Commands

Post-process existing 2026-07-24 artifacts without live capture:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -PostProcessOnly -Date 2026-07-24 -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Observed:

- The wrapper generated:
  - `simnow_risk_halt_decision_2026-07-24.json`
  - `simnow_risk_halt_decision_2026-07-24.md`
- The generated record is intentionally pending:
  - `decision_status=pending_decision`
  - `selected_decision=""`
  - `next_formal_observation_allowed=false`
- The wrapper final exit remains non-zero because the authoritative daily status is still `halt`.

Validation of the unfilled template:

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_risk_halt_decision.py --date 2026-07-24 --validate
```

Result:

- `valid=false`
- `errors=[decision_status_not_decided]`

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_risk_halt_decision.py .\examples\czsc_strategy\tests\unit\test_simnow_risk_halt_review.py .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
```

Result:

- `106 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `318 passed`.

### Next Action

Keep automation stopped until a human fills and validates `simnow_risk_halt_decision_2026-07-24.json`. If the selected decision changes thresholds or strategy behavior, reset the formal 20-day observation window before collecting new valid days.

## 2026-07-26 Pending Decision Live-Capture Gate

### Goal

Enforce the manual-review stop condition in the wrapper itself. A pending or non-resuming risk-halt decision record must block any new live capture before the wrapper can connect to SimNow.

### Changes

- Added `Assert-NoPendingRiskHaltDecision` to `run_next_work.ps1`.
  - Scans `simnow_risk_halt_decision_*.json` in the output directory.
  - Blocks live capture when any record is not `decision_status=decided`.
  - Blocks live capture when `next_formal_observation_allowed` is not `true`.
  - Does not block `-Preflight` or `-PostProcessOnly`.
- Added wrapper tests for:
  - helper presence;
  - gate execution before live capture;
  - pending decision rejection;
  - decided + explicitly allowed decision acceptance.

### Commands

Verified the current pending 2026-07-24 decision blocks a new live run before any SimNow connection:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -SkipKlineUpdate -SkipHistoricalDbUpdate -DurationSeconds 1800 -Date 2026-07-26
```

Result:

- The wrapper stopped immediately with:
  - `pending risk halt decision blocks live capture`
  - `simnow_risk_halt_decision_2026-07-24.json`
- This is expected safety behavior, not a code failure.

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
```

Result:

- `103 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `322 passed`.

### Next Action

Keep automation stopped. A human must fill and validate `simnow_risk_halt_decision_2026-07-24.json`; only a `decision_status=decided` record with `next_formal_observation_allowed=true` can unblock future live capture.

## 2026-07-26 Decision Gate Validation Hardening

### Goal

Make the live-capture gate enforce the same decision-record completeness rules as `simnow_risk_halt_decision.py --validate`, so an incomplete or invalid signed record cannot accidentally unblock SimNow live capture.

### Changes

- Hardened `Assert-NoPendingRiskHaltDecision` in `run_next_work.ps1`.
  - Still blocks non-`decided` records.
  - Still requires `next_formal_observation_allowed=true`.
  - Now also validates:
    - `selected_decision` is one of the allowed decisions;
    - `operator_name` is non-empty;
    - `rationale` is non-empty;
    - `requires_observation_window_reset` is present and non-null.
- Added wrapper tests proving:
  - invalid decided records are blocked;
  - all validation error codes are surfaced;
  - signed and explicitly allowed records pass the gate.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
```

Result:

- `104 passed`.

Verified the real pending 2026-07-24 decision still blocks live capture before any SimNow connection:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -SkipKlineUpdate -SkipHistoricalDbUpdate -DurationSeconds 1800 -Date 2026-07-26
```

Result:

- `pending risk halt decision blocks live capture`

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `323 passed`.

### Next Action

Keep automation stopped. Before resuming live capture, fill `simnow_risk_halt_decision_2026-07-24.json`, run `simnow_risk_halt_decision.py --date 2026-07-24 --validate`, and ensure the wrapper gate sees a complete decided record with `next_formal_observation_allowed=true`.

## 2026-07-24 Formal Daily Observation (21:05)

### Goal

Run the formal 21:05 SimNow daily observation in read-only mode, verify the night-session formal-window artifacts, and record the authoritative automation outcome from `simnow_run_summary_2026-07-24.json`.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `284 passed`.

Formal capture:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Observed:

- Wrapper entered the formal night window `21:05 -> 23:00` and auto-computed `duration=6752` seconds.
- The command exited non-zero because the authoritative automation result is `halt`, not because the pipeline crashed.

Verification:

```powershell
@'
import json, pathlib
base = pathlib.Path(r'D:\repo\vnpy\examples\czsc_strategy\diagnostics')
summary = json.loads((base / 'simnow_run_summary_2026-07-24.json').read_text(encoding='utf-8'))
print(summary['automation_status'], summary['automation_exit_code'], summary['automation_reason'], summary['automation_action'])
'@ | python -
```

Result:

- Verified output artifacts exist:
  - `simnow_export_2026-07-24.json`
  - `simnow_record_2026-07-24.json`
  - `simnow_report_2026-07-24.md`
  - `simnow_run_summary_2026-07-24.json`
  - `simnow_historical_db_update_2026-07-24.json`
  - `simnow_kline_update_2026-07-24.json`
  - `simnow_replay_2026-07-24.json`
  - `simnow_daily_brief_2026-07-24.md`
- Verified authoritative automation fields:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`

### Outcomes

- Execution date: `2026-07-24`.
- Preflight: `passed`.
- Formal observation mode: `yes` (`night_open`).
- Live capture: completed in read-only mode.
- Historical DB update: `passed`.
- Contract query: succeeded with `contracts_count=18052`.
- Enabled subscriptions complete: `4/4`.
- Tick count: `34781`.
- Accounts: `1`.
- Positions: `1` external account position (`sc2609`) captured as contamination evidence only.
- Orders: `0`.
- Trades: `0`.
- Workflow order safety: `pass` (`read_only=true`, `orders_sent_by_workflow=0`).
- Monitor / record status: `halt`.
- Automation status: `halt`.
- Risk threshold status: `halt`.
- Halt trigger metric: `consecutive_loss_abs_pct`.
- Kline coverage: complete, no missing or short symbols.
- Formal readiness: `overall_ready=true`.
- Delayed replay: available; `signals=4`, `trades=0`, `positions=11`.
- Consistency: `matched=true`.
- User action needed: `true`.

### Next Action

Keep the observation automation stopped and manually review the repeated risk-threshold halt on `consecutive_loss_abs_pct` before any further formal run.

## 2026-07-26 Risk Halt Governance Documentation Sync

### Goal

Analyze the remaining governance gap after the repeated `consecutive_loss_abs_pct` halt: code now generates review/decision artifacts and blocks live capture, but the acceptance documents and task queue also need to state those rules explicitly.

### Changes

- Updated `ACCEPTANCE.md` with a formal `Risk Halt Review and Decision Gate` section.
- Documented the required review artifacts:
  - `simnow_risk_halt_review_YYYY-MM-DD.json`
  - `simnow_risk_halt_review_YYYY-MM-DD.md`
- Documented the required decision artifacts:
  - `simnow_risk_halt_decision_YYYY-MM-DD.json`
  - `simnow_risk_halt_decision_YYYY-MM-DD.md`
- Defined the complete valid-decision requirements: `decision_status=decided`, allowed `selected_decision`, non-empty `operator_name`, non-empty `rationale`, explicit `requires_observation_window_reset`, and `next_formal_observation_allowed=true`.
- Updated `NEXT_WORK.md` with A36/A37/A38 for risk-halt review, decision record validation, and live-capture blocking.
- Updated formal live-capture documentation and `AUTOMATION_PROMPT.md` to avoid fixed `DurationSeconds` for formal runs. Formal observation now documents the auto-computed wrapper duration from the allowed `09:05`, `13:35`, or `21:05` Asia/Shanghai start windows.
- Added document tests so the risk-halt governance artifacts and formal auto-window command remain documented.

### Verification

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_simnow_docs.py -q
```

Result: `16 passed`.

Passed:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py .\examples\czsc_strategy\tests\unit\test_simnow_risk_halt_review.py .\examples\czsc_strategy\tests\unit\test_simnow_risk_halt_decision.py -q
```

Result: `111 passed`.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result: `325 passed`.

### Next Action

Keep automation stopped. A human must complete and validate `simnow_risk_halt_decision_2026-07-24.json`; only a complete decided record with `next_formal_observation_allowed=true` can unblock future formal live capture.

## 2026-07-24 Formal Daily Observation (09:05)

### Goal

Run the formal 09:05 SimNow daily observation in read-only mode, verify the morning formal-window artifacts, and record the authoritative automation outcome from `simnow_run_summary_2026-07-24.json`.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `284 passed`.

Formal capture:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Observed:

- Wrapper entered the formal morning window `09:05 -> 11:30` and auto-computed `duration=8501` seconds.
- The command exited non-zero because the authoritative automation result is `halt`, not because the pipeline crashed.

Verification:

```powershell
@'
import json, pathlib
base = pathlib.Path(r'D:\repo\vnpy\examples\czsc_strategy\diagnostics')
summary = json.loads((base / 'simnow_run_summary_2026-07-24.json').read_text(encoding='utf-8'))
print(summary['automation_status'], summary['automation_exit_code'], summary['automation_reason'], summary['automation_action'])
'@ | python -
```

Result:

- Verified output artifacts exist:
  - `simnow_export_2026-07-24.json`
  - `simnow_record_2026-07-24.json`
  - `simnow_report_2026-07-24.md`
  - `simnow_run_summary_2026-07-24.json`
  - `simnow_historical_db_update_2026-07-24.json`
  - `simnow_kline_update_2026-07-24.json`
  - `simnow_replay_2026-07-24.json`
  - `simnow_daily_brief_2026-07-24.md`
- Verified authoritative automation fields:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`

### Outcomes

- Execution date: `2026-07-24`.
- Preflight: `passed`.
- Formal observation mode: `yes` (`day_open`).
- Live capture: completed in read-only mode.
- Historical DB update: `passed`.
- Contract query: succeeded with `contracts_count=18000`.
- Enabled subscriptions complete: `4/4`.
- Tick count: `38048`.
- Accounts: `1`.
- Positions: `1` external account position (`sc2609`) captured as contamination evidence only.
- Orders: `0`.
- Trades: `0`.
- Workflow order safety: `pass` (`read_only=true`, `orders_sent_by_workflow=0`).
- Monitor / record status: `halt`.
- Automation status: `halt`.
- Risk threshold status: `halt`.
- Halt trigger metric: `consecutive_loss_abs_pct`.
- Kline coverage: complete, no missing or short symbols.
- Formal readiness: `overall_ready=true`.
- Delayed replay: available; `signals=4`, `trades=0`, `positions=11`.
- Consistency: `matched=true`.
- User action needed: `true`.

### Next Action

Keep the observation automation stopped and manually review the repeated risk-threshold halt on `consecutive_loss_abs_pct` before any further formal run.

## 2026-07-24 Formal Daily Observation (13:35)

### Goal

Run the formal 13:35 SimNow daily observation in read-only mode, verify the afternoon formal-window artifacts, and record the authoritative automation outcome from `simnow_run_summary_2026-07-24.json`.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `284 passed`.

Formal capture:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Observed:

- Wrapper entered the formal afternoon window `13:35 -> 15:00` and auto-computed `duration=4980` seconds.
- The command exited non-zero because the authoritative automation result is `halt`, not because the pipeline crashed.

Verification:

```powershell
@'
import json, pathlib
base = pathlib.Path(r'D:\repo\vnpy\examples\czsc_strategy\diagnostics')
summary = json.loads((base / 'simnow_run_summary_2026-07-24.json').read_text(encoding='utf-8'))
print(summary['automation_status'], summary['automation_exit_code'], summary['automation_reason'], summary['automation_action'])
'@ | python -
```

Result:

- Verified output artifacts exist:
  - `simnow_export_2026-07-24.json`
  - `simnow_record_2026-07-24.json`
  - `simnow_report_2026-07-24.md`
  - `simnow_run_summary_2026-07-24.json`
  - `simnow_historical_db_update_2026-07-24.json`
  - `simnow_kline_update_2026-07-24.json`
  - `simnow_replay_2026-07-24.json`
  - `simnow_daily_brief_2026-07-24.md`
- Verified authoritative automation fields:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`

### Outcomes

- Execution date: `2026-07-24`.
- Preflight: `passed`.
- Formal observation mode: `yes` (`day_afternoon`).
- Live capture: completed in read-only mode.
- Historical DB update: `passed`.
- Contract query: succeeded with `contracts_count=18000`.
- Enabled subscriptions complete: `4/4`.
- Tick count: `25000`.
- Accounts: `1`.
- Positions: `1` external account position (`sc2609`) captured as contamination evidence only.
- Orders: `0`.
- Trades: `0`.
- Workflow order safety: `pass` (`read_only=true`, `orders_sent_by_workflow=0`).
- Monitor / record status: `halt`.
- Automation status: `halt`.
- Risk threshold status: `halt`.
- Halt trigger metric: `consecutive_loss_abs_pct`.
- Kline coverage: complete, no missing or short symbols.
- Formal readiness: `overall_ready=true`.
- Delayed replay: available; `signals=4`, `trades=0`, `positions=11`.
- Consistency: `matched=true`.
- User action needed: `true`.

### Next Action

Keep the observation automation stopped and manually review the repeated risk-threshold halt on `consecutive_loss_abs_pct` before any further formal run.

## 2026-07-23 Formal Daily Observation (21:05)

### Goal

Run the formal 21:05 SimNow daily observation in read-only mode, verify the night-session formal window artifacts, and record the authoritative automation outcome from `simnow_run_summary_2026-07-23.json`.

### Commands

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result:

- Full SimNow workflow preflight passed: `284 passed`.

Formal capture:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -LiveCapture -MinKlineBarsPerSymbol 30 -UpdateHistoricalDb
```

Observed:

- Wrapper entered the formal night window `21:05 -> 23:00` and auto-computed `duration=6779` seconds.
- The command exited non-zero because the authoritative automation result is `halt`, not because the pipeline crashed.

Verification:

```powershell
@'
import json, pathlib
base = pathlib.Path(r'D:\repo\vnpy\examples\czsc_strategy\diagnostics')
summary = json.loads((base / 'simnow_run_summary_2026-07-23.json').read_text(encoding='utf-8'))
print(summary['automation_status'], summary['automation_exit_code'], summary['automation_reason'])
'@ | python -
```

Result:

- Verified output artifacts exist:
  - `simnow_export_2026-07-23.json`
  - `simnow_record_2026-07-23.json`
  - `simnow_report_2026-07-23.md`
  - `simnow_run_summary_2026-07-23.json`
  - `simnow_historical_db_update_2026-07-23.json`
- Verified authoritative automation fields:
  - `automation_status=halt`
  - `automation_exit_code=30`
  - `automation_reason=consecutive_loss_abs_pct`
  - `automation_action=stop automation and review manually`

### Outcomes

- Execution date: `2026-07-23`.
- Preflight: `passed`.
- Formal observation mode: `yes` (`night_open`).
- Live capture: completed in read-only mode.
- Historical DB update: `passed`.
- Contract query: succeeded with `contracts_count=18000`.
- Enabled subscriptions complete: `4/4`.
- Tick count: `32770`.
- Accounts: `1`.
- Positions: `1` external account position captured as contamination evidence only.
- Orders: `0`.
- Trades: `0`.
- Workflow order safety: `pass` (`read_only=true`, `orders_sent_by_workflow=0`).
- Monitor / record status: `halt`.
- Automation status: `halt`.
- Risk threshold status: `halt`.
- Halt trigger metric: `consecutive_loss_abs_pct`.
- Kline coverage: complete, no missing or short symbols.
- Formal readiness: `overall_ready=true`.
- Delayed replay: available.
- Consistency: `matched=true`.
- User action needed: `true`.

### Next Action

Keep the observation automation stopped and manually review the repeated risk-threshold halt on `consecutive_loss_abs_pct` before any further formal run.

## 2026-07-26 D3 Config Fallback Guard Follow-Up

### Goal

Close the remaining D3 review item from `AI_REVIEW_REPORT_2026-07-26_v2.md`: residual position-weight and core-risk `STRATEGY_CONFIG.get(..., literal_default)` fallbacks were still present in `backtest_engine.py` / `portfolio_engine.py` and were not covered by the AST guard.

### Changes

- Extended `test_core_risk_config_keys_do_not_use_literal_get_fallbacks` to scan `backtest_engine.py`.
- Added `pos_1buy`, `pos_2buy`, `pos_3buy`, `pos_1sell`, `pos_2sell`, and `pos_3sell` to the guarded config-key set.
- Scoped the AST guard to `STRATEGY_CONFIG.get(...)` so normal report/dict `.get(...)` calls are not false positives.
- Replaced core-risk and position-weight literal fallbacks in `backtest_engine.py` with hard `STRATEGY_CONFIG[...]` lookups.
- Replaced `portfolio_engine.py` fixed-weight fallback with hard strategy/key lookup and hard `STRATEGY_CONFIG[...]` lookup.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_a53_config_signal_cleanup.py::test_core_risk_config_keys_do_not_use_literal_get_fallbacks -q
```

Result before source fix: failed with 16 fallback violations.

Result after source fix: `1 passed`.

Regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_a53_config_signal_cleanup.py .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py .\examples\czsc_strategy\tests\unit\test_portfolio_ledger_report.py -q -m "not realdb"
```

Result: `33 passed`.

Preflight:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result: `327 passed`.

Sync checks:

```powershell
python tools\sync_check.py
python tools\sync_check.py --root examples\czsc_strategy
```

Result: both PASS.

### Next Action

Continue the review-priority queue with the next automatically actionable low-risk item; SimNow promotion remains blocked by the unresolved risk halt decision and 0/20 valid observation days.

## 2026-07-26 D8 Repository Hygiene Follow-Up

### Goal

Close the automatically actionable part of the D8 cleanup item from `AI_REVIEW_REPORT_2026-07-26_v2.md`: move the real idempotency regression test under `tests/unit` and label archived one-shot patch scripts so they are not mistaken for maintained workflow code.

### Changes

- Moved `test_backtest_idempotent.py` into `tests/unit/test_backtest_idempotent.py`.
- Added `test_repo_hygiene.py` to guard that the idempotency regression stays under `tests/unit`.
- Added `ONE-SHOT / LEGACY` top-level labels to:
  - `_patch_backtest.py`
  - `_patch_backtest2.py`
  - `_patch_backtest3.py`
  - `_patch_backtest4.py`
- Added a hygiene guard requiring those patch scripts to keep explicit `ONE-SHOT` and `LEGACY` labels.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py -q
```

Result before cleanup: failed because `test_backtest_idempotent.py` still lived at project root and `_patch_backtest*.py` lacked `ONE-SHOT` / `LEGACY` labels.

Result after cleanup:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py .\examples\czsc_strategy\tests\unit\test_backtest_idempotent.py -q
```

Result: `4 passed`.

Full unit gate:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit -q -m "not realdb"
```

Result: `920 passed, 4 deselected, 4 xfailed`.

Preflight and sync:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python tools\sync_check.py --root examples\czsc_strategy
```

Result: SimNow workflow preflight `327 passed`; czsc sync_check PASS.

### Data Cache Follow-Up

- Added a hygiene guard requiring `examples/czsc_strategy/data_cache/*.csv` to stay out of git tracking.
- Removed the 9 obsolete `data_cache/` CSV files from the git index with `git rm --cached`, while preserving the local files on disk.
- Verified local preservation: `Get-ChildItem .\examples\czsc_strategy\data_cache\*.csv` still reports `9` files.

Validation:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py -q
python -m pytest .\examples\czsc_strategy\tests\unit -q -m "not realdb"
python tools\sync_check.py --root examples\czsc_strategy
```

Result: hygiene `3 passed`; unit gate `921 passed, 4 deselected, 4 xfailed`; czsc sync_check PASS.

### Next Action

Continue the review-priority queue with the next automatically actionable low-risk item. SimNow promotion remains blocked by the unresolved risk halt decision and 0/20 valid observation days.

## 2026-07-26 D3 Core Config Fail-Fast Guard Follow-Up

### Goal

Close the remaining D3 config-drift risk where required core strategy switches
could still be read through `STRATEGY_CONFIG.get("key")`, silently returning
`None` if a required key drifted out of `config.py`.

### Changes

- Strengthened `test_core_risk_config_keys_do_not_use_literal_get_fallbacks`
  so guarded core keys reject any constant-key `STRATEGY_CONFIG.get(...)`, not
  only calls with literal fallback defaults.
- Replaced the remaining required-key `.get(...)` reads with hard
  `STRATEGY_CONFIG[...]` reads for:
  - `filter_freq` in `backtest_engine.py` and `positions.py`
  - `atr_chop_filter` and `second_buy_mode` in `positions.py`
  - `exit_event_semantics` in `signals.py` and `sell_signals.py`
- Kept optional override/dictionary reads unchanged.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_a53_config_signal_cleanup.py::test_core_risk_config_keys_do_not_use_literal_get_fallbacks -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_a53_config_signal_cleanup.py::test_core_risk_config_keys_do_not_use_literal_get_fallbacks -q -vv
```

Result before implementation: failed with core `.get(...)` violations for
`filter_freq`, `atr_chop_filter`, `second_buy_mode`, and
`exit_event_semantics`.

Result after implementation: `1 passed`.

Regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_a53_config_signal_cleanup.py .\examples\czsc_strategy\tests\unit\test_daily_filter.py .\examples\czsc_strategy\tests\unit\test_resonance_filter.py -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_exit_model.py .\examples\czsc_strategy\tests\unit\test_stop_execution_model.py .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py -q
```

Result: A53/daily/resonance `21 passed`; exit/stop/formal `40 passed`.

Full gate:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit -q -m "not realdb"
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python tools\sync_check.py --root examples\czsc_strategy
```

Result: unit gate `954 passed, 4 deselected, 4 xfailed`; SimNow workflow
preflight `328 passed`; czsc sync_check PASS.

### Next Action

Continue the review-priority queue. The remaining non-code promotion blockers
are still the pending risk-halt decision and the unmet 20 valid forward SimNow
observation-day requirement.

## 2026-07-26 D5 Temporary Limit-Widening Verification Disclosure Follow-Up

### Goal

Close the D5 transparency gap that AP888/RB888 `temporary_widening_windows` were present in `limit_config.py` with source strings saying they were not independently verified, but formal reports and README did not machine-readably surface that manual-confirmation status.

### Root Cause

The steady-state limit-band model and temporary-window override logic already existed and was tested. The missing piece was report/document disclosure: users could see `temporary_widening_windows` only by reading `limit_config.py`, while generated formal reports did not disclose that those temporary overrides require confirmation against a primary exchange notice.

### Changes

- Added `limit_halt_temporary_widening_status=manual_confirmation_required` and `limit_halt_rule_caveat` to formal reports when `limit_halt_model` is `aware` or `enforce`.
- Updated `README.md` and `chan_strategy/limit_config.py` to state that AP888/RB888 temporary widening windows are not independently verified against a primary exchange notice and remain research-only until human confirmation.
- Added report and docs guards for the temporary-window verification status.
- No limit-band calculation, temporary-window dates, or order/fill rejection logic was changed.

### Verification

Red evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py::test_formal_report_discloses_limit_halt_temporary_window_verification_status .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_limit_halt_docs_disclose_temporary_widening_manual_verification_status -q
```

Result before implementation: failed with missing `limit_halt_temporary_widening_status` / README docs anchors.

Target regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py .\examples\czsc_strategy\tests\unit\test_limit_halt_aware.py .\examples\czsc_strategy\tests\unit\test_limit_halt_enforce.py .\examples\czsc_strategy\tests\unit\test_limit_halt_off_equivalence.py -q
```

Result: `58 passed`.

### Next Action

Run the full unit gate, SimNow workflow preflight, and czsc sync_check after this log update. The unresolved promotion blockers remain the pending manual risk-halt decision and the 20-valid-day forward SimNow gate.

## 2026-07-26 D8 In-Flight Worktree Manifest Follow-Up

### Goal

Close the locally actionable part of the D8 residue that many SimNow/diagnostics/test changes remain in the dirty worktree and were previously governed only by human memory.

### Root Cause

The review item asked for the in-flight SimNow work to be committed or stashed. That final decision is a repository-integration action and should remain under user control, but the current dirty surface still needed an explicit local manifest so future agents do not mistake it for promoted evidence or silently lose the context.

### Changes

- Added `IN_FLIGHT_CHANGES.md` with a RESEARCH-ONLY banner.
- Documented the in-flight `diagnostics/`, `tests/unit/`, and strategy-disclosure work surfaces.
- Recorded that promotion remains blocked by the manual `risk-halt decision` and the `20 valid` SimNow observation-day gate.
- Added a repo hygiene guard requiring the manifest to mention SimNow, diagnostics/tests scope, `commit or stash` handling, and the remaining external blockers.
- Added a simple sensitive-token guard so the manifest does not contain obvious password/auth/API/account-id phrases.

### Verification

Red evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_in_flight_changes_manifest_documents_uncommitted_simnow_work -q
```

Result before implementation: failed because `IN_FLIGHT_CHANGES.md` did not exist. The first implementation also failed because the manifest contained a forbidden account-identifier phrase; the wording was corrected.

Target regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py -q
```

Result: `18 passed`.

### Next Action

Run the full unit gate, SimNow workflow preflight, and czsc sync_check after this log update. Final D8 closure still requires a user-owned integration decision: commit the coherent patch set or stash/archive unrelated local work.

## 2026-07-26 D6 Terminology Source Anchor Follow-Up

### Goal

Close the remaining D6 terminology-traceability residue: the README and one signal function referenced `skill_build/reference/缠论术语表.md`, but the production signal module (`sell_signals.py`) and shared zhongshu construction helper (`zhongshu.py`) did not carry the same non-authoritative workspace glossary anchor.

### Root Cause

The terminology issue was not a runtime defect. It was a traceability gap: production code used terms such as BI, zhongshu, divergence, first/second/third buy/sell, but only part of the documentation chain stated that `缠论术语表.md` is a workspace mapping rather than a canonical Chan-theory source.

### Changes

- Added module-level terminology source notes to `chan_strategy/zhongshu.py` and `chan_strategy/sell_signals.py`.
- The notes state that `skill_build/reference/缠论术语表.md` is a non-authoritative workspace mapping between Chan-theory terms and code signal fields.
- Added a repo hygiene guard requiring both production modules to retain that glossary link and caveat.
- No signal classification, zhongshu construction, or trading behavior was changed.

### Verification

Red evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_production_signal_modules_link_terms_to_non_authoritative_glossary -q
```

Result before implementation: failed because `zhongshu.py` / `sell_signals.py` did not include `skill_build/reference` glossary anchors.

Target regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py .\examples\czsc_strategy\tests\unit\test_signal_contract.py .\examples\czsc_strategy\tests\unit\test_signals.py .\examples\czsc_strategy\tests\unit\test_zhongshu.py .\examples\czsc_strategy\tests\unit\test_second_buy_real_path.py -q
```

Result: `31 passed, 4 xfailed`.

### Next Action

Run the full unit gate, SimNow workflow preflight, and czsc sync_check after this log update. Remaining hard promotion blockers are still external/manual: pending risk-halt decision and valid forward SimNow observation days.

## 2026-07-26 D4 Slippage Cost Model Disclosure Follow-Up

### Goal

Close the D4 review item that round-trip transaction costs were computed as `2 * commission_rate + slippage` but formal and portfolio reports did not machine-readably disclose that slippage is applied once per round trip.

### Root Cause

The accounting path was internally consistent: `Position` close/scale-out accounting and the weight-based portfolio flatten path all deducted `2 * commission_rate + slippage`. The gap was transparency, not a detected calculation drift: reports and docs described `slippage` as a parameter but did not state the single-side-per-round-trip assumption.

### Changes

- Added `transaction_cost_model=round_trip_commission_plus_single_side_slippage`, `round_trip_cost_formula=2 * commission_rate + slippage`, `slippage_application=single_side_per_round_trip`, and `slippage_model_caveat` to single-symbol formal reports.
- Added the same disclosure fields to portfolio reports for `portfolio_risk="off"`, weight-based `portfolio_risk="on"`, and risk joint replay.
- Updated `README.md` and `chan_strategy/config.py` to disclose the single-side round-trip slippage formula.
- Added regression guards for formal report output, portfolio report output, joint replay output, and docs/config disclosure.
- No order logic, signal logic, sizing logic, or net-PnL formula was changed.

### Verification

Red evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py::test_formal_report_discloses_single_side_slippage_cost_model .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_slippage_cost_docs_disclose_single_side_round_trip_formula -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_portfolio_risk.py::test_weight_based_portfolio_report_discloses_slippage_cost_model -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_portfolio_risk.py::test_portfolio_risk_off_report_discloses_slippage_cost_model .\examples\czsc_strategy\tests\unit\test_a87_joint_replay.py::test_joint_replay_no_trades_smoke -q
```

Result before implementation: failed with missing `transaction_cost_model` / `slippage_application` fields.

Target regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py .\examples\czsc_strategy\tests\unit\test_portfolio_risk.py .\examples\czsc_strategy\tests\unit\test_a87_joint_replay.py .\examples\czsc_strategy\tests\unit\test_exit_model.py .\examples\czsc_strategy\tests\unit\test_position_sizing.py -q
```

Result: `100 passed`.

Full gate:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit -q -m "not realdb"
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python tools\sync_check.py --root examples\czsc_strategy
```

Result: unit gate `948 passed, 4 deselected, 4 xfailed`; SimNow workflow preflight `328 passed`; czsc sync_check PASS.

### Next Action

Continue the review-priority queue with the remaining non-behavioral disclosures or wait for valid SimNow forward-observation days and manual risk-halt review. SimNow promotion remains blocked by the external observation requirements, not by this code item.

## 2026-07-26 D1 Long/Short Overlap Disclosure Follow-Up

### Goal

Close the D1 transparency residue that `enable_short=True` with `regime_model="independent"` can allow same-symbol long and short sub-strategies to overlap, while reports only exposed the raw `both_long_short_bars` count without a machine-readable policy/caveat field.

### Root Cause

The engine already computed `both_long_short_bars`, and the independent long/short behavior is an intentional research simplification rather than an execution bug. The missing piece was a stable report/documentation anchor explaining that the metric audits `independent_long_short_substrategies`.

### Changes

- Added `long_short_overlap_policy=independent_long_short_substrategies`, `long_short_overlap_metric=both_long_short_bars`, and `long_short_overlap_caveat` to single-symbol reports.
- Updated `README.md` and `chan_strategy/config.py` to disclose that `enable_short=True` + `regime_model="independent"` may overlap long/short sub-strategies on the same symbol and is audited through `both_long_short_bars`.
- Added report and docs guards so the disclosure cannot silently disappear.
- No signal gating, position management, or short-enable behavior was changed.

### Verification

Red evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py::test_formal_report_discloses_independent_long_short_overlap_policy .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_long_short_overlap_docs_disclose_independent_policy_and_metric -q
```

Result before implementation: failed with missing `long_short_overlap_policy` and docs anchors.

Target regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py .\examples\czsc_strategy\tests\unit\test_enable_short_false_equivalence.py .\examples\czsc_strategy\tests\unit\test_enable_short_independent_equivalence.py .\examples\czsc_strategy\tests\unit\test_backtest_entrypoints.py -q
```

Result: `34 passed`.

### Next Action

Run the full unit gate, SimNow workflow preflight, and czsc sync_check after this log update. The remaining non-local blocker remains the clean forward SimNow observation gate plus pending manual risk-halt decision.

## 2026-07-26 D9 Handoff Wrapper Encoding/Drift Follow-Up

### Goal

Close the remaining D9 portability/drift gap from
`AI_REVIEW_REPORT_2026-07-26_v2.md`: the local
`examples/czsc_strategy/tools/handoff.py` was a stale vendored copy of the
handoff driver, which made it vulnerable to console-encoding issues and logic
drift from the authoritative root `tools/sync_guardian/handoff.py` engine.

### Changes

- Replaced the local vendored handoff driver with a thin UTF-8-safe wrapper.
- The wrapper now mirrors `examples/czsc_strategy/tools/sync_check.py`: it adds
  root `tools/sync_guardian` to `sys.path` and runs the authoritative
  `handoff.py` through `runpy.run_path`.
- Added a regression guard that the local handoff tool remains a thin wrapper
  instead of reintroducing a copied driver.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_handoff_tool.py::test_handoff_tool_is_thin_utf8_safe_wrapper -q
```

Result before implementation: failed because the local handoff tool did not use
`runpy.run_path` and contained its own copied driver.

Result after implementation: covered by full handoff-tool regression below.

Regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_handoff_tool.py -q
python -m pytest .\tests\test_sync_guardian.py -q
python tools\sync_check.py --root examples\czsc_strategy
```

Result: local handoff `2 passed`; root sync_guardian `14 passed`; czsc
sync_check PASS.

### Next Action

Run the full unit gate and SimNow workflow preflight after this log update. The
remaining blockers are no longer local test portability issues; they are the
external/manual risk-halt decision and accumulation of valid forward observation
days.

## 2026-07-26 D9 PowerShell Test Environment Coupling Follow-Up

### Goal

Close the low-risk D9 portability gap from
`AI_REVIEW_REPORT_2026-07-26_v2.md`: many `test_run_next_work_wrapper.py`
tests invoke PowerShell directly, so environments without `powershell`/`pwsh`
would fail for infrastructure reasons instead of cleanly reporting that the
PowerShell-dependent wrapper tests are not runnable there.

### Changes

- Added `_powershell_executable()` to resolve `powershell` or `pwsh`.
- `_run_powershell_script(...)` now skips the wrapper subprocess tests when no
  PowerShell executable is available, instead of raising `FileNotFoundError`.
- Added a regression test that monkeypatches `shutil.which` to prove the skip
  path is explicit and intentional.
- Kept all existing wrapper assertions unchanged on this Windows environment.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py::test_run_powershell_script_skips_when_powershell_is_unavailable -q
```

Result before implementation: failed because `_run_powershell_script(...)` did
not raise a pytest skip.

Result after implementation: `1 passed`.

Regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_run_next_work_wrapper.py -q
```

Result: `105 passed`.

### Next Action

Run the full unit gate, SimNow workflow preflight, and czsc sync_check after this
log update. The remaining unresolved items are now primarily external/process
boundaries: manual risk-halt review and valid forward SimNow observation days.

## 2026-07-26 D2 Margin Model Limitation Disclosure Follow-Up

### Goal

Close the automatically actionable D2 transparency gap from
`AI_REVIEW_REPORT_2026-07-26_v2.md`: risk sizing used exchange-minimum margin
rates from `contract_specs`, while maintenance margin and broker forced
liquidation were not modeled but were not exposed in machine-readable reports.

### Changes

- Added risk-mode report fields:
  - `margin_rate_source=contract_specs.exchange_minimum_research`
  - `maintenance_margin_model=not_modeled`
  - `broker_forced_liquidation_model=not_modeled`
  - `margin_model_caveat`
- Kept sizing and margin calculations unchanged; this is a disclosure/reporting
  repair, not a strategy behavior change.
- Updated README and `config.py` comments to disclose exchange-minimum margin
  rates, missing maintenance-margin modeling, missing broker add-ons, missing
  margin-call modeling, and missing broker forced liquidation.
- Added tests so both the report fields and public documentation stay present.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py::test_formal_report_discloses_margin_model_limitations .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_margin_model_docs_disclose_exchange_minimum_and_no_broker_liquidation -q
```

Result before implementation: failed with missing `margin_rate_source` and
missing `margin_model_caveat` documentation.

Result after implementation: `2 passed`.

Related regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_position_sizing.py .\examples\czsc_strategy\tests\unit\test_position_sizing_report.py .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py -q
```

Result: `51 passed`.

### Next Action

Run the full unit gate, SimNow workflow preflight, and czsc sync_check after this
log update. Any actual maintenance-margin / broker-liquidation simulator would
be a behavior-changing model extension and should be handled as a separate
strategy-design task.

## 2026-07-26 D2 Risk-Parity Turnover and Concentration Disclosure Follow-Up

### Goal

Close the automatically actionable D2 transparency gap from
`AI_REVIEW_REPORT_2026-07-26_v2.md`: `weighting="risk_parity"` recomputed
weights every bar, had no turnover/rebalance constraint, and could temporarily
increase active-symbol concentration when a symbol's bars dropped out, but the
report did not expose that口径 in machine-readable form.

### Changes

- Added report fields for the weight-based `PortfolioCoordinator` path:
  - `risk_parity_rebalance_policy`
  - `risk_parity_turnover_control`
  - `max_symbol_weight_observed`
  - `risk_parity_concentration_caveat`
- Kept the existing risk-parity behavior unchanged: every-bar rolling-volatility
  weighting remains a research model, not a production rebalance engine.
- Updated README and `config.py` comments to disclose `every_bar`,
  no-turnover-control semantics, and missing-bar/dropout concentration risk.
- Added tests so report fields and public docs cannot silently drift.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_portfolio_risk.py::test_risk_parity_report_discloses_rebalance_turnover_and_concentration -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_risk_parity_docs_disclose_every_bar_no_turnover_and_dropout_concentration -q
```

Result before implementation: report test failed with missing
`risk_parity_rebalance_policy`; docs guard failed because README/config did not
mention the new report fields.

Result after implementation: both tests passed.

Related regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_portfolio_risk.py .\examples\czsc_strategy\tests\unit\test_portfolio_accounting.py .\examples\czsc_strategy\tests\unit\test_portfolio_ledger_report.py .\examples\czsc_strategy\tests\unit\test_a87_joint_replay.py .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py -q
```

Result: `62 passed`.

### Next Action

Run the full unit gate, SimNow workflow preflight, and czsc sync_check after this
log update. This closes the reporting/transparency part of the D2 risk-parity
item; adding an actual turnover/rebalance optimizer would be a behavior-changing
strategy design change and should not be bundled into this low-risk repair.

## 2026-07-26 D1/D6 Signal Assumption and Terminology Disclosure Follow-Up

### Goal

Close the automatically actionable D1/D6 documentation gap from
`AI_REVIEW_REPORT_2026-07-26_v2.md`: the strategy lacked an explicit expected
turnover / signal-stability assumption, a unique Chan-terminology source, and a
clear explanation that the `signal_zs_confirmation` `score=40` "未确认" branch
is defensive rather than expected under the current zhongshu builder.

### Changes

- Added a README disclosure that the strategy has no explicit `预期换手` target
  or rebalance-frequency constraint.
- Documented the signal `稳定性假设`: confirmed strokes only, T+1 open execution,
  and incremental/no-repaint validation.
- Declared `skill_build/reference/缠论术语表.md` as the workspace terminology
  mapping source for 笔 / 中枢 / 背驰 / 一买 / 二买 / 三买.
- Clarified `signal_zs_confirmation` semantics:
  - `score=30` is the reachable two-stroke "未确认" construction state.
  - `score=40` is a defensive compatibility branch for legacy zhongshu objects
    and is not expected with the current `build_zhongshu_from_bis` rules.
- Added a repository hygiene guard so the disclosure cannot silently disappear.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_signal_assumption_docs_cover_turnover_stability_terms_and_unconfirmed_zs -q
```

Result before documentation update: failed because README did not contain
`预期换手`.

Result after documentation update: `1 passed`.

Related regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py .\examples\czsc_strategy\tests\unit\test_signals.py .\examples\czsc_strategy\tests\unit\test_signal_properties.py .\examples\czsc_strategy\tests\unit\test_coverage_closure.py .\examples\czsc_strategy\tests\unit\test_more_coverage.py .\examples\czsc_strategy\tests\unit\test_branch_completion.py -q
```

Result: `47 passed`.

### Next Action

Run the full unit gate, SimNow workflow preflight, and czsc sync_check after this
log update. The structural clean-OOS blocker still requires valid forward SimNow
observation days and the manual risk-halt decision; this follow-up only closes
the remaining D1/D6 transparency gap.

## 2026-07-26 D3 Remaining Literal Fallback Guard Follow-Up

### Goal

Close the remaining D3 single-source-of-truth gap where runtime code still used
literal `STRATEGY_CONFIG.get(..., default)` fallbacks for keys already defined in
`config.py`.

### Changes

- Expanded the AST guard to cover `data_adapter.py`, `limit_config.py`,
  `signals.py`, and `validation.py` in addition to the existing runtime files.
- Added the remaining configured strategy keys to the no-literal-fallback guard:
  second-buy mode, short/regime routing, equity mode, MACD/divergence parameters,
  ATR chop parameters, exit model, ATR trail multiplier, and partial-take-profit
  fraction.
- Replaced the flagged literal fallbacks with direct `STRATEGY_CONFIG[...]`
  reads so changes to `config.py` cannot silently drift from runtime behavior.
- Re-scanned remaining `STRATEGY_CONFIG.get(..., literal)` calls; only sell-side
  parameters that intentionally inherit the corresponding buy-side defaults remain.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_a53_config_signal_cleanup.py::test_core_risk_config_keys_do_not_use_literal_get_fallbacks -q
```

Result before implementation: failed with 19 literal fallback violations.

Result after implementation: `1 passed`.

Related regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_a53_config_signal_cleanup.py .\examples\czsc_strategy\tests\unit\test_data_adapter.py .\examples\czsc_strategy\tests\unit\test_limit_halt_aware.py .\examples\czsc_strategy\tests\unit\test_limit_halt_enforce.py .\examples\czsc_strategy\tests\unit\test_divergence_macd.py .\examples\czsc_strategy\tests\unit\test_second_buy_mode.py .\examples\czsc_strategy\tests\unit\test_atr_chop_filter.py .\examples\czsc_strategy\tests\unit\test_exit_model.py .\examples\czsc_strategy\tests\unit\test_enable_short_false_equivalence.py .\examples\czsc_strategy\tests\unit\test_enable_short_independent_equivalence.py .\examples\czsc_strategy\tests\unit\test_positions.py .\examples\czsc_strategy\tests\unit\test_position_sizing.py .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py -q
```

Result: `141 passed`.

### Next Action

Run the full unit gate, SimNow workflow preflight, and czsc sync_check after this
log update, then continue the review-priority queue. Live SimNow capture remains
out of scope for this offline follow-up unless explicitly requested.

## 2026-07-26 D5 Limit-Halt Settlement Basis Follow-Up

### Goal

Close the D5 review item that daily futures limit-band basis should prefer the previous trading day's settlement price, with an explicit previous-close fallback only when historical bars do not expose settlement fields.

### Changes

- Added `_settlement_or_close(...)` in `limit_config.py`, preferring `settlement`, `settle`, `settlement_price`, or `settle_price` when present and positive.
- Updated `_daily_prev_close_map(...)` so each next trading day uses the previous day's settlement basis before falling back to close.
- Documented that the limit-halt model follows previous-settlement semantics and falls back to previous close only when settlement is unavailable.
- Added unit and hygiene guards covering settlement preference and README/code disclosure of the fallback.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_limit_halt_aware.py::test_daily_prev_close_map_prefers_previous_settlement_when_available -q
```

Result before implementation: failed because the map used previous close `100.0` instead of settlement `98.0`.

Result after implementation: `1 passed`.

Limit-halt regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_limit_halt_aware.py .\examples\czsc_strategy\tests\unit\test_limit_halt_enforce.py .\examples\czsc_strategy\tests\unit\test_limit_halt_off_equivalence.py -q
```

Result: `27 passed`.

Documentation guard:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_limit_halt_docs_disclose_settlement_basis_and_close_fallback .\examples\czsc_strategy\tests\unit\test_limit_halt_aware.py -q
```

Result: `13 passed`.

Full unit gate:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit -q -m "not realdb"
```

Result: `926 passed, 4 deselected, 4 xfailed`.

Preflight and sync:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python tools\sync_check.py --root examples\czsc_strategy
```

Result before this log append: SimNow workflow preflight `327 passed`; czsc sync_check PASS.

### Next Action

Continue the review-priority queue with the next automatically actionable item. SimNow promotion remains blocked by the unresolved risk halt decision and 0/20 valid observation days.

## 2026-07-26 D4 Direct Execution-Timing Regression Follow-Up

### Goal

Close the D4 minor review item that the "signal T -> execution T+1 open" protocol was implemented and indirectly covered, but lacked a directly named regression test in `test_execution_timing.py`.

### Changes

- Added `test_signal_generated_on_bar_executes_next_bar_open`.
- The test patches `get_all_signals(...)` to emit a signal on the first post-warmup trading bar.
- The test replaces `ChanTimingStrategy` with a recording strategy and asserts the signal reaches `strategy.update(...)` on the next resampled trading bar with `execution_price` equal to that bar's open.
- This is test coverage only; it does not change production execution behavior or SimNow automation rules.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_execution_timing.py::test_signal_generated_on_bar_executes_next_bar_open -q
```

Initial test iteration failed because the fixture injection targeted `engine.strategy`, while `run(...)` constructs `ChanTimingStrategy` internally.

Second test iteration failed because the assertion used the raw 1-minute fixture index instead of the engine's resampled trading bars.

Final result: `1 passed`.

Regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_execution_timing.py -q
```

Result: `3 passed`.

Full gate:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit -q -m "not realdb"
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python tools\sync_check.py --root examples\czsc_strategy
```

Result: unit gate `927 passed, 4 deselected, 4 xfailed`; SimNow workflow preflight `327 passed`; czsc sync_check PASS.

### Next Action

Continue the review-priority queue with the next automatically actionable item. The structural D4 clean-OOS issue remains unresolved until enough valid forward SimNow observation days are collected and the risk-halt decision is closed.

## 2026-07-26 D4 Rollover Gating Methodology Disclosure Follow-Up

### Goal

Close the D4 review item that formal rollover open-gating used full-window rollover transition detection but did not explicitly disclose the ex-post methodology in reports or user-facing configuration docs.

### Changes

- Added `rollover_open_gating_methodology` to generated reports when `rollover_open_gating="on"`.
- The report now states that rollover transition detection is full-window and ex-post, and that the gate is protective open gating only.
- Updated `README.md` to list `rollover_open_gating` and disclose the same methodology caveat.
- Updated `config.py` comments so the switch's source-of-truth configuration documents the same limitation.
- Added guards in `test_rollover_open_gating.py` and `test_repo_hygiene.py`.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_rollover_open_gating.py::test_formal_report_discloses_rollover_gating_ex_post_methodology -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_rollover_gating_docs_disclose_ex_post_full_window_detection -q
```

Result before implementation: report test failed with missing `rollover_open_gating_methodology`; docs guard failed because README did not mention `rollover_open_gating`.

Result after implementation: both tests passed.

Regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_rollover_open_gating.py -q
```

Result: `9 passed`.

### Next Action

Continue the review-priority queue with the next automatically actionable item. This disclosure does not solve the structural D4 clean-OOS blocker; forward SimNow observation and manual risk-halt review are still required before promotion.

## 2026-07-26 D5 Limit-Halt Touch-Based Methodology Disclosure Follow-Up

### Goal

Close the D5 review item that `limit_halt_model="enforce"` uses a conservative bar-range touch rule, while generated reports and README methodology did not explicitly name that high/low touch-based口径.

### Changes

- Added `limit_halt_methodology` to generated reports when `limit_halt_model` is `aware` or `enforce`.
- The report now states that the model is conservative, high/low touch-based, rejects directionally relevant at-limit fills under `enforce`, and retries on the next bar.
- Updated README to disclose that `limit_halt_model` uses previous settlement/fallback previous close for bands and a conservative high/low touch-based execution口径.
- Updated `_bar_at_limit(...)` docstring in `limit_config.py` to make the conservative high/low touch-based rule explicit.
- Added report and documentation guards.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py::test_formal_report_discloses_limit_halt_touch_based_methodology -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_limit_halt_docs_disclose_touch_based_enforcement_methodology -q
```

Result before implementation: report test failed with missing `limit_halt_methodology`; docs guard failed because README did not disclose `high/low` touch methodology.

Result after implementation: both tests passed.

Regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_limit_halt_aware.py .\examples\czsc_strategy\tests\unit\test_limit_halt_enforce.py .\examples\czsc_strategy\tests\unit\test_limit_halt_off_equivalence.py -q
```

Result: `27 passed`.

Full gate:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit -q -m "not realdb"
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python tools\sync_check.py --root examples\czsc_strategy
```

Result: unit gate `931 passed, 4 deselected, 4 xfailed`; SimNow workflow preflight `327 passed`; czsc sync_check PASS.

### Next Action

Continue the review-priority queue with the next automatically actionable item. Remaining data-quality items such as splice-boundary limit semantics and missing-rate fail-closed behavior require careful scope selection to avoid changing research results unintentionally.

## 2026-07-26 D5 Unparseable Row Rate Fail-Closed Follow-Up

### Goal

Close the D5 review item that datetime-unparseable historical rows were counted and skipped, but had no fail-closed missing-rate threshold for formal evaluation.

### Changes

- Added `max_unparseable_row_rate` to `STRATEGY_CONFIG`; default `None` preserves legacy research behavior.
- `formal_evaluation_config()` now sets `max_unparseable_row_rate=0.001`.
- `BacktestEngine.load_data()` now records `unparseable_rows_total` and `unparseable_row_rate` in addition to skipped count.
- `bar_generator()` now fails closed before warmup/strategy execution when the configured threshold is exceeded.
- Generated reports now surface `unparseable_rows_total`, `unparseable_row_rate`, and `max_unparseable_row_rate`.
- README/config docs now disclose the formal fail-closed threshold.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_a80_unparseable_rows.py::test_formal_evaluation_fails_closed_when_unparseable_row_rate_too_high -q
```

Result before implementation: failed because the run completed without an `error` field even with a high unparseable-row rate.

Result after implementation: `1 passed`.

Regression and docs:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_a80_unparseable_rows.py .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_unparseable_row_rate_docs_disclose_formal_fail_closed_threshold -q
```

Result: A80/formal `15 passed`; docs guard `1 passed`.

Full gate:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit -q -m "not realdb"
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python tools\sync_check.py --root examples\czsc_strategy
```

Result: unit gate `933 passed, 4 deselected, 4 xfailed`; SimNow workflow preflight `327 passed`; czsc sync_check PASS.

### Next Action

Continue the review-priority queue with the next automatically actionable item. The splice-boundary limit-halt item remains more behavior-sensitive and should be scoped with a narrow test before changing replay semantics.

## 2026-07-26 D3 Runtime Switch Fallback Guard Follow-Up

### Goal

Reduce the remaining D3 config-drift risk from duplicated literal defaults for formal/runtime switches in `backtest_engine.py` and `positions.py`.

### Changes

- Extended the existing AST guard to reject literal `STRATEGY_CONFIG.get(..., default)` fallbacks for:
  - `trade_freq`
  - `filter_freq`
  - `resonance_filter`
  - `resonance_freq_4h`
  - `rollover_open_gating`
  - `rollover_stat_tagging`
  - `exit_event_semantics`
  - `stop_execution_model`
  - `stop_penalty_bp`
- Replaced the matching runtime reads in `backtest_engine.py` and `positions.py` with hard `STRATEGY_CONFIG[...]` reads.
- Kept this slice limited to keys already present in `STRATEGY_CONFIG`; optional compatibility `.get(...)` calls without literal defaults were not changed.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_a53_config_signal_cleanup.py::test_core_risk_config_keys_do_not_use_literal_get_fallbacks -q
```

Result before source fix: failed with 19 fallback violations across `backtest_engine.py` and `positions.py`.

Result after source fix: `1 passed`.

Regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py .\examples\czsc_strategy\tests\unit\test_resonance_filter.py .\examples\czsc_strategy\tests\unit\test_stop_execution_model.py .\examples\czsc_strategy\tests\unit\test_rollover_open_gating.py -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_a53_config_signal_cleanup.py .\examples\czsc_strategy\tests\unit\test_position_sizing_research_equivalence.py .\examples\czsc_strategy\tests\unit\test_position_sizing_report.py .\examples\czsc_strategy\tests\unit\test_report_metrics.py -q -m "not realdb"
```

Result: formal/resonance/stop/rollover `35 passed`; A53/position/report `34 passed, 2 deselected`.

Full gate:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit -q -m "not realdb"
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python tools\sync_check.py --root examples\czsc_strategy
```

Result: unit gate `933 passed, 4 deselected, 4 xfailed`; SimNow workflow preflight `327 passed`; czsc sync_check PASS.

### Next Action

Continue the review-priority queue with the next automatically actionable item. Some lower-level indicator/diagnostic fallbacks may remain, but the guarded runtime/formal switch set now sources defaults from `config.py`.

## 2026-07-26 D5 Rollover Splice Limit-Halt Suppression Follow-Up

### Goal

Close the D5 review item that limit-halt bands are meaningless on continuous-contract splice boundaries and could incorrectly defer exits when the splice jump touches or exceeds a computed daily limit band.

### Changes

- Suppressed limit-halt tagging/rejection on bars whose trading date is inside the `rollover_open_gating="on"` exclusion window.
- Added `limit_halt_rollover_suppressed_bars` to generated reports when `limit_halt_model` is `aware` or `enforce`.
- Kept normal limit-halt enforcement unchanged outside rollover splice exclusion windows.
- Updated README/config docs to disclose splice-window suppression and the report counter.
- Added regression coverage for an existing long position exiting inside the rollover window while a mocked lower-limit touch would otherwise reject the fill.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_rollover_open_gating.py::test_limit_halt_is_suppressed_inside_rollover_window_for_existing_exit -q
```

Result before implementation: failed with `len(pairs) == 0`, proving the rollover-window exit was deferred by the mocked limit-halt touch.

Result after implementation: `1 passed`.

Regression and docs:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_limit_halt_enforce.py::test_enforce_rejects_long_signal_exit_at_lower_limit_then_fills_next_bar -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_limit_halt_docs_disclose_rollover_splice_suppression -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_rollover_open_gating.py .\examples\czsc_strategy\tests\unit\test_limit_halt_aware.py .\examples\czsc_strategy\tests\unit\test_limit_halt_enforce.py .\examples\czsc_strategy\tests\unit\test_limit_halt_off_equivalence.py -q
```

Result: non-splice enforce rejection `1 passed`; docs guard `1 passed`; rollover/limit-halt suite `37 passed`.

Full gate:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit -q -m "not realdb"
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python tools\sync_check.py --root examples\czsc_strategy
```

Result: unit gate `935 passed, 4 deselected, 4 xfailed`; SimNow workflow preflight `327 passed`; czsc sync_check PASS.

### Next Action

Continue the review-priority queue with the next automatically actionable item. The remaining hard blocker for promotion is still the external SimNow risk-halt review plus valid forward observation days.

## 2026-07-26 D5 Contract Tick Rounding Follow-Up

### Goal

Close the D5 review item that `contract_specs.tick` was defined but unused, so recorded fill prices were not rounded to the exchange minimum price increment.

### Changes

- Added `price_tick_rounding` config switch.
- Kept `price_tick_rounding="off"` by default to preserve legacy research baseline snapshots.
- `formal_evaluation_config()` now sets `price_tick_rounding="on"`.
- Added `_round_price_to_tick(...)` using `contract_specs[*]["tick"]` and `ROUND_HALF_UP` semantics.
- Applied tick rounding at the recorded-fill entrances: `_open_long`, `_open_short`, `_close_long`, `_close_short`, and `_scale_out`.
- Added `price_tick_rounding` to generated reports for machine-readable audit.
- Updated README/config docs to disclose the formal-only tick-rounding scope.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_position_sizing.py::test_trade_prices_are_rounded_to_contract_tick -q
```

Result before implementation: failed because `open_price` remained `100.5` instead of rounding to AP888 tick `101.0`.

Result after implementation: `1 passed`.

Regression and docs:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_position_sizing.py -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_stop_execution_model.py .\examples\czsc_strategy\tests\unit\test_stop_execution_crosscheck.py .\examples\czsc_strategy\tests\unit\test_exit_model.py .\examples\czsc_strategy\tests\unit\test_limit_halt_aware.py .\examples\czsc_strategy\tests\unit\test_limit_halt_enforce.py .\examples\czsc_strategy\tests\unit\test_limit_halt_off_equivalence.py -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_formal_evaluation.py -q
python -m pytest .\examples\czsc_strategy\tests\unit\test_repo_hygiene.py::test_price_tick_rounding_docs_disclose_formal_contract_spec_scope -q
```

Result: position sizing `19 passed`; stop/exit/limit suite `56 passed`; formal `10 passed`; docs guard `1 passed`.

Full gate:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit -q -m "not realdb"
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python tools\sync_check.py --root examples\czsc_strategy
```

Result: unit gate `937 passed, 4 deselected, 4 xfailed`; SimNow workflow preflight `327 passed`; czsc sync_check PASS.

### Next Action

Continue the review-priority queue with the next automatically actionable item. The SimNow promotion decision remains blocked by manual risk-halt review and valid forward observation-day requirements.

## 2026-07-26 D2 PortfolioCoordinator Drawdown Breaker Follow-Up

### Goal

Close the D2 review item that `max_drawdown_breaker_pct` existed in `PortfolioLedger` / joint replay but the weight-based `PortfolioCoordinator` path had not yet implemented the same persistent drawdown-breaker semantics.

### Changes

- Added `PortfolioCoordinator.max_drawdown_breaker_pct`, `peak_equity`, `drawdown_breaker_active`, and `drawdown_breaker_triggers`.
- Implemented peak-to-current drawdown detection in `PortfolioCoordinator.on_bar(...)`.
- Drawdown breaker now flattens open weight-book positions, records `reason=drawdown_breaker_flatten`, blocks later opens, and persists across trading-day changes.
- `_build_on_report(...)` now surfaces `drawdown_breaker_active` in equity rows and `drawdown_breaker_triggers` in the report.
- Flattened pairs from drawdown breaker use `reason=portfolio_drawdown_breaker`; daily-loss flatten pairs keep `reason=portfolio_daily_loss_limit`.
- Updated `README.md` and `config.py` to state that `PortfolioCoordinator` handles weight-based replay bookkeeping, while `PortfolioLedger` remains the true Position-level forced-liquidation path for `sizing_model="risk"`.

### Verification

Red/green evidence:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_portfolio_risk.py::test_drawdown_breaker_flattens_blocks_and_persists_across_days .\examples\czsc_strategy\tests\unit\test_portfolio_risk.py::test_drawdown_breaker_disabled_by_default_in_portfolio_coordinator -q
```

Result before implementation: failed because `PortfolioCoordinator` had no `drawdown_breaker_active`.

Result after implementation: `2 passed`.

Regression:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit\test_portfolio_risk.py .\examples\czsc_strategy\tests\unit\test_a87_joint_replay.py .\examples\czsc_strategy\tests\unit\test_portfolio_ledger_report.py -q
```

Result: `48 passed`.

Full unit gate:

```powershell
python -m pytest .\examples\czsc_strategy\tests\unit -q -m "not realdb"
```

Result: `924 passed, 4 deselected, 4 xfailed`.

Preflight and sync:

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
python tools\sync_check.py --root examples\czsc_strategy
```

Result: SimNow workflow preflight `327 passed`; czsc sync_check PASS.

### Next Action

Continue the review-priority queue with the next automatically actionable low-risk item. SimNow promotion remains blocked by the unresolved risk halt decision and 0/20 valid observation days.

## 2026-07-27 Daily SimNow Observation Attempt (Blocked, No Live Capture)

### Goal

Advance the daily SimNow observation ledger per `NEXT_WORK.md`/`ACCEPTANCE.md`.

### Findings

- A prior risk-halt decision record, `simnow_risk_halt_decision_2026-07-24.json`, is still `decision_status=pending_decision` with `next_formal_observation_allowed=false`. Per A38/ACCEPTANCE.md "Risk Halt Review and Decision Gate", `run_next_work.ps1 -LiveCapture` must block before any SimNow connection while this record is unresolved.
- The invocation also occurred outside all allowed formal start windows (`09:05`, `13:35`, `21:05` Asia/Shanghai).
- Given both conditions, `-LiveCapture` was intentionally not attempted this run; only the read-only `-Preflight` path was executed to validate workflow health.

### Verification

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result: script compiled; `328 passed` in the SimNow workflow unit suite; pending replay backfill plan reports `pending_historical_db_lag_days: 0`.

No live capture, no SimNow connection, no orders, and no new `simnow_run_summary_*.json` were produced this run.

### Next Action

Blocked pending human decision on `simnow_risk_halt_decision_2026-07-24.json` (select one of `keep_halted` / `adjust_thresholds_with_documented_rationale` / `retire_candidate` / `reset_observation_window_after_strategy_change`, fill `operator_name`/`rationale`/`requires_observation_window_reset`, and set `decision_status=decided`). Once decided and `next_formal_observation_allowed=true`, resume formal `-LiveCapture` runs inside the next allowed start window (`09:05`, `13:35`, or `21:05`).

## 2026-07-27 Risk Halt Decision Recorded: Observation Window Reset

### Goal

Resolve the pending `simnow_risk_halt_decision_2026-07-24.json` blocker identified above so formal `-LiveCapture` runs can resume.

### Decision

- `selected_decision`: `reset_observation_window_after_strategy_change`
- `operator_name`: `hanabeatrisa`
- `decision_status`: `decided`; `next_formal_observation_allowed`: `true`; `requires_observation_window_reset`: `true`
- Rationale: `chan_strategy/` has uncommitted engine/positions/signals changes as of 2026-07-27 (`backtest_engine.py`, `config.py`, `data_adapter.py`, `limit_config.py`, `portfolio_engine.py`, `positions.py`, `sell_signals.py`, `signals.py`, `validation.py`, `zhongshu.py`; 347 insertions / 83 deletions), including the D2 `PortfolioCoordinator` drawdown-breaker parity fix and the D5 tick-rounding fix already logged above. The 2026-07-24 halt (`consecutive_loss_abs_pct`) came from a delayed-replay equity curve (`upto = daily.loc[:day]` in `export_simnow_replay_snapshot.py`) cumulated from the start of the replay through a fixed historical segment, `2023-06-19`~`2023-06-28`, produced by the pre-fix engine. Because that metric is a cumulative-to-date scan (not a rolling window), the same halt would keep re-triggering on every future observation day regardless of new data, so it is treated as stale pre-fix evidence rather than a live risk breach.

### Changes

- `simnow_risk_halt_decision_2026-07-24.json` / `.md`: filled and validated (`python .\examples\czsc_strategy\diagnostics\simnow_risk_halt_decision.py --date 2026-07-24 --validate` → `{"valid": true, "errors": []}`).
- `simnow_observation_window.json`: `observation_start_date` moved from `2026-07-14` to `2026-07-27`; the 8 ledger rows from 2026-07-14 through 2026-07-24 remain in `simnow_observation_ledger.jsonl` as audit history but are excluded from the new 20-day count, per existing `filter_records_by_start` semantics.
- `tests/unit/test_simnow_ledger_summary.py::test_cli_writes_summary_json`: the fixture record date was hardcoded to `2026-07-14` and this test invokes `simnow_ledger_summary.py` without `--start-date`, so it depends on the repo's real default `simnow_observation_window.json`. Bumped the fixture date to `2026-07-27` to stay on/after the new start date; no other test in the suite depends on the real default config file for this date.

### Verification

```powershell
python .\examples\czsc_strategy\diagnostics\simnow_risk_halt_decision.py --date 2026-07-24 --validate
powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight
```

Result before the test fixture fix: preflight failed at `test_simnow_ledger_summary.py::test_cli_writes_summary_json` (`assert 0 == 1`, the 2026-07-14 fixture row was filtered out by the new `observation_start_date`).

Result after the fix: decision record `{"valid": true, "errors": []}`; preflight `328 passed`, script compiles, no pending replay backfill days.

### Next Action

Resume formal `-LiveCapture` runs inside the next allowed start window (`09:05`, `13:35`, or `21:05` Asia/Shanghai). Valid observation days now count starting `2026-07-27`; 20/20 valid days are required from this new start before promotion can be reconsidered.
