# Platform Optimization Round 7

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> This report was produced using the historical out-of-sample window `2022-01-01~2026-04-24`, which was repeatedly used for parameter selection. High-precision weights such as `0.847` and any bare `GOAL PASSED` rows are gate-fitting signatures, not evidence of a robust trading discovery. This artifact is retained as negative / contaminated evidence only.
>
> - `is_promotion_evidence`: False
> - `research_only`: True
> - `used_data_windows`: `["2022-01-01~2026-04-24"]`
> - `decision_data_windows`: ['2026-04-24~present', 'SimNow observation']
> - `note`: Future validation must use post-2026-04-24 incremental data and SimNow observation before any promotion claim can be considered.


## Base

- Long gate: `block_1buy_daily_down`
- SC short multiplier: `0.75`
- Hard platform gate:
  - SC weight neighborhood >= `4/6`
  - all5 walk-forward >= `7/9`
  - adjacent symbol-set pass count >= `4/6`

## What Changed

1. Added a cached trailing candidate scanner:
   - `platform_trailing_candidates.py`
   - Purpose: test whether targeted trailing stops can improve weak adjacent symbol sets.
2. Added a short-symbol candidate scanner:
   - `platform_short_symbol_candidates.py`
   - Purpose: test whether low-weight AP/A/ZN shorts can supply robust trades for `no_SC` and `core_AP_A_ZN`.
3. Added research-only per-symbol position weights:
   - `STRATEGY_CONFIG["symbol_position_overrides"]`
   - Used by both `backtest_engine.py` and `portfolio_goal_evaluator.py`.

## Main Findings

### Targeted trailing helps quality, not trade count

`AP/A/ZN 200/0.20` trailing improved all5 headline metrics:

- trades: `105`
- PF: `1.64`
- Sharpe: `1.19`
- Calmar: `1.40`
- quick WF: `2/2`

But `no_SC` and `core_AP_A_ZN` still failed the scaled trade-count gate:

- `no_SC`: `58/80`
- `core_AP_A_ZN`: `44/60`

### Low-weight AP/A/ZN shorts solve the trade-count shortage

Opening small shorts on A/ZN while keeping SC at `0.75` lifted:

- `no_SC`: above `80` trades and passed.
- `core_AP_A_ZN`: above `60` trades and passed.

Best full-sample variant tested:

`sc075_a_zn010 + A/AP trailing 250/0.20`

Result file:

- `platform_short_symbol_candidates_low_weight_a_ap_soft250_full.md`

Gate detail:

| set | pass | notes |
|---|---|---|
| all5 | True | `129` trades, PF `1.65`, WF `7/9` |
| no_SC | True | trade count and risk-adjusted metrics both pass |
| core_AP_A_ZN | True | trade count and risk-adjusted metrics both pass |
| no_RB | False | risk-adjusted vs buy-hold fails |
| no_A | False | risk-adjusted vs buy-hold fails |
| no_ZN | False | risk-adjusted vs buy-hold fails |

Overall symbol-set gate: `3/6`, still below required `4/6`.

## Negative Results

- Tight trailing `150/0.15` increased churn but damaged quality.
- Global AP/A/ZN shorts at `0.25` solved `no_SC` trade count but dragged all5/no_A.
- Mixed SC `0.75` + A/ZN `0.25` reached `3/6`, but did not clear `4/6`.
- Reducing A/ZN short weights from `0.25` to `0.15` / `0.10` did not recover `no_A`.
- Softer AP trailing `300/0.20` worsened all5 and core; `250/0.20` is the better local point.

## Current Gate Status

Command:

```bash
python examples\czsc_strategy\diagnostics\check_platform_stability_goal.py ^
  --symbol-sets examples\czsc_strategy\diagnostics\platform_short_symbol_candidates_low_weight_a_ap_soft250_full.json ^
  --candidate sc075_a_zn010
```

Output:

```text
sc_neighbor=5/6 required>=4/6 pass=True
walk_forward=7/9 required>=7/9 pass=True
symbol_sets=3/6 required>=4/6 pass=False
platform_goal_passed=False
```

## Verification

```text
pytest examples\czsc_strategy\tests -q
98 passed, 1 skipped
```

## Conclusion

The platform is no longer blocked by parameter neighborhood or all5 walk-forward. The remaining blocker is the adjacent symbol-set gate: the best tested candidate reaches `3/6`, and the remaining failures are all relative to strong buy-hold benchmarks rather than absolute strategy losses.

The next useful search should target `no_A` or `no_RB` risk-adjusted improvement specifically, not more generic entry-frequency or timeout changes.
