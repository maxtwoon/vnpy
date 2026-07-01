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
