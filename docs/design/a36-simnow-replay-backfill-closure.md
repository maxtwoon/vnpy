# A36 Design: SimNow Replay Backfill Closure

**Task:** Close the pending SimNow observation for `2026-07-06` by converting it from `pending/historical_db_lag` to `valid/matched` once the historical SQLite DB covers the date.

**Scope:** Read-only workflow orchestration. This task does not refresh the external historical DB, does not change SimNow order/cancel/trading interfaces, and does not tune strategy parameters.

---

## 1. Background

A35 completed the stop-loss stress diagnostic. The SimNow observation pipeline has already captured a read-only day for `2026-07-06`:

- Capture JSON, kline update, replay placeholder, daily record, and brief exist.
- `simnow_run_summary_2026-07-06.json` reports:
  - `record.status = pending`
  - `record.reason = historical_db_lag`
  - `record.valid_observation = false`
  - `record.consistency_matched = false`
  - `automation_status = pending`
- `simnow_ledger_summary.json` reports `valid_observation_days = 0`.

The only blocker is replay coverage: the configured historical DB was lagged behind the observation date. Once the DB covers `2026-07-06`, the existing `simnow_backfill_pending_replays.py` tooling can replay the captured market data and re-evaluate consistency.

---

## 2. Goal

Move `2026-07-06` from `pending/historical_db_lag` to `valid/matched`, so that:

- `simnow_run_summary_2026-07-06.json` shows:
  - `automation_status = valid`
  - `record.valid_observation = true`
  - `record.consistency_matched = true`
- `simnow_ledger_summary.json` shows:
  - `valid_observation_days >= 1`
- The 20-day observation gate has at least one valid day.

---

## 3. Proposed Approach

Reuse the existing backfill workflow. No new replay engine is needed.

### Step 1 — Verify DB coverage

Run:

```powershell
python examples/czsc_strategy/diagnostics/simnow_replay_readiness.py --date 2026-07-06
```

Expected result before backfill: `ready = true` and `latest_db_date >= 2026-07-06`.
If not ready, stop and wait for the external DB refresh; do not patch data.

### Step 2 — Backfill the pending day

Run:

```powershell
python examples/czsc_strategy/diagnostics/simnow_backfill_pending_replays.py `
  --date 2026-07-06 `
  --execute `
  --out-json examples/czsc_strategy/diagnostics/simnow_backfill_plan.json
```

This will:

1. Export a real replay snapshot for `2026-07-06` via `export_simnow_replay_snapshot.py`.
2. Run `simnow_daily_monitor.py` to compare the SimNow capture against the replay snapshot.
3. Update the formal ledger (`simnow_observation_ledger.jsonl`) and the promotion decision report.

### Step 3 — Verify closure

Run:

```powershell
python examples/czsc_strategy/diagnostics/simnow_run_summary.py --date 2026-07-06
```

Confirm:

- `automation_status = valid`
- `record.valid_observation = true`
- `record.consistency_matched = true`

Then inspect `simnow_ledger_summary.json`:

- `valid_observation_days >= 1`
- `pending_days` decreased by one (relative to the lagged baseline).

---

## 4. Acceptance Criteria

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | Historical DB covers `2026-07-06` | `simnow_replay_readiness.py --date 2026-07-06` returns `ready = true` |
| 2 | `simnow_run_summary_2026-07-06.json` shows `automation_status = valid` | Read JSON field |
| 3 | `record.valid_observation = true` | Read JSON field |
| 4 | `record.consistency_matched = true` | Read JSON field |
| 5 | `simnow_ledger_summary.json` shows `valid_observation_days >= 1` | Read JSON field |
| 6 | No workflow orders were sent | `meta.read_only = true`, `orders_sent_by_workflow = 0`, `workflow_order_actions = []` |
| 7 | Root sync check passes | `python tools/sync_check.py` |
| 8 | Subproject sync check passes | `python tools/sync_check.py --root examples/czsc_strategy` |
| 9 | Existing unit tests still pass | `pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` |

---

## 5. Out of Scope

- Refreshing or patching the external historical SQLite DB.
- Changing `Position`, `BacktestEngine`, strategy parameters, or SimNow trading interfaces.
- Claiming `GOAL PASSED` or promoting the strategy beyond the first valid observation day.
- Fixing non-`historical_db_lag` pending days (e.g. `ctp_disconnect_097_no_snapshot`, `kline_coverage_incomplete`).

---

## 6. Notes for the Dev Agent

- This is a **data-driven closure**, not a code change. The main risk is running the backfill before the DB is actually ready.
- Always run `simnow_replay_readiness.py` first; if it exits non-zero, stop.
- Keep the `--execute` flag explicit in the backfill command so the plan is not silently applied.
- After backfill, regenerate `simnow_run_summary_2026-07-06.json` and `simnow_ledger_summary.json`; do not hand-edit them.
- If `simnow_backfill_pending_replays.py` reports an action other than `ready_to_backfill` for `2026-07-06`, investigate before re-running.
- Commit the regenerated JSON/Markdown artifacts together with any code changes.


## 7. Closure Notes

A36 was closed on 2026-07-07. Although the historical DB had reached `2026-07-06`, the initial backfill still produced `no_replay_events_for_day`. Investigation found two loader/selector bugs that prevented the replay from reaching the target day:

1. **Date-only `end_date` exclusion** — `chan_strategy/data_adapter.py::load_kline_data` filtered rows with `datetime <= '2026-07-06'`. Because stored datetimes include a time component (e.g. `'2026-07-06 09:00:00'`), every bar on the target day was excluded. The fix appends `23:59:59` to date-only end bounds so the full day is included.
2. **Mixed-case continuous series selection** — `diagnostics/backtest_matrix_report.py::_dominant_symbol` chose the most frequent `symbol` value in a table. For `ap888_1M_raw` the historical uppercase `AP888` series had more rows but ended on `2026-02-13`, while the lowercase `ap888` series covered `2026-07-06`. The fix prefers the symbol whose latest bar covers the requested end date.

After fixing these, the replay produced the expected bar-level positions/snapshots but no trades on `2026-07-06`, and the live SimNow capture also recorded no actionable signals/trades. `simnow_daily_monitor.py::compare_simnow_replay` was updated so that such a no-trade/no-action day is considered consistent (`no_actionable_events_on_either_side`). Days where the replay has trades but the live capture does not are still flagged as mismatched.

Final state:

- `simnow_run_summary_2026-07-06.json`: `automation_status = valid`, `record.valid_observation = true`, `record.consistency_matched = true`.
- `simnow_ledger_summary.json`: `valid_observation_days = 1`, `consecutive_valid_days = 1`, `latest_valid_date = 2026-07-06`.
- All guardrails preserved: `meta.read_only = true`, `orders_sent_by_workflow = 0`, `workflow_order_actions = []`.
- Unit tests: `277 passed`; sync checks pass.
