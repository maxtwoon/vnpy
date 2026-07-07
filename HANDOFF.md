---
task: A37 Exit-Event Boolean Restructure
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-07
deliverables:
  - HANDOFF.md
  - docs/design/a37-exit-event-restructure.md
blockers: []
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

A36 closed the SimNow replay backfill. The 2026-07-07 win-rate audit identified the highest-leverage remaining structural defect (R1/R2): losing trades have no reachable structural exit path.

Evidence (full sample, `diagnostics/pnl_attribution_20220101_20260424.md`, 358 trades):

- `stop_loss`: 155 trades, 0% win rate, cumulative about `-489%` (pnl_pct sum).
- `trailing_stop`: 114 trades, 99.1% win rate, about `+411%`.
- `signal_exit`: only 88 trades, about `+8.4%`.
- `timeout`: 1 trade.

Structural causes, confirmed at source level:

1. All six exit events use AND semantics: `(结构失效 [∨ 震荡超限]) ∧ (directional/position factor)` (`Event.is_match`, `chan_strategy/positions.py:125-141`; exits at `:569-591`, `:668-696`, `:766-792`, `:846-860`, `:928-955`, `:1011-1030`). A standalone `结构失效` never closes a position, contradicting `signals.py:682-683` ("两者并存，先触发者执行").
2. `结构失效` uses the segment-mode center (`signals.py:696`, `sell_signals.py:237`) while the position factors use the recent-mode center (`zhongshu.py`), so the AND combines conditions about two different structures.
3. The 二买平多 / 二卖平空 factors depending on `背驰V260615_失效` (`positions.py:685-694`, `:946-954`) are dead code (H3: classification count = 0 on real data).

## Goal

Implement A37 exactly as specified in `docs/design/a37-exit-event-restructure.md`, in phase order:

- Phase 0: read-only exit-blocked reachability diagnostic (`exit_event_reachability_report.py`), counting `legacy_fired` / `struct_alone` / `factor_alone` per exit event per symbol.
- Phase 1: behavior-neutral removal of the two dead exit factors, with a machine-checkable equivalence proof (empty before/after trade-pair diff, including one `enable_short=True` replay leg).
- Phase 2: `STRATEGY_CONFIG["exit_event_semantics"]` switch (`"legacy"` default, byte-identical baseline; `"restructured"` emits standalone structural-exit events plus standalone directional-exit events, with `结构失效` recomputed from a recent-mode signal `风控RV260615` / `空头风控RV260615`).

## Acceptance Criteria

- `docs/design/a37-exit-event-restructure.md` acceptance gates all pass, per phase and in order.
- Phase 0 reports exist (`exit_event_reachability_report_YYYY-MM-DD.json/.md`) with the standard disclaimer; missing DB coverage marked `unavailable`, never silently passed; `背驰V260615_失效` replay count reported (expected 0).
- Phase 1 equivalence: before/after trade-pair diff empty on >=2 symbols x 1 year (long baseline) AND >=1 symbol x 1 year with `enable_short=True`; test fixtures gain the "confirmed BI directions alternate" invariant.
- Phase 2: switch defaults to `legacy`; with `legacy` the emitted event structures are identical to Phase 1 output (unit-tested); new signal keys registered in `validation.py` exhaustiveness sets; backtest report header prints the active switch value.
- No numeric threshold tuned (`stop_loss_pct=0.05` copied verbatim); no selection justified by pre-2026-04-24 data; no `GOAL PASSED`; no SimNow order/cancel/trading interface changes; `Position` stop/trailing/timeout logic and `BacktestEngine.run` ordering untouched.
- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight` passes.
- `python tools/handoff.py next --summary "A37 exit-event restructure implemented (phases 0-2)"` advances to review.

## Notes for the Next Agent

Read `docs/design/a37-exit-event-restructure.md` before writing code. The full dev prompt is in its §9.

Guardrails (reject-on-violation, see design §8):

- Implement phases strictly in order; Phase 2 must not ship before the Phase 1 equivalence diff is empty.
- Do not tune parameters or thresholds; do not use pre-2026-04-24 data for any selection.
- Do not "fix" the dead `失效` branch in `signal_divergence_status` in this task — consumer-side removal only; the signal-side repair/delete decision is explicitly deferred.
- Do not touch SimNow order/cancel/send-order paths.
- Do not claim `GOAL PASSED`; result reports carry the RESEARCH-ONLY banner.
- The local SQLite DB exists on this machine (verified 2026-07-07), so Phase 0/1 replays are executable locally.

## Decision Log

- 2026-07-07 - A37 started after A36 reached `done`; scope chosen from the win-rate audit's top recommendation (R1/R2 exit-event restructure).
- 2026-07-07 - Chose diagnostic-first phasing (Phase 0 counts blocked exits before any behavior change), mirroring A34/A35 discipline.
- 2026-07-07 - Chose OR semantics for `restructured` mode on traceability grounds (restores documented "先触发者执行" and 三买 "回落入中枢" intent), gated behind a default-off config switch; churn explosion on new data is a defined rejection outcome.
- 2026-07-07 - Design review fixed two gaps before dev handoff: pinned exact short-side exit anchors, and made the `enable_short=True` equivalence replay leg mandatory (baseline `enable_short=False` would otherwise vacuously pass the 二卖 removal).

## Handoff History

| Date | From -> To | Stage Change | Summary |
|------|------------|--------------|---------|
| 2026-07-07 | codex -> claude-code | done -> design | A37 exit-event restructure started |
| 2026-07-07 | claude-code -> kimi-code | design -> dev | A37 design complete: exit-event boolean restructure (3 phases, gated) |

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-07 | codex → claude-code | done → design | A37 出场事件布尔结构重构 启动 |
| 2026-07-07 | claude-code → kimi-code | design → dev | A37 设计完成：三阶段（只读诊断 → 行为中性删除 → 开关门控重构），默认基线不变 |
| 2026-07-07 | kimi-code → codex | dev → review | A37 exit-event restructure implemented (phases 0-2) |
