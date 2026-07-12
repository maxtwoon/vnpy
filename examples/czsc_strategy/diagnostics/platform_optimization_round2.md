# Platform Optimization Round 2

<!-- RESEARCH-ONLY / NOT PROMOTION EVIDENCE -->

> ⚠️ **RESEARCH ONLY — NOT PROMOTION EVIDENCE**
>
> This report was produced using the historical out-of-sample window `2022-01-01~2026-04-24`, which was repeatedly used for parameter selection. High-precision weights such as `0.847` and any `GOAL PASSED` rows are gate-fitting signatures, not evidence of a robust trading discovery. This artifact is retained as negative / contaminated evidence only.
>
> - `is_promotion_evidence`: False
> - `research_only`: True
> - `used_data_windows`: `["2022-01-01~2026-04-24"]`
> - `decision_data_windows`: ['2026-04-24~present', 'SimNow observation']
> - `note`: Future validation must use post-2026-04-24 incremental data and SimNow observation before any promotion claim can be considered.


## Goal

Continue building a stable platform that is not fragile across adjacent parameters, adjacent time windows, and adjacent symbol selections.

## Change Tested

Research-only first-buy environment gate:

```json
{"block_1buy_daily_down": true}
```

Meaning:

- Suppress new first-buy entries when the daily confirmed BI direction is down.
- Existing first-buy positions still receive exit, stop-loss, timeout, and trailing-stop updates.
- Default strategy behavior is unchanged unless this research switch is explicitly enabled.

## Why This Was Tested

Round 1 showed that second-buy eligibility changes were not the main platform lever. Weak-window attribution pointed to broad first-buy damage in `2023H1` and `2022H1`, plus AP888 damage in `2026YTD`.

## Parameter Neighborhood Result

Source: `sc_short_weight_neighborhood_first_buy_gate.md`

`block_1buy_daily_down` changes SC short-weight neighborhood from a narrow point into a broad region:

| multiplier | pass | WF |
|---:|---|---:|
| 0.75 | True | 7/9 |
| 0.80 | True | 6/9 |
| 0.847 | True | 6/9 |
| 0.85 | True | 6/9 |
| 0.90 | True | 6/9 |
| 1.00 | False | 5/9 |

Parameter pass ratio improved from `1/6` to `5/6`.

This is the first real improvement toward the stable-platform target.

## Symbol-Set Result

### `block_1buy_daily_down`, multiplier `0.847`

Source: `first_buy_environment_candidates_block_daily_down_6sets.md`

- all5: pass
- symbol sets: `1/6`
- no_SC and core_AP_A_ZN improved to `6/9` walk-forward but still fail trade-count / buy-hold checks.
- no_A and no_ZN remain `5/9`.

### `block_1buy_daily_down`, multiplier `0.75`

Source: `first_buy_environment_candidates_block_daily_down_075_6sets.md`

- all5: pass
- all5 walk-forward: `7/9`
- symbol sets: `2/6`
- no_A becomes pass.
- no_ZN remains `5/9`.
- no_SC and core_AP_A_ZN still fail mainly due to scaled trade count.

## Interpretation

The first-buy daily-down gate is a useful platform improvement:

- It broadens the SC short-weight parameter neighborhood.
- It improves all5 time stability.
- It improves some adjacent symbol sets.

But it does not yet solve symbol-selection fragility:

- Symbol-set pass ratio is still only `2/6`, below the `2/3` platform gate.
- Removing SC or focusing on AP/A/ZN creates too few trades under the current entry rules.
- Removing ZN still hurts walk-forward robustness.

## Next Optimization Target

Keep `block_1buy_daily_down` as the new research base, then address symbol-set fragility:

1. Investigate no_SC and core_AP_A_ZN trade-count shortage.
2. Test whether a small third-buy or second-buy relaxation can add trades without reintroducing 2023H1 damage.
3. Investigate no_ZN weak windows; if ZN is a stabilizer, the platform may need explicit commodity-basket diversification rather than pretending symbol choice is arbitrary.
4. Re-run symbol-set stability after any entry-frequency change.

## Current Status

Not a completed stable platform yet.

Current best research base:

```json
{
  "block_1buy_daily_down": true,
  "sc_short_multiplier": 0.75
}
```

This base improves adjacent-parameter and adjacent-time robustness, but adjacent-symbol robustness remains incomplete.

