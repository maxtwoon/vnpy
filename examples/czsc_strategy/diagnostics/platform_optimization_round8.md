# Platform Optimization Round 8

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


## Objective

Keep the SC short-weight neighborhood at least `4/6` and all5 walk-forward at least `7/9`, while improving adjacent symbol-set stability from `3/6` to at least `4/6`.

## Attribution

`no_A` failed only on `risk_adjusted_gt_buy_hold` under the previous best candidate.

The dedicated attribution report is:

- `no_a_failure_attribution.md`

Key finding:

- SC one-sell short was positive.
- SC third-buy long was the main OOS drag.
- Therefore the useful lever is not reducing SC short exposure; it is reducing SC third-buy long exposure.

## Final Candidate

`sc075_a_zn010_sc3buy_half + A/AP trailing 250/0.20`

Configuration summary:

- `block_1buy_daily_down = true`
- SC short multiplier: `0.75`
- Enable shorts on `SC888 / A888 / ZN888`
- A/ZN short weights: `0.10x` of normal sell weights
- SC third-buy weight: `0.15` instead of `0.30`
- A/AP trailing override: `250 / 0.20`

Full config artifact:

- `platform_final_candidate_config.json`

## Validation

### Symbol-Set Gate

Source:

- `platform_short_symbol_candidates_sc3buy_weight_full.md`

Result:

| set | pass |
|---|---|
| all5 | True |
| no_RB | True |
| no_SC | True |
| core_AP_A_ZN | True |
| no_A | True |
| no_ZN | False |

Symbol-set pass count: `5/6`.

### Final Candidate SC Neighborhood

Source:

- `sc_short_weight_neighborhood_final_candidate.md`

Result:

| multiplier | pass | WF |
|---:|---|---:|
| 0.75 | True | 7/9 |
| 0.80 | True | 7/9 |
| 0.847 | True | 7/9 |
| 0.85 | True | 7/9 |
| 0.90 | True | 6/9 |
| 1.00 | False | 5/9 |

SC-neighborhood pass count: `5/6`.

### Official Goal Check

Command:

```bash
python examples\czsc_strategy\diagnostics\check_platform_stability_goal.py ^
  --sc-neighbor examples\czsc_strategy\diagnostics\sc_short_weight_neighborhood_final_candidate.json ^
  --symbol-sets examples\czsc_strategy\diagnostics\platform_short_symbol_candidates_sc3buy_weight_full.json ^
  --candidate sc075_a_zn010_sc3buy_half ^
  --out-json examples\czsc_strategy\diagnostics\platform_stability_goal_status_final_candidate.json
```

Output:

```text
sc_neighbor=5/6 required>=4/6 pass=True
walk_forward=7/9 required>=7/9 pass=True
symbol_sets=5/6 required>=4/6 pass=True
platform_goal_passed=True
```

## Conclusion

The quantified platform-stability goal is achieved by reducing only the SC third-buy long weight while retaining SC short exposure and adding small A/ZN short exposure for breadth.
