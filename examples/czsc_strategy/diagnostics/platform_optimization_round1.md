# Platform Optimization Round 1

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


## Goal

Build a stable platform that is not fragile across adjacent parameters, adjacent time windows, and adjacent symbol selections.

## Current Candidate

`expanded_short_sc_0847`

Current platform review:

- Parameter neighborhood: `1/6` pass.
- Time windows: `6/9` positive, but `3` non-positive windows.
- Symbol sets: `2/8` pass.
- Verdict: `not_a_stable_platform_yet`.

## Failure Attribution

Source: `platform_failure_attribution.md`

Most common symbol-set failures:

- `walk_forward_ge_2_3`: `6`
- `risk_adjusted_gt_buy_hold`: `4`
- `trades_ge_scaled_min`: `2`
- `pf_ge_1_2`: `2`

Weakest windows:

- `2023H1`: return `-1.34%`, PF `0.29`, Sharpe `-3.99`
- `2022H1`: return `-0.43%`, PF `0.77`, Sharpe `-0.75`
- `2026YTD`: return `-0.20%`, PF `0.50`, Sharpe `-0.71`

Weak-window attribution:

- `2023H1`: broad weakness; SC888, ZN888, A888, AP888, RB888 all negative. SC888 and ZN888 are the largest drags.
- `2022H1`: AP888 and SC888 are the largest drags; SC888 short side is notably weak.
- `2026YTD`: AP888 dominates the drawdown, especially AP second-buy losses.

## Tests Run

### Candidate: `A_ZN_only`

Change: remove AP888 from second-buy eligibility, keep A888 / ZN888.

Quick stability result on `all5 / no_SC / core_AP_A_ZN`:

- `all5`: fail, 111 trades, PF `1.42`, Sharpe `1.03`, Calmar `1.18`, WF `6/9`
- `no_SC`: fail, WF improves to `6/9`, but trade count and risk-adjusted buy-hold comparison fail
- `core_AP_A_ZN`: fail, WF improves to `6/9`, but trade count and risk-adjusted buy-hold comparison fail

Interpretation: removing AP second-buy repairs some walk-forward failures, but weakens all5 enough that the candidate loses the hard gate.

### Candidate: `AP_A_only`

Change: remove ZN888 from second-buy eligibility, keep AP888 / A888.

Quick stability result on `all5 / no_SC / core_AP_A_ZN`:

- `all5`: fail, 112 trades, PF `1.41`, Sharpe `1.09`, Calmar `1.19`, WF `5/9`
- `no_SC`: fail, WF `4/9`
- `core_AP_A_ZN`: fail, WF `5/9`

Interpretation: removing ZN second-buy is worse than removing AP second-buy and does not repair platform fragility.

## Round 1 Conclusion

Second-buy symbol eligibility is not the main platform lever.

- Removing AP second-buy helps walk-forward in some adjacent symbol sets, but breaks all5 risk-adjusted comparison.
- Removing ZN second-buy does not help.
- The dominant weakness is still broad weak-window exposure, especially first-buy behavior in 2023H1 / 2022H1 and AP second-buy losses in 2026YTD.

## Next Optimization Direction

Shift from second-buy list tuning to weak-environment control:

1. Add a research-only first-buy environment gate or first-buy risk reduction.
2. Test whether disabling or reducing first-buy exposure in weak daily structures improves `2023H1` and `2022H1` without destroying trade count.
3. Keep AP second-buy under special review, but do not remove it globally unless a broader platform candidate survives all symbol-set checks.
4. Re-run platform stability only after a candidate improves weak-window results, not after cosmetic parameter changes.

