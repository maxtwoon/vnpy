---
task: A46 P7 - Symmetric Regime-Gated Shorts
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-12
deliverables:
  - HANDOFF.md
  - docs/design/a38-phase-contracts-p2-p8.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

Continues the P1-P8 roadmap after A45 (P6 second-buy hard-gate + ATR chop filter) reached `done`.
P1-P6 are all `done`. P7 begins the two-sided/portfolio layer (P7 -> P8).

**Task-ID renumbering (unchanged from A43/A44/A45's note):** the phase-contracts doc's original
`Task mapping` (`P7=A44`) is stale — A44 is actually P5 under the 2026-07-12 renumbering.
Confirmed mapping: **P4=A43 (done), P5=A44 (done), P6=A45 (done), P7=A46 (this task), P8a=A47,
P8b=A48.** Each phase is its own handoff task; P8a (A47) is not promoted until this task reaches
`done`.

Futures are two-sided; the strategy is currently long-only in practice even though short
sub-strategies already exist (`create_first_sell_position`/`create_second_sell_position`/
`create_third_sell_position`) — they ship disabled behind `enable_short=False` (confirmed
2026-07-12, `chan_strategy/config.py:23`, unchanged default). The trading-expert review found
long-only exposure bleeds through structural downtrends (RB, SC). This phase enables shorts with
the same P4 (A43 MACD divergence)/P5 (A44 resonance) rigor already applied to longs, and adds an
optional regime router so the strategy trades the dominant side instead of running long+short
simultaneously. Confirmed 2026-07-12: no `regime_model` config or router code exists yet — no
drift since the draft was written. `report["both_long_short_bars"]`
(`chan_strategy/backtest_engine.py:572`, counting bars where `long_exposure > 0 and
short_exposure > 0`) already exists and is exactly the invariant this phase's `"router"` mode must
drive to zero.

Full contract: `docs/design/a38-phase-contracts-p2-p8.md` §"P7 (A44) - Symmetric Regime-Gated
Shorts" (the section header still says A44 — that is the stale label; this task's real ID is
A46, content is otherwise authoritative and unchanged).

## Goal

Add `regime_model` config gate (`"independent"` default, current behavior | `"router"`).
`enable_short` (the master switch) stays `False` by default, unchanged.

- `"independent"`: today's behavior — long and short sub-strategies are each gated by their own
  daily/resonance filter independently; both can in principle be active simultaneously.
- `"router"`: a single regime decision per symbol from the higher level (daily trend + position)
  selects the allowed side for NEW opens: daily-up -> long-only, daily-down -> short-only,
  ambiguous (中枢内/无中枢 or conflicting) -> no new opens on either side. Counter-trend opens on
  the wrong side are suppressed; existing positions still exit normally regardless of regime.
  Under `"router"`, `both_long_short_bars` must be provably `0` across a replay.

Short opens (both modes, when `enable_short=True`) additionally require the P4 MACD 顶背驰
divergence signal and P5 short-side resonance (向下 + {中枢下方, 中枢内}), symmetric to how longs
already use these two phases' outputs.

Add a read-only `short_enable_report.py` (with `enable_short=True`, per-symbol short-side
expectancy and combined long+short vs long-only performance, on the honest post-P1 baseline,
focused on RB/SC per the design; report only, not for in-task selection).

## Acceptance Criteria

- [ ] `enable_short=False` (unchanged default) -> equity curve and every `Position.pairs` entry
      byte-identical to current (full-`BacktestEngine` equivalence test with a git-tracked golden
      snapshot, per the A44/A45 house pattern established after A44's review required it — do not
      ship with only a signal-filter unit check).
- [ ] `enable_short=True, regime_model="independent"` (unchanged behavior) matches the existing
      pre-A46 `enable_short=True` output (equivalence test against a pre-A46 short-replay
      baseline — this is the second required equivalence proof, since `"independent"` mode itself
      must not silently change once shorts are gated by P4/P5).
- [ ] `regime_model="router"` -> `both_long_short_bars == 0` across a replay (asserted directly
      via `report["both_long_short_bars"]`); short opens require daily 向下 (unit-tested); long
      opens are suppressed while daily is down (unit-tested); ambiguous regime blocks new opens
      on both sides (unit-tested); existing positions still exit normally regardless of regime.
- [ ] Short opens require the P4 MACD 顶背驰 signal AND P5 short-side resonance (向下 +
      {中枢下方, 中枢内}), symmetric to the long-side gating already shipped in A43/A44
      (unit-tested for each missing condition).
- [ ] `short_enable_report.py` generated (report only, RESEARCH-ONLY banner
      `Diagnostic only, not a trading recommendation.`), covering RB/SC; not used to select/tune
      parameters in-task. Must be regenerated with the script's own real default symbols — verify
      the output before committing, do not ship a placeholder/empty report (A45's first dev round
      shipped one against a fake "TEST" symbol and had to be corrected).
- [ ] No threshold tuning via backtest/capture-data selection; no pre-2026-04-24 data used for
      any parameter choice; no SimNow order/cancel/send path changed; no `GOAL PASSED`; this
      phase does not change position sizing (P3/A40's scope) or exits (P8's scope).
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes — this script
      genuinely exists at `diagnostics/run_next_work.ps1`; verify the path carefully before
      claiming otherwise (A44's dev round falsely claimed it was absent).

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a38-phase-contracts-p2-p8.md`, section "P7 (A44) - Symmetric
   Regime-Gated Shorts" — ignore the stale `(A44)` label in the header, this task's real ID is
   **A46**. Full dev prompt and review checklist are in that section (verbatim, still accurate).
2. **Scope:** `chan_strategy/positions.py` (regime router logic in `ChanTimingStrategy.update`,
   likely near the existing `self.enable_short` dispatch around line 1552/1683; short-open gating
   by P4/P5 signals in `create_first_sell_position`/`create_second_sell_position`/
   `create_third_sell_position`), `chan_strategy/config.py` (new `regime_model` key). Do not
   touch position sizing (`_size_open`, P3/A40, done) or exit logic (P8's scope, not started) —
   this phase only changes which side is allowed to open and adds P4/P5 gating symmetry to shorts.
3. **Two required equivalence proofs, both full-`BacktestEngine` golden-snapshot tests from the
   start** (learn from A44's review reject — do not ship with only unit-level signal checks):
   - `enable_short=False` (the master default) byte-identical to current.
   - `enable_short=True, regime_model="independent"` matching a pre-A46 short-enabled baseline —
     this confirms that simply adding the P4/P5 gating to shorts under `"independent"` mode
     doesn't silently change `"independent"` mode's own behavior in some other way beyond the
     intended new gating.
4. **`"router"`'s core invariant is `both_long_short_bars == 0`** — this metric already exists
   (`backtest_engine.py:572`); do not reimplement it, just assert it directly in a replay-level
   test.
5. **Symmetric short gating reuses P4/P5, does not reimplement them:** read how longs already
   consume the MACD divergence signal (`signal_first_buy` in `signals.py`, A43/done) and the
   resonance signal (`_higher_level_filter_signals`/`_resonance_filter_signals` in `positions.py`,
   A44/A45, done) — the short-side equivalents (`signal_first_sell`'s MACD path already exists
   from A43; P5's `_higher_level_filter_signals(direction="short", ...)` already exists from A44)
   should already provide what's needed; wire them in, don't duplicate the logic.
6. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched
   (this is backtest-only — no live short order routing); RESEARCH-ONLY banner on the new report;
   no `GOAL PASSED`; does not change position sizing or exits.
7. **Verify diagnostic reports against real default symbols before committing** — A45's first dev
   round shipped `second_buy_and_atr_report` against a placeholder "TEST" symbol that failed to
   load, producing an empty report; this had to be corrected before review. Run
   `short_enable_report.py` with no `--symbols` override and confirm the output actually contains
   real per-symbol data (RB/SC focus) before finishing.
8. **Before claiming any script "doesn't exist," verify the path carefully** — this is now the
   third time this note appears; `run_next_work.ps1` lives at
   `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
9. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A46 (P7) symmetric regime-gated shorts implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-12 - P7 promoted from the pre-authored phase-contracts draft to an active HANDOFF task
  as **A46** (not A44 — A44 is P5 under the established renumbering), continuing sequential
  single-phase-at-a-time promotion. P8a (A47) waits until this task reaches `done`.
- 2026-07-12 - Re-verified `enable_short` (config.py:23, default `False`, unchanged) and
  `both_long_short_bars` (backtest_engine.py:572, already exists) — no drift from A43/A44/A45,
  and confirmed no `regime_model` config or router code exists yet.
- 2026-07-12 - Added an explicit acceptance criterion requiring TWO full-`BacktestEngine`
  golden-snapshot equivalence proofs from the start (the `enable_short=False` default, and
  `enable_short=True, regime_model="independent"` against a pre-A46 short baseline), directly
  incorporating the lesson from A44's review reject.
- 2026-07-12 - Added an explicit note requiring the new diagnostic report be verified against
  real default symbols before committing, directly incorporating the lesson from A45's first dev
  round (which shipped an empty report against a placeholder "TEST" symbol).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-12 | codex → claude-code | done → design | P7 promoted from phase-contracts draft, confirmed A46 under the established renumbering |
| 2026-07-12 | claude-code → kimi-code | design → dev | A46 (P7 symmetric regime-gated shorts) started; re-verified no drift from A43/A44/A45 |
