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
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
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
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `powershell -ExecutionPolicy Bypass -File .\examples\czsc_strategy\diagnostics\run_next_work.ps1 -Preflight`
      passes (or the Manual-verification accommodation in `.synccheck.yml`/HANDOFF.md applies if
      the codex-sandbox symlink limitation is still unresolved at review time).

## Notes for the Next Agent

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
8. Finish with the four acceptance commands, then
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

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-11 | codex → claude-code | done → design | A40 (P3) real position sizing started |
| 2026-07-11 | claude-code → kimi-code | design → dev | A40 design complete: P3 real position sizing spec with cited exchange contract specs (AP/RB/SC/A/ZN) |
