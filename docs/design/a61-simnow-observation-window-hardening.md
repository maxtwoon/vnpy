# A61 Design: SimNow 20-Day Observation Window Hardening

**Task:** Convert the 2026-07-14 sub-agent audit's 4 open findings (74/100, B, "conditional go") into
a phased, dev-ready remediation sequence, continuing the same design→dev→review→done discipline
used for A38-A60.

**Scope:** Design only. Do not implement any fix in this document. Do not tune parameters, do not
use pre-2026-04-24 data to select any new value, do not touch any SimNow order/cancel/send path —
none of A61-A64 need to (all four are diagnostics/monitoring-script fixes, not trading-logic
changes).

**Status:** DRAFT — not yet started as a HANDOFF task. Produced 2026-07-14 immediately after the
sub-agent's second SimNow-observation audit (74/100, up from a prior lower score; no blocking
finding — "conditional go" to start the new 20-day observation window today). This document assigns
the next task IDs (**A61-A64**) but does not promote any of them; promote and start each phase
individually, in the sequence below, following the established one-task-at-a-time house rule.

---

## 1. Background

The sub-agent's 2026-07-14 review of the SimNow daily-observation workflow
(`examples/czsc_strategy/diagnostics/simnow_daily_capture.py`,
`simnow_strategy_surface.py`, `simnow_daily_monitor.py`, `simnow_run_summary.py`,
`simnow_daily_brief.py`, `simnow_observation_window.py/json`) confirmed:

- The new 2026-04-14 observation window is in effect; the old ledger is retained but correctly
  excluded (`excluded_before_start_count=12`, `valid_observation_days=0/20`).
- `simnow_observation_window.py`/`.json` are now git-tracked (yesterday's blocker, closed).
- Both `sync_check.py` gates PASS.
- No live order/cancel automation risk found.
- SimNow account PnL does not leak into strategy PnL; strategy PnL still comes from delayed replay.

Four open findings remain, none individually blocking, but the first two directly affect whether a
day can be trusted as a "valid observation day":

1. **External SimNow positions can still enter the consistency comparison.** Confirmed via direct
   code read: `simnow_daily_capture.py`'s capture payload already separates `raw.*` (full CTP
   account callbacks, unfiltered — comment at `simnow_daily_capture.py:293-296` explicitly says
   `raw.positions` "must not be compared directly with replay portfolio exposures") from
   `captured.*` (intended to be "the only trades/positions/orders that may be used to prove
   live-session agreement with replay," per the comment at `simnow_daily_capture.py:299-301`) — but
   `captured.positions`/`captured.trades` themselves (`simnow_daily_capture.py:302-306`) are simply
   `list(state.positions.values())` / the raw trade list, **not filtered to workflow-owned
   symbols**. `simnow_strategy_surface.py`'s `build_strategy_surface_from_captured_session`
   (`simnow_strategy_surface.py:85-107`) converts `captured.trades`/`captured.positions` into the
   comparison surface unchanged — any position or trade on a symbol the workflow doesn't itself
   trade (i.e. genuine external account activity in the same SimNow account) flows straight into
   `compare_simnow_replay`'s `positions`/`trades` categories (`simnow_daily_monitor.py:337-354`) and
   can produce a false `extra_in_simnow` mismatch, incorrectly failing consistency for a day the
   strategy itself behaved correctly. `extract_account_contamination`
   (`simnow_run_summary.py:107-129`) already exists and correctly reports external activity as
   "external audit evidence only, not strategy PnL" — but it reads from `raw.*` independently; it is
   not wired as the destination for symbols filtered *out* of the captured-session surface.
2. **`valid_observation` still depends on the raw `consistency.matched` boolean with no
   schema/source floor beyond today's default.** `simnow_daily_monitor.py`'s `compare_simnow_replay`
   already has a `consistency_source_mode` parameter defaulting to `"require_captured"`
   (`simnow_daily_monitor.py:290-308`), which is a reasonable existing safeguard — but the *ledger
   record* itself (`make_record`, `simnow_daily_monitor.py:465-560`) does not independently verify
   that the record's own `consistency` block actually came from a `captured_session`-sourced
   comparison (vs. e.g. a hand-edited or legacy-format ledger row being upserted directly via
   `upsert_ledger`/`append_ledger`, `simnow_daily_monitor.py:568-594`, with no schema/source
   validation at write time). A future manual or legacy-format record could set
   `consistency.matched=True` without ever having gone through `compare_simnow_replay`'s
   `require_captured` gate, and `build_20d_report` (`simnow_daily_monitor.py:619-685`) would count
   it as a valid day with no way to detect the provenance gap.
3. **The daily brief doesn't surface the new window's key fields.** `simnow_daily_brief.py`'s
   `build_daily_brief` (confirmed function present) does not print `observation_start_date`,
   `excluded_before_start_count`, or `ledger_summary.next_action` — these exist in the machine-
   readable JSON (`ledger_summary` in `simnow_run_summary.py`'s output) but are invisible in the
   human-facing report, making it easy for a human reviewer to misjudge whether today counts toward
   the 20-day window.
4. **`simnow_run_summary.py`'s `promotion` sub-section doesn't carry the window-filter metadata.**
   `ledger_summary` (the source) has `observation_start_date`/`excluded_before_start_count`, but
   whatever downstream `promotion` sub-section is built from it (need to confirm exact
   function/field name during A64's own design step) does not — a future agent that reads only the
   `promotion` sub-section (a plausible narrower read, since that's the field most directly
   answering "can we promote yet") could lose track of the window basis entirely.

**Task-ID note:** continues sequentially from **A61**, the next unused ID as of 2026-07-14
(A38-A48 = P1-P8 roadmap, A49-A54 = first audit remediation wave, A55-A60 = second remediation
wave, now `done`).

---

## 2. Task Sequence

| ID | Title | Findings covered | Priority |
|----|-------|-------------------|----------|
| A61 | Captured-session surface: workflow-owned filter + account_contamination wiring | #1 | **First — directly affects whether a valid-observation day can be trusted** |
| A62 | Consistency provenance floor: reject/flag non-`compare_simnow_replay`-sourced ledger records | #2 | **Second — same reason as A61** |
| A63 | Daily brief: surface window fields (`observation_start_date`, `excluded_before_start_count`, `ledger_summary.next_action`) | #3 | Third |
| A64 | Run-summary `promotion` sub-section: carry window-filter metadata | #4 | Fourth |

All four are independent of each other in code (different functions/files), but A61/A62 are
prioritized first per the user's own instruction ("先修1和2，它们直接影响'有效观察日是否可信'" — fix
1 and 2 first, they directly affect whether a valid-observation day can be trusted). A63/A64 are
purely presentational/metadata-completeness and do not affect any pass/fail decision, so they carry
no urgency beyond "before the next agent reads a stale report." Per the standing house rule, only
one task is promoted/active at a time.

**Whether today (2026-07-14) counts toward the 20-day window is explicitly NOT decided by this
roadmap** — that is a machine-field judgment made after `simnow_run_summary_2026-07-14.json` is
generated (per the sub-agent's own "最短下一步" note), independent of whether A61-A64 have shipped
yet. Do not block today's capture/observation run on this roadmap landing.

---

## A61 — Captured-Session Surface: Workflow-Owned Filter + `account_contamination` Wiring

### Rationale
`build_strategy_surface_from_captured_session` (`simnow_strategy_surface.py:85-107`) converts
`capture["captured"]["trades"]`/`["positions"]` — which are simply `list(state.positions.values())`
and the raw trade list from `simnow_daily_capture.py:302-306`, **not filtered by symbol** — directly
into the comparison surface consumed by `compare_simnow_replay`. Any trade or position in the same
SimNow account on a symbol the workflow does not itself trade (genuine external/manual account
activity, which SimNow accounts commonly have) flows into the `positions`/`trades` comparison
categories and can produce a false `extra_in_simnow` mismatch — incorrectly marking a day
inconsistent when the strategy itself behaved correctly. `extract_account_contamination`
(`simnow_run_summary.py:107-129`) already exists and is the correct destination for this
information ("external audit evidence only, not strategy PnL") but currently reads independently
from `raw.*`, not from whatever gets filtered out of the captured-session surface — so the two
paths are not yet connected, and nothing currently guarantees "external position → excluded from
comparison, counted in contamination" as a single coherent invariant.

### Semantics
In `build_strategy_surface_from_captured_session` (or a helper it calls), filter
`captured["trades"]`/`captured["positions"]` to only those rows whose `symbol` matches a
workflow-owned contract — the set of `contract["symbol"]` values from `capture["meta"]["contract_map"]`
(already available on the capture payload, built by `load_contract_map`/`contract_subscriptions` in
`simnow_daily_capture.py`). Rows that don't match should NOT enter the comparison surface's
`trades`/`positions`; instead, the caller (`enrich_capture_json` or `make_record`, whichever proves
to be the right seam during implementation) should route the filtered-out rows into the same
external-audit-evidence path `extract_account_contamination` already reports, so nothing is
silently dropped — every captured event is accounted for as either "workflow-owned, compared" or
"external, contamination-only." No new config key.

### No-lookahead & correctness
Pure same-day filtering on already-captured data; no new data read, no timing change, no SimNow
order/cancel/send path touched.

### Expected files
- `chan_strategy` is NOT touched — this is entirely within
  `examples/czsc_strategy/diagnostics/simnow_strategy_surface.py` (the filter) and possibly
  `simnow_daily_capture.py`/`simnow_run_summary.py` (wiring the filtered-out rows to
  `account_contamination` if the current call graph needs a small adjustment to pass them through).
- `examples/czsc_strategy/tests/unit/test_simnow_strategy_surface.py` (new cases: a captured
  position/trade on a non-workflow symbol is excluded from the comparison surface and appears in
  `account_contamination`'s counts instead; a captured position/trade on a workflow-owned symbol is
  unaffected — byte-identical to current behavior for that case).

### Acceptance (decidable)
- [ ] A fixture with a captured position on a symbol NOT in `contract_map` produces a comparison
      surface (`positions`) that does not include that row, and `account_contamination`'s
      `active_positions`/`position_symbols` count reflects it instead (unit-tested).
- [ ] The same fixture for a captured trade (not just position) on a non-workflow symbol.
- [ ] A fixture with only workflow-owned positions/trades is completely unaffected — existing
      `test_simnow_strategy_surface.py` tests still pass byte-identical.
- [ ] `compare_simnow_replay`'s existing consistency-matching behavior for workflow-owned events is
      unchanged (no new false negatives introduced by the filter itself).
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow order/cancel/send path changed; no
      `GOAL PASSED`.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not change `extract_account_contamination`'s own reporting shape (still reads `raw.*`
independently for its top-level counts) — this task only ensures a workflow-owned filter exists
upstream of the comparison surface and that filtered-out rows are traceable, not that
`account_contamination`'s implementation itself is restructured. Does not touch `raw.*`'s contents,
`compare_simnow_replay`'s comparison algorithm, or any SimNow live-session capture logic.

### Dev prompt
```text
Read A61. In simnow_strategy_surface.py's build_strategy_surface_from_captured_session, filter
captured trades/positions to workflow-owned symbols (from capture["meta"]["contract_map"]) before
they enter the comparison surface. Route filtered-out rows so they are still visible via
account_contamination's existing external-activity reporting, not silently dropped. Add tests
proving external-symbol events are excluded from comparison and workflow-owned events are
unaffected. No tuning, no SimNow paths, no GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: a captured event on a non-workflow symbol still reaches the comparison surface; a
workflow-owned event's comparison behavior changes at all; filtered-out rows become untraceable
(neither compared nor visible in contamination reporting).

---

## A62 — Consistency Provenance Floor for Ledger Records

### Rationale
`compare_simnow_replay` already gates on `consistency_source_mode="require_captured"` by default
(`simnow_daily_monitor.py:290-308`) — a real, existing safeguard. But this only controls what
`compare_simnow_replay` itself computes; nothing currently verifies, at the point a record is
written to the ledger (`upsert_ledger`/`append_ledger`, `simnow_daily_monitor.py:568-594`), that the
record's `consistency` block actually originated from that function with that mode. A future
hand-edited, legacy-format, or otherwise irregularly-produced ledger row could set
`consistency.matched=True` directly, and `build_20d_report`'s `valid_observation`/`matched_days`
counting (`simnow_daily_monitor.py:609-685`, and `is_valid_observation` wherever it's defined) would
accept it with no way to detect the provenance gap. The 2026-04-14 window exclusion already handles
the *old* ledger's rows being out-of-window — this task is about preventing a *future* row from
silently bypassing the provenance requirement the `require_captured` mode was designed to enforce.

### Semantics
Add a schema/provenance check — either at `upsert_ledger`/`append_ledger` write time, or as part of
`is_valid_observation`'s own logic (read `is_valid_observation` in full during this task's design
step to decide which seam is correct; do not guess) — that a record's `consistency` block must carry
a marker proving it passed through `compare_simnow_replay` under `consistency_source_mode=
"require_captured"` with `source == "captured_session"` (e.g. the existing `meta.strategy_surface.
source` field, or a new explicit `consistency.source_mode`/`consistency.verified` field set only by
`compare_simnow_replay` itself). Records lacking this marker should not count as `valid_observation`
even if `matched=True` — flag them distinctly (e.g. `reason="consistency_provenance_unverified"`)
rather than conflating them with a genuine mismatch, so a human can tell "this day never proved
consistency" apart from "this day proved inconsistency." No new config key beyond what's needed to
carry the marker itself.

### No-lookahead & correctness
Pure same-day validation logic; no new data read, no timing change, no SimNow paths touched.

### Expected files
- `examples/czsc_strategy/diagnostics/simnow_daily_monitor.py` (`compare_simnow_replay` sets the
  provenance marker; `is_valid_observation`/`make_record` checks it)
- `examples/czsc_strategy/tests/unit/test_simnow_daily_monitor.py` (new cases: a record with
  `matched=True` but no provenance marker is NOT counted as `valid_observation`, with a distinct
  reason code; a record produced through the normal `compare_simnow_replay` path is unaffected)

### Acceptance (decidable)
- [ ] A fixture record with `consistency.matched=True` but lacking the provenance marker is excluded
      from `valid_observation`/`matched_days` counting, with a distinct, identifiable reason
      (unit-tested).
- [ ] A fixture record produced through `compare_simnow_replay`'s normal `require_captured` path
      counts as `valid_observation` exactly as before (byte-identical for this case).
- [ ] Existing 20-day-report/ledger tests pass byte-identical for all previously-valid records.
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow order/cancel/send path changed; no
      `GOAL PASSED`.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Does not change `consistency_source_mode`'s own existing default or semantics — adds a provenance
floor on top of it. Does not retroactively re-validate already-`done` historical ledger rows beyond
what the 2026-04-14 window exclusion already does.

### Dev prompt
```text
Read A62. Read is_valid_observation and compare_simnow_replay in full first. Add a provenance
marker that compare_simnow_replay sets when a comparison genuinely passed through the
require_captured/captured_session path, and have valid_observation-counting logic require it --
records missing the marker must not count as valid even if matched=True, with a distinct reason
code. No tuning, no SimNow paths, no GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: a record can still count as `valid_observation` without the provenance marker; the
distinct reason code is conflated with genuine-mismatch reasons; any existing genuinely-valid record
stops counting.

---

## A63 — Daily Brief: Surface Window Fields

### Rationale
`simnow_daily_brief.py`'s `build_daily_brief` produces the human-facing report but does not print
`observation_start_date`, `excluded_before_start_count`, or `ledger_summary.next_action` — all
already present in the machine-readable `ledger_summary` JSON. The 2026-07-14 audit found the
machine logic itself correct ("机器口径没错") but the human report insufficiently clear about
window basis, risking a human reviewer misjudging whether a given day counts.

### Semantics
Add these three fields to `build_daily_brief`'s output, in the existing 20-day-observation summary
section (near the existing `valid_observation_days`/`ready_to_expand` lines). No new config key;
purely additive report content.

### No-lookahead & correctness
Not applicable — pure report-rendering change, no data-flow or timing change.

### Expected files
- `examples/czsc_strategy/diagnostics/simnow_daily_brief.py`
- `examples/czsc_strategy/tests/unit/test_simnow_daily_brief.py` (new case: a brief built from a
  summary containing these fields renders them; existing tests for briefs without them still pass)

### Acceptance (decidable)
- [ ] A fixture summary with `observation_start_date`/`excluded_before_start_count`/
      `ledger_summary.next_action` set produces a brief that includes all three values
      (unit-tested).
- [ ] A fixture summary without these fields (e.g. an older-shaped payload) renders without KeyError
      — graceful fallback (e.g. omit the line or show a placeholder), not a crash.
- [ ] Existing daily-brief tests pass byte-identical for their existing assertions.
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow order/cancel/send path changed; no
      `GOAL PASSED`.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Purely additive to the report text — does not change any machine-readable JSON schema, any
pass/fail decision logic, or any file other than the brief renderer and its test.

### Dev prompt
```text
Read A63. Add observation_start_date, excluded_before_start_count, and ledger_summary.next_action
to simnow_daily_brief.py's build_daily_brief output, near the existing 20-day-observation section.
Handle missing fields gracefully (no crash on older-shaped input). No tuning, no SimNow paths, no
GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: any of the three fields is missing from the rendered brief when present in the input; a
missing-field input crashes instead of degrading gracefully; any existing brief test's output
changes unexpectedly.

---

## A64 — Run-Summary `promotion` Sub-Section: Carry Window-Filter Metadata

### Rationale
`ledger_summary` (produced in `simnow_daily_monitor.py`/consumed by `simnow_run_summary.py`) carries
`observation_start_date`/`excluded_before_start_count`, but whatever `promotion` sub-section
`simnow_run_summary.py` builds from it does not — confirm the exact field/function name as this
task's own first design step (read `simnow_run_summary.py` in full; do not assume a name not yet
verified). A future agent reading only the narrower `promotion` sub-section (a plausible read, since
it most directly answers "can we promote yet") could lose the window basis entirely and
misinterpret `valid_observation_days` counts without knowing they already exclude pre-window rows.

### Semantics
Add `observation_start_date`/`excluded_before_start_count` (or equivalent window-filter metadata,
whatever the verified field names turn out to be) to the `promotion` sub-section's own output,
sourced from the same `ledger_summary` data already available. No new config key; purely additive
metadata propagation, mirroring the existing `_safe_ledger_summary` pattern
(`simnow_run_summary.py:221-229`) if that proves to be the right seam.

### No-lookahead & correctness
Not applicable — pure metadata propagation, no data-flow or timing change.

### Expected files
- `examples/czsc_strategy/diagnostics/simnow_run_summary.py`
- `examples/czsc_strategy/tests/unit/test_simnow_run_summary.py` (new case: the `promotion`
  sub-section includes the window-filter fields when `ledger_summary` has them)

### Acceptance (decidable)
- [ ] A fixture `ledger_summary` with `observation_start_date`/`excluded_before_start_count` produces
      a `promotion` sub-section that also carries them (unit-tested).
- [ ] Existing run-summary tests pass byte-identical for their existing assertions.
- [ ] No threshold tuning; no pre-2026-04-24 data; no SimNow order/cancel/send path changed; no
      `GOAL PASSED`.
- [ ] Full unit suite, root + child `sync_check`, preflight pass.

### Boundaries
Purely additive metadata propagation — does not change any promotion pass/fail decision itself,
only what context accompanies it.

### Dev prompt
```text
Read A64. First confirm the exact promotion sub-section function/field name in
simnow_run_summary.py (read the file in full). Propagate observation_start_date and
excluded_before_start_count (or equivalent verified field names) from ledger_summary into that
sub-section. No tuning, no SimNow paths, no GOAL PASSED. Handoff next.
```

### Review checklist
Reject if: the promotion sub-section still omits the window-filter fields when ledger_summary has
them; any existing run-summary test's output changes unexpectedly; a wrong/guessed field name is
used without having read the actual file first.

---

## 3. Cross-Task Notes

- **No hard dependencies** — A61-A64 may be resequenced if priorities change, though A61/A62 should
  land before A63/A64 per the user's stated priority (trustworthiness of valid-observation-day
  counting matters more than report presentation).
- **None of A61-A64 touch any SimNow order/cancel/send path** — all four are diagnostics/monitoring
  script changes only. This roadmap carries materially lower risk than A55-A60 (which touched live
  backtest-engine trading logic); reviewers should still apply the same rigor to test coverage and
  scope discipline, but there is no equivalence-snapshot concern analogous to
  `exit_model="legacy"`/`limit_halt_model="off"` here.
- **Today's (2026-07-14) observation-day validity is independent of this roadmap** — per the
  sub-agent's own note, whether today counts toward the 20-day window is a machine-field judgment
  made after `simnow_run_summary_2026-07-14.json` generates; do not block today's capture run on
  A61-A64 landing.
- **Promotion discipline unchanged**: no task in this roadmap may claim `GOAL PASSED` or
  profitability from pre-2026-04-24 data. Each task is its own handoff task (design → dev → review →
  done); do not batch multiple A61-A64 items into one dev handoff.
