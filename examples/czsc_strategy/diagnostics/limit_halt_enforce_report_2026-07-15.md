# A67 — Limit/Halt Enforce-Mode Diagnostic

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



Generated: 2026-07-15T12:30:15.602790
Window: 2026-04-24 ~ 2026-07-09

## Totals

| Mode | Trades | Wins | Losses | Total Return |
|------|-------:|-----:|-------:|-------------:|
| off | 2 | 0 | 0 | -0.90% |
| aware | 2 | 0 | 0 | -0.90% |
| enforce | 2 | 0 | 0 | -0.90% |

## Per-symbol summary

| Symbol | Mode | Trades | Win Rate | Return | Max DD | Sharpe | Rejected |
|--------|------|-------:|---------:|-------:|-------:|-------:|---------:|
| AP888 | off | 2 | 0.0% | -0.90% | 1.18% | -2.69 | 0 |
| AP888 | aware | 2 | 0.0% | -0.90% | 1.18% | -2.69 | 0 |
| AP888 | enforce | 2 | 0.0% | -0.90% | 1.18% | -2.69 | 0 |
| RB888 | - | - | - | - | - | - | error: off_error: 交易周期数据不足: 需要至少110根30分钟K线，实际98根; aware_error: 交易周期数据不足: 需要至少110根30分钟K线，实际98根; enforce_error: 交易周期数据不足: 需要至少110根30分钟K线，实际98根 |
| SC888 | off | 0 | 0.0% | 0.00% | 0.00% | 0.00 | 0 |
| SC888 | aware | 0 | 0.0% | 0.00% | 0.00% | 0.00 | 0 |
| SC888 | enforce | 0 | 0.0% | 0.00% | 0.00% | 0.00 | 0 |
| A888 | - | - | - | - | - | - | error: off_error: 交易周期数据不足: 需要至少110根30分钟K线，实际86根; aware_error: 交易周期数据不足: 需要至少110根30分钟K线，实际86根; enforce_error: 交易周期数据不足: 需要至少110根30分钟K线，实际86根 |
| ZN888 | off | 0 | 0.0% | 0.00% | 0.00% | 0.00 | 0 |
| ZN888 | aware | 0 | 0.0% | 0.00% | 0.00% | 0.00 | 0 |
| ZN888 | enforce | 0 | 0.0% | 0.00% | 0.00% | 0.00 | 0 |

## Note

This report is evidence only and is not used to select or tune parameters. No threshold tuning is performed from this report in-task. Window chosen as the most recent continuous post-2026-04-24 period available.

## Methodology

Methodology — each backtest is run with the same strategy configuration and the same post-2026-04-24 price window, varying only ``limit_halt_model``. ``off`` is the legacy baseline with no limit/halt tagging. ``aware`` tags fills that occur at the directionally-relevant daily limit band but does not block them. ``enforce`` rejects fills that occur at the unexecutable limit band (long entry at upper limit, long exit at lower limit, short entry at lower limit, short exit at upper limit) and retries on the next bar. The comparison is reported as honest measurement, not as evidence that any mode is superior.
