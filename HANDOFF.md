---
task: A58 - Gate-Combination Guards + Portfolio Flatten Cost Fix
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-14
deliverables:
  - HANDOFF.md
  - docs/design/a55-post-remediation-audit-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

Fourth task of the 2026-07-13 post-remediation re-audit roadmap
(`docs/design/a55-post-remediation-audit-roadmap.md` §"A58"), promoted immediately after A57
reached `done` (codex accepted on the first review round).

`docs/review/ai_trading_review_2026-07-13.md` Findings 🟠#4 and 🟠#5 (re-verified 2026-07-14 by
claude-code against current code, confirmed no line drift):

1. **No guard on `sizing_model="risk"` + `portfolio_risk="on"`** (`portfolio_engine.py:516-527`):
   the portfolio replay ledger unconditionally uses proportional-weight accounting
   (`realized = sum(p["pnl_pct"] * abs(p["weight"]) * self.initial_capital for p in
   coordinated_pairs)`, and the same pattern for `unrealized`) and never reads risk-mode's
   `pnl_currency`/integer-lot/margin fields. Confirmed via `grep -n "sizing_model"
   examples/czsc_strategy/chan_strategy/portfolio_engine.py` — **zero matches**: this file has no
   awareness of `sizing_model` at all. When both `sizing_model="risk"` and `portfolio_risk="on"`
   are set, the per-symbol report is currency-based and the portfolio report is weight-based
   simultaneously, and `daily_loss_limit_pct`'s trigger check uses a synthetic equity disconnected
   from real lot counts.
2. **Daily-loss-limit flatten pairs booked gross of costs** (`portfolio_engine.py:547`):
   `gross_pnl = sign * (flat_price - pos["open_price"]) / pos["open_price"]` is written directly as
   `pnl_pct` with no `2*commission_rate + slippage` deduction, while every other `coordinated_pairs`
   entry (sourced from `Position`, appended around line 507) is net-of-cost. The same list silently
   mixes gross and net entries, one-sidedly flattering `portfolio_risk="on"` outcomes that hit the
   daily loss limit.

Full contract: `docs/design/a55-post-remediation-audit-roadmap.md` §"A58 — Gate-Combination Guards
+ Portfolio Flatten Cost Fix" (the authoritative design — this HANDOFF summarizes it).

## Goal

1. **Guard the incompatible combination.** Add an explicit check at `PortfolioEngine.run()`'s entry
   point (`portfolio_engine.py:603-608`): if `STRATEGY_CONFIG.get("sizing_model") == "risk"` and
   `STRATEGY_CONFIG.get("portfolio_risk", "off") == "on"`, raise a clear
   `NotImplementedError`/`ValueError` stating the combination isn't supported yet. **Default
   expectation is to raise/warn, NOT to silently produce mismatched numbers.** Only attempt to
   actually thread currency-based accounting through the replay (the larger alternative) if, after
   reading `_build_on_report` in full, it turns out to be a genuinely small change — the roadmap's
   own guidance is to prefer the guard given how small/reviewable this task should stay.
2. **Fix the flatten-pair cost accounting.** Add `2 * self.commission_rate + self.slippage`
   deduction to the flatten `gross_pnl` computation (`portfolio_engine.py:547`), matching every
   other `coordinated_pairs` entry's net-of-cost convention. `self.commission_rate`/
   `self.slippage` are already instance attributes (set in `__init__`, lines 332-333) — no new
   parameters needed.

No new config key for either fix.

## Acceptance Criteria

- [x] `sizing_model="risk"` + `portfolio_risk="on"` produces a clear, immediate error (or, if the
      currency-threading alternative was chosen instead, produces correctly-threaded accounting —
      unit-tested either way) instead of silently running with mismatched accounting conventions.
- [x] A fixture with known `flat_price`/`open_price`/`commission_rate`/`slippage` proves the
      daily-loss-limit flatten pair's `pnl_pct` is net-of-cost, matching a hand-computed value.
- [x] `portfolio_risk="off"`'s existing equivalence test still passes byte-identical.
- [x] `sizing_model` defaulting to `"research"` (the existing default, not `"risk"`) with
      `portfolio_risk="on"` is completely unaffected by the new guard (no false-positive block).
- [x] No threshold tuning; no pre-2026-04-24 data used for any parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`.
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

## Manual verification (claude-code's independent re-run, dev-round output not self-reported by kimi-code)

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` — 582 passed, 4
  deselected in 31.30s (up from A57's 579 baseline by exactly the 3 new tests this task adds:
  `test_run_rejects_risk_sizing_with_portfolio_risk_on`,
  `test_run_allows_risk_sizing_with_portfolio_risk_off`,
  `test_daily_loss_limit_flatten_pair_is_net_of_cost`).
- `ruff check chan_strategy/portfolio_engine.py tests/unit/test_portfolio_risk.py` — pass.
- `python tools/sync_check.py` — pass (version 4.4.0).
- `python tools/sync_check.py --root examples/czsc_strategy` — pass (version 0.2.1). synccheck:ignore
- `run_next_work.ps1 -Preflight` — 164 passed; preflight complete.
- Diff scope confirmed minimal: `PortfolioEngine.run()` raises `NotImplementedError` before
  `_run_per_symbol()` when `sizing_model=="risk"` and `portfolio_risk=="on"`; the flatten-pair
  `gross_pnl` at line ~547 now deducts `2*commission_rate + slippage` before being stored as
  `pnl_pct`. No new config key; `portfolio_risk="off"` never reaches the guard branch since it
  requires `portfolio_risk=="on"` explicitly.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a55-post-remediation-audit-roadmap.md` §"A58". Fourth task of the
   A55-A60 roadmap triaging `docs/review/ai_trading_review_2026-07-13.md`'s findings — read that
   report's findings #4 and #5 (both 🟠 medium) for full context.
2. **Scope:** `chan_strategy/portfolio_engine.py` only — `PortfolioEngine.run()` (entry guard,
   around line 603) and the daily-loss-limit flatten block (around line 547). Do not add a full
   combination-legality matrix for all 10 stacked config gates in this task — scoped strictly to
   this one confirmed-broken combination and this one confirmed cost-accounting bug. A broader
   gate-compatibility audit is a separate, future task if warranted.
3. **Guard placement:** put the check in `run()` before it branches into `_build_off_report`/
   `_build_on_report` (or right at the start of `_build_on_report` itself — either works, but the
   check only needs to fire when `portfolio_risk == "on"`, since `sizing_model="risk"` alone with
   `portfolio_risk="off"` is already a normal, working, already-shipped combination from A40/A48).
4. **Test file:** `tests/unit/test_portfolio_risk.py` already has an `autouse` `restore_config`
   fixture — you can set `STRATEGY_CONFIG["sizing_model"] = "risk"` directly in a test body without
   any special monkeypatching machinery; it auto-restores after each test.
5. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; `portfolio_risk="off"`'s existing equivalence snapshot must stay byte-identical.
6. **Include a Manual-verification block with natively-run counts, and run `ruff check`
   proactively before finishing** — every dev round through A55-A57 that included this proactively
   passed review in one round; A56's round-1 rejection was for an unrelated sync-gate issue, not
   this, but the pattern still holds.
7. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A58 gate-combination guard + portfolio flatten cost fix implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-14 - A58 promoted from `docs/design/a55-post-remediation-audit-roadmap.md`'s draft to an
  active HANDOFF task, started immediately after A57 reached `done` (codex accepted on the first
  review round).
- 2026-07-14 - claude-code re-verified both findings against current code: `portfolio_engine.py`
  has zero references to `sizing_model` (confirmed via grep), and the flatten-pair `gross_pnl` at
  line 547 is confirmed to omit the cost deduction that every other `coordinated_pairs` entry
  applies. Line numbers unchanged since the 2026-07-13 audit. `self.commission_rate`/
  `self.slippage` are already available as instance attributes, so the cost fix needs no new
  parameters.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-14 | codex → claude-code | done → dev | A58 (gate-combination guards + portfolio flatten cost fix) promoted from post-remediation audit roadmap; handoff design->dev |
| 2026-07-14 | kimi-code → codex | dev → review | A58 gate-combination guard + portfolio flatten cost fix implemented |
| 2026-07-14 | codex → codex | review → done | A58 review accepted: guard, flatten cost fix, sync gates, and manual sandbox-affected verification checked |
