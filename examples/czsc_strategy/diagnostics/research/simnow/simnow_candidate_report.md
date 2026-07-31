# SimNow Candidate Report

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


## Recommended Candidate

- candidate: `expanded` for paper/SimNow observation, not default live trading.
- base: current `combined` candidate.
- expansion: AP888/A888 are exempt from the 3% second-buy chase filter; RB888/SC888 keep tight trailing `150/0.15` and second-buy disabled by symbol gate.

## OOS Baseline vs Combined

| scenario | return | drawdown | trades | win_rate |
|---|---:|---:|---:|---:|
| baseline | -0.52% | 4.66% | 92 | 49.86% |
| combined | 1.16% | 3.27% | 89 | 56.48% |

## Rolling Stability

| scenario | positive_return_windows | non_worse_drawdown_windows | total_windows |
|---|---:|---:|---:|
| combined | 6 | 9 | 9 |
| expanded | 6 | 9 | 9 |

| window | scenario | return_delta | drawdown_delta | trade_delta |
|---|---|---:|---:|---:|
| 2022H1 | combined | -0.30% | -0.10% | -4 |
| 2022H2 | combined | 0.51% | -0.67% | -4 |
| 2023H1 | combined | 0.20% | -0.41% | -2 |
| 2023H2 | combined | -0.00% | -0.27% | 2 |
| 2024H1 | combined | -0.07% | -0.20% | 1 |
| 2024H2 | combined | 0.59% | -0.60% | -1 |
| 2025H1 | combined | 0.43% | -0.42% | 0 |
| 2025H2 | combined | 0.01% | -0.14% | 0 |
| 2026YTD | combined | 0.23% | -0.27% | 0 |
| 2022H1 | expanded | -0.21% | -0.19% | -3 |
| 2022H2 | expanded | 0.61% | -0.62% | -3 |
| 2023H1 | expanded | 0.20% | -0.41% | -2 |
| 2023H2 | expanded | -0.00% | -0.27% | 2 |
| 2024H1 | expanded | -0.07% | -0.20% | 1 |
| 2024H2 | expanded | 0.59% | -0.60% | -1 |
| 2025H1 | expanded | 0.43% | -0.42% | 0 |
| 2025H2 | expanded | 0.01% | -0.14% | 0 |
| 2026YTD | expanded | 0.23% | -0.27% | 0 |

## Extreme Contribution

| metric | OOS value |
|---|---:|
| total_impact | 8.39% |
| without_top1_positive | 5.87% |
| without_top3_positive | 2.90% |
| top1_positive_share | 30.02% |
| top3_positive_share | 65.43% |

## Key Behavior Queue

| type | symbol | strategy | open_dt | reason | impact | review_hint |
|---|---|---|---|---|---:|---|
| removed | SC888 | 二买多头 | 2026-04-07 14:59:00 | stop_loss | 2.52% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| changed | RB888 | 三买多头 | 2025-12-08 09:29:00 | trailing_stop | 1.63% | strong: tighter trailing locked profit or reduced give-back. |
| changed | SC888 | 一买多头 | 2026-04-02 23:29:00 | trailing_stop | 1.34% | strong: tighter trailing locked profit or reduced give-back. |
| removed | SC888 | 二买多头 | 2025-09-03 14:29:00 | stop_loss | 0.76% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2026-03-30 21:40:00 | stop_loss | 0.72% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2026-04-13 14:59:00 | stop_loss | 0.68% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2025-05-20 14:29:00 | stop_loss | 0.67% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | RB888 | 二买多头 | 2025-02-19 09:59:00 | stop_loss | 0.64% | strong: filtered trade avoided a stop-loss; replay to confirm chase entry or weak structure. |
| removed | SC888 | 二买多头 | 2025-09-10 01:59:00 | trailing_stop | -0.45% | negative: profitable trade was filtered out; check whether the filter is too strict. |
| removed | SC888 | 二买多头 | 2025-08-18 23:29:00 | trailing_stop | -0.45% | negative: profitable trade was filtered out; check whether the filter is too strict. |

## SimNow Observation Metrics

- Track per-symbol return, drawdown, trade count, win rate and stop-loss weighted loss weekly.
- Track RB888/SC888 trailing-stop exits separately; confirm tight trailing reduces drawdown without cutting all large winners.
- Track second-buy stop-loss count. The candidate only makes sense if bad second-buy stop-losses remain suppressed.
- Compare live trade frequency against the rolling-window historical range; abnormal silence is also a failure mode.

## Kill Switches

- Any single symbol drawdown exceeds 1.5x its OOS backtest drawdown.
- Portfolio max losing streak exceeds 10, the baseline OOS value.
- Stop-loss weighted loss returns near baseline OOS level (`-21.69%`) on a rolling basis.
- RB888/SC888 generate new stop-loss clusters after the tight trailing override.
- Trade count deviates by more than 50% from the comparable rolling-window historical frequency without an obvious market-regime reason.

## Decision

Use `expanded` only as a SimNow candidate. Keep default production config unchanged until live-paper behavior confirms that the improvement is not concentrated in one or two historical trades.
