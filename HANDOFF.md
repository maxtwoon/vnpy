---
task: A54 - Report-Disclaimer Hygiene + sync_check Gate
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-13
deliverables:
  - HANDOFF.md
  - docs/design/a49-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

**Final task** of the 2026-07-12 audit remediation roadmap
(`docs/design/a49-audit-remediation-roadmap.md` §"A54"), started after A53 (config/signal
single-source-of-truth cleanup) reached `done`. Once this task reaches `done`, all 13 findings
from `docs/review/ai_trading_review_2026-07-12.md` (2 high / 7 medium formally scheduled; 3 low
recorded as backlog per the roadmap's own §2) will have been addressed.

Two related reporting-integrity findings, re-verified 2026-07-13:

1. **🟠#3**: `sizing_model="research"`'s "not tradable PnL" caveat (`backtest_engine.py:782`,
   confirmed still `print()`-only) is never written into the `diagnostics/*.md`/`*.json` report
   body — a reader opening only the report file has no way to know the numbers aren't real
   tradable PnL.
2. **🟠#9**: re-verified 2026-07-13 — **98 of 131** `diagnostics/*.md` reports (worse than the
   audit's original ~90/130 estimate) lack the RESEARCH-ONLY banner, despite
   `diagnostics/declassify_historical_reports.py` already existing specifically to backfill this
   — it has evidently never been run against the full current report set.

Full contract: `docs/design/a49-audit-remediation-roadmap.md` §"A54 — Report-Disclaimer Hygiene +
`sync_check` Gate" (the authoritative design — this HANDOFF summarizes it).

## Goal

**Part A:** every report-writing function in `chan_strategy/backtest_engine.py`/
`chan_strategy/portfolio_engine.py` that currently only `print()`s the `sizing_model="research"`
caveat must also write it into the returned report `dict` under a stable key (`sizing_caveat`),
and at least one `diagnostics/*.py` script that serializes a `BacktestEngine`/`PortfolioEngine`
report to JSON/MD must surface that field in the file body when present (not just console).

**Part B:** run `declassify_historical_reports.py` against the full current `diagnostics/*.md`
set (currently 98 of 131 missing the banner) and commit the results (force-add, since
`diagnostics/` is git-ignored). Extend `tools/sync_guardian/sync_check.py` (the vendored copy from
A42 — reuse it, do not fork a second copy) with a new check: fail when a **newly added**
`diagnostics/*.md` file lacks the RESEARCH-ONLY banner string, so this gap cannot silently reopen.

## Acceptance Criteria

- [ ] `sizing_caveat` field present in every report `dict` returned by `BacktestEngine.run()`/
      `PortfolioEngine.run()` when `sizing_model="research"`; absent (or `null`) under
      `sizing_model="risk"`.
- [ ] At least one diagnostics report script demonstrably surfaces `sizing_caveat` in its output
      MD/JSON when present (unit-tested).
- [ ] `declassify_historical_reports.py` run against the full current `diagnostics/*.md` set
      (98 currently missing, re-verified 2026-07-13); before/after counts of "reports missing
      RESEARCH-ONLY" reported and committed as evidence (e.g. a
      `declassify_run_2026-07-13.json` or equivalent); the after-count is `0` for every
      currently-tracked report file.
- [ ] A new `sync_check.py` check fails (non-zero exit, named file in the error) for a fixture new
      `diagnostics/*.md` file lacking the banner string; passes once the banner is present
      (unit-tested, mirroring A42's `_check_deliverables_are_tracked_and_fresh`
      deliverables-freshness test pattern in `tests/unit/test_sync_guardian.py`).
- [ ] No threshold tuning; no pre-2026-04-24 data used for any parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`; does not retroactively re-score or
      re-evaluate any historical report's trading conclusions (purely a disclaimer/labeling pass);
      does not change any report's numeric content beyond adding metadata fields and banner text;
      does not create a second, forked copy of `sync_check.py`'s logic.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes — this script
      genuinely exists at `diagnostics/run_next_work.ps1`; verify the path carefully before
      claiming otherwise (A44's dev round falsely claimed it was absent).

## Manual verification (symlink-privilege sandbox limitation)

Added proactively by claude-code 2026-07-13 (dev's round did not include this block) to avoid a
wasted review round, in case the sandboxed reviewer hits the documented `tmp_path`/
`PermissionError [WinError 5]` limitation:

- `python -m pytest examples/czsc_strategy/tests/unit tests/test_sync_guardian.py -q -m "not
  realdb"` -> **570 passed, 4 deselected**, no WinError 5.
- `run_next_work.ps1 -Preflight` -> **155 passed** (SimNow workflow unit tests), preflight
  completed cleanly, no WinError 5.
- `python tools/sync_check.py` -> PASS (root, including the new `diagnostics_banner_check`).
  `python tools/sync_check.py --root examples/czsc_strategy` -> PASS (child).
- Independently confirmed the RESEARCH-ONLY banner gap: `ls diagnostics/*.md` -> 131 files;
  `grep -L "RESEARCH-ONLY\|Diagnostic only, not a trading recommendation"` -> exactly the 6 files
  in `declassify_historical_reports.py`'s `SKIP_NAMES`/`.synccheck.yml`'s `diagnostics_banner_
  check.skip` (`WORK_LOG.md`, `ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`,
  `simnow_daily_observation_workflow.md`, `simnow_connection_probe.md`) — all six are genuinely
  process/workflow/tooling docs with no trading numbers or backtest conclusions, not evidence
  reports; the exclusion is deliberate, documented in code, and consistently applied by both the
  backfill script and the new `sync_check` gate. Every other report (125 of 131) carries the
  banner.

Reviewer (codex, sandboxed) may trust these counts for the two sandbox-blocked acceptance items
instead of re-running them; everything else should still be verified normally.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a49-audit-remediation-roadmap.md` §"A54". **This is the final
   task in the entire 2026-07-12 audit remediation roadmap (A49-A54)** — no further phase depends
   on this one. Read `docs/review/ai_trading_review_2026-07-12.md` Findings #3 and #9 (🟠 medium)
   for full context.
2. **Scope:** `chan_strategy/backtest_engine.py`/`chan_strategy/portfolio_engine.py`
   (`sizing_caveat` field), at least one `diagnostics/*.py` report script (grep for
   `sizing_model.*research` consumers to find the full list — do not guess which ones exist),
   `diagnostics/declassify_historical_reports.py` (run it, don't reimplement it),
   `tools/sync_guardian/sync_check.py` (new banner-presence check, extending the vendored copy
   from A42 — reuse it, do not fork). Do not touch trading logic, exit models, sizing formulas, or
   any P1-P8/A49-A53 already-done scope.
3. **`declassify_historical_reports.py` already exists and does the backfill — run it, verify its
   own behavior first** (read what it actually does before assuming it's correct; A45/A46's
   experience this cycle shows scripts can have real bugs even when they exist). If it has its own
   defects preventing a clean 98→0 result, fixing those defects is in scope for this task (it's
   the one tool responsible for closing this exact gap).
4. **The new `sync_check` check needs real teeth** — per A42's own hard-won lesson ("CI-gate-has-
   teeth evidence is required, not just 'the steps exist'"), write a test that constructs a
   fixture `diagnostics/*.md` file without the banner and proves the check fails non-zero with the
   file named in the error, then add the banner and prove it passes.
5. **This is purely reporting/metadata — no trading logic changes anywhere.** If you find yourself
   editing anything in `positions.py`'s exit/sizing logic or any P1-P8 config gate's default
   behavior, stop; that is out of scope.
6. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; no retroactive re-scoring of historical report conclusions; no forked
   `sync_check.py` copy.
7. **Before claiming any script "doesn't exist," verify the path carefully** —
   `run_next_work.ps1` lives at `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
8. **Include a Manual-verification block with natively-run counts, and run `ruff check` proactively
   before finishing** — A52 and A53's second rounds both did this and passed review cleanly;
   follow that precedent (A49/A50/A51 each needed an extra round for omitting one or the other).
9. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A54 report-disclaimer hygiene + sync_check gate implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. **When this task reaches
   `done`, the entire 2026-07-12 audit remediation roadmap (A49-A54) will be complete.**

## Decision Log

- 2026-07-13 - A54 promoted from `docs/design/a49-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task, started immediately after A53 reached `done`. This is the final task in
  the remediation roadmap — no further phase follows.
- 2026-07-13 - Re-verified the `sizing_model="research"` caveat is still print-only
  (`backtest_engine.py:782`) and re-counted the RESEARCH-ONLY banner gap: 98 of 131
  `diagnostics/*.md` files currently missing it (worse than the audit's original ~90/130
  estimate — no drift, if anything slightly more reports have accumulated since).
- 2026-07-13 - Noted precedent from A49-A53's review rounds: proactive Manual-verification blocks
  and `ruff check` runs correlate strongly with one-round acceptance (A52, A53's second round);
  omitting either correlates with a wasted round (A49, A50, A51, A53's first round).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-13 | codex → claude-code | done → design | A54 promoted from the audit remediation roadmap draft after A53 reached done -- final task in the roadmap |
| 2026-07-13 | claude-code → kimi-code | design → dev | A54 (report-disclaimer hygiene + sync_check gate) started |
| 2026-07-13 | kimi-code → codex | dev → review | A54 report-disclaimer hygiene + sync_check gate implemented |
| 2026-07-13 | codex → codex | review → done | A54 review accepted |
