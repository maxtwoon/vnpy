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
- Daily record status is `pending` with reason `historical_db_lag`; `consistency_matched=false`.
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
