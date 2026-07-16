---
task: A85 - Joint Replay + Shared PortfolioLedger Design (design-only, no production code)
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-16
deliverables:
  - HANDOFF.md
  - docs/design/a85-joint-replay-design.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

The Phase-2-readiness confirmation audit (triggered after A84) returned **READY WITH CAVEATS**: A83/A84
prove independent per-symbol aggregation is correct, but do NOT prove a joint/coordinated portfolio
replay, shared margin pool, real-time open-gating, or cluster/portfolio gating are correct — those are
untouched algorithmic surfaces.

The user reviewed this and gave an explicit ruling: proceed, but **A85 must be a design-only task**, not
an implementation task. The user does not want Phase 2 code written yet — they want the algorithm
boundary nailed down first, the same way `docs/design/portfolio-risk-fusion-design.md` preceded A83's
implementation. The user specified five design areas that must each get a concrete decision (not an
open question): (1) joint clock model, (2) shared ledger state, (3) open-gating semantics, (4) signal
execution ordering, (5) test matrix. They also noted the mojibake placeholder cosmetic issue found by
the readiness audit is not worth its own task — fold it in opportunistically later, no dedicated task.

claude-code (design role) has already written the full design document answering all five areas with
concrete decisions grounded in the current code (`portfolio_engine.py`, `positions.py`,
`backtest_engine.py`) at `docs/design/a85-joint-replay-design.md`. **This task's "dev" stage is
verification/finalization of that document, not new feature development** — there is no production
code to write. See the user's own acceptance criterion: "不写生产代码，只产出设计文档。"

## Goal

1. Read `docs/design/a85-joint-replay-design.md` in full, and cross-check every code reference it makes
   (file paths, line numbers, config key names such as `cluster_gross_cap`, `daily_loss_limit_pct`,
   `corr_clusters`, `daily_agg`, `sizing_model`, `portfolio_risk`) against the actual current state of
   `chan_strategy/portfolio_engine.py`, `chan_strategy/positions.py`, `chan_strategy/backtest_engine.py`.
   Line numbers may drift slightly; if a cited line number is off by a few lines but the referenced
   function/logic still exists, fix the line number rather than flagging it as wrong. If a referenced
   function/behavior no longer exists or works differently than described, correct the design doc's
   prose to match reality — do not silently leave a stale claim.
2. Confirm the design doc's five decision sections (joint clock model, shared ledger state, open-gating
   semantics, signal execution ordering, test matrix) each give an unambiguous decision with a stated
   reason — not an open question. If you find a spot that is still ambiguous or under-specified enough
   that a future implementer would have to guess, tighten the wording (do not invent brand-new
   architectural decisions beyond what's already written — only clarify/correct what's there).
3. This is a **documentation-only** change. Do NOT write or modify any production code in
   `chan_strategy/` or `diagnostics/`. Do NOT implement Phase 2. Do NOT touch the existing
   `NotImplementedError` gate in `portfolio_engine.py:610-615`.
4. Bump VERSION/CHANGELOG for this documentation-only change (house convention: every user-visible
   change gets a VERSION bump + CHANGELOG entry, including pure design-doc additions that are
   significant enough to warrant one — this qualifies since it's the accepted algorithm boundary for a
   future Phase 2 implementation).

## Acceptance Criteria

- [ ] Every code reference (file:line, config key name) in `docs/design/a85-joint-replay-design.md` is
      verified accurate against the current codebase; any drift is corrected.
- [ ] Each of the 5 design areas (joint clock, shared ledger, open-gating, execution ordering, test
      matrix) states a concrete decision with a reason — no unresolved "option A or option B" left.
- [ ] No production code changed in `chan_strategy/` or `diagnostics/`.
- [ ] No changes to the existing `NotImplementedError` gate or any existing test's assertions.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes unchanged (this
      change should not affect any test outcome, since no code changed).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] VERSION/CHANGELOG bumped for this documentation-only addition.
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **There is no code to write.** Your job is fact-checking and tightening a document
   claude-code already wrote, plus the routine VERSION/CHANGELOG/test-gate bookkeeping. Do not
   interpret "dev stage" as license to start implementing Phase 2 — the user was explicit that A85 is
   design-only.
2. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to a
   concurrent, unrelated SimNow-observation workstream. **Before committing, run `git status --short`
   and confirm only your own A85-scoped files are staged.**
3. **Include a literal `## Manual Verification` heading** — A77's first review round was rejected purely
   for lacking this literal heading despite the content existing elsewhere. Do not repeat that mistake.
4. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A85 joint-replay design verified/finalized"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. After review passes, this design
   becomes the accepted algorithm boundary for a future Phase 2 implementation task (not yet scheduled;
   the user will decide when to open it).

## Decision Log

- 2026-07-16 - Phase-2-readiness confirmation audit (triggered after A84) returned READY WITH CAVEATS:
  no blocking issue, one cosmetic mojibake placeholder in Markdown output (non-blocking, user said fold
  it in opportunistically later, not a dedicated task), and the key caveat that A83/A84 verify
  per-symbol lot/margin/PnL inputs and correct summation only — not a validated joint-replay algorithm.
- 2026-07-16 - User reviewed the caveat and explicitly ruled: proceed to A85, but A85 must be a
  design-only task (algorithm boundary document), not a Phase 2 implementation task. User specified the
  five required design areas (joint clock, shared ledger state, open-gating semantics, execution
  ordering, test matrix) and named the task "A85: Joint Replay + Shared PortfolioLedger Design."
- 2026-07-16 (claude-code, design stage) - Wrote `docs/design/a85-joint-replay-design.md` covering all
  five areas with concrete decisions grounded in current code (`PortfolioEngine._run_per_symbol()`,
  `PortfolioCoordinator.allow_open()`/`on_bar()`/`_flatten_all()`, `_trading_day()`, A83's forward-fill/
  cluster-case fixes). Key decisions: outer-join timestamp union as joint clock with no signal
  forward-fill (only valuation forward-fill within a symbol's own range); a `PortfolioLedger` state
  object updated once per tick in a fixed order (day rollover → per-symbol valuation → aggregation →
  daily-loss-limit check/flatten → close-then-open signal processing); hard-reject gating (no queueing/
  partial fills) for total-margin/per-symbol-margin/cluster caps, with daily-loss-limit retaining the
  existing flatten-all action (not "block-only") since that is the only path the current code already
  implements — deferring "block vs flatten" as a Phase 3 product decision, per
  `portfolio-risk-fusion-design.md`'s existing staging; deterministic dictionary-order tie-breaking for
  same-tick signal execution (chosen over business-priority ordering specifically to avoid inventing an
  unvalidated priority scheme); a 10-item test matrix covering all 7 scenario classes the user named.
  Explicitly out of scope: Phase 3 circuit-breaker action decision, external-data-dependent limitations
  (continuous-contract splice, settlement limit bands), and the implementation itself.

## Manual Verification

```text
$ python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
729 passed, 4 deselected in 31.61s

$ python tools/sync_check.py
[SYNC-CHECK] 配置: D:\repo\vnpy\.synccheck.yml
[SYNC-CHECK][OK] 版本单一真相 = 4.4.0  (source: vnpy/__init__.py::__version__)
[SYNC-CHECK][WARN] archive_dir 不存在: docs/archive/（仅提示，不 FAIL）
[SYNC-CHECK] PASS: 版本与文档一致。

$ python tools/sync_check.py --root examples/czsc_strategy
[SYNC-CHECK] 配置: D:\repo\vnpy\examples\czsc_strategy\.synccheck.yml
[SYNC-CHECK][OK] 版本单一真相 = 0.2.21  (source: VERSION::)  # synccheck:ignore
[SYNC-CHECK] PASS: 版本与文档一致。

$ cd examples/czsc_strategy/diagnostics; .\run_next_work.ps1 -Preflight
==> Compile SimNow capture script
==> Run SimNow workflow unit tests
191 passed in 17.16s
==> Build pending replay backfill plan
{"execute": false, ...}
==> Preflight complete; live SimNow capture was not requested
```

备注：`run_next_work.ps1` 位于 `examples/czsc_strategy/diagnostics/`（当前工作树中 SimNow
观察工作流的未提交文件），本 A85 任务未改动该文件；Preflight 结果仅作状态记录。

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-16 | claude-code → kimi-code | design → dev | A85 (joint-replay design doc) promoted for verification/finalization; handoff design->dev |
| 2026-07-16 | kimi-code → codex | dev → review | A85 joint-replay design verified/finalized; VERSION/CHANGELOG bumped; manual transition due to shell crash |
