---
task: A53 - Config/Signal Single-Source-of-Truth Cleanup
version: 4.4.0
stage: done
owner: codex
updated: 2026-07-13
deliverables:
  - HANDOFF.md
  - docs/design/a49-audit-remediation-roadmap.md
blockers: []
last_transition_kind: next
last_transition_actor: codex
last_transition_from_stage: review
last_transition_to_stage: done
last_transition_from_owner: codex
last_transition_to_owner: codex
---

## Background

Fifth task of the 2026-07-12 audit remediation roadmap
(`docs/design/a49-audit-remediation-roadmap.md` §"A53"), started after A52 (continuous-contract
data-integrity) reached `done`. Independent of A49-A52/A54.

Four related dead-config/dead-code findings, re-verified 2026-07-13, all unchanged since the
audit:

1. **🟠#6 Orphan config keys** (`chan_strategy/positions.py:396,405,407,409`):
   `_research_first_buy_allowed`/`_daily_trend_filter_signals`-area code reads
   `enable_1buy_symbols`, `block_1buy_daily_down`, `block_1buy_daily_not_up`,
   `block_1buy_daily_below_zs` via `STRATEGY_CONFIG.get(...)` — none of these keys exist in
   `config.py`, so these gates are permanently no-op regardless of any config edit.
2. **🟠#7 Duplicated `stop_loss_pct=0.05`**: hardcoded as a function-signature default in 4 places
   (`signals.py:726,793`, `sell_signals.py:235,261`) for the *structural-invalidation* concept
   (price breaking 5% past a center edge) — confusingly identically named to but distinct from the
   *position stop-loss* concept (`config.py`'s `stop_loss_1buy`/`2buy`/`3buy`, in basis points).
3. **🟠#8 Orphaned legacy signal implementation**: `signals.py:487`/`623`'s
   `signal_second_buy`/`signal_third_buy` are superseded by `sell_signals.py:28`/`73`'s corrected
   versions (per that module's own docstring: "安全二买实现：规避旧 signals.py 中 None 分支和
   Direction 比较缺陷"). **Re-verified 2026-07-13: `sell_signals.py` fully reimplements both
   functions from scratch — it does NOT call the `signals.py` originals.** It does import them
   under aliases (`signal_second_buy as _base_signal_second_buy`,
   `signal_third_buy as _base_signal_third_buy`, `sell_signals.py:21-22`) but **never uses either
   alias anywhere in the file** — this is itself an additional, previously-unflagged dead
   import, bundled into this task.
4. **🟢#10 `equity_mode` dead config** (`config.py:79`): declared with `"fixed"`/`"compound"`
   documented options, but no code anywhere branches on this key — re-verified 2026-07-13, zero
   hits in `positions.py`/`backtest_engine.py`/`portfolio_engine.py`; it is read only by a
   tautological test assertion.

Full contract: `docs/design/a49-audit-remediation-roadmap.md` §"A53 — Config/Signal
Single-Source-of-Truth Cleanup" (the authoritative design — this HANDOFF summarizes it).

## Goal

Fill in the four orphan config keys with defaults matching today's de-facto no-op behavior, prove
equivalence, then unit-test each gate's actual on-behavior (the underlying conditional logic in
`positions.py` was presumably written correctly at the time but has never actually been exercised
since it's been unreachable — verify it, don't just assume it's right). Single-source
`stop_loss_pct` as `structural_invalidation_pct` in `STRATEGY_CONFIG` across all 4 call sites, with
a comment distinguishing it from the position stop-loss tiers. Delete or deprecate-mark
`signals.py`'s superseded `signal_second_buy`/`signal_third_buy` (verify the import graph first —
confirmed clean above, but re-verify at dev time in case anything changed). Remove the newly-found
dead `_base_signal_second_buy`/`_base_signal_third_buy` import aliases in `sell_signals.py`.
Resolve `equity_mode`: either delete the key, or make `"compound"` raise `NotImplementedError` at
a real call site.

## Acceptance Criteria

- [x] All four orphan keys exist in `config.py` with defaults matching today's de-facto behavior;
      a full-`BacktestEngine` equivalence test proves default output is byte-identical to before
      this task (per the A44-A52 house pattern — do not ship with only a unit-level check).
- [x] Each orphan key's actual on-behavior (`True`/non-`None` value) is unit-tested and confirmed
      to behave as its variable name implies (e.g. `block_1buy_daily_down=True` genuinely blocks a
      一买 open when daily direction is 向下) — this is real verification of previously-untested
      logic, not just a smoke test.
- [x] `structural_invalidation_pct` is read from `STRATEGY_CONFIG` at all 4 former hardcode sites
      (`signals.py:726,793`, `sell_signals.py:235,261`); changing the config value changes all 4
      call sites' behavior identically (unit-tested); a comment at the config key distinguishes it
      from `stop_loss_1buy`/`2buy`/`3buy`.
- [x] `signals.py`'s superseded `signal_second_buy`/`signal_third_buy` are either deleted (with an
      import-graph check proving nothing outside `sell_signals.py`'s own now-confirmed-unused
      aliases referenced them) or carry an explicit deprecation comment pointing to the
      authoritative version.
- [x] `sell_signals.py:21-22`'s dead `_base_signal_second_buy`/`_base_signal_third_buy` import
      aliases are removed (they are never used — confirmed 2026-07-13 by grep).
- [x] `equity_mode` either no longer exists, or `"compound"` raises `NotImplementedError` at a
      real call site (unit-tested) — not a decorative unread key either way.
- [x] No threshold tuning; no pre-2026-04-24 data used for any parameter choice; no SimNow
      order/cancel/send path changed; no `GOAL PASSED`; does not touch `structural_atr`/P8a exit
      logic (A47, done) or the P8b portfolio coordinator (A48, done).
- [x] `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` passes.
- [x] `python tools/sync_check.py` and `python tools/sync_check.py --root examples/czsc_strategy`
      pass.
- [x] `run_next_work.ps1 -Preflight` (from `examples/czsc_strategy/`) passes — this script
      genuinely exists at `diagnostics/run_next_work.ps1`; verify the path carefully before
      claiming otherwise (A44's dev round falsely claimed it was absent).

## Notes for the Next Agent

### Codex Review Rejection (2026-07-13)

1. **Remove the remaining hardcoded `0.05` structural-invalidation fallbacks.**
   A53's review checklist says to reject if `structural_invalidation_pct` still has any
   hardcoded duplicate. The implementation moved the function defaults to `None`, but each former
   hardcode site still has a local fallback:
   - `examples/czsc_strategy/chan_strategy/signals.py:787`
   - `examples/czsc_strategy/chan_strategy/signals.py:842`
   - `examples/czsc_strategy/chan_strategy/sell_signals.py:252`
   - `examples/czsc_strategy/chan_strategy/sell_signals.py:285`

   Those should read the already-required `STRATEGY_CONFIG["structural_invalidation_pct"]`
   single source directly, or through one shared helper that itself reads the config, while
   preserving the explicit `stop_loss_pct` override behavior tested in A53.

(dev = kimi-code must read this before writing code)

1. **Entry point:** `docs/design/a49-audit-remediation-roadmap.md` §"A53". Fifth task of the
   6-task remediation roadmap (A49-A54) triaging `docs/review/ai_trading_review_2026-07-12.md` —
   read that audit report's Findings #6, #7, #8, #10 for full context.
2. **Scope:** `chan_strategy/config.py` (new keys, `equity_mode` resolution),
   `chan_strategy/positions.py` (now-reachable orphan-key gates — verify correctness, since this
   logic has never actually run against real data before),
   `chan_strategy/signals.py`/`sell_signals.py` (`structural_invalidation_pct` call-site updates;
   legacy-signal deprecation/deletion; dead alias-import removal). Do not touch
   `structural_atr`/P8a exit logic (A47), the P8b portfolio coordinator (A48), or anything from
   A49-A52 (already done, independent of this task).
3. **The orphan-key gates enable previously-unreachable code — treat it with the same scrutiny as
   new code, not as "already correct because it's already written."** Since `.get()` always
   returned `None`/falsy before this task, the conditional branches in `positions.py` around lines
   396-409 have never actually executed against real signals. Read them carefully; if the logic
   turns out to be subtly wrong once reachable, that is a legitimate finding to fix in this same
   task (it's still in scope — you're the one making it reachable).
4. **`structural_invalidation_pct` is a NEW name for an OLD concept** — do not confuse it with
   `stop_loss_1buy`/`stop_loss_2buy`/`stop_loss_3buy` (position stop-loss, basis points, used by
   `positions.py`'s exit logic). `structural_invalidation_pct` is `signal_risk_control`'s
   "结构失效" threshold (a fraction like 0.05, used to compute whether price breaking 5% past a
   center edge counts as structural failure). Keep the config comment explicit about this
   distinction — this exact confusion is what caused the original finding.
5. **Re-verify the `signals.py` deletion is safe before deleting** — re-run the import-graph check
   (`grep -rn "from chan_strategy.signals import" examples/czsc_strategy/ | grep
   "signal_second_buy\|signal_third_buy"` and similarly for any direct `chan_strategy.signals.
   signal_second_buy`/`signal_third_buy` module-attribute access) at dev time, since code may have
   changed since this HANDOFF was written. If genuinely unreferenced outside `sell_signals.py`'s
   now-dead aliases, delete; otherwise, deprecation-comment instead.
6. **Guardrails (reject-on-violation):** no threshold tuning via backtest/capture-data selection;
   no pre-2026-04-24 data for any parameter choice; no SimNow order/cancel/send paths touched; no
   `GOAL PASSED`; any orphan-key on-behavior test must genuinely verify the variable name matches
   real behavior, not just "the key is now settable."
7. **Before claiming any script "doesn't exist," verify the path carefully** —
   `run_next_work.ps1` lives at `examples/czsc_strategy/diagnostics/run_next_work.ps1`.
8. **Include a Manual-verification block with natively-run counts proactively** — A52's dev round
   did this and passed review on the first attempt; A49 and A51 both needed a second round solely
   because this block was missing. Follow A52's precedent.
9. Finish with the acceptance commands, then
   `python tools/handoff.py next --actor kimi-code --summary "A53 config/signal single-source-of-truth cleanup implemented"`.
   Transactional gate — fix and retry if it blocks; no `--no-gate`.

## Manual Verification (natively run)

- `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"` → **559 passed, 4 deselected** (30.29s)
- `python -m pytest examples/czsc_strategy/tests/unit/test_a53_config_signal_cleanup.py examples/czsc_strategy/tests/unit/test_a53_orphan_keys_equivalence.py -q` → **12 passed**
- `python tools/sync_check.py` → **PASS**
- `python tools/sync_check.py --root examples/czsc_strategy` → **PASS**
- `ruff check examples/czsc_strategy/chan_strategy/config.py examples/czsc_strategy/chan_strategy/signals.py examples/czsc_strategy/chan_strategy/sell_signals.py examples/czsc_strategy/tests/unit/test_a53_config_signal_cleanup.py examples/czsc_strategy/tests/unit/test_a53_orphan_keys_equivalence.py` → **All checks passed** (pre-existing `positions.py` UP035/B905/UP006/UP045 warnings are untouched as out-of-scope).
- `examples/czsc_strategy/diagnostics/run_next_work.ps1 -Preflight` → **Preflight complete; live SimNow capture was not requested** (155 workflow unit tests passed).

## Decision Log

- 2026-07-13 - A53 promoted from `docs/design/a49-audit-remediation-roadmap.md`'s draft to an
  active HANDOFF task, started immediately after A52 reached `done`. Independent of A49-A52/A54.
- 2026-07-13 - Re-verified all four cited targets (orphan keys, duplicated `stop_loss_pct`,
  superseded `signals.py` functions, dead `equity_mode`) are unchanged since the audit.
- 2026-07-13 - Found an additional, previously-unflagged issue while re-verifying finding #8:
  `sell_signals.py:21-22` imports `signal_second_buy`/`signal_third_buy` from `signals.py` under
  `_base_*` aliases but never uses either — confirming `sell_signals.py`'s versions are genuine
  independent reimplementations (not wrappers calling the base), and adding a small bonus
  dead-import cleanup to this task's scope.
- 2026-07-13 - Dev implementation completed by kimi-code:
  - Added four orphan first-buy keys to `STRATEGY_CONFIG` with no-op defaults.
  - Single-sourced `structural_invalidation_pct` in `STRATEGY_CONFIG`; all four risk-control
    functions read from config while preserving backward-compatible explicit argument override.
  - Added explicit deprecation comments to `signals.py`'s superseded `signal_second_buy`/
    `signal_third_buy` after re-verifying they are still imported by existing unit tests.
  - Removed dead `_base_signal_second_buy`/`_base_signal_third_buy` aliases from `sell_signals.py`.
  - Made `equity_mode="compound"` raise `NotImplementedError` in `Position._size_open`.
- 2026-07-13 - Review rejection fix by kimi-code:
  - Replaced the remaining `STRATEGY_CONFIG.get("structural_invalidation_pct", 0.05)` hardcoded
    fallbacks in `signals.py` (2 sites) and `sell_signals.py` (2 sites) with direct config access
    `STRATEGY_CONFIG["structural_invalidation_pct"]`; verified no duplicate 0.05 fallback remains.

## 交接历史

| 日期 | 从 → 到 | 阶段变化 | 摘要 |
|------|---------|----------|------|
| 2026-07-13 | codex → claude-code | done → design | A53 promoted from the audit remediation roadmap draft after A52 reached done |
| 2026-07-13 | claude-code → kimi-code | design → dev | A53 (config/signal single-source-of-truth cleanup) started |
| 2026-07-13 | kimi-code → codex | dev → review | A53 config/signal single-source-of-truth cleanup implemented |
| 2026-07-13 | codex → kimi-code | review → dev | 打回: structural_invalidation_pct still has hardcoded 0.05 fallbacks |
| 2026-07-13 | kimi-code → codex | dev → review | A53 config/signal single-source-of-truth cleanup implemented |
| 2026-07-13 | codex → codex | review → done | A53 review accepted |
