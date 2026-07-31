# Platform Stability Review

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


- candidate: `expanded_short_sc_0847`
- verdict: `not_a_stable_platform_yet`
- overall_passed: `False`

## Gate

- Parameter neighborhood: at least two thirds of tested adjacent points must pass.
- Time windows: at least two thirds positive, with no more than two non-positive windows.
- Symbol selection: at least two thirds of adjacent symbol sets must pass.

## Parameter Neighborhood

- passed: `False`
- pass ratio: `1/6` = `16.67%`

| multiplier | pass | trades | PF | sharpe | calmar | WF |
|---:|---|---:|---:|---:|---:|---:|
| 0.75 | False | 114 | 1.46 | 1.09 | 1.27 | 6/9 |
| 0.8 | False | 114 | 1.47 | 1.12 | 1.31 | 6/9 |
| 0.847 | True | 114 | 1.48 | 1.14 | 1.35 | 6/9 |
| 0.85 | False | 114 | 1.48 | 1.14 | 1.35 | 5/9 |
| 0.9 | False | 114 | 1.49 | 1.16 | 1.39 | 5/9 |
| 1.0 | False | 114 | 1.51 | 1.21 | 1.48 | 5/9 |

## Time Stability

- passed: `False`
- positive windows: `6/9` = `66.67%`
- non-positive windows: `3`

| window | return | PF | sharpe | calmar | trades |
|---|---:|---:|---:|---:|---:|
| 2022H1 | -0.43% | 0.77 | -0.75 | -1.26 | 67 |
| 2022H2 | 0.48% | 1.28 | 1.18 | 1.45 | 69 |
| 2023H1 | -1.34% | 0.29 | -3.99 | -1.83 | 50 |
| 2023H2 | 0.00% | 1.02 | 0.00 | 0.00 | 41 |
| 2024H1 | 0.47% | 1.25 | 1.21 | 2.57 | 44 |
| 2024H2 | 0.29% | 1.12 | 0.51 | 0.94 | 47 |
| 2025H1 | 0.34% | 1.13 | 0.82 | 1.29 | 37 |
| 2025H2 | 1.61% | 3.09 | 2.56 | 11.62 | 52 |
| 2026YTD | -0.20% | 0.50 | -0.71 | -1.87 | 24 |

## Symbol-Set Stability

- passed: `False`
- proven pass ratio: `2/8` = `25.00%`

| set | symbols | pass | evidence |
|---|---|---|---|
| all5 | AP888, RB888, SC888, A888, ZN888 | True | symbol_set_stability_scan.json |
| no_RB | AP888, SC888, A888, ZN888 | False | symbol_set_stability_scan.json |
| no_SC | AP888, RB888, A888, ZN888 | False | symbol_set_stability_scan.json |
| core_AP_A_ZN | AP888, A888, ZN888 | False | symbol_set_stability_scan.json |
| no_AP | RB888, SC888, A888, ZN888 | False | symbol_set_stability_scan_extra.json |
| no_A | AP888, RB888, SC888, ZN888 | True | symbol_set_stability_scan_extra.json |
| no_ZN | AP888, RB888, SC888, A888 | False | symbol_set_stability_scan_extra.json |
| metals_energy | RB888, SC888, ZN888 | False | symbol_set_stability_scan_extra.json |

### Missing Symbol Evidence


## Next Optimization Target

The current candidate is a narrow feasible point. The next search should optimize for a platform: multiple adjacent SC short weights, multiple adjacent half-year windows, and multiple adjacent symbol sets must pass together before promotion.