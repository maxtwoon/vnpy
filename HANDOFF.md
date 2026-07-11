---
task: A41 SimNow Authenticity Fix
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-12
deliverables:
  - HANDOFF.md
  - docs/design/a41-simnow-authenticity-fix.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

Diagnostics-integrity work, not part of the P1-P8 backtest-return-quality roadmap
(`docs/design/a38-phase-contracts-p2-p8.md`) — a parallel line of work, started after A40 (P3
real position sizing) reached `done`. Promoted 2026-07-11 from a DRAFT design produced during an
independent read-only 3-way audit; re-verified at promotion time that A40's changes (scoped to
`chan_strategy/`) did not touch any of A41's target files.

Three independent defects were found in the SimNow observation pipeline, all downstream of the
same root pattern — a diagnostic silently substitutes a synthetic or placeholder value for a real
measurement without labeling the substitution:

1. `simnow_daily_capture.py:234-259` (`build_risk`) emits an all-zero risk block for every
   genuinely risk-relevant field; `simnow_daily_monitor.py:380` prioritizes this placeholder over
   the replay-computed real risk via Python truthiness (a dict of zeros is still truthy).
2. `simnow_strategy_surface.py:58-76` constructs the "live" comparison surface **from the replay
   itself**, windowed to the capture's timestamps; genuinely-captured CTP callbacks are confined
   to `raw.*` and never promoted to the fields the consistency check actually compares — so that
   check can only prove windowing-logic self-consistency, never real captured-session agreement.
3. `simnow_tick_bars.py:159-202` (`upsert_bars_to_sqlite`) writes SimNow-derived ticks directly
   into `{symbol}_1M_raw` — the exact tables `BacktestEngine` reads for every historical
   backtest — via `INSERT OR REPLACE` with no staging step, no dry-run, no promotion gate.

Single source of truth: `docs/design/a41-simnow-authenticity-fix.md`.

## Goal

Ship three independent fixes to the SimNow diagnostics layer only (no order/cancel/send path
changes, no `chan_strategy/` runtime changes): (1) a labeled risk-source selection
(`select_risk_metrics`) that never lets a known-placeholder `simnow.risk` block silently satisfy
a warning/halt threshold (new `"unproven"` status when only the placeholder is available); (2) a
`build_strategy_surface_from_captured_session` path using the session's own captured
trades/positions, with the consistency check reporting `"unavailable"` (never a pass) when only
replay-derived data exists; (3) staged K-line writes (`{symbol}_1M_raw_staging` by default,
promotion via an explicit `dry_run=False` call only). All three new defaults **change today's
unsafe behavior** — a deliberate deviation from the usual default-off house style, justified in
design §2's "Default-justification note" because today's behavior is a silent bug in a safety
gate, not a conservative baseline.

## Acceptance Criteria

- [ ] `SIMNOW_MONITOR_CONFIG` exists with `risk_priority` (`"replay_first"` default |
      `"legacy_simnow_first"`), `consistency_source_mode` (`"require_captured"` default |
      `"replay_derived_allowed"`), `kline_write_mode` (`"staging"` default | `"direct"`, gated by
      an additional `--allow-direct-write` CLI flag).
- [ ] `select_risk_metrics` returns `(dict, risk_source_label)`; a fixture where `simnow.risk` is
      the known all-zero placeholder shape and `replay.risk` has nonzero fields returns
      `replay.risk`/`"replay_computed"` under the default mode; the same fixture under
      `"legacy_simnow_first"` reproduces today's exact old behavior (returns the placeholder) for
      A/B diffing.
- [ ] `evaluate_thresholds`/`make_record` never report `record["status"] == "pass"` when
      `risk_source == "simnow_capture_placeholder"` was the only available source (unit test with
      a fixture that would have passed under old behavior and must not pass under new).
- [ ] `build_strategy_surface_from_captured_session` exists and is exercised by a fixture using
      `capture["captured"]["trades"/"positions"]` (not replay-derived) as the comparison basis;
      `compare_simnow_replay` under `consistency_source_mode="require_captured"` returns
      `status="unavailable"` (never `matched=True`/`False` treated as a pass) for a fixture whose
      surface `meta.source != "captured_session"`.
- [ ] `record["status"]` is never `"pass"` when `consistency["status"] == "unavailable"` (unit
      test).
- [ ] `simnow_tick_bars.py` under default `kline_write_mode="staging"` writes only to
      `{symbol}_1M_raw_staging`, never touches `{symbol}_1M_raw`; a test asserts `{symbol}_1M_raw`
      row count is unchanged after an `upsert_bars_to_sqlite` call under the default mode.
- [ ] `promote_staged_bars(dry_run=True)` (default) writes nothing and returns a diff summary;
      `promote_staged_bars(dry_run=False)` (requires explicit `--promote --no-dry-run`) performs
      the `INSERT OR REPLACE` and only after that call does `{symbol}_1M_raw` change.
- [ ] Before/after diff proving the new defaults change unsafe old output: a fixture-based test
      (or a recorded before/after report pair, git-tracked) demonstrates at least one concrete
      case per finding where `"legacy_*"`/`"direct"` mode would have produced a `"pass"`/silent-
      write outcome that the new default mode correctly downgrades to
      `"unproven"`/`"unavailable"`/staged-not-promoted.
- [ ] Every new/modified report emitted by `simnow_daily_monitor.py` carries the
      `Diagnostic only, not a trading recommendation.` (RESEARCH-ONLY) banner.
- [ ] No SimNow order/cancel/send path changed (grep diff — none added); no threshold value
      tuned via backtest/capture-data selection; no pre-2026-04-24 data used for any parameter
      choice.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass (or the Manual-verification accommodation in `.synccheck.yml`/HANDOFF.md applies if
      the codex-sandbox symlink limitation is still unresolved at review time).

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a41-simnow-authenticity-fix.md`. Full dev prompt in design §8.
2. **This is diagnostics-layer-only work** — `examples/czsc_strategy/diagnostics/
   simnow_daily_capture.py`, `simnow_daily_monitor.py`, `simnow_strategy_surface.py`,
   `simnow_tick_bars.py`, plus a new `simnow_monitor_config.py`. Do not touch `chan_strategy/`
   runtime (positions.py/backtest_engine.py/config.py) or SimNow order/cancel/send paths — none
   of the three findings are there.
3. **Why the defaults change unsafe behavior (design §2):** unlike every prior phase's
   default-off discipline, all three new switches default to the *safe* mode, not the
   *current* mode, because current behavior is a silent correctness bug in a safety gate (a risk
   check that can never fire from real risk; a consistency check that structurally cannot prove
   what it claims; a raw write path with no undo). The `"legacy_*"`/`"direct"` opt-outs exist
   purely for A/B diffing — do not make them the default.
4. **Core discipline: never silently default to "pass".** A diagnostic that cannot verify
   something must report `"unavailable"`/`"unproven"`/`"pending"`. This is the single
   load-bearing behavior change — `make_record`'s `record["status"]` computation must be updated
   so both new non-authoritative states (placeholder-risk-only, replay-derived-only-consistency)
   force it away from `"pass"`.
5. **Staging is the highest blast-radius fix** — `kline_write_mode="direct"` requires an
   *additional* explicit `--allow-direct-write` CLI flag on top of the config override
   (belt-and-suspenders), since a bad write here corrupts the exact tables every historical
   backtest reads.
6. **Guardrails (reject-on-violation):** no tuning any threshold via captured/backtest data; no
   pre-2026-04-24 data for any selection; no SimNow order/cancel/send paths; RESEARCH-ONLY
   banner on every report; no `GOAL PASSED`.
7. **Known environment accommodation:** if pytest/preflight hit the documented codex-sandbox
   Windows-symlink limitation during review, that's covered by the standing Manual-verification
   accommodation in `.synccheck.yml` — not something dev needs to fix. Add a fresh
   Manual-verification block to this task's `HANDOFF.md` if/when it's needed (each task carries
   its own; it doesn't persist automatically — see A40's history).
8. Finish with the four acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A41 SimNow authenticity fix implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-11 - A41 promoted from DRAFT to an active HANDOFF task after A40 reached `done`,
  matching the user's chosen sequencing ("先完成 A40 再依次 A41→A42"). Re-verified all four
  cited file:line targets are unchanged since the draft was written — A40's changes were scoped
  entirely to `chan_strategy/`, no drift in `diagnostics/simnow_*.py`.
- 2026-07-11 (design, original) - Chose safe-by-default (not current-behavior-by-default)
  switches for all three fixes, a deliberate deviation from the A37-A40 house style, because
  today's behavior in each case is a silent bug in a safety gate rather than a conservative
  baseline worth preserving as the default.
- 2026-07-11 (design, original) - Scoped strictly to the diagnostics layer; does not attempt to
  fix `build_risk()`'s zero placeholders at the source (would need portfolio-level context the
  live capture doesn't have) — only ensures downstream code never mistakes the placeholder for a
  real measurement.
- 2026-07-12 (dev complete, pre-commit check) - Found `examples/czsc_strategy/diagnostics/
  simnow_strategy_surface.py` was **never git-tracked at all** (`git ls-files` returns empty),
  despite being an actively-imported module (`simnow_daily_monitor.py` depends on it) predating
  this task — a genuine pre-existing reproducibility gap, not something A41 introduced (every
  other `simnow_*.py` module IS tracked; verified this is isolated to this one file plus the new
  `simnow_monitor_config.py`, not a systemic "whole diagnostics dir untracked" problem). Force-
  added both at commit time so A41's `build_strategy_surface_from_captured_session` addition is
  actually reviewable/reproducible from a clean checkout — this is exactly the class of gap A42
  targets at the harness-tooling level; worth flagging there too if any other diagnostics *code*
  modules (not just generated reports) turn out to share this problem.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-11 | codex → claude-code | done → design | A41 promoted from draft to active task after A40 reached done |
| 2026-07-11 | claude-code → kimi-code | design → dev | A41 promoted from draft to active task; re-verified no drift from A40 |
| 2026-07-12 | kimi-code → codex | dev → review | A41 SimNow authenticity fix implemented |
