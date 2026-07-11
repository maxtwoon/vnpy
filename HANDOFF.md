---
task: A40 Real Position Sizing (P3 - ATR-Risk Units + Contract Multiplier + Margin)
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-11
deliverables:
  - HANDOFF.md
  - docs/design/a40-real-position-sizing.md
blockers: []
last_transition_kind: reject
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: dev
last_transition_from_owner: codex
last_transition_to_owner: kimi-code
---

## Background

Roadmap phase **P3** (see `docs/design/a38-phase-contracts-p2-p8.md` §P3), now a standalone task
after A39 (P2) reached `done`. `Position` is currently direction-only (`pos in {-1,0,1}`, no
`volume`) — PnL is a percentage per pair, turned into money only via `BacktestEngine`'s post-hoc
fixed-weight loop (`pos_1buy=0.10`, `pos_2buy=0.20`, `pos_3buy=0.30`, ...), regardless of the
symbol's actual volatility, the trade's actual stop distance, or the contract's real value. Every
reported return/drawdown/Sharpe in every prior diagnostic (A31-A39) is therefore a signal-quality
index, not tradeable PnL, and no future Tier B/C profitability claim can be trusted until this is
fixed.

A40 gives `Position` real integer-lot sizing and currency PnL behind a gated switch
(`sizing_model`: `"research"` default = byte-identical current behavior | `"risk"` = ATR-style
risk-per-trade sizing against the P1 stop distance, contract multiplier, and a margin cap).
Contract specs (multiplier/tick/margin_rate) for AP/RB/SC/A/ZN were sourced and cited from the
exchanges' own published contract rules during design (2026-07-11) — see the design doc §2 for
citations; do not alter these numbers without a new citation.

Single source of truth: `docs/design/a40-real-position-sizing.md`.

## Goal

Implement: `Position` gains `volume` (default 1) and `contract_multiplier` (default 1); under
`sizing_model="risk"`, opens are sized by
`floor(equity_at_entry * risk_per_trade_pct / (stop_distance * multiplier))`, skip (no forced
1-lot floor) when that's `< 1`, and capped by `max_margin_pct` of equity (reduce or skip);
`pairs` gain `pnl_currency`. `BacktestEngine` threads `equity_at_entry`/margin state into opens
under `"risk"` mode only; `"research"` mode's existing fixed-weight equity loop is untouched.

## Acceptance Criteria

- [ ] `STRATEGY_CONFIG["sizing_model"]` (`"research"` default | `"risk"`),
      `risk_per_trade_pct` (0.005), `max_margin_pct` (0.50), `equity_mode` (`"fixed"`), and
      `contract_specs` (AP888/RB888/SC888/A888/ZN888, each with `multiplier`/`tick`/
      `margin_rate` and an inline source citation comment) exist in `config.py`.
- [ ] Research equivalence: with `sizing_model="research"`, the equity curve and every
      `Position.pairs` entry's `pnl_pct`/`open_price`/`close_price`/`bars_held`/`reason` are
      byte-identical to the pre-A40 baseline on >=2 symbols x 1 year (empty diff). `volume`/
      `pnl_currency` may be present but equal `1`/`pnl_pct * entry_price` and are not read by any
      existing report/diagnostic code path.
- [ ] Risk sizing (unit): given a fixture, `volume == floor(risk_amount/(stop_distance*
      multiplier))` exactly, long and short.
- [ ] Zero-size skip: `raw_volume < 1` skips the open entirely (no `pairs`/`trades` entry, no
      forced 1-lot floor); increments a `size_zero_skip` counter.
- [ ] Margin cap: a fixture whose sized `volume` breaches `equity_at_entry * max_margin_pct`
      reduces to the largest lot count that fits (>=1), else skips (`margin_cap_skip` counter).
- [ ] Currency PnL: `pnl_currency == (exit-entry)*volume*multiplier*sign -
      (2*commission_rate+slippage)*entry*volume*multiplier`, long and short, within float
      tolerance.
- [ ] No-lookahead: `equity_at_entry`/margin-cap decisions read only bars up to and including the
      entry bar; `BacktestEngine.run` step ordering unchanged beyond new optional sizing params.
- [ ] Report header (and risk-mode equity-curve rows) print `sizing_model` and (risk mode)
      `total_open_margin`/`margin_utilization_pct`.
- [ ] No threshold tuned via backtest selection; no pre-2026-04-24 data used for any parameter
      choice; no SimNow order/cancel/send paths changed; no new `send_order`/`cancel_order`/
      `buy`/`sell`/`short`/`cover` calls.

### Addendum (2026-07-11, post independent read-only audit — see design doc §7a for full rationale)

- [ ] AC-A40-9: one new command produces a single git-tracked report showing, for the same
      backtest run, real sizing (a), A38 stop-execution mode + touch-vs-close exit counts (b),
      and whether a SimNow replay risk caliber was consulted (c) — `"status":
      "not_available_pending_A41"` if A41 hasn't landed, never a fabricated number.
- [ ] AC-A40-10: no judgment this report derives from `simnow_daily_capture.py`'s `build_risk()`
      output may treat its hardcoded-zero fields as a real measurement; a `simnow.risk`-sourced
      figure must be labelled `"risk_source": "simnow_capture_placeholder"` vs
      `"replay_computed"` and a placeholder zero must never silently satisfy a warning/halt
      threshold.
- [ ] AC-A40-11: a test/report section confirms the risk-mode `stop_distance` sizing denominator
      is the same value A38's `stop_execution_model="intrabar"` actually uses to trigger an exit.
- [ ] AC-A40-12: a dedicated test exercises `sizing_model="risk"` + `stop_execution_model=
      "intrabar"` together (long+short), asserting `pnl_currency` on a touch-based exit uses the
      actual touched stop price, not `bar.close`.
- [ ] AC-A40-13: the AC-A40-9 report carries the RESEARCH-ONLY banner and states its PnL/margin
      figures use exchange-*minimum* margin rates, not production-ready numbers.

- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight`
      passes (or the Manual-verification accommodation in `.synccheck.yml`/HANDOFF.md applies if
      the codex-sandbox symlink limitation is still unresolved at review time).

## Manual verification (symlink-privilege sandbox limitation)

(claude-code, 2026-07-11 — see `.synccheck.yml` NOTE above the `review` command for the full
root-cause writeup; codex should trust this block for these two items instead of re-running them)

Root cause (unchanged from A39; relogin/reboot to activate Developer Mode has not happened yet):
codex exec's sandbox cannot create Windows symlinks, and pytest's `tmp_path` fixture creates a
"-current" symlink per temp dir, so tmp_path setup fails with `PermissionError [WinError 5]`
regardless of `--add-dir`. Manually verified in this unsandboxed session:

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` -> **402 passed,
  4 deselected** (2026-07-11, this session).
- `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight`
  -> **Preflight complete** (2026-07-11, this session).

Everything else (diffs, `sync_check` gates, guardrail scans, deliverable tracking, report content
correctness) should still be verified normally by review. Remove this block once a review round
passes both commands cleanly inside the sandbox again (post-relogin).

## Notes for the Next Agent

(review = codex, 2026-07-11)

Review rejected on A40 acceptance:

1. AC-A40-9 requires the generated position-sizing report to be git-tracked. The file
   `examples/czsc_strategy/diagnostics/position_sizing_report_risk_2023-01-01_2025-12-31.json`
   exists locally but is ignored and absent from `git ls-files`. Root cause: `.gitignore` unignores
   `position_sizing_report_*.json` at lines 82-83, but the later
   `examples/czsc_strategy/diagnostics/` rule at line 110 re-ignores the directory. Fix the ignore
   ordering/rules and commit the report artifact, or explicitly `git add -f` it.
2. The AC-A40-9 report's stop-exit summary is internally inconsistent:
   `touch_based_stop_exits=0`, `gap_fill_stop_exits=0`, `close_based_stop_exits=34`, but
   `total_stop_exits=47`. In `run_position_sizing_report.py`, `summary["total_stop_exits"] +=`
   the cumulative component totals inside the per-symbol loop, double-counting earlier symbols.
   Set the total once from the final component counts, or increment it only per trade.

Verification notes from this review:
- `python tools/sync_check.py` passed.
- `python tools/sync_check.py --root examples/czsc_strategy` passed.
- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` failed with the documented
  sandbox `tmp_path` / `pytest-of-Admin` `PermissionError [WinError 5]` signature after 313 passed,
  4 deselected, 89 setup errors; no `Manual verification` block was present in `HANDOFF.md`.
- `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight`
  failed with the same documented sandbox signature after 110 passed and 34 setup errors.

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a40-real-position-sizing.md`. Full dev prompt in design §8.
2. **`contract_specs` numbers are sourced, not placeholders — do not alter them.** AP888
   multiplier=10/tick=1.0/margin_rate=0.07; RB888 multiplier=10/tick=1.0/margin_rate=0.05; SC888
   multiplier=1000/tick=0.1/margin_rate=0.05; A888 multiplier=10/tick=1.0/margin_rate=0.05; ZN888
   multiplier=5/tick=5.0/margin_rate=0.05. Citations in design §2 and §9 (exchange source URLs).
   These are **exchange minimum** margin rates, not production/broker rates — design §6 makes
   this explicit; don't "fix" it by adding a markup, that's out of scope.
3. **Sizing formula (design §3.1):** `stop_distance = price * stop_loss / 10000` (the Position's
   own nominal stop BP, same one P1's touch-based stop uses); `risk_amount = equity_at_entry *
   risk_per_trade_pct`; `raw_volume = risk_amount / (stop_distance * multiplier)`;
   `volume = floor(raw_volume)`; **no forced 1-lot floor** — `raw_volume < 1` skips the open.
   Margin cap (step 5) can further reduce or skip.
4. **`"research"` must stay byte-identical** — same default-off discipline as every prior phase
   (A37/A38/A39). Only `"risk"` mode changes `Position`'s open-sizing and `BacktestEngine`'s
   equity computation; the existing fixed-weight loop must be untouched under `"research"`.
5. **`pnl_currency` is additive, not a replacement** — `pnl_pct` stays exactly as-is (every
   existing diagnostic keys off it); `pnl_currency` is a new field on `pairs`.
6. **Guardrails (reject-on-violation):** no tuning `risk_per_trade_pct`/`max_margin_pct` via
   backtest results; no pre-2026-04-24 data for any selection; no SimNow order paths; no
   `GOAL PASSED`.
7. **Known environment accommodation:** if the pytest/preflight acceptance commands hit the
   documented codex-sandbox Windows-symlink limitation during review, that's covered by the
   standing Manual-verification accommodation already in `.synccheck.yml` (see the NOTE above the
   `review` command) — not something dev needs to fix.
8. **Addendum (AC-A40-9..13, design §7a):** added after an independent read-only 3-way audit,
   before any dev work started. Build one new unified report script
   (`diagnostics/run_position_sizing_report.py`) joining real sizing + A38 stop-execution mode +
   a SimNow-risk-caliber placeholder field; label any risk figure sourced from
   `simnow_daily_capture.py`'s known-placeholder `build_risk()` output so it can never silently
   satisfy a threshold (that root cause is A41's job — this only guards A40's own new report);
   add a stop-distance cross-check against A38 and a sizing×intrabar-stop interaction test.
9. Finish with the four acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A40 P3 real position sizing implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-11 - A40 started after A39 reached `done`; scope = roadmap P3 (real position sizing),
  promoted from A38's placeholder contract to a fully-specified standalone design.
- 2026-07-11 - Sourced real exchange contract specs (multiplier/tick/margin_rate) for
  AP/RB/SC/A/ZN via web search against the exchanges' own published contract rules, replacing
  A38's explicitly-illustrative placeholder numbers, per that document's own instruction ("dev
  MUST replace with cited exchange spec, do not fabricate") — done at design time instead of
  leaving it to dev, since sourcing authoritative numbers is a research task better done once by
  the design owner than repeated/guessed by dev.
- 2026-07-11 - Sizing keys off the Position's own nominal stop_loss BP (P1's stop distance) as
  the risk-budget denominator, not a separately-computed ATR, to keep sizing consistent with the
  stop that actually bounds the trade's loss (an ATR-based stop distance is a different, larger
  change belonging to a future exit-model task, not P3).
- 2026-07-11 - `pnl_currency` is additive alongside the existing `pnl_pct`, not a replacement,
  so no existing report/diagnostic code needs to change to consume A40's default (`"research"`)
  output.
- 2026-07-11 - Added acceptance-criteria addendum (AC-A40-9..13) after an independent read-only
  3-way subagent audit found A40 in isolation would not close the real gap: a return/drawdown
  number isn't trustworthy until real sizing, the actual A38 stop distance, and SimNow risk
  observation are jointly reconciled in one report, and that report can't be fooled by a known
  zero-placeholder risk value (`simnow_daily_capture.py`'s `build_risk()` — root-cause fix is a
  new task, A41; A40 only has to not be undermined by it). Applied before dev started (no rework
  needed) — reverted stage to `design` momentarily to make this edit honestly, then re-advanced
  to `dev`. Full audit produced two further follow-on task plans (A41 SimNow authenticity fix,
  A42 sync-guardian hardening) — not started as HANDOFF tasks yet, pending sequencing decision.
- 2026-07-11 (review reject) - codex found: (1) the AC-A40-9 report JSON wasn't git-tracked
  (`.gitignore`'s `!position_sizing_report_*.json` negation is structurally dead — a later
  blanket `examples/czsc_strategy/diagnostics/` ignore rule always wins for files not already
  tracked; this mirrors several other pre-existing negation lines in the same block that only
  "work" for legacy already-tracked files. Not a new bug kimi introduced — left `.gitignore`
  as-is and will `git add -f` the regenerated report at commit time instead, matching the
  established A37-A40 pattern); (2) `run_position_sizing_report.py`'s stop-exit summary
  double-counts `total_stop_exits` inside the per-symbol loop (real bug, dev to fix); (3) no
  Manual-verification block existed for this task yet (added above, matching the A39 pattern —
  each task's `HANDOFF.md` carries its own current block, it doesn't persist automatically).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-11 | codex → claude-code | done → design | A40 (P3) real position sizing started |
| 2026-07-11 | claude-code → kimi-code | design → dev | A40 design complete: P3 real position sizing spec with cited exchange contract specs (AP/RB/SC/A/ZN) |
| 2026-07-11 | claude-code → claude-code | dev → design (self-revisit) | Reverted stage to design before dev started, to add acceptance-criteria addendum AC-A40-9..13 after an independent read-only 3-way audit |
| 2026-07-11 | claude-code → kimi-code | design → dev | A40 design addendum: AC-A40-9..13 (unified report, no zero-placeholder risk, A38 stop-distance cross-check, sizing x intrabar-stop interaction) after independent audit |
| 2026-07-11 | kimi-code → codex | dev → review | A40 P3 real position sizing implemented |
| 2026-07-11 | codex → kimi-code | review → dev | 打回: A40 report artifact is ignored/untracked and stop-exit total is inconsistent |
