---
task: A95 - Document risk_per_trade_pct as a nominal budget, not a hard loss cap (audit M1)
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-21
deliverables:
  - HANDOFF.md
  - examples/czsc_strategy/chan_strategy/config.py
  - examples/czsc_strategy/chan_strategy/positions.py
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

`diagnostics_ai_stock_review_report.md` (2026-07-21 full project audit) flagged **M1**:
`_size_open()` (`positions.py:1013-1050`) sizes an integer lot count by dividing a fixed risk budget
(`equity * risk_per_trade_pct`, `risk_per_trade_pct` defaults to `0.005` = 0.5% of equity, `config.py:87`)
by `stop_distance` (the position's own fixed stop-loss distance in price terms). This closes the loop
correctly ONLY for the specific exit path "position hits its own fixed stop-loss" — actual exits can also
happen via structural-failure signals, timeout, or an overnight gap that jumps past the stop price
(`stop_execution_model="intrabar"` partially models gap-through via `min(trigger, close)`, `positions.py:
904-906`, but this still isn't a hard cap), all of which can realize a loss materially larger than the
nominal 0.5% budget. This is not a bug — the sizing math is internally correct for what it actually
computes — but the naming/documentation implies a guarantee ("risk per trade") that the mechanism does not
actually provide. A reader could reasonably believe 0.5% is the worst-case per-trade loss, when it is only
the loss-if-stopped-out-exactly-at-the-stop-price case.

## Goal

**This is a documentation-only clarification — no code logic changes.** claude-code confirmed via `grep`
that `risk_per_trade_pct` is referenced in exactly two production-code places
(`config.py:87`'s inline comment, `positions.py:1030`'s read) plus one historical evidence document
(`diagnostics/joint_replay_acceptance_2026-07-17.md:143` — do NOT touch that file, it's a frozen
acceptance artifact, not documentation to update).

1. Update the inline comment at `config.py:87` (currently
   `"fraction of equity risked per trade (0.5%)"`) to make explicit that this is a **nominal** budget based
   on the stop-loss distance, not a guaranteed maximum loss — actual realized loss on a given trade can
   exceed it via non-stop-loss exit paths (structural-failure exit, timeout exit, or a gap-through the stop
   price). Keep it concise (this is a config dict inline comment, not a paragraph), but the "nominal, not a
   hard cap" fact must be stated, not just implied.
2. Add a short clarifying note to `_size_open()`'s docstring (`positions.py:1013-1016`) stating the same
   thing in slightly more detail — this is the function a future maintainer is most likely to read when
   trying to understand what "risk per trade" actually guarantees. Reference the specific non-stop-loss
   exit paths that can exceed the budget (structural failure, timeout, gap-through) so the docstring is
   concrete, not just a vague disclaimer.
3. **Do not change `_size_open()`'s actual sizing formula, the `stop_execution_model="intrabar"` gap
   handling, or any other logic in `positions.py`.** This task is documentation only.
4. If you find any other production-code comment or docstring (outside the two locations above) that
   implies `risk_per_trade_pct` is a hard cap rather than a nominal budget, fix it too and note where in
   the Decision Log — but don't go looking in unrelated files/docs beyond a reasonable grep for the config
   key name and its common synonyms (e.g. "risk per trade", "风险预算").

## Acceptance Criteria

- [ ] `config.py:87`'s comment explicitly states `risk_per_trade_pct` is a nominal budget, not a
      guaranteed maximum loss.
- [ ] `_size_open()`'s docstring explains why actual loss can exceed the nominal budget, naming the
      specific non-stop-loss exit paths that can do so.
- [ ] No change to any function's logic, to any config default value, or to any test's assertions.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes, exact same pass
      count as before this change.
- [ ] `-m realdb` equivalence gate still passes unchanged (comment-only change, but this task touches
      `positions.py` again — verify rather than assume, same discipline as A94).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy` pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.
- [ ] `ruff check` clean on touched files.
- [ ] VERSION/CHANGELOG bumped, with a note in the CHANGELOG entry summarizing the documentation
      clarification (not just "docs updated" — state what was clarified, per this project's CHANGELOG
      convention of being specific).
- [ ] Include a literal `## Manual Verification` heading with natively-run command output.
- [ ] **Remember the `synccheck:ignore` marker**: any HANDOFF.md line mentioning this task's own new
      VERSION number (a version-like string not matching the true root version) needs the literal
      `<!-- synccheck:ignore -->` marker on that same line, or `tools/sync_check.py` (root) will fail. This
      has bitten nearly every task in this session — do not repeat it.

## Notes for the Next Agent

(dev = kimi-code must read this before starting)

1. **This is a small documentation task, same shape as A94** — two comment/docstring edits, no logic
   changes. Do not use this as an opportunity to add a real hard-cap enforcement mechanism (e.g. a
   post-hoc loss-limit check) — that would be a real behavior change requiring its own design and
   real-data validation, not something to bundle into a documentation task.
2. **Do not touch `diagnostics/joint_replay_acceptance_2026-07-17.md`** — it's a frozen, already-reviewed
   acceptance artifact from A88; even though it mentions `risk_per_trade_pct`, editing a historical
   evidence document after the fact would misrepresent what was actually verified at the time.
3. **Do not touch the unrelated files currently sitting modified in the working tree**
   (`diagnostics/ACCEPTANCE.md`, `AUTOMATION_PROMPT.md`, `NEXT_WORK.md`, `WORK_LOG.md`,
   `run_next_work.ps1`, `simnow_20d_promotion_decision.md`,
   `tests/unit/test_run_next_work_wrapper.py`, `tests/unit/test_simnow_docs.py`) — these belong to a
   concurrent, unrelated SimNow-observation workstream. **Before committing, run `git status --short`
   and confirm only your own A95-scoped files are staged.**
4. **Include a literal `## Manual Verification` heading** — required every time; do not omit it.
5. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A95 risk_per_trade_pct nominal-budget documentation completed"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`. If the command itself crashes/times
   out for environment reasons (this has happened repeatedly on this machine, apparently correlated with
   the pipeline's timeout landing right at the finish line), do not manually hand-edit HANDOFF.md's
   stage/owner fields to bypass it — leave the working tree with your changes uncommitted and note the
   failure in the Decision Log; claude-code will verify and commit properly.

## Decision Log

- 2026-07-21 - Continuing the M-series from the audit report after M4 (A94) closed. This task (A95) is
  M1, chosen next for being another small documentation-only item (same shape/risk as A94).
- 2026-07-21 (claude-code, design) - Confirmed via grep that `risk_per_trade_pct` appears in exactly two
  production-code locations (`config.py:87`, `positions.py:1030`) plus one frozen historical evidence
  document (`diagnostics/joint_replay_acceptance_2026-07-17.md`, explicitly excluded from this task's
  scope). Scoped the fix to comment/docstring clarification only, matching the audit's own recommendation
  ("应在文档中明确其名义属性").
- 2026-07-21 (kimi-code, dev) - Implemented exactly as scoped: rewrote the `config.py:87` inline comment
  to state `risk_per_trade_pct` is a NOMINAL risk budget (sized off stop-loss distance), not a guaranteed
  max loss, naming the three non-stop exit paths; added a Note paragraph to `_size_open()`'s docstring
  explaining the same with concrete exit paths (structural failure, timeout, gap-through incl. the
  `intrabar` `min(trigger, close)` partial modeling). Independent grep for `risk_per_trade|risk per
  trade|风险预算|每笔风险` found no other production-code comment implying a hard cap (test files only
  read the value / assert the default — untouched per scope). No logic, default, or test changes.
  VERSION bumped to 0.2.33 with a specific CHANGELOG entry. <!-- synccheck:ignore -->
- 2026-07-21 (kimi-code, dev) - `run_next_work.ps1` lives under `examples/czsc_strategy/diagnostics/`,
  not directly under `examples/czsc_strategy/`; ran Preflight from there (passed).
- 2026-07-21 (kimi-code, dev) - One background pytest invocation (not-realdb + realdb chained) hit the
  60s default background timeout after the not-realdb half completed (761 passed); reran `-m realdb`
  separately with an explicit longer timeout — 4 passed, 761 deselected, equivalence gate green. No
  hand-editing of stage/owner fields involved.

## Manual Verification

All commands run natively on this machine (Windows PowerShell, repo root `D:\repo\vnpy` unless noted).

```text
# 1. Baseline unit tests (before edits)
PS> cd examples/czsc_strategy; python -m pytest tests/unit -q -m "not realdb"
761 passed, 4 deselected in 42.50s

# 2. Post-change unit tests (identical pass count)
PS> cd examples/czsc_strategy; python -m pytest tests/unit -q -m "not realdb"
761 passed, 4 deselected in 42.42s

# 3. realdb equivalence gate
PS> cd examples/czsc_strategy; python -m pytest tests/unit -q -m "realdb"
4 passed, 761 deselected in 79.47s (0:01:19)

# 4. ruff on touched files
PS> cd examples/czsc_strategy; ruff check chan_strategy/config.py chan_strategy/positions.py
All checks passed!

# 5. sync_check (root + czsc_strategy)
PS> python tools/sync_check.py
[SYNC-CHECK][OK] 版本单一真相 = 4.4.0  (source: vnpy/__init__.py::__version__)
[SYNC-CHECK] PASS: 版本与文档一致。
PS> python tools/sync_check.py --root examples/czsc_strategy
[SYNC-CHECK][OK] 版本单一真相 = 0.2.33  (source: VERSION::)  <!-- synccheck:ignore -->
[SYNC-CHECK] PASS: 版本与文档一致。

# 6. Preflight (script lives under diagnostics/)
PS> cd examples/czsc_strategy/diagnostics; powershell -ExecutionPolicy Bypass -File .\run_next_work.ps1 -Preflight
200 passed in 23.74s
==> Preflight complete; live SimNow capture was not requested

# 7. Working tree scope check — only A95 files modified
PS> git status --short
 M examples/czsc_strategy/CHANGELOG.md
 M examples/czsc_strategy/VERSION
 M examples/czsc_strategy/chan_strategy/config.py
 M examples/czsc_strategy/chan_strategy/positions.py
 M HANDOFF.md  (this file's own dev-stage update)
```

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-21 | claude-code → kimi-code | design → dev | A95 (document risk_per_trade_pct nominal budget, audit M1) promoted; handoff design->dev |
| 2026-07-21 | kimi-code → codex | dev → review | A95 risk_per_trade_pct nominal-budget documentation completed |
