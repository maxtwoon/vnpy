# SimNow Candidate V1 Robustness Summary

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


## Candidate

`expanded_short_sc_0847`

This candidate passes the hard OOS goal gate:

- Trades: `114`
- Profit factor: `1.4776`
- Max drawdown: `0.9501%`
- Sharpe: `1.1381`
- Calmar: `1.3482`
- Walk-forward: `6/9`
- Risk-adjusted return is better than equal-weight buy-and-hold.

## Neighborhood Result

Source: `sc_short_weight_neighborhood.md`

The candidate is not robust across the tested SC short-weight neighborhood:

- Lower weights `0.75` and `0.80` keep walk-forward at `6/9`, but fail risk-adjusted comparison versus buy-and-hold.
- Higher weights `0.85`, `0.90`, and `1.00` beat buy-and-hold on risk-adjusted metrics, but fail walk-forward with only `5/9` positive windows.
- The exact `0.847` point passes both sides.

## Interpretation

This is a narrow feasible point rather than a broad stable plateau. It should be treated as:

- acceptable for SimNow / paper-trading observation;
- not acceptable as default production configuration;
- not yet evidence of a generally robust strategy improvement.

## Required Follow-Up

- Run the profile in SimNow with explicit monitoring.
- Do not widen SC short exposure without a fresh walk-forward gate.
- Do not lower SC short exposure without rechecking buy-and-hold risk-adjusted comparison.
- Re-evaluate after each new month of data.

