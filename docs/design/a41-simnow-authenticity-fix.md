# A41 Design: SimNow Authenticity Fix

> **Status: DRAFT — not yet started as a HANDOFF task.** Produced 2026-07-11 by a read-only
> planning pass over an independent 3-way audit, at the same time as the A40 acceptance-criteria
> addendum (see `docs/design/a40-real-position-sizing.md` §7a) and A42
> (`docs/design/a42-sync-guardian-hardening.md`). Sequencing relative to A40/A42 is a pending
> user decision — do not `handoff.py new`/promote this to an active task without that decision.
> All file:line citations below were re-verified against the working tree at the time this draft
> was written; re-verify again before starting dev, since A40 may still be landing changes to
> nearby files.

**Task:** Diagnostics-integrity work, addressing three independently-verified authenticity bugs
in the SimNow observation pipeline that could make the 20-day SimNow observation gate pass when
it should not. Not part of the P1-P8 backtest-return-quality roadmap
(`docs/design/a38-phase-contracts-p2-p8.md`) — a parallel, orthogonal line of work.

**Scope:** `examples/czsc_strategy/diagnostics/` only — `simnow_daily_capture.py`,
`simnow_daily_monitor.py`, `simnow_strategy_surface.py`, `simnow_tick_bars.py`, and their tests.
No changes to SimNow order/cancel/send paths (those live in the connection/gateway layer, not
touched by any of the three findings), no changes to `chan_strategy/` runtime, no changes to
A38/A39/A40.

---

## 1. Background

Three independent defects were found in the SimNow observation pipeline during a read-only audit
(2026-07-11), all downstream of the same root pattern — **a diagnostic silently substitutes a
synthetic or placeholder value for a real measurement without labeling the substitution**:

1. `simnow_daily_capture.py:234-259` (`build_risk`) emits an all-zero risk block for every
   genuinely risk-relevant field; `simnow_daily_monitor.py:380` prioritizes this placeholder over
   the replay-computed real risk (`export_simnow_replay_snapshot.py:185-240`) via Python
   truthiness (`risk or simnow.get("risk") or replay.get("risk") or {}`), because a dict of zeros
   is still truthy.
2. `simnow_strategy_surface.py:58-76` constructs the "live" comparison surface **from the replay
   itself**, windowed to the capture's timestamps; the genuinely-captured CTP callbacks are
   confined to `raw.*` in `simnow_daily_capture.py:288-308` and never promoted to the fields
   `simnow_daily_monitor.py:209` (`compare_simnow_replay`) actually compares — so the
   "consistency" check can only prove the windowing logic is internally consistent, never that a
   captured session agrees with the backtest.
3. `simnow_tick_bars.py:159-202` (`upsert_bars_to_sqlite`) writes SimNow-derived ticks directly
   into `{symbol}_1M_raw` — the exact tables `BacktestEngine` reads for every historical backtest
   (`backtest_engine.py:95,145`) — via `INSERT OR REPLACE` with no staging step, no dry-run, no
   promotion gate.

## 2. Config

Add to a new `SIMNOW_MONITOR_CONFIG` dict (new file
`examples/czsc_strategy/diagnostics/simnow_monitor_config.py`, imported by
`simnow_daily_monitor.py`/`simnow_tick_bars.py`):

```python
SIMNOW_MONITOR_CONFIG = {
    # Finding #2 fix. When True (default), a risk block sourced from
    # simnow_daily_capture.py's known-placeholder build_risk() output is never
    # silently treated as authoritative for threshold evaluation; it is
    # reported separately and labeled. Default is True (safety-first) even
    # though this changes today's behavior -- see the "default justification"
    # note below.
    "risk_priority": "replay_first",   # "replay_first" (new default) | "legacy_simnow_first" (old behavior, for A/B diff only)

    # Finding #3 fix. Governs whether compare_simnow_replay treats a
    # replay-derived comparison surface as a pass/fail verdict, or as
    # "not_proven".
    "consistency_source_mode": "require_captured",  # "require_captured" (new default) | "replay_derived_allowed" (old behavior)

    # Finding #4 fix. Governs whether simnow_tick_bars.py writes straight to
    # {symbol}_1M_raw or to a staging table requiring an explicit promote step.
    "kline_write_mode": "staging",     # "staging" (new default) | "direct" (old behavior, requires --allow-direct-write flag)
}
```

### Default-justification note (why these three defaults change today's behavior, contrary to the usual default-off house style)

The house style (A38/A39/A40) defaults every new switch to reproduce **current** behavior
byte-for-byte, because "current behavior" for a backtest engine is a known, understood quantity
that downstream consumers already rely on. That reasoning does not apply here, because in all
three cases **today's behavior is not "safe but conservative" — it is a *silent correctness bug
in a safety gate*** whose entire job is to stop the 20-day SimNow observation from green-lighting
something it shouldn't:

- Finding #2's "current behavior" is a live risk check that can never fire a `warning`/`halt`
  from real risk, because the value it prioritizes is architecturally always zero for the fields
  that matter. Defaulting to preserve that would mean A41 ships specifically to *not* fix the bug
  it exists to fix.
- Finding #3's "current behavior" produces a `matched: true/false` verdict that looks like a real
  cross-source consistency proof but structurally cannot be one. Defaulting to preserve that
  would keep a false-confidence signal live by default.
- Finding #4's "current behavior" writes to the primary backtest-source-of-truth tables with no
  undo path; defaulting to "direct" would mean A41 ships a staging mechanism nobody uses by
  default, leaving the corruption risk exactly where it was.

In all three cases, `"legacy_*"`/`"direct"` is retained as an explicit non-default opt-out (for a
reviewer who wants to literally diff old-vs-new report shape, or for a future task that decides
staging is unnecessary overhead) — but the safe behavior ships as the default, and the acceptance
criteria require an explicit before/after diff proving the new default actually changes output
where the old defaults were unsafe (see acceptance criteria).

## 3. Semantics

### 3a. Risk-source priority fix (Finding #2)

In `simnow_daily_monitor.py`, replace the single-line priority chain at line 380 with an
explicit, labeled selection:

```python
def select_risk_metrics(
    risk: dict | None,
    simnow: dict,
    replay: dict,
    mode: str = "replay_first",
) -> tuple[dict, str]:
    """Return (raw_risk_dict, risk_source_label). Never silently prefers a
    known-placeholder simnow.risk block over a real replay-computed one."""
    if risk is not None:
        return risk, "explicit_risk_json"
    simnow_risk = simnow.get("risk") or {}
    replay_risk = replay.get("risk") or {}
    simnow_is_placeholder = _is_zero_placeholder_risk(simnow_risk)  # checks the
        # specific fields build_risk() hardcodes to 0.0/0 -- daily_return_pct,
        # drawdown_pct, gross_exposure, net_exposure, both_long_short_symbols,
        # consecutive_loss.*, *_concentration.top1_abs_share -- all == 0
    if mode == "legacy_simnow_first":
        return (simnow_risk or replay_risk or {}), (
            "simnow_capture_placeholder" if simnow_is_placeholder and simnow_risk
            else ("simnow_capture" if simnow_risk else "replay_computed")
        )
    # mode == "replay_first" (new default): prefer replay-computed risk
    # whenever it's available and simnow's own risk block is the known
    # placeholder shape; a genuinely non-placeholder simnow.risk (future
    # capture format upgrade) still wins over replay, since a real live
    # measurement is more authoritative than a replay approximation.
    if simnow_risk and not simnow_is_placeholder:
        return simnow_risk, "simnow_capture"
    if replay_risk:
        return replay_risk, "replay_computed"
    if simnow_risk:
        return simnow_risk, "simnow_capture_placeholder"
    return {}, "no_risk_available"
```

`make_record` threads `risk_source` into the output record
(`record["risk_source"] = risk_source_label`), and `evaluate_thresholds`'s result additionally
carries `"risk_source"` so any consumer of `threshold_result["status"]` can see whether the
"pass" came from a placeholder. **A `risk_source == "simnow_capture_placeholder"` must never be
allowed to produce `threshold_result["status"] == "pass"` on its own** — `evaluate_thresholds`
gains a guard: if `risk_source == "simnow_capture_placeholder"` and no
`replay_computed`/`explicit_risk_json` alternative was available, `threshold_result["status"]`
is forced to `"unproven"` (a new status value, distinct from `pass`/`warning`/`halt`), and
`make_record`'s overall `record["status"]` must not be `"pass"` when
`threshold_result["status"] == "unproven"` (falls through to `"pending"`).

### 3b. Surface-independence fix (Finding #3)

`simnow_daily_capture.py`'s `build_export` (or its caller) must promote the genuinely-captured
`state.trades`/`state.positions`/`state.orders` (currently confined to `raw.*`) into a new
top-level field, `captured` (distinct from the existing `signals`/`trades`/`positions` fields,
which remain reserved for the replay-derived enrichment path per the existing comment at
`simnow_daily_capture.py:289-296`):

```python
"captured": {
    "trades": trades,      # from state.trades, real CTP callbacks
    "positions": list(state.positions.values()),
    "orders": orders,
},
```

`simnow_strategy_surface.py` gains a second comparison mode alongside
`build_strategy_surface_from_capture` (unchanged, kept for the windowed-replay-surface use case
which remains legitimately useful as a "what would replay have produced in this exact wall-clock
window" reference):

```python
def build_strategy_surface_from_captured_session(capture: dict) -> dict:
    """Build a comparison surface from the SESSION'S OWN captured trades/
    positions (capture["captured"]), not from replay. Returns a surface with
    meta.source == "captured_session" so callers can distinguish it from the
    replay-derived surface."""
```

`simnow_daily_monitor.py`'s `compare_simnow_replay` gains a `source` argument threaded from the
capture's `meta.strategy_surface.source` (`"windowed_strategy_replay"` — legacy, replay-derived
— vs `"captured_session"` — real). Under `consistency_source_mode="require_captured"` (new
default): if `source != "captured_session"` (i.e. no real captured trades/positions were
available for that day — e.g. `state.trades` was empty because the strategy didn't trade that
session), `consistency["matched"]` is **not** set to `True` or `False` — the record instead
reports `consistency["status"] = "unavailable"`,
`consistency["reason"] = "no_captured_session_data_only_replay_derived"`, and this must not be
interpreted by `make_record` as `"pass"` (falls through the same way as the placeholder-risk
case — `record["status"]` becomes `"pending"`, never `"pass"`, when consistency is
`"unavailable"`). Under `consistency_source_mode="replay_derived_allowed"` (legacy opt-out),
today's behavior is preserved byte-for-byte for A/B diffing.

### 3c. Staging-DB fix for K-line writes (Finding #4)

`simnow_tick_bars.py` gains a staging table per symbol, `{symbol}_1M_raw_staging` (created via
`_ensure_bar_table` with the same schema, just a different table-name suffix), and
`upsert_bars_to_sqlite` under `kline_write_mode="staging"` (new default) writes there instead of
`{symbol}_1M_raw`. A new, separate, explicit function
`promote_staged_bars(db_path, symbol, date_range, *, dry_run=True)` performs the actual
`INSERT OR REPLACE INTO {symbol}_1M_raw SELECT * FROM {symbol}_1M_raw_staging WHERE ...` —
**defaults to `dry_run=True`**, printing a diff summary (row counts, date range, any rows that
would overwrite existing `{symbol}_1M_raw` rows with materially different OHLCV values beyond a
float-tolerance threshold) without writing; promotion only happens with an explicit
`--promote --no-dry-run` CLI invocation. `kline_write_mode="direct"` (legacy opt-out) requires
passing `--allow-direct-write` on the CLI (belt-and-suspenders: config default is `"staging"`,
and even overriding it to `"direct"` requires an additional explicit flag, since this is the
highest blast-radius of the three findings).

## 4. No-lookahead / no-silent-pass discipline

- None of the three fixes touch backtest replay's own bar ordering, signal generation, or
  execution timing — all changes are confined to how the diagnostics *layer*
  labels/sources/gates already-computed values. No new lookahead surface is introduced.
- **Core discipline, mirroring house style's "no GOAL PASSED" rule**: a diagnostic that cannot
  verify something must report `"unavailable"`/`"unproven"`/`"pending"`, never silently default
  to `"pass"`. This applies to: risk-source selection (3a — `"unproven"` status),
  consistency-check source (3b — `"unavailable"` status), and by extension any future SimNow
  diagnostic — this principle should be called out in the diagnostics module's docstring/README
  so it's discoverable, not just encoded in this one task's logic.
- `make_record`'s existing `record["status"]` computation (`simnow_daily_monitor.py:441-446`)
  must be updated so that **both** new non-authoritative states (placeholder-risk-only,
  replay-derived-only-consistency) force `record["status"]` away from `"pass"` — this is the
  single load-bearing behavior change that actually closes Finding #2/#3's real-world risk (a
  20-day observation window silently accumulating `"pass"` days that were never actually
  proven).

## 5. Expected file changes

- `examples/czsc_strategy/diagnostics/simnow_monitor_config.py` — new, `SIMNOW_MONITOR_CONFIG`
  per §2.
- `examples/czsc_strategy/diagnostics/simnow_daily_capture.py` — `build_export` gains
  `"captured"` top-level field (§3b); `build_risk` unchanged (still produces the same placeholder
  shape — it's a capture-time limitation, not something A41 can fix at capture time since real
  risk requires portfolio-level replay context the live capture doesn't have; A41 fixes how
  downstream code *treats* this output, not the capture code itself).
- `examples/czsc_strategy/diagnostics/simnow_daily_monitor.py` — `select_risk_metrics` (§3a,
  replaces line-380 one-liner), `evaluate_thresholds` gains `"unproven"` status handling,
  `compare_simnow_replay`/`make_record` gain `consistency_source_mode` handling (§3b) and the
  "never silently pass on placeholder/unproven" guard (§4).
- `examples/czsc_strategy/diagnostics/simnow_strategy_surface.py` — new
  `build_strategy_surface_from_captured_session` (§3b); existing
  `build_strategy_surface_from_capture` unchanged/retained.
- `examples/czsc_strategy/diagnostics/simnow_tick_bars.py` — staging table +
  `promote_staged_bars` (§3c); `upsert_bars_to_sqlite` gated on `kline_write_mode`.
- `examples/czsc_strategy/tests/unit/test_simnow_risk_priority.py`,
  `test_simnow_consistency_source.py`, `test_simnow_kline_staging.py` — new, per §7.

## 6. Boundaries (what A41 does NOT do)

- **Does not change SimNow order/cancel/send paths.** No `send_order`/`cancel_order`/
  connection-layer code is touched — all three findings are in the read-only
  diagnostics/reporting layer.
- **Does not backfill or retroactively re-score historical SimNow captures.** Prior
  20-day-observation days that passed under the old silent-placeholder/circular-comparison logic
  are not automatically re-evaluated or invalidated by this task; if a retroactive audit of past
  "pass" days is wanted, that is a separate follow-up task, not in scope here.
- **Does not fix `build_risk()`'s zero placeholders at the source.** Computing genuine
  daily-return/drawdown/exposure/concentration figures from a live capture would require
  portfolio-level context (multi-symbol equity curve, prior-day baseline) that the capture script
  does not currently have access to at capture time; A41 only ensures the *downstream* consumer
  never mistakes the placeholder for a real zero. A future task could add real live-risk
  computation to the capture script itself.
- **Does not implement automatic promotion of staged K-line bars.** `promote_staged_bars`
  defaults to `dry_run=True`; an operator/agent must explicitly review and promote. Building an
  automated promotion policy (e.g. auto-promote if diff is below some tolerance) is out of scope
  — a human-in-the-loop step is the safer default until this mechanism has track record.
- **Does not change the `{symbol}_1M_raw` table schema** — the staging table is a same-schema
  shadow table, not a redesign of the historical DB.
- **Does not touch A38/A39/A40 code** (`positions.py`, `backtest_engine.py`, `config.py`) — those
  are independent tasks tracked separately.
- **Does not add a markup/production risk model** — this task is about not being *fooled* by a
  known-zero placeholder, not about computing a better live risk number.

## 7. Acceptance Criteria (decidable checkboxes)

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
      `risk_source == "simnow_capture_placeholder"` was the only available source (asserted by a
      unit test with a fixture that would have passed under old behavior and must not pass under
      new).
- [ ] `build_strategy_surface_from_captured_session` exists and is exercised by a fixture using
      `capture["captured"]["trades"/"positions"]` (not replay-derived) as the comparison basis;
      `compare_simnow_replay` under `consistency_source_mode="require_captured"` returns
      `status="unavailable"` (never `matched=True`/`False` treated as a pass) for a fixture whose
      surface `meta.source != "captured_session"`.
- [ ] `record["status"]` is never `"pass"` when `consistency["status"] == "unavailable"` (unit
      test).
- [ ] `simnow_tick_bars.py` under default `kline_write_mode="staging"` writes only to
      `{symbol}_1M_raw_staging`, never touches `{symbol}_1M_raw`; a test asserts
      `{symbol}_1M_raw` row count is unchanged after an `upsert_bars_to_sqlite` call under the
      default mode.
- [ ] `promote_staged_bars(dry_run=True)` (default) writes nothing and returns a diff summary;
      `promote_staged_bars(dry_run=False)` (requires explicit `--promote --no-dry-run`) performs
      the `INSERT OR REPLACE` and only after that call does `{symbol}_1M_raw` change.
- [ ] **Before/after diff proving the new defaults change unsafe old output**: a fixture-based
      test (or a recorded before/after report pair, git-tracked) demonstrates at least one
      concrete case per finding where `"legacy_*"`/`"direct"` mode would have produced a
      `"pass"`/silent-write outcome that the new default mode correctly downgrades to
      `"unproven"`/`"unavailable"`/staged-not-promoted.
- [ ] Every new/modified report emitted by `simnow_daily_monitor.py` carries the
      `Diagnostic only, not a trading recommendation.` (RESEARCH-ONLY) banner.
- [ ] No SimNow order/cancel/send path changed (grep diff for
      `send_order`/`cancel_order`/`buy`/`sell`/`short`/`cover` calls — none added); no threshold
      value tuned via backtest/capture-data selection; no pre-2026-04-24 data used for any
      parameter choice.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass (or the Manual-verification accommodation applies per `.synccheck.yml`).

## 8. Dev Handoff Prompt (dev = kimi-code)

```text
Read HANDOFF.md and docs/design/a41-simnow-authenticity-fix.md. Implement A41 exactly as specified
-- three independent fixes to the SimNow diagnostics layer only, no order/cancel/send path changes.

1. Add SIMNOW_MONITOR_CONFIG (simnow_daily_monitor.py's new sibling config module) per design S2:
   risk_priority ("replay_first" default), consistency_source_mode ("require_captured" default),
   kline_write_mode ("staging" default).
2. Risk-source fix (S3a): replace simnow_daily_monitor.py:380's one-line priority chain with
   select_risk_metrics(), returning (dict, source_label). A placeholder-only risk source must force
   threshold status to "unproven", never "pass".
3. Surface-independence fix (S3b): add "captured" top-level field to simnow_daily_capture.py's
   export (real state.trades/positions/orders, NOT the replay-derived enrichment). Add
   build_strategy_surface_from_captured_session to simnow_strategy_surface.py. compare_simnow_replay
   must report "unavailable" (never a pass) when only replay-derived surface data exists under the
   default consistency_source_mode.
4. Staging fix (S3c): simnow_tick_bars.py writes to {symbol}_1M_raw_staging by default; add
   promote_staged_bars(dry_run=True default) as the only path that ever touches {symbol}_1M_raw.
5. Tests per S7, including explicit before/after fixtures proving the new defaults change output
   where old defaults were unsafe (not just "new code runs without crashing").

Do not touch SimNow order/cancel/send paths. Do not tune any threshold via captured/backtest data.
No pre-2026-04-24 data for any selection. No GOAL PASSED.

Run:
- python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
- python tools/sync_check.py ; python tools/sync_check.py --root examples/czsc_strategy
- python tools/handoff.py next --actor kimi-code --summary "A41 SimNow authenticity fix implemented"
```

## 9. Review Checklist (review = codex)

Reject if: `risk_priority`/`consistency_source_mode`/`kline_write_mode` legacy modes don't
byte-for-byte reproduce today's old behavior (needed for the A/B diff acceptance item to be
meaningful); any code path can still reach `record["status"] == "pass"` off a
`simnow_capture_placeholder` risk source or an `"unavailable"` consistency status;
`promote_staged_bars` writes to `{symbol}_1M_raw` under any call that didn't pass explicit
`dry_run=False`; `kline_write_mode="direct"` is reachable without the `--allow-direct-write` CLI
flag; any SimNow order/cancel/send path touched; any threshold tuned via captured/backtest data;
`sync_check` (root or child) fails.

Accept if all §7 boxes are checked and the before/after diff evidence concretely demonstrates the
fix (not just "tests pass").
