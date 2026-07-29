# Fix `signal_divergence_status()` Zhongshu Selection (P4 Divergence Signal Structurally Unreachable)

## Background

While investigating why `enable_short=True` produced zero short trades across every symbol/frequency
combination tested (A888 @5min and @30min, SC888 @5min, full year 2025-04-25~2026-04-24), root-caused it to
a concrete code defect, not a market-condition or configuration issue. Full investigation trail is in
`examples/czsc_strategy/diagnostics/WORK_LOG.md`'s `2026-07-27`/`2026-07-28` entries; this design formalizes
the fix.

### Root cause

`chan_strategy/positions.py::_research_short_open_allowed()` (the A46 gate requiring P4 top-divergence +
P5 resonance symmetry for every short open) reads `{freq}_D1BI_背驰V260615`, produced by
`chan_strategy/signals.py::signal_divergence_status()`. That function selects its reference zhongshu as:

```python
zhongshu_list = build_zhongshu_from_bis(bi_list)   # default mode="recent"
last_zs = zhongshu_list[-1]
after_zs_bis = bi_list[zs_end_idx + 1:]            # almost always empty
```

`build_zhongshu_from_bis(..., mode="recent")` (the default) returns candidates sorted by `end_idx`, so
`zhongshu_list[-1]` is, by construction, the candidate whose center ends **closest to the current end of the
confirmed bi list** — meaning it almost never has any bi's after it (`after_zs_bis` is empty), so the function
falls straight through to its default `v1 = "无"` (no divergence) every time, regardless of symbol, frequency,
or actual market structure. Empirically confirmed: 16442/16443 calls returned `"无"` for A888 across a full
year at both 5-minute and 30-minute frequency, and 26356/26357 for SC888 @5min — the one outlier in each case
was a data-availability edge case, not a real "疑似" (candidate) classification.

**This is a real, isolated bug, not a design choice**: the same file's `signal_first_buy()`
(`signals.py:428`) and `sell_signals.py`'s `signal_first_sell()` (line 117) both select their reference
zhongshu correctly:

```python
last_zs = next((zs for zs in reversed(zhongshu_list) if bi_list[zs["end_idx"] + 1:]), zhongshu_list[-1])
```

— i.e., search backward for a candidate that actually **has** a departure leg after it, only falling back to
the naive last-candidate pick if none qualify. `signal_divergence_status()` is the only one of the three
sibling functions that skips this search, and it is the sole producer of `{freq}_D1BI_背驰V260615`, which is
consumed by `_research_short_open_allowed()`'s P4 check. Net effect: the P4 half of the AND-gated short-open
condition is structurally almost unreachable, independent of P5, independent of symbol, independent of
frequency — confirmed empirically above, not merely reasoned from code reading.

### Why this matters

`enable_short=True` is a documented, user-facing STRATEGY_CONFIG switch (`config.py:24`,
"是否启用一卖/二卖/三卖空头子策略") that currently does essentially nothing for the specific short sub-strategy
this gate covers, because the gate it must clear can practically never open. Any research conclusion drawn
from an `enable_short=True` backtest today ("shorts don't help", "shorts are too rare to matter") is not a
finding about the strategy — it's an artifact of this bug.

## Proposed Fix

One-line change to `signal_divergence_status()`'s zhongshu selection, mirroring the already-correct pattern
in `signal_first_buy()`/`signal_first_sell()`:

```python
last_zs = next((zs for zs in reversed(zhongshu_list) if bi_list[zs["end_idx"] + 1:]), zhongshu_list[-1])
```

### Backward-compatibility: gate behind a new config switch, default to legacy

This repo's established convention (seen in `exit_model`, `stop_execution_model`, `daily_agg`,
`resonance_filter`, `second_buy_mode`, `atr_chop_filter`, `divergence_model`, `rollover_open_gating`,
`limit_halt_model`, `price_tick_rounding`, `rollover_stat_tagging`, `exit_event_semantics` — every one of
these is legacy-default/byte-identical unless explicitly opted in) is followed here even though this is a
bug fix, not a new feature: unconditionally changing `signal_divergence_status()`'s output would silently
change every existing default-config backtest result (including historical precheck baselines and any prior
promotion-decision evidence that used default config), which is exactly the kind of silent-drift problem
`examples/czsc_strategy/diagnostics/WORK_LOG.md`'s `2026-07-27` precheck-rerun investigation (534→318 trade
count drift) already flagged as a real, recurring risk in this codebase.

Add `STRATEGY_CONFIG["divergence_status_zhongshu_mode"]`:

- `"legacy"` (default): current behavior, `zhongshu_list[-1]` naive pick. Byte-identical to today.
- `"departure_leg"`: the corrected search (matches `signal_first_buy`/`signal_first_sell`).

`signal_divergence_status()` reads this key and branches on it. No other function changes. `_research_short_
open_allowed()` and any other consumer of `{freq}_D1BI_背驰V260615` are unaffected code-wise — they just see
the corrected signal value when the new mode is enabled.

### Where the toggle should also apply

`formal_evaluation_config()` (`backtest_engine.py`) should NOT be changed to enable this by default — it
already has a defined, stable set of overrides for a different purpose (execution realism: sizing, limit/halt,
rollover gating, tick rounding). Whether to enable `divergence_status_zhongshu_mode="departure_leg"` for
formal evaluation is a separate strategy decision the user has not made; leave `formal_evaluation_config()`
untouched. The new key is opt-in via direct `STRATEGY_CONFIG` mutation only, same as how this session's ad-hoc
backtests have been toggling `trade_freq`/`enable_short`/`html_report_enabled` directly.

## Acceptance Criteria

- [ ] `STRATEGY_CONFIG["divergence_status_zhongshu_mode"]` added, default `"legacy"`.
- [ ] `signal_divergence_status()` branches on this key; `"legacy"` path is byte-identical to current code
      (no behavior change when the key is left at its default — verify with a regression test that pins the
      exact same "无"-heavy output distribution this design doc's investigation already measured, or an
      equivalent fixture-based exact-output test).
- [ ] `"departure_leg"` mode uses the exact same selection expression as `signal_first_buy`/`signal_first_sell`
      (do not reimplement independently — extract a small shared helper if that avoids triplicated logic,
      but do not change `signal_first_buy`/`signal_first_sell`'s own behavior while doing so).
- [ ] New unit test(s) demonstrating the fix actually works: a fixture with a confirmed bi/zhongshu structure
      where the current "legacy" path returns "无" but "departure_leg" mode returns "疑似" for the same input
      — i.e. prove the mode actually changes the classification, not just that the code runs.
- [ ] Manual verification (not just unit tests): re-run a real backtest with `enable_short=True` AND
      `divergence_status_zhongshu_mode="departure_leg"` (same symbol/window used in this investigation, e.g.
      A888 or SC888, full year, 2025-04-25~2026-04-24) and confirm `_research_short_open_allowed()` now
      returns `True` at least sometimes (report the actual pass count, comparable to this design doc's
      "P4_PASS 0 / P5_PASS 0" baseline) and that at least one real short trade appears in
      `engine.strategy.get_combined_trades()`. Include the actual command and output in the handoff's Manual
      Verification section — do not just assert "should work now."
- [ ] Confirm `formal_evaluation_config()` is unchanged (does not set the new key) — verify via diff, not
      just by not editing the function.
- [ ] Full unit gate: `python -m pytest examples/czsc_strategy/tests/unit -q -m "not realdb"`, report exact
      before/after count (this task adds tests, so count must increase by exactly the number added).
      `-m realdb` gate verified unaffected per `AGENTS.md` rule (signals.py is touched, so this must be run,
      not assumed).
- [ ] `powershell -ExecutionPolicy Bypass -File examples/czsc_strategy/diagnostics/run_next_work.ps1
      -Preflight` still passes (confirms no accidental breakage of the unrelated SimNow workflow).
- [ ] `python tools/sync_check.py` (root) and `python tools/sync_check.py --root examples/czsc_strategy`
      both pass.
- [ ] `ruff check` on touched files: report before/after counts.
- [ ] `examples/czsc_strategy/VERSION` / `CHANGELOG.md` bumped in the same commit (current version `0.2.52`
      <!-- synccheck:ignore -->); changelog entry states plainly that this is a bug fix to a structurally
      unreachable signal, names the new opt-in config key, and states default-config behavior is unchanged.
- [ ] Include a literal `## Manual Verification` heading with natively-run command output (this series'
      established practice).

## Boundaries (explicitly not done in this task)

- Does not change `signal_first_buy()` or `signal_first_sell()` — they already select correctly.
- Does not change `_research_short_open_allowed()`'s P4/P5 AND-gate logic itself, or add/remove any gate —
  only fixes the upstream signal that feeds P4.
- Does not enable the new mode in `formal_evaluation_config()` or anywhere else by default — stays fully
  opt-in.
- Does not investigate or fix the separate, already-flagged `534→318` trade-count-drift / `max_single_day_
  loss_pct` drift item from the `2026-07-27` precheck-rerun `WORK_LOG.md` entry — that remains open,
  unrelated, and out of scope here.
- Does not re-run or update the historical `simnow_precheck_risk_report.json` baseline or any promotion
  decision — those all use default config, which this fix leaves byte-identical.
- Does not change the divergence *power* comparison itself (`_divergence_power`/`_bi_power`/
  `_macd_divergence_power`) — only which zhongshu is selected as the reference point before that comparison
  runs.

## Given to the Next Agent (dev = kimi-code)

1. Read this design doc in full, then `signals.py:282-372` (`signal_divergence_status`) and
   `signals.py:428-517` (`signal_first_buy`, the reference for correct selection) side by side before editing.
2. The fix is genuinely small (the selection line + a config branch); the bulk of the acceptance criteria is
   about **proving** it actually changes behavior under the opt-in mode and **proving** it changes nothing
   under the default — both directions need real test/manual evidence, not just "the diff looks right."
3. If extracting a shared helper for the departure-leg search (to avoid a third copy of the same one-liner),
   keep it a pure function taking `(bi_list, zhongshu_list)` — do not give it side effects or couple it to
   `STRATEGY_CONFIG` reads; let each caller decide whether to use it.
4. `_research_short_open_allowed`'s docstring (`positions.py:471-481`) already documents the P4/P5 symmetry
   intent — no change needed there, but re-read it to confirm the fix doesn't accidentally change P5's
   `_resonance_holds(..., direction="short", force_resonance=True)` path, which this task does not touch.
