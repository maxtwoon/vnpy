---
task: A84 - Portfolio Ledger Report Acceptance / Sanity-Check
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-16
deliverables:
  - HANDOFF.md
  - docs/design/portfolio-risk-fusion-design.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

A83 (Phase 1 of the portfolio-risk-fusion work, `docs/design/portfolio-risk-fusion-design.md`)
delivered `diagnostics/portfolio_ledger_report.py` — a read-only aggregation of independently-run
per-symbol `sizing_model="risk"` backtests into a portfolio-level margin/PnL view. It reached
`done` after codex caught and kimi-code fixed two real bugs (forward-fill leak past a symbol's
final bar; cluster case-insensitivity).

**User's explicit next-step decision (2026-07-16)**: do NOT move to Phase 2 (joint replay + real
gating) yet. First prove the Phase 1 ledger's numbers are actually trustworthy against real data —
"先证明它看得准，再让它有权拦单." This task (A84) is that acceptance/sanity-check step. Only after
A84 passes should Phase 2 (a future task, tentatively "A85") be designed.

**Full contract**: this HANDOFF is fairly self-contained for this task; the design doc has the
broader Phase 1/2/3 context if needed.

## Goal

1. Run `diagnostics/portfolio_ledger_report.py` against the real historical SQLite DB
   (`SQLITE_DB_PATH` from `chan_strategy/config.py`) using its own default symbols/window
   (`AP888`/`RB888`/`SC888`/`A888`/`ZN888`, `2022-01-01`~`2026-04-24` — confirmed by claude-code
   these are the script's existing `DEFAULT_SYMBOLS`/`DEFAULT_START`/`DEFAULT_END`; do not change
   them or pick new parameters).
2. Perform the following sanity checks against the real output, cross-referencing each symbol's own
   independent `BacktestEngine` report (which the ledger script already produces per-symbol
   internally — you may need to also run `run_formal_evaluation.py` or an equivalent single-symbol
   `sizing_model="risk"` run for the same symbol/window to get an independent traceable number to
   compare against, since the ledger script's own per-symbol breakdown is the thing being checked,
   not an independent source):
   - Does portfolio total margin occupied at each timestamp equal the timestamp-aligned sum of each
     symbol's own margin?
   - Does portfolio total currency PnL equal the sum of each symbol's own currency PnL?
   - Can the timestamp of max margin utilization be traced back to which specific symbol(s)/cluster
     drove it?
   - Does each symbol's margin contribution correctly go to zero outside that symbol's own data
     range (this was A83's first bug fix — confirm it holds on real data, not just the fixture
     tests)?
   - Is cluster membership correctly case-insensitive on real symbol names (this was A83's second
     bug fix — confirm on real data)?
3. Write up the findings as a fixed acceptance artifact: a markdown report documenting each check,
   the actual numbers observed, and a clear verdict (trustworthy / found issues). This artifact
   must explicitly state, verbatim or in substance: **"this is an independent per-symbol
   aggregation, not a joint/coordinated portfolio replay"** — carrying forward A83's own honesty
   requirement into this acceptance artifact.
4. If the sanity check reveals a genuine bug in `portfolio_ledger_report.py` (not just an
   observation), fix it as part of this task if the fix is small and localized (same file); if it
   reveals something architecturally significant, stop and document it in the Decision Log rather
   than attempting a large fix here — this task's job is to verify Phase 1, not to build Phase 2.

## Acceptance Criteria

- [ ] Real-data run of `diagnostics/portfolio_ledger_report.py` completed; its JSON/Markdown output
      committed as a git-tracked acceptance artifact (`diagnostics/` is gitignored — use
      `git add -f` per house convention, same as prior evidence artifacts in this repo).
- [ ] A new, separate acceptance write-up document (e.g.
      `diagnostics/portfolio_ledger_acceptance_2026-07-16.md`, also `git add -f`'d) covers all five
      sanity checks listed above with actual observed numbers, not just "looks fine."
- [ ] The acceptance write-up explicitly states the report is an independent per-symbol
      aggregation, not a joint replay.
- [ ] If any sanity check fails, it is reported honestly in the write-up (do not paper over a
      failed check to force a "trustworthy" verdict) — and if a small bug is found and fixed,
      the write-up documents the before/after.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped if any code changed; if this task is pure verification with no code
      changes, VERSION/CHANGELOG bump is not required (record which case applies in the Decision
      Log).

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **This task is primarily verification/analysis, not new feature development.** Read
   `diagnostics/portfolio_ledger_report.py` and its test file
   (`tests/unit/test_portfolio_ledger_report.py`) first to understand exactly what the script
   already does before running it.
2. **Use the real SQLite DB** — confirmed accessible by claude-code at the path configured in
   `chan_strategy/config.py`'s `SQLITE_DB_PATH`. Do not fabricate or simulate numbers; run the
   actual script.
3. **No pre-2026-04-24 data for any NEW parameter choice** — this doesn't apply to just running the
   script's own existing defaults, but do not introduce any new parameter tuning while doing this
   verification.
4. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to
   a concurrent, unrelated SimNow-observation workstream. **Before committing, run
   `git status --short` and confirm only your own A84-scoped files are staged.**
5. **Guardrails:** no gating/threshold logic added anywhere; no SimNow order/cancel/send paths
   touched; no `GOAL PASSED`; do not claim the ledger is "production-ready" or a "joint replay" —
   the honest labeling from A83 must be preserved and reinforced, not walked back.
6. **Include a literal `## Manual Verification` heading** with natively-run counts. Run
   `ruff check` proactively before finishing if any code changed.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A84 portfolio ledger acceptance sanity-check completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. After this reaches `done`,
   claude-code will trigger a narrow, targeted confirmation audit (not a full project re-audit)
   asking specifically whether this ledger is sufficient input for a future Phase 2 design task.

## Decision Log

- 2026-07-16 - User reviewed A83's completion and explicitly decided NOT to proceed directly to
  Phase 2. Requested an acceptance/sanity-check step (A84) against real data first, followed by a
  narrow (not full-project) confirmation audit specifically on Phase-2-readiness, before any Phase
  2 design work begins.
- 2026-07-16 - A84 promoted. claude-code confirmed the real historical SQLite DB is accessible on
  this machine at the path configured in `chan_strategy/config.py`.
- 2026-07-16 (kimi-code dev) - Found and fixed a real bug while running the report against the real
  DB: `_find_table()` couldn't disambiguate `{symbol}_1M_raw` vs `{symbol}_5M_raw` when both exist,
  so the ledger initially failed for all five symbols. Added `_infer_table_names()` (small,
  localized to `portfolio_ledger_report.py`) that picks the table matching `freq`, merged so
  explicit caller-supplied `table_names` still take precedence. Ran the report and a separate
  independent acceptance-check script against real data; all five requested sanity checks passed
  (documented with actual numbers in `diagnostics/portfolio_ledger_acceptance_2026-07-16.md`).
  Committed the ledger JSON/Markdown and acceptance write-up as `git add -f`'d tracked evidence
  (`diagnostics/` is gitignored). Bumped VERSION to 0.2.20 <!-- synccheck:ignore -->.
- 2026-07-16 (claude-code independent verification, before triggering codex review) - Read the full
  acceptance write-up and the table-name fix. Independently re-verified the PnL arithmetic by hand
  (33,595.59 − 74,395.27 + 0 − 15,113.73 − 9,550.17 = −65,463.58, matching the reported portfolio
  total of −65,463.57 within rounding). Noted one honest nuance worth recording: the aggregation
  cross-check in `portfolio_ledger_acceptance_check.py` reuses `_build_ledger()` itself (imported
  directly) rather than a from-scratch alternate algorithm, so it verifies reproducibility of a
  freshly-re-executed independent per-symbol backtest through the same aggregation code, not an
  algorithmically independent re-derivation — the write-up discloses this candidly rather than
  overclaiming, and the underlying per-symbol `BacktestEngine` runs genuinely are freshly re-executed
  (not cached), which is what matters for catching data-flow/wiring mistakes. Spot-checked the
  committed `portfolio_ledger_acceptance_check.json` matches the write-up's claimed results
  (`overall_accepted: true` and all five sub-checks `true`). Confirmed no changes to
  `portfolio_engine.py`/`backtest_engine.py` (`git diff --stat` empty on both) and scope was clean
  (only A84-scoped files in kimi-code's commit, unrelated concurrent-workstream files untouched).
  Re-ran everything independently, matching kimi-code's recorded counts: full unit suite `729
  passed, 4 deselected`; `ruff check` clean; both `sync_check.py` gates passed; `run_next_work.ps1
  -Preflight` passed.

## Manual Verification

```text
pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
# 729 passed, 4 deselected

ruff check examples/czsc_strategy/diagnostics/portfolio_ledger_report.py \
           examples/czsc_strategy/diagnostics/portfolio_ledger_acceptance_check.py
# All checks passed

python tools/sync_check.py
# PASS

python tools/sync_check.py --root examples/czsc_strategy
# PASS

powershell -ExecutionPolicy Bypass -File examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight
# Preflight complete

python -c "import json; d = json.load(open('examples/czsc_strategy/diagnostics/portfolio_ledger_acceptance_check.json', encoding='utf-8')); print(d['overall_accepted'])"
# True — spot-checked the committed acceptance-check JSON matches the write-up's claimed verdict
```

Full detailed results with real numbers: `diagnostics/portfolio_ledger_acceptance_2026-07-16.md`.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-16 | claude-code → kimi-code | design → dev | A84 (portfolio ledger acceptance sanity-check) promoted; handoff design->dev |
| 2026-07-16 | kimi-code → codex | dev → review | A84 portfolio ledger acceptance sanity-check completed |
| 2026-07-16 | codex → codex | review → done | A84 portfolio ledger acceptance review passed |
