---
task: A66 - Rewrite README.md to Reflect Current Strategy
version: 4.4.0
stage: dev
owner: kimi-code
updated: 2026-07-15
deliverables:
  - HANDOFF.md
  - docs/design/a65-third-party-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: claude-code
last_transition_from_stage: design
last_transition_to_stage: dev
last_transition_from_owner: claude-code
last_transition_to_owner: kimi-code
---

## Background

Second task of the 2026-07-14 third-party-audit remediation roadmap
(`docs/design/a65-third-party-audit-remediation-roadmap.md` §"A66"), promoted immediately after
A65 reached `done` (codex accepted on the first review round).

**Re-verified 2026-07-15 by claude-code:** `examples/czsc_strategy/README.md` (194 lines, read in
full) describes a completely different, superseded strategy version: a 5-minute/30-minute/4-hour
three-tier position-sizing "波段战法" (swing-trading tactic) for A-share stocks, backtested
2021-01-01~2022-12-31 on Baostock data with 万三+印花税 costs, referencing files
`czsc_adapter.py`/`czsc_multi_timeframe_strategy.py`/`run_baostock_backtest.py` — **these files
still exist on disk** (confirmed via `ls`), but are NOT referenced by any test or by
`chan_strategy/`'s own code (confirmed via `grep`) — they are an inactive, superseded early
prototype, not the current strategy.

The CURRENT, actively-tested-and-gated strategy lives entirely under `chan_strategy/` and is a
completely different design: a futures CTA strategy using Chan-theory (缠论) 一买/二买/三买 (first/
second/third-buy) and mirrored sell signals (`chan_strategy/signals.py`, `chan_strategy/
sell_signals.py`, signal version `V260615` per `config.py:172`), with:
- Default instruments (confirmed `config.py:145-159`): `AP888`/`RB888`/`SC888`/`A888`/`ZN888`
  futures contracts, each with a cited exchange-minimum margin rate.
- Default frequencies (confirmed `config.py:12-15`): `base_freq="5分钟"`, `trade_freq="30分钟"`,
  `confirm_freq="5分钟"`, `filter_freq="日线"`.
- Default backtest window/costs (confirmed `config.py:163-169`): `2023-01-01~2025-12-31`,
  `commission_rate=0.0001` (万一), `slippage=0.0005` (0.05%) — NOT the README's 2021-2022/万三+印花税.
- Position sizing by signal tier (confirmed `config.py:19-28`): `pos_1buy=0.10`, `pos_2buy=0.20`,
  `pos_3buy=0.30` (and mirrored sell-side), fixed stop-loss/timeout/trailing-stop parameters per
  tier, plus a long list of research-only opt-in gates layered on top over many prior tasks
  (`exit_model`, `sizing_model`, `limit_halt_model`, `resonance_filter`, `second_buy_mode`,
  `divergence_model`, `portfolio_risk`, `rollover_stat_tagging`, `weighting`, etc. — all confirmed
  present in `config.py`, each individually documented by its own inline comment citing the task
  that introduced it).
- No test asserts on `README.md`'s content (confirmed via `grep` across `tests/unit/`) — rewriting
  it is safe and will not break any test.

**Known, pre-existing, OUT-OF-SCOPE technical-debt note (do not fix as part of this task):**
`signals.py` itself still contains a `get_all_signals` function that assembles the deprecated
`signal_second_buy`/`signal_third_buy` implementations from that same file — but the PRODUCTION
path (`sell_signals.py`'s own `get_all_signals`, which is what the backtest engine actually calls)
uses its OWN, separately-defined, bug-fixed `signal_second_buy`/`signal_third_buy` (confirmed via
direct read of both files). The stale `signals.py`-internal `get_all_signals` is a previously-known
backlog item (🟢#12 in the 2026-07-13 audit) consumed only by some `skill_build/` scripts, not by
`chan_strategy`'s own backtest path. Do not attempt to fix this as part of A66 — it's out of scope;
just be aware of it so the new README correctly describes the PRODUCTION signal path
(`sell_signals.get_all_signals`), not the stale one.

Full contract: `docs/design/a65-third-party-audit-remediation-roadmap.md` §"A66 — Rewrite
`README.md` to Reflect Current Strategy" (the authoritative design — this HANDOFF summarizes it).

## Goal

Rewrite `examples/czsc_strategy/README.md` to accurately describe the CURRENT `chan_strategy`
codebase: its actual signal taxonomy (一买/二买/三买 and mirrored sell signals, sourced from
`sell_signals.py`'s production `get_all_signals`, not the stale `signals.py`-internal one), actual
default config (frequencies, instruments, position sizing, backtest window, costs — all cited above
from direct reads), and the RESEARCH-ONLY/not-a-recommendation posture already established
elsewhere in this project's house style (mirror the tone of `diagnostics/declassify_historical_
reports.py`'s banner text or `docs/design/a38-phase-contracts-p2-p8.md`'s own framing — do not
invent new disclaimer language from scratch). Do NOT invent new performance claims — if citing any
historical result, it must already exist in a properly-banner'd `diagnostics/*.md` report, cited by
file-path reference, not reproduced as if fresh.

Preserve the OLD README content as a dated historical appendix (or move it to an archive file with
a clear pointer from the new README) — do not silently delete the historical record. The old
content describes a real, once-functional early prototype (`czsc_adapter.py` et al., still present
on disk) — label it clearly as superseded, not as if it never existed.

## Acceptance Criteria

- [ ] `README.md`'s described base/trade/filter/confirm frequencies match `chan_strategy/
      config.py`'s actual current defaults (`5分钟`/`30分钟`/`日线`/`5分钟`).
- [ ] `README.md`'s described instrument universe matches `config.py`'s `contract_specs`
      (`AP888`/`RB888`/`SC888`/`A888`/`ZN888`).
- [ ] `README.md`'s described backtest window and cost assumptions match `BACKTEST_CONFIG`
      (`2023-01-01~2025-12-31`, 万一 commission, 0.05% slippage) — NOT the old 2021-2022/万三+印花税.
- [ ] `README.md`'s described signal taxonomy matches the PRODUCTION signal path
      (`sell_signals.py`'s `get_all_signals`: 一买/二买/三买 and mirrored sell signals), not the
      stale `signals.py`-internal `get_all_signals`.
- [ ] Any cited historical performance number is sourced from an existing, properly-banner'd
      `diagnostics/*.md` report by file-path reference, never presented as a fresh claim.
- [ ] The old README content is preserved (dated historical appendix or archive reference with a
      clear pointer), not silently deleted.
- [ ] No threshold tuning; no pre-2026-04-24 data used to justify any NEW claim; no `GOAL PASSED`.
- [ ] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes (should be a
      no-op — confirms the rewrite touched no tracked code).
- [ ] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [ ] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes.

## Notes for the Next Agent

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a65-third-party-audit-remediation-roadmap.md` §"A66". Second task
   of the A65-A69 roadmap — read the design doc's Background for the full picture.
2. **Scope:** `examples/czsc_strategy/README.md` only (a documentation-only task). Do not touch
   `chan_strategy/*.py`, `config.py`'s actual values, `czsc_adapter.py`/`czsc_multi_timeframe_
   strategy.py`/`run_baostock_backtest.py` (the old files being described — leave them on disk
   untouched, just stop describing them as the current strategy in the main README body), or any
   diagnostics script.
3. **Read `signals.py` and `sell_signals.py` yourself before describing the signal taxonomy** —
   don't just trust this HANDOFF's summary. Confirm the exact one-buy/two-buy/three-buy semantics
   and which `get_all_signals` is actually on the production path (`sell_signals.py`'s), per the
   "known, pre-existing, out-of-scope" note above.
4. **Read `config.py` in full yourself** — it has ~15 different research-only opt-in switches
   layered on by many prior tasks (each with its own inline comment). The new README does not need
   to enumerate every single one exhaustively, but should give an accurate overview of the defaults
   (all switches default to their legacy/byte-identical value) and point to `config.py` itself as
   the source of truth for the full list, rather than trying to duplicate every switch's docs in
   the README (which would itself drift again over time).
5. **Historical-appendix placement is your own design call** — a dated section at the bottom of
   the same README, or a separate `README.legacy.md`/similar with a one-line pointer from the main
   README, are both acceptable; document your choice and reasoning in the Decision Log.
6. **Any performance number you cite MUST already exist in a banner'd `diagnostics/*.md` file** —
   search `diagnostics/` for an existing report before citing any number; do not compute or imply a
   new one.
7. **Guardrails (reject-on-violation):** no threshold tuning; no pre-2026-04-24 data used to justify
   any NEW claim; no `GOAL PASSED`; no code file touched; old README content not silently deleted.
8. **Include a Manual-verification block with natively-run counts** (should mostly show "no
   change" since this is docs-only, but run the commands anyway to prove nothing broke).
9. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A66 README rewrite implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Decision Log

- 2026-07-15 - A66 promoted from `docs/design/a65-third-party-audit-remediation-roadmap.md`'s
  draft to an active HANDOFF task, started immediately after A65 reached `done` (codex accepted on
  the first review round).
- 2026-07-15 - claude-code confirmed the old README's referenced files
  (`czsc_adapter.py`/`czsc_multi_timeframe_strategy.py`/`run_baostock_backtest.py`) still exist on
  disk but are unreferenced by any test or by `chan_strategy/`'s own code — a genuinely inactive,
  superseded prototype, not a currently-used alternate path. Also confirmed the production signal
  path is `sell_signals.py`'s `get_all_signals` (not the stale `signals.py`-internal one, which is
  a separate, already-known, out-of-scope backlog item — 🟢#12 from the 2026-07-13 audit).

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-15 | codex → claude-code | done → dev | A66 (README rewrite) promoted from third-party audit remediation roadmap; handoff design->dev |
