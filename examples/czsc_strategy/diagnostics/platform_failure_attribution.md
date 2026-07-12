# Platform Failure Attribution

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


- candidate: `expanded_short_sc_0847`
- verdict: `not_a_stable_platform_yet`

## Failure Counts Across Symbol Sets

| check | count |
|---|---:|
| walk_forward_ge_2_3 | 6 |
| risk_adjusted_gt_buy_hold | 4 |
| trades_ge_scaled_min | 2 |
| pf_ge_1_2 | 2 |
| sharpe_ge_0_5 | 1 |
| calmar_ge_0_5 | 1 |

## Weak Time Windows

| window | return | PF | sharpe | calmar | trades |
|---|---:|---:|---:|---:|---:|
| 2023H1 | -1.34% | 0.29 | -3.99 | -1.83 | 50 |
| 2022H1 | -0.43% | 0.77 | -0.75 | -1.26 | 67 |
| 2026YTD | -0.20% | 0.50 | -0.71 | -1.87 | 24 |
| 2023H2 | 0.00% | 1.02 | 0.00 | 0.00 | 41 |
| 2024H2 | 0.29% | 1.12 | 0.51 | 0.94 | 47 |
| 2025H1 | 0.34% | 1.13 | 0.82 | 1.29 | 37 |
| 2024H1 | 0.47% | 1.25 | 1.21 | 2.57 | 44 |
| 2022H2 | 0.48% | 1.28 | 1.18 | 1.45 | 69 |
| 2025H2 | 1.61% | 3.09 | 2.56 | 11.62 | 52 |

## Symbol-Set Details

| set | pass | symbols | return | PF | sharpe | calmar | WF | failing_checks |
|---|---|---|---:|---:|---:|---:|---:|---|
| all5 | True | AP888, RB888, SC888, A888, ZN888 | 1.83% | 1.48 | 1.14 | 1.35 | 6/9 | - |
| no_RB | False | AP888, SC888, A888, ZN888 | 2.15% | 1.49 | 1.10 | 1.29 | 5/9 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
| no_SC | False | AP888, RB888, A888, ZN888 | 2.68% | 2.39 | 1.58 | 2.45 | 5/9 | trades_ge_scaled_min, walk_forward_ge_2_3 |
| core_AP_A_ZN | False | AP888, A888, ZN888 | 3.40% | 2.63 | 1.56 | 2.55 | 5/9 | trades_ge_scaled_min, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
| no_AP | False | RB888, SC888, A888, ZN888 | 1.03% | 1.16 | 0.55 | 0.54 | 5/9 | pf_ge_1_2, walk_forward_ge_2_3 |
| no_A | True | AP888, RB888, SC888, ZN888 | 1.37% | 1.40 | 0.78 | 0.83 | 6/9 | - |
| no_ZN | False | AP888, RB888, SC888, A888 | 2.00% | 1.46 | 1.19 | 1.20 | 5/9 | walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |
| metals_energy | False | RB888, SC888, ZN888 | 0.15% | 1.01 | 0.08 | 0.07 | 5/9 | pf_ge_1_2, sharpe_ge_0_5, calmar_ge_0_5, walk_forward_ge_2_3, risk_adjusted_gt_buy_hold |

## Priority

- Repair walk-forward robustness first; it is the most common failure across adjacent symbol sets.
- Focus diagnostics on 2023H1, 2026YTD, and 2022H1 before adding new parameters.
- Treat SC short weight as a secondary lever; current failures are mostly window robustness rather than OOS headline metrics.
- Prefer candidate rules that improve no_RB, no_SC, no_ZN, and core_AP_A_ZN together.