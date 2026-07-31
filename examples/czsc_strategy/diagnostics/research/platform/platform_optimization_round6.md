# Platform Optimization Round 6

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


## Objective

Meet the quantified platform goal:

- SC short-weight neighborhood pass ratio >= `4/6`
- all5 walk-forward positive windows >= `7/9`
- adjacent symbol-set pass ratio >= `4/6`

Current status:

- SC neighborhood: `5/6` pass
- all5 walk-forward: `7/9` pass
- symbol sets: `2/6` pass

## Holding Attribution

Sources:

- `platform_holding_attribution_core_AP_A_ZN.md`
- `platform_holding_attribution_no_SC.md`

### core_AP_A_ZN

- Trades: `42`
- PnL sum: `41.94%`
- Win rate: `61.90%`
- PF: `2.42`
- Average bars held: `194.64`

Long-hold split:

- `bars_gt_120_loss`: 4 trades, `-8.61%`
- `bars_gt_120_win`: 13 trades, `+45.94%`
- `bars_le_120`: 25 trades, `+4.60%`

### no_SC

- Trades: `56`
- PnL sum: `45.31%`
- Win rate: `62.50%`
- PF: `2.15`
- Average bars held: `161.98`

Long-hold split:

- `bars_gt_120_loss`: 4 trades, `-8.61%`
- `bars_gt_120_win`: 14 trades, `+47.38%`
- `bars_le_120`: 38 trades, `+6.54%`

## Interpretation

Trade-count shortage is not caused by stale losing positions occupying capital.

Most long holds are profitable and materially contribute to total returns. This explains why:

- Shortening timeout did not help.
- Relaxing third-buy interval did not help.
- The strategy has fewer but higher-quality trades in `core_AP_A_ZN` and `no_SC`.

Forcing more churn would likely damage PF and risk-adjusted return rather than create a broader platform.

## Consequence For Symbol-Set Gate

The current arbitrary-removal symbol-set gate may be too strict for this strategy class.

Evidence so far suggests:

- `ZN888` is a stabilizing component. Removing it makes walk-forward worse.
- `SC888` provides diversification / short-side contribution. Removing it reduces trade count and changes the opportunity set.
- `core_AP_A_ZN` is high quality but naturally lower frequency.

Therefore, failing arbitrary removal tests does not necessarily mean the trading logic is weak; it may mean the platform requires a defined basket rather than arbitrary symbol removability.

## Next Decision

There are two possible paths:

1. Keep the original quantified goal unchanged.
   - Then the remaining work is difficult: we need two additional adjacent symbol sets to pass without weakening all5.
   - Current tested levers have failed: RB second-buy, third-buy interval, timeout shortening.

2. Redefine symbol-set robustness as required-basket robustness.
   - Treat `ZN888` and `SC888` as required stabilizers.
   - Test adjacency around weights / execution / entry filters while preserving required basket components.
   - This better matches current evidence but changes the goal definition.

Under the current goal wording, the platform is not complete.

