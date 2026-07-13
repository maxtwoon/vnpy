---
task: A59 - Limit-Band Basis Accuracy
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-14
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

Fifth task of the 2026-07-13 post-remediation re-audit roadmap
(`docs/design/a55-post-remediation-audit-roadmap.md` §"A59"), promoted immediately after A58
reached `done` (codex accepted on the first review round).

`docs/review/ai_trading_review_2026-07-13.md` Finding 🟠#6 (re-verified 2026-07-14 by claude-code):
three undocumented simplifications in the A50/A51 limit-band computation, plus one directional gap:

1. **Night-session pollution**: `_daily_prev_close_map`'s `_bar_date`
   (`chan_strategy/limit_config.py:58-86`) buckets bars by *calendar* date. RB/SC's 21:00-23:00
   night-session bars belong to the *next trading day* per exchange convention, but get bucketed
   into the current calendar day — "previous close" can self-referentially include same-evaluation
   -day night-session bars. A39 already solved exactly this class of problem
   (`daily_agg="trading_calendar"`/`night_session_start_hour`); reuse it, do not reimplement.
2. **Settlement-vs-close basis**: `SYMBOL_LIMIT_CONFIG`'s cited sources say "previous trading day's
   **settlement price** ± x%"; the implementation uses the last bar's close. Acknowledged in
   methodology text but never quantified.
3. **Temporary widening windows undocumented**: AP888/RB888 had exchange-notice limit widenings
   inside the A50/A51 measurement window — **see the "IMPORTANT — citation caveat" note below
   before hardcoding these dates.**
4. **No directional distinction**: `_bar_at_limit` (`limit_config.py:94-105`) returns a single
   `at_limit` bool without distinguishing upper-touch (limit-up) from lower-touch (limit-down), so
   a long open on a limit-down bar (genuinely unexecutable in that direction) and a long open on a
   limit-up bar get identical tags.

**IMPORTANT — citation caveat, read before touching the widening-window registry:** the specific
dates/percentages ("RB888 to 5% effective 2026-05-19, AP888 to 8% effective 2026-05-06") come from
`git show 4b228834:HANDOFF.md` (A50's own completion record) — claude-code's live web search
*during that earlier task*, worded with **"presumably"** ("both presumably following limit-hit
days, per the standard CZCE/SHFE escalation mechanism"). **This is NOT a verified primary-source
exchange-notice citation** — it is a plausible secondary observation from a web search, not a
document number. Do NOT invent or fabricate a specific exchange announcement number to make the
registry entry look more authoritative than it is. If you (kimi-code) have no way to independently
re-verify this against a primary source in this session, register the entry with an honest
citation along the lines of: `"source": "claude-code 2026-07-13 web search during A50 review (see
HANDOFF commit 4b228834); not independently verified against a primary exchange notice — flagged
for human confirmation"`. This is more honest than a confident-sounding fake citation and satisfies
the "every entry must carry a citation" bar by being truthful about the citation's actual strength.

Full contract: `docs/design/a55-post-remediation-audit-roadmap.md` §"A59 — Limit-Band Basis
Accuracy" (the authoritative design — this HANDOFF summarizes it).

## Goal

1. **Reuse A39's trading-calendar logic, do not reimplement.** Two existing helpers already solve
   "map a bar timestamp to its trading day": `data_adapter.py`'s `_trading_day_for_bar` (the
   original A39 implementation — more rigorous, needs a `trading_dates` set + a `notes` list) and
   `portfolio_engine.py`'s `_trading_day` (A48's lighter reuse — just `dt.date() + 1` when
   `dt.hour >= night_session_start_hour`, no `trading_dates` set needed). **Prefer
   `portfolio_engine.py`'s `_trading_day`** for `_daily_prev_close_map`'s bucketing: it needs no new
   inputs `limit_config.py` doesn't already have (bars only, no separate trading-dates set), and its
   simpler night-session-only rule is what this bug actually needs (bars fed into
   `_daily_prev_close_map` are already trading-day data, not raw calendar data with gaps to skip).
   Import it explicitly; do not copy its logic into a third implementation.
2. **Add a cited, dated temporary-widening-window registry** to `SYMBOL_LIMIT_CONFIG` for AP888 and
   RB888, per the citation caveat above. Structure: a list of `{start_date, end_date, limit_pct,
   source}` overrides per symbol, falling back to the steady-state percentage outside any
   registered window.
3. **Make `_bar_at_limit` return a directional result** (e.g. `(touched_upper, touched_lower)`
   instead of one bool), and have `backtest_engine.py`'s entry/exit tagging consume the direction
   that matters for that side of the trade. Decide and document the exact semantic during this
   task (e.g., for a long position, a limit-up touch on entry is the adverse/unexecutable direction
   for opening favorably, while a limit-down touch is the more typical "can't get filled" case —
   work out which direction each of entry/exit for long/short actually cares about; this is a
   judgment call, document your reasoning in the Decision Log).
4. **Quantify the settlement-vs-close gap** for the 5 default symbols — a short, read-only
   measurement (not a full settlement-price data-sourcing project). Report the finding even if the
   conclusion is "gap is small/immaterial" — that must be a measured conclusion, not an assumption.

## Acceptance Criteria

- [x] A fixture with a night-session bar proves `_daily_prev_close_map` no longer includes
      same-evaluation-day night-session data in "previous close" (unit-tested, mirroring A39's own
      night-session test pattern in `test_data_adapter.py`).
- [x] AP888 and RB888's known temporary-widening windows are registered with the honest citation
      described above; a fixture proves a date inside the window uses the overridden percentage, a
      date outside uses the steady-state percentage.
- [x] `_bar_at_limit`'s directional result is unit-tested for both upper-touch and lower-touch
      cases, and the entry/exit consumption logic correctly maps direction to trade side (documented
      reasoning in the Decision Log for which direction matters for which side).
- [x] The settlement-vs-close gap for the 5 default symbols is measured and reported (even a "gap is
      immaterial" conclusion must show the actual measurement, not just assert it).
- [x] `limit_halt_model="off"` equivalence test (`test_limit_halt_off_equivalence.py`) still passes
      byte-identical.
- [x] No threshold tuning; no pre-2026-04-24 data used for any NEW parameter choice (the widening
      windows are historical facts being registered, not tuned parameters); no SimNow order/cancel/
      send path changed; no `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a55-post-remediation-audit-roadmap.md` §"A59". Fifth task of the
   A55-A60 roadmap triaging `docs/review/ai_trading_review_2026-07-13.md`'s finding #6 (🟠 medium).
2. **Scope:** `chan_strategy/limit_config.py` (`_daily_prev_close_map` bucketing,
   `SYMBOL_LIMIT_CONFIG` widening registry, `_bar_at_limit` directional return) and
   `chan_strategy/backtest_engine.py` (consume the directional result correctly at the two call
   sites added by A57, around line 314-326). Do not touch `sizing_model`, `portfolio_engine.py`, or
   anything from A55-A58's already-`done` scope.
3. **Read the citation caveat in Background above carefully before writing the widening registry.**
   Do not invent a fake exchange-notice document number. Honesty about the citation's actual
   strength (a secondary web-search observation, not a primary document) is required, not optional.
4. **Test file:** `tests/unit/test_limit_halt_aware.py` already exists for limit/halt tagging tests;
   consider whether the night-session/trading-calendar test fits better alongside
   `test_data_adapter.py`'s existing night-session tests (mirror that pattern) since it's really
   testing `_daily_prev_close_map`'s date bucketing, not the tagging logic itself. Use your
   judgment; do not create a third duplicate test file for the same concern.
5. **Settlement-vs-close measurement**: this can be a small standalone script under `diagnostics/`
   (with the RESEARCH-ONLY banner — reuse `declassify_historical_reports.build_banner()`, the
   A56-fixed pattern, if you add a new report generator) or a one-off computation reported directly
   in this HANDOFF's Decision Log if a full report script feels like overkill for "measure one gap
   number for 5 symbols." Your call, but the measurement must be real and reproducible, not a guess.
6. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection; no
   pre-2026-04-24 data for any NEW parameter choice (the widening dates are historical facts being
   registered, not tuned); no SimNow order/cancel/send paths touched; no `GOAL PASSED`;
   `limit_halt_model="off"`'s existing equivalence snapshot must stay byte-identical; do not
   fabricate a citation.
7. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing.**
8. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A59 limit-band basis accuracy implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-14 - A59 promoted from `docs/design/a55-post-remediation-audit-roadmap.md`'s draft to an
  active HANDOFF task, started immediately after A58 reached `done` (codex accepted on the first
  review round).
- 2026-07-14 - claude-code re-verified `limit_config.py`'s current implementation matches the
  audit's description (line numbers shifted slightly since A57's edits but structurally unchanged).
  Found two existing "map bar to trading day" helpers (`data_adapter.py`'s
  `_trading_day_for_bar`, `portfolio_engine.py`'s lighter `_trading_day`) and directed dev to prefer
  the latter since it needs no new inputs. Traced the temporary-widening-window dates/percentages
  to A50's own completion record (`git show 4b228834:HANDOFF.md`) and found they are a web-search
  observation worded with "presumably," NOT a verified primary-source exchange notice — flagged
  this explicitly so dev does not fabricate a more confident-looking citation than the evidence
  actually supports.
- 2026-07-14 - kimi-code reused `portfolio_engine._trading_day` inside
  `limit_config._daily_prev_close_map` (local import to break the backtest_engine <->
  portfolio_engine cycle) so night-session bars are bucketed by exchange trading day, fixing the
  same-evaluation-day night-session pollution.
- 2026-07-14 - kimi-code added `temporary_widening_windows` entries for AP888 (2026-05-06 → 8%)
  and RB888 (2026-05-19 → 5%) with the honest secondary-source citation required by the caveat
  above. `_limit_pct_for_date` selects the override when a bar's trading day falls inside the
  registered window and falls back to the steady-state percentage otherwise.
- 2026-07-14 - kimi-code changed `_bar_at_limit` to return `(touched_upper, touched_lower, upper,
  lower)`. The entry/exit consumption maps the touch that matters for each side:
  * Long entry: upper touch is adverse (cannot buy favorably at limit-up).
  * Short entry: lower touch is adverse (cannot sell favorably at limit-down).
  * Long exit: lower touch is adverse (cannot sell to close at limit-down).
  * Short exit: upper touch is adverse (cannot buy to cover at limit-up).
  `positions.py` now interprets the `(upper, lower)` tuple per side; legacy callers that pass a
  plain bool still work unchanged.
- 2026-07-14 - Settlement-vs-close gap was measured with the post-2026-04-24 window
  (2026-05-01 ~ 2026-07-13) using a last-30-minute VWAP proxy for settlement (the database has no
  official settlement column). Mean absolute gaps were well under 0.13% for all five symbols and
  ≤50 bp on every observed day, so the gap is immaterial under this proxy. A definitive
  primary-source measurement would require an official settlement-price field.

## Manual Verification

```text
python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"
586 passed, 4 deselected in 31.46s

ruff check on A59-changed files (limit_config.py, backtest_engine.py,
test_limit_halt_aware.py, test_limit_halt_exposure_report.py,
limit_halt_exposure_report.py, settlement_close_gap_report.py): pass

python tools/sync_check.py
[SYNC-CHECK] PASS: 版本与文档一致。

python tools/sync_check.py --root examples/czsc_strategy
[SYNC-CHECK] PASS: 版本与文档一致。

diagnostics\run_next_work.ps1 -Preflight
==> Preflight complete; live SimNow capture was not requested
```

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-14 | codex → claude-code | done → dev | A59 (limit-band basis accuracy) promoted from post-remediation audit roadmap; handoff design->dev |
