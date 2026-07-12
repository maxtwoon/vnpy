# Platform Optimization Round 4

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


## Quantified Goal

On the base:

```json
{
  "block_1buy_daily_down": true,
  "sc_short_multiplier": 0.75
}
```

Reach:

- SC short-weight neighborhood pass ratio >= `4/6`
- all5 walk-forward positive windows >= `7/9`
- adjacent symbol-set pass ratio >= `4/6`

## Current Gate Status

Source: `check_platform_stability_goal.py`

- SC short-weight neighborhood: `5/6` pass
- all5 walk-forward: `7/9` pass
- adjacent symbol sets: `2/6` fail

The only remaining quantified gap is symbol-set robustness.

## Hypothesis Tested

`no_SC` fails only by trade count, so adding RB888 second-buy eligibility might add enough trades without damaging all5.

Candidate:

```json
{
  "enable_2buy_symbols": ["AP888", "RB888", "A888", "ZN888"],
  "block_1buy_daily_down": true,
  "sc_short_multiplier": 0.75
}
```

Source: `second_buy_platform_candidates_rb_block1buy_075.md`

## Result

| set | pass | trades | WF | failing checks |
|---|---|---:|---:|---|
| all5 | True | 104 | 7/9 | - |
| no_SC | False | 57 | 6/9 | trades_ge_scaled_min |
| core_AP_A_ZN | False | 42 | 6/9 | trades_ge_scaled_min, risk_adjusted_gt_buy_hold |
| no_RB | False | 89 | 6/9 | risk_adjusted_gt_buy_hold |
| no_ZN | False | 90 | 5/9 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

Compared with the current base, RB second-buy eligibility adds only one all5 trade and one no_SC trade.

## Conclusion

RB888 second-buy eligibility is not a useful platform lever.

The symbol-set gap is not caused by RB second-buy being disabled.

## Next Direction

The remaining evidence points to two structural facts:

1. `no_SC` and `core_AP_A_ZN` fail because the current 30-minute structure does not generate enough eligible entries after the first-buy daily-down filter.
2. `no_ZN` fails because ZN appears to be a stabilizing diversification component; removing it weakens walk-forward and buy-hold-relative metrics.

Next useful work:

- Run a signal-funnel audit on `no_SC` and `core_AP_A_ZN` under the current base to locate whether entries are absent at the signal layer or blocked by filters.
- If signals exist but are blocked, test targeted daily-filter relaxation for second/third-buy only.
- If signals are absent, redefine symbol-set robustness around required basket components rather than arbitrary removals.

