# A46 P7 — Short-Enable Diagnostic

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

Generated: 2026-07-12T16:33:56.240433
Window: 2026-04-24 ~ 2026-07-09

## Totals

| Mode | Total trades | Short trades | Both-long-short bars |
|------|-------------:|-------------:|---------------------:|
| long_only | 0 | 0 | 0 |
| independent | 0 | 0 | 0 |
| router | 0 | 0 | 0 |

## Per-symbol summary

| Symbol | Mode | Trades | Long WR | Long Exp | Short WR | Short Exp | Return | Max DD | Both-L-S |
|--------|------|-------:|--------:|---------:|---------:|----------:|-------:|-------:|---------:|
| RB888 | - | - | - | - | - | - | error: router_error: 交易周期数据不足: 需要至少110根30分钟K线，实际95根 | - | - |
| SC888 | long_only | 0 | 0.0% | 0.00% | 0.0% | 0.00% | 0.00% | 0.00% | 0 |
| SC888 | independent | 0 | 0.0% | 0.00% | 0.0% | 0.00% | 0.00% | 0.00% | 0 |
| SC888 | router | 0 | 0.0% | 0.00% | 0.0% | 0.00% | 0.00% | 0.00% | 0 |

## Note

This report is evidence only and is not used to select or tune parameters. No threshold tuning is performed from this report in-task. Window chosen as the most recent continuous 4-month period available for both RB888 and SC888.
