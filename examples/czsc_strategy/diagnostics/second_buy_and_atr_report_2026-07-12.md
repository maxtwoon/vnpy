# A45 P6 — Second-Buy Hard-Gate + ATR Chop Filter Diagnostic

**RESEARCH-ONLY — Diagnostic only, not a trading recommendation.**

Generated: 2026-07-12T14:25:29.813436
Window: 2026-04-24 ~ 2026-07-09

## ATR configuration

- period: 14
- lookback: 100
- percentile floor: 0.3

## Second-buy trades by mode

| Mode | Second-buy trades |
|------|------------------:|
| baseline | 1 |
| gated | 0 |
| off | 0 |

## Per-symbol summary

| Symbol | Mode | Total trades | 2nd-buy trades | 2nd-buy WR | Return | Max DD |
|--------|------|-------------:|---------------:|-----------:|-------:|-------:|
| AP888 | baseline | 2 | 1 | 0.0% | -0.90% | 1.18% |
| AP888 | gated | 1 | 0 | 0.0% | -0.27% | 0.55% |
| AP888 | off | 1 | 0 | 0.0% | -0.27% | 0.55% |
| RB888 | - | - | - | - | error: off_error: 交易周期数据不足: 需要至少110根30分钟K线，实际95根 | - |
| SC888 | baseline | 0 | 0 | 0.0% | 0.00% | 0.00% |
| SC888 | gated | 0 | 0 | 0.0% | 0.00% | 0.00% |
| SC888 | off | 0 | 0 | 0.0% | 0.00% | 0.00% |
| A888 | - | - | - | - | error: off_error: 交易周期数据不足: 需要至少110根30分钟K线，实际86根 | - |
| ZN888 | baseline | 0 | 0 | 0.0% | 0.00% | 0.00% |
| ZN888 | gated | 0 | 0 | 0.0% | 0.00% | 0.00% |
| ZN888 | off | 0 | 0 | 0.0% | 0.00% | 0.00% |

## Entry win-rate by ATR percentile (baseline mode)

| Symbol | Bucket | Count | Wins | Win rate |
|--------|--------|------:|-----:|---------:|
| AP888 | >=p70 | 2 | 0 | 0.0% |
| SC888 | - | - | - | - |
| ZN888 | - | - | - | - |

## Note

This report is evidence only and is not used to select or tune parameters. atr_percentile_floor is NOT adjusted based on this report in-task.
