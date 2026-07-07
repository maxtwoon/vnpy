---
task: A36 SimNow Replay Backfill Closure
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-07
deliverables:
  - HANDOFF.md
  - docs/design/a36-simnow-replay-backfill-closure.md
  - examples/czsc_strategy/chan_strategy/data_adapter.py
  - examples/czsc_strategy/diagnostics/backtest_matrix_report.py
  - examples/czsc_strategy/diagnostics/simnow_daily_monitor.py
  - examples/czsc_strategy/diagnostics/export_simnow_replay_snapshot.py
  - examples/czsc_strategy/tests/unit/test_backtest_matrix_report.py
  - examples/czsc_strategy/tests/unit/test_data_adapter.py
  - examples/czsc_strategy/tests/unit/test_simnow_daily_monitor.py
blockers: []
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

A35 (stop-loss stress diagnostics) has reached `done`. The remaining open item is a single SimNow observation day that is stuck in `pending/historical_db_lag`:

- `simnow_run_summary_2026-07-06.json` reports:
  - `automation_status = pending`
  - `record.reason = historical_db_lag`
  - `record.valid_observation = false`
  - `record.consistency_matched = false`
- `simnow_ledger_summary.json` reports `valid_observation_days = 0`.

The read-only capture for `2026-07-06` is already complete; the only blocker is that the historical SQLite DB did not yet cover the observation date when the replay was first attempted. Once the DB catches up, the existing backfill tooling can close the day.

## Goal

Move the `2026-07-06` SimNow observation from `pending/historical_db_lag` to `valid/matched`, and make the 20-day observation ledger show at least one valid day.

Quantified target:

- `simnow_run_summary_2026-07-06.json`:
  - `automation_status = valid`
  - `record.valid_observation = true`
  - `record.consistency_matched = true`
- `simnow_ledger_summary.json`:
  - `valid_observation_days >= 1`

## Acceptance Criteria

- Historical DB covers `2026-07-06` (`simnow_replay_readiness.py --date 2026-07-06` returns `ready = true`).
- `simnow_run_summary_2026-07-06.json` shows `automation_status = valid`.
- `record.valid_observation = true`.
- `record.consistency_matched = true`.
- `simnow_ledger_summary.json` shows `valid_observation_days >= 1`.
- No workflow orders are sent (`meta.read_only = true`, `orders_sent_by_workflow = 0`, `workflow_order_actions = []`).
- `python tools/sync_check.py` passes.
- `python tools/sync_check.py --root examples/czsc_strategy` passes.
- `pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.

## Result

- 2026-07-06 moved from `pending/historical_db_lag` to `valid/matched`.
- `simnow_run_summary_2026-07-06.json` now reports:
  - `automation_status = valid`
  - `record.valid_observation = true`
  - `record.consistency_matched = true`
- `simnow_ledger_summary.json` now reports `valid_observation_days = 1`.

Root causes fixed:

1. `chan_strategy/data_adapter.py` used a date-only `end_date` filter (`<= '2026-07-06'`),
   which excluded all intraday timestamps on the target day. It now appends
   `23:59:59` for date-only end bounds so the full day is included.
2. `diagnostics/backtest_matrix_report.py::_dominant_symbol` selected the most
   frequent `symbol` value in a table, even when that series stopped before the
   target date (e.g. `AP888` stopped on 2026-02-13 while `ap888` continued to
   2026-07-06). It now prefers the symbol whose latest bar covers `end`,
   falling back to the latest bar if none cover.
3. `diagnostics/simnow_daily_monitor.py::compare_simnow_replay` now treats a
   no-trade day where both the live capture and the replay have no actionable
   events as matched, with reason `no_actionable_events_on_either_side`.

## Notes for the Next Agent

Read `docs/design/a36-simnow-replay-backfill-closure.md` before doing any work.

This was originally expected to be a **data-driven closure** using existing tools:

1. Verify DB coverage:
   ```powershell
   python examples/czsc_strategy/diagnostics/simnow_replay_readiness.py --date 2026-07-06
   ```
2. If ready, execute backfill:
   ```powershell
   python examples/czsc_strategy/diagnostics/simnow_backfill_pending_replays.py `
     --date 2026-07-06 `
     --execute `
     --out-json examples/czsc_strategy/diagnostics/simnow_backfill_plan.json
   ```
3. Verify closure:
   ```powershell
   python examples/czsc_strategy/diagnostics/simnow_run_summary.py --date 2026-07-06
   ```

Guardrails:

- Do not patch or fabricate historical DB data.
- Do not change SimNow order/cancel/trading interfaces.
- Do not tune strategy parameters.
- Do not claim `GOAL PASSED`.
- If `simnow_replay_readiness.py` is not ready, stop and report the actual `latest_db_date`.

## Decision Log

- 2026-07-06 - A36 started after A35 reached `done`.
- 2026-07-06 - Chose to reuse `simnow_backfill_pending_replays.py` and `simnow_replay_readiness.py` instead of building a new replay engine.

## Handoff History

| Date | From -> To | Stage Change | Summary |
|------|------------|--------------|---------|
| 2026-07-06 | codex -> claude-code | done -> design | A36 SimNow replay backfill closure started |
| 2026-07-07 | kimi-code -> codex | dev -> review | A36 implementation complete; awaiting codex review before done |

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-06 | codex → claude-code | done → design | A36 SimNow replay backfill closure started |
| 2026-07-06 | claude-code → kimi-code | design → dev | A36 design complete: SimNow replay backfill closure |
| 2026-07-07 | kimi-code → codex | dev → review | A36 implementation complete; awaiting codex review before done |
| 2026-07-07 | codex → codex | review → done | A36 review passed: SimNow replay backfill closure accepted |
