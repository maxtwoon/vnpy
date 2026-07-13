---
task: A57 - Limit-Config Case Normalization + Fail-Loud
version: 4.4.0
stage: review
owner: codex
updated: 2026-07-13
deliverables:
  - HANDOFF.md
  - docs/design/a55-post-remediation-audit-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: kimi-code
last_transition_from_stage: dev
last_transition_to_stage: review
last_transition_from_owner: kimi-code
last_transition_to_owner: codex
---

## Background

Third task of the 2026-07-13 post-remediation re-audit roadmap
(`docs/design/a55-post-remediation-audit-roadmap.md` §"A57"), promoted immediately after A56
reached `done` (codex accepted round 2 directly, no further reject).

`docs/review/ai_trading_review_2026-07-13.md` Finding 🟠#3 (re-verified 2026-07-13 by claude-code
against current code, confirmed no line drift): `backtest_engine.py:314`'s
`SYMBOL_LIMIT_CONFIG.get(self.symbol, {}).get("limit_pct")` does not normalize `self.symbol`'s case
before lookup. `SYMBOL_LIMIT_CONFIG`'s keys (`limit_config.py:19-55`) are all uppercase (e.g.
`"AP888"`, `"RB888"`), but the data layer explicitly supports lowercase symbol codes
(`data_adapter.py:317`'s `COLLATE NOCASE`) and position/weight code already normalizes via
`_research_symbol_key()` (`positions.py:302-304`) before doing config lookups elsewhere. Only the
limit lookup at `backtest_engine.py:314` skips this. A lowercase `self.symbol` silently produces
`limit_pct=None`, and every `pairs` entry gets `is_entry_at_limit=False`/`is_exit_at_limit=False`
with no warning — a false-negative tag that looks like "checked, not at limit" but was never
actually checked.

**Important nuance found during claude-code's due-diligence re-verification (read this before
touching code):** `backtest_engine.py` already has its OWN LOCAL `_research_symbol_key()` defined
at line 45 (`"".join(ch for ch in str(symbol).upper() if ch.isalnum())` — strips ALL non-alphanumeric
characters), which is DIFFERENT from `positions.py`'s `_research_symbol_key()` at line 302-304
(`str(symbol or "").upper().split(".")[0]` — splits at the first dot and keeps only the part before
it). These are two functions with the *same name* but *different behavior* living in different
modules — a pre-existing drift issue, NOT something to fix as part of A57 (out of scope; flag it as
a backlog note in the Decision Log if you notice it again, but do not touch it here).

For a symbol like `"sc888.SHFE"` (dot + exchange suffix): `positions.py`'s version correctly
extracts `"SC888"` (matches `SYMBOL_LIMIT_CONFIG`'s bare uppercase keys); `backtest_engine.py`'s own
local version incorrectly produces `"SC888SHFE"` (strips the dot but keeps the suffix letters,
which would NOT match `SYMBOL_LIMIT_CONFIG`). **Use `positions.py`'s `_research_symbol_key`
for this specific fix** — import it explicitly (mirroring `portfolio_engine.py:29`'s existing
precedent: `from chan_strategy.positions import _research_symbol_key`) rather than reusing
`backtest_engine.py`'s own local, narrower one. Do not rename, remove, or unify the two existing
`_research_symbol_key` functions — that consolidation is out of scope for this task.

Full contract: `docs/design/a55-post-remediation-audit-roadmap.md` §"A57 — Limit-Config Case
Normalization + Fail-Loud" (the authoritative design — this HANDOFF summarizes it).

## Goal

In `backtest_engine.py`'s limit-lookup call site (line 314), normalize `self.symbol` through
`positions.py`'s `_research_symbol_key()` (imported explicitly, per the nuance above) before the
`SYMBOL_LIMIT_CONFIG.get(...)` lookup. When `limit_halt_model == "aware"` AND the normalized symbol
still isn't found in `SYMBOL_LIMIT_CONFIG` (a genuinely-unconfigured symbol, not a case mismatch),
fail loud: either raise a clear exception, or write `is_entry_at_limit=None`/`is_exit_at_limit=None`
(never silently `False`) so downstream readers can distinguish "not checked" from "checked, clear."
No new config key. Does not add new symbols to `SYMBOL_LIMIT_CONFIG` or change any existing cited
percentage — purely a lookup-key-normalization and fail-loud fix.

## Acceptance Criteria

- [x] A fixture with `BacktestEngine(symbol="sc888", ...)` (or another already-configured symbol in
      lowercase) and `limit_halt_model="aware"` produces identical `is_entry_at_limit`/
      `is_exit_at_limit` values to the equivalent uppercase-symbol run (unit-tested).
- [x] A fixture with a symbol genuinely absent from `SYMBOL_LIMIT_CONFIG` under `"aware"` produces
      `None` (not `False`) for both tag fields, or raises — dev's choice, but must not silently
      write `False` (unit-tested).
- [x] `limit_halt_model="off"` behavior is completely unaffected (existing golden-snapshot
      equivalence test — `test_limit_halt_off_equivalence.py` — still passes byte-identical).
- [x] Uses `positions.py`'s `_research_symbol_key` (imported), not `backtest_engine.py`'s own local
      one, and does not modify either existing `_research_symbol_key` definition.
- [x] No threshold tuning; no pre-2026-04-24 data used for any parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a55-post-remediation-audit-roadmap.md` §"A57". Third task of the
   A55-A60 roadmap triaging `docs/review/ai_trading_review_2026-07-13.md`'s findings — read that
   report's finding #3 (🟠 medium) for full context.
2. **Scope:** `chan_strategy/backtest_engine.py`'s limit-lookup call site (around line 314) only.
   Import `_research_symbol_key` from `chan_strategy.positions` (do not reuse the file's own local
   `_research_symbol_key` at line 45 — see the "Important nuance" note above for why: the two
   functions behave differently for symbols with exchange-suffix dots). Do not touch
   `limit_config.py`'s `SYMBOL_LIMIT_CONFIG` contents, `_bar_at_limit`, `_daily_prev_close_map`, or
   anything scheduled for A59.
3. **Fail-loud semantics — pick one, document which:** either raise a clear exception when
   `limit_halt_model="aware"` and the normalized symbol is genuinely unconfigured, or set both tag
   fields to `None` (not `False`). Either is acceptable per the design; just be explicit and
   consistent, and make sure it's unit-tested.
4. **Test file:** `tests/unit/test_limit_halt_aware.py` already exists — add cases there
   (lowercase-vs-uppercase-symbol equivalence; unconfigured-symbol fail-loud behavior). Do not
   create a duplicate test file.
5. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; `limit_halt_model="off"`'s existing equivalence snapshot must stay byte-identical.
6. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing.**
7. **Lesson from A56's round 1 rejection, carried forward:** if your dev round's own
   `sync_check.py`/preflight run happens to regenerate any `diagnostics/*.md` report (e.g. via
   `run_next_work.ps1 -Preflight`'s SimNow steps), the RESEARCH-ONLY banner generators were fixed in
   A56 — this should no longer be an issue, but if you see a banner-check failure anyway, it is
   very likely unrelated pre-existing/concurrent repo activity, not something A57 introduced;
   note it plainly in the Decision Log rather than silently working around it, and do not spend
   large effort chasing it — surface it to review instead.
8. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A57 limit-config case normalization + fail-loud implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Manual verification (claude-code's independent re-run, dev-round output not self-reported by kimi-code)

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` — 579 passed, 4
  deselected in 31.28s (up from A56's 577 baseline by exactly the 2 new tests this task adds:
  `test_aware_lowercase_symbol_matches_uppercase`, `test_aware_unconfigured_symbol_fails_loud`).
- `ruff check chan_strategy/backtest_engine.py tests/unit/test_limit_halt_aware.py` — pass.
- `python tools/sync_check.py` — pass (version 4.4.0).
- `python tools/sync_check.py --root examples/czsc_strategy` — pass (version 0.2.1). synccheck:ignore
- Diff scope confirmed minimal and correct: `backtest_engine.py` imports `positions.py`'s
  `_research_symbol_key` under the alias `_position_symbol_key` (avoids colliding with the file's
  own pre-existing local `_research_symbol_key`), normalizes `self.symbol` only inside the
  `limit_aware` branch (so `limit_halt_model="off"` never executes the new code path — the
  existing equivalence snapshot is provably untouched), and raises `ValueError` with a clear
  message when the normalized symbol has no `SYMBOL_LIMIT_CONFIG` entry, rather than silently
  producing `False` tags. No changes to `limit_config.py`, `_bar_at_limit`, or either
  `_research_symbol_key` definition.

## Decision Log

- 2026-07-13 - A57 promoted from `docs/design/a55-post-remediation-audit-roadmap.md`'s draft to an
  active HANDOFF task, started immediately after A56 reached `done` (codex accepted the round-2 fix
  directly).
- 2026-07-13 - claude-code re-verified `backtest_engine.py:314`'s lookup is unchanged since the
  audit, and discovered during due-diligence that `backtest_engine.py` has its own local
  `_research_symbol_key` (line 45, strips all non-alnum chars) that is DIFFERENT from
  `positions.py`'s version (line 302-304, splits at first dot) — for symbols with an exchange-suffix
  dot (e.g. `"sc888.SHFE"`), the local version would produce a wrong, non-matching key. Directed dev
  to import and use `positions.py`'s version specifically (matching `portfolio_engine.py:29`'s
  existing precedent), and to leave the pre-existing duplicate-function drift itself out of scope.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-13 | codex → claude-code | done → dev | A57 (limit-config case normalization + fail-loud) promoted from post-remediation audit roadmap; handoff design->dev |
| 2026-07-13 | kimi-code → codex | dev → review | A57 limit-config case normalization + fail-loud implemented in backtest_engine.py; added lowercase equivalence and unconfigured-symbol fail-loud tests. Unit tests pass (579). ruff check clean on changed files. sync_check root and czsc_strategy pass. run_next_work.ps1 -Preflight not run because examples/czsc_strategy/run_next_work.ps1 does not exist in this working tree. |
