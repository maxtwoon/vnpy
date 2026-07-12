# A47 P8a — Exit-Model Diagnostic

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


**RESEARCH-ONLY — Diagnostic only, not a trading recommendation.**

Generated: 2026-07-12T17:31:05.342674
Window: 2026-04-24 ~ 2026-07-09

## Totals

| Mode | Trades | Wins | Losses |
|------|-------:|-----:|-------:|
| legacy | 2 | 0 | 2 |
| structural_atr | 3 | 2 | 1 |

## Per-symbol summary

| Symbol | Mode | Trades | Win Rate | Return | Max DD | Avg Give-Back | Avg Early-Exit |
|--------|------|-------:|---------:|-------:|-------:|--------------:|---------------:|
| AP888 | legacy | 2 | 0.0% | -0.90% | 1.18% | 5.01% | 4.78% |
| AP888 | structural_atr | 3 | 66.7% | -0.54% | 0.87% | 2.92% | 2.66% |
| RB888 | - | - | - | - | - | error: legacy_error: 交易周期数据不足: 需要至少110根30分钟K线，实际95根; structural_atr_error: 交易周期数据不足: 需要至少110根30分钟K线，实际95根 | - |
| SC888 | legacy | 0 | 0.0% | 0.00% | 0.00% | 0.00% | 0.00% |
| SC888 | structural_atr | 0 | 0.0% | 0.00% | 0.00% | 0.00% | 0.00% |
| A888 | - | - | - | - | - | error: legacy_error: 交易周期数据不足: 需要至少110根30分钟K线，实际86根; structural_atr_error: 交易周期数据不足: 需要至少110根30分钟K线，实际86根 | - |
| ZN888 | legacy | 0 | 0.0% | 0.00% | 0.00% | 0.00% | 0.00% |
| ZN888 | structural_atr | 0 | 0.0% | 0.00% | 0.00% | 0.00% | 0.00% |

## Note

This report is evidence only and is not used to select or tune parameters. No threshold tuning is performed from this report in-task. Window chosen as the most recent continuous post-2026-04-24 period available.
