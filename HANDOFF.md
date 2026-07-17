---
task: A88 - Joint-clock replay real-data acceptance / sanity-check
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-17
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/diagnostics/joint_replay_acceptance_check.py
  - examples/czsc_strategy/diagnostics/joint_replay_acceptance_check.json
  - examples/czsc_strategy/diagnostics/joint_replay_acceptance_2026-07-17.md
  - examples/czsc_strategy/VERSION
  - examples/czsc_strategy/CHANGELOG.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

A87 (`done`) implemented `PortfolioEngine._build_joint_report()` — the real joint-clock multi-symbol
replay with a shared `PortfolioLedger`, replacing the `NotImplementedError` for `sizing_model="risk"` +
`portfolio_risk="on"`. Its own unit tests (30 passing, constructed fixtures) proved the mechanism works
correctly on synthetic data. Following the exact same pattern as A83→A84 (Phase 1 read-only ledger →
real-data acceptance check), this task (A88) is the real-data sanity-check step for A87 **before** anyone
treats the joint replay as trustworthy for anything beyond unit-test fixtures.

**This task is primarily verification, not new feature development** — same framing as A84.

## Goal

1. Run `PortfolioEngine` with `sizing_model="risk"` + `portfolio_risk="on"` against the real historical
   SQLite DB (`SQLITE_DB_PATH` from `chan_strategy/config.py`), using the **same 5 symbols and window
   A83/A84 already used and validated**: `AP888`/`RB888`/`SC888`/`A888`/`ZN888`,
   `2022-01-01`~`2026-04-24`. Do not introduce new parameters or a different window — reuse exactly what
   A84 already established as valid. You will need a small runner script (e.g.
   `diagnostics/joint_replay_acceptance_check.py`, mirroring `diagnostics/portfolio_ledger_acceptance_check.py`'s
   structure) since there isn't yet a diagnostics entry point for the joint-replay path specifically —
   creating this script is in scope, it's the natural vehicle for this task's real-data run.
2. Perform these sanity checks against the real joint-replay output:
   - **No crash / no data errors** across all 5 symbols (an empty `symbol_errors` dict, or if any symbol
     legitimately fails to load, confirm it's a pre-existing/known data issue, not new).
   - **Equity/margin arithmetic sanity**: `equity_curve` entries have `equity > 0` throughout and
     `total_open_margin >= 0`; `margin_utilization_pct` values are in a sane range (not wildly
     discontinuous or negative).
   - **`blocked_opens` diagnostic is coherent**: if non-empty, each entry's `reason` is one of
     `"daily_loss_limit"`, `"symbol_margin_cap"`, or a `"cluster_gross_cap:<name>"` string, and the `dt`
     falls within the run window. If empty (margin never got tight enough with these 5 symbols'
     defaults), that's a valid, reportable outcome — do not manufacture artificial gating to force
     non-empty results.
   - **Compare against A83/A84's independent-aggregation ledger** for the same symbols/window: the joint
     replay's *total realized PnL* should be reasonably close to A83/A84's sum (both are summing the same
     underlying per-symbol trades when no gating actually blocks an open) — if `blocked_opens` is empty
     for a symbol's entire run, that symbol's trades should be **identical** to its independent run (same
     signals, same fills, since nothing was ever gated); if `blocked_opens` has entries affecting a
     symbol, expect its trade sequence to diverge from A83/A84's independent version starting at the
     first blocked open — explain the divergence, don't just note a number mismatch as an anomaly.
   - **Case-insensitive cluster membership holds on real symbol names** (reuse the same check style as
     A83/A84: confirm `margin_by_cluster` groups `RB888`/`SC888`/`ZN888` under `industrial_energy` etc.).
3. Write up findings as a fixed acceptance artifact (e.g.
   `diagnostics/joint_replay_acceptance_2026-07-17.md`, `git add -f`'d per house convention since
   `diagnostics/` is gitignored) with real numbers, explicitly stating whether `blocked_opens` was empty
   or not and why that's expected given the 5 symbols' actual real-data margin usage (A84 already
   recorded max margin utilization was only ~6.49% for this symbol set — if that holds, expect
   `blocked_opens` to be empty or rare, since nothing gets close to any cap; **do not treat an empty
   `blocked_opens` list as a test failure or as evidence the mechanism doesn't work** — it's expected
   given these specific symbols' real risk profile, and the unit tests already prove the mechanism
   triggers correctly under margin pressure).
4. **Do not claim this proves "production-ready"** — same honesty requirement A83/A84 carried. State
   explicitly: this confirms the joint replay runs correctly end-to-end on real data and its gating
   mechanism is coherent; it does NOT constitute a trading recommendation, and forced liquidation
   (A89, not yet scoped) is still not implemented.
5. If a genuine, small, localized bug is found, fix it in this task (same latitude A84 had). If something
   architecturally significant surfaces, stop and document it in the Decision Log rather than attempting
   a large fix here.

## Acceptance Criteria

- [ ] Real-data run of the joint replay (`sizing_model="risk"` + `portfolio_risk="on"`) completed for the
      same 5 symbols/window as A83/A84; output committed as a `git add -f`'d evidence artifact.
- [ ] A new acceptance write-up covers all the sanity checks in Goal §2 with actual observed numbers.
- [ ] The write-up explicitly addresses whether `blocked_opens` was empty and why, rather than treating
      either outcome as inherently good or bad.
- [ ] The write-up explicitly states the scope boundary (block-new-opens only, no forced liquidation,
      not a trading recommendation).
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped if any code changed; if this task is pure verification with no code
      changes, VERSION/CHANGELOG bump is not required (record which case applies in the Decision Log).
- [ ] Include a literal `## Manual Verification` heading with natively-run counts.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **This task is primarily verification/analysis, not new feature development.** Read
   `chan_strategy/portfolio_ledger.py` and `PortfolioEngine._build_joint_report()`
   (`chan_strategy/portfolio_engine.py`) and their tests (`tests/unit/test_a87_joint_replay.py`) first to
   understand exactly what you're running before writing the acceptance script.
2. **Use the real SQLite DB** — same path/window A83/A84 already validated. Do not fabricate or simulate
   numbers; run the actual joint replay.
3. **No pre-2026-04-24 data for any NEW parameter choice** — this doesn't apply to reusing A83/A84's
   already-established defaults, but do not introduce any new parameter tuning while doing this
   verification.
4. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to a
   concurrent, unrelated SimNow-observation workstream. **Before committing, run `git status --short`
   and confirm only your own A88-scoped files are staged.**
5. **Guardrails**: no gating/threshold logic added anywhere beyond what A87 already built; no SimNow
   order/cancel/send paths touched; no `GOAL PASSED`; do not claim the joint replay is "production-ready"
   — the honest scope boundary (block-new-opens only, A89 not yet built) must be preserved and
   reinforced, not walked back.
6. **Include a literal `## Manual Verification` heading** — A77's first review round was rejected purely
   for lacking this literal heading; this lesson has repeated across nearly every task since. Do not
   repeat it.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A88 joint replay real-data acceptance completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times
   out for environment reasons (this has happened on this machine on A85, A86, and A87's final steps —
   apparently correlated with the pipeline's 3600s timeout landing right at the finish line), do not
   manually hand-edit HANDOFF.md's stage/owner fields to bypass it — leave the working tree with your
   changes uncommitted and note the failure in the Decision Log; claude-code will verify and commit
   properly, same as the last three tasks.

## Decision Log

- 2026-07-17 - User authorized proceeding with the A86→A87→A88 implementation sequence; A86 and A87 both
  reached `done`, accepted first review round each.
- 2026-07-17 (claude-code, design) - Promoted A88 following the exact A83→A84 pattern: real-data
  acceptance check before treating a newly-implemented replay mechanism as trustworthy beyond its own
  unit-test fixtures. Deliberately did not pre-judge whether `blocked_opens` should be empty or not —
  A84 already established this symbol set's real max margin utilization is low (~6.49%), so an empty
  `blocked_opens` list is an expected, valid outcome here, not a sign the A87 mechanism is untested; the
  unit tests already cover the triggering path under synthetic margin pressure.
- 2026-07-17 (kimi-code, dev) - A88 real-data acceptance completed; **VERSION/CHANGELOG bumped to
  0.2.24** (this task added new code <!-- synccheck:ignore --> — the read-only `diagnostics/joint_replay_acceptance_check.py` —
  so the "pure verification, no bump" case does not apply). No production code touched; no bugs found,
  so no fix latitude was exercised. Key real-data findings (full numbers in
  `diagnostics/joint_replay_acceptance_2026-07-17.md` + `joint_replay_acceptance_check.json`, both
  `git add -f`'d):
  (a) `blocked_opens` was NOT empty — 58 entries, all `daily_loss_limit`, all on 2022-03-30, from a
      single trigger at 09:29 (day PnL -3.0044% vs -3% limit); block persisted through the night
      session under `daily_agg="natural"` and lifted at the 2022-03-31 trading-day rollover, matching
      the A87 unit-test semantics. Zero margin-cap blocks (peak utilization 6.21%, caps never close
      to binding) — exactly the design-stage expectation for this symbol set.
  (b) ZN888's trade sequence diverges from its independent run exactly at its first blocked open
      (index 5: independent 2022-03-30 22:59 @26,875 blocked → joint re-entry 2022-03-31 00:29
      @27,005), the design-predicted divergence pattern; the other 4 symbols stayed timing-identical.
  (c) Per-trade volume differences on timing-identical trades (AP888 10/73, RB888 3/43, A888 12/48,
      ZN888 15/78) are the documented shared-equity sizing behavior (joint sizes opens off shared
      portfolio equity; A83/A84 sized off standalone equity), not gating and not an anomaly.
  (d) Joint total realized PnL -57,473.59 vs A83/A84's -65,463.57 (+7,989.99, 12.2% relative, within
      the 20% tolerance the checker codifies); joint equity curve has exactly 19,470 rows, matching
      A83's ledger row count; final equity 949,526.41 reconciles to the cent
      (1,000,000 - 57,473.59 realized + 7,000.00 unrealized on RB888's still-open position).
  (e) Scope boundary preserved and restated: block-new-opens only, forced liquidation still
      unimplemented (A89), not a trading recommendation, not "production-ready".
  (f) The checker was run twice end-to-end; both executions produced byte-identical check JSON,
      confirming the joint driver is deterministic on real data.

## Manual Verification

(kimi-code, dev, 2026-07-17 — all commands run natively on this machine)

```bash
# 1. Joint replay on real DB + all sanity checks (run twice; byte-identical check JSON)
python examples/czsc_strategy/diagnostics/joint_replay_acceptance_check.py
#    -> overall_accepted: true; 5 symbols, 0 errors; 19,470 curve rows; 242 pairs;
#       blocked_opens: 58 (all daily_loss_limit, all 2022-03-30; 1 trigger -3.0044%);
#       joint total realized PnL -57,473.59 vs A83/A84 independent sum -65,463.57 (rel diff 12.2%)

# 2. Unit tests
python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
#    -> 751 passed, 4 deselected in 33.32s

# 3. Sync gates
python tools/sync_check.py
#    -> PASS (version 4.4.0 consistent)
python tools/sync_check.py --root examples/czsc_strategy
#    -> PASS (VERSION 0.2.24 consistent with CHANGELOG) <!-- synccheck:ignore -->

# 4. Preflight (from examples/czsc_strategy/)
powershell -ExecutionPolicy Bypass -File diagnostics\run_next_work.ps1 -Preflight
#    -> 192 SimNow unit tests passed; "Preflight complete; live SimNow capture was not requested"

# 5. Lint on the new checker
python -m ruff check examples/czsc_strategy/diagnostics/joint_replay_acceptance_check.py
#    -> All checks passed!
```

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-17 | claude-code → kimi-code | design → dev | A88 (joint replay real-data acceptance) promoted; handoff design->dev |
| 2026-07-17 | kimi-code → codex | dev → review | A88 joint replay real-data acceptance completed |
