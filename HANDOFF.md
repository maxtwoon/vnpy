---
task: A46 P7 - Symmetric Regime-Gated Shorts
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-12
deliverables:
  - HANDOFF.md
  - docs/design/a38-phase-contracts-p2-p8.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
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
- [ ] **Correction (claude-code, 2026-07-12): this item as originally written was
      self-contradictory and unsatisfiable — do not attempt a byte-identical equivalence test
      here, it cannot pass.** The P4/P5 short-open gating below is new behavior that applies
      whenever `enable_short=True`, in BOTH `"independent"` and `"router"` modes (per the design's
      own Semantics section: "Short opens additionally require the P4 MACD顶背驰 and P5
      short-side resonance... symmetric to the long side" — no carve-out for `"independent"`).
      That gating necessarily changes which short opens fire compared to the pre-A46 baseline, so
      `enable_short=True, regime_model="independent"` output CANNOT be byte-identical to pre-A46
      `enable_short=True` output — the two requirements are mutually exclusive. What actually
      needs proving for `"independent"` mode is structural, not byte-identical: long and short
      sub-strategies remain independently gated (unlike `"router"`, which enforces mutual
      exclusion) — i.e. `both_long_short_bars` can be nonzero under `"independent"` but must be
      `0` under `"router"` (unit/replay-tested), and a short open under `"independent"` is
      blocked/allowed by exactly the same P4/P5 conditions as under `"router"` (same gate
      function, just without the regime-direction restriction on top).
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

## Manual Verification

Re-run natively by claude-code 2026-07-12:

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` -> **PASS** (503
  passed, 4 deselected).
- `python tools/sync_check.py` -> PASS (root). `python tools/sync_check.py --root
  examples/czsc_strategy` -> PASS (child).
- `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) -> **PASS**, 155 SimNow
  workflow unit tests passed, preflight completed cleanly, no WinError 5.

### Correction (claude-code, 2026-07-12): report window hardcoded backwards (pre-cutoff data)

`short_enable_report.py` hardcoded `WINDOW_START = "2026-01-01"` / `WINDOW_END = "2026-04-24"` —
the reverse of every other report script in this roadmap (A43/A44/A45's `second_buy_and_atr_
report.py`/`resonance_filter_comparison_report.py`/`divergence_model_comparison_report.py` all
use `WINDOW_START = "2026-04-24"` / `WINDOW_END = "2026-07-09"`, i.e. the honest post-cutoff
window). The generated report used 2026-01-01~2026-04-24 — entirely pre-2026-04-24 data, directly
contradicting the house discipline's "promotion evidence needs the post-2026-04-24 + SimNow
stream" convention every prior phase's report followed. Fixed the two constants in
`short_enable_report.py` to match precedent and regenerated the report with the corrected
default window; it now correctly shows sparse/zero trade counts on the honest post-cutoff window
(RB888 reports `交易周期数据不足`, consistent with every other A43-A45 report on the same window).

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
3. **Only ONE full-`BacktestEngine` golden-snapshot equivalence test is required, not two** —
   correcting an error in this HANDOFF's original draft (see the corrected Acceptance Criteria
   above): `enable_short=False` (the master default, unchanged) must be byte-identical to current.
   Do NOT attempt a byte-identical equivalence test for `enable_short=True, regime_model=
   "independent"` against a pre-A46 baseline — P4/P5 short gating is new behavior that changes
   short-open outcomes under `"independent"` too, so no such equivalence can exist. For
   `"independent"` mode, write structural tests instead: (a) long and short can both be
   simultaneously active (`both_long_short_bars` can be nonzero, unlike `"router"`), (b) a short
   open is gated by the same P4/P5 conditions as under `"router"`, just without the
   regime-direction restriction layered on top.
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
9. **Remove all debug artifacts before finishing:** a prior dev-round attempt left a
   `print(f"[DEBUG SHORT GATE] keys=...")` statement inside `_research_short_open_allowed`
   (`positions.py`, currently uncommitted) and a throwaway `debug_short.py` script at the repo
   root (also uncommitted) — both must be deleted/removed before this round's commit. The
   underlying confusion that produced them was almost certainly the AC #2 contradiction now fixed
   above, not a real bug in the gate logic — re-check `_research_short_open_allowed` once the
   corrected acceptance criteria make the actual required behavior unambiguous.
10. Finish with the acceptance commands, then
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
- 2026-07-12 (correction, after a dev round timed out at 2400s stuck debugging) - The original
  promotion's acceptance criteria required a byte-identical equivalence test for
  `enable_short=True, regime_model="independent"` against a pre-A46 baseline, while also requiring
  P4/P5 gating to apply to short opens under `"independent"` mode too — these two requirements are
  mutually exclusive (new gating necessarily changes short-open outcomes). This self-contradiction
  is almost certainly why dev got stuck in a print-debugging loop and hit the 2400s timeout without
  transitioning. Corrected: only `enable_short=False` needs byte-identical equivalence;
  `"independent"` mode needs structural tests (both sides can be simultaneously active, same P4/P5
  gate as `"router"` minus the direction restriction) instead. Also flagged debug artifacts
  (`debug_short.py`, a stray `print()` in `_research_short_open_allowed`) left uncommitted from the
  timed-out round for removal.
- 2026-07-12 - Added an explicit note requiring the new diagnostic report be verified against
  real default symbols before committing, directly incorporating the lesson from A45's first dev
  round (which shipped an empty report against a placeholder "TEST" symbol).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-12 | codex → claude-code | done → design | P7 promoted from phase-contracts draft, confirmed A46 under the established renumbering |
| 2026-07-12 | claude-code → kimi-code | design → dev | A46 (P7 symmetric regime-gated shorts) started; re-verified no drift from A43/A44/A45 |
| 2026-07-12 | kimi-code → codex | dev → review | A46 (P7) symmetric regime-gated shorts implemented |
