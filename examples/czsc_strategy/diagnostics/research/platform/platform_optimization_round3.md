# Platform Optimization Round 3

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

Continue improving the current research base toward a stable platform.

Current research base:

```json
{
  "block_1buy_daily_down": true,
  "sc_short_multiplier": 0.75
}
```

Round 2 improved parameter robustness, but symbol-set stability remained weak:

- all5: pass
- no_A: pass
- no_SC: fail mainly due to scaled trade count
- core_AP_A_ZN: fail mainly due to scaled trade count and buy-hold comparison
- no_ZN: fail due to walk-forward and buy-hold comparison

## Hypothesis Tested

Maybe `no_SC` and `core_AP_A_ZN` fail because entry frequency is artificially suppressed by the 24h third-buy interval.

Tested candidate:

```json
{"interval_3buy": 0}
```

Evaluation mode:

- Candidate comparison: `base` vs `3buy_0h`
- Symbol sets: `no_SC`, `core_AP_A_ZN`
- Windows: `2023H1`, `2025H1`, `2026YTD`
- Source: `platform_entry_frequency_candidates_quick_windows.md`

## Result

| candidate | all5 trades | all5 PF | all5 WF | no_SC trades | core_AP_A_ZN trades |
|---|---:|---:|---:|---:|---:|
| base | 103 | 1.50 | 1/3 weak-window sample | 56 | 42 |
| 3buy_0h | 106 | 1.42 | 1/3 weak-window sample | 56 | 42 |

Third-buy interval relaxation did not add trades to the failing adjacent symbol sets.

It slightly increased all5 trades but worsened PF, drawdown, Sharpe, and Calmar.

## Conclusion

Entry cooldown is not the cause of the symbol-set fragility.

Do not continue tuning `interval_3buy` as a platform lever unless a separate signal-level audit shows many missed third-buy triggers.

## Next Direction

The remaining bottleneck is not cooldown; it is signal availability and weak-window regime behavior.

Recommended next tests:

1. Signal-level audit for `no_SC` and `core_AP_A_ZN`: count how many first/second/third-buy candidates are generated but blocked by daily filters, data sufficiency, or structure confirmation.
2. If candidates exist but are blocked by daily strictness, test a targeted second/third-buy daily-filter relaxation.
3. If candidates do not exist, accept that those symbol sets lack enough opportunity under the current 30-minute structure and treat ZN/SC as required diversification components rather than arbitrary removable symbols.

