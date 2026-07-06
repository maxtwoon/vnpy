---
task: A36 SimNow Replay Backfill Closure
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-06
deliverables:
  - HANDOFF.md
  - docs/design/a36-simnow-replay-backfill-closure.md
blockers: []
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
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

## Notes for the Next Agent

Read `docs/design/a36-simnow-replay-backfill-closure.md` before doing any work.

This is primarily a **data-driven closure** using existing tools:

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

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-06 | codex → claude-code | done → design | A36 SimNow replay backfill closure started |
| 2026-07-06 | claude-code → kimi-code | design → dev | A36 design complete: SimNow replay backfill closure |
