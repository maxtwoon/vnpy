---
task: A39 Rollover-Pollution Diagnostic + Trading-Calendar Daily Aggregation (P2)
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-11
deliverables:
  - HANDOFF.md
  - docs/design/a39-rollover-trading-calendar.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

Roadmap phase **P2** (see `docs/design/a38-phase-contracts-p2-p8.md`), now a standalone task
after A38 Phase 1 (touch-based stop execution) reached `done`. Two 888 data-hygiene changes:

- **Rollover pollution (audit H4 / review A2):** 888 tables are a raw multi-contract splice;
  rollover gaps are read as real moves (fake breakouts / gap stops / divergence). Confirmed
  2026-07-10: the raw tables carry a **`real_symbol`** column (e.g. `sc888 -> sc2202`) that
  changes at each rollover, so transitions are detectable **exactly**.
- **Session boundary:** `resample_bars` builds daily bars by natural date
  (`data_adapter.py:61-83`), which splits a futures night session (start ~21:00, past midnight,
  belongs to the next trading day) into two "daily" bars — the daily trend filter then sees a
  structure that does not match the exchange trading day.

A39 = a read-only rollover-exclusion diagnostic (Phase 0) + a gated trading-calendar daily
aggregation (Phase 1, default `"natural"` byte-identical). Guardrails: gated default-off,
diagnostic-first, no OOS tuning, research-only, no SimNow order changes.

Single source of truth: `docs/design/a39-rollover-trading-calendar.md`.

## Goal

Ship, in order: (Phase 0) `diagnostics/rollover_exclusion_report.py` detecting rollover dates
from `real_symbol` and reporting before/after `trade_count`/`return`/`drawdown`/
`stop_loss_overshoot` when signals/trades within `transition ± 1 trading day` are excluded, plus
a tracked 888 `found_spliced` risk note; (Phase 1) `STRATEGY_CONFIG["daily_agg"]`
(`"natural"` default | `"trading_calendar"`) mapping night/evening bars to the next trading day
in the daily resample path, with the `"natural"` path byte-identical.

## Acceptance Criteria

- [ ] `STRATEGY_CONFIG["daily_agg"]` (`"natural"` default | `"trading_calendar"`) and
      `night_session_start_hour` exist and are documented in `config.py`.
- [ ] Natural equivalence: with `daily_agg="natural"`, the daily-bar sequence (dt, OHLC, vol) is
      byte-identical to the current output on >=2 symbols x 1 year (golden resample test).
- [ ] Trading-calendar grouping (unit): a fixture with an evening session crossing midnight
      (bars at 22:00 + 01:00 + next day-session 10:00 of the same trading day) aggregates into
      ONE daily bar keyed to the trading day; a Friday-night bar rolls to the next present
      trading date (not Saturday); a post-midnight bar on a non-trading date rolls forward.
- [ ] `test_daily_no_lookahead` passes under both `daily_agg` modes; daily-bar timestamps remain
      the last constituent 1-minute bar.
- [ ] Rollover diagnostic: `rollover_exclusion_report_*.{json,md}` generated; AP/RB/SC/A/ZN each
      have `transition_dates` (with from/to contracts from `real_symbol`) or an explicit
      `unavailable` reason; `detection_method` stated (real_symbol primary); before/after
      `trade_count` / `return` / `drawdown` / `stop_loss_overshoot` all present.
- [ ] Both reports carry the RESEARCH-ONLY disclaimer; no `GOAL PASSED`; evidence git-tracked
      (diagnostics/ is ignored -> `git add -f`).
- [ ] 888 `found_spliced` + no-cross-rollover-adjustment declaration written to a tracked doc.
- [ ] No threshold tuned; no pre-2026-04-24 data used for any selection; no SimNow order/cancel/
      send paths changed; no new `send_order`/`cancel_order`/`buy`/`sell`/`short`/`cover`.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight`
      passes.

## Notes for the Next Agent

(review = codex, 2026-07-11)

Rejected: A39 is closer, but the review gates and report-shape acceptance criteria are still not
met.

Actionable findings:

1. The exact unit-test acceptance command did not pass:
   `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"`.
   First run failed during collection because `vnpy.trader.logger` tried to write
   `C:\Users\Admin\.vntrader\log\vt_20260711.log` and hit `PermissionError`. After creating the
   repo-local ignored `.vntrader\log`, pytest progressed but still ended with `288 passed,
   2 deselected, 85 errors`; the errors were all pytest `tmp_path` setup failures because the
   default temp root `C:\Users\Admin\AppData\Local\Temp\pytest-of-Admin` is not accessible in this
   managed workspace. Make the required test command runnable without external user-profile write
   access, or document/update the gate if a specific temp/log setup is mandatory.
2. The exact preflight gate failed:
   `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight`.
   Failure occurred at "Compile SimNow capture script" with `WinError 5` while Python tried to
   replace `examples\czsc_strategy\diagnostics\__pycache__\simnow_daily_capture.cpython-314.pyc`.
   The acceptance command must pass as written.
3. The generated rollover JSON omits required before/after metric blocks for unavailable symbols.
   `RB888` and `A888` contain `unavailable` and `detection_method`, but no `before` / `after`
   `trade_count`, `return`, `drawdown`, or `stop_loss_overshoot`. The design review checklist
   rejects if any before/after report field is missing or hidden.
4. The generated report evidence does not carry the explicit `RESEARCH-ONLY` label. `rg` found
   `RESEARCH-ONLY` only in `examples/czsc_strategy/RISK_NOTE_888_SPLICE.md`, not in
   `rollover_exclusion_report_2026-07-10.{json,md}`. If the intended required text is only
   `Diagnostic only, not a trading recommendation.`, update the acceptance wording; otherwise add
   the explicit label to both report outputs.
5. Natural equivalence evidence is weak against the stated contract. The real-db test is marked
   `realdb` and excluded by the required unit command, and it checks populated daily bars rather
   than comparing against a cached/pre-change golden sequence on >=2 symbols x 1 year. Add a
   decidable golden comparison or update the acceptance criterion to match the available evidence.

Checks that did pass in this review:

- `python tools/sync_check.py`
- `python tools/sync_check.py --root examples/czsc_strategy`
- The cumulative A39 diff is scoped to expected files, and no new
  `send_order` / `cancel_order` / `buy` / `sell` / `short` / `cover` calls were found in the task
  diff.

(review = codex, 2026-07-10)

Rejected again: this dev -> review handoff still does not satisfy the A39 acceptance criteria.
The current diff remains unrelated SimNow daily-observation wrapper work plus handoff/work-log
updates; it does not contain the rollover-pollution diagnostic or trading-calendar daily
aggregation implementation required by `docs/design/a39-rollover-trading-calendar.md`.

Actionable findings:

1. Implement the A39 deliverables from `docs/design/a39-rollover-trading-calendar.md` Section 5.
   Review evidence: `git diff --stat` only shows `HANDOFF.md`,
   `examples/czsc_strategy/diagnostics/WORK_LOG.md`,
   `examples/czsc_strategy/diagnostics/run_next_work.ps1`, and
   `examples/czsc_strategy/tests/unit/test_run_next_work_wrapper.py`.
2. Add and document `STRATEGY_CONFIG["daily_agg"]` and `night_session_start_hour`. Review check:
   `rg "daily_agg|night_session_start_hour" examples/czsc_strategy/chan_strategy examples/czsc_strategy/tests docs/design/a39-rollover-trading-calendar.md`
   found hits only in the design doc, not implementation or tests.
3. Add the trading-calendar daily aggregation path and tests. `data_adapter.resample_bars`
   still groups daily bars by `bar.dt.date()` only, and `test_data_adapter.py` still asserts the
   night session is split by natural day.
4. Add and track `diagnostics/rollover_exclusion_report.py`,
   `test_rollover_exclusion_report.py`, and `rollover_exclusion_report_*.{json,md}` evidence.
   Review check: `git ls-files examples/czsc_strategy/diagnostics/rollover_exclusion_report* examples/czsc_strategy/tests/unit/test_rollover_exclusion_report.py`
   returned no files.
5. Add the tracked 888 `found_spliced` / no-cross-rollover-adjustment risk note required by A39.
6. Keep the SimNow daily-observation wrapper changes out of this A39 handoff, or move them to a
   separate task. They are not acceptance evidence for rollover pollution or trading-calendar
   daily aggregation.
7. Re-run acceptance commands after implementation. Current review results:
   `python tools/sync_check.py` passed; `python tools/sync_check.py --root examples/czsc_strategy`
   passed; `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` failed during
   collection with `PermissionError: C:\Users\Admin\.vntrader\log\vt_20260710.log`; and
   `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight`
   failed compiling `simnow_daily_capture.py` because Python could not update a `.pyc` file under
   `diagnostics/__pycache__` (`WinError 5` / access denied).

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a39-rollover-trading-calendar.md`. Implement **Phase 0 first**
   (read-only diagnostic), then **Phase 1** (gated daily aggregation). Full dev prompt in design
   S8.
2. **Rollover detection is exact:** the raw table has a `real_symbol` column (verified:
   `sc888_1M_raw.real_symbol = "sc2202"`, changes at rollover). Use it as the primary detector;
   the ATR-gap heuristic is a labelled fallback only.
3. **`"natural"` must be byte-identical** (golden resample test on >=2 symbols x 1 year) — same
   default-off discipline as A38. Only the daily path changes; the intraday minute resample path
   is untouched.
4. **Trading-day mapping (design 4.1):** derive `trading_dates` from bars with `hour in [8,16)`.
   Evening bar (`hour >= night_session_start_hour`) -> next trading date strictly after its date;
   non-evening bar -> its own date if a trading date else next; timestamp = last constituent bar
   (preserve no-lookahead; `test_daily_no_lookahead` must pass both modes).
5. **Track the evidence:** `diagnostics/` is git-ignored — `git add -f` the diagnostic script and
   the report JSON/MD, or the review will reject as not reproducible from a clean checkout (this
   burned A37 twice and A38 once).
6. **Guardrails (reject-on-violation):** no threshold tuning; no pre-2026-04-24 data for
   selection; no SimNow order paths; RESEARCH-ONLY banner; no `GOAL PASSED`.
7. Finish with the four acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A39 P2 rollover diagnostic + trading-calendar daily implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-10 - A39 started after A38 reached `done`; scope = roadmap P2 (rollover diagnostic +
  trading-calendar daily), split as Phase 0 (read-only) then Phase 1 (gated, default-off).
- 2026-07-10 - Rollover detection uses the raw `real_symbol` column (verified present and
  contract-changing) as the exact primary source; the ATR-gap heuristic is a labelled fallback,
  not the default. Rationale: exact transition dates beat a threshold heuristic and avoid a tuned
  parameter.
- 2026-07-10 - A39 declares the splice and excludes rollover windows only in the diagnostic; it
  does NOT back-adjust live prices or gate live opens around rollover. Those are heavier,
  separate decisions to be informed by this diagnostic first.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-10 | codex → claude-code | done → design | A39 (P2) rollover diagnostic + trading-calendar daily started |
| 2026-07-10 | claude-code → kimi-code | design → dev | A39 design complete: P2 rollover-exclusion diagnostic (via real_symbol) + gated trading-calendar daily aggregation; Phase 0 then Phase 1 |
| 2026-07-10 | kimi-code → codex | dev → review | 自动交接（dev 阶段 agent 完成） |
| 2026-07-10 | codex → kimi-code | review → dev | 打回: A39 implementation and tracked evidence are missing |
| 2026-07-10 | kimi-code → codex | dev → review | 自动交接（dev 阶段 agent 完成） |
| 2026-07-10 | codex → kimi-code | review → dev | 打回: A39 implementation and tracked evidence are still missing |
| 2026-07-10 | kimi-code → codex | dev → review | 自动交接（dev 阶段 agent 完成） |
| 2026-07-10 | codex → kimi-code | review → dev | 打回: A39 implementation and tracked evidence are still missing |
| 2026-07-10 | kimi-code → codex | dev → review | 自动交接（dev 阶段 agent 完成） |
| 2026-07-10 | codex → kimi-code | review → dev | 打回: A39 implementation and tracked evidence are still missing; current diff is unrelated SimNow wrapper work |
| 2026-07-10 | kimi-code → codex | dev → review | 自动交接（dev 阶段 agent 完成） |
| 2026-07-10 | codex → kimi-code | review → dev | 打回: A39 implementation and tracked evidence are still missing |
| 2026-07-10 | kimi-code → codex | dev → review | 自动交接（dev 阶段 agent 完成） |
| 2026-07-10 | codex → kimi-code | review → dev | 打回: A39 implementation and tracked evidence are still missing |
| 2026-07-11 | kimi-code → codex | dev → review | A39 P2 rollover diagnostic + trading-calendar daily implemented |
| 2026-07-11 | codex → kimi-code | review → dev | 打回: A39 report fields and acceptance gates still fail |
| 2026-07-11 | kimi-code → codex | dev → review | A39 P2 rollover diagnostic + trading-calendar daily implemented |
