# SimNow Candidate V1 Monitoring

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


## Profile

- Profile: `simnow_candidate_v1_watchlist`
- Config: `simnow_candidate_v1.json`
- Candidate scenario: `expanded_short_sc_0847`
- Status: watchlist only; do not promote to default/live production without paper-trading evidence.

## Why Watchlist, Not Default

The hard OOS gate passes, but neighborhood robustness is weak:

| SC short multiplier | Gate | Main failure |
|---:|---|---|
| 0.75 | fail | risk-adjusted return below buy-and-hold |
| 0.80 | fail | risk-adjusted return below buy-and-hold |
| 0.847 | pass | none |
| 0.85 | fail | walk-forward falls to 5/9 positive windows |
| 0.90 | fail | walk-forward falls to 5/9 positive windows |
| 1.00 | fail | walk-forward falls to 5/9 positive windows |

This is a narrow parameter point, so SimNow should validate behavior rather than assume robustness.

## Daily Checks

- Confirm all generated signals use next-bar execution, not same-bar fill.
- Record trade count by symbol and sub-strategy.
- Record SC888 short trades separately.
- Record stop-loss count and weighted stop-loss loss.
- Record trailing-stop exits for RB888 and SC888.
- Confirm no symbol outside `SC888` opens short positions.

## Weekly Checks

- Portfolio return, max drawdown, Sharpe proxy, Calmar proxy.
- Per-symbol return and drawdown.
- Stop-loss weighted loss versus baseline OOS reference.
- Trade frequency versus comparable rolling-window history.
- SC888 short contribution split by one-sell / three-sell.

## Kill Switches

Stop or demote the candidate if any condition is hit:

- Portfolio max losing streak exceeds `10`.
- Any single-symbol drawdown exceeds `1.5x` its OOS backtest drawdown.
- SC888 short side has `3` consecutive stop-loss exits.
- Weighted stop-loss loss trends back toward baseline OOS level `-21.69%`.
- 30-day trade count is more than `50%` below or above comparable historical rolling-window frequency.
- SC888 short trades are net negative after at least `10` paper trades.
- Live/paper fills deviate materially from next-bar open assumptions.

## Promotion Criteria

Promotion from watchlist to stronger candidate requires:

- At least one complete monthly paper-trading cycle.
- No kill switch triggered.
- SC888 short side positive or near-flat with reduced drawdown.
- Stop-loss weighted loss remains materially below baseline.
- Trade frequency is within historical range.

## Commands

```powershell
python examples\czsc_strategy\diagnostics\check_portfolio_goal_gate.py
pytest examples\czsc_strategy\tests -q
```

