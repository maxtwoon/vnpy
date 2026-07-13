---
task: A56 - structural_atr Profit-Protection Gap: Decide and Document
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-13
deliverables:
  - HANDOFF.md
  - docs/design/a55-post-remediation-audit-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

Second task of the 2026-07-13 post-remediation re-audit roadmap
(`docs/design/a55-post-remediation-audit-roadmap.md` §"A56"), promoted immediately after A55
(partial-TP transaction-cost double-scaling fix) reached `done` with a clean, one-round codex
acceptance.

`docs/review/ai_trading_review_2026-07-13.md` Finding 🟠#2 (re-verified 2026-07-13 by claude-code
against current code, confirmed no line drift beyond a 3-line shift from A55's own edits):
`Position.update`'s `exit_model="structural_atr"` branch (`chan_strategy/positions.py:677-699`)
is an `elif` chain — `elif not self._partial_tp_done: ... (try partial TP) ... elif
self._check_atr_trailing_stop(price, atr): ...` — so `_check_atr_trailing_stop` is only ever
reached once `self._partial_tp_done is True`. A49 fixed the specific bug where a lot-floor skip
left this flag permanently `False`; it did not change the underlying structural fact that ATR
trailing is gated behind partial-TP firing at all. A position whose directional target (the
partial-TP trigger condition) never fires has **zero profit-side protection** for its entire life
under `structural_atr` — only the fixed stop-loss and timeout remain — a materially different risk
profile from `"legacy"`'s percentage-giveback trailing (active from the moment `trailing_start` is
crossed, independent of any other event). Neither `config.py`'s `exit_model` comment nor the
original A47 design document states this difference.

Full contract: `docs/design/a55-post-remediation-audit-roadmap.md` §"A56 — `structural_atr`
Profit-Protection Gap: Decide and Document" (the authoritative design — this HANDOFF summarizes
it).

## Goal

**This task requires a design decision BEFORE any code is written**, then implementation of
whichever option is chosen:

- **Option A** (behavior change): make ATR trailing independent of `_partial_tp_done` — evaluate
  `_check_atr_trailing_stop` every bar regardless of partial-TP state, with partial-TP becoming an
  additional, non-blocking action rather than a prerequisite. Requires a new equivalence test
  proving `exit_model="legacy"` stays byte-identical, plus a fresh `exit_model_report.py`
  before/after comparison reported honestly (not framed as an improvement claim).
- **Option B** (documentation-only): leave the `elif` chain exactly as-is; add an explicit,
  prominent disclosure in three locations — `config.py`'s `exit_model` comment, the A47 design
  section of `docs/design/a38-phase-contracts-p2-p8.md` (a dated addendum, do not rewrite history),
  and `diagnostics/exit_model_report.py`'s Methodology text — stating plainly that ATR trailing is
  not active until a partial take-profit event has fired, and positions that never reach a
  directional target rely solely on the fixed stop-loss and timeout.

## Design-step pre-analysis (claude-code, 2026-07-13 — evidence for dev to weigh, NOT a
pre-made decision; dev must still read the cited source and record its own reasoned conclusion in
the Decision Log before writing any code)

Re-read `docs/design/a38-phase-contracts-p2-p8.md` lines 520-526 (P8a's own "### Semantics" text,
the original, unedited A47 design intent):

> "**P8a - exits (`"structural_atr"`):** replace the profit-side fixed-giveback trailing with an
> ATR trailing stop (`trail = peak - atr_trail_mult * ATR`), keep the structural stop (center
> break) as the hard structural exit, and **add a partial take-profit: scale out
> `partial_tp_frac` of the position at the next center boundary / measured target, then trail the
> remainder.**"

The phrase "**then trail the remainder**" is sequential, not concurrent — it describes partial-TP
firing as a precondition for trailing to begin, matching the current `elif` chain's actual
behavior exactly. There is no language anywhere in P8a about trailing being active "from open" or
protecting the whole position before any target is reached (contrast with `"legacy"`'s own
described behavior elsewhere in the codebase, which IS active from `trailing_start`). This reads
as evidence for **Option B** — the current gating appears to match original intent, just
undocumented — but dev should form its own judgment from the full source text (already quoted
above in full) rather than taking this paraphrase as the final word, and should also check
whether any later design note (A49-A54 HANDOFF Decision Log entries, if any touch this) added
context this excerpt doesn't capture.

## Acceptance Criteria

- [ ] A clear, recorded design decision (Option A or B) with rationale citing A47's original
      intent (the P8a excerpt above, or dev's own re-reading of it), documented in this task's own
      HANDOFF Decision Log **before any code is written**.
- [ ] If Option A: `exit_model="legacy"` byte-identical (existing equivalence test unaffected); a
      new test proves ATR trailing now fires even when no partial-TP event has occurred; the
      `exit_model_report.py` comparison is re-run and the before/after behavior change for
      `structural_atr` is reported honestly (not framed as an improvement claim).
- [ ] If Option B: the documentation change is present in all three locations (config.py comment,
      `a38-phase-contracts-p2-p8.md` dated addendum, `exit_model_report.py` Methodology text); no
      code/test changes; existing test suite untouched.
- [ ] No threshold tuning; no pre-2026-04-24 data used for any parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a55-post-remediation-audit-roadmap.md` §"A56". Second task of the
   A55-A60 roadmap triaging `docs/review/ai_trading_review_2026-07-13.md`'s findings — read that
   report's finding #2 (🟠 medium) for full context.
2. **Do the decision step first, literally before writing any code.** Re-read
   `docs/design/a38-phase-contracts-p2-p8.md` lines 509-526 (P8a's full Semantics text) yourself —
   don't just trust this HANDOFF's excerpt. This HANDOFF's "Design-step pre-analysis" section above
   leans toward Option B based on the "then trail the remainder" phrasing, but you are the one who
   must record the final reasoned decision in the Decision Log, citing the source text, before
   touching `positions.py` or `config.py`.
3. **Scope:** `chan_strategy/positions.py:677-699` (`Position.update`'s `structural_atr` branch)
   if Option A; `chan_strategy/config.py`, `docs/design/a38-phase-contracts-p2-p8.md`,
   `diagnostics/exit_model_report.py` if Option B. Do not touch `exit_model="legacy"`'s own
   trailing logic, `sizing_model`, `limit_halt_model`, `rollover_stat_tagging`, or any P8b/
   portfolio code either way.
4. **If Option A is chosen, it is a real behavior change** — do not retune `atr_trail_mult`/
   `partial_tp_frac`'s values, only change *when* the trailing check is evaluated. A fresh
   `exit_model_report.py` before/after run is mandatory and must be reported as honest measurement,
   never as a superiority/profitability claim (RESEARCH-ONLY banner still applies).
5. **If Option B is chosen, do not skip any of the three documentation locations** — reviewer will
   check all three. Editing `docs/design/a38-phase-contracts-p2-p8.md` should be a dated addendum
   (e.g. "**2026-07-13 addendum (A56):** ..."), not a rewrite of the original P8a text, to preserve
   the historical record of what was originally specified vs. later clarified.
6. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; `exit_model="legacy"` provably untouched either way.
7. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing** — this consistently correlates with one-round review acceptance
   across the A49-A54 and A55 rounds.
8. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A56 structural_atr profit-protection gap: <Option A|B> implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-13 - A56 promoted from `docs/design/a55-post-remediation-audit-roadmap.md`'s draft to an
  active HANDOFF task, started immediately after A55 reached `done` with a clean one-round codex
  acceptance.
- 2026-07-13 - Re-verified the `elif` chain's current location (`positions.py:677-699`, shifted
  from the roadmap doc's cited `688-698` by A55's own unrelated edits earlier in the file) and
  confirmed the structural gating behavior is unchanged since the audit.
- 2026-07-13 - claude-code (design step) re-read `docs/design/a38-phase-contracts-p2-p8.md`'s P8a
  Semantics text in full and found the phrase "add a partial take-profit: scale out
  `partial_tp_frac` of the position at the next center boundary / measured target, **then trail the
  remainder**" — sequential phrasing consistent with the current `elif` gating, leaning toward
  Option B (documentation-only). This is presented as evidence for dev's own decision, not a
  pre-made call — dev must independently confirm and record the final decision before writing code,
  per the roadmap's own dev-prompt requirement.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-13 | codex → claude-code | done → dev | A56 (structural_atr profit-protection gap) promoted from post-remediation audit roadmap; handoff design->dev |
