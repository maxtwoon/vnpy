# A44 P5 — Multi-Level Resonance Entry Filter Comparison

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

Generated: 2026-07-12T12:50:01.728707
Window: 2026-04-24 ~ 2026-07-09

## Aggregate trade counts

| Mode | Total trades |
|------|-------------:|
| off | 2 |
| daily | 0 |
| daily_4h | 0 |

## Per-symbol summary

| Symbol | Mode | Trades | Win rate | PF | Return | Max DD |
|--------|------|--------|----------|----|--------|--------|
| AP888 | off | 2 | 0.0% | 0.00 | -0.90% | 1.18% |
| AP888 | daily | 0 | 0.0% | 0.00 | 0.00% | 0.00% |
| AP888 | daily_4h | 0 | 0.0% | 0.00 | 0.00% | 0.00% |
| RB888 | - | - | - | - | error: daily_4h_error: 交易周期数据不足: 需要至少110根30分钟K线，实际95根 | - |
| SC888 | off | 0 | 0.0% | 0.00 | 0.00% | 0.00% |
| SC888 | daily | 0 | 0.0% | 0.00 | 0.00% | 0.00% |
| SC888 | daily_4h | 0 | 0.0% | 0.00 | 0.00% | 0.00% |
| A888 | - | - | - | - | error: daily_4h_error: 交易周期数据不足: 需要至少110根30分钟K线，实际86根 | - |
| ZN888 | off | 0 | 0.0% | 0.00 | 0.00% | 0.00% |
| ZN888 | daily | 0 | 0.0% | 0.00 | 0.00% | 0.00% |
| ZN888 | daily_4h | 0 | 0.0% | 0.00 | 0.00% | 0.00% |

## Note

This report is evidence only and is not used to select or tune parameters. No numeric thresholds were introduced; 'constructive' reuses existing categorical signals.
