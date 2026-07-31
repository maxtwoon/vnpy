# A43 P4 — MACD-Area Divergence Comparison Report

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


> RESEARCH-ONLY — Diagnostic only, not a trading recommendation.

Generated: 2026-07-12T09:06:40.792733
Window: 2026-04-24 ~ 2026-07-09

## Parameters

- Divergence models: amplitude vs macd
- MACD fast: 12
- MACD slow: 26
- MACD signal: 9

> MACD parameters are fixed at the 12/26/9 standard values. This report is evidence only and is not used to select or tune parameters.

## Summary

- Amplitude first-buy trades: 1
- MACD first-buy trades: 1

## Per-Symbol First-Buy Metrics

| Symbol | Model | Trades | Win Rate | PF | Avg Profit | Avg Loss | Return | Max DD |
|--------|-------|--------|----------|----|------------|----------|--------|--------|
| AP888 | amplitude | 1 | 0.0% | 0.00 | 0.00% | 2.67% | -0.90% | 1.18% |
| AP888 | macd | 1 | 0.0% | 0.00 | 0.00% | 2.67% | -0.90% | 1.18% |
| RB888 | — | — | — | — | — | — | — | macd_error: 交易周期数据不足: 需要至少110根30分钟K线，实际95根 |
| SC888 | amplitude | 0 | 0.0% | 0.00 | 0.00% | 0.00% | 0.00% | 0.00% |
| SC888 | macd | 0 | 0.0% | 0.00 | 0.00% | 0.00% | 0.00% | 0.00% |
| A888 | — | — | — | — | — | — | — | macd_error: 交易周期数据不足: 需要至少110根30分钟K线，实际86根 |
| ZN888 | amplitude | 0 | 0.0% | 0.00 | 0.00% | 0.00% | 0.00% | 0.00% |
| ZN888 | macd | 0 | 0.0% | 0.00 | 0.00% | 0.00% | 0.00% | 0.00% |

## Interpretation

This report compares the legacy amplitude proxy for 背驰 against a standard MACD area measure on the post-P1 baseline.  It is read-only evidence; any decision to switch the default divergence model belongs to a future holdout-validated promotion step.
