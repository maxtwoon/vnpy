---
task: A97 - Make rollover_open_gating fail-closed on detection failure (audit M2 + H2 mitigation)
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-22
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/backtest_engine.py
  - examples/czsc_strategy/tests/unit/test_rollover_open_gating.py
  - examples/czsc_strategy/tests/unit/test_a80_unparseable_rows.py
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

`diagnostics_ai_stock_review_report.md` (2026-07-21 full project audit) flagged **M2** (with H2 noting the
same mitigation as its recommended action): when `rollover_open_gating="on"` but rollover-transition
detection fails (`backtest_engine.py:530-541`), the engine currently **silently disables gating and
continues the backtest** (`print(...)` + `gating disabled for this run`) rather than stopping. This is
asymmetric with `limit_halt_model`'s existing behavior (`backtest_engine.py:515-520`ish — missing
`SYMBOL_LIMIT_CONFIG` entry `raise ValueError`s immediately, fail-closed). Since
`formal_evaluation_config()` (`backtest_engine.py:55-90`ish) turns `rollover_open_gating="on"` on for what
this project calls its "trustworthy" evaluation path, a metadata/detection failure there should not be
allowed to silently downgrade to an unprotected run — the whole point of `formal_evaluation_config` is
that its output can be trusted as having the stated protections active.

**claude-code confirmed the exact scope of what needs to change** (re-verify yourself before touching
anything, in case line numbers have drifted):

- `backtest_engine.py:528-541` has TWO distinct branches after `rollover_gating_active` is true:
  1. **Detection failure/unavailable** (`transitions.get("unavailable")` at line 536, populated either by
     `_detect_transitions()` raising an exception at line 533, or returning `{"unavailable": ...}` itself)
     — currently prints a warning and disables gating. **This is what M2 wants changed to fail-closed.**
  2. **Detection succeeded but found zero exclusion dates** (`if not excluded_dates:` at line 547-551) —
     this is a completely legitimate, non-error outcome (the symbol/window genuinely had no rollover in
     range) and must NOT be touched — it should keep printing its informational note and continuing
     normally, exactly as today.
- The only test that specifically validates the current fail-open behavior is
  `test_gating_reports_unavailable_when_metadata_missing` (`tests/unit/test_rollover_open_gating.py:220-229`)
  — it constructs a nonexistent DB path to force detection failure and asserts the backtest completes with
  a degraded-state marker in the report. This test's assertions need to flip direction (assert an
  exception is raised, not that the run completes) — same pattern as A82's fix to
  `assert_not_research_baseline`'s tests: this is fixing a bug the test was encoding, not deleting
  coverage.

## Goal

1. Change the detection-failure branch (`backtest_engine.py:533-541`) from print-and-continue to
   fail-closed: `raise ValueError(...)` with a message following the same style as `limit_halt_model`'s
   existing fail-closed error (`backtest_engine.py:515-520`ish) — state what's misconfigured/missing, and
   what the caller can do about it (fix the metadata/detection issue, or explicitly set
   `rollover_open_gating="off"` if they want to proceed without this protection). Include the original
   detection failure reason (`transitions["unavailable"]` or the caught exception) in the message so a
   caller can actually diagnose it.
2. **Do NOT touch the zero-exclusion-dates branch** (`backtest_engine.py:542-551`, currently
   `if not excluded_dates: print(...)`) — that stays exactly as-is, it's a legitimate outcome, not a
   failure.
3. **This is not scoped to `formal_evaluation_config()` specifically — it applies to
   `rollover_open_gating="on"` regardless of how it was set** (via `formal_evaluation_config()`'s context
   manager, or a caller setting `STRATEGY_CONFIG["rollover_open_gating"] = "on"` directly). This mirrors
   `limit_halt_model`'s existing design: the fail-closed behavior triggers on the config value itself, not
   on "which code path set it" — there's no clean way to distinguish those cases anyway, and a user who
   explicitly asked for `"on"` deserves the same guarantee regardless of how they asked for it.
4. Rewrite `test_gating_reports_unavailable_when_metadata_missing`
   (`tests/unit/test_rollover_open_gating.py:220-229`) to assert the new fail-closed behavior (e.g.
   `with pytest.raises(ValueError, match=...): _run_symbol(...)`) instead of asserting graceful
   degradation. Keep the test's existing setup (nonexistent DB path forcing detection failure) — only the
   assertion direction changes, matching what actually happens now.
5. Verify `test_gating_off_does_not_add_audit_fields` and all other existing
   `test_rollover_open_gating.py` tests are unaffected (they don't hit the detection-failure path) — run
   the full file, don't assume.
6. **Real-data sanity check required, since this changes formal-evaluation-path behavior**: run a
   `formal_evaluation_config()` backtest against the real historical DB (same symbols/window A83/A84/A88
   already established, e.g. one or two of `AP888`/`RB888`) with `rollover_open_gating="on"` and confirm it
   completes without raising the new exception — i.e. confirm detection genuinely succeeds against real
   data and this change doesn't accidentally break the formal-evaluation path that's supposed to keep
   working. Record the actual command and outcome in the Decision Log; this is a smoke check, not a new
   acceptance artifact task — don't over-engineer it into a separate diagnostics script.
7. **Also check `rollover_stat_tagging`** (`backtest_engine.py`, a separate related feature per its own
   config key) doesn't share this exact code path — if it has its own independent detection-failure
   handling, leave it alone; this task is scoped to `rollover_open_gating` only. Note in the Decision Log
   which is the case.

## Acceptance Criteria

- [ ] `rollover_open_gating="on"` + detection failure now raises `ValueError` (or equivalent fail-closed
      exception) instead of silently continuing with gating disabled.
- [ ] The zero-exclusion-dates branch (detection succeeded, no rollovers found in window) is completely
      unchanged — still prints its informational note and continues normally.
- [ ] `test_gating_reports_unavailable_when_metadata_missing` rewritten to assert the exception is raised;
      all other `test_rollover_open_gating.py` tests pass unchanged.
- [ ] Real-data smoke check confirms `formal_evaluation_config()` + `rollover_open_gating="on"` still
      completes successfully against the real historical DB (detection genuinely succeeds there) —
      recorded in the Decision Log with the actual command/output.
- [ ] No change to `rollover_open_gating="off"` behavior (the default) — byte-identical.
- [ ] No change to the zero-exclusion-dates informational path.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes (pass count changes
      only by the rewritten test's assertion direction, not by count, unless a new test was added — note
      which in the Decision Log).
- [ ] `-m realdb` equivalence gate still passes unchanged (this task touches `backtest_engine.py` — verify
      rather than assume).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] `ruff check` clean on touched files.
- [ ] VERSION/CHANGELOG bumped — this is a real behavior change (H2's mitigation), so the CHANGELOG entry
      must clearly state the new fail-closed behavior, not just "docs updated."
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.
- [ ] **Remember the `synccheck:ignore` marker** for any version-like string in this task's own HANDOFF
      notes.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **This task is a real behavior change, not documentation** — unlike M4(A94)/M1(A95)/M3(A96), be
   careful and thorough, same discipline as A82's fix to a real guard bug.
2. **Do not touch the zero-exclusion-dates branch or any other rollover-related code beyond the
   detection-failure branch** — scope creep here (e.g. "let's also tighten the zero-dates case") is
   explicitly out of scope; that's a different, legitimate outcome, not a bug.
3. **Do not touch `limit_halt_model`'s existing fail-closed logic** — it's the reference pattern to match
   the style of, not something to modify.
4. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to a
   concurrent, unrelated SimNow-observation workstream. **Before committing, run `git status --short`
   and confirm only your own A97-scoped files are staged.**
5. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
6. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A97 rollover_open_gating fail-closed completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times
   out for environment reasons (this has happened repeatedly on this machine), do not manually hand-edit
   HANDOFF.md's stage/owner fields to bypass it — leave the working tree with your changes uncommitted and
   note the failure in the Decision Log; claude-code will verify and commit properly.

## Decision Log

- 2026-07-21 - This is the last item from the audit report's M-series (and closes H2's recommended
  mitigation, since H2's root cause — raw 888 continuous-contract splice — remains parked with no
  adjusted-price data source available). After this task, the audit's 3 High + 5 Medium findings are all
  either closed or explicitly, permanently parked with documented reasoning.
- 2026-07-21 (claude-code, design) - Confirmed via code reading that the detection-failure branch
  (`backtest_engine.py:533-541`) and the zero-exclusion-dates branch (`:542-551`) are cleanly separable —
  only the former should change. Confirmed the fail-closed scope should key off
  `rollover_open_gating="on"` itself (not "only inside `formal_evaluation_config()`"), matching
  `limit_halt_model`'s existing precedent, since there's no reliable way to distinguish "set via
  `formal_evaluation_config()`" from "set directly" and no principled reason a direct setter should get a
  weaker guarantee than the context manager. Checked A76's original design doc for a documented rationale
  behind the original fail-open choice — found none, consistent with the audit's assessment that this was
  an oversight, not a deliberate design decision.
- 2026-07-22 (kimi-code, dev) - Implemented exactly per design: the detection-failure branch in
  `backtest_engine.py` now `raise ValueError(...)` (fail-closed) with the detection reason
  (`transitions["unavailable"]` or caught exception, via the existing `detection_failed:` fallback) and the
  explicit opt-out (`rollover_open_gating='off'`) in the message, mirroring `limit_halt_model`'s style.
  Zero-exclusion-dates branch untouched (verified in diff); `"off"` path untouched (verified in diff);
  `limit_halt_model` untouched.
- 2026-07-22 (kimi-code, dev) - Task item 7 answer: `rollover_stat_tagging` does NOT share this code path —
  it uses the separate `BacktestEngine._rollover_excluded_dates()` method (backtest_engine.py:847-861), which
  has its own independent best-effort handling (returns `set()` on any detection failure, tags nothing).
  Left alone per scope.
- 2026-07-22 (kimi-code, dev) - Ripple beyond the design's predicted blast radius (small deviation, recorded
  per workflow rules): `tests/unit/test_a80_unparseable_rows.py::test_formal_evaluation_report_includes_unparseable_rows_skipped`
  also encoded the old fail-open behavior — it runs `formal_evaluation_config()` (gating="on") against a
  synthetic fixture DB with no `real_symbol` metadata, so it hit the detection-failure path and broke under
  fail-closed. Fixed by giving that fixture a valid single-contract `real_symbol` metadata table
  (`_add_rollover_metadata_table` helper), which routes detection to the legitimate zero-exclusion-dates
  outcome; the test's A80 purpose (unparseable-row counting on the formal path) and assertions are unchanged.
  No test added or removed; suite count unchanged (766 not-realdb before and after).
- 2026-07-22 (kimi-code, dev) - VERSION bumped to 0.2.35 (synccheck:ignore) with a CHANGELOG entry stating
  the new fail-closed behavior (real behavior change, H2 mitigation). Deliverables list extended with the two
  additionally touched files (`test_a80_unparseable_rows.py`, VERSION/CHANGELOG) so it matches reality.
- 2026-07-22 (kimi-code, dev) - realdb gate first attempt timed out at the 60s shell default (environment
  quirk, no failure); re-ran with an explicit longer timeout → `4 passed, 766 deselected in 80.02s`.
  Smoke-check script kept at `D:\repo\vnpy\.tmp\a97_smoke.py` (scratch dir, not a new acceptance artifact).

## Manual Verification

(kimi-code, dev, 2026-07-22 — all commands run natively on this machine from
`D:\repo\vnpy\examples\czsc_strategy` unless noted)

1. Targeted tests:
   `python -m pytest tests/unit/test_rollover_open_gating.py tests/unit/test_formal_evaluation.py -q`
   → `17 passed in 0.49s`
2. Full unit suite:
   `python -m pytest tests/unit -q -m "not realdb"`
   → `766 passed, 4 deselected in 49.73s` (pass count unchanged vs pre-change run — the
   rewritten test flipped assertion direction only; no test added/removed)
3. realdb equivalence gate (touches `backtest_engine.py`, so run per AGENTS.md rule):
   `python -m pytest tests/unit -m realdb -q`
   → `4 passed, 766 deselected in 80.02s (0:01:20)`
4. Real-data smoke check (`formal_evaluation_config()` + `rollover_open_gating="on"`,
   real historical DB, window 2024-01-01~2024-06-30, warmup 100):
   `python D:\repo\vnpy\.tmp\a97_smoke.py` →
   ```
   DB: D:\BaiduNetdiskDownload\新数据库\ssquant数据库_20260425\kline_data.db exists=True
   AP888: OK | mode=PARTIAL_PRODUCTION_FEATURES(sizing_model=risk,limit_halt_model=enforce,rollover_open_gating=on) | rollover_open_gating=on | unavailable=None | rejected_opens={'一买多头': 0, '二买多头': 0, '三买多头': 0}
   RB888: OK | mode=PARTIAL_PRODUCTION_FEATURES(sizing_model=risk,limit_halt_model=enforce,rollover_open_gating=on) | rollover_open_gating=on | unavailable=None | rejected_opens={'一买多头': 0, '二买多头': 0, '三买多头': 0}
   A97 SMOKE CHECK PASSED
   ```
   Detection genuinely succeeds on real data; the formal-evaluation path completes
   without raising the new fail-closed ValueError.
5. `ruff check chan_strategy/backtest_engine.py tests/unit/test_rollover_open_gating.py tests/unit/test_a80_unparseable_rows.py`
   → `All checks passed!`
6. `python tools/sync_check.py` (repo root) → `PASS: 版本与文档一致。` (exit 0);
   `python tools/sync_check.py --root examples/czsc_strategy` →
   `[SYNC-CHECK][OK] 版本单一真相 = 0.2.35  (source: VERSION::)   (synccheck:ignore)` + PASS (exit 0)
7. `powershell -ExecutionPolicy Bypass -File .\diagnostics\run_next_work.ps1 -Preflight`
   → `205 passed in 32.12s` + `==> Preflight complete; live SimNow capture was not requested` (exit 0)
8. `git status --short` before handoff: only A97-scoped files changed
   (`CHANGELOG.md`, `VERSION`, `chan_strategy/backtest_engine.py`,
   `tests/unit/test_rollover_open_gating.py`, `tests/unit/test_a80_unparseable_rows.py`,
   `HANDOFF.md`) plus the two pre-existing unrelated SimNow-workstream modifications
   (`diagnostics/WORK_LOG.md`, `diagnostics/simnow_20d_promotion_decision.md`) which were
   NOT touched by this task.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-21 | claude-code → kimi-code | design → dev | A97 (rollover_open_gating fail-closed, audit M2+H2 mitigation) promoted; handoff design->dev |
| 2026-07-22 | kimi-code → codex | dev → review | A97 rollover_open_gating fail-closed completed |
